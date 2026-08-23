import hashlib
import importlib.util
import json
import os
import stat
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("train_airi_behavior_lora_test",
                                              HERE / "train_airi_behavior_lora.py")
assert SPEC is not None and SPEC.loader is not None
trainer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trainer)

try:  # CI 러너에는 torch 스택이 없다 — 스타일 트레이너 테스트와 같은 스킵 규약.
    import torch  # noqa: F401
    import peft  # noqa: F401
    import transformers  # noqa: F401
    TORCH_STACK = True
except Exception:  # pragma: no cover - environment probe
    TORCH_STACK = False


def dataset_lines(count: int = 8) -> bytes:
    rows = []
    for index in range(count):
        rows.append({"id": f"bseed-register-{index:04d}", "split": "train",
                     "behavior": "register",
                     "messages": [
                         {"role": "system", "content": "너는 AIRI라는 방송 동료야."},
                         {"role": "user", "content": f"[YouTube] 질문 {index}이야, 대답해 줄래요?"},
                         {"role": "assistant", "content": f"응, {index}번째 답이야! 편하게 물어봐!"},
                     ]})
    return ("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) for row in rows) + "\n").encode("utf-8")


def v4_row(identifier: str, split: str = "train", group: str = "group-a",
           token: str | None = "amber") -> dict:
    return {"id": identifier, "split": split,
            "schema_version": "airi.broadcast-continuity.v4",
            "scenario_group": group, "semantic_family": "callback",
            "evidence_surface": "native-context", "required_token": token,
            "fact_tokens": [token] if token else [],
            "review": {"user_aggregate_authorized": True, "adoption_authorized": False},
            "messages": [
                {"role": "system", "content": "AIRI broadcast"},
                {"role": "user", "content": "Remember amber"},
                {"role": "assistant", "content": "I remember amber."},
            ]}


def pinned_payload(rows: list[dict]) -> tuple[bytes, str]:
    payload = ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()
    return payload, hashlib.sha256(payload).hexdigest()


class ContractTests(unittest.TestCase):
    def test_adapter_initialization_requires_complete_exact_artifact_and_fresh_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = root / "prior-adapter"
            adapter.mkdir()
            model = adapter / "adapter_model.safetensors"
            config = adapter / "adapter_config.json"
            model.write_bytes(b"test adapter weights")
            config.write_text(json.dumps({"peft_type": "LORA", "task_type": "CAUSAL_LM",
                                          "r": 16, "lora_alpha": 32,
                                          "lora_dropout": 0.05,
                                          # PEFT serializes all-linear as this expanded,
                                          # order-independent E2 projection set.
                                          "target_modules": ["up_proj", "o_proj", "v_proj",
                                                             "down_proj", "k_proj", "q_proj",
                                                             "gate_proj"]}), encoding="utf-8")
            inventory = [{"path": path.name, "bytes": path.stat().st_size,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for path in (config, model)]
            manifest = {"schema_version": "airi.behavior-adapter-artifact.v1",
                        "run_id": "prior-run", "pins": {"model_weight_sha256": "b" * 64},
                        "files": inventory}
            manifest_path = adapter / "artifact-manifest.json"
            manifest_path.write_bytes(trainer._canonical_json_bytes(manifest))
            args = SimpleNamespace(
                init_adapter_dir=str(adapter),
                init_adapter_model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                init_adapter_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
                init_adapter_artifact_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                resume_from_checkpoint=None, lora_r=16, lora_alpha=32, lora_dropout=0.05,
            )
            result = trainer._adapter_initialization(args, "b" * 64)
            self.assertEqual(result["init_mode"], "adapter-weights-only")
            self.assertEqual(result["run_id"], "prior-run")
            self.assertEqual(result["directory_identity"], "prior-adapter")
            self.assertEqual(result["inventory"], inventory)

            args.init_adapter_config_sha256 = "0" * 64
            with self.assertRaisesRegex(trainer.BehaviorTrainingError, "config SHA"):
                trainer._adapter_initialization(args, "b" * 64)
            args.init_adapter_config_sha256 = hashlib.sha256(config.read_bytes()).hexdigest()
            model.write_bytes(b"tampered")
            with self.assertRaisesRegex(trainer.BehaviorTrainingError, "artifact"):
                trainer._adapter_initialization(args, "b" * 64)

    def test_adapter_initialization_all_or_none_and_resume_are_rejected(self) -> None:
        args = SimpleNamespace(init_adapter_dir="x", init_adapter_model_sha256="",
                               init_adapter_config_sha256="", init_adapter_artifact_manifest_sha256="",
                               resume_from_checkpoint=None, lora_r=16, lora_alpha=32,
                               lora_dropout=0.05)
        with self.assertRaisesRegex(trainer.BehaviorTrainingError, "all-or-none"):
            trainer._adapter_initialization(args, "a" * 64)
        args.init_adapter_model_sha256 = "a" * 64
        args.init_adapter_config_sha256 = "a" * 64
        args.init_adapter_artifact_manifest_sha256 = "a" * 64
        args.resume_from_checkpoint = Path("checkpoint")
        with self.assertRaisesRegex(trainer.BehaviorTrainingError, "mutually exclusive"):
            trainer._adapter_initialization(args, "a" * 64)

    @unittest.skipUnless(os.name == "nt", "native sharing semantics are Windows-only")
    def test_held_windows_loader_handle_blocks_replace_delete_and_final_reparse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config.json"
            target.write_bytes(b"pinned")
            generation = root / "generation_config.json"
            generation.write_bytes(b"also-pinned")
            self.assertEqual(
                {target, generation}, set(trainer._closed_model_loader_files(root)))
            replacement = root / "replacement.json"
            replacement.write_bytes(b"replacement")
            with trainer._HeldInputFiles([target, generation]) as held:
                with self.assertRaises(PermissionError):
                    os.replace(replacement, target)
                with self.assertRaises(PermissionError):
                    generation.unlink()
                held.verify()
            link = root / "linked.json"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlink privilege unavailable: {exc}")
            with self.assertRaisesRegex(trainer.BehaviorTrainingError, "reparse"):
                with trainer._HeldInputFiles([link]):
                    pass

    def test_held_input_partial_open_failure_closes_prior_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.json"
            first.write_bytes(b"first")
            missing = root / "missing.json"
            opened: list[int] = []
            original = trainer._HeldInputFiles._open_read_only

            def record_open(path: Path, flags: int) -> int:
                descriptor = original(path, flags)
                opened.append(descriptor)
                return descriptor

            with mock.patch.object(trainer._HeldInputFiles, "_open_read_only",
                                   side_effect=record_open):
                with self.assertRaises(trainer.BehaviorTrainingError):
                    trainer._HeldInputFiles([first, missing]).__enter__()
            self.assertEqual(1, len(opened))
            with self.assertRaises(OSError):
                os.fstat(opened[0])

    def test_deterministic_validation_configures_exact_cuda_controls(self) -> None:
        fake_torch = mock.Mock()
        fake_torch.backends.cudnn.deterministic = False
        fake_torch.backends.cudnn.benchmark = True
        fake_torch.backends.cudnn.allow_tf32 = True
        fake_torch.backends.cuda.matmul.allow_tf32 = True
        with mock.patch.dict(os.environ, {}, clear=True):
            trainer._configure_deterministic_validation(fake_torch, True)
            self.assertEqual(os.environ["CUBLAS_WORKSPACE_CONFIG"], ":4096:8")
        fake_torch.use_deterministic_algorithms.assert_called_once_with(True)
        self.assertIs(fake_torch.backends.cudnn.deterministic, True)
        self.assertIs(fake_torch.backends.cudnn.benchmark, False)
        self.assertIs(fake_torch.backends.cudnn.allow_tf32, False)
        self.assertIs(fake_torch.backends.cuda.matmul.allow_tf32, False)

    def test_deterministic_validation_rejects_conflicting_cublas_contract(self) -> None:
        with mock.patch.dict(os.environ, {"CUBLAS_WORKSPACE_CONFIG": ":16:8"}, clear=True):
            with self.assertRaisesRegex(trainer.BehaviorTrainingError, "CUBLAS_WORKSPACE_CONFIG"):
                trainer._prepare_deterministic_validation(True)

    def test_resumed_pause_acceptance_is_noop_after_complete_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "control" / "history").mkdir(parents=True)
            trainer._accept_resumed_pause_control(
                run_dir, "archived-run", "checkpoint-00000001", "a" * 64)
            self.assertFalse((run_dir / "control" / "resume.accepted.json").exists())

    def test_resumed_pause_acceptance_rejects_one_live_control(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            control = run_dir / "control"
            control.mkdir(parents=True)
            trainer.atomic_json(control / "pause.request.json", {
                "schema_version": "airi.behavior-pause-request.v1",
                "run_id": "partial-run", "request_id": "partial-request",
            })
            with self.assertRaisesRegex(
                    trainer.BehaviorTrainingError, "incomplete"):
                trainer._accept_resumed_pause_control(
                    run_dir, "partial-run", "checkpoint-00000001", "a" * 64)

    def test_dataset_path_rejects_reparse_attributes_before_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dataset.jsonl"
            payload = dataset_lines(1)
            path.write_bytes(payload)
            fake_stat = SimpleNamespace(
                st_file_attributes=0x400,
                st_mode=stat.S_IFREG)
            with mock.patch.object(trainer.os, "lstat", return_value=fake_stat):
                with self.assertRaisesRegex(
                        trainer.BehaviorTrainingError, "reparse"):
                    trainer.load_pinned_dataset(
                        path, hashlib.sha256(payload).hexdigest())

    def test_checkpoint_event_is_canonical_hash_bound_and_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            generation = "checkpoint-00000001"
            pins = {"dataset_sha256": "c" * 64}
            # v2 events are only published by the checkpoint transaction; a
            # public standalone event writer would reintroduce self-authentication.
            receipt = trainer.publish_checkpoint(
                run_dir, "p0b-run", generation, b"payload", pins,
                {"run_id": "p0b-run", "generation": generation, "reason": "interval",
                 "microsteps_completed": 80, "optimizer_steps": 5,
                 "pending_microbatches": 0, "training_elapsed_ns": 2_000_000_000,
                 "checkpoint_payload_progress": {"microsteps_completed": 80,
                                                  "optimizer_steps": 5,
                                                  "pending_microbatches": 0}})["event"]
            event_path = run_dir / receipt["relative_path"]
            event_bytes = event_path.read_bytes()
            self.assertEqual(hashlib.sha256(event_bytes).hexdigest(), receipt["sha256"])
            event = json.loads(event_bytes)
            self.assertEqual(event["schema_version"], "airi.behavior-checkpoint-event.v2")
            self.assertEqual(event["checkpoint_manifest_sha256"], hashlib.sha256(
                (run_dir / "checkpoints" / generation / "manifest.json").read_bytes()).hexdigest())
            self.assertEqual(event["checkpoint_payload_sha256"], hashlib.sha256(b"payload").hexdigest())
            self.assertEqual(event["pending_microbatches"], 0)
            with self.assertRaisesRegex(trainer.CheckpointError, "already exists"):
                trainer.publish_checkpoint(run_dir, "p0b-run", generation, b"payload", pins, event)

    def test_v4_metadata_and_native_context_are_accepted(self) -> None:
        row = v4_row("v4-1")
        row["messages"] = row["messages"][:-1] + [
            {"role": "user", "content": f"turn {index}"} for index in range(12)
        ] + [{"role": "assistant", "content": "final amber"}]
        payload, digest = pinned_payload([row])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v4.jsonl"
            path.write_bytes(payload)
            self.assertEqual(trainer.load_pinned_dataset(path, digest)[0]["id"], "v4-1")

    def test_v4_metadata_and_split_leaks_fail_closed(self) -> None:
        cases = []
        missing = v4_row("v4-missing")
        del missing["semantic_family"]
        cases.append([missing])
        wrong_review = v4_row("v4-review")
        wrong_review["review"]["adoption_authorized"] = True
        cases.append([wrong_review])
        named = v4_row("v4-name")
        named["messages"][0]["name"] = "airi_broadcast_arc"
        cases.append([named])
        cases.append([v4_row("v4-g1", "train", "shared", "one"),
                      v4_row("v4-g2", "dev", "shared", "two")])
        cases.append([v4_row("v4-t1", "train", "one", "leaked"),
                      v4_row("v4-t2", "dev", "two", "leaked")])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-v4.jsonl"
            for rows in cases:
                payload, digest = pinned_payload(rows)
                path.write_bytes(payload)
                with self.assertRaises(trainer.BehaviorTrainingError):
                    trainer.load_pinned_dataset(path, digest)

    def test_group_shuffle_is_reproducible_epoch_varying_and_group_contained(self) -> None:
        rows = [v4_row("a1", group="a", token="alpha"), v4_row("a2", group="a", token="alpha"),
                v4_row("b1", group="b", token="beta"), v4_row("b2", group="b", token="beta")]
        first = trainer.epoch_group_order(rows, 17, 0)
        self.assertEqual([row["id"] for row in first],
                         [row["id"] for row in trainer.epoch_group_order(rows, 17, 0)])
        self.assertNotEqual([row["id"] for row in first],
                            [row["id"] for row in trainer.epoch_group_order(rows, 17, 1)])
        groups = [row["scenario_group"] for row in first]
        self.assertEqual(1, sum(groups[index] != groups[index - 1]
                                for index in range(1, len(groups))))

    def test_best_state_selection_keeps_only_strictly_better_dev_loss(self) -> None:
        model = object()
        with mock.patch.object(trainer, "snapshot_trainable_state", return_value={"lora": "cpu"}) as snapshot:
            best = trainer.consider_best_state(None, 1.0, 3, 1, model)
            retained = trainer.consider_best_state(best, 1.0, 6, 2, model)
            improved = trainer.consider_best_state(retained, 0.5, 9, 3, model)
        self.assertEqual((best["step"], retained["epoch"]), (3, 1))
        self.assertEqual((improved["loss"], improved["step"], improved["epoch"]), (0.5, 9, 3))
        self.assertEqual(snapshot.call_count, 2)

    def test_epoch_tail_is_flushed_before_dev_state_selection(self) -> None:
        events: list[str] = []

        class Optimizer:
            def step(self) -> None:
                events.append("step")

            def zero_grad(self) -> None:
                events.append("zero")

        self.assertEqual(trainer.flush_epoch_accumulation(Optimizer(), 2), 1)
        self.assertEqual(events, ["step", "zero"])
        with mock.patch.object(trainer, "snapshot_trainable_state", side_effect=lambda _model: {
                "selected_after": list(events)}):
            best = trainer.consider_best_state(None, 0.25, 2, 1, object())
        self.assertEqual(best["state"]["selected_after"], ["step", "zero"])
        self.assertEqual(trainer.flush_epoch_accumulation(Optimizer(), 0), 0)
    def test_dataset_must_match_its_sha_pin(self) -> None:
        payload = dataset_lines()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat.jsonl"
            path.write_bytes(payload)
            good = trainer.load_pinned_dataset(path, hashlib.sha256(payload).hexdigest())
            self.assertEqual(len(good), 8)
            with self.assertRaises(trainer.BehaviorTrainingError):
                trainer.load_pinned_dataset(path, "0" * 64)

    def test_malformed_message_shapes_fail_closed(self) -> None:
        bad = {"id": "x", "split": "train", "behavior": "register",
               "messages": [{"role": "user", "content": "혼자"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat.jsonl"
            payload = (json.dumps(bad, ensure_ascii=False) + "\n").encode("utf-8")
            path.write_bytes(payload)
            with self.assertRaises(trainer.BehaviorTrainingError):
                trainer.load_pinned_dataset(path, hashlib.sha256(payload).hexdigest())

    def test_unknown_split_fails_closed(self) -> None:
        row = json.loads(dataset_lines(1).decode("utf-8"))
        row["split"] = "holdout"
        payload = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-split.jsonl"
            path.write_bytes(payload)
            with self.assertRaises(trainer.BehaviorTrainingError):
                trainer.load_pinned_dataset(path, hashlib.sha256(payload).hexdigest())

    def test_request_local_affect_shape_is_accepted_but_near_variants_fail(self) -> None:
        row = {"id": "bseed-affect_playful_annoyed-0001", "split": "train",
               "behavior": "affect_playful_annoyed", "messages": [
                   {"role": "system", "content": "너는 AIRI라는 방송 동료야."},
                   {"role": "system", "name": "airi_request_local", "content": "닫힌 표현 계약"},
                   {"role": "user", "content": "[YouTube] 또 자신감 충전했네"},
                   {"role": "assistant", "content": "충전은 끝났고, 이번엔 네 예측부터 방전시키자!"},
               ]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "affect.jsonl"
            payload = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
            path.write_bytes(payload)
            loaded = trainer.load_pinned_dataset(path, hashlib.sha256(payload).hexdigest())
            self.assertEqual(loaded[0]["messages"][1]["name"], "airi_request_local")
            for mutation in ("wrong_name", "missing_name"):
                broken = json.loads(json.dumps(row, ensure_ascii=False))
                if mutation == "wrong_name":
                    broken["messages"][1]["name"] = "other"
                else:
                    del broken["messages"][1]["name"]
                bad = (json.dumps(broken, ensure_ascii=False) + "\n").encode("utf-8")
                path.write_bytes(bad)
                with self.assertRaises(trainer.BehaviorTrainingError):
                    trainer.load_pinned_dataset(path, hashlib.sha256(bad).hexdigest())

    def test_post_proxy_runtime_shape_with_history_and_request_local_is_accepted(self) -> None:
        row = {"id": "continuity-v3-0001", "split": "train",
               "behavior": "fact_direct", "messages": [
                   {"role": "system", "content": "너는 AIRI라는 방송 동료야."},
                   {"role": "user", "content": "[YouTube] 먼저 창고를 보자"},
                   {"role": "assistant", "content": "창고부터 훑어볼게."},
                   {"role": "system", "content": "[오늘 방송]\n- 주제: 탐험\n\n[턴 브리핑]\n- 관련 사실"},
                   {"role": "system", "name": "airi_request_local", "content": "방송 응답 문체 계약"},
                   {"role": "user", "content": "[YouTube] 아까 표식 어디였지?"},
                   {"role": "assistant", "content": "표식은 북쪽 기둥이라고 했지. 거기부터 다시 볼게."},
               ]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.jsonl"
            payload = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
            path.write_bytes(payload)
            loaded = trainer.load_pinned_dataset(path, hashlib.sha256(payload).hexdigest())
            self.assertEqual(len(loaded[0]["messages"]), 7)
            for mutation in ("unknown_name", "assistant_not_final"):
                broken = json.loads(json.dumps(row, ensure_ascii=False))
                if mutation == "unknown_name":
                    broken["messages"][4]["name"] = "untrusted_note"
                else:
                    broken["messages"][-2]["role"] = "assistant"
                bad = (json.dumps(broken, ensure_ascii=False) + "\n").encode("utf-8")
                path.write_bytes(bad)
                with self.assertRaises(trainer.BehaviorTrainingError):
                    trainer.load_pinned_dataset(path, hashlib.sha256(bad).hexdigest())

    def test_network_and_hub_paths_are_refused(self) -> None:
        for value in ("//share/model", r"\\\\server\\model", "hf://org/model"):
            with self.assertRaises(trainer.BehaviorTrainingError):
                trainer.reject_network_path(Path(value), "model dir")
        with self.assertRaises(trainer.BehaviorTrainingError):
            trainer.require_local_model_dir("K-intelligence/Midm-2.0-Mini-Instruct")

    def test_production_weight_pin_is_required_and_exact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp)
            weights = model / "model.safetensors"
            weights.write_bytes(b"bounded test weights")
            digest = hashlib.sha256(weights.read_bytes()).hexdigest()
            self.assertEqual(
                trainer.verify_model_weight_sha256(model, digest), digest)
            for bad in ("", "A" * 64, "0" * 64):
                with self.assertRaises(trainer.BehaviorTrainingError):
                    trainer.verify_model_weight_sha256(model, bad)

    def test_fallback_render_masks_exactly_the_prompt(self) -> None:
        class BareTokenizer:
            chat_template = None
        messages = [{"role": "system", "content": "시스템"},
                    {"role": "user", "content": "질문"},
                    {"role": "assistant", "content": "답변"}]
        prompt, full = trainer.render_pair(BareTokenizer(), messages)
        self.assertTrue(full.startswith(prompt))
        self.assertIn("답변", full[len(prompt):])
        self.assertNotIn("답변", prompt)

        affect_messages = [
            {"role": "system", "content": "시스템"},
            {"role": "system", "name": "airi_request_local", "content": "표현 계약"},
            {"role": "user", "content": "질문"},
            {"role": "assistant", "content": "답변"},
        ]
        affect_prompt, affect_full = trainer.render_pair(BareTokenizer(), affect_messages)
        self.assertTrue(affect_full.startswith(affect_prompt))
        self.assertIn("표현 계약", affect_prompt)
        self.assertNotIn("답변", affect_prompt)

    def test_encode_example_refuses_partial_target_truncation(self) -> None:
        class BareTokenizer:
            chat_template = None

            def __call__(self, text, add_special_tokens=False):
                return {"input_ids": list(range(len(text)))}

        messages = [
            {"role": "system", "content": "시스템"},
            {"role": "user", "content": "질문"},
            {"role": "assistant", "content": "충분히 긴 실제 답변"},
        ]
        _prompt, full = trainer.render_pair(BareTokenizer(), messages)
        with self.assertRaisesRegex(trainer.BehaviorTrainingError, "without truncating"):
            trainer.encode_example(BareTokenizer(), messages, len(full) - 1)


@unittest.skipUnless(TORCH_STACK, "torch/peft/transformers unavailable on this runner")
class CpuSmokeTests(unittest.TestCase):
    """A tiny random model proves the loop end to end — no download, no network."""

    @classmethod
    def setUpClass(cls) -> None:
        from tokenizers import Tokenizer, models, pre_tokenizers, trainers
        from transformers import LlamaConfig, LlamaForCausalLM, PreTrainedTokenizerFast

        cls.tmp = Path(tempfile.mkdtemp(prefix="airi-behavior-smoke-"))
        corpus = ["응 답이야 편하게 물어봐 질문 [YouTube] 너는 AIRI라는 방송 동료야 <|system|> <|user|> <|assistant|>"]
        tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))
        tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel()
        tokenizer.train_from_iterator(corpus, trainers.BpeTrainer(
            vocab_size=300, special_tokens=["<unk>", "<pad>", "</s>"]))
        wrapped = PreTrainedTokenizerFast(tokenizer_object=tokenizer,
                                          unk_token="<unk>", pad_token="<pad>", eos_token="</s>")
        model_dir = cls.tmp / "tiny-model"
        model_dir.mkdir()
        wrapped.save_pretrained(str(model_dir))
        config = LlamaConfig(vocab_size=wrapped.vocab_size + 10, hidden_size=32,
                             intermediate_size=64, num_hidden_layers=2,
                             num_attention_heads=2, num_key_value_heads=2,
                             max_position_embeddings=512)
        LlamaForCausalLM(config).save_pretrained(str(model_dir))
        payload = dataset_lines()
        cls.dataset = cls.tmp / "chat.jsonl"
        cls.dataset.write_bytes(payload)
        cls.sha = hashlib.sha256(payload).hexdigest()
        cls.model_dir = model_dir

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_cpu_smoke_trains_saves_and_reports_honestly(self) -> None:
        args = trainer.build_parser().parse_args([
            "--dataset", str(self.dataset), "--dataset-sha256", self.sha,
            "--model-dir", str(self.model_dir),
            "--output", str(self.tmp / "adapter"), "--mode", "cpu-smoke",
            "--max-steps", "12", "--batch-size", "3", "--gradient-accumulation", "2",
        ])
        summary = trainer.run_training(args)
        self.assertEqual(summary["mode"], "cpu-smoke")
        self.assertEqual(summary["dataset_samples"], 8)
        self.assertEqual(summary["split_counts"], {"train": 8})
        self.assertEqual(summary["training_samples"], 8)
        self.assertEqual(summary["seed"], 42)
        # Three microbatches per epoch leave a tail after every epoch: four
        # epoch-boundary flushes plus four full accumulation steps.
        self.assertEqual(summary["optimizer_steps"], 8)
        self.assertLess(summary["loss_last3_mean"], summary["loss_first3_mean"])
        self.assertIs(summary["training_authorization"], False)
        self.assertIs(summary["adoption_authorized"], False)
        self.assertEqual(summary["t3_status"], "pending")
        self.assertIn("NOT a trained adapter", summary["note"])
        adapter_dir = Path(summary["adapter_dir"])
        self.assertTrue(adapter_dir.name.endswith("-SMOKE"))
        self.assertTrue((adapter_dir / "adapter_config.json").is_file())
        self.assertTrue((adapter_dir / "artifact-manifest.json").is_file())
        self.assertRegex(summary["adapter_artifact_manifest_sha256"], r"^[0-9a-f]{64}$")

        with self.assertRaises(trainer.BehaviorTrainingError):
            trainer.run_training(args)

    def test_cpu_weights_only_initialization_loads_exact_tensors_with_fresh_progress(self) -> None:
        import torch
        from peft import PeftModel
        from safetensors.torch import load_file

        source_args = trainer.build_parser().parse_args([
            "--dataset", str(self.dataset), "--dataset-sha256", self.sha,
            "--model-dir", str(self.model_dir), "--output", str(self.tmp / "init-source"),
            "--mode", "cpu-smoke", "--max-steps", "8", "--batch-size", "2",
            "--gradient-accumulation", "2",
        ])
        source = trainer.run_training(source_args)
        source_dir = Path(source["adapter_dir"])
        model_sha = hashlib.sha256((source_dir / "adapter_model.safetensors").read_bytes()).hexdigest()
        config_sha = hashlib.sha256((source_dir / "adapter_config.json").read_bytes()).hexdigest()
        manifest_sha = hashlib.sha256((source_dir / "artifact-manifest.json").read_bytes()).hexdigest()
        target_args = trainer.build_parser().parse_args([
            "--dataset", str(self.dataset), "--dataset-sha256", self.sha,
            "--model-dir", str(self.model_dir), "--output", str(self.tmp / "init-target"),
            "--mode", "cpu-smoke", "--max-steps", "8", "--batch-size", "2",
            "--gradient-accumulation", "2", "--run-id", "weights-only-init",
            "--run-dir", str(self.tmp / "weights-only-run"),
            "--init-adapter-dir", str(source_dir), "--init-adapter-model-sha256", model_sha,
            "--init-adapter-config-sha256", config_sha,
            "--init-adapter-artifact-manifest-sha256", manifest_sha,
        ])
        captured = {}
        original = PeftModel.from_pretrained.__func__

        def capture(cls, model, *args, **kwargs):
            loaded = original(cls, model, *args, **kwargs)
            captured.update({key.replace(".default.", "."): value.detach().cpu().clone()
                             for key, value in loaded.state_dict().items() if "lora_" in key})
            return loaded

        with mock.patch.object(PeftModel, "from_pretrained", classmethod(capture)):
            result = trainer.run_training(target_args)
        expected = load_file(str(source_dir / "adapter_model.safetensors"))
        self.assertEqual(set(expected), set(captured))
        for key, value in expected.items():
            self.assertTrue(torch.equal(value, captured[key]), key)
        receipt = json.loads((target_args.run_dir / "fresh-state-receipt.json").read_text())
        self.assertEqual(receipt["fresh_state"], {
            "microsteps_completed": 0, "optimizer_steps": 0, "epoch": 0,
            "next_batch_index": 0, "pending_microbatches": 0,
            "optimizer_state_entries": 0})
        self.assertEqual(result["initialization"]["init_mode"], "adapter-weights-only")

    def test_cpu_uninterrupted_and_safe_pause_resume_are_exact(self) -> None:
        import torch
        from safetensors.torch import load_file

        def arguments(name: str, run_id: str, resume: Path | None = None):
            values = [
                "--dataset", str(self.dataset), "--dataset-sha256", self.sha,
                "--model-dir", str(self.model_dir),
                "--output", str(self.tmp / name), "--mode", "cpu-smoke",
                "--max-steps", "8", "--batch-size", "2",
                "--gradient-accumulation", "2", "--run-id", run_id,
                "--run-dir", str(self.tmp / f"{name}-run"),
                "--checkpoint-every-optimizer-steps", "1",
            ]
            if resume is not None:
                values.extend(("--resume-from-checkpoint", str(resume)))
            return trainer.build_parser().parse_args(values)

        def latest_state(run_dir: Path):
            index = json.loads(
                (run_dir / "checkpoints" / "checkpoint-index.json").read_text())
            generation = index["latest"]["relative_path"]
            return torch.load(
                run_dir / "checkpoints" / generation / "state.pt",
                map_location="cpu", weights_only=False)

        def assert_equal(left, right, path: str = "state") -> None:
            if isinstance(left, torch.Tensor):
                self.assertTrue(
                    torch.equal(left, right), f"tensor mismatch at {path}")
            elif isinstance(left, dict):
                self.assertEqual(set(left), set(right), f"keys mismatch at {path}")
                for key in left:
                    assert_equal(left[key], right[key], f"{path}.{key}")
            elif isinstance(left, (list, tuple)):
                self.assertEqual(len(left), len(right), f"length mismatch at {path}")
                for index, (left_item, right_item) in enumerate(zip(left, right)):
                    assert_equal(left_item, right_item, f"{path}[{index}]")
            else:
                self.assertEqual(left, right, f"value mismatch at {path}")

        uninterrupted_args = arguments("exact-uninterrupted", "exact-run-a")
        uninterrupted = trainer.run_training(uninterrupted_args)

        resumed_args = arguments("exact-resumed", "exact-run-b")
        control = resumed_args.run_dir / "control"
        control.mkdir(parents=True)
        trainer.atomic_json(control / "pause.request.json", {
            "schema_version": "airi.behavior-pause-request.v1",
            "run_id": "exact-run-b", "request_id": "pause-exact-001",
        })
        with self.assertRaises(trainer.PauseRequested) as paused:
            trainer.run_training(resumed_args)
        self.assertEqual(paused.exception.code, 75)
        paused_index = json.loads(
            (resumed_args.run_dir / "checkpoints" / "checkpoint-index.json").read_text())
        resume_path = (resumed_args.run_dir / "checkpoints" /
                       paused_index["latest"]["relative_path"])
        resumed = trainer.run_training(
            arguments("exact-resumed", "exact-run-b", resume_path))
        accepted = json.loads((control / "resume.accepted.json").read_text())
        self.assertEqual(accepted["request_id"], "pause-exact-001")
        self.assertEqual(accepted["checkpoint_relative_path"], resume_path.name)
        self.assertTrue((control / "pause.request.json").is_file())
        self.assertTrue((control / "pause.ack.json").is_file())

        uninterrupted_comparable = dict(uninterrupted)
        resumed_comparable = dict(resumed)
        uninterrupted_comparable.pop("adapter_dir")
        resumed_comparable.pop("adapter_dir")
        uninterrupted_manifest_sha = uninterrupted_comparable.pop(
            "adapter_artifact_manifest_sha256")
        resumed_manifest_sha = resumed_comparable.pop(
            "adapter_artifact_manifest_sha256")
        self.assertEqual(uninterrupted_comparable, resumed_comparable)

        uninterrupted_manifest_path = (
            self.tmp / "exact-uninterrupted-SMOKE" / "artifact-manifest.json")
        resumed_manifest_path = (
            self.tmp / "exact-resumed-SMOKE" / "artifact-manifest.json")
        self.assertEqual(
            hashlib.sha256(uninterrupted_manifest_path.read_bytes()).hexdigest(),
            uninterrupted_manifest_sha)
        self.assertEqual(
            hashlib.sha256(resumed_manifest_path.read_bytes()).hexdigest(),
            resumed_manifest_sha)
        uninterrupted_manifest = json.loads(
            uninterrupted_manifest_path.read_text(encoding="utf-8"))
        resumed_manifest = json.loads(
            resumed_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(uninterrupted_manifest.pop("run_id"), "exact-run-a")
        self.assertEqual(resumed_manifest.pop("run_id"), "exact-run-b")
        self.assertEqual(uninterrupted_manifest, resumed_manifest)

        uninterrupted_tensors = load_file(
            str(self.tmp / "exact-uninterrupted-SMOKE" / "adapter_model.safetensors"))
        resumed_tensors = load_file(
            str(self.tmp / "exact-resumed-SMOKE" / "adapter_model.safetensors"))
        assert_equal(uninterrupted_tensors, resumed_tensors, "adapter")

        uninterrupted_state = latest_state(uninterrupted_args.run_dir)
        resumed_state = latest_state(resumed_args.run_dir)
        uninterrupted_state.pop("run_id")
        resumed_state.pop("run_id")
        # Cumulative monotonic evidence deliberately includes real publication
        # time, unlike deterministic optimizer/model state.
        uninterrupted_state.pop("training_elapsed_ns")
        resumed_state.pop("training_elapsed_ns")
        assert_equal(uninterrupted_state, resumed_state)

    def test_cpu_resume_full_pin_mismatch_preserves_live_pause_evidence(self) -> None:
        def arguments(resume: Path | None = None):
            values = [
                "--dataset", str(self.dataset), "--dataset-sha256", self.sha,
                "--model-dir", str(self.model_dir),
                "--output", str(self.tmp / "pin-mismatch"), "--mode", "cpu-smoke",
                "--max-steps", "8", "--batch-size", "2",
                "--gradient-accumulation", "2", "--run-id", "pin-mismatch-run",
                "--run-dir", str(self.tmp / "pin-mismatch-run-dir"),
                "--checkpoint-every-optimizer-steps", "1",
            ]
            if resume is not None:
                values.extend(("--resume-from-checkpoint", str(resume)))
            return trainer.build_parser().parse_args(values)

        initial = arguments()
        control = initial.run_dir / "control"
        control.mkdir(parents=True)
        trainer.atomic_json(control / "pause.request.json", {
            "schema_version": "airi.behavior-pause-request.v1",
            "run_id": "pin-mismatch-run", "request_id": "pin-mismatch-pause",
        })
        with self.assertRaises(trainer.PauseRequested):
            trainer.run_training(initial)
        index = json.loads(
            (initial.run_dir / "checkpoints" / "checkpoint-index.json").read_text())
        resume_path = (initial.run_dir / "checkpoints" /
                       index["latest"]["relative_path"])
        extra_tokenizer_pin = self.model_dir / "token-durability-probe.txt"
        try:
            extra_tokenizer_pin.write_text("changed after checkpoint\n", encoding="utf-8")
            with self.assertRaisesRegex(
                    trainer.BehaviorTrainingError, "checkpoint exact pins mismatch"):
                trainer.run_training(arguments(resume_path))
        finally:
            extra_tokenizer_pin.unlink(missing_ok=True)
        self.assertTrue((control / "pause.request.json").is_file())
        self.assertTrue((control / "pause.ack.json").is_file())
        self.assertFalse((control / "resume.accepted.json").exists())

    def test_cuda_mode_refuses_a_gpu_less_box(self) -> None:
        import torch
        if torch.cuda.is_available():  # pragma: no cover - not this machine
            self.skipTest("box has CUDA; refusal path not applicable")
        args = trainer.build_parser().parse_args([
            "--dataset", str(self.dataset), "--dataset-sha256", self.sha,
            "--model-dir", str(self.model_dir),
            "--output", str(self.tmp / "adapter2"), "--mode", "cuda-qlora",
        ])
        with self.assertRaises(trainer.BehaviorTrainingError):
            trainer.run_training(args)


if __name__ == "__main__":
    unittest.main()
