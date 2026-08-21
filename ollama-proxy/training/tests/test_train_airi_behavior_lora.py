import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path


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

        with self.assertRaises(trainer.BehaviorTrainingError):
            trainer.run_training(args)

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
