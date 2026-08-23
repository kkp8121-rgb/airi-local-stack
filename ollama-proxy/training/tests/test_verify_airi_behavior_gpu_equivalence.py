import importlib.util
import json
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
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
        "config": {"mode": "cuda-qlora", "seed": 42, "lora_r": 8,
                   "lora_alpha": 16, "lora_dropout": 0.05,
                   "learning_rate": 0.00002, "max_steps": 320,
                   "batch_size": 1, "gradient_accumulation": 16, "max_seq_len": 2048,
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


def _manifest_payload():
    config = _pins()["config"]
    return {
        "schema_version": "airi.behavior-input-manifest.v2",
        "dataset_sha256": "1" * 64,
        "model_weight_sha256": "2" * 64,
        "trainer_source_sha256": "3" * 64,
        "training_config": config,
        "training_config_sha256": verifier._sha256_bytes(verifier._canonical(config)),
        "checkpoint_helper_source_sha256": "4" * 64,
        "model_inventory": [{"path": "model.safetensors", "bytes": 1,
                             "sha256": "5" * 64}],
    }


_MANIFEST_TEMPORARY = tempfile.TemporaryDirectory()
TEST_MANIFEST_PATH = Path(_MANIFEST_TEMPORARY.name) / "input-manifest.json"
TEST_MANIFEST_PATH.write_bytes(verifier._canonical(_manifest_payload()))
TEST_MANIFEST_SHA256 = verifier._sha256_file(TEST_MANIFEST_PATH)


def _state(run_id: str):
    return {"run_id": run_id,
            "inputs": {"dataset_sha256": "1" * 64,
                       "model_weight_sha256": "2" * 64,
                       "trainer_source_sha256": "3" * 64,
                       "input_manifest_path": str(TEST_MANIFEST_PATH),
                       "input_manifest_sha256": TEST_MANIFEST_SHA256,
                       "input_manifest_training_config_sha256": verifier._sha256_bytes(
                           verifier._canonical(_pins()["config"])),
                       "checkpoint_helper_source_sha256": "4" * 64},
            "progress": {"microsteps_completed": 320, "optimizer_steps": 20},
            "checkpoint": {"relative_path": "checkpoint-00000001",
                           "manifest_sha256": "b" * 64},
            "status": "complete"}


def _expected_bindings(**overrides):
    bindings = {
        "expected_input_manifest_sha256": TEST_MANIFEST_SHA256,
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


def test_injected_loaders_cannot_publish_a_pass_receipt() -> None:
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
                patch.object(verifier, "_events", side_effect=[([_event("base", "checkpoint-00000001")], [3, 4, 5, 6]), ([_event("resume", "checkpoint-00000001", "safe-pause")], [1, 2, 3, 4, 5])]), \
                patch.object(verifier, "_safe_pause_history", return_value=[{"path": "control/history/x.request.json", "sha256": "c" * 64}]), \
                patch.object(verifier, "_verify_artifact_snapshot", return_value={"manifest_sha256": "a" * 64, "files": {"adapter_model.safetensors": b"x"}}), \
                patch.object(verifier, "_report_fields", return_value={"mode": "cuda-qlora", "steps": 2}), \
                patch.object(verifier, "_tensor_report", return_value={"mode": "exact", "max_abs_diff": 0.0, "max_rel_diff": 0.0, "tensor_names": [], "tensor_count": 0}):
            with pytest.raises(verifier.EquivalenceError, match="non-production injected"):
                verifier.verify_equivalence(
                    baseline, resumed, receipt,
                    baseline_adapter_dir=baseline / "adapter", resumed_adapter_dir=resumed / "adapter",
                    expected_microsteps=320, expected_optimizer_steps=20,
                    expected_checkpoint_every_optimizer_steps=5,
                    **_expected_bindings(),
                    tensor_loader=lambda _path: {}, state_loader=lambda _dir, _events: {"run_id": "different", "checkpoint_generation": "different", "same": [1]})
        assert not receipt.exists()


@pytest.mark.parametrize("name", [
    "run-state.json", "checkpoint-index.json", "checkpoint-00000001.json",
    "pause-001.ack.json",
])
def test_evidence_cut_keeps_json_evidence_hash_after_path_replacement(name: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        state_path = root / name
        original = b'{"evidence":"original"}\n'
        state_path.write_bytes(original)
        verifier._EVIDENCE_CUT = {}
        try:
            assert verifier._evidence_bytes(state_path, "run-state") == original
            state_path.write_bytes(b'{"evidence":"replacement"}\n')
            assert verifier._sha256_file(state_path) == verifier._sha256_bytes(original)
        finally:
            verifier._EVIDENCE_CUT = None


def test_latest_checkpoint_state_loads_cached_payload_after_path_replacement() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        checkpoints = root / "checkpoints"
        generation = "checkpoint-00000001"
        payload_path = checkpoints / generation / "state.pt"
        payload_path.parent.mkdir(parents=True)
        original = b"original-checkpoint"
        payload_path.write_bytes(original)
        (checkpoints / "checkpoint-index.json").write_bytes(verifier._canonical({
            "schema_version": "airi.behavior-checkpoint-index.v1",
            "latest": {"relative_path": generation, "manifest_sha256": "a" * 64},
            "previous": None,
        }))
        original_snapshot = verifier._evidence_bytes

        def replace_after_snapshot(path, label):
            value = original_snapshot(path, label)
            if label == "latest checkpoint state":
                payload_path.write_bytes(b"replacement-checkpoint")
            return value

        loaded: dict[str, bytes] = {}

        def load(stream, **_kwargs):
            loaded["bytes"] = stream.read()
            return {"loaded": loaded["bytes"]}

        verifier._EVIDENCE_CUT = {}
        try:
            with patch.object(verifier, "_evidence_bytes", side_effect=replace_after_snapshot), \
                    patch.dict(sys.modules, {"torch": SimpleNamespace(load=load)}):
                assert verifier._latest_checkpoint_state(root, []) == {"loaded": original}
        finally:
            verifier._EVIDENCE_CUT = None
        assert payload_path.read_bytes() == b"replacement-checkpoint"


def test_artifact_snapshot_keeps_manifest_and_file_bytes_after_replacement() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary) / "adapter"
        directory.mkdir()
        weights = directory / "adapter_model.safetensors"
        original = b"original-safetensors"
        weights.write_bytes(original)
        manifest = {
            "schema_version": "airi.behavior-adapter-artifact.v1", "run_id": "base",
            "pins": _pins(), "files": [{"path": "adapter_model.safetensors",
                                            "bytes": len(original),
                                            "sha256": verifier._sha256_bytes(original)}],
        }
        manifest_path = directory / "artifact-manifest.json"
        manifest_path.write_bytes(verifier._canonical(manifest))
        original_snapshot = verifier._evidence_bytes

        def replace_after_snapshot(path, label):
            value = original_snapshot(path, label)
            if label == "adapter artifact file":
                weights.write_bytes(b"replacement-safetensors")
            return value

        verifier._EVIDENCE_CUT = {}
        try:
            with patch.object(verifier, "_evidence_bytes", side_effect=replace_after_snapshot):
                verified = verifier._verify_artifact_snapshot(directory, _pins(), "base")
        finally:
            verifier._EVIDENCE_CUT = None
        assert verified["manifest_sha256"] == verifier._sha256_bytes(verifier._canonical(manifest))
        assert verified["files"]["adapter_model.safetensors"] == original
        assert weights.read_bytes() == b"replacement-safetensors"


def test_report_fields_keep_cached_report_after_path_replacement() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        report_path = Path(temporary) / "report.json"
        manifest_sha = "a" * 64
        report = {"mode": "cuda-qlora", "steps": 1, "optimizer_steps": 1,
                  "checkpoint_every_optimizer_steps": 5, "deterministic_validation": True,
                  "determinism": _pins()["determinism"],
                  "adapter_artifact_manifest_sha256": manifest_sha,
                  "dataset_sha256": _pins()["dataset_sha256"],
                  "model_weight_sha256": _pins()["model_weight_sha256"], "seed": 42,
                  "training_authorization": True, "adoption_authorized": False,
                  "t3_status": "pending"}
        report_path.write_bytes(verifier._canonical(report))
        state = {"outputs": {"report": {"path": str(report_path)}}}
        original_snapshot = verifier._evidence_bytes

        def replace_after_snapshot(path, label):
            value = original_snapshot(path, label)
            if label == "training report":
                report_path.write_bytes(b'{"replacement":true}\n')
            return value

        verifier._EVIDENCE_CUT = {}
        try:
            with patch.object(verifier, "_evidence_bytes", side_effect=replace_after_snapshot):
                assert verifier._report_fields(state, manifest_sha, _pins())["steps"] == 1
        finally:
            verifier._EVIDENCE_CUT = None
        assert report_path.read_bytes() == b'{"replacement":true}\n'


def test_v3_report_and_checkpoint_bind_exact_weights_only_initialization() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        report_path = Path(temporary) / "report.json"
        manifest_sha = "a" * 64
        initialization = {
            "init_mode": "adapter-weights-only", "directory_identity": "e2-adapter",
            "run_id": "e2-source", "model_sha256": "6" * 64,
            "config_sha256": "7" * 64, "artifact_manifest_sha256": "8" * 64,
            "inventory": [
                {"path": "adapter_config.json", "bytes": 1, "sha256": "7" * 64},
                {"path": "adapter_model.safetensors", "bytes": 1, "sha256": "6" * 64},
            ],
        }
        pins = {**_pins(), "config": {**_pins()["config"],
                                       "init_mode": "adapter-weights-only"},
                "initialization": initialization}
        report = {
            "mode": "cuda-qlora", "steps": 1, "optimizer_steps": 1,
            "checkpoint_every_optimizer_steps": 5, "deterministic_validation": True,
            "determinism": pins["determinism"], "initialization": initialization,
            "adapter_artifact_manifest_sha256": manifest_sha,
            "dataset_sha256": pins["dataset_sha256"],
            "model_weight_sha256": pins["model_weight_sha256"], "seed": 42,
            "training_authorization": True, "adoption_authorized": False,
            "t3_status": "pending",
        }
        report_path.write_bytes(verifier._canonical(report))
        state = {"outputs": {"report": {"path": str(report_path)}},
                 "inputs": {"init_mode": "adapter-weights-only",
                            "init_adapter_dir": str(Path(temporary) / "e2-adapter"),
                            "init_adapter_model_sha256": "6" * 64,
                            "init_adapter_config_sha256": "7" * 64,
                            "init_adapter_artifact_manifest_sha256": "8" * 64}}
        assert verifier._report_fields(state, manifest_sha, pins)["initialization"] == initialization
        verifier._bind_run_state_initialization(state, initialization)

        report.pop("initialization")
        report_path.write_bytes(verifier._canonical(report))
        with pytest.raises(verifier.EquivalenceError, match="semantic fields"):
            verifier._report_fields(state, manifest_sha, pins)
        state["inputs"]["init_adapter_model_sha256"] = "0" * 64
        with pytest.raises(verifier.EquivalenceError, match="pin differ"):
            verifier._bind_run_state_initialization(state, initialization)


def test_initialization_provenance_rejects_inventory_and_mode_faults() -> None:
    fresh = {**_pins(), "config": {**_pins()["config"], "init_mode": "fresh-lora"},
             "initialization": {"init_mode": "fresh-lora"}}
    assert verifier._initialization_provenance(fresh) == {"init_mode": "fresh-lora"}
    broken = {**fresh, "initialization": {"init_mode": "adapter-weights-only"}}
    with pytest.raises(verifier.EquivalenceError, match="fresh LoRA"):
        verifier._initialization_provenance(broken)

    invalid_adapter = {
        **_pins(), "config": {**_pins()["config"], "init_mode": "adapter-weights-only"},
        "initialization": {
            "init_mode": "adapter-weights-only", "directory_identity": "nested/path",
            "run_id": "e2", "model_sha256": "6" * 64, "config_sha256": "7" * 64,
            "artifact_manifest_sha256": "8" * 64,
            "inventory": [{"path": "adapter_model.safetensors", "bytes": 1,
                           "sha256": "6" * 64}],
        },
    }
    with pytest.raises(verifier.EquivalenceError, match="provenance is invalid"):
        verifier._initialization_provenance(invalid_adapter)


def test_completed_output_receipts_refuse_adapter_and_report_substitution() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        adapter = root / "adapter"; adapter.mkdir()
        manifest_path = adapter / "artifact-manifest.json"
        manifest_path.write_bytes(b"{}\n")
        weight = adapter / "adapter_model.safetensors"; weight.write_bytes(b"weights")
        report = root / "report.json"; report.write_bytes(b"{}\n")
        artifact = {"files": {"adapter_model.safetensors": b"weights"}}
        rows = [
            {"path": "adapter_model.safetensors", "size": 7,
             "sha256": verifier._sha256_bytes(b"weights")},
            {"path": "artifact-manifest.json", "size": 3,
             "sha256": verifier._sha256_bytes(b"{}\n")},
        ]
        state = {"outputs": {
            "adapter": {"path": str(adapter), "kind": "directory", "files": rows,
                        "manifest_sha256": "0" * 64},
            "report": {"path": str(report), "kind": "file", "size": 2,
                       "sha256": "0" * 64},
        }}
        with pytest.raises(verifier.EquivalenceError, match="adapter output receipt"):
            verifier._bind_completed_output_receipts(state, adapter, artifact)
        state["outputs"]["adapter"]["manifest_sha256"] = verifier._sha256_bytes(
            verifier._canonical(rows))
        with pytest.raises(verifier.EquivalenceError, match="report output receipt"):
            verifier._bind_completed_output_receipts(state, adapter, artifact)


def test_completed_output_receipts_follow_platform_path_order() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        adapter = Path(temporary) / "adapter"; adapter.mkdir()
        payloads = {
            "adapter_config.json": b"config",
            "adapter_model.safetensors": b"weights",
            "artifact-manifest.json": b"{}\n",
            "README.md": b"readme",
        }
        for name, payload in payloads.items():
            (adapter / name).write_bytes(payload)
        rows = [
            {"path": path.relative_to(adapter).as_posix(), "size": path.stat().st_size,
             "sha256": verifier._sha256_bytes(path.read_bytes())}
            for path in sorted(adapter.rglob("*")) if path.is_file()
        ]
        state = {"outputs": {"adapter": {
            "path": str(adapter), "kind": "directory", "files": rows,
            "manifest_sha256": verifier._sha256_bytes(verifier._canonical(rows)),
        }}}
        artifact = {"files": {
            name: payload for name, payload in payloads.items()
            if name != "artifact-manifest.json"
        }}

        verifier._bind_completed_output_receipts(state, adapter, artifact)


def test_artifact_inventory_rejects_windows_reparse_attribute() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary) / "adapter"; directory.mkdir()
        item = directory / "adapter_model.safetensors"; item.write_bytes(b"x")
        manifest = {
            "schema_version": "airi.behavior-adapter-artifact.v1", "run_id": "base",
            "pins": _pins(), "files": [{"path": item.name, "bytes": 1,
                                           "sha256": verifier._sha256_bytes(b"x")}],
        }
        (directory / "artifact-manifest.json").write_bytes(verifier._canonical(manifest))
        original_lstat = verifier.os.lstat

        def reparse(path):
            value = original_lstat(path)
            if Path(path) == item:
                return SimpleNamespace(st_file_attributes=0x400)
            return value

        with patch.object(verifier.os, "lstat", side_effect=reparse):
            with pytest.raises(verifier.EquivalenceError, match="reparse point|linked entry"):
                verifier._verify_artifact_snapshot(directory, _pins(), "base")


@pytest.mark.parametrize("receipt_name", [
    "baseline/evidence/receipt.json", "resumed/logs/receipt.json",
    "baseline/adapter/receipt.json", "resumed/adapter/checkpoints/receipt.json",
])
def test_receipt_refuses_every_run_and_adapter_evidence_tree_before_publication(receipt_name) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline, resumed = root / "baseline", root / "resumed"
        for directory in (baseline, resumed):
            directory.mkdir(); (directory / "run-state.json").write_bytes(b"{}\n")
            adapter = directory / "adapter"; adapter.mkdir()
            (adapter / "adapter_model.safetensors").write_bytes(b"x")
        (baseline / "control").mkdir()
        receipt = root / receipt_name
        latest = {"manifest": {"pins": _pins(), "generation": "checkpoint-00000001",
                               "payload": {"sha256": "c" * 64}}, "manifest_sha256": "b" * 64}
        with patch.object(verifier, "_completed_run", side_effect=[_state("base"), _state("resume")]), \
                patch.object(verifier, "_latest_verified_generation", side_effect=[latest, latest]), \
                patch.object(verifier, "_events", side_effect=[([_event("base", "checkpoint-00000001")], [1, 2, 3, 4]), ([_event("resume", "checkpoint-00000001", "safe-pause")], [1, 2, 3, 4])]), \
                patch.object(verifier, "_safe_pause_history", return_value=[]), \
                patch.object(verifier, "_verify_artifact_snapshot", return_value={"manifest_sha256": "a" * 64, "files": {"adapter_model.safetensors": b"x"}}), \
                patch.object(verifier, "_report_fields", return_value={"mode": "cuda-qlora", "steps": 2}), \
                patch.object(verifier, "_tensor_report", return_value={"mode": "exact", "max_abs_diff": 0.0, "max_rel_diff": 0.0, "tensor_names": [], "tensor_count": 0}):
            with pytest.raises(verifier.EquivalenceError, match="non-production injected"):
                verifier.verify_equivalence(
                    baseline, resumed, receipt, baseline_adapter_dir=baseline / "adapter",
                    resumed_adapter_dir=resumed / "adapter", expected_microsteps=320,
                    expected_optimizer_steps=20, expected_checkpoint_every_optimizer_steps=5,
                    **_expected_bindings(), tensor_loader=lambda _path: {},
                    state_loader=lambda _dir, _events: {"run_id": "different", "checkpoint_generation": "different", "same": [1]})
        assert not receipt.exists()


def test_input_manifest_binding_requires_a_canonical_actual_file_and_current_hash() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = Path(temporary) / "manifest.json"
        manifest.write_bytes(verifier._canonical(_manifest_payload()))
        digest = verifier._sha256_file(manifest)
        state = _state("base")
        state["inputs"] = {**state["inputs"], "input_manifest_path": str(manifest.resolve()),
                           "input_manifest_sha256": digest}
        expected_config = _expected_bindings()["expected_training_config_sha256"]
        assert verifier._input_manifest_binding(state, digest, expected_config) == {
            "path": str(manifest.resolve()), "sha256": digest,
            "training_config_sha256": expected_config}
        manifest.unlink()
        with pytest.raises(verifier.EquivalenceError, match="missing"):
            verifier._input_manifest_binding(state, digest, expected_config)


def test_v3_fresh_lora_manifest_binding_preserves_legacy_empty_init_provenance() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = Path(temporary) / "manifest.json"
        payload = _manifest_payload()
        payload["schema_version"] = "airi.behavior-input-manifest.v3"
        payload["training_config"] = {**payload["training_config"],
                                      "init_mode": "fresh-lora"}
        payload["training_config_sha256"] = verifier._sha256_bytes(
            verifier._canonical(payload["training_config"]))
        payload["initial_adapter"] = None
        manifest.write_bytes(verifier._canonical(payload))
        digest = verifier._sha256_file(manifest)
        state = _state("fresh")
        state["inputs"] = {
            **state["inputs"], "input_manifest_path": str(manifest.resolve()),
            "input_manifest_sha256": digest,
            "input_manifest_training_config_sha256": payload["training_config_sha256"],
            "init_mode": "fresh-lora", "init_adapter_dir": "",
            "init_adapter_model_sha256": "", "init_adapter_config_sha256": "",
            "init_adapter_artifact_manifest_sha256": "",
        }
        assert verifier._input_manifest_binding(
            state, digest, payload["training_config_sha256"])["init_mode"] == "fresh-lora"


def test_v3_weights_only_manifest_reverifies_adapter_inventory_and_provenance() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        adapter = root / "source-adapter"
        adapter.mkdir()
        model = adapter / "adapter_model.safetensors"
        config = adapter / "adapter_config.json"
        readme = adapter / "README.md"
        model.write_bytes(b"adapter weights")
        config.write_bytes(b'{"peft_type":"LORA"}\n')
        readme.write_bytes(b"local test artifact\n")
        files = [{"path": path.name, "bytes": path.stat().st_size,
                  "sha256": verifier._sha256_file(path)}
                 for path in (config, model, readme)]
        artifact = {
            "schema_version": "airi.behavior-adapter-artifact.v1",
            "run_id": "e2-source-run", "pins": {"model_weight_sha256": "2" * 64},
            "files": files,
        }
        artifact_path = adapter / "artifact-manifest.json"
        artifact_path.write_bytes(verifier._canonical(artifact))
        artifact_sha = verifier._sha256_file(artifact_path)
        model_sha = verifier._sha256_file(model)
        config_sha = verifier._sha256_file(config)
        payload = _manifest_payload()
        payload["schema_version"] = "airi.behavior-input-manifest.v3"
        payload["training_config"] = {**payload["training_config"],
                                      "init_mode": "adapter-weights-only"}
        payload["training_config_sha256"] = verifier._sha256_bytes(
            verifier._canonical(payload["training_config"]))
        payload["initial_adapter"] = {
            "run_id": "e2-source-run", "model_sha256": model_sha,
            "config_sha256": config_sha, "artifact_manifest_sha256": artifact_sha,
            "files": files,
        }
        manifest = root / "manifest.json"
        manifest.write_bytes(verifier._canonical(payload))
        digest = verifier._sha256_file(manifest)
        state = _state("weights-only")
        state["inputs"] = {
            **state["inputs"], "input_manifest_path": str(manifest.resolve()),
            "input_manifest_sha256": digest,
            "input_manifest_training_config_sha256": payload["training_config_sha256"],
            "init_mode": "adapter-weights-only",
            "init_adapter_dir": str(adapter.resolve()),
            "init_adapter_model_sha256": model_sha,
            "init_adapter_config_sha256": config_sha,
            "init_adapter_artifact_manifest_sha256": artifact_sha,
        }
        result = verifier._input_manifest_binding(
            state, digest, payload["training_config_sha256"])
        assert result["init_mode"] == "adapter-weights-only"

        extra = adapter / "unexpected.bin"
        extra.write_bytes(b"unexpected")
        with pytest.raises(verifier.EquivalenceError,
                           match="initial adapter inventory file inventory mismatch"):
            verifier._input_manifest_binding(
                state, digest, payload["training_config_sha256"])
        extra.unlink()
        empty = adapter / "unexpected-empty-directory"
        empty.mkdir()
        with pytest.raises(verifier.EquivalenceError,
                           match="initial adapter inventory file inventory mismatch"):
            verifier._input_manifest_binding(
                state, digest, payload["training_config_sha256"])
        empty.rmdir()

        model.write_bytes(b"tampered weights")
        with pytest.raises(verifier.EquivalenceError, match="integrity mismatch"):
            verifier._input_manifest_binding(
                state, digest, payload["training_config_sha256"])


def test_v3_weights_only_manifest_rejects_run_state_init_pin_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = Path(temporary) / "manifest.json"
        payload = _manifest_payload()
        payload["schema_version"] = "airi.behavior-input-manifest.v3"
        payload["training_config"] = {**payload["training_config"],
                                      "init_mode": "adapter-weights-only"}
        payload["training_config_sha256"] = verifier._sha256_bytes(
            verifier._canonical(payload["training_config"]))
        payload["initial_adapter"] = {
            "run_id": "e2-source", "model_sha256": "6" * 64,
            "config_sha256": "7" * 64, "artifact_manifest_sha256": "8" * 64,
            "files": [{"path": "adapter_model.safetensors", "bytes": 1,
                       "sha256": "6" * 64}],
        }
        manifest.write_bytes(verifier._canonical(payload))
        digest = verifier._sha256_file(manifest)
        state = _state("pin-mismatch")
        state["inputs"] = {
            **state["inputs"], "input_manifest_path": str(manifest.resolve()),
            "input_manifest_sha256": digest,
            "input_manifest_training_config_sha256": payload["training_config_sha256"],
            "init_mode": "adapter-weights-only", "init_adapter_dir": str(Path(temporary).resolve()),
            "init_adapter_model_sha256": "0" * 64,
            "init_adapter_config_sha256": "7" * 64,
            "init_adapter_artifact_manifest_sha256": "8" * 64,
        }
        with pytest.raises(verifier.EquivalenceError, match="initial adapter pin differs"):
            verifier._input_manifest_binding(
                state, digest, payload["training_config_sha256"])


def test_manifest_binding_uses_one_snapshot_across_hash_parse_cutpoint() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = Path(temporary) / "manifest.json"
        payload = verifier._canonical(_manifest_payload())
        manifest.write_bytes(payload)
        digest = verifier._sha256_bytes(payload)
        state = _state("base")
        state["inputs"] = {**state["inputs"], "input_manifest_path": str(manifest.resolve()),
                           "input_manifest_sha256": digest}
        original_loads = verifier.json.loads

        def replace_after_snapshot(value, *args, **kwargs):
            manifest.write_bytes(b'{"replaced":true}\n')
            return original_loads(value, *args, **kwargs)

        with patch.object(verifier.json, "loads", side_effect=replace_after_snapshot):
            result = verifier._input_manifest_binding(
                state, digest, _expected_bindings()["expected_training_config_sha256"])
        assert result["sha256"] == digest
        assert manifest.read_bytes() == b'{"replaced":true}\n'


def test_input_manifest_binding_refuses_mutation_and_reparse_simulation() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest = root / "manifest.json"
        manifest.write_bytes(b"original\n")
        digest = verifier._sha256_file(manifest)
        state = _state("base")
        state["inputs"] = {**state["inputs"], "input_manifest_path": str(manifest.resolve()),
                           "input_manifest_sha256": digest}
        manifest.write_bytes(b"mutated\n")
        with pytest.raises(verifier.EquivalenceError, match="bytes differ"):
            verifier._input_manifest_binding(
                state, digest, _expected_bindings()["expected_training_config_sha256"])
        manifest.write_bytes(b"original\n")
        with patch.object(verifier, "_require_local_fixed_path",
                          side_effect=verifier.EquivalenceError("completed run input manifest cannot traverse a reparse point")):
            with pytest.raises(verifier.EquivalenceError, match="reparse point"):
                verifier._input_manifest_binding(
                    state, digest, _expected_bindings()["expected_training_config_sha256"])


def test_input_manifest_binding_refuses_malformed_training_config_sha256() -> None:
    state = _state("base")
    state["inputs"] = {**state["inputs"],
                       "input_manifest_training_config_sha256": "not-a-sha256"}
    with pytest.raises(verifier.EquivalenceError, match="identity is malformed"):
        verifier._input_manifest_binding(
            state, TEST_MANIFEST_SHA256,
            _expected_bindings()["expected_training_config_sha256"])


@pytest.mark.parametrize(("mutation", "message"), [
    (lambda value: value.update({"schema_version": "wrong"}), "schema mismatch"),
    (lambda value: value.update({"unexpected": True}), "schema mismatch"),
    (lambda value: value["training_config"].pop("max_seq_len"), "configuration schema mismatch"),
    (lambda value: value.update({"training_config_sha256": "0" * 64}), "config hash is invalid"),
    (lambda value: value.update({"dataset_sha256": "4" * 64}), "pin differs"),
])
def test_input_manifest_binding_refuses_content_schema_hash_and_pin_faults(mutation, message) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = Path(temporary) / "manifest.json"
        payload = _manifest_payload()
        mutation(payload)
        manifest.write_bytes(verifier._canonical(payload))
        digest = verifier._sha256_file(manifest)
        state = _state("base")
        state["inputs"] = {**state["inputs"], "input_manifest_path": str(manifest.resolve()),
                           "input_manifest_sha256": digest}
        with pytest.raises(verifier.EquivalenceError, match=message):
            verifier._input_manifest_binding(
                state, digest, _expected_bindings()["expected_training_config_sha256"])


def test_input_manifest_binding_refuses_nonfinite_manifest_config() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = Path(temporary) / "manifest.json"
        payload = _manifest_payload()
        payload["training_config"]["learning_rate"] = float("inf")
        manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                            encoding="utf-8", newline="\n")
        digest = verifier._sha256_file(manifest)
        state = _state("base")
        state["inputs"] = {**state["inputs"], "input_manifest_path": str(manifest.resolve()),
                           "input_manifest_sha256": digest}
        with pytest.raises(verifier.EquivalenceError, match="non-canonical values"):
            verifier._input_manifest_binding(
                state, digest, _expected_bindings()["expected_training_config_sha256"])


def test_equivalence_refuses_same_bytes_manifest_path_swap() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline, resumed = root / "baseline", root / "resumed"
        baseline.mkdir(); resumed.mkdir()
        first, second = root / "first.json", root / "second.json"
        first.write_bytes(verifier._canonical(_manifest_payload()))
        second.write_bytes(verifier._canonical(_manifest_payload()))
        digest = verifier._sha256_file(first)
        base_state, resume_state = _state("base"), _state("resume")
        base_state["inputs"] = {**base_state["inputs"], "input_manifest_path": str(first.resolve()),
                                "input_manifest_sha256": digest}
        resume_state["inputs"] = {**resume_state["inputs"], "input_manifest_path": str(second.resolve()),
                                  "input_manifest_sha256": digest}
        with patch.object(verifier, "_completed_run", side_effect=[base_state, resume_state]):
            with pytest.raises(verifier.EquivalenceError, match="different canonical input manifest paths"):
                verifier.verify_equivalence(
                    baseline, resumed, root / "receipt.json",
                    expected_microsteps=320, expected_optimizer_steps=20,
                    expected_checkpoint_every_optimizer_steps=5,
                    **_expected_bindings(expected_input_manifest_sha256=digest))


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


def test_completed_run_without_final_evidence_root_is_not_publishable() -> None:
    state = _state("base")
    state["terminal"] = {"exit_code": 0}
    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(verifier.EquivalenceError, match="final producer evidence receipt"):
            verifier._closed_producer_evidence(
                state, Path(temporary), {"index_sha256": "a" * 64},
                {"microsteps_completed": 320, "optimizer_steps": 20,
                 "pending_microbatches": 0, "training_elapsed_ns": 1})


def test_completed_run_state_checkpoint_must_match_latest_index_and_event() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline, resumed = root / "baseline", root / "resumed"
        baseline.mkdir(); resumed.mkdir()
        latest = {"manifest": {"pins": _pins(), "generation": "checkpoint-00000001",
                               "payload": {"sha256": "c" * 64}}, "manifest_sha256": "b" * 64}
        bad = _state("base")
        bad["checkpoint"] = {"relative_path": "checkpoint-00000002", "manifest_sha256": "b" * 64}
        with patch.object(verifier, "_completed_run", side_effect=[bad, _state("resume")]), \
                patch.object(verifier, "_latest_verified_generation", side_effect=[latest, latest]), \
                patch.object(verifier, "_events", side_effect=[([_event("base", "checkpoint-00000001")], [1, 2, 3, 4]), ([_event("resume", "checkpoint-00000001", "safe-pause")], [1, 2, 3, 4])]):
            with pytest.raises(verifier.EquivalenceError, match="run-state/latest checkpoint"):
                verifier.verify_equivalence(
                    baseline, resumed, root / "receipt.json", expected_microsteps=320,
                    expected_optimizer_steps=20, expected_checkpoint_every_optimizer_steps=5,
                    **_expected_bindings())


def test_normalization_only_ignores_identity_fields() -> None:
    assert verifier._normalise_state({"run_id": "a", "training_elapsed_ns": 1,
                                      "x": [{"checkpoint_generation": "g", "v": 1}]}) == {"x": [{"v": 1}]}


@pytest.mark.parametrize("field, incorrect", [
    ("epoch", 2),
    ("next_batch_index", 3),
    ("microsteps_completed", 319),
    ("optimizer_steps", 19),
    ("pending_microbatches", 1),
])
def test_runner_progress_rejects_each_compact_projection_mismatch(field, incorrect) -> None:
    progress = {"epoch": 1, "next_batch_index": 2, "microsteps_completed": 320,
                "optimizer_steps": 20, "pending_microbatches": 0,
                "training_elapsed_ns": 123}
    state = {"progress": {key: progress[key] for key in (
        "epoch", "next_batch_index", "microsteps_completed", "optimizer_steps",
        "pending_microbatches")}}
    verifier._require_runner_progress_projection(state, progress)
    state["progress"][field] = incorrect
    with pytest.raises(verifier.EquivalenceError, match="progress differs"):
        verifier._require_runner_progress_projection(state, progress)


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


def test_checkpoint_state_ignores_elapsed_time_but_not_deterministic_state() -> None:
    baseline = {"run_id": "baseline", "training_elapsed_ns": 1,
                "optimizer": {"step": 20}, "losses": [0.5]}
    resumed = {"run_id": "resumed", "training_elapsed_ns": 2,
               "optimizer": {"step": 20}, "losses": [0.5]}
    verifier._compare_state(baseline, resumed)
    resumed["optimizer"]["step"] = 21
    with pytest.raises(verifier.EquivalenceError, match="value differs"):
        verifier._compare_state(baseline, resumed)


def test_real_shaped_event_uses_three_field_payload_progress_and_top_level_timing() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        events = run / "checkpoint-events"
        events.mkdir()
        pins = _pins()
        run_state = {"created_at_utc": "2026-08-22T00:00:00Z"}
        (run / "run-state.json").write_bytes(verifier._canonical(run_state))
        previous = None
        for number, second in enumerate((100, 200, 300, 400), start=1):
            generation = f"checkpoint-{number:08d}"
            index = {"schema_version": verifier.TRANSACTION_INDEX_SCHEMA, "run_id": "base",
                     "latest": {"relative_path": generation, "manifest_sha256": "a" * 64,
                                "event_relative_path": f"checkpoint-events/{generation}.json", "event_sha256": "c" * 64},
                     "previous": None, "previous_index_sha256": None}
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
                "checkpoint_payload_progress": {"microsteps_completed": number * 80,
                                                "optimizer_steps": number * 5,
                                                 "pending_microbatches": 0},
                "pins_sha256": verifier._sha256_bytes(verifier._canonical(pins)),
                "previous_event_sha256": previous,
                "previous_index_sha256": None,
                "training_elapsed_ns": second * 1_000_000_000,
            }
            raw = verifier._canonical(event)
            (events / f"{generation}.json").write_bytes(raw)
            previous = verifier._sha256_bytes(raw)
        found, intervals = verifier._events(run, "base", pins)
        assert len(found) == 4
        assert intervals == [101.0, 101.0, 101.0, 101.0]


def test_event_inventory_rejects_a_generation_gap() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        events = run / "checkpoint-events"
        events.mkdir()
        pins = _pins()
        for number in (1, 3):
            generation = f"checkpoint-{number:08d}"
            index = {"schema_version": verifier.TRANSACTION_INDEX_SCHEMA, "run_id": "base",
                     "latest": {"relative_path": generation, "manifest_sha256": "a" * 64,
                                "event_relative_path": f"checkpoint-events/{generation}.json", "event_sha256": "c" * 64},
                     "previous": None, "previous_index_sha256": None}
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
                "checkpoint_payload_progress": {"microsteps_completed": number,
                                                "optimizer_steps": number,
                                                 "pending_microbatches": 0},
                "pins_sha256": verifier._sha256_bytes(verifier._canonical(pins)),
                "previous_event_sha256": None,
                "previous_index_sha256": None,
                "training_elapsed_ns": number * 1_000_000_000,
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
        index = {"schema_version": verifier.TRANSACTION_INDEX_SCHEMA, "run_id": "base",
                 "latest": {"relative_path": generation, "manifest_sha256": "a" * 64,
                            "event_relative_path": f"checkpoint-events/{generation}.json", "event_sha256": "c" * 64},
                 "previous": None, "previous_index_sha256": None}
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
            "checkpoint_payload_progress": {"microsteps_completed": 1, "optimizer_steps": 1,
                                             "pending_microbatches": 0},
            "pins_sha256": verifier._sha256_bytes(verifier._canonical(pins)),
            "previous_event_sha256": None,
            "previous_index_sha256": None,
            "training_elapsed_ns": 1_000_000_000,
        }
        (events / f"{generation}.json").write_bytes(verifier._canonical(event))
        with pytest.raises(verifier.EquivalenceError, match="wall/monotonic"):
            verifier._events(run, "base", pins)


@pytest.mark.parametrize("mutate", [
    lambda index: index["latest"].__setitem__("event_sha256", "d" * 64),
    lambda index: index.__setitem__("previous", {"event_sha256": "e" * 64}),
    lambda index: index.__setitem__("previous_index_sha256", "f" * 64),
])
def test_current_index_rejects_wrong_event_or_predecessor(mutate) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        generation = "checkpoint-00000001"
        index = {"schema_version": verifier.TRANSACTION_INDEX_SCHEMA, "run_id": "base",
                 "latest": {"relative_path": generation, "manifest_sha256": "a" * 64,
                            "event_relative_path": f"checkpoint-events/{generation}.json", "event_sha256": "c" * 64},
                 "previous": None, "previous_index_sha256": None}
        mutate(index)
        event = {"generation": generation, "checkpoint_manifest_sha256": "a" * 64,
                 "previous_event_sha256": None, "previous_index_sha256": None}
        with pytest.raises(verifier.EquivalenceError, match="checkpoint index"):
            verifier._bind_current_index_event(run, {"index": index, "event_sha256": "c" * 64}, event)


@pytest.mark.parametrize("mutate", [
    lambda index: index.__setitem__("schema_version", "wrong"),
    lambda index: index.__setitem__("extra", True),
])
def test_current_index_rejects_wrong_schema_or_extra_field(mutate) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        generation = "checkpoint-00000001"
        event_path = run / "checkpoint-events" / f"{generation}.json"
        event_path.parent.mkdir(parents=True)
        event_path.write_bytes(b"{}\n")
        index = {"schema_version": verifier.TRANSACTION_INDEX_SCHEMA, "run_id": "base",
                 "latest": {"relative_path": generation, "manifest_sha256": "a" * 64,
                            "event_relative_path": f"checkpoint-events/{generation}.json",
                            "event_sha256": verifier._sha256_bytes(b"{}\n")},
                 "previous": None, "previous_index_sha256": None}
        mutate(index)
        path = run / "checkpoints" / "checkpoint-index.json"
        path.parent.mkdir()
        path.write_bytes(verifier._canonical(index))
        with pytest.raises(verifier.EquivalenceError, match="checkpoint index"):
            verifier._latest_verified_generation(run, "base")


@pytest.mark.parametrize("fault", ["malformed", "wrong-run", "wrong-latest"])
def test_current_index_rejects_malformed_or_unlinked_retained_predecessor(fault) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        checkpoints = run / "checkpoints"
        checkpoints.mkdir(parents=True)
        previous = {"relative_path": "checkpoint-00000001", "manifest_sha256": "a" * 64,
                    "event_relative_path": "checkpoint-events/checkpoint-00000001.json", "event_sha256": "b" * 64}
        predecessor = {"schema_version": verifier.TRANSACTION_INDEX_SCHEMA, "run_id": "base",
                       "latest": previous, "previous": None, "previous_index_sha256": None}
        path = checkpoints / "checkpoint-index.prev.json"
        if fault == "malformed":
            path.write_bytes(b"not-json\n")
        else:
            if fault == "wrong-run":
                predecessor["run_id"] = "other"
            else:
                predecessor["latest"] = {**previous, "event_sha256": "c" * 64}
            path.write_bytes(verifier._canonical(predecessor))
        index = {"schema_version": verifier.TRANSACTION_INDEX_SCHEMA, "run_id": "base",
                 "latest": {"relative_path": "checkpoint-00000002", "manifest_sha256": "d" * 64,
                            "event_relative_path": "checkpoint-events/checkpoint-00000002.json", "event_sha256": "e" * 64},
                 "previous": previous,
                 "previous_index_sha256": verifier._sha256_bytes(path.read_bytes())}
        event = {"generation": "checkpoint-00000002", "checkpoint_manifest_sha256": "d" * 64,
                 "previous_event_sha256": "b" * 64,
                 "previous_index_sha256": index["previous_index_sha256"]}
        with pytest.raises(verifier.EquivalenceError, match="previous checkpoint index|retained previous"):
            verifier._bind_current_index_event(run, {"index": index, "event_sha256": "e" * 64}, event)


def test_event_counters_reject_bool_values() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run = Path(temporary)
        events = run / "checkpoint-events"
        events.mkdir()
        event = {"schema_version": verifier.EVENT_SCHEMA, "run_id": "base", "generation": "checkpoint-00000001",
                 "reason": "interval", "microsteps_completed": True, "optimizer_steps": 1,
                 "pending_microbatches": 0, "publish_started_at_utc": "2026-08-22T00:00:00Z",
                 "checkpoint_durable_at_utc": "2026-08-22T00:00:01Z", "publish_elapsed_ns": 1_000_000_000,
                 "training_elapsed_ns": 1_000_000_000, "checkpoint_manifest_sha256": "a" * 64,
                 "checkpoint_payload_sha256": "b" * 64,
                 "checkpoint_payload_progress": {"microsteps_completed": True, "optimizer_steps": 1,
                                                  "pending_microbatches": 0},
                 "pins_sha256": verifier._sha256_bytes(verifier._canonical(_pins())),
                 "previous_event_sha256": None, "previous_index_sha256": None}
        (events / "checkpoint-00000001.json").write_bytes(verifier._canonical(event))
        with pytest.raises(verifier.EquivalenceError, match="progress fields"):
            verifier._events(run, "base", _pins())


def test_producer_output_root_hashes_must_match_verified_receipts() -> None:
    state = {"outputs": {"report": {"sha256": "r" * 64}}}
    artifact = {"manifest_sha256": "a" * 64}
    evidence = {"adapter_artifact_manifest_sha256": "a" * 64, "report_sha256": "r" * 64}
    verifier._bind_producer_output_hashes("baseline", state, artifact, evidence)
    with pytest.raises(verifier.EquivalenceError, match="output receipts"):
        verifier._bind_producer_output_hashes(
            "baseline", state, artifact,
            {"adapter_artifact_manifest_sha256": "b" * 64, "report_sha256": "r" * 64})


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
