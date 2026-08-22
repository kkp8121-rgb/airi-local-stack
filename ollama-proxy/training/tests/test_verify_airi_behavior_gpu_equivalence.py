import importlib.util
import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "verify_airi_behavior_gpu_equivalence_test",
    HERE / "verify_airi_behavior_gpu_equivalence.py")
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class ArtifactVerifier:
    def verify_artifact_directory(self, directory, pins, run_id):
        return {"manifest_sha256": "a" * 64}

    def atomic_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(verifier._canonical(value))


def _event(run_id: str, generation: str, reason: str = "interval"):
    return {"run_id": run_id, "generation": generation, "reason": reason,
            "checkpoint_manifest_sha256": "b" * 64,
            "checkpoint_payload_sha256": "c" * 64,
            "microsteps_completed": 16 if reason == "safe-pause" else 320,
            "optimizer_steps": 1 if reason == "safe-pause" else 20,
            "pending_microbatches": 0}


def _pins():
    return {
        "dataset_sha256": "1" * 64,
        "model_weight_sha256": "2" * 64,
        "trainer_source_sha256": "3" * 64,
        "config": {"mode": "cuda-qlora", "seed": 42, "max_steps": 320,
                   "batch_size": 1, "gradient_accumulation": 16,
                   "checkpoint_every_optimizer_steps": 5,
                   "deterministic_validation": True},
        "determinism": {"validation_enabled": True, "algorithms_enabled": True,
                        "cudnn_deterministic": True, "cudnn_benchmark": False,
                        "cudnn_allow_tf32": False,
                        "cuda_matmul_allow_tf32": False,
                        "cublas_workspace_config": ":4096:8"},
        "cuda_identity": {"torch_cuda_runtime": "12.1", "device_name": "test-gpu",
                          "device_capability": [8, 6],
                          "total_memory_bytes": 8_000_000_000},
        "quantization": {"load_in_4bit": True, "quant_type": "nf4",
                         "double_quant": True, "compute_dtype": "bfloat16"},
    }


def _state(run_id: str):
    return {"run_id": run_id,
            "inputs": {"dataset_sha256": "1" * 64,
                       "model_weight_sha256": "2" * 64,
                       "trainer_source_sha256": "3" * 64,
                       "input_manifest_sha256": "4" * 64},
            "progress": {"microsteps_completed": 320, "optimizer_steps": 20},
            "status": "complete"}


def _expected_bindings(**overrides):
    bindings = {
        "expected_input_manifest_sha256": "4" * 64,
        "expected_training_config_sha256": verifier._sha256_bytes(
            verifier._canonical(_pins()["config"])),
        "expected_seed": 42,
        "expected_batch_size": 1,
        "expected_gradient_accumulation": 16,
        "expected_safe_pause_microsteps": 16,
        "expected_safe_pause_optimizer_step": 1,
    }
    bindings.update(overrides)
    return bindings


def _write_pause_history(run: Path, run_id: str = "resume",
                         request_id: str = "pause-001") -> None:
    history = run / "control" / "history"
    history.mkdir(parents=True, exist_ok=True)
    request = {"schema_version": "airi.behavior-pause-request.v1",
               "run_id": run_id, "request_id": request_id}
    ack = {"schema_version": "airi.behavior-pause-ack.v1",
           "run_id": run_id, "request_id": request_id,
           "checkpoint_manifest_sha256": "b" * 64,
           "checkpoint_relative_path": "checkpoint-00000001",
           "acknowledged_at_utc": "2026-08-22T00:00:00Z",
           "safe_to_power_off": True}
    accepted = {"schema_version": "airi.behavior-resume-accepted.v1",
                "run_id": run_id, "request_id": request_id,
                "checkpoint_manifest_sha256": "b" * 64,
                "checkpoint_relative_path": "checkpoint-00000001"}
    (history / f"{request_id}.request.json").write_bytes(verifier._canonical(request))
    (history / f"{request_id}.ack.json").write_bytes(verifier._canonical(ack))
    (history / f"{request_id}.resume-accepted.json").write_bytes(
        verifier._canonical(accepted))


def test_pass_receipt_is_canonical_atomic_and_never_authorizes_adoption() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline, resumed = root / "baseline", root / "resumed"
        for directory in (baseline, resumed):
            directory.mkdir()
            (directory / "run-state.json").write_bytes(b"{}\n")
            adapter = directory / "adapter"; adapter.mkdir()
            (adapter / "adapter_model.safetensors").write_bytes(b"not-model-bytes-in-receipt")
        (baseline / "control").mkdir()
        receipt = root / "out" / "receipt.json"
        latest = {"manifest": {"pins": _pins(), "generation": "checkpoint-00000001",
                               "payload": {"sha256": "c" * 64}},
                  "manifest_sha256": "b" * 64}
        with patch.object(verifier, "_completed_run", side_effect=[_state("base"), _state("resume")]), \
                patch.object(verifier, "_latest_verified_generation", side_effect=[latest, latest]), \
                patch.object(verifier, "_events", side_effect=[([_event("base", "checkpoint-00000001")], [1, 2, 3, 4]), ([_event("resume", "checkpoint-00000001", "safe-pause")], [])]), \
                patch.object(verifier, "_safe_pause_history", return_value=[{"path": "control/history/x.request.json", "sha256": "c" * 64}]), \
                patch.object(verifier, "_load_module", return_value=ArtifactVerifier()), \
                patch.object(verifier, "_report_fields", return_value={"mode": "cuda-qlora", "steps": 2}), \
                patch.object(verifier, "_tensor_report", return_value={"mode": "exact", "max_abs_diff": 0.0, "max_rel_diff": 0.0, "tensor_names": [], "tensor_count": 0}):
            result = verifier.verify_equivalence(
                baseline, resumed, receipt,
                baseline_adapter_dir=baseline / "adapter", resumed_adapter_dir=resumed / "adapter",
                expected_microsteps=320, expected_optimizer_steps=20,
                expected_checkpoint_every_optimizer_steps=5,
                **_expected_bindings(),
                tensor_loader=lambda _path: {}, state_loader=lambda _dir, _events: {"run_id": "different", "checkpoint_generation": "different", "same": [1]})
        assert result["pass"] is True
        assert result["adoption_authorized"] is False
        raw = receipt.read_bytes()
        assert raw == verifier._canonical(json.loads(raw))
        assert b"not-model-bytes" not in raw
        assert result["baseline"]["latest_checkpoint_payload_sha256"] == "c" * 64
        assert result["safe_pause_resume"]["latest_checkpoint_payload_sha256"] == "c" * 64
        assert result["comparator"]["schema_version"] == verifier.COMPARATOR_SCHEMA
        assert result["comparator"]["exact"] is True
        assert result["expected_bindings"] == {
            key.removeprefix("expected_"): value
            for key, value in _expected_bindings().items()
        }
        assert result["safe_pause_resume"]["safe_pause_event"]["generation"] == "checkpoint-00000001"


def test_failure_never_publishes_a_pass_receipt() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline, resumed = root / "baseline", root / "resumed"
        baseline.mkdir(); resumed.mkdir()
        receipt = root / "receipt.json"
        latest = {"manifest": {"pins": _pins(), "generation": "checkpoint-00000001",
                               "payload": {"sha256": "c" * 64}},
                  "manifest_sha256": "b" * 64}
        with patch.object(verifier, "_completed_run", side_effect=[_state("base"), _state("resume")]), \
                patch.object(verifier, "_latest_verified_generation", side_effect=[latest, latest]), \
                patch.object(verifier, "_events", side_effect=[([_event("base", "checkpoint-00000001")], [601]), ([_event("resume", "checkpoint-00000001", "safe-pause")], [])]), \
                patch.object(verifier, "_safe_pause_history", return_value=[]):
            try:
                verifier.verify_equivalence(
                    baseline, resumed, receipt,
                    expected_microsteps=320, expected_optimizer_steps=20,
                    expected_checkpoint_every_optimizer_steps=5,
                    **_expected_bindings())
            except verifier.EquivalenceError as error:
                assert "interval" in str(error)
            else:
                raise AssertionError("excessive interval unexpectedly passed")
        assert not receipt.exists()


def test_normalization_only_ignores_identity_fields() -> None:
    assert verifier._normalise_state({"run_id": "a", "x": [{"checkpoint_generation": "g", "v": 1}]}) == {"x": [{"v": 1}]}


def test_nested_checkpoint_tensor_comparison_is_exact() -> None:
    torch = pytest.importorskip("torch")
    left = {"run_id": "a", "checkpoint_generation": 4,
            "optimizer": {"state": [torch.tensor([1.0, 2.0])]}, "losses": [1.0]}
    right = {"run_id": "b", "checkpoint_generation": 5,
             "optimizer": {"state": [torch.tensor([1.0, 2.0])]}, "losses": [1.0]}
    verifier._compare_state(left, right)
    right["optimizer"]["state"][0][1] = 3.0
    try:
        verifier._compare_state(left, right)
    except verifier.EquivalenceError as error:
        assert "tensor differs" in str(error)
    else:
        raise AssertionError("changed optimizer tensor unexpectedly passed")


def test_event_intervals_use_durable_timestamps_and_interval_reason() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        events = run / "checkpoint-events"
        events.mkdir()
        pins = _pins()
        run_state = {"created_at_utc": "2026-08-22T00:00:00Z"}
        (run / "run-state.json").write_bytes(verifier._canonical(run_state))
        for number, second in enumerate((100, 200, 300, 400), start=1):
            generation = f"checkpoint-{number:08d}"
            index = {"schema_version": "airi.behavior-checkpoint-index.v1",
                     "latest": {"relative_path": generation,
                                "manifest_sha256": "a" * 64}, "previous": None}
            event = {
                "schema_version": verifier.EVENT_SCHEMA, "run_id": "base",
                "generation": generation, "reason": "interval",
                "microsteps_completed": number * 80, "optimizer_steps": number * 5,
                "pending_microbatches": 0,
                "publish_started_at_utc": f"2026-08-22T00:{(second - 1) // 60:02d}:{(second - 1) % 60:02d}Z",
                "checkpoint_durable_at_utc": f"2026-08-22T00:{second // 60:02d}:{second % 60:02d}Z",
                "publish_elapsed_ns": 1_000_000_000,
                "checkpoint_manifest_sha256": "a" * 64,
                "checkpoint_payload_sha256": "b" * 64,
                "checkpoint_index_sha256": verifier._sha256_bytes(verifier._canonical(index)),
                "checkpoint_index": index,
                "pins_sha256": verifier._sha256_bytes(verifier._canonical(pins)),
            }
            (events / f"{generation}.json").write_bytes(verifier._canonical(event))
        found, intervals = verifier._events(run, "base", pins)
        assert len(found) == 4
        assert intervals == [100.0, 100.0, 100.0, 100.0]


def test_event_inventory_rejects_a_generation_gap() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        events = run / "checkpoint-events"
        events.mkdir()
        pins = _pins()
        for number in (1, 3):
            generation = f"checkpoint-{number:08d}"
            index = {"schema_version": "airi.behavior-checkpoint-index.v1",
                     "latest": {"relative_path": generation,
                                "manifest_sha256": "a" * 64}, "previous": None}
            event = {
                "schema_version": verifier.EVENT_SCHEMA, "run_id": "base",
                "generation": generation, "reason": "interval",
                "microsteps_completed": number, "optimizer_steps": number,
                "pending_microbatches": 0,
                "publish_started_at_utc": "2026-08-22T00:00:00Z",
                "checkpoint_durable_at_utc": "2026-08-22T00:00:01Z",
                "publish_elapsed_ns": 1_000_000_000,
                "checkpoint_manifest_sha256": "a" * 64,
                "checkpoint_payload_sha256": "b" * 64,
                "checkpoint_index_sha256": verifier._sha256_bytes(
                    verifier._canonical(index)), "checkpoint_index": index,
                "pins_sha256": verifier._sha256_bytes(verifier._canonical(pins)),
            }
            (events / f"{generation}.json").write_bytes(verifier._canonical(event))
        with pytest.raises(verifier.EquivalenceError, match="generation sequence"):
            verifier._events(run, "base", pins)


def test_event_inventory_rejects_wall_monotonic_clock_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        events = run / "checkpoint-events"
        events.mkdir()
        pins = _pins()
        generation = "checkpoint-00000001"
        index = {"schema_version": "airi.behavior-checkpoint-index.v1",
                 "latest": {"relative_path": generation,
                            "manifest_sha256": "a" * 64}, "previous": None}
        event = {
            "schema_version": verifier.EVENT_SCHEMA, "run_id": "base",
            "generation": generation, "reason": "interval",
            "microsteps_completed": 1, "optimizer_steps": 1,
            "pending_microbatches": 0,
            "publish_started_at_utc": "2026-08-22T00:00:00Z",
            "checkpoint_durable_at_utc": "2026-08-22T00:00:20Z",
            "publish_elapsed_ns": 1_000_000_000,
            "checkpoint_manifest_sha256": "a" * 64,
            "checkpoint_payload_sha256": "b" * 64,
            "checkpoint_index_sha256": verifier._sha256_bytes(
                verifier._canonical(index)), "checkpoint_index": index,
            "pins_sha256": verifier._sha256_bytes(verifier._canonical(pins)),
        }
        (events / f"{generation}.json").write_bytes(verifier._canonical(event))
        with pytest.raises(verifier.EquivalenceError, match="wall/monotonic"):
            verifier._events(run, "base", pins)


def test_latest_checkpoint_without_matching_event_is_refused() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline, resumed = root / "baseline", root / "resumed"
        baseline.mkdir(); resumed.mkdir()
        receipt = root / "receipt.json"
        latest = {"manifest": {"pins": _pins(), "generation": "checkpoint-00000002",
                               "payload": {"sha256": "c" * 64}},
                  "manifest_sha256": "b" * 64}
        with patch.object(verifier, "_completed_run",
                          side_effect=[_state("base"), _state("resume")]), \
                patch.object(verifier, "_latest_verified_generation",
                             side_effect=[latest, latest]), \
                patch.object(verifier, "_events", side_effect=[
                    ([_event("base", "checkpoint-00000001")], [1, 2, 3, 4]),
                    ([_event("resume", "checkpoint-00000001", "safe-pause")], [])]):
            with pytest.raises(verifier.EquivalenceError, match="lacks its exact"):
                verifier.verify_equivalence(
                    baseline, resumed, receipt,
                    expected_microsteps=320, expected_optimizer_steps=20,
                    expected_checkpoint_every_optimizer_steps=5,
                    **_expected_bindings())
        assert not receipt.exists()


def test_cli_has_no_tolerance_or_interval_gate_override() -> None:
    with pytest.raises(SystemExit) as refusal:
        verifier.main([
            "--baseline-run-dir", "baseline",
            "--safe-pause-resume-run-dir", "resumed",
            "--receipt", "receipt.json",
            "--expected-microsteps", "320",
            "--expected-optimizer-steps", "20",
            "--expected-checkpoint-every-optimizer-steps", "5",
            "--expected-input-manifest-sha256", "4" * 64,
            "--expected-training-config-sha256", verifier._sha256_bytes(
                verifier._canonical(_pins()["config"])),
            "--expected-seed", "42",
            "--expected-batch-size", "1",
            "--expected-gradient-accumulation", "16",
            "--expected-safe-pause-microsteps", "16",
            "--expected-safe-pause-optimizer-step", "1",
            "--atol", "inf",
        ])
    assert refusal.value.code == 2


@pytest.mark.parametrize(
    "live_name",
    ["pause.request.json", "pause.ack.json", "resume.accepted.json"],
)
def test_safe_pause_history_rejects_any_live_control(live_name: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        _write_pause_history(run)
        live = run / "control" / live_name
        live.write_bytes(b"{}\n")
        with pytest.raises(verifier.EquivalenceError, match="ambiguous live"):
            verifier._safe_pause_history(
                run, "resume",
                [_event("resume", "checkpoint-00000001", "safe-pause")])


def test_safe_pause_history_rejects_orphan_or_extra_history_entry() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        _write_pause_history(run)
        history = run / "control" / "history"
        (history / "orphan.ack.json").write_bytes(b"{}\n")
        with pytest.raises(verifier.EquivalenceError, match="orphan or unexpected"):
            verifier._safe_pause_history(
                run, "resume",
                [_event("resume", "checkpoint-00000001", "safe-pause")])


def test_atomic_new_receipt_never_overwrites_or_deletes_concurrent_file() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "receipt.json"
        receipt.write_bytes(b"concurrent-owner\n")
        with pytest.raises(verifier.EquivalenceError):
            verifier._atomic_new_receipt(receipt, {"pass": True})
        assert receipt.read_bytes() == b"concurrent-owner\n"


def test_expected_manifest_config_and_training_shape_mismatches_refuse() -> None:
    cases = [
        ("manifest", _expected_bindings(expected_input_manifest_sha256="0" * 64), _pins()),
        ("config", _expected_bindings(expected_training_config_sha256="0" * 64), _pins()),
        ("seed", _expected_bindings(), {**_pins(), "config": {**_pins()["config"], "seed": 43}}),
        ("batch", _expected_bindings(), {**_pins(), "config": {**_pins()["config"], "batch_size": 2}}),
        ("grad", _expected_bindings(), {**_pins(), "config": {**_pins()["config"], "gradient_accumulation": 8}}),
    ]
    for label, bindings, pins in cases:
        if label in {"seed", "batch", "grad"}:
            bindings = _expected_bindings(
                expected_training_config_sha256=verifier._sha256_bytes(
                    verifier._canonical(pins["config"])))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline, resumed = root / "baseline", root / "resumed"
            baseline.mkdir(); resumed.mkdir()
            latest = {"manifest": {"pins": pins, "generation": "checkpoint-00000001",
                                   "payload": {"sha256": "c" * 64}},
                      "manifest_sha256": "b" * 64}
            with ExitStack() as stack:
                stack.enter_context(patch.object(verifier, "_completed_run",
                                                 side_effect=[_state("base"), _state("resume")]))
                stack.enter_context(patch.object(verifier, "_latest_verified_generation",
                                                 side_effect=[latest, latest]))
                with pytest.raises(verifier.EquivalenceError):
                    verifier.verify_equivalence(
                        baseline, resumed, root / "receipt.json",
                        expected_microsteps=320, expected_optimizer_steps=20,
                        expected_checkpoint_every_optimizer_steps=5, **bindings)


@pytest.mark.parametrize(
    "events,bindings",
    [
        ((([_event("base", "checkpoint-00000001")], [1, 2, 3, 4]),
          ([_event("resume", "checkpoint-00000001", "safe-pause")], [])),
         _expected_bindings(expected_safe_pause_microsteps=32,
                            expected_safe_pause_optimizer_step=2)),
        ((([_event("base", "checkpoint-00000001")], [1, 2, 3, 4]),
          ([_event("resume", "checkpoint-00000001", "safe-pause"),
            _event("resume", "checkpoint-00000002", "safe-pause")], [])),
         _expected_bindings()),
    ],
)
def test_safe_pause_location_and_extra_event_refuse(events, bindings) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline, resumed = root / "baseline", root / "resumed"
        baseline.mkdir(); resumed.mkdir()
        latest = {"manifest": {"pins": _pins(), "generation": "checkpoint-00000001",
                               "payload": {"sha256": "c" * 64}},
                  "manifest_sha256": "b" * 64}
        with patch.object(verifier, "_completed_run", side_effect=[_state("base"), _state("resume")]), \
                patch.object(verifier, "_latest_verified_generation", side_effect=[latest, latest]), \
                patch.object(verifier, "_events", side_effect=events), \
                patch.object(verifier, "_safe_pause_history", return_value=[]):
            with pytest.raises(verifier.EquivalenceError):
                verifier.verify_equivalence(
                    baseline, resumed, root / "receipt.json",
                    expected_microsteps=320, expected_optimizer_steps=20,
                    expected_checkpoint_every_optimizer_steps=5, **bindings)


def test_safe_pause_history_rejects_extra_complete_triple() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        _write_pause_history(run, request_id="pause-001")
        _write_pause_history(run, request_id="pause-002")
        with pytest.raises(verifier.EquivalenceError, match="exactly one"):
            verifier._safe_pause_history(
                run, "resume", [_event("resume", "checkpoint-00000001", "safe-pause")])


def test_baseline_control_must_be_absent_or_an_empty_regular_directory() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        control = run / "control"
        control.mkdir()
        verifier._require_no_safe_pause_evidence(run, [])
        (control / ".orphan").write_bytes(b"evidence\n")
        with pytest.raises(verifier.EquivalenceError, match="control evidence"):
            verifier._require_no_safe_pause_evidence(run, [])


def test_baseline_control_rejects_a_link_when_supported() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        target = run / "target"
        target.mkdir()
        control = run / "control"
        try:
            control.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("filesystem does not permit test symlinks")
        with pytest.raises(verifier.EquivalenceError, match="control evidence"):
            verifier._require_no_safe_pause_evidence(run, [])
