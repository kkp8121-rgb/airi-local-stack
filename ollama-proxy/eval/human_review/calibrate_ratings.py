"""AI 채점을 사람 부분 채점으로 눈금 보정해 전수 채점에 준하는 추정치를 만든다.

왜 이게 필요한가 (2026-08-27 실측):
  - AI 채점 단독은 게이트에 쓸 수 없다. 앵커 캘리브레이션을 줘도 채점자 2종(codex/claude)이
    사람 3.0976 회차를 각각 1.98/2.11 로 매겨 PASS 를 FAIL 로 뒤집었다.
  - 그러나 두 AI 는 서로 0.09~0.13 안에서 일치했다. 즉 오차는 무작위가 아니라 체계적
    편향이고, 앵커 평균 쪽으로 수축(shrinkage)한 결과다. 체계적 편향은 사람 표본으로
    교정할 수 있다.
  - 사람이 k턴만 채점하고 나머지를 AI+오프셋으로 메우면, 사람 k턴만 쓰는 것보다 p95 오차가
    15~48% 줄었다. k=30 층화 기준 p95 오차 0.13~0.18.

그래서 이 도구는 두 가지만 한다.
  select : AI 채점 분포를 가로지르도록 k턴을 결정론적으로 골라 리뷰 JSONL 을 걸러낸다.
           그 JSONL 을 build_rating_sheet.py 에 넣으면 부분 평가지 HTML 이 나온다.
  merge  : 사람 부분 채점 + AI 채점 → 보정된 전수 채점 JSON + 불확실성 리포트.

출력에 대화 텍스트도 코멘트 원문도 넣지 않는다. 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Sequence

SCHEMA_VERSION = "airi.human-rating.v1"
# summarize_ratings.AXIS_KEYS / FLAG_KEYS 와 같은 키·순서를 유지한다.
# 이 디렉터리 규약상 다른 eval 모듈을 import 하지 않으므로 의도적으로 복제했다.
AXIS_KEYS: tuple[str, ...] = (
    "broadcast_likeness", "context_retention", "response_appropriateness",
    "style_rules", "factuality",
)
FLAG_KEYS: tuple[str, ...] = (
    "critical_failure", "silence_or_filler", "invented_name", "polite_violation",
)
COMPOSITE_AXES: tuple[str, ...] = AXIS_KEYS[:3]
# critical 은 놓치면 끝이라 합집합으로 모은다. 나머지 플래그는 과잉 검출을 막으려고
# 과반(2인일 때는 전원 일치)을 요구한다.
UNION_FLAGS: frozenset[str] = frozenset({"critical_failure"})
SCORE_MIN, SCORE_MAX = 1, 5


class CalibrationError(ValueError):
    """입력이 계약을 벗어났을 때."""


def load_rating(path: Path) -> dict[int, dict]:
    """채점 JSON 하나를 turn_no -> 레코드 로 읽는다."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"{path.name}: 읽을 수 없는 채점 파일: {exc}") from exc
    turns = payload.get("turns")
    if not isinstance(turns, list) or not turns:
        raise CalibrationError(f"{path.name}: turns 가 비어 있다")
    out: dict[int, dict] = {}
    for turn in turns:
        turn_no = turn.get("turn_no")
        if not isinstance(turn_no, int) or isinstance(turn_no, bool):
            raise CalibrationError(f"{path.name}: turn_no 가 정수가 아니다")
        scores = turn.get("scores")
        if not isinstance(scores, dict) or any(axis not in scores for axis in AXIS_KEYS):
            raise CalibrationError(f"{path.name}: turn {turn_no} 의 scores 축이 모자란다")
        if turn_no in out:
            raise CalibrationError(f"{path.name}: turn {turn_no} 가 중복된다")
        out[turn_no] = turn
    return out


def composite(scores: dict) -> float:
    return statistics.fmean(float(scores[axis]) for axis in COMPOSITE_AXES)


def ensemble(ratings: Sequence[dict[int, dict]]) -> dict[int, dict]:
    """여러 AI 채점자를 평균 앙상블로 합친다. 모든 채점자가 가진 turn 만 남긴다."""
    shared = set(ratings[0])
    for other in ratings[1:]:
        shared &= set(other)
    if not shared:
        raise CalibrationError("채점자들이 공유하는 turn 이 없다")
    merged: dict[int, dict] = {}
    for turn_no in sorted(shared):
        records = [r[turn_no] for r in ratings]
        flags = {}
        for flag in FLAG_KEYS:
            votes = [bool(rec.get("flags", {}).get(flag, False)) for rec in records]
            flags[flag] = any(votes) if flag in UNION_FLAGS else sum(votes) * 2 > len(votes)
        merged[turn_no] = {
            "session_id": records[0].get("session_id", ""),
            "turn_no": turn_no,
            "scores": {axis: statistics.fmean(float(rec["scores"][axis]) for rec in records)
                       for axis in AXIS_KEYS},
            "flags": flags,
        }
    return merged


def select_turns(ai: dict[int, dict], count: int) -> list[int]:
    """AI 3축 점수 오름차순으로 count 개 층을 만들고 각 층의 중앙 turn 을 고른다.

    난수를 쓰지 않는다 — 같은 입력이면 같은 표본이 나와야 재현이 된다.
    층화 추출은 무작위보다 p95 오차가 6~22% 작았다(2026-08-27 실측).
    """
    if count < 2:
        raise CalibrationError("표본은 최소 2턴이어야 오프셋을 추정할 수 있다")
    if count > len(ai):
        raise CalibrationError(f"표본 {count} 턴이 전체 {len(ai)} 턴보다 많다")
    ordered = sorted(ai, key=lambda turn_no: (composite(ai[turn_no]["scores"]), turn_no))
    picked = []
    for index in range(count):
        lo = index * len(ordered) // count
        hi = (index + 1) * len(ordered) // count
        picked.append(ordered[(lo + hi - 1) // 2])
    return sorted(picked)


def calibrate(ai: dict[int, dict], human: dict[int, dict]) -> dict:
    """사람이 채점한 턴은 그대로 두고, 나머지는 축별 오프셋으로 보정한다."""
    sampled = sorted(set(human) & set(ai))
    if len(sampled) < 2:
        raise CalibrationError("사람 채점과 AI 채점이 겹치는 턴이 2개 미만이다")
    unknown = sorted(set(human) - set(ai))
    if unknown:
        raise CalibrationError(f"AI 채점에 없는 turn 을 사람이 채점했다: {unknown[:5]}")
    rest = [turn_no for turn_no in sorted(ai) if turn_no not in set(sampled)]

    offsets = {axis: statistics.fmean(float(human[t]["scores"][axis]) - ai[t]["scores"][axis]
                                      for t in sampled)
               for axis in AXIS_KEYS}
    exact: dict[int, dict[str, float]] = {}
    turns = []
    for turn_no in sorted(ai):
        from_human = turn_no in set(sampled)
        if from_human:
            values = {axis: float(human[turn_no]["scores"][axis]) for axis in AXIS_KEYS}
            flags = {flag: bool(human[turn_no].get("flags", {}).get(flag, False))
                     for flag in FLAG_KEYS}
        else:
            values = {axis: min(SCORE_MAX, max(SCORE_MIN, ai[turn_no]["scores"][axis] + offsets[axis]))
                      for axis in AXIS_KEYS}
            flags = dict(ai[turn_no]["flags"])
        exact[turn_no] = values
        turns.append({
            "session_id": ai[turn_no]["session_id"], "turn_no": turn_no,
            # 정수 스키마를 지켜야 summarize_ratings.py 가 그대로 받는다. 소수점 추정치는
            # 아래 estimate 에 따로 남기므로 반올림으로 잃는 정밀도는 없다.
            "scores": {axis: int(round(values[axis])) for axis in AXIS_KEYS},
            "flags": flags,
            "source": "human" if from_human else "calibrated",
        })

    estimate = statistics.fmean(composite(exact[t]) for t in exact)
    # 표본에서 잰 사람-AI 잔차로 추정치의 표준오차를 낸다.
    #   est - true = ((n-k)/n)(d_bar_sample - d_bar_rest)  →  SE = sd_d * sqrt((n-k)/(n*k))
    # 층화 추출은 이보다 실제 오차가 작으므로 이 값은 보수적이다.
    residuals = [composite({a: float(human[t]["scores"][a]) for a in AXIS_KEYS})
                 - composite(ai[t]["scores"]) for t in sampled]
    total, taken = len(ai), len(sampled)
    residual_sd = statistics.stdev(residuals) if len(residuals) > 1 else 0.0
    standard_error = residual_sd * ((total - taken) / (total * taken)) ** 0.5 if rest else 0.0

    filler = sum(1 for t in turns if t["flags"]["silence_or_filler"]) / total
    critical = sum(1 for t in turns if t["flags"]["critical_failure"])
    axis_means = {axis: statistics.fmean(exact[t][axis] for t in exact) for axis in AXIS_KEYS}
    return {
        "schema_version": SCHEMA_VERSION,
        "rater": "calibrated",
        "calibration": {
            "turns_total": total, "turns_human": taken, "turns_calibrated": len(rest),
            "human_effort": round(taken / total, 4),
            "axis_offsets": {axis: round(value, 4) for axis, value in offsets.items()},
            "composite_estimate": round(estimate, 4),
            "composite_standard_error": round(standard_error, 4),
            "composite_interval_95": [round(estimate - 1.96 * standard_error, 4),
                                      round(estimate + 1.96 * standard_error, 4)],
            "residual_sd": round(residual_sd, 4),
            "axis_means": {axis: round(value, 4) for axis, value in axis_means.items()},
            "filler_rate": round(filler, 4),
            "critical_count": critical,
            "human_turns": sampled,
        },
        "turns": turns,
    }


def report_lines(result: dict, gate_composite: float, gate_filler: float,
                 gate_style: float, gate_factuality: float) -> list[str]:
    """돌파 정의 5개 기준을 전부 낸다.

    계약 §4(AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26)의 돌파 정의는
    3축 합성 >= 3.0, critical 0, silence_or_filler <= 25%, 말투 >= 3.5,
    사실성 >= 기준선 이다. 일부만 보면 통과 판정이 잘못 나온다.
    """
    meta = result["calibration"]
    low, high = meta["composite_interval_95"]
    if low >= gate_composite:
        band = "기준선 위 — 확정 가능"
    elif high < gate_composite:
        band = "기준선 아래 — 확정 가능"
    else:
        band = "구간이 기준선을 가로지름 — 판정 보류, 전수 채점 필요"
    axis = meta["axis_means"]
    checks = (
        (f"3축 합성 >= {gate_composite:.2f}", meta["composite_estimate"] >= gate_composite,
         f"{meta['composite_estimate']:.4f}"),
        ("critical = 0", meta["critical_count"] == 0, f"{meta['critical_count']}건"),
        (f"filler <= {gate_filler:.0%}", meta["filler_rate"] <= gate_filler,
         f"{meta['filler_rate']:.2%}"),
        (f"말투 >= {gate_style:.2f}", axis["style_rules"] >= gate_style,
         f"{axis['style_rules']:.4f}"),
        (f"사실성 >= {gate_factuality:.2f}", axis["factuality"] >= gate_factuality,
         f"{axis['factuality']:.4f}"),
    )
    lines = [
        "# 보정 채점 요약",
        "",
        f"- 전체 {meta['turns_total']}턴 중 사람 {meta['turns_human']}턴"
        f" (노력 {meta['human_effort']:.0%}), 보정 {meta['turns_calibrated']}턴",
        f"- 3축 합성 추정 **{meta['composite_estimate']:.4f}**"
        f" ± {1.96 * meta['composite_standard_error']:.4f} (95%)",
        f"- 95% 구간 [{low:.4f}, {high:.4f}] · 기준선 {gate_composite:.2f} → **{band}**",
        f"- 축별 오프셋 " + ", ".join(f"{a}={v:+.2f}" for a, v in meta["axis_offsets"].items()),
        "",
        "## 돌파 정의 5개 기준 (계약 §4)",
        "",
    ]
    lines += [f"- [{'O' if ok else 'X'}] {name} — {detail}" for name, ok, detail in checks]
    lines += [
        "",
        f"→ 5개 기준 종합 **{'전부 충족' if all(c[1] for c in checks) else '미충족 있음'}**",
        "",
        "AI 채점 단독은 게이트 판정을 뒤집은 실적이 있다. 이 추정치는 사람 표본으로",
        "눈금을 맞춘 값이며, 구간이 기준선을 가로지르면 확정하지 말고 전수 채점한다.",
        "filler 와 critical 은 보정으로 닫히지 않으니 계약대로 사람이 확인한다.",
    ]
    return lines


def cmd_select(args) -> int:
    ai = ensemble([load_rating(Path(p)) for p in args.ai])
    picked = select_turns(ai, args.k)
    lines = [line for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    kept = [line for line in lines if json.loads(line).get("turn_no") in set(picked)]
    if len(kept) != len(picked):
        raise CalibrationError(f"리뷰 JSONL 에서 {len(picked) - len(kept)} 턴을 찾지 못했다")
    Path(args.output).write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"전체 {len(ai)}턴 중 {len(picked)}턴 층화 선정 → {args.output}")
    print(f"선정 turn_no: {picked}")
    return 0


def cmd_merge(args) -> int:
    ai = ensemble([load_rating(Path(p)) for p in args.ai])
    result = calibrate(ai, load_rating(Path(args.human)))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = report_lines(result, args.gate_composite, args.gate_filler,
                         args.gate_style, args.gate_factuality)
    if args.markdown:
        Path(args.markdown).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n보정 채점 JSON → {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI 채점을 사람 부분 채점으로 보정해 전수 채점에 준하는 추정치를 만든다.")
    sub = parser.add_subparsers(dest="command", required=True)

    select = sub.add_parser("select", help="사람이 채점할 k턴을 층화 선정해 리뷰 JSONL 을 걸러낸다.")
    select.add_argument("--ai", nargs="+", required=True, help="AI 채점 JSON (여러 개면 앙상블).")
    select.add_argument("--input", required=True, help="원본 review JSONL.")
    select.add_argument("--output", required=True, help="선정 턴만 담은 JSONL 출력 경로.")
    select.add_argument("--k", type=int, default=30, help="사람이 채점할 턴 수 (기본 30).")
    select.set_defaults(func=cmd_select)

    merge = sub.add_parser("merge", help="사람 부분 채점 + AI 채점 → 보정 전수 채점.")
    merge.add_argument("--ai", nargs="+", required=True, help="AI 채점 JSON (여러 개면 앙상블).")
    merge.add_argument("--human", required=True, help="사람이 부분 채점한 JSON.")
    merge.add_argument("--output", required=True, help="보정 채점 JSON 출력 경로.")
    merge.add_argument("--markdown", default=None, help="사람이 읽을 요약 Markdown 출력 경로.")
    # 기본값은 계약 §4 돌파 정의와 run 04 확정 기준선(사실성 2.75)을 그대로 옮긴 것이다.
    merge.add_argument("--gate-composite", type=float, default=3.0, help="3축 합성 기준선.")
    merge.add_argument("--gate-filler", type=float, default=0.25, help="filler 비율 기준선.")
    merge.add_argument("--gate-style", type=float, default=3.5, help="말투 규칙 기준선.")
    merge.add_argument("--gate-factuality", type=float, default=2.75,
                       help="사실성 기준선 (run 04 확정 기준선).")
    merge.set_defaults(func=cmd_merge)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CalibrationError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
