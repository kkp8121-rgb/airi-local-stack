#!/usr/bin/env python3
"""Score an ignored human review packet without copying its text to reports."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from chat_replay import (
    ALLOWED_KINDS, CAPTURE_PHASES, SOURCE_SLOTS, SURFACE_SIGNAL_ORDER,
    _canonical, _surface_signals,
)
from replay_local_io import _secure_inside, write_atomic_json


HERE = Path(__file__).resolve().parent
PACKET_SCHEMA = "airi.chat-replay-private-review.v2"
REPORT_SCHEMA = "airi.chat-replay-human-score.v1"
MAX_PACKET_BYTES = 32 * 1024 * 1024
_PACKET_KEYS = frozenset({
    "schema_version", "local_only", "capture_profile",
    "source_structural_sha256", "rows",
})
_ROW_KEYS = frozenset({
    "seq", "offset_ms", "timing_bucket", "event_kind", "duplicate_of_seq",
    "surface_signals",
    "selection_eligible", "delivered", "input", "response", "review",
})
_REVIEW_KEYS = frozenset({
    "expected_action", "grounded", "context_preserved", "tone_ok",
    "privacy_ok", "epistemic_ok",
})
_QUALITY_FIELDS = (
    "grounded", "context_preserved", "tone_ok", "privacy_ok", "epistemic_ok",
)
_TIMING_BUCKETS = frozenset({"under_1s", "1s_to_5s", "5s_to_15s", "15s_plus"})


class PrivateReviewError(ValueError):
    """The private packet is incomplete or outside the scorer contract."""


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if not 1 <= len(raw) <= MAX_PACKET_BYTES:
            raise PrivateReviewError("private review packet size is outside the limit")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrivateReviewError("private review packet is unreadable") from exc
    if (
        not isinstance(value, dict)
        or set(value) != _PACKET_KEYS
        or value.get("schema_version") != PACKET_SCHEMA
        or value.get("local_only") is not True
        or not isinstance(value.get("source_structural_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["source_structural_sha256"]) is None
        or not isinstance(value.get("rows"), list)
        or not 1 <= len(value["rows"]) <= 20_000
    ):
        raise PrivateReviewError("private review packet has unsupported fields")
    profile = value.get("capture_profile")
    if (
        not isinstance(profile, dict)
        or set(profile) != {"source_slot", "phase"}
        or profile.get("source_slot") not in SOURCE_SLOTS
        or profile.get("phase") not in CAPTURE_PHASES
    ):
        raise PrivateReviewError("private review capture profile is invalid")
    return value


def score_private_review(path: Path) -> dict[str, Any]:
    packet = _load(path)
    confusion = Counter()
    quality_passes = Counter()
    reviewed_responses = 0
    noise_deliveries = 0
    repeat_deliveries = 0
    source_structural_rows: list[dict[str, Any]] = []
    structural_rows: list[dict[str, Any]] = []
    for expected_seq, row in enumerate(packet["rows"], 1):
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise PrivateReviewError("private review row has unsupported fields")
        signals = row.get("surface_signals")
        review = row.get("review")
        if (
            row.get("seq") != expected_seq
            or type(row.get("offset_ms")) is not int
            or row["offset_ms"] < 0
            or row.get("timing_bucket") not in _TIMING_BUCKETS
            or type(row.get("selection_eligible")) is not bool
            or type(row.get("delivered")) is not bool
            or row.get("event_kind") not in ALLOWED_KINDS
            or not isinstance(row.get("input"), str)
            or not 1 <= len(row["input"]) <= 1_000
            or not isinstance(signals, list)
            or len(signals) != len(set(signals))
            or any(signal not in SURFACE_SIGNAL_ORDER for signal in signals)
            or not isinstance(review, dict)
            or set(review) != _REVIEW_KEYS
            or review.get("expected_action") not in {"respond", "ignore"}
        ):
            raise PrivateReviewError("private review row is invalid or incomplete")
        duplicate_of_seq = row.get("duplicate_of_seq")
        if duplicate_of_seq is not None and (
            type(duplicate_of_seq) is not int
            or not 1 <= duplicate_of_seq < expected_seq
        ):
            raise PrivateReviewError("private review duplicate relation is invalid")
        if row["selection_eligible"] is not (
            row["event_kind"] != "system_noise" and duplicate_of_seq is None
        ):
            raise PrivateReviewError("private review selector structure is inconsistent")
        expected_signals = _surface_signals(
            row["input"], row["event_kind"], duplicate=duplicate_of_seq is not None,
        )
        if tuple(signals) != expected_signals:
            raise PrivateReviewError("private review surface signals are inconsistent")
        response = row.get("response")
        if row["delivered"]:
            if not isinstance(response, str) or not response or len(response) > 4_000:
                raise PrivateReviewError("delivered review rows require bounded response text")
            if any(type(review[field]) is not bool for field in _QUALITY_FIELDS):
                raise PrivateReviewError("delivered review rows require all quality judgments")
            reviewed_responses += 1
            for field in _QUALITY_FIELDS:
                quality_passes[field] += review[field]
        elif response is not None or any(review[field] is not None for field in _QUALITY_FIELDS):
            raise PrivateReviewError("undelivered review rows cannot contain response judgments")

        expected_respond = review["expected_action"] == "respond"
        predicted_respond = row["delivered"]
        confusion[
            "tp" if expected_respond and predicted_respond
            else "fn" if expected_respond
            else "fp" if predicted_respond
            else "tn"
        ] += 1
        if predicted_respond and row.get("event_kind") == "system_noise":
            noise_deliveries += 1
        if predicted_respond and "source_text_repeat" in signals:
            repeat_deliveries += 1
        source_structural_rows.append({
            "seq": expected_seq,
            "offset_ms": row["offset_ms"],
            "timing_bucket": row["timing_bucket"],
            "event_kind": row["event_kind"],
            "duplicate_of_seq": duplicate_of_seq,
            "selection_eligible": row["selection_eligible"],
            "surface_signals": signals,
        })
        structural_rows.append({
            "seq": expected_seq,
            "event_kind": row.get("event_kind"),
            "surface_signals": signals,
            "selection_eligible": row["selection_eligible"],
            "delivered": predicted_respond,
            "review": review,
        })

    actual_source_hash = hashlib.sha256(_canonical({
        "capture_profile": packet["capture_profile"],
        "events": source_structural_rows,
    })).hexdigest()
    if actual_source_hash != packet["source_structural_sha256"]:
        raise PrivateReviewError("private review packet does not bind its source report")

    tp, fp, fn = confusion["tp"], confusion["fp"], confusion["fn"]
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = (
        round(2 * precision * recall / (precision + recall), 6)
        if precision is not None and recall is not None and precision + recall else None
    )
    quality = {
        field: {
            "pass_count": quality_passes[field],
            "pass_rate": _ratio(quality_passes[field], reviewed_responses),
        }
        for field in _QUALITY_FIELDS
    }
    return {
        "schema_version": REPORT_SCHEMA,
        "capture_profile": packet["capture_profile"],
        "row_count": len(packet["rows"]),
        "reviewed_response_count": reviewed_responses,
        "replay_selector": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": confusion["tn"],
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "noise_delivery_count": noise_deliveries,
            "source_repeat_delivery_count": repeat_deliveries,
        },
        "response_quality": quality,
        "critical_failure_count": sum(
            1 for row in packet["rows"]
            if row["delivered"] and (
                row["review"]["privacy_ok"] is False
                or row["review"]["epistemic_ok"] is False
            )
        ),
        "source_structural_sha256": packet["source_structural_sha256"],
        "structural_sha256": hashlib.sha256(_canonical({
            "capture_profile": packet["capture_profile"],
            "source_structural_sha256": packet["source_structural_sha256"],
            "rows": structural_rows,
        })).hexdigest(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not _secure_inside(args.input, HERE / "private-replays"):
        parser.error("review input must stay inside the ignored private-replays directory")
    if not _secure_inside(args.report, HERE / "reports"):
        parser.error("score report must stay inside the ignored reports directory")
    write_atomic_json(args.report, score_private_review(args.input), HERE / "reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
