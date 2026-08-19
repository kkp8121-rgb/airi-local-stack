import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
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


class ContractTests(unittest.TestCase):
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

    def test_network_and_hub_paths_are_refused(self) -> None:
        for value in ("//share/model", r"\\\\server\\model", "hf://org/model"):
            with self.assertRaises(trainer.BehaviorTrainingError):
                trainer.reject_network_path(Path(value), "model dir")
        with self.assertRaises(trainer.BehaviorTrainingError):
            trainer.require_local_model_dir("K-intelligence/Midm-2.0-Mini-Instruct")

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
            "--max-steps", "12", "--batch-size", "2", "--gradient-accumulation", "2",
        ])
        summary = trainer.run_training(args)
        self.assertEqual(summary["mode"], "cpu-smoke")
        self.assertLess(summary["loss_last3_mean"], summary["loss_first3_mean"])
        self.assertIs(summary["training_authorization"], False)
        self.assertIn("NOT a trained adapter", summary["note"])
        adapter_dir = Path(summary["adapter_dir"])
        self.assertTrue(adapter_dir.name.endswith("-SMOKE"))
        self.assertTrue((adapter_dir / "adapter_config.json").is_file())

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
