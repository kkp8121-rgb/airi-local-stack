"""스트리머가 실제로 반응한 채팅을 찾아 (채팅, 응답) 쌍으로 낸다.

왜 필요한가. 평가에는 두 가지가 계속 없었다.

  1. **픽업 정답지.** `plan_pickups` 가 무엇을 골라야 하는지를 추측으로 정하고 있었다.
     실제 인기 스트리머가 무엇에 반응했는지가 있으면 추측할 필요가 없다.
  2. **흔들리지 않는 채점 기준점.** 사람 전수 채점은 병목이고, AI 채점은 프롬프트에 따라
     3축 합성이 1.0 씩 움직였다(2026-08-27 실측). "같은 채팅에 실제 스트리머는 이렇게
     답했다" 는 그 자리에 놓을 수 있는 고정점이다.

시간만으로 짝지으면 안 된다 — 채팅이 초당 3건인데 스트리머는 극히 일부만 읽는다. 스트리머가
채팅을 읽을 때는 그 채팅의 고유 어휘를 발화에 그대로 쓰므로, 그 겹침을 신호로 쓴다.

**방향을 반드시 가른다.** 시청자가 스트리머 말을 따라한 경우가 훨씬 흔하다. 채팅 직전
발화에 이미 나온 어휘는 '시청자가 꺼낸 화제'가 아니므로 응답 근거가 될 수 없다.
실측에서 이 필터 하나로 후보 170건 중 123건이 걸러졌다.

출력 JSONL 은 저장소 밖에 둔다 — 실제 대화 원문을 담는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# 검색·후보 추출과 같은 토크나이저를 쓴다. 다른 분절을 쓰면 같은 말을 다르게 세게 된다.
from knowledge_store import _QUERY_STOP_TERMS, _tokens  # noqa: E402
from knowledge_batch import _COMMON_TERMS  # noqa: E402

RESPONSE_WINDOW_MS = 20_000   # 채팅 직후 이 시간 안에 시작한 발화만 응답 후보
ECHO_LOOKBACK_MS = 60_000     # 채팅 직전 이 시간 안에 스트리머가 이미 쓴 말이면 따라하기
MAX_SEGMENT_MS = 30_000       # 이보다 긴 세그먼트는 VAD 실패로 보고 짝짓기에서 뺀다
MIN_TERM_LEN = 2


def content_terms(text: str) -> set[str]:
    return {term for term in _tokens(text or "")
            if len(term) >= MIN_TERM_LEN
            and term not in _QUERY_STOP_TERMS
            and term not in _COMMON_TERMS}


def _same_word(left: str, right: str) -> bool:
    """조사·어미가 붙어 분절이 갈린 같은 말인지 본다.

    "충실한편" 과 "충실한" 은 같은 말인데 토큰이 다르다. 에코 판정에서 이걸 놓치면
    시청자가 따라한 말을 '시청자가 꺼낸 화제' 로 세어 응답을 과대 집계한다.
    (공통 접두 ≥2자 이고 짧은 쪽의 6할 이상 — 시뮬레이터의 시청자 사실 매칭과 같은 기준)
    """
    if left == right:
        return True
    common = 0
    for a, b in zip(left, right):
        if a != b:
            break
        common += 1
    return common >= 2 and common >= 0.6 * min(len(left), len(right))


def _already_said(term: str, prior: set[str]) -> bool:
    return any(_same_word(term, said) for said in prior)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def pair_responses(chats: Sequence[dict], speech: Sequence[dict], *,
                   response_window_ms: int = RESPONSE_WINDOW_MS,
                   echo_lookback_ms: int = ECHO_LOOKBACK_MS,
                   max_segment_ms: int = MAX_SEGMENT_MS) -> dict:
    usable = [s for s in speech if s["end_ms"] - s["start_ms"] <= max_segment_ms]
    dropped = len(speech) - len(usable)
    indexed = [(segment, content_terms(segment["text"])) for segment in usable]
    audio_end = max((s["end_ms"] for s in usable), default=0)
    in_window = [c for c in chats if c.get("offset_ms", 0) <= audio_end]

    pairs: list[dict] = []
    echoes = 0
    for chat in in_window:
        terms = content_terms(chat.get("text", ""))
        if not terms:
            continue
        prior: set[str] = set()
        for segment, segment_terms in indexed:
            if chat["offset_ms"] - echo_lookback_ms <= segment["end_ms"] <= chat["offset_ms"]:
                prior |= segment_terms
        novel = {term for term in terms if not _already_said(term, prior)}
        if not novel:
            echoes += 1
            continue
        best: tuple[dict, set[str]] | None = None
        for segment, segment_terms in indexed:
            if not chat["offset_ms"] <= segment["start_ms"] <= chat["offset_ms"] + response_window_ms:
                continue
            shared = novel & segment_terms
            if shared and (best is None or len(shared) > len(best[1])):
                best = (segment, shared)
        if best:
            pairs.append({
                "chat_offset_ms": chat["offset_ms"],
                "author": chat.get("author", ""),
                "chat_text": chat.get("text", ""),
                "speech_start_ms": best[0]["start_ms"],
                "speech_text": best[0]["text"],
                "shared_terms": sorted(best[1]),
                "delay_ms": best[0]["start_ms"] - chat["offset_ms"],
            })
    return {
        "pairs": pairs,
        "stats": {
            "speech_segments": len(speech), "speech_dropped_overlong": dropped,
            "chats_in_audio_window": len(in_window), "chats_total": len(chats),
            "viewer_echoed_streamer": echoes, "responded": len(pairs),
            "responded_rate": round(len(pairs) / len(in_window), 4) if in_window else 0.0,
            "responded_authors": len({p["author"] for p in pairs}),
            "high_confidence": sum(1 for p in pairs if len(p["shared_terms"]) >= 2),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="스트리머가 실제로 반응한 채팅을 찾아 (채팅, 응답) 쌍으로 낸다.")
    parser.add_argument("--chat", required=True, help="가명화 채팅 JSONL(저장소 밖).")
    parser.add_argument("--transcript", required=True, help="STT 트랜스크립트 JSONL(저장소 밖).")
    parser.add_argument("--output", required=True, help="응답 쌍 JSONL 출력 경로(저장소 밖).")
    parser.add_argument("--response-window-ms", type=int, default=RESPONSE_WINDOW_MS)
    parser.add_argument("--echo-lookback-ms", type=int, default=ECHO_LOOKBACK_MS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = pair_responses(
        read_jsonl(Path(args.chat)), read_jsonl(Path(args.transcript)),
        response_window_ms=args.response_window_ms, echo_lookback_ms=args.echo_lookback_ms)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "\n".join(json.dumps(pair, ensure_ascii=False) for pair in result["pairs"]) + "\n",
        encoding="utf-8")
    stats = result["stats"]
    print(f"발화 세그먼트 {stats['speech_segments']}개"
          f" (과장 세그먼트 {stats['speech_dropped_overlong']}개 제외)")
    print(f"오디오 구간 채팅 {stats['chats_in_audio_window']}건 / 전체 {stats['chats_total']}건")
    print(f"시청자가 스트리머 말을 따라한 것으로 제외: {stats['viewer_echoed_streamer']}건")
    print(f"스트리머가 반응한 채팅: {stats['responded']}건 ({stats['responded_rate']:.1%})"
          f" · 고유 시청자 {stats['responded_authors']}명"
          f" · 고신뢰(공유 어휘 2개+) {stats['high_confidence']}건")
    print(f"→ {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
