"""Run the seven-sentence GPT-SoVITS streaming gate from the project root.

Exits non-zero when the gate fails so it can be wired into a check, and targets
the speech proxy by default because that is the path AIRI actually uses.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time

import requests

# Importing the production proxy keeps the reference clip and the prompt pair in
# a single source. Benchmarking a different prompt combination than production
# once produced passing numbers for a configuration that synthesized silence.
import openai_compatible_proxy as proxy

TEXTS = [
    "안녕하세요. 오늘은 어떤 이야기를 해볼까요?",
    "잠깐만요, 그건 제가 생각했던 것과 조금 다른데요?",
    "정말요? 그건 꽤 재미있겠는데요!",
    "아, 아니거든요! 제가 언제 그랬다고 그래요?",
    "오늘도 와줘서 고마워요. 조금 더 같이 있어요.",
    "저는 지금 아주 즐겁게 이야기하고 있어요.",
    "그럼 다음 주제는 무엇으로 해볼까요?",
]

PROXY_URL = "http://127.0.0.1:8880/v1/audio/speech"
DIRECT_URL = "http://127.0.0.1:9880/tts"


def build_payload(text: str, direct: bool, mode: int, minimum: int) -> dict:
    if not direct:
        return {
            "model": "tts-1-ko",
            "input": text,
            "voice": "airi-vtuber",
            "response_format": "wav",
            "speed": 1.0,
        }
    payload = proxy.build_backend_payload(text)
    payload["streaming_mode"] = mode
    payload["min_chunk_length"] = minimum
    return payload


def run(
    url: str,
    direct: bool,
    mode: int,
    minimum: int,
    gate_first_ms: float,
    gate_min_bytes: int,
    timeout: float,
) -> int:
    first_ms: list[float] = []
    total_ms: list[float] = []
    failures: list[str] = []
    for text in TEXTS:
        label = text[:14]
        started = time.perf_counter()
        try:
            response = requests.post(
                url, json=build_payload(text, direct, mode, minimum), stream=True, timeout=timeout
            )
        except requests.RequestException as exc:
            failures.append(f"{label}: request failed: {exc}")
            continue
        with response:
            if response.status_code != 200:
                failures.append(f"{label}: HTTP {response.status_code}: {response.text[:200]}")
                continue
            first = None
            total_bytes = 0
            for chunk in response.iter_content(4096):
                if not chunk:
                    continue
                if first is None:
                    first = time.perf_counter()
                total_bytes += len(chunk)
        finished = time.perf_counter()
        if first is None:
            failures.append(f"{label}: HTTP 200 without a single audio byte")
            continue
        first_latency = (first - started) * 1000
        first_ms.append(first_latency)
        total_ms.append((finished - started) * 1000)
        if first_latency > gate_first_ms:
            failures.append(f"{label}: first chunk {first_latency:.1f}ms exceeds {gate_first_ms:.0f}ms")
        if total_bytes < gate_min_bytes:
            failures.append(f"{label}: {total_bytes} bytes below {gate_min_bytes}")

    target = "direct" if direct else "proxy"
    if first_ms:
        print(
            f"target={target} url={url} sentences={len(first_ms)}/{len(TEXTS)} "
            f"first_p50_ms={statistics.median(first_ms):.1f} "
            f"first_max_ms={max(first_ms):.1f} "
            f"total_p50_ms={statistics.median(total_ms):.1f} "
            f"total_max_ms={max(total_ms):.1f}"
        )
    else:
        print(f"target={target} url={url} sentences=0/{len(TEXTS)} no successful generation")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"FAIL gate: {len(failures)} problem(s) across {len(TEXTS)} sentences")
        return 1
    print(f"PASS gate: first_chunk <= {gate_first_ms:.0f}ms and >= {gate_min_bytes} bytes on every sentence")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--direct",
        action="store_true",
        help="bypass the speech proxy and call GPT-SoVITS api_v2 directly",
    )
    parser.add_argument("--url", default=None, help="override the target URL")
    parser.add_argument("--mode", type=int, default=proxy.STREAMING_MODE)
    parser.add_argument("--min-chunk-length", type=int, default=proxy.MIN_CHUNK_LENGTH)
    parser.add_argument("--gate-first-ms", type=float, default=800.0)
    parser.add_argument("--gate-min-bytes", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    url = args.url or (DIRECT_URL if args.direct else PROXY_URL)
    return run(
        url,
        args.direct,
        args.mode,
        args.min_chunk_length,
        args.gate_first_ms,
        args.gate_min_bytes,
        args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
