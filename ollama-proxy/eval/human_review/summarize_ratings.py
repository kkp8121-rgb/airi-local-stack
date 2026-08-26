"""사람 평가 JSON 을 검증하고 내용 없는 요약 통계로 집계한다.

출력에는 대화 텍스트도 코멘트 원문도 절대 넣지 않는다. 채택 게이트는 이 요약의
숫자만 보고 판단한다.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from itertools import combinations
from pathlib import Path
from typing import Sequence

SCHEMA_VERSION = "airi.human-rating.v1"
# build_rating_sheet.AXES 와 같은 키/순서를 유지한다(테스트가 일치를 강제한다).
AXIS_KEYS: tuple[str, ...] = (
    "broadcast_likeness",
    "context_retention",
    "response_appropriateness",
    "style_rules",
    "factuality",
)
FLAG_KEYS: tuple[str, ...] = (
    "critical_failure",
    "silence_or_filler",
    "invented_name",
    "polite_violation",
)
GOOD_SCORE = 4


class SchemaError(ValueError):
    """평가 JSON 이 계약을 벗어났을 때."""


def load_ratings(path: Path) -> dict:
    """평가 JSON 한 개를 읽고 스키마를 검증한다."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"{path.name}: unreadable ratings file: {exc}") from exc
    if not isinstance(payload, dict):
        raise SchemaError(f"{path.name}: top level must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SchemaError(f"{path.name}: schema_version must be {SCHEMA_VERSION!r}")
    rater = payload.get("rater")
    if not isinstance(rater, str) or not rater.strip():
        raise SchemaError(f"{path.name}: rater must be a non-empty string")
    turns = payload.get("turns")
    if not isinstance(turns, list):
        raise SchemaError(f"{path.name}: turns must be a list")
    for index, turn in enumerate(turns):
        validate_turn(path.name, index, turn)
    return payload


def validate_turn(source: str, index: int, turn: object) -> None:
    """한 turn 평가 레코드를 검증한다."""
    where = f"{source}: turns[{index}]"
    if not isinstance(turn, dict):
        raise SchemaError(f"{where} must be an object")
    if not isinstance(turn.get("session_id"), str) or not turn["session_id"]:
        raise SchemaError(f"{where}.session_id must be a non-empty string")
    if not isinstance(turn.get("turn_no"), int) or isinstance(turn.get("turn_no"), bool):
        raise SchemaError(f"{where}.turn_no must be an integer")
    scores = turn.get("scores")
    if not isinstance(scores, dict):
        raise SchemaError(f"{where}.scores must be an object")
    for axis in AXIS_KEYS:
        value = scores.get(axis)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
            raise SchemaError(f"{where}.scores.{axis} must be an integer in 1..5")
    flags = turn.get("flags", {})
    if not isinstance(flags, dict):
        raise SchemaError(f"{where}.flags must be an object")
    for flag, value in flags.items():
        if flag not in FLAG_KEYS:
            raise SchemaError(f"{where}.flags has unknown flag {flag!r}")
        if not isinstance(value, bool):
            raise SchemaError(f"{where}.flags.{flag} must be a boolean")
    comment = turn.get("comment", "")
    if not isinstance(comment, str):
        raise SchemaError(f"{where}.comment must be a string")


def axis_stats(values: list[int]) -> dict:
    return {
        "mean": round(statistics.fmean(values), 4),
        "median": round(float(statistics.median(values)), 4),
        "min": min(values),
        "n": len(values),
    }


def agreement(records: list[tuple[str, dict]]) -> dict:
    """같은 (session_id, turn_no) 를 2명 이상이 평가한 경우의 불일치 지표."""
    by_turn: dict[tuple[str, int], list[tuple[str, dict]]] = {}
    for rater, turn in records:
        by_turn.setdefault((turn["session_id"], turn["turn_no"]), []).append((rater, turn))

    shared = {
        key: raters
        for key, raters in by_turn.items()
        if len({rater for rater, _turn in raters}) >= 2
    }
    if not shared:
        return {"shared_turns": 0, "axis_mean_abs_diff": {}, "flag_disagreement_rate": {}}

    axis_diffs: dict[str, list[float]] = {axis: [] for axis in AXIS_KEYS}
    flag_diffs: dict[str, list[int]] = {flag: [] for flag in FLAG_KEYS}
    for raters in shared.values():
        for (_rater_a, turn_a), (_rater_b, turn_b) in combinations(raters, 2):
            for axis in AXIS_KEYS:
                axis_diffs[axis].append(abs(turn_a["scores"][axis] - turn_b["scores"][axis]))
            for flag in FLAG_KEYS:
                flag_a = bool(turn_a.get("flags", {}).get(flag, False))
                flag_b = bool(turn_b.get("flags", {}).get(flag, False))
                flag_diffs[flag].append(int(flag_a != flag_b))
    return {
        "shared_turns": len(shared),
        "axis_mean_abs_diff": {
            axis: round(statistics.fmean(values), 4) for axis, values in axis_diffs.items()
        },
        "flag_disagreement_rate": {
            flag: round(statistics.fmean(values), 4) for flag, values in flag_diffs.items()
        },
    }


def summarize(payloads: list[dict]) -> dict:
    """내용 없는 요약을 만든다. 대화·코멘트 원문은 포함하지 않는다."""
    records: list[tuple[str, dict]] = []
    for payload in payloads:
        for turn in payload["turns"]:
            records.append((payload["rater"], turn))
    if not records:
        raise SchemaError("no rated turns found")

    per_axis = {
        axis: axis_stats([turn["scores"][axis] for _rater, turn in records]) for axis in AXIS_KEYS
    }
    all_good = sum(
        1
        for _rater, turn in records
        if all(turn["scores"][axis] >= GOOD_SCORE for axis in AXIS_KEYS)
    )
    flag_rates = {
        flag: round(
            statistics.fmean(
                [int(bool(turn.get("flags", {}).get(flag, False))) for _rater, turn in records]
            ),
            4,
        )
        for flag in FLAG_KEYS
    }
    raters = sorted({rater for rater, _turn in records})
    unique_turns = {(turn["session_id"], turn["turn_no"]) for _rater, turn in records}
    return {
        "schema_version": SCHEMA_VERSION,
        "rating_files": len(payloads),
        "raters": raters,
        "n_ratings": len(records),
        "n_unique_turns": len(unique_turns),
        "n_sessions": len({session_id for session_id, _turn_no in unique_turns}),
        "per_axis": per_axis,
        "all_axes_at_least_4_share": round(all_good / len(records), 4),
        "flag_rates": flag_rates,
        "commented_ratings": sum(
            1 for _rater, turn in records if str(turn.get("comment", "")).strip()
        ),
        "agreement": agreement(records),
    }


def render_markdown(summary: dict) -> str:
    lines = [
        "# AIRI 실제 대화 사람 평가 요약",
        "",
        f"- 평가 파일 {summary['rating_files']}개, 평가자 {', '.join(summary['raters'])}",
        f"- 평가 레코드 {summary['n_ratings']}건 / 고유 turn {summary['n_unique_turns']}개 "
        f"/ 세션 {summary['n_sessions']}개",
        f"- 전 축 4점 이상 비율: {summary['all_axes_at_least_4_share']}",
        "",
        "| 축 | 평균 | 중앙값 | 최소 |",
        "| --- | --- | --- | --- |",
    ]
    for axis, stats in summary["per_axis"].items():
        lines.append(f"| {axis} | {stats['mean']} | {stats['median']} | {stats['min']} |")
    lines += ["", "| 플래그 | 비율 |", "| --- | --- |"]
    for flag, rate in summary["flag_rates"].items():
        lines.append(f"| {flag} | {rate} |")
    agree = summary["agreement"]
    lines += ["", f"공통 평가 turn: {agree['shared_turns']}"]
    for axis, diff in agree["axis_mean_abs_diff"].items():
        lines.append(f"- {axis} 평균 절대차: {diff}")
    for flag, rate in agree["flag_disagreement_rate"].items():
        lines.append(f"- {flag} 불일치율: {rate}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="사람 평가 JSON 을 내용 없는 요약으로 집계한다.")
    parser.add_argument(
        "--ratings",
        action="append",
        required=True,
        help="평가 JSON 경로. 평가자별로 여러 번 지정할 수 있다.",
    )
    parser.add_argument("--output", required=True, help="요약 JSON 출력 경로.")
    parser.add_argument("--markdown", default=None, help="사람이 읽을 요약 Markdown 출력 경로.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payloads = [load_ratings(Path(path)) for path in args.ratings]
        summary = summarize(payloads)
    except SchemaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    if args.markdown:
        markdown_path = Path(args.markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        with markdown_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_markdown(summary))

    print(
        f"ratings={summary['n_ratings']} turns={summary['n_unique_turns']} "
        f"raters={len(summary['raters'])} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
