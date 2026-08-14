#!/usr/bin/env python3
"""Score an ignored human review packet without copying its text to reports."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Any

from chat_replay import ALLOWED_KINDS, CAPTURE_PHASES, SOURCE_SLOTS, SURFACE_SIGNAL_ORDER, _canonical, _surface_signals
from normalize_authorized_export import read_identity_key
from replay_local_io import _secure_inside, write_atomic_json

HERE = Path(__file__).resolve().parent
PACKET_SCHEMA = "airi.chat-replay-private-review.v3"
REPORT_SCHEMA = "airi.chat-replay-human-score.v2"
MAX_PACKET_BYTES = 32 * 1024 * 1024
MAX_REPLAY_REPORT_BYTES = 32 * 1024 * 1024
REPORT_HMAC_DOMAIN = b"airi.chat-replay-report.v1\0"
SCORE_HMAC_DOMAIN = b"airi.chat-replay-human-score.v1\0"
SOURCE_LABEL_HMAC_DOMAIN = b"airi.chat-replay-source-labels.v1\0"
_PACKET_KEYS = frozenset({"schema_version", "local_only", "capture_profile", "source_structural_sha256", "source_evidence", "runtime_profile", "run_binding_sha256", "report_hmac_sha256", "source_review", "rows"})
_ROW_KEYS = frozenset({"seq", "offset_ms", "timing_bucket", "event_kind", "duplicate_of_seq", "surface_signals", "selection_eligible", "delivered", "input", "response", "outcome", "response_char_count", "response_hmac_sha256", "review"})
_REVIEW_KEYS = frozenset({"expected_action", "grounded", "context_preserved", "tone_ok", "privacy_ok", "current_fact_ok", "reference_grounding_ok", "agreement_calibration_ok"})
_QUALITY_FIELDS = (
    "grounded", "context_preserved", "tone_ok", "privacy_ok",
    "current_fact_ok", "reference_grounding_ok", "agreement_calibration_ok",
)
_CRITICAL_FIELDS = ("privacy_ok", "current_fact_ok", "reference_grounding_ok", "agreement_calibration_ok")
_TIMING_BUCKETS = frozenset({"under_1s", "1s_to_5s", "5s_to_15s", "15s_plus"})
_ATMOSPHERES = frozenset({"calm", "playful", "excited", "tense", "supportive", "mixed", "unclear"})
_PACES = frozenset({"slow", "steady", "bursty"})
_PRESSURES = frozenset({"low", "medium", "high"})
_PATTERNS = frozenset({"question_wave", "laughter_wave", "correction_wave", "donation_reaction", "topic_shift", "game_transition", "repetition_wave", "cross_viewer_followup", "unclear"})

class PrivateReviewError(ValueError):
    """The private packet is incomplete or outside the scorer contract."""

def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 6) if b else None

def _load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if not 1 <= len(raw) <= MAX_PACKET_BYTES:
            raise PrivateReviewError("private review packet size is outside the limit")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrivateReviewError("private review packet is unreadable") from exc
    if not isinstance(value, dict) or set(value) != _PACKET_KEYS or value.get("schema_version") != PACKET_SCHEMA or value.get("local_only") is not True or not isinstance(value.get("rows"), list) or not 1 <= len(value["rows"]) <= 20_000:
        raise PrivateReviewError("private review packet has unsupported fields")
    if any(
        not isinstance(value.get(name), str)
        or re.fullmatch(r"[0-9a-f]{64}", value[name]) is None
        for name in (
            "source_structural_sha256", "run_binding_sha256",
            "report_hmac_sha256",
        )
    ):
        raise PrivateReviewError("private review binding is invalid")
    profile = value.get("capture_profile")
    evidence = value.get("source_evidence")
    if not isinstance(profile, dict) or set(profile) != {"source_slot", "phase"} or profile.get("source_slot") not in SOURCE_SLOTS or profile.get("phase") not in CAPTURE_PHASES or not isinstance(evidence, dict) or set(evidence) != {"provider", "source_identity_hmac", "exact_capture_hmac"} or not all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for k, v in evidence.items() if k != "provider") or not isinstance(evidence.get("provider"), str) or not isinstance(value.get("runtime_profile"), dict):
        raise PrivateReviewError("private review provenance is invalid")
    review = value.get("source_review")
    if not isinstance(review, dict) or set(review) != {"atmosphere", "pace", "context_pressure", "dominant_patterns"} or review.get("atmosphere") not in _ATMOSPHERES or review.get("pace") not in _PACES or review.get("context_pressure") not in _PRESSURES or not isinstance(review.get("dominant_patterns"), list) or not 1 <= len(review["dominant_patterns"]) <= 4 or review["dominant_patterns"] != sorted(set(review["dominant_patterns"])) or not set(review["dominant_patterns"]) <= _PATTERNS:
        raise PrivateReviewError("source review is invalid or incomplete")
    return value

def _load_report(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if not 1 <= len(raw) <= MAX_REPLAY_REPORT_BYTES:
            raise PrivateReviewError("replay report size is outside the limit")
        report = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrivateReviewError("replay report is unreadable") from exc
    if not isinstance(report, dict):
        raise PrivateReviewError("replay report is invalid")
    source_evidence = report.get("source_evidence")
    runtime = report.get("runtime_profile")
    if (
        report.get("schema_version") != "airi.chat-replay-report.v2"
        or not isinstance(report.get("response_rows"), list)
        or not isinstance(report.get("structural_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", report["structural_sha256"]) is None
        or not isinstance(report.get("run_binding_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", report["run_binding_sha256"]) is None
        or not isinstance(report.get("report_hmac_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", report["report_hmac_sha256"]) is None
        or not isinstance(source_evidence, dict)
        or set(source_evidence) != {"provider", "source_identity_hmac", "exact_capture_hmac"}
        or not isinstance(source_evidence.get("provider"), str)
        or any(
            not isinstance(source_evidence.get(name), str)
            or re.fullmatch(r"[0-9a-f]{64}", source_evidence[name]) is None
            for name in ("source_identity_hmac", "exact_capture_hmac")
        )
        or not isinstance(runtime, dict)
        or type(runtime.get("history_turns")) is not int
        or not 1 <= runtime["history_turns"] <= 32
    ):
        raise PrivateReviewError("replay report is invalid")
    return report

def score_private_review(path: Path, replay_report_path: Path, identity_key_path: Path) -> dict[str, Any]:
    packet, replay = _load(path), _load_report(replay_report_path)
    key = read_identity_key(identity_key_path)
    unsigned_replay = dict(replay)
    replay_hmac = unsigned_replay.pop("report_hmac_sha256")
    expected_replay_hmac = hmac.new(
        key, REPORT_HMAC_DOMAIN + _canonical(unsigned_replay), hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(replay_hmac, expected_replay_hmac):
        raise PrivateReviewError("replay report HMAC is invalid")
    if (
        replay.get("structural_sha256") != packet["source_structural_sha256"]
        or replay.get("source_evidence") != packet["source_evidence"]
        or replay.get("runtime_profile") != packet["runtime_profile"]
        or replay.get("run_binding_sha256") != packet["run_binding_sha256"]
        or replay_hmac != packet["report_hmac_sha256"]
    ):
        raise PrivateReviewError("private review does not match replay report")
    binding = hashlib.sha256(_canonical({"source_structural_sha256": replay["structural_sha256"], "source_evidence": replay["source_evidence"], "runtime_profile": replay["runtime_profile"], "response_rows": replay["response_rows"]})).hexdigest()
    if not hmac.compare_digest(binding, packet["run_binding_sha256"]):
        raise PrivateReviewError("replay binding hash is invalid")
    report_rows: dict[int, dict[str, Any]] = {}
    for item in replay["response_rows"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"seq", "outcome", "response_char_count", "response_hmac_sha256"}
            or type(item.get("seq")) is not int
            or item["seq"] < 1
            or not isinstance(item.get("outcome"), str)
            or type(item.get("response_char_count")) is not int
            or item["response_char_count"] < 1
            or not isinstance(item.get("response_hmac_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", item["response_hmac_sha256"]) is None
            or item["seq"] in report_rows
        ):
            raise PrivateReviewError("replay response rows are invalid or duplicated")
        report_rows[item["seq"]] = item
    confusion, passes, critical = Counter(), Counter(), Counter()
    reviewed = noise = repeats = 0
    source_rows, structural_rows, source_labels = [], [], []
    for seq, row in enumerate(packet["rows"], 1):
        if not isinstance(row, dict) or set(row) != _ROW_KEYS or row.get("seq") != seq or type(row.get("offset_ms")) is not int or row["offset_ms"] < 0 or row.get("timing_bucket") not in _TIMING_BUCKETS or row.get("event_kind") not in ALLOWED_KINDS or type(row.get("selection_eligible")) is not bool or type(row.get("delivered")) is not bool or not isinstance(row.get("input"), str) or not 1 <= len(row["input"]) <= 1000 or not isinstance(row.get("surface_signals"), list) or not isinstance(row.get("review"), dict) or set(row["review"]) != _REVIEW_KEYS:
            raise PrivateReviewError("private review row has unsupported fields")
        dup, signals, review = row["duplicate_of_seq"], row["surface_signals"], row["review"]
        if (dup is not None and (type(dup) is not int or not 1 <= dup < seq)) or len(signals) != len(set(signals)) or any(x not in SURFACE_SIGNAL_ORDER for x in signals) or tuple(signals) != _surface_signals(row["input"], row["event_kind"], duplicate=dup is not None) or row["selection_eligible"] is not (row["event_kind"] != "system_noise" and dup is None) or review.get("expected_action") not in {"respond", "ignore"}:
            raise PrivateReviewError("private review row is inconsistent")
        if row["delivered"]:
            response = row.get("response")
            expected = report_rows.pop(seq, None)
            digest = hmac.new(key, b"airi.chat-replay-response.v1\0" + str(seq).encode("ascii") + b"\0" + (response.encode("utf-8") if isinstance(response, str) else b""), hashlib.sha256).hexdigest()
            if not isinstance(response, str) or not response or len(response) > 4000 or not isinstance(row.get("outcome"), str) or row.get("response_char_count") != len(response) or not isinstance(row.get("response_hmac_sha256"), str) or expected != {"seq": seq, "outcome": row["outcome"], "response_char_count": len(response), "response_hmac_sha256": digest} or not hmac.compare_digest(row["response_hmac_sha256"], digest) or any(type(review[x]) is not bool for x in _QUALITY_FIELDS):
                raise PrivateReviewError("delivered response does not bind replay report")
            reviewed += 1
            for field in _QUALITY_FIELDS: passes[field] += review[field]
            for field in _CRITICAL_FIELDS: critical[field] += review[field] is False
            noise += row["event_kind"] == "system_noise"; repeats += "source_text_repeat" in signals
        elif row.get("response") is not None or row.get("outcome") is not None or row.get("response_char_count") is not None or row.get("response_hmac_sha256") is not None or any(review[x] is not None for x in _QUALITY_FIELDS):
            raise PrivateReviewError("undelivered rows cannot carry response data")
        confusion["tp" if review["expected_action"] == "respond" and row["delivered"] else "fn" if review["expected_action"] == "respond" else "fp" if row["delivered"] else "tn"] += 1
        source_rows.append({k: row[k] for k in ("seq", "offset_ms", "timing_bucket", "event_kind", "duplicate_of_seq", "selection_eligible", "surface_signals")})
        structural_rows.append({"seq": seq, "event_kind": row["event_kind"], "surface_signals": signals, "selection_eligible": row["selection_eligible"], "delivered": row["delivered"], "review": review})
        source_labels.append({
            "seq": seq,
            "expected_action": review["expected_action"],
        })
    if report_rows or hashlib.sha256(_canonical({"capture_profile": packet["capture_profile"], "events": source_rows})).hexdigest() != packet["source_structural_sha256"]:
        raise PrivateReviewError("packet source structure or response sequence is invalid")
    precision = _ratio(confusion["tp"], confusion["tp"] + confusion["fp"])
    recall = _ratio(confusion["tp"], confusion["tp"] + confusion["fn"])
    total_critical_rows = sum(
        any(row["review"][field] is False for field in _CRITICAL_FIELDS)
        for row in packet["rows"] if row["delivered"]
    )
    critical_failure_counts = {
        **{field: critical[field] for field in _CRITICAL_FIELDS},
        "total_critical_rows": total_critical_rows,
    }
    structural_sha256 = hashlib.sha256(_canonical({
        "capture_profile": packet["capture_profile"],
        "source_observation": packet["source_review"],
        "runtime_profile": packet["runtime_profile"],
        "source_evidence": packet["source_evidence"],
        "source_structural_sha256": packet["source_structural_sha256"],
        "run_binding_sha256": packet["run_binding_sha256"],
        "rows": structural_rows,
    })).hexdigest()
    source_label_hmac_sha256 = hmac.new(
        key,
        SOURCE_LABEL_HMAC_DOMAIN + _canonical({
            "source_structural_sha256": packet["source_structural_sha256"],
            "labels": source_labels,
        }),
        hashlib.sha256,
    ).hexdigest()
    result = {
        "schema_version": REPORT_SCHEMA,
        "capture_profile": packet["capture_profile"],
        "source_observation": packet["source_review"],
        "runtime_profile": packet["runtime_profile"],
        "source_evidence": packet["source_evidence"],
        "run_binding_sha256": packet["run_binding_sha256"],
        "row_count": len(packet["rows"]),
        "reviewed_response_count": reviewed,
        "replay_selector": {
            "tp": confusion["tp"], "fp": confusion["fp"],
            "fn": confusion["fn"], "tn": confusion["tn"],
            "precision": precision, "recall": recall,
            "f1": round(2 * precision * recall / (precision + recall), 6)
            if precision is not None and recall is not None and precision + recall else None,
            "noise_delivery_count": noise,
            "source_repeat_delivery_count": repeats,
        },
        "response_quality": {
            field: {"pass_count": passes[field], "pass_rate": _ratio(passes[field], reviewed)}
            for field in _QUALITY_FIELDS
        },
        "critical_failure_count": total_critical_rows,
        "critical_failure_counts": critical_failure_counts,
        "source_label_hmac_sha256": source_label_hmac_sha256,
        "source_structural_sha256": packet["source_structural_sha256"],
        "structural_sha256": structural_sha256,
    }
    result["score_hmac_sha256"] = hmac.new(
        key,
        SCORE_HMAC_DOMAIN + _canonical(result),
        hashlib.sha256,
    ).hexdigest()
    return result

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--replay-report", required=True, type=Path)
    parser.add_argument("--identity-key", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (
        not _secure_inside(args.input, HERE / "private-replays")
        or not _secure_inside(args.replay_report, HERE / "reports")
        or not _secure_inside(args.identity_key, HERE / "local-replay-intake")
        or not _secure_inside(args.report, HERE / "reports")
    ):
        raise SystemExit("review paths must remain in local replay directories")
    if str(args.report.resolve()).casefold() == str(args.replay_report.resolve()).casefold():
        raise SystemExit("--report must not overwrite --replay-report")
    write_atomic_json(
        args.report,
        score_private_review(args.input, args.replay_report, args.identity_key),
        HERE / "reports",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
