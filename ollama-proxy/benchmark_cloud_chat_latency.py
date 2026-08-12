"""Bounded, opt-in TTFT benchmark for CloudChatProvider's SSE stream."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from cloud_chat_provider import CloudChatConfig, CloudChatProvider


DEFAULT_PROMPT = "Reply with a short greeting."
MAX_RUNS = 20
MAX_PROMPT_CHARS = 4_000


class BenchmarkError(RuntimeError):
    """A safe, user-actionable benchmark failure."""


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def latency_summary(values: list[float]) -> dict[str, float | int]:
    return {"count": len(values), "p50_ms": percentile(values, 50)}


def _env_config(provider: str | None, model: str | None) -> CloudChatConfig:
    """Apply CLI overrides through CloudChatConfig's existing env contract."""
    overrides = {
        "AIRI_CHAT_PROVIDER": provider,
        "AIRI_CHAT_MODEL": model,
    }
    original = {name: os.environ.get(name) for name in overrides}
    try:
        for name, value in overrides.items():
            if value is not None:
                os.environ[name] = value
        config = CloudChatConfig.from_env()
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return replace(config, usage_ledger_path="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("openai", "anthropic"),
                        help="Overrides AIRI_CHAT_PROVIDER for this run.")
    parser.add_argument("--model", help="Overrides AIRI_CHAT_MODEL for this run.")
    parser.add_argument("--runs", type=int, default=int(os.getenv("AIRI_CLOUD_CHAT_BENCHMARK_RUNS", "5")))
    parser.add_argument("--prompt", default=os.getenv("AIRI_CLOUD_CHAT_BENCHMARK_PROMPT", DEFAULT_PROMPT))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("AIRI_CLOUD_CHAT_BENCHMARK_TIMEOUT", "60")))
    parser.add_argument("--report", type=Path, help="Optional JSON output path; no report is written by default.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.runs <= MAX_RUNS:
        raise BenchmarkError(f"--runs must be between 1 and {MAX_RUNS}")
    if not args.prompt or len(args.prompt) > MAX_PROMPT_CHARS:
        raise BenchmarkError(f"--prompt must be between 1 and {MAX_PROMPT_CHARS} characters")
    if args.timeout <= 0:
        raise BenchmarkError("--timeout must be positive")


async def measure_stream(provider: CloudChatProvider, payload: dict[str, Any],
                         clock: Callable[[], float] = time.perf_counter) -> dict[str, float]:
    started = clock()
    response = await provider.open_stream(payload)
    ttft_ms: float | None = None
    async for delta in provider.deltas(response):
        if delta and ttft_ms is None:
            ttft_ms = (clock() - started) * 1000
    if ttft_ms is None:
        raise BenchmarkError("cloud chat stream completed without a text delta")
    return {"ttft_ms": round(ttft_ms, 3), "total_ms": round((clock() - started) * 1000, 3)}


async def benchmark(config: CloudChatConfig, runs: int, prompt: str, client: Any,
                    clock: Callable[[], float] = time.perf_counter) -> dict[str, Any]:
    validate_config(config)
    provider = CloudChatProvider(config, client=client)
    measurements = []
    payload = {"messages": [{"role": "user", "content": prompt}]}
    for _ in range(runs):
        measurements.append(await measure_stream(provider, payload, clock))
    ttft = [row["ttft_ms"] for row in measurements]
    total = [row["total_ms"] for row in measurements]
    return {
        "status": "measured",
        "provider": config.provider,
        "model": config.model,
        "runs": measurements,
        "summary": {"ttft": latency_summary(ttft), "total": latency_summary(total)},
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }


def validate_config(config: CloudChatConfig) -> None:
    if config.provider not in {"openai", "anthropic"}:
        raise BenchmarkError("configure AIRI_CHAT_PROVIDER as openai or anthropic")
    if not config.allow_external:
        raise BenchmarkError("external chat is not approved; set AIRI_ALLOW_EXTERNAL_CHAT=1")
    if not config.api_key:
        raise BenchmarkError(f"missing credential for {config.provider} cloud chat")
    if not config.model:
        raise BenchmarkError("missing AIRI_CHAT_MODEL")


def _safe_error(exc: Exception) -> str:
    # Never print provider exception details: they can contain an Authorization header.
    if isinstance(exc, BenchmarkError):
        return str(exc)
    return f"stream failed: {type(exc).__name__}"


def write_report(path: Path, result: dict[str, Any]) -> None:
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def async_main(args: argparse.Namespace, client: Any = None) -> tuple[int, dict[str, Any]]:
    validate_args(args)
    config = _env_config(args.provider, args.model)
    validate_config(config)
    if client is None:
        import httpx
        client = httpx.AsyncClient(timeout=args.timeout, http2=True)
        try:
            result = await benchmark(config, args.runs, args.prompt, client)
        finally:
            await client.aclose()
    else:
        result = await benchmark(config, args.runs, args.prompt, client)
    return 0, result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, result = asyncio.run(async_main(args))
    except Exception as exc:
        code, result = 2, {"status": "error", "error": _safe_error(exc)}
    if args.report:
        write_report(args.report, result)
    if code:
        print(f"cloud latency benchmark: {result['error']}")
        return code
    summary = result["summary"]
    print(f"cloud latency benchmark: {result['provider']}/{result['model']}; "
          f"TTFT P50 {summary['ttft']['p50_ms']} ms; total P50 {summary['total']['p50_ms']} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
