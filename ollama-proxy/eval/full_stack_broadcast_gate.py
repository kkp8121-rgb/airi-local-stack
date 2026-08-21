"""Offline, fail-closed validation for full-stack AIRI broadcast evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "full-stack-broadcast-gate-manifest-v1"
REQUIRED_CATEGORIES = (
    "runtime_activation", "long_broadcast", "model_training", "tts_latency", "safety_activation",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UTC_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class GateError(Exception):
    def __init__(self, code: str, category: str = "manifest") -> None:
        self.code = code
        self.category = category


def _fail(code: str, category: str) -> None:
    raise GateError(code, category)


def _object(value: Any, keys: set[str], category: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("invalid_object", category)
    actual = set(value)
    if actual != keys:
        _fail("unknown_or_missing_keys", category)
    return value


def _number(value: Any, category: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail("non_finite_or_invalid_number", category)
    return float(value)


def _integer(value: Any, category: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("invalid_integer", category)
    return value


def _bool(value: Any, category: str) -> bool:
    if not isinstance(value, bool):
        _fail("invalid_boolean", category)
    return value


def _digest(value: Any, category: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        _fail("invalid_digest", category)
    return value


def _text(value: Any, category: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("empty_required_value", category)
    return value


def _captured_at(value: Any, category: str) -> str:
    value = _text(value, category)
    if not UTC_RFC3339.fullmatch(value):
        _fail("invalid_captured_at", category)
    try:
        if datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            _fail("invalid_captured_at", category)
    except ValueError:
        _fail("invalid_captured_at", category)
    return value


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return path.is_symlink() or bool(getattr(metadata, "st_file_attributes", 0) & reparse)


def _artifact_path(bundle_root: Path, relative: str, category: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        _fail("artifact_path_outside_bundle", category)
    untrusted = bundle_root / candidate
    try:
        resolved = untrusted.resolve(strict=True)
        resolved.relative_to(bundle_root)
    except (OSError, RuntimeError, ValueError):
        _fail("artifact_path_outside_bundle", category)
    # Reject final links/reparse points as well as any link/reparse path component.
    current = bundle_root
    for part in candidate.parts:
        current = current / part
        if _is_link_or_reparse(current):
            _fail("artifact_path_outside_bundle", category)
    if not resolved.is_file() or _is_link_or_reparse(resolved):
        _fail("artifact_path_outside_bundle", category)
    return resolved


def _common(evidence: Any, category: str) -> dict[str, Any]:
    return _object(evidence, {"run_id", "captured_at", "model_digest", "evidence"}, category)


def _validate_runtime(e: Any, model_digest: str) -> None:
    category = "runtime_activation"
    root = _common(e, category)
    _text(root["run_id"], category); _captured_at(root["captured_at"], category)
    if _digest(root["model_digest"], category) != model_digest: _fail("model_digest_mismatch", category)
    x = _object(root["evidence"], {"before_health_sha256", "after_health_sha256", "chat_model", "chat_digest", "memory", "knowledge", "continuity_observation_delta", "broadcast_contract_on", "memory_claim_guard_on", "immediate_ack_marker", "character_state_session_delta", "show_arc", "affect", "input_safety_state", "output_safety_state"}, category)
    before = _digest(x["before_health_sha256"], category)
    if before == _digest(x["after_health_sha256"], category): _fail("health_telemetry_unchanged", category)
    _text(x["chat_model"], category)
    if _digest(x["chat_digest"], category) != model_digest: _fail("chat_digest_mismatch", category)
    for name in ("memory", "knowledge"):
        item = _object(x[name], {"enabled", "ready", "retrieval_delta", "journal_delta" if name == "memory" else "relevant_retrieval_delta"}, category)
        if not _bool(item["enabled"], category) or not _bool(item["ready"], category): _fail("required_runtime_state_off", category)
        for key in item:
            if key.endswith("delta") and _number(item[key], category) <= 0: _fail("missing_runtime_delta", category)
    for name in ("continuity_observation_delta", "character_state_session_delta"):
        if _number(x[name], category) <= 0: _fail("missing_runtime_delta", category)
    for name in ("broadcast_contract_on", "memory_claim_guard_on", "immediate_ack_marker"):
        if not _bool(x[name], category): _fail("required_runtime_state_off", category)
    for name, fields in (("show_arc", {"enabled", "ready", "seed_delta", "callback_delta"}), ("affect", {"enabled", "ready", "event_delta", "snapshot_delta", "expression_delta"})):
        item = _object(x[name], fields, category)
        if not _bool(item["enabled"], category) or not _bool(item["ready"], category): _fail("required_runtime_state_off", category)
        if any(_number(item[key], category) <= 0 for key in item if key.endswith("delta")): _fail("missing_runtime_delta", category)
    if x["input_safety_state"] != "enabled_ready" or x["output_safety_state"] != "enabled_ready": _fail("unsafe_runtime_state", category)


def _validate_broadcast(e: Any, model_digest: str) -> None:
    category = "long_broadcast"; root = _common(e, category)
    _text(root["run_id"], category); _captured_at(root["captured_at"], category)
    if _digest(root["model_digest"], category) != model_digest: _fail("model_digest_mismatch", category)
    x = _object(root["evidence"], {"duration_minutes", "seeds", "callback_gaps_minutes", "complete_arc_recall", "wrong_or_forbidden_callbacks", "cross_show_leakage", "self_led_initiative", "cta_rate", "meta_leaks"}, category)
    if _number(x["duration_minutes"], category) < 180: _fail("broadcast_too_short", category)
    if not isinstance(x["seeds"], list) or len(x["seeds"]) < 3: _fail("insufficient_seeds", category)
    seed_ids: set[str] = set()
    for seed in x["seeds"]:
        s = _object(seed, {"seed_id", "turns", "arcs"}, category)
        seed_id = _text(s["seed_id"], category)
        if seed_id in seed_ids: _fail("duplicate_seed_id", category)
        seed_ids.add(seed_id)
        if _integer(s["turns"], category) < 500 or _integer(s["arcs"], category) < 12: _fail("insufficient_seed_coverage", category)
    gaps = x["callback_gaps_minutes"]
    if not isinstance(gaps, list) or len(gaps) < 6 or any(_number(v, category) < 90 for v in gaps): _fail("insufficient_callback_gaps", category)
    limits = (("complete_arc_recall", lambda v: v >= .90), ("wrong_or_forbidden_callbacks", lambda v: v == 0), ("cross_show_leakage", lambda v: v == 0), ("self_led_initiative", lambda v: v >= .30), ("cta_rate", lambda v: v <= .45), ("meta_leaks", lambda v: v == 0))
    if any(not test(_number(x[name], category)) for name, test in limits): _fail("broadcast_quality_threshold_failed", category)


def _validate_training(e: Any, model_digest: str) -> None:
    category = "model_training"; root = _common(e, category)
    _text(root["run_id"], category); _captured_at(root["captured_at"], category)
    if _digest(root["model_digest"], category) != model_digest: _fail("model_digest_mismatch", category)
    x = _object(root["evidence"], {"cuda", "base_digest", "adapter_digest", "export_digest", "dataset_digest", "dataset_reviewed_airi_original", "splits", "official_transcript_training", "qlora_metrics"}, category)
    if not _bool(x["cuda"], category): _fail("cuda_not_verified", category)
    for name in ("base_digest", "adapter_digest", "export_digest", "dataset_digest"): _digest(x[name], category)
    if not _bool(x["dataset_reviewed_airi_original"], category): _fail("dataset_not_reviewed", category)
    splits = _object(x["splits"], {"train_rows", "dev_rows", "test_rows", "group_leakage", "duplicate_targets", "heldout_reference_overlap"}, category)
    if _integer(splits["train_rows"], category) < 200 or _integer(splits["dev_rows"], category) <= 0 or _integer(splits["test_rows"], category) <= 0: _fail("invalid_train_dev_test_split", category)
    if any(_integer(splits[name], category) != 0 for name in ("group_leakage", "duplicate_targets", "heldout_reference_overlap")): _fail("training_split_leakage", category)
    if _bool(x["official_transcript_training"], category): _fail("official_transcript_training_present", category)
    metrics = x["qlora_metrics"]
    if not isinstance(metrics, dict) or not metrics: _fail("missing_qlora_metrics", category)
    for value in metrics.values(): _number(value, category)


def _validate_tts(e: Any, model_digest: str) -> None:
    category = "tts_latency"; root = _common(e, category)
    _text(root["run_id"], category); _captured_at(root["captured_at"], category)
    if _digest(root["model_digest"], category) != model_digest: _fail("model_digest_mismatch", category)
    x = _object(root["evidence"], {"engine", "first_4096_byte_ms", "playback_start_evidence", "render_evidence", "latency_spans_ms"}, category)
    if x["engine"] != "GPT-SoVITS v2ProPlus": _fail("wrong_tts_engine", category)
    samples = x["first_4096_byte_ms"]
    if not isinstance(samples, list) or len(samples) != 7 or any(_number(v, category) > 800 or _number(v, category) <= 0 for v in samples): _fail("tts_first_chunk_threshold_failed", category)
    if not _bool(x["playback_start_evidence"], category) or not _bool(x["render_evidence"], category): _fail("missing_tts_evidence", category)
    spans = _object(x["latency_spans_ms"], {"llm_start", "llm_content", "llm_end", "tts_start", "tts_first", "tts_end"}, category)
    if any(_number(value, category) <= 0 for value in spans.values()): _fail("missing_latency_telemetry", category)


def _validate_safety(e: Any, model_digest: str) -> None:
    category = "safety_activation"; root = _common(e, category)
    _text(root["run_id"], category); _captured_at(root["captured_at"], category)
    if _digest(root["model_digest"], category) != model_digest: _fail("model_digest_mismatch", category)
    x = _object(root["evidence"], {"prerequisites_closed", "user_approved", "greybox_span", "greybox_taxonomy", "greybox_alias", "greybox_briefing_evidence", "external_services", "training_artifact_promotion", "user_approval"}, category)
    for name in ("prerequisites_closed", "user_approved", "greybox_span", "greybox_taxonomy", "greybox_alias", "greybox_briefing_evidence", "external_services", "training_artifact_promotion", "user_approval"):
        _bool(x[name], category)
    # This validator is readiness-only: it never grants activation, even if prerequisites exist.
    if any(x[name] for name in ("greybox_span", "greybox_taxonomy", "greybox_alias", "greybox_briefing_evidence", "external_services", "training_artifact_promotion", "user_approval")):
        _fail("premature_or_unauthorized_activation", category)


VALIDATORS = {"runtime_activation": _validate_runtime, "long_broadcast": _validate_broadcast, "model_training": _validate_training, "tts_latency": _validate_tts, "safety_activation": _validate_safety}


def validate_manifest(manifest_path: str | Path) -> dict[str, Any]:
    """Return a content-free validation report. Bad input always produces pass=False."""
    failures: list[dict[str, str]] = []
    checks: list[dict[str, str]] = []
    try:
        path = Path(manifest_path)
        bundle_root = path.parent.resolve(strict=True)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        m = _object(manifest, {"schema_version", "model_digest", "artifacts"}, "manifest")
        if m["schema_version"] != SCHEMA_VERSION: _fail("unsupported_schema_version", "manifest")
        model_digest = _digest(m["model_digest"], "manifest")
        artifacts = m["artifacts"]
        if not isinstance(artifacts, list) or len(artifacts) != len(REQUIRED_CATEGORIES): _fail("invalid_artifact_count", "manifest")
        seen_categories: set[str] = set(); seen_runs: set[str] = set(); seen_files: set[str] = set(); seen_digests: set[str] = set()
        for item in artifacts:
            a = _object(item, {"category", "path", "sha256", "run_id", "captured_at", "model_digest"}, "manifest")
            category = a["category"]
            if category not in REQUIRED_CATEGORIES or category in seen_categories: _fail("missing_or_duplicate_category", "manifest")
            if not isinstance(a["path"], str) or not a["path"]: _fail("invalid_artifact_path", "manifest")
            if a["run_id"] in seen_runs or not isinstance(a["run_id"], str) or not a["run_id"]: _fail("duplicate_or_invalid_run_id", "manifest")
            if a["path"] in seen_files: _fail("artifact_reused_across_categories", "manifest")
            digest = _digest(a["sha256"], "manifest")
            if digest in seen_digests: _fail("artifact_reused_across_categories", "manifest")
            _captured_at(a["captured_at"], "manifest")
            if _digest(a["model_digest"], "manifest") != model_digest: _fail("model_digest_mismatch", "manifest")
            artifact_path = _artifact_path(bundle_root, a["path"], category)
            raw = artifact_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest: _fail("artifact_digest_mismatch", category)
            evidence = json.loads(raw.decode("utf-8"))
            common = _common(evidence, category)
            if common["run_id"] != a["run_id"] or common["captured_at"] != a["captured_at"] or common["model_digest"] != a["model_digest"]: _fail("artifact_manifest_binding_mismatch", category)
            VALIDATORS[category](evidence, model_digest)
            seen_categories.add(category); seen_runs.add(a["run_id"]); seen_files.add(a["path"]); seen_digests.add(digest)
            checks.append({"category": category, "status": "passed"})
        if seen_categories != set(REQUIRED_CATEGORIES): _fail("missing_required_category", "manifest")
    except GateError as error:
        failures.append({"category": error.category, "code": error.code})
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        failures.append({"category": "manifest", "code": "unreadable_or_invalid_json"})
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        # Validation is evidence readiness only; no output can authorize an operation.
        "authorizations": {
            "greybox": False,
            "external_services": False,
            "training_artifact_promotion": False,
            "user_approval": False,
        },
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"pass": False, "checks": [], "failures": [{"category": "manifest", "code": "manifest_path_required"}], "authorizations": {"greybox": False, "external_services": False, "training_artifact_promotion": False, "user_approval": False}}))
        raise SystemExit(2)
    report = validate_manifest(sys.argv[1])
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["pass"] else 1)
