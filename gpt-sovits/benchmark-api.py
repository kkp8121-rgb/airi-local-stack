"""Measure GPT-SoVITS API first-chunk and total latency."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:9880/tts")
    parser.add_argument("--reference", default="chatterbox/voices/airi-reference.wav")
    parser.add_argument("--prompt-lang", default="ko")
    parser.add_argument("--prompt-text", default="안녕하세요.")
    parser.add_argument("--text", default="안녕하세요. 오늘은 어떤 이야기를 해볼까요?")
    parser.add_argument("--mode", type=int, default=2)
    parser.add_argument("--min-chunk-length", type=int, default=8)
    args = parser.parse_args()
    payload = {
        "text": args.text,
        "text_lang": "ko",
        "ref_audio_path": str(Path(args.reference).resolve()),
        "prompt_lang": args.prompt_lang,
        "prompt_text": args.prompt_text,
        "streaming_mode": args.mode,
        "min_chunk_length": args.min_chunk_length,
        "media_type": "wav",
        "parallel_infer": True,
    }
    started = time.perf_counter()
    response = requests.post(args.url, json=payload, stream=True, timeout=180)
    response.raise_for_status()
    first = None
    chunks = total_bytes = 0
    for chunk in response.iter_content(4096):
        if first is None:
            first = time.perf_counter()
        chunks += 1
        total_bytes += len(chunk)
    elapsed = time.perf_counter() - started
    print(f"status={response.status_code}")
    print(f"first_chunk_ms={(first - started) * 1000:.1f}" if first else "first_chunk_ms=none")
    print(f"total_ms={elapsed * 1000:.1f} chunks={chunks} bytes={total_bytes}")


if __name__ == "__main__":
    main()
