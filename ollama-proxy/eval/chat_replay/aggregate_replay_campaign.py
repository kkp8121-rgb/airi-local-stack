#!/usr/bin/env python3
"""Validate and aggregate one local three-source OFF/ON replay campaign."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Any

from chat_replay import ALLOWED_KINDS, SURFACE_SIGNAL_ORDER, _canonical
from normalize_authorized_export import read_identity_key
from replay_local_io import _secure_inside, write_atomic_json


HERE = Path(__file__).resolve().parent
MANIFEST_SCHEMA = "airi.chat-replay-campaign-manifest.v1"
REPLAY_SCHEMA = "airi.chat-replay-report.v2"
SCORE_SCHEMA = "airi.chat-replay-human-score.v2"
CAMPAIGN_SCHEMA = "airi.chat-replay-campaign-report.v1"
REPORT_HMAC_DOMAIN = b"airi.chat-replay-report.v1\0"
SCORE_HMAC_DOMAIN = b"airi.chat-replay-human-score.v1\0"
SOURCE_LABEL_HMAC_DOMAIN = b"airi.chat-replay-source-labels.v1\0"
SLOTS = ("channel_a", "channel_b", "channel_c")
PHASES = frozenset({"opening", "middle", "topic_transition", "game_transition"})
PROVIDERS = frozenset({"chzzk", "soop", "youtube"})
GATES = ("off", "on")
QUALITY_FIELDS = (
    "grounded", "context_preserved", "tone_ok", "privacy_ok",
    "current_fact_ok", "reference_grounding_ok", "agreement_calibration_ok",
)
CRITICAL_FIELDS = (
    "privacy_ok", "current_fact_ok", "reference_grounding_ok",
    "agreement_calibration_ok",
)
ATMOSPHERES = frozenset({"calm", "playful", "excited", "tense", "supportive", "mixed", "unclear"})
PACES = frozenset({"slow", "steady", "bursty"})
PRESSURES = frozenset({"low", "medium", "high"})
PATTERNS = frozenset({"question_wave", "laughter_wave", "correction_wave", "donation_reaction", "topic_shift", "game_transition", "repetition_wave", "cross_viewer_followup", "unclear"})
OUTCOMES = frozenset({"normal", "epistemic_live_state", "epistemic_agreement", "epistemic_reference", "epistemic_other", "serious_safety", "input_screened"})
EVENT_KINDS = ALLOWED_KINDS
TIMING_BUCKETS = frozenset({"under_1s", "1s_to_5s", "5s_to_15s", "15s_plus"})
SURFACE_SIGNALS = frozenset(SURFACE_SIGNAL_ORDER)
EXPECTED_RUNTIME = {
    "model": "midm-airi:2.0-mini",
    "model_digest": "92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f",
    "model_digest_status": "pinned",
    "num_ctx": 2048,
    "temperature": 0,
    "seed": 42,
    "max_tokens": 128,
    "history_turns": 8,
}
RUNTIME_FIELDS = tuple(EXPECTED_RUNTIME)
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json")
_OPAQUE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_HEX = re.compile(r"[0-9a-f]{64}")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_REPLAY_KEYS = frozenset({
    "schema_version", "event_count", "event_kinds", "timing_buckets",
    "duplicate_count", "noise_count", "delivered_count", "response_count",
    "response_rows", "response_outcome_counts", "outcome_by_surface_signal",
    "surface_signal_counts", "adjacent_event_count",
    "adjacent_signal_pair_counts", "max_events_in_rolling_5s",
    "capture_profile", "flow", "structural_sha256", "runtime_profile",
    "source_evidence", "run_binding_sha256", "report_hmac_sha256",
})
_SCORE_KEYS = frozenset({
    "schema_version", "capture_profile", "source_observation",
    "runtime_profile", "source_evidence", "run_binding_sha256", "row_count",
    "reviewed_response_count", "replay_selector", "response_quality",
    "critical_failure_count", "critical_failure_counts",
    "source_label_hmac_sha256", "source_structural_sha256",
    "structural_sha256", "score_hmac_sha256",
})


class CampaignFormatError(ValueError):
    """A campaign artifact does not satisfy the paired-study contract."""


def _read(path: Path, parent: Path) -> dict[str, Any]:
    if not _secure_inside(path, parent):
        raise CampaignFormatError("artifact escaped its permitted local directory")
    try:
        raw = path.read_bytes()
        if not 1 <= len(raw) <= MAX_ARTIFACT_BYTES:
            raise CampaignFormatError("artifact size is outside the limit")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignFormatError("artifact is unreadable") from exc
    if not isinstance(value, dict):
        raise CampaignFormatError("artifact must be a JSON object")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise CampaignFormatError("attestation timestamp must be UTC Z")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CampaignFormatError("attestation timestamp is invalid") from exc


def _nonnegative(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise CampaignFormatError(f"{label} must be a non-negative integer")
    return value


def _hex(value: object, label: str) -> str:
    if not isinstance(value, str) or _HEX.fullmatch(value) is None:
        raise CampaignFormatError(f"{label} is invalid")
    return value


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _profile(value: object) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"source_slot", "phase"}
        or value.get("source_slot") not in SLOTS
        or value.get("phase") not in PHASES
    ):
        raise CampaignFormatError("capture profile is invalid")
    return value


def _evidence(value: object) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"provider", "source_identity_hmac", "exact_capture_hmac"}
        or value.get("provider") not in PROVIDERS
    ):
        raise CampaignFormatError("source evidence is invalid")
    _hex(value.get("source_identity_hmac"), "source identity HMAC")
    _hex(value.get("exact_capture_hmac"), "exact capture HMAC")
    return value


def _runtime(value: object) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != set(RUNTIME_FIELDS) | {"epistemic_confidence_enabled"}
        or type(value.get("epistemic_confidence_enabled")) is not bool
        or any(value.get(name) != expected for name, expected in EXPECTED_RUNTIME.items())
    ):
        raise CampaignFormatError("runtime is not the frozen Mi:dm replay profile")
    return value


def _int_map(value: object, label: str, *, allowed: frozenset[str] | None = None) -> dict[str, int]:
    if not isinstance(value, dict):
        raise CampaignFormatError(f"{label} is invalid")
    result: dict[str, int] = {}
    for name, count in value.items():
        if not isinstance(name, str) or (allowed is not None and name not in allowed):
            raise CampaignFormatError(f"{label} is invalid")
        result[name] = _nonnegative(count, label)
    return result


def _adjacent_signal_pairs(value: object) -> dict[str, int]:
    result = _int_map(value, "adjacent signal pairs")
    allowed = SURFACE_SIGNALS | {"none"}
    for name in result:
        parts = name.split("->")
        if len(parts) != 2 or any(part not in allowed for part in parts):
            raise CampaignFormatError("adjacent signal pairs are invalid")
    return result


def _outcomes_by_signal(value: object) -> None:
    if not isinstance(value, dict):
        raise CampaignFormatError("outcomes by signal are invalid")
    for signal, counts in value.items():
        if signal not in SURFACE_SIGNALS | {"none"}:
            raise CampaignFormatError("outcomes by signal are invalid")
        _int_map(counts, "outcomes by signal", allowed=OUTCOMES)


def _flow(value: object, event_count: int) -> dict[str, Any]:
    keys = {
        "duration_ms", "gap_p50_ms", "gap_p95_ms", "gap_max_ms",
        "interarrival_rate_per_minute", "active_fixed_5s_bins",
        "rolling_5s_burst_threshold", "rolling_5s_burst_start_count",
        "duplicate_rate", "noise_rate", "eligible_rate",
        "repeat_cluster_count", "max_repeat_cluster_size",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise CampaignFormatError("source flow summary is invalid")
    for name in (
        "duration_ms", "active_fixed_5s_bins", "rolling_5s_burst_start_count",
        "repeat_cluster_count", "max_repeat_cluster_size",
    ):
        _nonnegative(value[name], name)
    if value["rolling_5s_burst_threshold"] != 5:
        raise CampaignFormatError("source flow burst threshold is invalid")
    for name in ("gap_p50_ms", "gap_p95_ms", "gap_max_ms"):
        if value[name] is not None:
            _nonnegative(value[name], name)
    rate = value["interarrival_rate_per_minute"]
    if rate is not None and (type(rate) not in (int, float) or isinstance(rate, bool) or rate < 0):
        raise CampaignFormatError("source interarrival rate is invalid")
    for name in ("duplicate_rate", "noise_rate", "eligible_rate"):
        ratio = value[name]
        if type(ratio) not in (int, float) or isinstance(ratio, bool) or not 0 <= ratio <= 1:
            raise CampaignFormatError("source flow ratio is invalid")
    if event_count == 1 and any(value[name] is not None for name in (
        "gap_p50_ms", "gap_p95_ms", "gap_max_ms", "interarrival_rate_per_minute",
    )):
        raise CampaignFormatError("single-event flow summary is invalid")
    return value


def _source_observation(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "atmosphere", "pace", "context_pressure", "dominant_patterns",
    }:
        raise CampaignFormatError("source observation is invalid")
    patterns = value.get("dominant_patterns")
    if (
        value.get("atmosphere") not in ATMOSPHERES
        or value.get("pace") not in PACES
        or value.get("context_pressure") not in PRESSURES
        or not isinstance(patterns, list)
        or not 1 <= len(patterns) <= 4
        or patterns != sorted(set(patterns))
        or not set(patterns) <= PATTERNS
    ):
        raise CampaignFormatError("source observation is invalid")
    return value


def _validate_replay(report: dict[str, Any], key: bytes) -> dict[str, Any]:
    if set(report) != _REPLAY_KEYS or report.get("schema_version") != REPLAY_SCHEMA:
        raise CampaignFormatError("replay report schema is unsupported")
    _profile(report["capture_profile"])
    _evidence(report["source_evidence"])
    _runtime(report["runtime_profile"])
    _hex(report["structural_sha256"], "source structural hash")
    _hex(report["run_binding_sha256"], "run binding")
    report_hmac = _hex(report["report_hmac_sha256"], "replay report HMAC")
    unsigned = dict(report)
    unsigned.pop("report_hmac_sha256")
    expected_hmac = hmac.new(
        key, REPORT_HMAC_DOMAIN + _canonical(unsigned), hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(report_hmac, expected_hmac):
        raise CampaignFormatError("replay report HMAC is invalid")

    event_count = _nonnegative(report["event_count"], "event count")
    if event_count < 1:
        raise CampaignFormatError("replay report has no events")
    event_kinds = _int_map(report["event_kinds"], "event kinds", allowed=EVENT_KINDS)
    timing = _int_map(report["timing_buckets"], "timing buckets", allowed=TIMING_BUCKETS)
    duplicate_count = _nonnegative(report["duplicate_count"], "duplicate count")
    noise_count = _nonnegative(report["noise_count"], "noise count")
    delivered = _nonnegative(report["delivered_count"], "delivered count")
    response_count = _nonnegative(report["response_count"], "response count")
    adjacent = _nonnegative(report["adjacent_event_count"], "adjacent count")
    rolling_max = _nonnegative(report["max_events_in_rolling_5s"], "rolling maximum")
    if (
        sum(event_kinds.values()) != event_count
        or sum(timing.values()) != event_count
        or any(count > event_count for count in (duplicate_count, noise_count, delivered, response_count, rolling_max))
        or response_count != delivered
        or adjacent != max(event_count - 1, 0)
    ):
        raise CampaignFormatError("replay aggregate counts are inconsistent")

    rows = report["response_rows"]
    if not isinstance(rows, list) or len(rows) != response_count:
        raise CampaignFormatError("replay response rows are invalid")
    seen: set[int] = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"seq", "outcome", "response_char_count", "response_hmac_sha256"}
            or type(row.get("seq")) is not int
            or not 1 <= row["seq"] <= event_count
            or row["seq"] in seen
            or row.get("outcome") not in OUTCOMES
            or type(row.get("response_char_count")) is not int
            or not 1 <= row["response_char_count"] <= 4000
        ):
            raise CampaignFormatError("replay response rows are invalid")
        _hex(row.get("response_hmac_sha256"), "response HMAC")
        seen.add(row["seq"])
    outcome_counts = _int_map(
        report["response_outcome_counts"], "response outcomes", allowed=OUTCOMES,
    )
    if sum(outcome_counts.values()) != response_count:
        raise CampaignFormatError("response outcome counts are inconsistent")
    _outcomes_by_signal(report["outcome_by_surface_signal"])
    _int_map(
        report["surface_signal_counts"], "surface signal counts",
        allowed=SURFACE_SIGNALS,
    )
    _adjacent_signal_pairs(report["adjacent_signal_pair_counts"])
    _flow(report["flow"], event_count)
    run_binding = hashlib.sha256(_canonical({
        "source_structural_sha256": report["structural_sha256"],
        "source_evidence": report["source_evidence"],
        "runtime_profile": report["runtime_profile"],
        "response_rows": rows,
    })).hexdigest()
    if not hmac.compare_digest(run_binding, report["run_binding_sha256"]):
        raise CampaignFormatError("replay run binding is invalid")
    return report


def _validate_rate(value: object, expected: float | None, label: str) -> None:
    if value != expected:
        raise CampaignFormatError(f"{label} is inconsistent")


def _validate_score(score: dict[str, Any], report: dict[str, Any], key: bytes) -> dict[str, Any]:
    if set(score) != _SCORE_KEYS or score.get("schema_version") != SCORE_SCHEMA:
        raise CampaignFormatError("human score schema is unsupported")
    score_hmac = _hex(score["score_hmac_sha256"], "human score HMAC")
    source_label_hmac = _hex(
        score["source_label_hmac_sha256"], "source label HMAC",
    )
    unsigned = dict(score)
    unsigned.pop("score_hmac_sha256")
    expected_hmac = hmac.new(
        key, SCORE_HMAC_DOMAIN + _canonical(unsigned), hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(score_hmac, expected_hmac):
        raise CampaignFormatError("human score HMAC is invalid")
    for name in ("capture_profile", "runtime_profile", "source_evidence", "run_binding_sha256"):
        if score[name] != report[name]:
            raise CampaignFormatError("human score does not bind the replay")
    if score["source_structural_sha256"] != report["structural_sha256"]:
        raise CampaignFormatError("human score source binding is invalid")
    _hex(score["structural_sha256"], "human score structural hash")
    observation = _source_observation(score["source_observation"])
    row_count = _nonnegative(score["row_count"], "review row count")
    reviewed = _nonnegative(score["reviewed_response_count"], "reviewed response count")
    if row_count != report["event_count"] or reviewed != report["response_count"] or reviewed < 1:
        raise CampaignFormatError("human review coverage is incomplete")

    selector = score["replay_selector"]
    selector_keys = {"tp", "fp", "fn", "tn", "precision", "recall", "f1", "noise_delivery_count", "source_repeat_delivery_count"}
    if not isinstance(selector, dict) or set(selector) != selector_keys:
        raise CampaignFormatError("replay selector score is invalid")
    counts = {name: _nonnegative(selector[name], "selector count") for name in ("tp", "fp", "fn", "tn", "noise_delivery_count", "source_repeat_delivery_count")}
    if sum(counts[name] for name in ("tp", "fp", "fn", "tn")) != row_count:
        raise CampaignFormatError("selector counts are inconsistent")
    if (
        counts["tp"] + counts["fp"] != reviewed
        or counts["noise_delivery_count"] > reviewed
        or counts["source_repeat_delivery_count"] > reviewed
    ):
        raise CampaignFormatError("selector delivery counts are inconsistent")
    precision = _ratio(counts["tp"], counts["tp"] + counts["fp"])
    recall = _ratio(counts["tp"], counts["tp"] + counts["fn"])
    f1 = round(2 * precision * recall / (precision + recall), 6) if precision is not None and recall is not None and precision + recall else None
    _validate_rate(selector["precision"], precision, "selector precision")
    _validate_rate(selector["recall"], recall, "selector recall")
    _validate_rate(selector["f1"], f1, "selector F1")

    quality = score["response_quality"]
    if not isinstance(quality, dict) or set(quality) != set(QUALITY_FIELDS):
        raise CampaignFormatError("response quality fields are invalid")
    quality_counts: dict[str, int] = {}
    for name in QUALITY_FIELDS:
        item = quality[name]
        if not isinstance(item, dict) or set(item) != {"pass_count", "pass_rate"}:
            raise CampaignFormatError("response quality entry is invalid")
        count = _nonnegative(item["pass_count"], "quality pass count")
        if count > reviewed:
            raise CampaignFormatError("quality pass count exceeds review count")
        _validate_rate(item["pass_rate"], _ratio(count, reviewed), "quality pass rate")
        quality_counts[name] = count

    critical = score["critical_failure_counts"]
    expected_critical_keys = set(CRITICAL_FIELDS) | {"total_critical_rows"}
    if not isinstance(critical, dict) or set(critical) != expected_critical_keys:
        raise CampaignFormatError("critical failure categories are invalid")
    critical_counts = {name: _nonnegative(critical[name], "critical failure count") for name in CRITICAL_FIELDS}
    total_critical = _nonnegative(critical["total_critical_rows"], "critical row count")
    if (
        score["critical_failure_count"] != total_critical
        or total_critical > reviewed
        or any(count > reviewed for count in critical_counts.values())
        or any(
            critical_counts[name] != reviewed - quality_counts[name]
            for name in CRITICAL_FIELDS
        )
        or total_critical < max(critical_counts.values(), default=0)
        or total_critical > min(reviewed, sum(critical_counts.values()))
    ):
        raise CampaignFormatError("critical failure total is inconsistent")
    return {
        "reviewed": reviewed,
        "row_count": row_count,
        "quality": quality_counts,
        "selector": counts,
        "critical": critical_counts,
        "critical_total": total_critical,
        "source_observation": observation,
        "source_label_hmac_sha256": source_label_hmac,
    }


def validate_campaign_manifest(
    manifest_path: Path,
    identity_key: bytes,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load a complete campaign and return validated, paired run records."""
    manifest = _read(manifest_path, HERE / "private-replays")
    if (
        set(manifest) != {"schema_version", "local_only", "campaign_id", "operator_attestation", "runs"}
        or manifest.get("schema_version") != MANIFEST_SCHEMA
        or manifest.get("local_only") is not True
        or not isinstance(manifest.get("campaign_id"), str)
        or _OPAQUE_ID.fullmatch(manifest["campaign_id"]) is None
    ):
        raise CampaignFormatError("campaign manifest is invalid")
    attestation = manifest["operator_attestation"]
    attestation_keys = {"permission_scope_verified", "privacy_review_completed", "retention_and_revocation_checked", "exclusive_local_model_session", "reviewed_at", "valid_until", "reviewer_role"}
    if (
        not isinstance(attestation, dict)
        or set(attestation) != attestation_keys
        or any(attestation[name] is not True for name in (
            "permission_scope_verified", "privacy_review_completed",
            "retention_and_revocation_checked", "exclusive_local_model_session",
        ))
        or attestation.get("reviewer_role") not in {"operator", "authorized_reviewer"}
    ):
        raise CampaignFormatError("operator attestation is invalid")
    reviewed_at = _timestamp(attestation["reviewed_at"])
    valid_until = _timestamp(attestation["valid_until"])
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise CampaignFormatError("current time must be timezone-aware")
    current = current.astimezone(timezone.utc)
    if (
        reviewed_at > current
        or current >= valid_until
        or valid_until <= reviewed_at
        or valid_until - reviewed_at > timedelta(hours=24)
    ):
        raise CampaignFormatError("operator attestation is stale or invalid")

    entries = manifest["runs"]
    if not isinstance(entries, list) or not 12 <= len(entries) <= 32:
        raise CampaignFormatError("campaign must contain 12 to 32 runs")
    artifact_paths: set[str] = set()
    pair_gates: set[tuple[str, str]] = set()
    slot_identities: dict[str, tuple[str, str]] = {}
    baseline: dict[str, Any] | None = None
    records: list[dict[str, Any]] = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"pair_id", "gate", "replay_report", "human_score_report"}
            or not isinstance(entry.get("pair_id"), str)
            or _OPAQUE_ID.fullmatch(entry["pair_id"]) is None
            or entry.get("gate") not in GATES
            or any(
                not isinstance(entry.get(name), str)
                or _BASENAME.fullmatch(entry[name]) is None
                for name in ("replay_report", "human_score_report")
            )
        ):
            raise CampaignFormatError("campaign run entry is invalid")
        paths = tuple(
            str((HERE / "reports" / entry[name]).resolve(strict=False)).casefold()
            for name in ("replay_report", "human_score_report")
        )
        if any(path in artifact_paths for path in paths):
            raise CampaignFormatError("campaign artifact path is duplicated")
        artifact_paths.update(paths)
        pair_gate = (entry["pair_id"], entry["gate"])
        if pair_gate in pair_gates:
            raise CampaignFormatError("campaign pair arm is duplicated")
        pair_gates.add(pair_gate)

        report = _validate_replay(
            _read(HERE / "reports" / entry["replay_report"], HERE / "reports"),
            identity_key,
        )
        score = _validate_score(
            _read(HERE / "reports" / entry["human_score_report"], HERE / "reports"),
            report,
            identity_key,
        )
        runtime = report["runtime_profile"]
        if runtime["epistemic_confidence_enabled"] is not (entry["gate"] == "on"):
            raise CampaignFormatError("manifest gate does not match attested runtime")
        common_runtime = {name: runtime[name] for name in RUNTIME_FIELDS}
        if baseline is None:
            baseline = common_runtime
        elif common_runtime != baseline:
            raise CampaignFormatError("campaign runtime profile drifted")
        profile = report["capture_profile"]
        evidence = report["source_evidence"]
        source_identity = (evidence["provider"], evidence["source_identity_hmac"])
        existing = slot_identities.setdefault(profile["source_slot"], source_identity)
        if existing != source_identity:
            raise CampaignFormatError("anonymous source slot changed identity")
        records.append({"entry": entry, "report": report, "score": score})

    if set(slot_identities) != set(SLOTS) or len(set(slot_identities.values())) != len(SLOTS):
        raise CampaignFormatError("three distinct anonymous source slots are required")
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        pairs[record["entry"]["pair_id"]].append(record)
    exact_captures: set[str] = set()
    phases: dict[str, set[str]] = defaultdict(set)
    source_fields = (
        "capture_profile", "structural_sha256", "source_evidence", "event_count",
        "event_kinds", "timing_buckets", "duplicate_count", "noise_count",
        "delivered_count", "response_count", "surface_signal_counts",
        "adjacent_event_count", "adjacent_signal_pair_counts",
        "max_events_in_rolling_5s", "flow",
    )
    for pair in pairs.values():
        if len(pair) != 2 or {record["entry"]["gate"] for record in pair} != set(GATES):
            raise CampaignFormatError("each capture needs exactly one OFF and one ON run")
        left, right = pair
        if any(left["report"][name] != right["report"][name] for name in source_fields):
            raise CampaignFormatError("paired runs do not use the same exact source")
        if left["score"]["source_observation"] != right["score"]["source_observation"]:
            raise CampaignFormatError("paired source observation changed")
        left_selector, right_selector = left["score"]["selector"], right["score"]["selector"]
        if (
            left["score"]["source_label_hmac_sha256"]
            != right["score"]["source_label_hmac_sha256"]
            or
            left["score"]["row_count"] != right["score"]["row_count"]
            or left_selector["tp"] + left_selector["fn"] != right_selector["tp"] + right_selector["fn"]
            or left_selector["fp"] + left_selector["tn"] != right_selector["fp"] + right_selector["tn"]
        ):
            raise CampaignFormatError("paired human source labels changed")
        exact_capture = left["report"]["source_evidence"]["exact_capture_hmac"]
        if exact_capture in exact_captures:
            raise CampaignFormatError("exact capture was reused under another pair")
        exact_captures.add(exact_capture)
        profile = left["report"]["capture_profile"]
        phases[profile["source_slot"]].add(profile["phase"])
    if any(len(phases[slot]) < 2 for slot in SLOTS):
        raise CampaignFormatError("each source slot needs at least two distinct phases")
    return manifest, records


def aggregate_campaign(
    manifest_path: Path,
    output_path: Path,
    identity_key_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not _secure_inside(identity_key_path, HERE / "local-replay-intake"):
        raise CampaignFormatError("identity key escaped local replay custody")
    identity_key = read_identity_key(identity_key_path)
    _, records = validate_campaign_manifest(manifest_path, identity_key, now=now)
    if (
        not _secure_inside(output_path, HERE / "reports")
        or _BASENAME.fullmatch(output_path.name) is None
    ):
        raise CampaignFormatError("output must be a JSON basename under reports")
    referenced_paths = {
        str((HERE / "reports" / record["entry"][name]).resolve(strict=False)).casefold()
        for record in records
        for name in ("replay_report", "human_score_report")
    }
    if str(output_path.resolve(strict=False)).casefold() in referenced_paths:
        raise CampaignFormatError("campaign output must not overwrite evidence")

    arm_state = {
        gate: {
            "reviewed": 0,
            "responses": 0,
            "quality": Counter(),
            "selector": Counter(),
            "outcomes": Counter(),
            "critical": Counter(),
            "critical_total": 0,
        }
        for gate in GATES
    }
    source_state = {
        "capture_count": 0,
        "event_count": 0,
        "noise_count": 0,
        "duplicate_count": 0,
        "duration_ms": 0,
        "interarrival_count": 0,
        "rolling_5s_burst_start_count": 0,
        "max_events_in_rolling_5s": 0,
        "event_kinds": Counter(),
        "timing_buckets": Counter(),
        "surface_signals": Counter(),
        "atmospheres": Counter(),
        "paces": Counter(),
        "context_pressures": Counter(),
        "dominant_patterns": Counter(),
    }
    seen_pairs: set[str] = set()
    phases: dict[str, set[str]] = defaultdict(set)
    for record in records:
        gate = record["entry"]["gate"]
        report = record["report"]
        score = record["score"]
        arm = arm_state[gate]
        arm["reviewed"] += score["reviewed"]
        arm["responses"] += report["response_count"]
        arm["quality"].update(score["quality"])
        arm["selector"].update(score["selector"])
        arm["outcomes"].update(report["response_outcome_counts"])
        arm["critical"].update(score["critical"])
        arm["critical_total"] += score["critical_total"]

        pair_id = record["entry"]["pair_id"]
        if pair_id in seen_pairs:
            continue
        seen_pairs.add(pair_id)
        source_state["capture_count"] += 1
        source_state["event_count"] += report["event_count"]
        source_state["noise_count"] += report["noise_count"]
        source_state["duplicate_count"] += report["duplicate_count"]
        source_state["interarrival_count"] += max(report["event_count"] - 1, 0)
        source_state["event_kinds"].update(report["event_kinds"])
        source_state["timing_buckets"].update(report["timing_buckets"])
        source_state["surface_signals"].update(report["surface_signal_counts"])
        flow = report["flow"]
        duration = flow.get("duration_ms")
        bursts = flow.get("rolling_5s_burst_start_count")
        if type(duration) is not int or duration < 0 or type(bursts) is not int or bursts < 0:
            raise CampaignFormatError("source flow summary is invalid")
        source_state["duration_ms"] += duration
        source_state["rolling_5s_burst_start_count"] += bursts
        source_state["max_events_in_rolling_5s"] = max(
            source_state["max_events_in_rolling_5s"],
            report["max_events_in_rolling_5s"],
        )
        observation = score["source_observation"]
        source_state["atmospheres"][observation["atmosphere"]] += 1
        source_state["paces"][observation["pace"]] += 1
        source_state["context_pressures"][observation["context_pressure"]] += 1
        source_state["dominant_patterns"].update(observation["dominant_patterns"])
        profile = report["capture_profile"]
        phases[profile["source_slot"]].add(profile["phase"])

    arms: dict[str, Any] = {}
    for gate, state in arm_state.items():
        reviewed = state["reviewed"]
        tp, fp = state["selector"]["tp"], state["selector"]["fp"]
        fn = state["selector"]["fn"]
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        f1 = round(2 * precision * recall / (precision + recall), 6) if precision is not None and recall is not None and precision + recall else None
        outcome_total = sum(state["outcomes"].values())
        epistemic_count = sum(count for name, count in state["outcomes"].items() if name.startswith("epistemic_"))
        arms[gate] = {
            "reviewed_response_count": reviewed,
            "response_count": state["responses"],
            "response_quality": {
                name: {
                    "pass_count": state["quality"][name],
                    "pass_rate": _ratio(state["quality"][name], reviewed),
                }
                for name in QUALITY_FIELDS
            },
            "replay_selector": {
                **{name: state["selector"][name] for name in ("tp", "fp", "fn", "tn", "noise_delivery_count", "source_repeat_delivery_count")},
                "precision": precision,
                "recall": recall,
                "f1": f1,
            },
            "response_outcome_counts": dict(sorted(state["outcomes"].items())),
            "epistemic_outcome_rate": _ratio(epistemic_count, outcome_total),
            "critical_failure_counts": dict(sorted(state["critical"].items())),
            "critical_failure_count": state["critical_total"],
        }

    total_events = source_state["event_count"]
    total_duration = source_state["duration_ms"]
    source_patterns = {
        "capture_count": source_state["capture_count"],
        "event_count": total_events,
        "event_kind_counts": dict(sorted(source_state["event_kinds"].items())),
        "timing_bucket_counts": dict(sorted(source_state["timing_buckets"].items())),
        "noise_count": source_state["noise_count"],
        "noise_rate": _ratio(source_state["noise_count"], total_events),
        "duplicate_count": source_state["duplicate_count"],
        "duplicate_rate": _ratio(source_state["duplicate_count"], total_events),
        "duration_ms_total": total_duration,
        "interarrival_rate_per_minute": _ratio(
            source_state["interarrival_count"] * 60_000,
            total_duration,
        ),
        "rolling_5s_burst_start_count": source_state["rolling_5s_burst_start_count"],
        "max_events_in_rolling_5s": source_state["max_events_in_rolling_5s"],
        "surface_signal_counts": dict(sorted(source_state["surface_signals"].items())),
        "atmosphere_counts": dict(sorted(source_state["atmospheres"].items())),
        "pace_counts": dict(sorted(source_state["paces"].items())),
        "context_pressure_counts": dict(sorted(source_state["context_pressures"].items())),
        "dominant_pattern_counts": dict(sorted(source_state["dominant_patterns"].items())),
    }
    output = {
        "schema_version": CAMPAIGN_SCHEMA,
        "local_only": True,
        "coverage": {
            "pair_count": len(seen_pairs),
            "run_count": len(records),
            "anonymous_slot_phase_sets": {
                f"slot_{index + 1}": sorted(phases[slot])
                for index, slot in enumerate(SLOTS)
            },
        },
        "frozen_runtime_profile": {
            name: value for name, value in EXPECTED_RUNTIME.items()
            if name != "model_digest"
        },
        "source_pattern_aggregates": source_patterns,
        "arms": arms,
        "on_minus_off": {
            "quality_rate_deltas": {
                name: round(
                    arms["on"]["response_quality"][name]["pass_rate"]
                    - arms["off"]["response_quality"][name]["pass_rate"],
                    6,
                )
                for name in QUALITY_FIELDS
            },
            "epistemic_outcome_rate_delta": round(
                arms["on"]["epistemic_outcome_rate"]
                - arms["off"]["epistemic_outcome_rate"],
                6,
            ),
            "critical_failure_count_delta": (
                arms["on"]["critical_failure_count"]
                - arms["off"]["critical_failure_count"]
            ),
        },
        "campaign_critical_gate": "fail" if any(
            arms[gate]["critical_failure_count"] for gate in GATES
        ) else "pass",
        "automatic_adoption": False,
        "user_confirmation_required": True,
    }
    write_atomic_json(output_path, output, HERE / "reports")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate a local paired replay campaign")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--identity-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    aggregate_campaign(args.manifest, args.output, args.identity_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
