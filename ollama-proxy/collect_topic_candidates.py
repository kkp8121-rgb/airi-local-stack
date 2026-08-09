"""Default-off writer for policy-bound raw topic discoveries only.

There is deliberately no production source or HTTP client in this module.
Reviewed adapters may pass already bounded raw-v1 records to the merge helper.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from topic_review_contract import (
    OwnershipLock,
    TopicReviewError,
    atomic_write_jsonl,
    record_sha256,
    review_output_path,
)
from topic_discovery_contract import load_raw, load_source_policies, validate_raw_record

LOCK_WAIT_SECONDS = 5.0


class CollectionError(ValueError):
    pass


# Compatibility alias used by the ownership-lock regression tests.
_SidecarLock = OwnershipLock


def _existing_raw(path: Path, policies_path: str | Path) -> list[dict[str, Any]]:
    return load_raw(path, policies_path) if path.exists() else []


def collect_raw_discoveries(
    raw_path: str | Path,
    policies_path: str | Path,
    records: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """Atomically merge policy-bound raw discovery rows only."""
    output = review_output_path(raw_path)
    policies = load_source_policies(policies_path)
    candidates = [validate_raw_record(record, policies) for record in records]
    with OwnershipLock(output, wait_seconds=LOCK_WAIT_SECONDS):
        existing = _existing_raw(output, policies_path)
        ids = {row["discovery_id"]: record_sha256(row) for row in existing}
        hashes = {record_sha256(row) for row in existing}
        axes = {(row["source_policy_id"], row["source_url"], row["published_at"]) for row in existing}
        merged = list(existing)
        for row in candidates:
            digest = record_sha256(row)
            axis = (row["source_policy_id"], row["source_url"], row["published_at"])
            if row["discovery_id"] in ids and ids[row["discovery_id"]] != digest:
                raise CollectionError("raw collision")
            if digest not in hashes and axis not in axes:
                merged.append(row); hashes.add(digest); axes.add(axis); ids[row["discovery_id"]] = digest
        if len(merged) != len(existing):
            atomic_write_jsonl(output, merged)
    return {"raw_count": len(merged), "added_count": len(merged) - len(existing)}


def collect_candidates(*_: Any, **__: Any) -> dict[str, int]:
    """Fail closed for the removed direct-to-pending collector API."""
    raise CollectionError("pending collection is disabled")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--enable-collection", action="store_true")
    parser.add_argument("--raw-discoveries")
    parser.add_argument("--source-policies")
    try:
        args, unknown = parser.parse_known_args(argv)
        if not args.enable_collection:
            print('{"status":"disabled","added_count":0,"raw_count":0}')
            return 0
        if unknown or not args.raw_discoveries or not args.source_policies:
            raise CollectionError("invalid request")
        # The standalone CLI has no reviewed adapter or HTTP client. An enabled
        # run therefore remains fail-closed rather than creating an empty file.
        raise CollectionError("source adapter unavailable")
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError, TopicReviewError, json.JSONDecodeError):
        print('{"status":"rejected","added_count":0,"raw_count":0}')
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
