import hashlib
import importlib.util
import json
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


parser = argparse.ArgumentParser()
parser.add_argument("--run-dir", type=Path, required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--dataset-sha256", required=True)
parser.add_argument("--model-sha256", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--resume-from-checkpoint", type=Path)
args, _ = parser.parse_known_args()
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
    index = {
        "schema_version": "airi.behavior-checkpoint-index.v1",
        "latest": reference, "previous": None,
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
    values = [
        "--run-dir", str(root / "run"), "--run-id", "integration-run",
        "--python", sys.executable, "--trainer", str(trainer),
        "--working-directory", str(root), "--input-manifest-sha256", "c" * 64,
        "--checkpoint-every-optimizer-steps", "5", "--heartbeat-seconds", "0.05",
    ]
    if resume:
        values.append("--resume-interrupted")
    values.extend([
        "--", "--dataset", str(dataset), "--dataset-sha256", "a" * 64,
        "--model-dir", str(model_dir), "--model-sha256", "b" * 64,
        "--output", str(root / "adapter"), "--report", str(root / "report.json"),
    ])
    return values


def test_actual_checkpoint_manifest_latest_and_previous_are_compatible() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_for_runner_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
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


def test_torn_current_index_recovers_only_through_previous_index() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_torn_index_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"dataset_sha256": "a" * 64, "model_weight_sha256": "b" * 64,
                "trainer_source_sha256": "d" * 64}
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000002", b"two", pins)
        (root / "checkpoints" / "checkpoint-index.json").write_bytes(b"{")
        selected = runner.resolve_resume_checkpoint(
            root, "run-1", {**pins, "input_manifest_sha256": "c" * 64})
        assert selected["relative_path"] == "checkpoint-00000001"
        assert list((root / "quarantine").glob("checkpoint-index.*.json"))


def test_structurally_corrupt_current_index_uses_valid_previous_index() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_bad_index_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
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
        selected = runner.resolve_resume_checkpoint(
            root, "run-1", {**pins, "input_manifest_sha256": "c" * 64})
        assert selected["relative_path"] == "checkpoint-00000001"
        assert list((root / "quarantine").glob("checkpoint-index.*.json"))


def test_pin_mismatch_refuses_without_quarantining_valid_checkpoint() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_pin_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
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
        assert "pin mismatch" in resumed.stderr
        assert (control / "pause.request.json").is_file()
        assert ack_path.is_file()
        assert not (control / "history").exists()


def test_supervisor_failed_verified_final_artifacts_recover_complete_terminal() -> None:
    checkpoint_spec = importlib.util.spec_from_file_location(
        "behavior_checkpoint_final_recovery_test", HERE / "behavior_training_checkpoint.py")
    assert checkpoint_spec and checkpoint_spec.loader
    checkpoint = importlib.util.module_from_spec(checkpoint_spec)
    checkpoint_spec.loader.exec_module(checkpoint)
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
        state = runner._base_state(
            args, [sys.executable, str(trainer), *trainer_args], inputs,
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
        paused_revision = paused["revision"]

        changed = _arguments(root, trainer, resume=True)
        changed.extend(["--seed", "43"])
        mismatch = subprocess.run(
            [sys.executable, str(runner_script), *changed],
            cwd=root, capture_output=True, text=True, check=False)
        assert mismatch.returncode == 2
        assert "command differs" in mismatch.stderr
        assert (control / "pause.request.json").is_file()
        assert (control / "pause.ack.json").is_file()

        second = subprocess.run(
            [sys.executable, str(runner_script),
             *_arguments(root, trainer, resume=True)],
            cwd=root, capture_output=True, text=True, check=False)
        assert second.returncode == 0, second.stderr
        completed = json.loads((root / "run" / "run-state.json").read_text())
        assert completed["status"] == "complete"
        assert completed["terminal"]["exit_code"] == 0
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
