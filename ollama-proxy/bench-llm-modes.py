"""Compare AIRI LLM backend modes on latency, output size and cost.

Run this on the development PC (the one that holds the API keys). It calls the
adapters directly, so the proxy does not have to be running or restarted
between modes.

    python bench-llm-modes.py                     # every mode that has its key
    python bench-llm-modes.py --modes local cloud # a subset
    python bench-llm-modes.py --repeat 3          # average over three runs

Modes that are missing their prerequisite - an API key environment variable, or
an installed codex CLI for codex-cli modes - are reported as SKIP instead of
failing the run. Outputs land next to this script:

    bench-llm-modes-<timestamp>.md            comparison tables
    bench-llm-modes-<timestamp>.json          raw measurements
    bench-llm-modes-<timestamp>-responses.md  full answers for persona review
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import httpx

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

# The report is Korean and the console may be cp949; never let an unencodable
# character kill a run whose measurements are already on disk.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from llm_backends import (  # noqa: E402
    LLMBackendError,
    build_backend,
    codex_program,
    load_llm_config,
    load_persona_prompt,
    missing_llm_credential,
    sentence_chunker,
    sentence_chunker_options,
)

DEFAULT_KRW_PER_USD = 1400.0


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def krw_per_usd(config: dict[str, object]) -> float:
    override = os.environ.get("KRW_PER_USD", "").strip()
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    try:
        return float(config.get("krw_per_usd", DEFAULT_KRW_PER_USD))
    except (TypeError, ValueError):
        return DEFAULT_KRW_PER_USD


def estimate_cost_usd(mode_config: dict[str, object], usage: dict[str, int]) -> float:
    pricing = mode_config.get("pricing_usd_per_mtok") or {}
    price_in = float(pricing.get("input", 0.0))
    price_out = float(pricing.get("output", 0.0))
    return (
        usage.get("input_tokens", 0) / 1_000_000 * price_in
        + usage.get("output_tokens", 0) / 1_000_000 * price_out
    )


async def measure_codex_spawn_overhead(runs: int = 3) -> dict[str, object] | None:
    """Time a bare `codex --version` spawn: the floor every codex turn pays.

    Isolates process/CLI boot from model time, so the report can say how much
    of a codex-cli turn is structural rather than inference.
    """
    program = codex_program()
    if not program:
        return None
    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        process = await asyncio.create_subprocess_exec(
            *program,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0),
        )
        await process.communicate()
        samples.append(elapsed_ms(started))
    return {
        "program": " ".join(program),
        "runs": runs,
        "min_ms": round(min(samples), 1),
        "mean_ms": round(statistics.fmean(samples), 1),
    }


async def run_case(
    mode: str,
    mode_config: dict[str, object],
    utterance: str,
    persona: str,
    chunker_options: dict[str, object],
    client: httpx.AsyncClient,
) -> dict[str, object]:
    """Measure one utterance against one mode."""
    backend = build_backend(mode_config, client)
    messages = [{"role": "user", "content": utterance}]
    started = time.perf_counter()
    ttft_ms: float | None = None
    first_sentence_ms: float | None = None
    text_parts: list[str] = []
    sentences: list[str] = []

    async def timed_deltas() -> AsyncIterator[str]:
        nonlocal ttft_ms
        async for delta in backend.stream_completion(persona, messages):
            if ttft_ms is None:
                ttft_ms = elapsed_ms(started)
            text_parts.append(delta)
            yield delta

    error = ""
    try:
        async for sentence in sentence_chunker(timed_deltas(), **chunker_options):
            if first_sentence_ms is None:
                first_sentence_ms = elapsed_ms(started)
            sentences.append(sentence)
    except (LLMBackendError, httpx.HTTPError, asyncio.TimeoutError) as exc:
        error = f"{type(exc).__name__}: {exc}"

    total_ms = elapsed_ms(started)
    answer = "".join(text_parts)
    usage = dict(backend.last_usage)
    cost_usd = estimate_cost_usd(mode_config, usage)
    return {
        "mode": mode,
        "provider": str(mode_config.get("provider", "")),
        "model": str(mode_config.get("model", "")),
        "utterance": utterance,
        "status": "error" if error else "ok",
        "error": error,
        "ttft_ms": ttft_ms,
        "first_sentence_ms": first_sentence_ms,
        "total_ms": total_ms,
        "chars": len(answer),
        "sentences": len(sentences),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cost_usd": cost_usd,
        "answer": answer,
    }


def cell(value: object, digits: int = 1) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def mean_or_none(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def render_markdown(
    rows: list[dict[str, object]],
    skipped: list[dict[str, str]],
    rate: float,
    repeat: int,
    codex_spawn: dict[str, object] | None = None,
) -> str:
    lines = [
        "# AIRI LLM 백엔드 모드 비교",
        "",
        f"- 생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"- 발화 반복 횟수: {repeat}",
        f"- 환율(KRW/USD): {rate:g}",
    ]
    if codex_spawn:
        lines.append(
            f"- codex 프로세스 스폰 오버헤드: min {codex_spawn['min_ms']}ms / "
            f"mean {codex_spawn['mean_ms']}ms ({codex_spawn['runs']}회, `--version` 기준) "
            "- codex-cli 모드의 TTFT는 여기에 모델 시간이 더해진 값이다."
        )
    lines += [
        "",
        "## 모드별 요약 (평균)",
        "",
        "| 모드 | provider | 모델 | TTFT(ms) | 첫 문장(ms) | 완료(ms) | 글자수 | 출력토큰 | USD/발화 | KRW/발화 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in dict.fromkeys(row["mode"] for row in rows):
        mode_rows = [row for row in rows if row["mode"] == mode and row["status"] == "ok"]
        if not mode_rows:
            lines.append(f"| {mode} | - | - | ERROR | ERROR | ERROR | - | - | - | - |")
            continue
        cost = mean_or_none([row["cost_usd"] for row in mode_rows]) or 0.0
        lines.append(
            "| {mode} | {provider} | {model} | {ttft} | {first} | {total} | {chars} | {out} | {usd} | {krw} |".format(
                mode=mode,
                provider=mode_rows[0]["provider"],
                model=mode_rows[0]["model"],
                ttft=cell(mean_or_none([r["ttft_ms"] for r in mode_rows if r["ttft_ms"]])),
                first=cell(
                    mean_or_none([r["first_sentence_ms"] for r in mode_rows if r["first_sentence_ms"]])
                ),
                total=cell(mean_or_none([r["total_ms"] for r in mode_rows])),
                chars=cell(mean_or_none([float(r["chars"]) for r in mode_rows]), 0),
                out=cell(mean_or_none([float(r["output_tokens"]) for r in mode_rows]), 0),
                usd=f"{cost:.6f}",
                krw=f"{cost * rate:.2f}",
            )
        )

    lines += [
        "",
        "## 발화별 상세",
        "",
        "| 모드 | 발화 | 상태 | TTFT(ms) | 첫 문장(ms) | 완료(ms) | 글자수 | 문장수 | in tok | out tok | USD | KRW |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {mode} | {utterance} | {status} | {ttft} | {first} | {total} | {chars} | {sentences} "
            "| {in_tok} | {out_tok} | {usd} | {krw} |".format(
                mode=row["mode"],
                utterance=str(row["utterance"]).replace("|", "/"),
                status=row["status"] if row["status"] == "ok" else f"error ({row['error'][:40]})",
                ttft=cell(row["ttft_ms"]),
                first=cell(row["first_sentence_ms"]),
                total=cell(row["total_ms"]),
                chars=row["chars"],
                sentences=row["sentences"],
                in_tok=row["input_tokens"],
                out_tok=row["output_tokens"],
                usd=f"{row['cost_usd']:.6f}",
                krw=f"{row['cost_usd'] * rate:.2f}",
            )
        )

    if skipped:
        lines += ["", "## SKIP", "", "| 모드 | 사유 |", "| --- | --- |"]
        for entry in skipped:
            lines.append(f"| {entry['mode']} | {entry['reason']} |")

    lines += [
        "",
        "> 요금은 llm_modes.json의 pricing_usd_per_mtok 기준 추정치다. 토큰 사용량을 돌려주지",
        "> 않는 엔드포인트는 0으로 집계되므로 비용 칸도 0이 된다.",
        "",
    ]
    return "\n".join(lines)


def render_responses(rows: list[dict[str, object]]) -> str:
    lines = ["# 모드별 응답 전문 (페르소나 순응도 수동 평가용)", ""]
    for row in rows:
        lines += [
            f"## [{row['mode']}] {row['utterance']}",
            "",
            f"- 모델: `{row['model']}` / 상태: {row['status']}",
            f"- TTFT {cell(row['ttft_ms'])}ms / 첫 문장 {cell(row['first_sentence_ms'])}ms / 완료 {cell(row['total_ms'])}ms",
            "",
            "```",
            str(row["answer"]).strip() or (row["error"] or "(빈 응답)"),
            "```",
            "",
        ]
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> int:
    config = load_llm_config(args.config) if args.config else load_llm_config()
    persona = load_persona_prompt()
    chunker_options = sentence_chunker_options(config)
    rate = krw_per_usd(config)
    modes = config.get("modes") or {}

    bench = config.get("bench") or {}
    utterances = list(bench.get("utterances") or [])
    if args.utterances_file:
        utterances = [
            line.strip()
            for line in Path(args.utterances_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if not utterances:
        print("error: no bench utterances configured", file=sys.stderr)
        return 2

    requested = args.modes or list(modes)
    rows: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    codex_spawn: dict[str, object] | None = None
    if any(
        str((modes.get(mode) or {}).get("provider", "")).lower() == "codex-cli"
        for mode in requested
    ):
        codex_spawn = await measure_codex_spawn_overhead()
        if codex_spawn:
            print(
                f"codex spawn overhead: min {codex_spawn['min_ms']}ms / "
                f"mean {codex_spawn['mean_ms']}ms",
                flush=True,
            )

    async with httpx.AsyncClient() as client:
        for mode in requested:
            mode_config = modes.get(mode)
            if not isinstance(mode_config, dict):
                skipped.append({"mode": mode, "reason": "llm_modes.json에 없는 모드"})
                continue
            missing = missing_llm_credential(mode_config)
            if missing:
                skipped.append({"mode": mode, "reason": f"{missing} 미설정/미설치"})
                print(f"SKIP {mode}: {missing} is not available", flush=True)
                continue
            for utterance in utterances:
                for attempt in range(args.repeat):
                    row = await run_case(
                        mode, mode_config, utterance, persona, chunker_options, client
                    )
                    row["attempt"] = attempt + 1
                    rows.append(row)
                    print(
                        f"{mode:<7} run{attempt + 1} ttft={cell(row['ttft_ms'])}ms "
                        f"first={cell(row['first_sentence_ms'])}ms total={cell(row['total_ms'])}ms "
                        f"chars={row['chars']} :: {utterance}",
                        flush=True,
                    )

    if not rows:
        print("error: every requested mode was skipped", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else MODULE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"bench-llm-modes-{stamp}"

    (stem.with_suffix(".md")).write_text(
        render_markdown(rows, skipped, rate, args.repeat, codex_spawn), encoding="utf-8"
    )
    (stem.with_suffix(".json")).write_text(
        json.dumps(
            {
                "krw_per_usd": rate,
                "repeat": args.repeat,
                "codex_spawn_overhead": codex_spawn,
                "skipped": skipped,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    responses_path = stem.parent / f"{stem.name}-responses.md"
    responses_path.write_text(render_responses(rows), encoding="utf-8")

    print("")
    print(render_markdown(rows, skipped, rate, args.repeat, codex_spawn))
    print(f"saved: {stem.with_suffix('.md')}")
    print(f"saved: {stem.with_suffix('.json')}")
    print(f"saved: {responses_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modes", nargs="*", help="modes to bench (default: every mode in the config)")
    parser.add_argument("--repeat", type=int, default=1, help="runs per utterance (default: 1)")
    parser.add_argument("--config", help="path to an alternative llm_modes.json")
    parser.add_argument("--utterances-file", help="newline-separated utterances to use instead of the config")
    parser.add_argument("--out-dir", help="where to write the report (default: next to this script)")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
