"""Privacy-preserving local usage ledger for cloud chat providers.

The ledger deliberately contains only operational metadata.  Prompts,
responses, request headers, and API keys must never be passed to this module.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class UsageRecord:
    provider: str
    model: str
    started_at: str
    ended_at: str
    duration_ms: int
    status: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class UsageLedger:
    """A tiny SQLite append-only ledger; callers may safely ignore its errors."""

    def __init__(self, path: str | Path):
        self.path = str(path)

    def record(self, record: UsageRecord) -> None:
        # A short-lived connection is safe across async tasks and worker threads.
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS provider_usage (
                id INTEGER PRIMARY KEY, provider TEXT NOT NULL, model TEXT NOT NULL,
                started_at TEXT NOT NULL, ended_at TEXT NOT NULL, duration_ms INTEGER NOT NULL,
                status TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
                cache_read_tokens INTEGER, cache_write_tokens INTEGER)""")
            db.execute("""INSERT INTO provider_usage
                (provider, model, started_at, ended_at, duration_ms, status, input_tokens,
                 output_tokens, cache_read_tokens, cache_write_tokens)
                VALUES (:provider, :model, :started_at, :ended_at, :duration_ms, :status,
                 :input_tokens, :output_tokens, :cache_read_tokens, :cache_write_tokens)""", asdict(record))
            db.commit()
        finally:
            db.close()

    def records(self) -> list[UsageRecord]:
        if not Path(self.path).exists():
            return []
        db = sqlite3.connect(self.path)
        try:
            rows = db.execute("SELECT provider, model, started_at, ended_at, duration_ms, status, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens FROM provider_usage ORDER BY id").fetchall()
        finally:
            db.close()
        return [UsageRecord(*row) for row in rows]


def calculate_cost(record: UsageRecord, prices: Mapping[str, Mapping[str, float]]) -> float | None:
    """Return cost for a record from per-million-token prices, or None if unknown."""
    price = prices.get(record.model)
    if price is None:
        return None
    # Missing usage is intentionally not invented; a known zero is billable at zero.
    input_tokens = record.input_tokens
    output_tokens = record.output_tokens
    if input_tokens is None or output_tokens is None:
        return None
    # OpenAI reports cached tokens as a subset of prompt_tokens, whereas
    # Anthropic reports cache read/creation tokens alongside uncached input.
    # Split the OpenAI total so cache hits are not charged twice.
    uncached_input = input_tokens
    if record.provider == "openai":
        uncached_input = max(0, input_tokens - (record.cache_read_tokens or 0))
    return ((uncached_input * price.get("input", 0.0)) +
            (output_tokens * price.get("output", 0.0)) +
            ((record.cache_read_tokens or 0) * price.get("cache_read", 0.0)) +
            ((record.cache_write_tokens or 0) * price.get("cache_write", 0.0))) / 1_000_000


def report(records: list[UsageRecord], prices: Mapping[str, Mapping[str, float]]) -> list[dict[str, Any]]:
    """Return one serializable, cost-annotated row per call without mutating storage."""
    rows = []
    for record in records:
        cost = calculate_cost(record, prices)
        rows.append(asdict(record) | {
            "cost": cost,
            "cost_status": "known" if cost is not None else "unknown",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Report a local provider usage ledger")
    parser.add_argument("report", nargs="?", default="report")
    parser.add_argument("--db", required=True, help="SQLite ledger path")
    parser.add_argument("--prices", default="{}", help="JSON model -> per-million-token price table")
    args = parser.parse_args()
    print(json.dumps(report(UsageLedger(args.db).records(), json.loads(args.prices)), ensure_ascii=False))


if __name__ == "__main__":
    main()
