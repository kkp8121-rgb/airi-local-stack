"""3축 게이트가 주어진 채점 결과에서 도달 가능한지 계산한다.

왜 필요한가. 2026-08-27 실측에서 `context_retention` 이 입력 구조 때문에 오르지 못한다는 것이
드러났다 — 사용자가 직접 채점한 198턴에서 평균 1.54, **4점 이상 0건**이다. 그 축이 3축 합성의
1/3 이므로, 게이트가 실제로 도달 가능한지는 나머지 두 축이 얼마나 나와야 하는지로 판정된다.

결과: 3.0 을 넘으려면 나머지 두 축이 평균 **3.73** 이어야 한다(실측 1.98의 1.9배). 맥락 유지가
관측 상한 3.0 까지 올라도 나머지가 3.00 은 되어야 한다. **모델을 고쳐도 넘지 못한다.**

채점 JSON 은 저장소 밖에 있으므로 경로를 인자로 받는다. 출력에 대화 텍스트는 넣지 않는다.
상세 = `airi_docs/진행중/AIRI-EVAL-INPUT-CONTEXT-AUDIT-2026-08-27.md` §10.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Sequence

COMPOSITE_AXES = ("broadcast_likeness", "context_retention", "response_appropriateness")
DEFAULT_GATE = 3.0
HIGH_SCORE = 4


def load_turns(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    turns = payload.get("turns")
    if not isinstance(turns, list) or not turns:
        raise SystemExit(f"{path.name}: turns 가 비어 있다")
    return turns


def summarise(turns: Sequence[dict], gate: float) -> dict:
    means = {axis: statistics.fmean(turn["scores"][axis] for turn in turns)
             for axis in COMPOSITE_AXES}
    composite = statistics.fmean(means.values())
    blocked = means["context_retention"]
    return {
        "n": len(turns), "axis_means": means, "composite": composite,
        "high_context": sum(1 for turn in turns
                            if turn["scores"]["context_retention"] >= HIGH_SCORE),
        # 맥락 유지가 지금 값에 묶인다고 할 때 나머지 두 축의 필요 평균
        "needed_from_others": (gate * len(COMPOSITE_AXES) - blocked) / 2,
        "others_actual": statistics.fmean(
            statistics.fmean((turn["scores"]["broadcast_likeness"],
                              turn["scores"]["response_appropriateness"]))
            for turn in turns),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="3축 게이트가 이 채점 결과에서 도달 가능한지 계산한다.")
    parser.add_argument("--ratings", nargs="+", required=True,
                        help="사람 채점 JSON (저장소 밖).")
    parser.add_argument("--gate", type=float, default=DEFAULT_GATE)
    args = parser.parse_args(argv)

    print(f"{'회차':<28}{'방송다움':>9}{'맥락유지':>9}{'반응적절':>9}{'3축':>9}"
          f"{'맥락 4점+':>11}{'필요(나머지 2축)':>18}")
    print("-" * 94)
    pooled: list[dict] = []
    for raw in args.ratings:
        path = Path(raw)
        turns = load_turns(path)
        pooled.extend(turns)
        result = summarise(turns, args.gate)
        means = result["axis_means"]
        print(f"{path.stem[:27]:<28}{means['broadcast_likeness']:>9.2f}"
              f"{means['context_retention']:>9.2f}{means['response_appropriateness']:>9.2f}"
              f"{result['composite']:>9.4f}{result['high_context']:>8}/{result['n']:<3}"
              f"{result['needed_from_others']:>18.2f}")

    if len(args.ratings) > 1:
        total = summarise(pooled, args.gate)
        print("-" * 94)
        print(f"\n합산 {total['n']}턴 — 맥락 유지 평균 {total['axis_means']['context_retention']:.2f}"
              f" (4점 이상 {total['high_context']}건)")
        print(f"나머지 두 축 실측 평균 {total['others_actual']:.2f}")
        print(f"→ 게이트 {args.gate:.1f} 을 넘으려면 나머지 두 축이 평균 "
              f"**{total['needed_from_others']:.2f}** 이어야 한다 "
              f"({total['needed_from_others'] / max(total['others_actual'], 1e-9):.1f}배)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
