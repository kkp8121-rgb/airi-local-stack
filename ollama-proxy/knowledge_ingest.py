"""Offline approved-knowledge importer.  It never contacts a network or model."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any
from knowledge_store import KnowledgeInputError, KnowledgeStore, runtime_path, validate_record

MAX_INPUT_BYTES = 2_000_000
MAX_RECORDS = 1_000

def load_records(path: Path) -> list[dict[str, Any]]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise KnowledgeInputError("input exceeds byte limit")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        if len(records) > MAX_RECORDS:
            raise KnowledgeInputError("input exceeds record limit")
        return records
    parsed = json.loads(text)
    records = parsed if isinstance(parsed, list) else parsed.get("records", [])
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise KnowledgeInputError("input exceeds record limit")
    return records

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import approved local knowledge (dry-run by default).")
    parser.add_argument("--runtime-dir", default=str(Path(__file__).resolve().parent / "runtime"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--db", default="airi-knowledge.sqlite3")
    parser.add_argument("--apply", action="store_true", help="write validated records; otherwise dry-run")
    args = parser.parse_args(argv)
    try:
        root = Path(args.runtime_dir).resolve()
        input_path = runtime_path(args.input, root)
        if input_path.suffix.lower() not in {".json", ".jsonl"}:
            raise KnowledgeInputError("input must be JSON or JSONL")
        db_path = runtime_path(args.db if Path(args.db).is_absolute() else root / args.db, root)
        records = load_records(input_path)
        if not isinstance(records, list):
            raise KnowledgeInputError("input must be a JSON array/object records or JSONL")
        validated = [validate_record(record) for record in records]
        if not args.apply:
            print(json.dumps({"dry_run": True, "validated": len(validated)}))
            return 0
        store = KnowledgeStore(db_path, runtime_dir=root)
        result = {"inserted": 0, "updated": 0, "duplicate": 0}
        for record in validated:
            result[store.ingest({**record, "approved": True})] += 1
        print(json.dumps({"dry_run": False, **result}))
        return 0
    except (OSError, json.JSONDecodeError, KnowledgeInputError) as exc:
        print(json.dumps({"error": type(exc).__name__}))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
