import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("package_airi_gguf_test", HERE / "package_airi_gguf.py")
assert SPEC is not None and SPEC.loader is not None
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)
BUILD_ID = "1" * 32


class FakeRunner:
    def __init__(self): self.commands = []
    def __call__(self, command):
        command = list(command); self.commands.append(command)
        if command[1] == "create": return self.result(0, "", "")
        if command[1] == "rm": return self.result(0, "", "")
        if "--outtype" in command: Path(command[-1]).write_bytes(b"bf16")
        elif command[-1] == "Q4_K_M": Path(command[-2]).write_bytes(b"q4")
        return self.result(0, "", "")
    @staticmethod
    def result(code, stdout, stderr): return packager.subprocess.CompletedProcess([], code, stdout, stderr)


class FakeApi:
    def __init__(self, runner, tag, *, present=False, quant="Q4_K_M", changed=False, missing=False):
        self.runner, self.tag, self.present, self.quant = runner, tag, present, quant
        self.changed, self.missing, self.calls, self.post_calls = changed, missing, [], 0
    def __call__(self, method, path, payload):
        self.calls.append((method, path, payload))
        if path == "/api/tags":
            if self.present: return {"models": [{"name": self.tag, "digest": "a" * 64}]}
            if any(call[1] == "create" for call in self.runner.commands):
                self.post_calls += 1
                if self.post_calls >= 2 and self.missing: return {"models": []}
                digest = "b" * 64 if self.post_calls >= 2 and self.changed else "a" * 64
                return {"models": [{"name": self.tag, "digest": digest}]}
            return {"models": []}
        if path == "/api/show": return {"details": {"quantization_level": self.quant, "format": "gguf", "family": "llama"}}
        raise AssertionError(path)


class PackageTests(unittest.TestCase):
    def test_default_runner_decodes_llama_output_as_utf8(self):
        completed = packager.subprocess.CompletedProcess([], 0, "ok", "")
        with mock.patch.object(packager.subprocess, "run", return_value=completed) as run:
            self.assertIs(packager.default_runner(["tool", "arg"]), completed)
        run.assert_called_once_with(
            ["tool", "arg"], shell=False, text=True, encoding="utf-8",
            errors="replace", capture_output=True, check=False,
        )

    def make_args(self, root):
        merged = root / "merged"; merged.mkdir(); (merged / "config.json").write_text("{}")
        weight = merged / "model.safetensors"; weight.write_bytes(b"merged-weight")
        tools = []
        for name in ("python.exe", "convert_hf_to_gguf.py", "ollama.exe"):
            item = root / name; item.write_bytes(name.encode()); tools.append(item)
        bundle = root / "quantizer-bundle"; bundle.mkdir()
        quantizer = bundle / "llama-quantize.exe"; quantizer.write_bytes(b"quantizer")
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = [{"name": quantizer.name, "size_bytes": quantizer.stat().st_size, "sha256": digest(quantizer)}]
        bundle_pin = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return packager.parse_args(["--converter-python", str(tools[0]), "--converter-python-sha256", digest(tools[0]),
            "--converter-script", str(tools[1]), "--converter-script-sha256", digest(tools[1]),
            "--quantizer", str(quantizer), "--quantizer-bundle-sha256", bundle_pin,
            "--merged-dir", str(merged), "--merged-model-sha256", digest(weight),
            "--output-dir", str(root / "package"), "--tag-prefix", "airi:build",
            "--ollama-exe", str(tools[2]), "--ollama-exe-sha256", digest(tools[2])])

    def call(self, args, runner=None, api=None, build_id=BUILD_ID):
        runner = runner or FakeRunner(); tag = f"{args.tag_prefix}-{build_id}"
        return packager.package(args, runner, api or FakeApi(runner, tag), build_id=build_id), runner, tag

    def test_commands_use_generated_tag_and_record_pins(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); args = self.make_args(root)
            evidence_path, runner, tag = self.call(args)
            self.assertEqual(runner.commands[2][1:4], ["create", tag, "-f"])
            self.assertNotIn(args.tag_prefix, runner.commands[2])
            evidence = json.loads(evidence_path.read_text())
            self.assertEqual(evidence["tag_evidence"]["tag"], tag)
            self.assertEqual(evidence["tool_hashes"]["quantizer_bundle"]["manifest_sha256"], args.quantizer_bundle_sha256)
            self.assertEqual(evidence["pins"]["ollama_exe_sha256"], args.ollama_exe_sha256)
            self.assertFalse(evidence["adoption_authorized"])

    def test_controlled_build_ids_produce_distinct_actual_tags(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "one").mkdir(); (root / "two").mkdir()
            first = self.make_args(root / "one"); second = self.make_args(root / "two")
            _, first_runner, first_tag = self.call(first, build_id="1" * 32)
            _, second_runner, second_tag = self.call(second, build_id="2" * 32)
            self.assertNotEqual(first_tag, second_tag)
            self.assertEqual(first_runner.commands[2][2], first_tag)
            self.assertEqual(second_runner.commands[2][2], second_tag)

    def test_bad_tool_pin_prevents_runner_and_api_calls(self):
        with tempfile.TemporaryDirectory() as raw:
            args = self.make_args(Path(raw)); args.converter_python_sha256 = "0" * 64
            runner = FakeRunner(); api = FakeApi(runner, f"{args.tag_prefix}-{BUILD_ID}")
            with self.assertRaisesRegex(packager.PackagingError, "converter python SHA-256"):
                packager.package(args, runner, api, build_id=BUILD_ID)
            self.assertEqual(runner.commands, []); self.assertEqual(api.calls, [])

    def test_mismatch_same_digest_removes_exact_tag(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); args = self.make_args(root); runner = FakeRunner(); tag = f"{args.tag_prefix}-{BUILD_ID}"
            with self.assertRaisesRegex(packager.PackagingError, "Q4_K_M"):
                self.call(args, runner, FakeApi(runner, tag, quant="Q8_0"))
            self.assertEqual(runner.commands[-1], [str(Path(args.ollama_exe).resolve()), "rm", tag])
            self.assertFalse(Path(args.output_dir).exists())

    def test_changed_or_missing_digest_keeps_blocked_evidence_without_rm(self):
        for changed, missing in ((True, False), (False, True)):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as raw:
                root = Path(raw); args = self.make_args(root); runner = FakeRunner(); tag = f"{args.tag_prefix}-{BUILD_ID}"
                with self.assertRaisesRegex(packager.PackagingError, "changed or missing digest"):
                    self.call(args, runner, FakeApi(runner, tag, quant="Q8_0", changed=changed, missing=missing))
                self.assertFalse(any(command[1] == "rm" for command in runner.commands))
                self.assertEqual(json.loads((Path(args.output_dir) / "package-evidence.json").read_text())["tag"], tag)

    def test_existing_output_and_quantizer_subdir_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); args = self.make_args(root); Path(args.output_dir).mkdir()
            with self.assertRaises(packager.PackagingError): self.call(args)
            Path(args.output_dir).rmdir(); (Path(args.quantizer).parent / "bad").mkdir()
            with self.assertRaisesRegex(packager.PackagingError, "regular non-symlink"): self.call(args)


if __name__ == "__main__": unittest.main()
