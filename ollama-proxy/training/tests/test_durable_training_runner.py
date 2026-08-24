import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "durable_training_runner_test", HERE / "durable_training_runner.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
BUILDER = HERE / "build_airi_behavior_input_manifest.py"


def _event(run_id: str, generation: str, *, progress: int = 1) -> dict:
    return {
        "run_id": run_id, "generation": generation, "reason": "interval",
        "microsteps_completed": progress, "optimizer_steps": progress,
        "pending_microbatches": 0, "training_elapsed_ns": progress,
        "checkpoint_payload_progress": {"microsteps_completed": progress,
                                        "optimizer_steps": progress,
                                        "pending_microbatches": 0},
    }


def _eventful_publish(publish):
    """Test-only adapter: every fixture still supplies a concrete v2 event."""
    def invoke(run_dir, run_id, generation, payload, pins, event=None):
        return publish(run_dir, run_id, generation, payload, pins,
                       _event(run_id, generation) if event is None else event)
    return invoke


FAKE_TRAINER = r'''
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument("--run-dir", type=Path, required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--dataset-sha256", required=True)
parser.add_argument("--model-sha256", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--resume-from-checkpoint", type=Path)
args, _ = parser.parse_known_args()
print(json.dumps({"argv": sys.argv[1:]}, sort_keys=True), flush=True)
now = datetime.now(timezone.utc).isoformat()
time.sleep(1.5)

if args.resume_from_checkpoint is None:
    request_path = args.run_dir / "control" / "pause.request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    generation = "checkpoint-00000001"
    checkpoint = args.run_dir / "checkpoints" / generation
    checkpoint.mkdir(parents=True)
    payload = b"verified-checkpoint"
    (checkpoint / "state.pt").write_bytes(payload)
    pins = {
        "dataset_sha256": args.dataset_sha256,
        "model_weight_sha256": args.model_sha256,
        "trainer_source_sha256": sha(__file__),
        "config": {"learning_rate": 2e-5, "lora_dropout": 0.05},
    }
    manifest = {
        "schema_version": 1,
        "generation": generation,
        "run_id": args.run_id,
        "payload": {
            "name": "state.pt", "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        "pins": pins,
    }
    manifest_bytes = canonical(manifest)
    (checkpoint / "manifest.json").write_bytes(manifest_bytes)
    reference = {
        "relative_path": generation,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    event = {
        "schema_version": "airi.behavior-checkpoint-event.v2",
        "run_id": args.run_id, "generation": generation, "reason": "interval",
        "microsteps_completed": 16, "optimizer_steps": 1,
        "pending_microbatches": 0, "training_elapsed_ns": 1,
        "checkpoint_payload_progress": {"microsteps_completed": 16,
                                        "optimizer_steps": 1,
                                        "pending_microbatches": 0},
        "checkpoint_manifest_sha256": reference["manifest_sha256"],
        "checkpoint_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "pins_sha256": hashlib.sha256(canonical(pins)).hexdigest(),
        "previous_event_sha256": None, "previous_index_sha256": None,
        "publish_started_at_utc": now, "checkpoint_durable_at_utc": now,
        "publish_elapsed_ns": 1,
    }
    event_path = args.run_dir / "checkpoint-events" / f"{generation}.json"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_bytes = canonical(event)
    event_path.write_bytes(event_bytes)
    index_reference = dict(reference)
    index_reference["event_relative_path"] = event_path.relative_to(args.run_dir).as_posix()
    index_reference["event_sha256"] = hashlib.sha256(event_bytes).hexdigest()
    index = {
        "schema_version": "airi.behavior-checkpoint-index.v2", "run_id": args.run_id,
        "latest": index_reference, "previous": None, "previous_index_sha256": None,
    }
    (args.run_dir / "checkpoints" / "checkpoint-index.json").write_bytes(
        canonical(index))
    progress = {
        "schema_version": "airi.behavior-training-progress.v1",
        "run_id": args.run_id, "status": "paused-safe", "epoch": 0,
        "next_batch_index": 16, "microsteps_completed": 16,
        "optimizer_steps": 1, "pending_microbatches": 0,
        "checkpoint": reference, "updated_at_utc": now,
    }
    (args.run_dir / "progress.json").write_bytes(canonical(progress))
    ack = {
        "schema_version": "airi.behavior-pause-ack.v1",
        "run_id": args.run_id, "request_id": request["request_id"],
        "checkpoint_manifest_sha256": reference["manifest_sha256"],
        "checkpoint_relative_path": generation,
        "acknowledged_at_utc": now, "safe_to_power_off": True,
    }
    (args.run_dir / "control" / "pause.ack.json").write_bytes(canonical(ack))
    raise SystemExit(75)

if not args.resume_from_checkpoint.is_dir():
    raise SystemExit(9)
request = json.loads((args.run_dir / "control" / "pause.request.json").read_text())
ack = json.loads((args.run_dir / "control" / "pause.ack.json").read_text())
accepted = {
    "schema_version": "airi.behavior-resume-accepted.v1",
    "run_id": args.run_id, "request_id": request["request_id"],
    "checkpoint_relative_path": ack["checkpoint_relative_path"],
    "checkpoint_manifest_sha256": ack["checkpoint_manifest_sha256"],
}
(args.run_dir / "control" / "resume.accepted.json").write_bytes(canonical(accepted))
args.output.mkdir(parents=True)
(args.output / "adapter.bin").write_bytes(b"adapter")
args.report.write_text("{}\n", encoding="utf-8")
progress_path = args.run_dir / "progress.json"
progress = json.loads(progress_path.read_text(encoding="utf-8"))
progress.update({"status": "completed", "epoch": 1,
                 "next_batch_index": 0, "microsteps_completed": 32,
                 "optimizer_steps": 2, "updated_at_utc": now})
progress_path.write_bytes(canonical(progress))
'''


def _arguments(root: Path, trainer: Path, *, resume: bool = False) -> list[str]:
    dataset = root / "dataset.jsonl"
    model_dir = root / "model"
    if not dataset.exists():
        dataset.write_bytes(b"{}\n")
    model_dir.mkdir(exist_ok=True)
    config = model_dir / "config.json"
    if not config.exists():
        config.write_bytes(b"{}\n")
    model_weight = model_dir / "model.safetensors"
    if not model_weight.exists():
        model_weight.write_bytes(b"synthetic-model\n")
    helper = trainer.parent / "behavior_training_checkpoint.py"
    if not helper.exists():
        helper.write_bytes(b"# synthetic checkpoint helper\n")
    training_config = {
        "mode": "cpu-smoke", "seed": 42, "lora_r": 8, "lora_alpha": 16,
        "lora_dropout": 0.0, "learning_rate": 0.0002, "max_steps": 32,
        "batch_size": 1, "gradient_accumulation": 1, "max_seq_len": 128,
        "checkpoint_every_optimizer_steps": 5, "deterministic_validation": False,
    }
    manifest = root / "input-manifest.json"
    manifest_payload = {
        "schema_version": "airi.behavior-input-manifest.v2",
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "model_weight_sha256": hashlib.sha256(model_weight.read_bytes()).hexdigest(),
        "trainer_source_sha256": hashlib.sha256(trainer.read_bytes()).hexdigest(),
        "checkpoint_helper_source_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        "training_config": training_config,
        "training_config_sha256": hashlib.sha256(
            runner.canonical_bytes(training_config)).hexdigest(),
        "model_inventory": [
            {"path": item.relative_to(model_dir).as_posix(), "bytes": item.stat().st_size,
             "sha256": hashlib.sha256(item.read_bytes()).hexdigest()}
            for item in sorted(model_dir.rglob("*")) if item.is_file()
        ],
    }
    manifest.write_bytes(runner.canonical_bytes(manifest_payload))
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    values = [
        "--run-dir", str(root / "run"), "--run-id", "integration-run",
        "--python", sys.executable, "--trainer", str(trainer),
        "--working-directory", str(root), "--input-manifest-path", str(manifest),
        "--input-manifest-sha256", manifest_sha256,
        "--checkpoint-every-optimizer-steps", "5", "--heartbeat-seconds", "0.05",
    ]
    if resume:
        values.append("--resume-interrupted")
    values.extend([
        "--", "--dataset", str(dataset), "--dataset-sha256", manifest_payload["dataset_sha256"],
        "--model-dir", str(model_dir), "--model-sha256", manifest_payload["model_weight_sha256"],
        "--output", str(root / "adapter"), "--report", str(root / "report.json"),
        "--mode", "cpu-smoke", "--seed", "42", "--lora-r", "8",
        "--lora-alpha", "16", "--lora-dropout", "0.0", "--learning-rate", "0.0002",
        "--max-steps", "32", "--batch-size", "1", "--gradient-accumulation", "1",
        "--max-seq-len", "128",
    ])
    return values


def _with_runner_flag(arguments: list[str], flag: str) -> list[str]:
    values = list(arguments)
    values.insert(values.index("--"), flag)
    return values


def _synthetic_live_state(revision: int = 0) -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": runner.RUN_STATE_SCHEMA, "revision": revision,
        "run_id": "state-recovery", "status": "running",
        "created_at_utc": "2026-01-01T00:00:00+00:00",
        "updated_at_utc": "2026-01-01T00:00:00+00:00",
        "runner": {"pid": 1, "creation_time_utc": "2026-01-01T00:00:00+00:00",
                   "executable_path_sha256": digest, "command_line_sha256": digest},
        "trainer": None, "inputs": {}, "command": {}, "progress": {},
        "heartbeat": {}, "checkpoint": None, "logs": {}, "outputs": {}, "terminal": None,
    }


def _next_synthetic_state(state: dict[str, object]) -> dict[str, object]:
    value = dict(state)
    value["revision"] = int(value["revision"]) + 1
    return value


def _receipt(path: Path) -> dict[str, object]:
    state = json.loads(path.read_text(encoding="utf-8"))
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "revision": state["revision"]}


def test_manifest_builder_hashes_actual_inputs_and_never_replaces_output() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset = root / "dataset.jsonl"
        model_dir = root / "model"
        model_dir.mkdir()
        model_weight = model_dir / "model.safetensors"
        trainer = root / "trainer.py"
        manifest = root / "input-manifest.json"
        dataset.write_bytes(b"{}\n")
        model_weight.write_bytes(b"model")
        (model_dir / "config.json").write_bytes(b"{}\n")
        (model_dir / "generation_config.json").write_bytes(b"{}\n")
        (model_dir / "merge-evidence.bin").write_bytes(b"extra")
        trainer.write_bytes(b"# trainer\n")
        (root / "behavior_training_checkpoint.py").write_bytes(b"# helper\n")
        command = [
            sys.executable, str(BUILDER), "--output", str(manifest),
            "--dataset", str(dataset), "--dataset-sha256",
            hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "--model-weight", str(model_weight), "--model-sha256",
            hashlib.sha256(model_weight.read_bytes()).hexdigest(),
            "--trainer", str(trainer), "--mode", "cuda-qlora",
            "--seed", "42", "--lora-r", "8", "--lora-alpha", "16",
            "--lora-dropout", "0.05", "--learning-rate", "2e-5",
            "--max-steps", "480", "--batch-size", "1",
            "--gradient-accumulation", "16", "--max-seq-len", "2048",
            "--checkpoint-every-optimizer-steps", "5",
            "--deterministic-validation",
        ]
        built = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        assert built.returncode == 0, built.stderr
        receipt = json.loads(built.stdout)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert manifest.read_bytes() == runner.canonical_bytes(payload)
        assert receipt["sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
        assert receipt["training_config_sha256"] == hashlib.sha256(
            runner.canonical_bytes(payload["training_config"])).hexdigest()
        assert [row["path"] for row in payload["model_inventory"]] == [
            "config.json", "generation_config.json", "merge-evidence.bin", "model.safetensors"]
        trainer_args = _trainer_arguments_for_manifest_test(payload) + [
            "--model-dir", str(model_dir)]
        runner.validate_input_manifest_content(
            manifest, receipt["sha256"], trainer_args,
                payload["trainer_source_sha256"], payload["dataset_sha256"],
                payload["model_weight_sha256"], 5,
                payload["checkpoint_helper_source_sha256"])
        (model_dir / "unexpected.json").write_bytes(b"unexpected")
        with pytest.raises(runner.DurableRunnerError, match="closed exact"):
            runner.validate_input_manifest_content(
                manifest, receipt["sha256"], trainer_args,
                payload["trainer_source_sha256"], payload["dataset_sha256"],
                payload["model_weight_sha256"], 5,
                payload["checkpoint_helper_source_sha256"])
        (model_dir / "unexpected.json").unlink()
        (model_dir / "generation_config.json").unlink()
        with pytest.raises(runner.DurableRunnerError, match="closed exact"):
            runner.validate_input_manifest_content(
                manifest, receipt["sha256"], trainer_args,
                payload["trainer_source_sha256"], payload["dataset_sha256"],
                payload["model_weight_sha256"], 5,
                payload["checkpoint_helper_source_sha256"])

        original = manifest.read_bytes()
        refused = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        assert refused.returncode == 2
        assert "already exists" in refused.stderr
        assert manifest.read_bytes() == original


def test_write_state_recovers_corrupt_current_from_anchor_current_predecessor() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary)
        initial = _synthetic_live_state()
        runner._write_state(run_dir, initial)
        current = run_dir / "run-state.json"
        previous = run_dir / "run-state.prev.json"
        authoritative = current.read_bytes()
        previous.write_bytes(authoritative)
        current.write_bytes(b'{"torn":true}\n')
        runner._write_state(run_dir, _next_synthetic_state(initial))
        assert json.loads(current.read_text())["revision"] == 1
        assert previous.read_bytes() == authoritative
        assert any((run_dir / "quarantine").glob("run-state.corrupt.*.json"))


def test_write_state_retains_only_anchor_previous_after_corrupt_current() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary)
        oldest = _synthetic_live_state()
        runner._write_state(run_dir, oldest)
        current = run_dir / "run-state.json"
        previous = run_dir / "run-state.prev.json"
        older_bytes = current.read_bytes()
        current_state = _next_synthetic_state(oldest)
        runner._write_state(run_dir, current_state)
        assert previous.read_bytes() == older_bytes
        current.write_bytes(b'{"torn":true}\n')
        runner._write_state(run_dir, _next_synthetic_state(current_state))
        assert previous.read_bytes() == older_bytes
        assert json.loads(current.read_text())["revision"] == 2


def test_write_state_quarantines_unbound_predecessor_and_valid_competitor() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary)
        initial = _synthetic_live_state()
        runner._write_state(run_dir, initial)
        current = run_dir / "run-state.json"
        previous = run_dir / "run-state.prev.json"
        previous.write_bytes(b'{"forged":true}\n')
        competitor = _next_synthetic_state(initial)
        competitor["heartbeat"] = {"competitor": True}
        current.write_bytes(runner.canonical_bytes(competitor))
        runner._write_state(run_dir, _next_synthetic_state(competitor))
        quarantine = run_dir / "quarantine"
        assert any(quarantine.glob("run-state.corrupt.*.json"))
        assert any(quarantine.glob("run-state-prev.corrupt.*.json"))
        assert json.loads(current.read_text())["revision"] == 2
        assert not previous.exists()


def test_write_state_recovers_current_publish_before_anchor_only_from_authenticated_previous() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary)
        initial = _synthetic_live_state()
        runner._write_state(run_dir, initial)
        current = run_dir / "run-state.json"
        previous = run_dir / "run-state.prev.json"
        authenticated = current.read_bytes()
        previous.write_bytes(authenticated)
        # Simulate the durable current publication completing before its anchor.
        current.write_bytes(runner.canonical_bytes(_next_synthetic_state(initial)))
        runner._write_state(run_dir, _next_synthetic_state(initial))
        assert previous.read_bytes() == authenticated
        assert json.loads(current.read_text())["revision"] == 1
        assert any((run_dir / "quarantine").glob("run-state.corrupt.*.json"))


def test_tampered_predecessor_never_becomes_anchor_authorized() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary)
        initial = _synthetic_live_state()
        runner._write_state(run_dir, initial)
        current = run_dir / "run-state.json"
        previous = run_dir / "run-state.prev.json"
        current.write_bytes(b'{"torn":true}\n')
        forged = _next_synthetic_state(initial)
        previous.write_bytes(runner.canonical_bytes(forged))
        assert runner.load_run_state_with_previous(run_dir) == (None, None)
        # Re-create the corrupt cut and prove publication quarantines the forged
        # predecessor instead of anchoring it.
        current.write_bytes(b'{"torn":true}\n')
        runner._write_state(run_dir, _next_synthetic_state(initial))
        assert any((run_dir / "quarantine").glob("run-state-prev.corrupt.*.json"))


@pytest.mark.parametrize(("flag", "value"), [
    ("--lora-dropout", "nan"),
    ("--lora-dropout", "inf"),
    ("--learning-rate", "nan"),
    ("--learning-rate", "inf"),
])
def test_manifest_builder_rejects_nonfinite_configuration_before_publication(
        flag: str, value: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset, model_weight, trainer = root / "dataset.jsonl", root / "model.bin", root / "trainer.py"
        output = root / "input-manifest.json"
        dataset.write_bytes(b"{}\n")
        model_weight.write_bytes(b"model")
        trainer.write_bytes(b"# trainer\n")
        command = [
            sys.executable, str(BUILDER), "--output", str(output),
            "--dataset", str(dataset), "--dataset-sha256", hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "--model-weight", str(model_weight), "--model-sha256", hashlib.sha256(model_weight.read_bytes()).hexdigest(),
            "--trainer", str(trainer), "--mode", "cuda-qlora", "--seed", "42",
            "--lora-r", "8", "--lora-alpha", "16", "--lora-dropout", "0.05",
            "--learning-rate", "2e-5", "--max-steps", "480", "--batch-size", "1",
            "--gradient-accumulation", "16", "--max-seq-len", "2048",
            "--checkpoint-every-optimizer-steps", "5",
        ]
        command[command.index(flag) + 1] = value
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        assert result.returncode == 2
        assert "dropout/learning-rate" in result.stderr
        assert not output.exists()


def _trainer_arguments_for_manifest_test(manifest: dict[str, object]) -> list[str]:
    config = manifest["training_config"]
    assert isinstance(config, dict)
    arguments = [
        "--mode", str(config["mode"]), "--seed", str(config["seed"]),
        "--lora-r", str(config["lora_r"]), "--lora-alpha", str(config["lora_alpha"]),
        "--lora-dropout", str(config["lora_dropout"]),
        "--learning-rate", str(config["learning_rate"]),
        "--max-steps", str(config["max_steps"]), "--batch-size", str(config["batch_size"]),
        "--gradient-accumulation", str(config["gradient_accumulation"]),
        "--max-seq-len", str(config["max_seq_len"]),
    ]
    if config["deterministic_validation"]:
        arguments.append("--deterministic-validation")
    return arguments


def test_manifest_binding_rejects_missing_mismatch_and_path_swap_without_run_state() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        runner_script = HERE / "durable_training_runner.py"
        arguments = _arguments(root, trainer)

        missing = list(arguments)
        path_index = missing.index("--input-manifest-path") + 1
        missing[path_index] = str(root / "missing-manifest.json")
        missing_result = subprocess.run(
            [sys.executable, str(runner_script), *missing], cwd=root,
            capture_output=True, text=True, check=False)
        assert missing_result.returncode == 2
        assert not (root / "run").exists()

        mismatch = list(arguments)
        hash_index = mismatch.index("--input-manifest-sha256") + 1
        mismatch[hash_index] = "f" * 64
        mismatch_result = subprocess.run(
            [sys.executable, str(runner_script), *mismatch], cwd=root,
            capture_output=True, text=True, check=False)
        assert mismatch_result.returncode == 2
        assert not (root / "run").exists()

        manifest = root / "input-manifest.json"
        moved = root / "original-manifest.json"
        manifest.replace(moved)
        manifest.write_bytes(b'{"schema_version":2}\n')
        swapped_result = subprocess.run(
            [sys.executable, str(runner_script), *arguments], cwd=root,
            capture_output=True, text=True, check=False)
        assert swapped_result.returncode == 2
        assert "does not match its bytes" in swapped_result.stderr
        assert not (root / "run").exists()

        manifest.write_bytes(runner.canonical_bytes({"schema_version": 1}))
        schema_mismatch = list(arguments)
        schema_mismatch[hash_index] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        schema_result = subprocess.run(
            [sys.executable, str(runner_script), *schema_mismatch], cwd=root,
            capture_output=True, text=True, check=False)
        assert schema_result.returncode == 2
        assert "schema mismatch" in schema_result.stderr
        assert not (root / "run").exists()


def test_runner_rejects_nonfinite_manifest_before_creating_run_dir() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        arguments = _arguments(root, trainer)
        manifest = root / "input-manifest.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["training_config"]["learning_rate"] = float("nan")
        manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                            encoding="utf-8", newline="\n")
        arguments[arguments.index("--input-manifest-sha256") + 1] = hashlib.sha256(
            manifest.read_bytes()).hexdigest()
        result = subprocess.run(
            [sys.executable, str(HERE / "durable_training_runner.py"), *arguments], cwd=root,
            capture_output=True, text=True, check=False)
        assert result.returncode == 2
        assert "non-canonical" in result.stderr
        assert not (root / "run").exists()


def test_runner_rejects_nan_heartbeat_before_run_dir_or_trainer_side_effect() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        marker = root / "trainer-started.marker"
        trainer = root / "fake_trainer.py"
        trainer.write_text(f"from pathlib import Path\nPath(r'{marker}').write_text('started')\n",
                           encoding="utf-8", newline="\n")
        arguments = _arguments(root, trainer)
        arguments[arguments.index("--heartbeat-seconds") + 1] = "nan"
        result = subprocess.run(
            [sys.executable, str(HERE / "durable_training_runner.py"), *arguments], cwd=root,
            capture_output=True, text=True, check=False)
        assert result.returncode == 2
        assert "heartbeat" in result.stderr
        assert not (root / "run").exists()
        assert not marker.exists()


def test_manifest_validation_uses_one_snapshot_across_hash_parse_cutpoint() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        arguments = _arguments(root, trainer)
        manifest = root / "input-manifest.json"
        payload = manifest.read_bytes()
        parsed_payload = json.loads(payload)
        digest = hashlib.sha256(payload).hexdigest()
        original_loads = runner.json.loads

        def replace_after_snapshot(value, *args, **kwargs):
            manifest.write_bytes(b'{"replaced":true}\n')
            return original_loads(value, *args, **kwargs)

        with mock.patch.object(runner.json, "loads", side_effect=replace_after_snapshot):
            runner.validate_input_manifest_content(
                manifest, digest, _trainer_arguments_for_manifest_test(parsed_payload),
                hashlib.sha256(trainer.read_bytes()).hexdigest(),
                str(parsed_payload["dataset_sha256"]),
                str(parsed_payload["model_weight_sha256"]), 5,
                str(parsed_payload["checkpoint_helper_source_sha256"]))
        assert manifest.read_bytes() == b'{"replaced":true}\n'


def test_input_snapshot_keeps_durable_error_type_not_checkpoint_override() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        missing = Path(temporary) / "missing-manifest.json"
        with pytest.raises(runner.DurableRunnerError) as error:
            runner._read_regular_file_snapshot(missing, "input manifest")


def test_held_v2_inputs_close_every_handle_after_partial_open_failure() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        _arguments(root, trainer)
        dataset = root / "dataset.jsonl"
        model_dir = root / "model"
        inventory = json.loads((root / "input-manifest.json").read_text())["model_inventory"]
        opened: list[runner._HeldRegularInput] = []
        original = runner._open_held_regular_input

        def fail_second(path, label):
            if opened:
                raise runner.DurableRunnerError("injected second open failure")
            handle = original(path, label)
            opened.append(handle)
            return handle

        with mock.patch.object(runner, "_open_held_regular_input", side_effect=fail_second):
            with pytest.raises(runner.DurableRunnerError, match="injected"):
                runner._hold_training_inputs(
                    dataset, hashlib.sha256(dataset.read_bytes()).hexdigest(), model_dir, inventory)
        assert opened[0].descriptor == -1


@pytest.mark.skipif(os.name == "nt", reason="POSIX permits atomic pathname replacement")
def test_held_v2_inputs_detect_posix_path_swap_after_child_cutpoint() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset = root / "dataset.jsonl"
        model_dir = root / "model"
        model_dir.mkdir()
        dataset.write_bytes(b"original\n")
        model = model_dir / "model.safetensors"
        model.write_bytes(b"model\n")
        inventory = [{"path": "model.safetensors", "bytes": model.stat().st_size,
                      "sha256": hashlib.sha256(model.read_bytes()).hexdigest()}]
        held = runner._hold_training_inputs(
            dataset, hashlib.sha256(dataset.read_bytes()).hexdigest(), model_dir, inventory)
        try:
            replacement = root / "replacement.jsonl"
            replacement.write_bytes(b"replacement\n")
            replacement.replace(dataset)
            with pytest.raises(runner.DurableRunnerError, match="path changed"):
                runner._verify_held_training_inputs(held)
        finally:
            for handle in held:
                handle.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows share-mode semantics")
def test_held_v2_inputs_deny_windows_write_delete_and_replacement() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset = root / "dataset.jsonl"
        model_dir = root / "model"
        model_dir.mkdir()
        dataset.write_bytes(b"original\n")
        model = model_dir / "model.safetensors"
        model.write_bytes(b"model\n")
        inventory = [{"path": "model.safetensors", "bytes": model.stat().st_size,
                      "sha256": hashlib.sha256(model.read_bytes()).hexdigest()}]
        held = runner._hold_training_inputs(
            dataset, hashlib.sha256(dataset.read_bytes()).hexdigest(), model_dir, inventory)
        try:
            with pytest.raises(PermissionError):
                dataset.write_bytes(b"write denied\n")
            with pytest.raises(PermissionError):
                dataset.unlink()
            replacement = root / "replacement.jsonl"
            replacement.write_bytes(b"replacement\n")
            with pytest.raises(PermissionError):
                replacement.replace(dataset)
        finally:
            for handle in held:
                handle.close()


def test_closed_model_inventory_rejects_reparse_before_walk_recursion() -> None:
    class Entry:
        name = "junction"
        path = "C:/synthetic-model/junction"

        def is_symlink(self):
            return False

        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)

    class Scan:
        def __enter__(self):
            return [Entry()]

        def __exit__(self, *_args):
            return False

    with mock.patch.object(runner, "validate_local_path", return_value=Path("C:/synthetic-model")), \
         mock.patch.object(Path, "is_dir", return_value=True), \
         mock.patch.object(runner.os, "scandir", return_value=Scan()) as scandir:
        with pytest.raises(runner.DurableRunnerError, match="reparse"):
            runner._validate_closed_model_inventory(Path("C:/synthetic-model"), [])
    scandir.assert_called_once()


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse semantics")
def test_closed_model_inventory_rejects_actual_windows_symlink_directory() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "model"
        target = Path(temporary) / "target"
        root.mkdir()
        target.mkdir()
        (target / "config.json").write_bytes(b"{}")
        link = root / "linked"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlink privilege unavailable: {exc}")
        with pytest.raises(runner.DurableRunnerError, match="reparse"):
            runner._validate_closed_model_inventory(root, [])


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse semantics")
def test_closed_model_inventory_rejects_actual_windows_junction_before_target_read() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "model"
        target = Path(temporary) / "target"
        root.mkdir()
        target.mkdir()
        (target / "config.json").write_bytes(b"target-must-not-be-read")
        junction = root / "junction"
        made = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J",
                                str(junction), str(target)], capture_output=True, text=True)
        assert made.returncode == 0, made.stderr
        with pytest.raises(runner.DurableRunnerError, match="reparse"):
            runner._validate_closed_model_inventory(root, [])


def test_load_json_refuses_final_component_snapshot_failure() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "run-state.json"
        path.write_bytes(b"{}\n")
        with mock.patch.object(
                runner, "_read_regular_file_snapshot",
                side_effect=runner.DurableRunnerError("JSON receipt must be a local regular file")):
            with pytest.raises(runner.DurableRunnerError, match="invalid JSON receipt"):
                runner._load_json(path)


def test_checkpoint_manifest_validation_uses_one_snapshot_across_parse_cutpoint() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_snapshot_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
                "trainer_source_sha256": "c" * 64}
        published = checkpoint.publish_checkpoint(
            root, "snapshot-run", "checkpoint-00000001", b"original", pins)
        reference = {"relative_path": "checkpoint-00000001",
                     "manifest_sha256": published["manifest_sha256"]}
        manifest_path = root / "checkpoints" / "checkpoint-00000001" / "manifest.json"
        original_loads = runner.json.loads

        def replace_after_snapshot(value, *args, **kwargs):
            manifest_path.write_bytes(b'{"replacement":true}\n')
            return original_loads(value, *args, **kwargs)

        with mock.patch.object(runner.json, "loads", side_effect=replace_after_snapshot):
            validated = runner.validate_checkpoint_reference(root, reference)
        assert validated["manifest"]["run_id"] == "snapshot-run"
        assert manifest_path.read_bytes() == b'{"replacement":true}\n'
        with pytest.raises(runner.CheckpointIntegrityError, match="manifest integrity"):
            runner.validate_checkpoint_reference(root, reference)


def test_checkpoint_payload_validation_uses_one_snapshot_across_hash_cutpoint() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_payload_snapshot_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
                "trainer_source_sha256": "c" * 64}
        published = checkpoint.publish_checkpoint(
            root, "snapshot-run", "checkpoint-00000001", b"original", pins)
        reference = {"relative_path": "checkpoint-00000001",
                     "manifest_sha256": published["manifest_sha256"]}
        payload_path = root / "checkpoints" / "checkpoint-00000001" / "state.pt"
        original_snapshot = runner._read_regular_file_snapshot

        def replace_after_snapshot(path, label):
            payload = original_snapshot(path, label)
            if label == "checkpoint payload":
                path.write_bytes(b"replacement")
            return payload

        with mock.patch.object(
                runner, "_read_regular_file_snapshot", side_effect=replace_after_snapshot):
            validated = runner.validate_checkpoint_reference(root, reference)
        assert validated["manifest"]["payload"]["sha256"] == hashlib.sha256(
            b"original").hexdigest()
        assert payload_path.read_bytes() == b"replacement"
        with pytest.raises(runner.CheckpointIntegrityError, match="payload integrity"):
            runner.validate_checkpoint_reference(root, reference)


def test_fresh_publication_preserves_competitor_at_check_publish_cutpoint() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "pause.request.json"
        original_write = runner._write_fsynced

        def competitor(stage, payload):
            original_write(stage, payload)
            target.write_bytes(b"competitor\n")

        with mock.patch.object(runner, "_write_fsynced", side_effect=competitor):
            with pytest.raises(runner.DurableRunnerError, match="appeared during publication"):
                runner.publish_new_bytes(target, b"ours\n", "prearm")
        assert target.read_bytes() == b"competitor\n"


def test_manifest_binding_persists_path_and_sha_and_prearms_before_spawn() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        runner_script = HERE / "durable_training_runner.py"
        result = subprocess.run(
            [sys.executable, str(runner_script),
             *_with_runner_flag(_arguments(root, trainer),
                                "--pause-at-first-optimizer-boundary")],
            cwd=root, capture_output=True, text=True, check=False)
        assert result.returncode == 75, result.stderr
        state = json.loads((root / "run" / "run-state.json").read_text())
        request = json.loads((root / "run" / "control" / "pause.request.json").read_text())
        assert state["inputs"]["input_manifest_path"] == str(root / "input-manifest.json")
        assert state["inputs"]["input_manifest_sha256"] == hashlib.sha256(
            (root / "input-manifest.json").read_bytes()).hexdigest()
        assert request["run_id"] == "integration-run"
        assert request["request_id"].startswith("prearm-")
        assert state["status"] == "paused-safe"
        verification = state["terminal"]["checkpoint_verification"]
        manifest_path = root / "run" / "checkpoints" / "checkpoint-00000001" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert verification == {
            "schema_version": runner.CHECKPOINT_VERIFICATION_SCHEMA,
            "checkpoint_relative_path": "checkpoint-00000001",
            "checkpoint_manifest_sha256": hashlib.sha256(
                manifest_path.read_bytes()).hexdigest(),
            "checkpoint_payload_sha256": manifest["payload"]["sha256"],
            "checkpoint_payload_bytes": manifest["payload"]["bytes"],
            "canonical_pins_sha256": hashlib.sha256(
                runner.checkpoint_canonical_bytes(manifest["pins"])).hexdigest(),
        }


def test_final_input_mutation_fails_terminal_without_verified_output_promotion() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        mutating = FAKE_TRAINER.replace(
            'parser.add_argument("--dataset-sha256", required=True)',
            'parser.add_argument("--dataset", type=Path, required=True)\n'
            'parser.add_argument("--dataset-sha256", required=True)').replace(
                'args.output.mkdir(parents=True)',
                'args.dataset.write_bytes(b"mutated after launch\\n")\n'
                'args.output.mkdir(parents=True)')
        trainer.write_text(mutating, encoding="utf-8", newline="\n")
        runner_script = HERE / "durable_training_runner.py"
        paused = subprocess.run(
            [sys.executable, str(runner_script), *_with_runner_flag(
                _arguments(root, trainer), "--pause-at-first-optimizer-boundary")],
            cwd=root, capture_output=True, text=True, check=False)
        assert paused.returncode == 75, paused.stderr
        resumed = subprocess.run(
            [sys.executable, str(runner_script), *_arguments(root, trainer, resume=True)],
            cwd=root, capture_output=True, text=True, check=False)
        # Windows denies the child's write at the held share-mode boundary;
        # POSIX lets it write and the supervisor rejects it at child exit.
        assert resumed.returncode in {1, 2}
        if resumed.returncode == 2:
            assert "changed while held" in resumed.stderr
        state = json.loads((root / "run" / "run-state.json").read_text())
        assert state["status"] == "failed"
        assert state["terminal"]["reason"] in {
            "supervisor-durablerunnererror", "trainer-nonzero-exit"}
        assert state["outputs"]["adapter"] == {"path": str(root / "adapter")}
        assert not (root / "run" / "final-evidence-root.json").exists()


def test_final_evidence_binds_adapter_artifact_manifest_file_receipt() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        run_dir = root / "run"
        checkpoints = run_dir / "checkpoints"
        events = run_dir / "checkpoint-events"
        checkpoints.mkdir(parents=True)
        events.mkdir()
        adapter = root / "adapter"
        adapter.mkdir()
        (adapter / "adapter_model.safetensors").write_bytes(b"adapter")
        artifact_manifest = adapter / "artifact-manifest.json"
        artifact_manifest.write_bytes(runner.canonical_bytes({"artifact": "adapter"}))
        report_path = root / "report.json"
        report_path.write_bytes(runner.canonical_bytes({"status": "complete"}))
        adapter_receipt = runner._artifact_receipt(str(adapter))
        report_receipt = runner._artifact_receipt(str(report_path))
        assert adapter_receipt is not None
        assert report_receipt is not None
        artifact_manifest_sha256 = runner.sha256_file(artifact_manifest)
        assert artifact_manifest_sha256 != adapter_receipt["manifest_sha256"]

        event_path = events / "checkpoint-00000001.json"
        event_path.write_bytes(runner.canonical_bytes({"generation": "checkpoint-00000001"}))
        latest = {
            "relative_path": "checkpoint-00000001",
            "manifest_sha256": "a" * 64,
            "event_relative_path": "checkpoint-events/checkpoint-00000001.json",
            "event_sha256": runner.sha256_file(event_path),
        }
        index_path = checkpoints / "checkpoint-index.json"
        index_path.write_bytes(runner.canonical_bytes({
            "schema_version": "airi.behavior-checkpoint-index.v2",
            "run_id": "final-evidence-run", "latest": latest,
            "previous": None, "previous_index_sha256": None,
        }))
        progress = {
            "schema_version": runner.PROGRESS_SCHEMA, "run_id": "final-evidence-run",
            "status": "completed", "epoch": 1, "next_batch_index": 0,
            "microsteps_completed": 16, "optimizer_steps": 1,
            "pending_microbatches": 0, "training_elapsed_ns": 123,
            "checkpoint": {
                "relative_path": latest["relative_path"],
                "manifest_sha256": latest["manifest_sha256"],
            },
            "updated_at_utc": "2026-08-23T00:00:00Z",
        }
        (run_dir / "progress.json").write_bytes(runner.canonical_bytes(progress))
        state = {
            "revision": 7,
            "outputs": {"adapter": adapter_receipt, "report": report_receipt},
        }
        producer = {
            "schema_version": "airi.behavior-producer-evidence-root.v1",
            "run_id": "final-evidence-run",
            "checkpoint_index_sha256": runner.sha256_file(index_path),
            "latest_checkpoint": latest,
            "progress": {
                key: progress[key] for key in (
                    "microsteps_completed", "optimizer_steps",
                    "pending_microbatches", "training_elapsed_ns")
            },
            "report_sha256": report_receipt["sha256"],
            "adapter_artifact_manifest_sha256": adapter_receipt["manifest_sha256"],
        }
        producer_path = run_dir / "producer-evidence-root.json"
        producer_path.write_bytes(runner.canonical_bytes(producer))
        with pytest.raises(runner.DurableRunnerError, match="adapter mismatch"):
            runner._bind_final_evidence_root(
                run_dir, "final-evidence-run", state, progress, {"input": "pinned"})
        assert not (run_dir / "final-evidence-root.json").exists()

        producer["adapter_artifact_manifest_sha256"] = artifact_manifest_sha256
        producer_path.write_bytes(runner.canonical_bytes(producer))
        receipt = runner._bind_final_evidence_root(
            run_dir, "final-evidence-run", state, progress, {"input": "pinned"})
        assert receipt["relative_path"] == "final-evidence-root.json"
        assert receipt["sha256"] == runner.sha256_file(
            run_dir / "final-evidence-root.json")


def test_corrupt_current_run_state_never_authorizes_stale_paused_resume() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        runner_script = HERE / "durable_training_runner.py"
        paused = subprocess.run(
            [sys.executable, str(runner_script), *_with_runner_flag(
                _arguments(root, trainer), "--pause-at-first-optimizer-boundary")],
            cwd=root, capture_output=True, text=True, check=False)
        assert paused.returncode == 75, paused.stderr
        run_dir = root / "run"
        (run_dir / "run-state.prev.json").write_bytes(
            (run_dir / "run-state.json").read_bytes())
        (run_dir / "run-state.json").write_bytes(b'{"torn":true}\n')
        resumed = subprocess.run(
            [sys.executable, str(runner_script), *_arguments(root, trainer, resume=True)],
            cwd=root, capture_output=True, text=True, check=False)
        assert resumed.returncode == 2
        assert "resume requires an existing run-state" in resumed.stderr
        assert not (root / "adapter").exists()


def test_missing_current_run_state_never_authorizes_stale_paused_resume() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        runner_script = HERE / "durable_training_runner.py"
        paused = subprocess.run(
            [sys.executable, str(runner_script), *_with_runner_flag(
                _arguments(root, trainer), "--pause-at-first-optimizer-boundary")],
            cwd=root, capture_output=True, text=True, check=False)
        assert paused.returncode == 75, paused.stderr
        run_dir = root / "run"
        current = run_dir / "run-state.json"
        (run_dir / "run-state.prev.json").write_bytes(current.read_bytes())
        current.unlink()
        resumed = subprocess.run(
            [sys.executable, str(runner_script), *_arguments(root, trainer, resume=True)],
            cwd=root, capture_output=True, text=True, check=False)
        assert resumed.returncode == 2
        assert "resume requires an existing run-state" in resumed.stderr


def test_prearm_is_fresh_only_and_preserves_existing_control_evidence() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        runner_script = HERE / "durable_training_runner.py"
        resume_prearm = _with_runner_flag(
            _arguments(root, trainer, resume=True),
            "--pause-at-first-optimizer-boundary")
        rejected_resume = subprocess.run(
            [sys.executable, str(runner_script), *resume_prearm], cwd=root,
            capture_output=True, text=True, check=False)
        assert rejected_resume.returncode == 2
        assert not (root / "run").exists()

        (root / "run").mkdir()
        rejected_empty = subprocess.run(
            [sys.executable, str(runner_script),
             *_with_runner_flag(_arguments(root, trainer),
                                "--pause-at-first-optimizer-boundary")],
            cwd=root, capture_output=True, text=True, check=False)
        assert rejected_empty.returncode == 2
        assert "absent run directory" in rejected_empty.stderr
        (root / "run").rmdir()

        control = root / "run" / "control"
        control.mkdir(parents=True)
        evidence = control / "pause.request.json"
        evidence.write_bytes(runner.canonical_bytes({
            "schema_version": "airi.behavior-pause-request.v1",
            "run_id": "integration-run", "request_id": "existing-001",
        }))
        rejected_existing = subprocess.run(
            [sys.executable, str(runner_script),
             *_with_runner_flag(_arguments(root, trainer),
                                "--pause-at-first-optimizer-boundary")],
            cwd=root, capture_output=True, text=True, check=False)
        assert rejected_existing.returncode == 2
        assert evidence.read_bytes() == runner.canonical_bytes({
            "schema_version": "airi.behavior-pause-request.v1",
            "run_id": "integration-run", "request_id": "existing-001",
        })


def test_actual_checkpoint_manifest_latest_and_previous_are_compatible() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_for_runner_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {
            "dataset_sha256": "a" * 64,
            "model_weight_sha256": "b" * 64,
            "trainer_source_sha256": "d" * 64,
        }
        checkpoint.publish_checkpoint(
            root, "run-1", "checkpoint-00000001", b"one", pins)
        checkpoint.publish_checkpoint(
            root, "run-1", "checkpoint-00000002", b"two", pins)
        expected = dict(pins)
        expected["input_manifest_sha256"] = "c" * 64
        selected = runner.resolve_resume_checkpoint(root, "run-1", expected)
        assert selected["source"] == "latest"
        (root / "checkpoints" / "checkpoint-00000002" / "state.pt").write_bytes(
            b"corrupt")
        selected = runner.resolve_resume_checkpoint(root, "run-1", expected)
        assert selected["source"] == "previous"
        assert list((root / "quarantine").iterdir())


def test_unacknowledged_pause_request_is_preserved_for_power_cut_resume() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary) / "run"
        control = run_dir / "control"
        control.mkdir(parents=True)
        request = {
            "schema_version": "airi.behavior-pause-request.v1",
            "run_id": "power-cut-run", "request_id": "pause-before-ack",
        }
        request_path = control / "pause.request.json"
        request_path.write_bytes(runner.canonical_bytes(request))
        runner._archive_unacknowledged_pause_request(run_dir, "power-cut-run")
        preserved = control / "history" / "pause-before-ack.unacknowledged.request.json"
        assert not request_path.exists()
        assert json.loads(preserved.read_text(encoding="utf-8")) == request


def test_resume_acceptance_for_n_survives_n_plus_two_rotation_and_archive_fault() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_acceptance_n_plus_two_test",
        HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary) / "run"
        pins = {
            "dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
            "trainer_source_sha256": "d" * 64,
        }
        first = checkpoint.publish_checkpoint(
            run_dir, "archive-recovery", "checkpoint-00000001", b"one", pins)
        reference = {
            "relative_path": "checkpoint-00000001",
            "manifest_sha256": first["manifest_sha256"],
        }
        control = run_dir / "control"
        history = control / "history"
        history.mkdir(parents=True)
        request = {
            "schema_version": "airi.behavior-pause-request.v1",
            "run_id": "archive-recovery", "request_id": "pause-archive-001",
        }
        ack = {
            "schema_version": "airi.behavior-pause-ack.v1",
            "run_id": "archive-recovery", "request_id": "pause-archive-001",
            "checkpoint_manifest_sha256": reference["manifest_sha256"],
            "checkpoint_relative_path": reference["relative_path"],
            "acknowledged_at_utc": "2026-08-22T00:00:00Z",
            "safe_to_power_off": True,
        }
        accepted = {
            "schema_version": "airi.behavior-resume-accepted.v1",
            "run_id": "archive-recovery", "request_id": "pause-archive-001",
            "checkpoint_relative_path": reference["relative_path"],
            "checkpoint_manifest_sha256": reference["manifest_sha256"],
        }
        # Simulate power loss after the request moved but before ack/acceptance.
        (history / "pause-archive-001.request.json").write_bytes(
            runner.canonical_bytes(request))
        (control / "pause.ack.json").write_bytes(runner.canonical_bytes(ack))
        (control / "resume.accepted.json").write_bytes(runner.canonical_bytes(accepted))
        checkpoint.publish_checkpoint(
            run_dir, "archive-recovery", "checkpoint-00000002", b"two", pins)
        third = checkpoint.publish_checkpoint(
            run_dir, "archive-recovery", "checkpoint-00000003", b"three", pins)
        assert (run_dir / "checkpoints" / "checkpoint-00000001").is_dir()
        assert not (run_dir / "archive" / "checkpoint-00000001").exists()
        assert runner._archive_accepted_pause_control(
            run_dir, "archive-recovery",
            {**pins, "input_manifest_sha256": "c" * 64})
        assert (history / "pause-archive-001.ack.json").is_file()
        assert (history / "pause-archive-001.resume-accepted.json").is_file()
        assert not (control / "pause.ack.json").exists()
        assert not (control / "resume.accepted.json").exists()
        selected = runner.resolve_resume_checkpoint(
            run_dir, "archive-recovery",
            {**pins, "input_manifest_sha256": "c" * 64})
        assert selected["relative_path"] == "checkpoint-00000003"
        assert selected["manifest_sha256"] == third["manifest_sha256"]


@pytest.mark.parametrize(
    "already_archived",
    [
        {"request"}, {"ack"}, {"accepted"},
        {"request", "ack"}, {"request", "accepted"},
        {"ack", "accepted"}, {"request", "ack", "accepted"},
    ],
)
def test_pause_archive_recovers_every_power_cut_subset(already_archived) -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_archive_cutpoints_test",
        HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary) / "run"
        pins = {"dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
                "trainer_source_sha256": "d" * 64}
        published = checkpoint.publish_checkpoint(
            run_dir, "archive-cutpoints", "checkpoint-00000001", b"state", pins)
        request_id = "pause-cutpoint-001"
        control = run_dir / "control"
        history = control / "history"
        history.mkdir(parents=True)
        values = {
            "request": {
                "schema_version": "airi.behavior-pause-request.v1",
                "run_id": "archive-cutpoints", "request_id": request_id,
            },
            "ack": {
                "schema_version": "airi.behavior-pause-ack.v1",
                "run_id": "archive-cutpoints", "request_id": request_id,
                "checkpoint_manifest_sha256": published["manifest_sha256"],
                "checkpoint_relative_path": "checkpoint-00000001",
                "acknowledged_at_utc": "2026-08-22T00:00:00Z",
                "safe_to_power_off": True,
            },
            "accepted": {
                "schema_version": "airi.behavior-resume-accepted.v1",
                "run_id": "archive-cutpoints", "request_id": request_id,
                "checkpoint_relative_path": "checkpoint-00000001",
                "checkpoint_manifest_sha256": published["manifest_sha256"],
            },
        }
        live = {
            "request": control / "pause.request.json",
            "ack": control / "pause.ack.json",
            "accepted": control / "resume.accepted.json",
        }
        archived = {
            "request": history / f"{request_id}.request.json",
            "ack": history / f"{request_id}.ack.json",
            "accepted": history / f"{request_id}.resume-accepted.json",
        }
        for name, path in live.items():
            path.write_bytes(runner.canonical_bytes(values[name]))
        for name in already_archived:
            live[name].replace(archived[name])

        recovered = runner._archive_accepted_pause_control(
            run_dir, "archive-cutpoints",
            {**pins, "input_manifest_sha256": "c" * 64})
        assert recovered is (already_archived != {"request", "ack", "accepted"})
        for name in values:
            assert not live[name].exists()
            assert archived[name].read_bytes() == runner.canonical_bytes(values[name])


def test_pause_archive_removes_identical_live_history_duplicate() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_archive_duplicate_test",
        HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary) / "run"
        pins = {"dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
                "trainer_source_sha256": "d" * 64}
        published = checkpoint.publish_checkpoint(
            run_dir, "archive-duplicate", "checkpoint-00000001", b"state", pins)
        control = run_dir / "control"
        history = control / "history"
        history.mkdir(parents=True)
        request_id = "pause-duplicate-001"
        request = {"schema_version": "airi.behavior-pause-request.v1",
                   "run_id": "archive-duplicate", "request_id": request_id}
        ack = {"schema_version": "airi.behavior-pause-ack.v1",
               "run_id": "archive-duplicate", "request_id": request_id,
               "checkpoint_manifest_sha256": published["manifest_sha256"],
               "checkpoint_relative_path": "checkpoint-00000001",
               "acknowledged_at_utc": "2026-08-22T00:00:00Z",
               "safe_to_power_off": True}
        accepted = {"schema_version": "airi.behavior-resume-accepted.v1",
                    "run_id": "archive-duplicate", "request_id": request_id,
                    "checkpoint_relative_path": "checkpoint-00000001",
                    "checkpoint_manifest_sha256": published["manifest_sha256"]}
        (control / "pause.request.json").write_bytes(runner.canonical_bytes(request))
        (history / f"{request_id}.request.json").write_bytes(
            runner.canonical_bytes(request))
        (control / "pause.ack.json").write_bytes(runner.canonical_bytes(ack))
        (control / "resume.accepted.json").write_bytes(
            runner.canonical_bytes(accepted))
        assert runner._archive_accepted_pause_control(
            run_dir, "archive-duplicate",
            {**pins, "input_manifest_sha256": "c" * 64})
        assert not (control / "pause.request.json").exists()
        assert (history / f"{request_id}.request.json").read_bytes() == runner.canonical_bytes(request)


def test_runner_path_validation_rejects_reparse_attributes() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "dataset.jsonl"
        path.write_bytes(b"{}\n")
        fake_stat = SimpleNamespace(
            st_file_attributes=0x400,
            st_mode=stat.S_IFREG)
        with mock.patch.object(runner.os, "lstat", return_value=fake_stat):
            with pytest.raises(runner.DurableRunnerError, match="reparse"):
                runner.validate_local_path(path, "dataset")


def test_torn_current_index_never_authorizes_unbound_predecessor() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_torn_index_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
                "trainer_source_sha256": "d" * 64}
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000002", b"two", pins)
        (root / "checkpoints" / "checkpoint-index.json").write_bytes(b"{")
        with pytest.raises(runner.DurableRunnerError, match="checkpoint index JSON"):
            runner.resolve_resume_checkpoint(
                root, "run-1", {**pins, "input_manifest_sha256": "c" * 64})
        assert list((root / "quarantine").glob("checkpoint-index.*.json"))


def test_structurally_corrupt_current_index_never_authorizes_unbound_predecessor() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_bad_index_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
                "trainer_source_sha256": "d" * 64}
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000002", b"two", pins)
        index_path = root / "checkpoints" / "checkpoint-index.json"
        malformed = {"schema_version": "airi.behavior-checkpoint-index.v1",
                     "latest": {"relative_path": "../escape", "manifest_sha256": "x"},
                     "previous": None}
        index_path.write_text(json.dumps(malformed), encoding="utf-8")
        with pytest.raises(runner.DurableRunnerError):
            runner.resolve_resume_checkpoint(
                root, "run-1", {**pins, "input_manifest_sha256": "c" * 64})
        assert list((root / "quarantine").glob("checkpoint-index.*.json"))


def test_pin_mismatch_refuses_without_quarantining_valid_checkpoint() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_pin_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {
            "dataset_sha256": "a" * 64,
            "model_weight_sha256": "b" * 64,
            "trainer_source_sha256": "d" * 64,
        }
        checkpoint.publish_checkpoint(
            root, "run-1", "checkpoint-00000001", b"one", pins)
        expected = dict(pins)
        expected["dataset_sha256"] = "e" * 64
        with pytest.raises(runner.DurableRunnerError, match="pin mismatch"):
            runner.resolve_resume_checkpoint(root, "run-1", expected)
        assert (root / "checkpoints" / "checkpoint-00000001").is_dir()
        assert not (root / "quarantine").exists()


def test_terminal_state_requires_receipt_and_progress_cannot_regress() -> None:
    state = {
        "schema_version": runner.RUN_STATE_SCHEMA, "revision": 1,
        "run_id": "run-1", "status": "complete",
        "created_at_utc": "now", "updated_at_utc": "now",
        "runner": {"pid": 1, "creation_time_utc": "now",
                   "executable_path_sha256": "a" * 64,
                   "command_line_sha256": "b" * 64},
        "trainer": None, "inputs": {}, "command": {},
        "progress": {"epoch": 1, "next_batch_index": 0,
                     "microsteps_completed": 10, "optimizer_steps": 2,
                     "pending_microbatches": 0},
        "heartbeat": {"sequence": 0, "at_utc": "now", "phase": "running"},
        "checkpoint": None, "logs": {}, "outputs": {},
        "terminal": None,
    }
    with pytest.raises(runner.DurableRunnerError, match="terminal"):
        runner.validate_run_state(state)
    state["status"] = "running"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        stdout = root / "stdout.log"
        stderr = root / "stderr.log"
        stdout.write_bytes(b"")
        stderr.write_bytes(b"")
        progress = {
            "epoch": 1, "next_batch_index": 0, "microsteps_completed": 9,
            "optimizer_steps": 2, "pending_microbatches": 0,
        }
        with pytest.raises(runner.DurableRunnerError, match="backwards"):
            runner._update_runtime_state(
                state, root, progress, stdout, stderr, "running")
        state["progress"] = {"epoch": 1, "next_batch_index": 5,
                             "microsteps_completed": 10, "optimizer_steps": 2,
                             "pending_microbatches": 0}
        progress["microsteps_completed"] = 10
        progress["next_batch_index"] = 4
        with pytest.raises(runner.DurableRunnerError, match="next_batch_index"):
            runner._update_runtime_state(
                state, root, progress, stdout, stderr, "running")
        progress.update({"epoch": 2, "next_batch_index": 0,
                         "microsteps_completed": 11, "optimizer_steps": 2})
        runner._update_runtime_state(state, root, progress, stdout, stderr, "running")
        state["checkpoint"] = {
            "relative_path": "checkpoint-00000002", "manifest_sha256": "a" * 64}
        state["progress"] = {"epoch": 2, "next_batch_index": 0,
                             "microsteps_completed": 11, "optimizer_steps": 2,
                             "pending_microbatches": 0}
        with pytest.raises(runner.DurableRunnerError, match="disappeared"):
            runner._update_runtime_state(
                state, root, dict(state["progress"]), stdout, stderr, "running")


def test_resume_pin_mismatch_preserves_pause_request_and_ack() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        control = root / "run" / "control"
        control.mkdir(parents=True)
        request = {"schema_version": "airi.behavior-pause-request.v1",
                   "run_id": "integration-run", "request_id": "pause-001"}
        (control / "pause.request.json").write_text(
            json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8", newline="\n")
        first = subprocess.run([sys.executable, str(HERE / "durable_training_runner.py"),
                                *_arguments(root, trainer)], cwd=root,
                               capture_output=True, text=True, check=False)
        assert first.returncode == 75, first.stderr
        manifest_path = root / "run" / "checkpoints" / "checkpoint-00000001" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["pins"]["dataset_sha256"] = "f" * 64
        manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        manifest_path.write_bytes(manifest_bytes)
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        reference = {"relative_path": "checkpoint-00000001", "manifest_sha256": digest}
        index_path = root / "run" / "checkpoints" / "checkpoint-index.json"
        index = json.loads(index_path.read_text())
        index["latest"] = reference
        index_path.write_text(json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n")
        progress_path = root / "run" / "progress.json"
        progress = json.loads(progress_path.read_text())
        progress["checkpoint"] = reference
        progress_path.write_text(json.dumps(progress, sort_keys=True, separators=(",", ":")) + "\n")
        ack_path = control / "pause.ack.json"
        ack = json.loads(ack_path.read_text())
        ack["checkpoint_manifest_sha256"] = digest
        ack_path.write_text(json.dumps(ack, sort_keys=True, separators=(",", ":")) + "\n")
        resumed = subprocess.run([sys.executable, str(HERE / "durable_training_runner.py"),
                                  *_arguments(root, trainer, resume=True)], cwd=root,
                                 capture_output=True, text=True, check=False)
        assert resumed.returncode == 2
        assert "checkpoint index" in resumed.stderr
        assert (control / "pause.request.json").is_file()
        assert ack_path.is_file()
        assert not (control / "history").exists()


def test_supervisor_failed_verified_final_artifacts_recover_complete_terminal() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_final_recovery_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    checkpoint.publish_checkpoint = _eventful_publish(checkpoint.publish_checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        run_dir = root / "run"
        run_dir.mkdir()
        trainer = root / "trainer.py"
        trainer.write_text("# recovery fixture\n", encoding="utf-8")
        output = root / "adapter"
        report_path = root / "report.json"
        inputs = {
            "dataset_sha256": "a" * 64,
            "model_weight_sha256": "b" * 64,
            "input_manifest_sha256": "c" * 64,
            "trainer_source_sha256": runner.sha256_file(trainer),
        }
        pins = dict(inputs)
        pins.pop("input_manifest_sha256")
        published_checkpoint = checkpoint.publish_checkpoint(
            run_dir, "recovery-run", "checkpoint-00000001", b"state", pins)
        stage = root / "adapter.tmp"
        stage.mkdir()
        (stage / "adapter_model.safetensors").write_bytes(b"adapter")
        artifact = checkpoint.publish_artifact_directory(
            stage, output, "recovery-run", pins)
        report = {
            "mode": "cuda-qlora", "steps": 16, "optimizer_steps": 1,
            "adapter_dir": str(output),
            "adapter_artifact_manifest_sha256": artifact["manifest_sha256"],
            "dataset_sha256": inputs["dataset_sha256"],
            "model_weight_sha256": inputs["model_weight_sha256"],
            "seed": 42, "training_authorization": True,
            "adoption_authorized": False, "t3_status": "pending",
        }
        checkpoint.atomic_json(report_path, report)
        progress = {
            "schema_version": runner.PROGRESS_SCHEMA, "run_id": "recovery-run",
            "status": "completed", "epoch": 1, "next_batch_index": 0,
            "microsteps_completed": 16, "optimizer_steps": 1,
            "pending_microbatches": 0,
            "checkpoint": {
                "relative_path": "checkpoint-00000001",
                "manifest_sha256": published_checkpoint["manifest_sha256"],
            },
            "updated_at_utc": "2026-08-22T00:00:00Z",
        }
        checkpoint.atomic_json(run_dir / "progress.json", progress)
        trainer_args = [
            "--dataset-sha256", "a" * 64, "--model-sha256", "b" * 64,
            "--output", str(output), "--report", str(report_path),
            "--max-steps", "16", "--seed", "42",
        ]
        args = SimpleNamespace(run_id="recovery-run", trainer=trainer)
        command = [sys.executable, str(trainer), *trainer_args]
        state = runner._base_state(
            args, command, runner.sha256_bytes(runner.canonical_bytes(command)), inputs,
            {}, {"adapter": {"path": str(output)}, "report": {"path": str(report_path)}},
            "running", None)
        state["status"] = "failed"
        state["terminal"] = {
            "exit_code": None, "reason": "supervisor-durablerunnererror",
            "at_utc": "2026-08-22T00:00:01Z",
        }
        assert runner._is_recoverable_final_state(state)
        assert not runner._is_recoverable_final_state({
            **state, "terminal": {
                "exit_code": 2, "reason": "trainer-nonzero-exit",
                "at_utc": "2026-08-22T00:00:01Z",
            },
        })
        assert runner._reconcile_interrupted_final_artifacts(
            state, run_dir, "recovery-run", trainer_args, inputs,
            output, report_path)
        recovered = json.loads((run_dir / "run-state.json").read_text())
        assert recovered["status"] == "complete"
        assert recovered["terminal"]["reason"] == "recovered-complete-artifacts"
        assert recovered["outputs"]["adapter"]["kind"] == "directory"
        runner._validate_completed_outputs(recovered)


def test_interrupted_partial_and_staging_artifacts_are_quarantined() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        run_dir = root / "run"
        run_dir.mkdir()
        output = root / "adapter"
        temporary_output = root / "adapter.tmp"
        temporary_output.mkdir()
        (temporary_output / "partial.bin").write_bytes(b"partial")
        output.mkdir()
        (output / "partial.bin").write_bytes(b"partial")
        report_path = root / "report.json"
        state: dict[str, object] = {}
        assert not runner._reconcile_interrupted_final_artifacts(
            state, run_dir, "recovery-run", [], {
                "dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
                "input_manifest_sha256": "c" * 64, "trainer_source_sha256": "d" * 64,
            }, output, report_path)
        assert not output.exists()
        assert not temporary_output.exists()
        quarantined = list((run_dir / "quarantine" / "runtime-artifacts").iterdir())
        assert len(quarantined) == 2


def test_safe_pause_then_explicit_resume_reaches_atomic_terminal_receipt() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "fake_trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        control = root / "run" / "control"
        control.mkdir(parents=True)
        request = {
            "schema_version": "airi.behavior-pause-request.v1",
            "run_id": "integration-run", "request_id": "pause-001",
        }
        (control / "pause.request.json").write_text(
            json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8", newline="\n")

        runner_script = HERE / "durable_training_runner.py"
        first = subprocess.run(
            [sys.executable, str(runner_script), *_arguments(root, trainer)],
            cwd=root, capture_output=True, text=True, check=False)
        assert first.returncode == 75, first.stderr
        paused = json.loads((root / "run" / "run-state.json").read_text())
        assert paused["status"] == "paused-safe"
        assert paused["terminal"]["reason"] == "safe-optimizer-boundary"
        verification = paused["terminal"]["checkpoint_verification"]
        assert verification["schema_version"] == runner.CHECKPOINT_VERIFICATION_SCHEMA
        assert verification["checkpoint_relative_path"] == "checkpoint-00000001"
        # The immutable run-local trainer snapshot is intentionally distinct
        # from the caller's replaceable source pathname.
        assert paused["command"]["base_canonical_sha256"] != paused["command"]["canonical_sha256"]
        paused_revision = paused["revision"]

        changed = _arguments(root, trainer, resume=True)
        changed.extend(["--test-command-difference", "43"])
        mismatch = subprocess.run(
            [sys.executable, str(runner_script), *changed],
            cwd=root, capture_output=True, text=True, check=False)
        assert mismatch.returncode == 2
        assert "command differs" in mismatch.stderr
        assert (control / "pause.request.json").is_file()
        assert (control / "pause.ack.json").is_file()
        checkpoint_manifest = json.loads(
            (root / "run" / "checkpoints" / "checkpoint-00000001" / "manifest.json").read_text())
        expected_model_sha = hashlib.sha256(
            (root / "model" / "model.safetensors").read_bytes()).hexdigest()
        assert checkpoint_manifest["pins"]["model_weight_sha256"] == expected_model_sha
        assert paused["inputs"]["model_weight_sha256"] == expected_model_sha

        tampered = json.loads((root / "run" / "run-state.json").read_text())
        tampered["terminal"]["checkpoint_verification"][
            "checkpoint_payload_sha256"] = "0" * 64
        (root / "run" / "run-state.json").write_bytes(runner.canonical_bytes(tampered))
        receipt_mismatch = subprocess.run(
            [sys.executable, str(runner_script),
             *_arguments(root, trainer, resume=True)],
            cwd=root, capture_output=True, text=True, check=False)
        assert receipt_mismatch.returncode == 2
        assert "resume requires an existing run-state" in receipt_mismatch.stderr
        assert (control / "pause.request.json").is_file()
        assert (control / "pause.ack.json").is_file()
        (root / "run" / "run-state.json").write_bytes(runner.canonical_bytes(paused))

        second = subprocess.run(
            [sys.executable, str(runner_script),
             *_arguments(root, trainer, resume=True)],
            cwd=root, capture_output=True, text=True, check=False)
        assert second.returncode == 0, second.stderr
        completed = json.loads((root / "run" / "run-state.json").read_text())
        assert completed["status"] == "complete"
        assert completed["terminal"]["exit_code"] == 0
        assert completed["command"]["base_canonical_sha256"] == paused["command"][
            "base_canonical_sha256"]
        assert completed["command"]["canonical_sha256"] != completed["command"][
            "base_canonical_sha256"]
        assert completed["revision"] > paused_revision
        assert completed["progress"]["microsteps_completed"] == 32
        assert (root / "adapter" / "adapter.bin").read_bytes() == b"adapter"
        assert list((control / "history").glob("pause-001.*.json"))
        assert (control / "history" / "pause-001.resume-accepted.json").is_file()

        (root / "adapter" / "adapter.bin").unlink()
        damaged = subprocess.run(
            [sys.executable, str(runner_script),
             *_arguments(root, trainer, resume=True)],
            cwd=root, capture_output=True, text=True, check=False)
        assert damaged.returncode == 2
        failed = json.loads((root / "run" / "run-state.json").read_text())
        assert failed["status"] == "failed"
        assert failed["terminal"]["reason"] == "completed-artifact-integrity-mismatch"


def test_v3_initial_adapter_is_closed_pinned_held_and_kept_on_resume() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trainer = root / "trainer.py"
        trainer.write_text(FAKE_TRAINER, encoding="utf-8", newline="\n")
        arguments = _arguments(root, trainer)
        manifest_path = root / "input-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy_manifest = json.loads(json.dumps(manifest))
        adapter = root / "initial-adapter"
        adapter.mkdir()
        model = adapter / "adapter_model.safetensors"
        config = adapter / "adapter_config.json"
        model.write_bytes(b"adapter-model")
        config.write_bytes(b"{}\n")
        files = [{"path": path.name, "bytes": path.stat().st_size,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                 for path in (config, model)]
        artifact = {"schema_version": "airi.behavior-adapter-artifact.v1",
                    "run_id": "source-run", "pins": {
                        "model_weight_sha256": manifest["model_weight_sha256"]},
                    "files": files}
        artifact_path = adapter / "artifact-manifest.json"
        artifact_path.write_bytes(runner.canonical_bytes(artifact))
        manifest["schema_version"] = "airi.behavior-input-manifest.v3"
        manifest["training_config"]["init_mode"] = "adapter-weights-only"
        manifest["training_config_sha256"] = hashlib.sha256(
            runner.canonical_bytes(manifest["training_config"])).hexdigest()
        manifest["initial_adapter"] = {
            "run_id": "source-run", "model_sha256": files[1]["sha256"],
            "config_sha256": files[0]["sha256"],
            "artifact_manifest_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "files": files,
        }
        manifest_path.write_bytes(runner.canonical_bytes(manifest))
        trailer = ["--init-adapter-dir", str(adapter), "--init-adapter-model-sha256",
                   files[1]["sha256"], "--init-adapter-config-sha256", files[0]["sha256"],
                   "--init-adapter-artifact-manifest-sha256",
                   manifest["initial_adapter"]["artifact_manifest_sha256"]]
        trainer_args = arguments[arguments.index("--") + 1:] + trailer
        identity = runner.validate_input_manifest_content(
            manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest(), trainer_args,
            manifest["trainer_source_sha256"], manifest["dataset_sha256"],
            manifest["model_weight_sha256"], 5, manifest["checkpoint_helper_source_sha256"])
        assert identity["initial_adapter"]["directory"] == str(adapter.resolve())

        extra = adapter / "unexpected.bin"
        extra.write_bytes(b"unexpected")
        with pytest.raises(runner.DurableRunnerError, match="closed exact"):
            runner.validate_input_manifest_content(
                manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest(), trainer_args,
                manifest["trainer_source_sha256"], manifest["dataset_sha256"],
                manifest["model_weight_sha256"], 5,
                manifest["checkpoint_helper_source_sha256"])
        extra.unlink()
        empty = adapter / "unexpected-empty-directory"
        empty.mkdir()
        with pytest.raises(runner.DurableRunnerError, match="closed exact"):
            runner.validate_input_manifest_content(
                manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest(), trainer_args,
                manifest["trainer_source_sha256"], manifest["dataset_sha256"],
                manifest["model_weight_sha256"], 5,
                manifest["checkpoint_helper_source_sha256"])
        empty.rmdir()

        missing_v3_mode = json.loads(json.dumps(manifest))
        del missing_v3_mode["training_config"]["init_mode"]
        missing_v3_mode["training_config_sha256"] = hashlib.sha256(
            runner.canonical_bytes(missing_v3_mode["training_config"])).hexdigest()
        manifest_path.write_bytes(runner.canonical_bytes(missing_v3_mode))
        with pytest.raises(runner.DurableRunnerError, match="configuration schema mismatch"):
            runner.validate_input_manifest_content(
                manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest(), trainer_args,
                manifest["trainer_source_sha256"], manifest["dataset_sha256"],
                manifest["model_weight_sha256"], 5,
                manifest["checkpoint_helper_source_sha256"])
        invalid_v2 = json.loads(json.dumps(legacy_manifest))
        invalid_v2["training_config"]["init_mode"] = "fresh-lora"
        invalid_v2["training_config_sha256"] = hashlib.sha256(
            runner.canonical_bytes(invalid_v2["training_config"])).hexdigest()
        manifest_path.write_bytes(runner.canonical_bytes(invalid_v2))
        with pytest.raises(runner.DurableRunnerError, match="configuration schema mismatch"):
            runner.validate_input_manifest_content(
                manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                arguments[arguments.index("--") + 1:], invalid_v2["trainer_source_sha256"],
                invalid_v2["dataset_sha256"], invalid_v2["model_weight_sha256"], 5,
                invalid_v2["checkpoint_helper_source_sha256"])
        manifest_path.write_bytes(runner.canonical_bytes(manifest))

        command = _with_runner_flag(arguments, "--pause-at-first-optimizer-boundary")
        command[command.index("--input-manifest-sha256") + 1] = hashlib.sha256(
            manifest_path.read_bytes()).hexdigest()
        command.extend(trailer)
        launched = subprocess.run([sys.executable, str(HERE / "durable_training_runner.py"), *command],
                                 cwd=root, capture_output=True, text=True, check=False)
        assert launched.returncode == 75, launched.stderr
        state = json.loads((root / "run" / "run-state.json").read_text(encoding="utf-8"))
        assert state["inputs"]["init_mode"] == "adapter-weights-only"
        assert state["inputs"]["init_adapter_model_sha256"] == files[1]["sha256"]
        resumed_command = list(arguments)
        resumed_command[resumed_command.index("--input-manifest-sha256") + 1] = hashlib.sha256(
            manifest_path.read_bytes()).hexdigest()
        resumed_command = _with_runner_flag(resumed_command, "--resume-interrupted")
        resumed_command.extend(trailer)
        resumed = subprocess.run(
            [sys.executable, str(HERE / "durable_training_runner.py"), *resumed_command],
            cwd=root, capture_output=True, text=True, check=False)
        assert resumed.returncode == 0, resumed.stderr
        completed = json.loads((root / "run" / "run-state.json").read_text(encoding="utf-8"))
        assert completed["inputs"] == state["inputs"]
        assert completed["command"]["base_canonical_sha256"] == state["command"]["base_canonical_sha256"]
        assert completed["command"]["canonical_sha256"] != completed["command"]["base_canonical_sha256"]
        # Regression: the resumed trainer command must keep initial-adapter
        # provenance, or its pins say fresh-lora and the checkpoint pin gate
        # makes every adapter-init run unresumable.
        launches = [json.loads(line)["argv"] for line
                    in (root / "run" / "logs" / "trainer.stdout.log")
                    .read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(launches) == 2, launches
        resumed_argv = launches[1]
        assert "--resume-from-checkpoint" in resumed_argv
        for index in range(0, len(trailer), 2):
            flag, value = trailer[index], trailer[index + 1]
            assert flag in resumed_argv, flag
            assert resumed_argv[resumed_argv.index(flag) + 1] == value, flag
        assert (resumed_argv[resumed_argv.index("--resume-from-checkpoint") + 1]
                == str((root / "run" / "checkpoints" / "checkpoint-00000001").resolve()))
        held = runner._hold_training_inputs(root / "dataset.jsonl", manifest["dataset_sha256"],
                                            root / "model", manifest["model_inventory"],
                                            identity["initial_adapter"])
        try:
            replacement = adapter / "replacement"
            replacement.write_bytes(b"tampered")
            with pytest.raises(PermissionError):
                os.replace(replacement, model)
            assert model.read_bytes() == b"adapter-model"
        finally:
            for handle in held:
                handle.close()
        with pytest.raises(runner.DurableRunnerError, match="supplied together"):
            runner._init_adapter_arguments(trainer_args[:-2])
        manifest["initial_adapter"]["model_sha256"] = "0" * 64
        manifest_path.write_bytes(runner.canonical_bytes(manifest))
        with pytest.raises(runner.DurableRunnerError, match="pin mismatch"):
            runner.validate_input_manifest_content(
                manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest(), trainer_args,
                manifest["trainer_source_sha256"], manifest["dataset_sha256"],
                manifest["model_weight_sha256"], 5, manifest["checkpoint_helper_source_sha256"])


def test_builder_main_publishes_and_self_validates_adapter_init_manifest() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset = root / "dataset.jsonl"
        model_dir = root / "model"
        model_dir.mkdir()
        model_weight = model_dir / "model.safetensors"
        trainer = root / "trainer.py"
        manifest_path = root / "input-manifest.json"
        dataset.write_bytes(b"{}\n")
        model_weight.write_bytes(b"model")
        (model_dir / "config.json").write_bytes(b"{}\n")
        trainer.write_bytes(b"# trainer\n")
        (root / "behavior_training_checkpoint.py").write_bytes(b"# helper\n")
        model_sha256 = hashlib.sha256(model_weight.read_bytes()).hexdigest()

        adapter = root / "initial-adapter"
        adapter.mkdir()
        config = adapter / "adapter_config.json"
        model = adapter / "adapter_model.safetensors"
        config.write_bytes(b"{}\n")
        model.write_bytes(b"adapter-model")
        files = [{"path": path.name, "bytes": path.stat().st_size,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                 for path in (config, model)]
        artifact = {"schema_version": "airi.behavior-adapter-artifact.v1",
                    "run_id": "source-run", "pins": {"model_weight_sha256": model_sha256},
                    "files": files}
        artifact_path = adapter / "artifact-manifest.json"
        artifact_path.write_bytes(runner.canonical_bytes(artifact))

        command = [
            sys.executable, str(BUILDER), "--output", str(manifest_path),
            "--dataset", str(dataset), "--dataset-sha256",
            hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "--model-weight", str(model_weight), "--model-sha256", model_sha256,
            "--trainer", str(trainer), "--mode", "cuda-qlora",
            "--seed", "42", "--lora-r", "8", "--lora-alpha", "16",
            "--lora-dropout", "0.05", "--learning-rate", "2e-5",
            "--max-steps", "480", "--batch-size", "1",
            "--gradient-accumulation", "16", "--max-seq-len", "2048",
            "--checkpoint-every-optimizer-steps", "5",
            "--deterministic-validation",
            "--init-adapter-dir", str(adapter),
            "--init-adapter-model-sha256", files[1]["sha256"],
            "--init-adapter-config-sha256", files[0]["sha256"],
            "--init-adapter-artifact-manifest-sha256",
            hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        ]
        built = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        # Regression: the self-check omitted --model-sha256, so the builder
        # published a v3 manifest and then refused it with exit code 2.
        assert built.returncode == 0, built.stderr
        receipt = json.loads(built.stdout)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest_path.read_bytes() == runner.canonical_bytes(payload)
        assert receipt["sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        assert payload["schema_version"] == "airi.behavior-input-manifest.v3"
        assert payload["training_config"]["init_mode"] == "adapter-weights-only"
        assert payload["initial_adapter"]["run_id"] == artifact["run_id"]
        assert payload["initial_adapter"]["files"] == files
