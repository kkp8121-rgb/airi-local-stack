"""Dataset-level quality gate for AIRI-original Korean broadcast responses.

Single-row correctness is not enough: a corpus can be grounded and safe while
teaching one robotic show-runner formula.  This gate therefore scores the
*distribution* of endings and audience-management phrases.  It is intentionally
separate from the older behavior answer gate, whose short chatbot-shaped data
has been rejected for broadcast training.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "airi.broadcast-response-quality-report.v1"
CTA_MARKERS = (
    "골라줘", "던져줘", "외쳐줘", "찍어줘", "얹어줘", "남겨줘",
    "잡아줘", "찾아줘", "말해줘", "알려줘", "같이 보자", "같이 세자",
)
ONE_UNIT_MARKERS = ("하나만", "하나씩만", "한 줄만", "한 점", "하나씩")
META_LEAK_MARKERS = (
    "본대답", "내 방식으로", "끝에는 다음 얘기", "반응은 빠르게",
    "response beat", "required_beats", "training_eligible", "학습 데이터",
)
MANAGER_MARKERS = (
    "기준 하나씩", "가장 많이 나온", "이유 하나", "이유 두 개",
    "하나만 남겨", "많은 쪽부터", "제일 많이 나온",
)
QUESTION_END_RE = re.compile(r"[?？][\"'”’)]*$")
INITIATIVE_PATTERNS = (
    re.compile(r"내가\s+.{0,32}(?:예측해\s*볼게|해\s*볼게|볼게|할게|고를게|정할게|간다)"),
    re.compile(r"(?:나는|난)\s+.{0,32}(?:할래|볼래|갈래|고를래|틀래|간다|한다)"),
    re.compile(r"(?:일단|이번에는|이번엔|먼저|그냥)\s*.{0,40}(?:가자|보자|간다|연다|열자|할게|갈게|노려보자|해보자|확인하자)"),
    re.compile(r"(?:부터|먼저).{0,32}(?:갈게|볼게|해\s*볼게|보자|하자)"),
    re.compile(r"내\s*판단(?:은|으로)"),
)

MAX_CTA_RATE = 0.45
MAX_ONE_UNIT_RATE = 0.25
MAX_CHAT_ADDRESS_RATE = 0.55
MAX_QUESTION_END_RATE = 0.35
MAX_MANAGER_RATE = 0.25
MAX_DOMINANT_ENDING_RATE = 0.60
MIN_ENDING_MODES = 4
MIN_INITIATIVE_RATE = 0.30
MIN_INITIATIVE_WITHOUT_CTA_RATE = 0.20


class BroadcastQualityGateError(ValueError):
    """Raised for an invalid input corpus rather than a quality failure."""


def _selected_length(row: dict[str, Any]) -> int:
    selected = (row.get("event") or {}).get("selected_message", "")
    if isinstance(selected, list):
        return sum(len(str(item)) for item in selected)
    return len(str(selected))


def _has_any(text: str, markers: Sequence[str]) -> bool:
    return any(marker.lower() in text.lower() for marker in markers)


def _has_self_led_initiative(text: str) -> bool:
    """Detect a bounded host decision, not merely an audience-management CTA."""
    return any(pattern.search(text) for pattern in INITIATIVE_PATTERNS)


def ending_mode(row: dict[str, Any]) -> str:
    target = str(row.get("target", "")).strip()
    event_type = str((row.get("event") or {}).get("event_type", ""))
    if event_type == "acute_health":
        return "safety_stop"
    if event_type in {"privacy", "moderation", "imitation_copyright"}:
        return "boundary_redirect"
    if QUESTION_END_RE.search(target):
        return "open_question"
    if _has_any(target, CTA_MARKERS):
        return "audience_prompt"
    if re.search(r"(?:갈게|볼게|할게|가자|보자|이어가자|넘어가자)[.!~]*$", target):
        return "return_or_continue"
    if re.search(r"(?:다|어|야|네|지|임)[.!~]*$", target):
        return "statement"
    return "other"


def analyze(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise BroadcastQualityGateError("broadcast response corpus is empty")
    ids = [row.get("id") for row in rows]
    if not all(isinstance(record_id, str) and record_id for record_id in ids):
        raise BroadcastQualityGateError("every row needs a non-empty id")
    if len(set(ids)) != len(ids):
        raise BroadcastQualityGateError("duplicate broadcast response id")
    targets = [str(row.get("target", "")).strip() for row in rows]
    if not all(targets):
        raise BroadcastQualityGateError("every row needs a non-empty target")

    aliases = {
        str((row.get("event") or {}).get("synthetic_alias", "")).strip()
        for row in rows
        if str((row.get("event") or {}).get("synthetic_alias", "")).strip()
    }
    cta_ids = [row["id"] for row, target in zip(rows, targets) if _has_any(target, CTA_MARKERS)]
    one_unit_ids = [row["id"] for row, target in zip(rows, targets) if _has_any(target, ONE_UNIT_MARKERS)]
    chat_address_ids = [row["id"] for row, target in zip(rows, targets) if "채팅" in target]
    question_end_ids = [row["id"] for row, target in zip(rows, targets) if QUESTION_END_RE.search(target)]
    manager_ids = [row["id"] for row, target in zip(rows, targets) if _has_any(target, MANAGER_MARKERS)]
    initiative_ids = [row["id"] for row, target in zip(rows, targets) if _has_self_led_initiative(target)]
    initiative_without_cta_ids = [
        row["id"] for row, target in zip(rows, targets)
        if _has_self_led_initiative(target) and not _has_any(target, CTA_MARKERS)
    ]
    meta_leak_ids = [row["id"] for row, target in zip(rows, targets) if _has_any(target, META_LEAK_MARKERS)]
    shorter_than_input_ids = [
        row["id"] for row, target in zip(rows, targets)
        if len(target) < _selected_length(row)
    ]
    ungrounded_alias_ids = []
    for row, target in zip(rows, targets):
        own = str((row.get("event") or {}).get("synthetic_alias", "")).strip()
        foreign = sorted(alias for alias in aliases if alias != own and alias in target)
        if foreign or (own and own not in target and "callout" in row.get("required_beats", [])):
            ungrounded_alias_ids.append({"id": row["id"], "foreign": foreign, "own_missing": bool(own and own not in target)})

    modes = Counter(ending_mode(row) for row in rows)
    count = len(rows)
    rate = lambda hits: round(len(hits) / count, 4)
    normalized = [re.sub(r"\s+", "", target).lower() for target in targets]
    duplicate_target_count = len(normalized) - len(set(normalized))
    dominant_mode, dominant_count = modes.most_common(1)[0]
    checks = {
        "no_meta_leak": not meta_leak_ids,
        "no_ungrounded_alias": not ungrounded_alias_ids,
        "no_duplicate_target": duplicate_target_count == 0,
        "target_not_shorter_than_input": not shorter_than_input_ids,
        "cta_rate": rate(cta_ids) <= MAX_CTA_RATE,
        "one_unit_rate": rate(one_unit_ids) <= MAX_ONE_UNIT_RATE,
        "chat_address_rate": rate(chat_address_ids) <= MAX_CHAT_ADDRESS_RATE,
        "question_end_rate": rate(question_end_ids) <= MAX_QUESTION_END_RATE,
        "manager_formula_rate": rate(manager_ids) <= MAX_MANAGER_RATE,
        "self_led_initiative_rate": rate(initiative_ids) >= MIN_INITIATIVE_RATE,
        "initiative_without_cta_rate": rate(initiative_without_cta_ids) >= MIN_INITIATIVE_WITHOUT_CTA_RATE,
        "ending_mode_diversity": len(modes) >= MIN_ENDING_MODES,
        "dominant_ending_rate": round(dominant_count / count, 4) <= MAX_DOMINANT_ENDING_RATE,
    }
    lengths = sorted(map(len, targets))
    return {
        "schema_version": SCHEMA_VERSION,
        "records": count,
        "pass": all(checks.values()),
        "checks": checks,
        "rates": {
            "cta": rate(cta_ids),
            "one_unit": rate(one_unit_ids),
            "chat_address": rate(chat_address_ids),
            "question_end": rate(question_end_ids),
            "manager_formula": rate(manager_ids),
            "self_led_initiative": rate(initiative_ids),
            "initiative_without_cta": rate(initiative_without_cta_ids),
            "dominant_ending": round(dominant_count / count, 4),
        },
        "ending_modes": dict(sorted(modes.items())),
        "dominant_ending_mode": dominant_mode,
        "lengths": {
            "min": lengths[0],
            "p50": lengths[len(lengths) // 2],
            "max": lengths[-1],
        },
        "failures": {
            "meta_leak_ids": meta_leak_ids,
            "ungrounded_alias": ungrounded_alias_ids,
            "duplicate_target_count": duplicate_target_count,
            "shorter_than_input_ids": shorter_than_input_ids,
            "cta_ids": cta_ids,
            "one_unit_ids": one_unit_ids,
            "chat_address_ids": chat_address_ids,
            "question_end_ids": question_end_ids,
            "manager_formula_ids": manager_ids,
            "initiative_ids": initiative_ids,
            "initiative_without_cta_ids": initiative_without_cta_ids,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Korean broadcast response corpus quality gate")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    rows = [
        json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = analyze(rows)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
