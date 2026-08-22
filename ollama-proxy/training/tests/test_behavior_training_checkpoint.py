import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("behavior_training_checkpoint_test", HERE / "behavior_training_checkpoint.py")
assert SPEC and SPEC.loader
checkpoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checkpoint)
_publish_checkpoint = checkpoint.publish_checkpoint


def _event(run_id: str, generation: str) -> dict:
    return {"run_id": run_id, "generation": generation, "reason": "interval",
            "microsteps_completed": 1, "optimizer_steps": 1,
            "pending_microbatches": 0, "training_elapsed_ns": 1,
            "checkpoint_payload_progress": {"microsteps_completed": 1,
                                            "optimizer_steps": 1,
                                            "pending_microbatches": 0}}


def _test_publish_checkpoint(run_dir, run_id, generation, payload, pins, event=None):
    return _publish_checkpoint(run_dir, run_id, generation, payload, pins,
                               _event(run_id, generation) if event is None else event)


# Existing integrity scenarios focus on rotation/fault behavior; supply their
# deterministic producer event explicitly through this test-local fixture.
checkpoint.publish_checkpoint = _test_publish_checkpoint


def pause_receipts(run_id: str, generation: str, manifest_sha256: str):
    ack = {
        "schema_version": "airi.behavior-pause-ack.v1", "run_id": run_id,
        "request_id": "pause-control-001", "checkpoint_relative_path": generation,
        "checkpoint_manifest_sha256": manifest_sha256,
        "acknowledged_at_utc": "2026-08-22T00:00:00Z", "safe_to_power_off": True,
    }
    accepted = {
        "schema_version": "airi.behavior-resume-accepted.v1", "run_id": run_id,
        "request_id": "pause-control-001", "checkpoint_relative_path": generation,
        "checkpoint_manifest_sha256": manifest_sha256,
    }
    return ack, accepted


def test_checkpoint_events_commit_monotonic_active_elapsed_and_publish_duration() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        elapsed = (101, 303)
        events = []
        for sequence, active_ns in enumerate(elapsed, start=1):
            generation = f"checkpoint-{sequence:08d}"
            payload = json.dumps({"training_elapsed_ns": active_ns}).encode("utf-8")
            published = _publish_checkpoint(
                root, "timing-run", generation, payload, pins,
                {"run_id": "timing-run", "generation": generation, "reason": "interval",
                 "microsteps_completed": sequence, "optimizer_steps": sequence,
                 "pending_microbatches": 0, "training_elapsed_ns": active_ns,
                 "checkpoint_payload_progress": {"microsteps_completed": sequence,
                                                  "optimizer_steps": sequence,
                                                  "pending_microbatches": 0}})
            raw = (root / published["event"]["relative_path"]).read_bytes()
            event = json.loads(raw)
            state = json.loads((root / "checkpoints" / generation / "state.pt").read_bytes())
            assert event["training_elapsed_ns"] == state["training_elapsed_ns"] == active_ns
            assert event["checkpoint_payload_progress"]["microsteps_completed"] == sequence
            assert event["publish_elapsed_ns"] >= 0
            events.append(event)
        assert events[1]["training_elapsed_ns"] > events[0]["training_elapsed_ns"]
        assert events[1]["previous_event_sha256"] == hashlib.sha256(
            (root / "checkpoint-events" / "checkpoint-00000001.json").read_bytes()).hexdigest()


def test_publishes_verified_rotating_generations() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        one = checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        two = checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000002", b"two", pins)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000003", b"three", pins)
        index = json.loads((root / "checkpoints" / "checkpoint-index.json").read_text())
        assert index["schema_version"] == "airi.behavior-checkpoint-index.v2"
        assert index["latest"]["relative_path"] == "checkpoint-00000003"
        assert index["previous"]["manifest_sha256"] == two["manifest_sha256"]
        assert not (root / "checkpoints" / "checkpoint-00000001").exists()
        assert (root / "archive" / "checkpoint-00000001").is_dir()
        assert checkpoint.load_latest_or_previous(root, pins)["payload"] == b"three"


def test_invalid_live_control_fails_before_generation_or_index_side_effect() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        first = checkpoint.publish_checkpoint(
            root, "run-1", "checkpoint-00000001", b"one", pins)
        control = root / "control"
        control.mkdir()
        ack, _accepted = pause_receipts(
            "run-1", "checkpoint-00000001", first["manifest_sha256"])
        ack["checkpoint_manifest_sha256"] = "0" * 64
        checkpoint.atomic_json(control / "pause.ack.json", ack)
        index = root / "checkpoints" / "checkpoint-index.json"
        before = index.read_bytes()
        try:
            checkpoint.publish_checkpoint(
                root, "run-1", "checkpoint-00000002", b"two", pins)
        except checkpoint.CheckpointIntegrityError as error:
            assert "control checkpoint hash mismatch" in str(error)
        else:
            raise AssertionError("invalid live control was accepted")
        assert index.read_bytes() == before
        assert not (root / "checkpoints" / "checkpoint-00000002").exists()
        assert not list((root / "checkpoints").glob(".checkpoint-00000002.*.tmp"))


def test_control_archive_during_preflight_commits_consistently() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        first = checkpoint.publish_checkpoint(
            root, "run-1", "checkpoint-00000001", b"one", pins)
        control = root / "control"
        history = control / "history"
        history.mkdir(parents=True)
        ack, accepted = pause_receipts(
            "run-1", "checkpoint-00000001", first["manifest_sha256"])
        checkpoint.atomic_json(control / "pause.ack.json", ack)
        checkpoint.atomic_json(control / "resume.accepted.json", accepted)
        original = checkpoint._read_live_control_snapshot

        def archive_after_snapshot(path):
            receipt = original(path)
            if receipt is not None and path.is_file():
                path.replace(history / path.name)
            return receipt

        checkpoint._read_live_control_snapshot = archive_after_snapshot
        try:
            second = checkpoint.publish_checkpoint(
                root, "run-1", "checkpoint-00000002", b"two", pins)
        finally:
            checkpoint._read_live_control_snapshot = original
        index = json.loads((root / "checkpoints" / "checkpoint-index.json").read_text())
        assert index["latest"]["manifest_sha256"] == second["manifest_sha256"]
        assert (root / "checkpoints" / "checkpoint-00000001").is_dir()
        assert (history / "pause.ack.json").is_file()
        assert (history / "resume.accepted.json").is_file()


def test_dangling_control_link_is_rejected_before_filesystem_side_effect() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dangling = root / "control" / "pause.ack.json"
        real_lexists = checkpoint.os.path.lexists

        def fake_lexists(path):
            return True if Path(path) == dangling else real_lexists(path)

        with patch.object(checkpoint.os.path, "lexists", side_effect=fake_lexists), \
                patch.object(Path, "is_symlink", return_value=True):
            try:
                checkpoint.publish_checkpoint(
                    root, "run-1", "checkpoint-00000001", b"one", {"input": "exact"})
            except checkpoint.CheckpointIntegrityError as error:
                assert "cannot be a link" in str(error)
            else:
                raise AssertionError("dangling live control link was ignored")
        assert not (root / "checkpoints").exists()


def test_corrupt_latest_is_quarantined_and_previous_used() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000002", b"two", pins)
        (root / "checkpoints" / "checkpoint-00000002" / "state.pt").write_bytes(b"broken")
        loaded = checkpoint.load_latest_or_previous(root, pins)
        assert loaded["position"] == "previous"
        assert loaded["payload"] == b"one"
        assert list((root / "quarantine").iterdir())


def test_torn_current_index_is_quarantined_and_verified_previous_index_recovers() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000002", b"two", pins)
        index = root / "checkpoints" / "checkpoint-index.json"
        previous = root / "checkpoints" / "checkpoint-index.prev.json"
        assert previous.is_file()
        index.write_bytes(b'{"schema_version":')
        loaded = checkpoint.load_latest_or_previous(root, pins, "run-1")
        assert loaded["position"] == "latest"
        assert loaded["payload"] == b"one"
        quarantined = list((root / "quarantine").glob("checkpoint-index.*.corrupt.json"))
        assert quarantined and quarantined[0].read_bytes() == b'{"schema_version":'


def test_publish_quarantines_corrupt_old_latest_and_retains_verified_previous() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000002", b"two", pins)
        (root / "checkpoints" / "checkpoint-00000002" / "state.pt").write_bytes(b"bad")
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000003", b"three", pins)
        index = json.loads((root / "checkpoints" / "checkpoint-index.json").read_text())
        assert index["latest"]["relative_path"] == "checkpoint-00000003"
        assert index["previous"]["relative_path"] == "checkpoint-00000001"
        assert not (root / "checkpoints" / "checkpoint-00000002").exists()
        assert list((root / "quarantine").glob("checkpoint-00000002.*.corrupt"))


def test_invalid_latest_manifest_json_is_quarantined_and_previous_used() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000002", b"two", pins)
        (root / "checkpoints" / "checkpoint-00000002" / "manifest.json").write_bytes(b"{")
        loaded = checkpoint.load_latest_or_previous(root, pins, "run-1")
        assert loaded["payload"] == b"one"
        assert list((root / "quarantine").glob("checkpoint-00000002.*.corrupt"))


def test_power_cut_after_generation_publish_quarantines_orphan_and_replays_name() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pins = {"input": "exact"}
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", pins)
        original_atomic_json = checkpoint.atomic_json

        def fail_index_publication(path, value, *, keep_previous=False):
            if path.name == "checkpoint-index.json":
                raise RuntimeError("simulated power cut before index publication")
            return original_atomic_json(path, value, keep_previous=keep_previous)

        checkpoint.atomic_json = fail_index_publication
        try:
            try:
                checkpoint.publish_checkpoint(
                    root, "run-1", "checkpoint-00000002", b"orphan", pins)
            except RuntimeError as error:
                assert "simulated power cut" in str(error)
            else:
                raise AssertionError("index publication fault did not interrupt checkpoint")
        finally:
            checkpoint.atomic_json = original_atomic_json

        assert (root / "checkpoints" / "checkpoint-00000002").is_dir()
        checkpoint.publish_checkpoint(
            root, "run-1", "checkpoint-00000002", b"replayed", pins)
        loaded = checkpoint.load_latest_or_previous(root, pins, "run-1")
        assert loaded["payload"] == b"replayed"
        assert list((root / "quarantine").glob("checkpoint-00000002.*.corrupt"))


def test_pin_mismatch_and_orphan_tmp_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        checkpoint.publish_checkpoint(root, "run-1", "checkpoint-00000001", b"one", {"pin": "a"})
        (root / "checkpoints" / ".checkpoint-999.tmp").mkdir()
        try:
            checkpoint.load_latest_or_previous(root, {"pin": "b"})
        except checkpoint.CheckpointError as error:
            assert "pins mismatch" in str(error)
        else:
            raise AssertionError("pin mismatch resumed")
        assert (root / "checkpoints" / ".checkpoint-999.tmp").exists()
        assert (root / "checkpoints" / "checkpoint-00000001").is_dir()
        assert not (root / "quarantine").exists()


def test_final_adapter_directory_is_inventoried_and_write_through_published() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        stage = root / "adapter.tmp"
        final = root / "adapter"
        stage.mkdir()
        (stage / "adapter_config.json").write_bytes(b"{}\n")
        (stage / "adapter_model.safetensors").write_bytes(b"weights")
        published = checkpoint.publish_artifact_directory(
            stage, final, "run-1", {"input": "exact"})
        assert not stage.exists()
        assert final.is_dir()
        assert len(published["manifest_sha256"]) == 64
        verified = checkpoint.verify_artifact_directory(
            final, {"input": "exact"}, "run-1")
        assert verified["manifest_sha256"] == published["manifest_sha256"]
        (final / "adapter_model.safetensors").write_bytes(b"corrupt")
        try:
            checkpoint.verify_artifact_directory(final)
        except checkpoint.CheckpointIntegrityError as error:
            assert "integrity" in str(error)
        else:
            raise AssertionError("corrupt final adapter passed verification")
