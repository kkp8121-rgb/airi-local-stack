"""Interactive local curation of untrusted discovery evidence."""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TextIO

from topic_discovery_contract import (
    load_curated_pending,
    load_raw,
    materialize_curations,
    source_metadata,
    validate_curation,
)
from topic_review_contract import (
    OwnershipLock,
    TopicReviewError,
    atomic_write_jsonl,
    canonical_jsonl_bytes,
    read_jsonl,
    record_sha256,
    review_input_path,
    review_output_path,
    validate_pending_record,
)

Input = Callable[[str], str]


def _ask(prompt: str, input_fn: Input) -> str | None:
    try:
        return input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def _show_evidence(raw: dict, output: TextIO) -> None:
    for key in (
        "source_title", "source_snippet", "source", "source_url", "published_at",
        "discovered_at", "license",
    ):
        print(f"{key}: {raw[key]}", file=output)


def _show_confirmation(raw: dict, pending: dict | None, output: TextIO) -> None:
    print(f"source_title: {raw['source_title']}", file=output)
    print(f"source_url: {raw['source_url']}", file=output)
    print(
        f"source_metadata_sha256: {record_sha256(source_metadata(raw))}",
        file=output,
    )
    if pending is not None:
        print(f"pending_title: {pending['title']}", file=output)
        print(f"pending_summary: {pending['summary']}", file=output)
        print(f"pending_broadcast_line: {pending['broadcast_line']}", file=output)


def _cancelled(pending_count: int, output: TextIO) -> int:
    print(
        json.dumps(
            {"status": "cancelled", "pending_count": pending_count},
            separators=(",", ":"),
        ),
        file=output,
    )
    return 0


def _curation(
    raw: dict,
    curator: str,
    disposition: str,
    notes: str,
    pending: dict | None,
) -> dict:
    curation = {
        "curation_schema_version": 1,
        "discovery_id": raw["discovery_id"],
        "raw_record_sha256": record_sha256(raw),
        "source_metadata_sha256": record_sha256(source_metadata(raw)),
        "disposition": disposition,
        "notes": notes,
        "pending_record": pending,
        "pending_record_sha256": record_sha256(pending) if pending else None,
        "curator": curator,
        "curated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    return validate_curation(curation, raw)


def _pending(raw: dict, values: list[str]) -> dict:
    return validate_pending_record({
        "pending_schema_version": 1,
        "id": values[0],
        "title": values[1],
        "source": raw["source"],
        "source_url": raw["source_url"],
        "published_at": raw["published_at"],
        "summary": values[2],
        "broadcast_line": values[3],
        "expires_at": values[4],
        "review": {"status": "pending", "reviewer": "", "reviewed_at": ""},
    })


def run_cli(
    argv: list[str] | None = None,
    *,
    input_fn: Input = input,
    output: TextIO = sys.stdout,
    error: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--source-policies")
    parser.add_argument("--raw-discoveries")
    parser.add_argument("--curations")
    parser.add_argument("--pending")
    parser.add_argument("--curator")
    parser.add_argument("--repair-from-curations", action="store_true")
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown or not all((args.source_policies, args.raw_discoveries, args.curations, args.pending)):
            raise TopicReviewError("invalid request")
        raw = load_raw(args.raw_discoveries, args.source_policies)
        curations_path = review_output_path(args.curations)
        pending_path = review_output_path(args.pending)
        if curations_path == pending_path:
            raise TopicReviewError("invalid request")
        with ExitStack() as locks:
            for target in sorted(
                (curations_path, pending_path),
                key=lambda path: str(path).casefold(),
            ):
                locks.enter_context(OwnershipLock(target))
            if args.repair_from_curations:
                if not curations_path.exists():
                    raise TopicReviewError("partial curation")
                curations = read_jsonl(review_input_path(curations_path))
                materialized = materialize_curations(raw, curations)
                if curations_path.read_bytes() != canonical_jsonl_bytes(curations):
                    raise TopicReviewError("invalid curation")
                if pending_path.exists():
                    loaded = load_curated_pending(
                        args.raw_discoveries,
                        args.source_policies,
                        curations_path,
                        pending_path,
                    )
                    if (
                        loaded != materialized
                        or pending_path.read_bytes()
                        != canonical_jsonl_bytes(materialized)
                    ):
                        raise TopicReviewError("partial curation")
                    print(
                        json.dumps(
                            {
                                "status": "repaired",
                                "pending_count": len(materialized),
                            },
                            separators=(",", ":"),
                        ),
                        file=output,
                    )
                    return 0
                atomic_write_jsonl(pending_path, materialized)
                print(
                    json.dumps(
                        {
                            "status": "repaired",
                            "pending_count": len(materialized),
                        },
                        separators=(",", ":"),
                    ),
                    file=output,
                )
                return 0
            curator = (args.curator or "").strip()
            if not curator:
                raise TopicReviewError("curator required")
            existing = []
            if curations_path.exists() != pending_path.exists():
                raise TopicReviewError("partial curation")
            if curations_path.exists():
                # Existing state must be fully materialized and immutable.
                loaded_pending = load_curated_pending(
                    args.raw_discoveries,
                    args.source_policies,
                    curations_path,
                    pending_path,
                )
                existing = read_jsonl(review_input_path(curations_path))
                if (
                    curations_path.read_bytes() != canonical_jsonl_bytes(existing)
                    or pending_path.read_bytes()
                    != canonical_jsonl_bytes(loaded_pending)
                ):
                    raise TopicReviewError("partial curation")
            curations = list(existing)
            existing_pending_count = sum(
                1 for row in existing if row["disposition"] == "curate"
            )
            stop = False
            for raw_row in raw[len(existing):]:
                _show_evidence(raw_row, output)
                while True:
                    choice = _ask("Disposition [curate/reject/skip]: ", input_fn)
                    if choice is None:
                        return _cancelled(existing_pending_count, output)
                    choice = choice.strip().casefold()
                    if choice == "skip":
                        stop = True
                        break
                    if choice == "reject":
                        notes = _ask("Rejection notes: ", input_fn)
                        if notes is None:
                            return _cancelled(existing_pending_count, output)
                        _show_confirmation(raw_row, None, output)
                        confirm = _ask("Confirm rejection [yes/no]: ", input_fn)
                        if confirm is None or confirm.strip().casefold() not in {
                            "yes",
                            "y",
                        }:
                            return _cancelled(existing_pending_count, output)
                        curations.append(
                            _curation(
                                raw_row,
                                curator,
                                "reject",
                                notes.strip(),
                                None,
                            )
                        )
                        break
                    if choice != "curate":
                        continue
                    values = []
                    for prompt in (
                        "Pending id: ",
                        "Korean title: ",
                        "Summary: ",
                        "Broadcast line: ",
                        "Expires at: ",
                    ):
                        value = _ask(prompt, input_fn)
                        if value is None:
                            return _cancelled(existing_pending_count, output)
                        values.append(value.strip())
                    pending_record = _pending(raw_row, values)
                    _show_confirmation(raw_row, pending_record, output)
                    confirm = _ask("Materialize [yes/no]: ", input_fn)
                    if confirm is None or confirm.strip().casefold() not in {
                        "yes",
                        "y",
                    }:
                        return _cancelled(existing_pending_count, output)
                    curations.append(
                        _curation(raw_row, curator, "curate", "", pending_record)
                    )
                    break
                if stop:
                    break
            pending = materialize_curations(raw, curations)
            if curations != existing:
                atomic_write_jsonl(curations_path, curations)
                atomic_write_jsonl(pending_path, pending)
        print(json.dumps({"status": "curated", "pending_count": len(pending)}, separators=(",", ":")), file=output)
        return 0
    except (OSError, RuntimeError, ValueError, TopicReviewError):
        print('{"status":"rejected"}', file=error)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
