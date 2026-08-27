"""VOD 오디오를 배치로 받아써 run_broadcast_sim --replay-transcript 형식 JSONL 로 낸다.

왜 별도 스크립트인가: `openai_stt_server.py` 는 마이크 스트리밍용 loopback 서버라 긴 파일을
한 번에 처리하는 경로가 없다. 모델·beam·언어는 그 서버와 **같은 값으로 핀**한다 — 회차마다
다른 설정으로 받아쓰면 트랜스크립트끼리 비교가 성립하지 않는다.

출력 계약은 `run_broadcast_sim.TRANSCRIPT_ROW_KEYS` 와 같아야 한다: start_ms / end_ms / text.

GPU 가 없으면 `--device cpu --compute-type int8` 로 돈다. 실측(2026-08-27, 클로드 PC):
32분 오디오를 large-v3-turbo/int8/CPU 로 654초에 처리(2.94배속).

대화 원문은 표준출력에 찍지 않는다 — 세그먼트 수·자수·경과만 낸다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

# openai_stt_server.py 와 같은 값. 어긋나면 회차 간 트랜스크립트 비교가 깨진다.
MODEL_NAME = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
BEAM_SIZE = 1
LANGUAGE = "ko"
PROGRESS_EVERY = 50


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VOD 오디오를 --replay-transcript 형식 JSONL 로 받아쓴다.")
    parser.add_argument("--input", required=True, help="오디오 파일(저장소 밖).")
    parser.add_argument("--output", required=True, help="트랜스크립트 JSONL 출력 경로(저장소 밖).")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--compute-type", default="int8",
                        help="cpu 는 int8, cuda 는 int8_float16 이 서버 기본값이다.")
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--language", default=LANGUAGE)
    parser.add_argument("--beam-size", type=int, default=BEAM_SIZE)
    parser.add_argument("--max-segment-seconds", type=float, default=30.0,
                        help="이보다 긴 세그먼트는 VAD 실패로 보고 경고한다(제외하지는 않는다).")
    return parser


def transcribe(model, audio: Path, *, language: str, beam_size: int) -> "Sequence":
    """faster-whisper 세그먼트 이터레이터를 낸다. 테스트는 이 함수를 갈아 끼운다."""
    segments, info = model.transcribe(
        str(audio), language=language, beam_size=beam_size,
        vad_filter=True, condition_on_previous_text=False,
    )
    print(f"길이 {info.duration:.0f}s · 언어 {info.language}({info.language_probability:.2f})",
          flush=True)
    return segments


def write_transcript(segments, out_path: Path, *, max_segment_seconds: float,
                     started: float) -> tuple[int, int, int]:
    rows = chars = long_segments = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            start_ms, end_ms = int(segment.start * 1000), int(segment.end * 1000)
            if (end_ms - start_ms) / 1000 > max_segment_seconds:
                long_segments += 1
            handle.write(json.dumps(
                {"start_ms": start_ms, "end_ms": end_ms, "text": text},
                ensure_ascii=False) + "\n")
            rows += 1
            chars += len(text)
            if rows % PROGRESS_EVERY == 0:
                elapsed = max(time.perf_counter() - started, 1e-6)
                print(f"  {rows}세그먼트 · 오디오 {segment.end:.0f}s · 경과 {elapsed:.0f}s "
                      f"(x{segment.end / elapsed:.2f} 실시간)", flush=True)
    return rows, chars, long_segments


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audio, out_path = Path(args.input), Path(args.output)
    if not audio.is_file():
        print(f"error: 오디오 파일이 없다: {audio}", file=sys.stderr)
        return 1
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("error: faster-whisper 가 설치돼 있지 않다 (pip install faster-whisper)",
              file=sys.stderr)
        return 2

    started = time.perf_counter()
    print(f"모델 로드: {args.model} ({args.device}/{args.compute_type})", flush=True)
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments = transcribe(model, audio, language=args.language, beam_size=args.beam_size)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows, chars, long_segments = write_transcript(
        segments, out_path, max_segment_seconds=args.max_segment_seconds, started=started)
    print(f"완료: {rows}세그먼트 · {chars:,}자 · {time.perf_counter() - started:.0f}s → {out_path}")
    if long_segments:
        # 대기화면·BGM 구간에서 VAD 가 통째로 뭉개는 일이 있다(실측 1건, 296초).
        print(f"경고: {args.max_segment_seconds:.0f}초를 넘는 세그먼트 {long_segments}개 — "
              "VAD 실패일 수 있으니 짝짓기에서 제외를 검토할 것")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
