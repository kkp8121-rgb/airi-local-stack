"""Run the seven-sentence GPT-SoVITS streaming gate from the project root."""
from __future__ import annotations

import argparse
import statistics
import time

import requests

TEXTS = [
    "안녕하세요. 오늘은 어떤 이야기를 해볼까요?",
    "잠깐만요, 그건 제가 생각했던 것과 조금 다른데요?",
    "정말요? 그건 꽤 재미있겠는데요!",
    "아, 아니거든요! 제가 언제 그랬다고 그래요?",
    "오늘도 와줘서 고마워요. 조금 더 같이 있어요.",
    "저는 지금 아주 즐겁게 이야기하고 있어요.",
    "그럼 다음 주제는 무엇으로 해볼까요?",
]


def run(url: str, reference: str, mode: int, minimum: int) -> None:
    first_ms = []
    total_ms = []
    for text in TEXTS:
        payload = {
            "text": text,
            "text_lang": "ko",
            "ref_audio_path": reference,
            "prompt_lang": "ko",
            "prompt_text": "안녕하세요.",
            "streaming_mode": mode,
            "min_chunk_length": minimum,
            "media_type": "wav",
            "parallel_infer": True,
        }
        started = time.perf_counter()
        response = requests.post(url, json=payload, stream=True, timeout=180)
        response.raise_for_status()
        first = None
        for chunk in response.iter_content(4096):
            if first is None:
                first = time.perf_counter()
        finished = time.perf_counter()
        first_ms.append((first - started) * 1000)
        total_ms.append((finished - started) * 1000)
    print(
        f"mode={mode} min_chunk_length={minimum} "
        f"first_p50_ms={statistics.median(first_ms):.1f} "
        f"first_max_ms={max(first_ms):.1f} "
        f"total_p50_ms={statistics.median(total_ms):.1f} "
        f"total_max_ms={max(total_ms):.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:9880/tts")
    parser.add_argument("--reference", default="C:/Projects/airi/chatterbox/voices/airi-reference.wav")
    parser.add_argument("--mode", type=int, default=2)
    parser.add_argument("--min-chunk-length", type=int, default=16)
    args = parser.parse_args()
    run(args.url, args.reference, args.mode, args.min_chunk_length)


if __name__ == "__main__":
    main()
