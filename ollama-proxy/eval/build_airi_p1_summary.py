"""Build a content-safe, deterministic P1 evaluation summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from model_usage_manifest import CANDIDATES, canonical_json_bytes, canonical_sha256, file_sha256, validate_complete_set


SCHEMA_VERSION = "airi.p1-summary.v1"
CLASSIFICATION_SCHEMA_VERSION = "airi.p1-classification.v1"
RESULT_SCHEMA_VERSION = "airi.p1-result.v1"
PROFILES = ("native", "common")
STATUSES = {"actually_run", "unrunnable", "blocked", "pending"}
_FORBIDDEN_KEY_PARTS = ("raw", "output", "response", "completion", "prompt", "message", "text", "score", "rating", "rank", "preference")


class SummaryValidationError(ValueError):
    """Raised when P1 input cannot produce an unambiguous safe matrix."""


def _fail(message: str) -> None:
    raise SummaryValidationError(message)


def _load_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"{path}: invalid JSON: {exc}")


def _safe_metrics(value: Any, path: str = "measured") -> Any:
    if isinstance(value, dict):
        result = {}
        for key in sorted(value):
            if not isinstance(key, str) or any(part in key.lower() for part in _FORBIDDEN_KEY_PARTS):
                _fail(f"{path}: forbidden content or human-score key {key!r}")
            result[key] = _safe_metrics(value[key], f"{path}.{key}")
        return result
    if isinstance(value, list):
        return [_safe_metrics(item, path) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    _fail(f"{path}: must contain JSON scalar, arrays, or objects")


def _load_manifests(paths: Sequence[str | Path]) -> dict[str, dict[str, Any]]:
    documents = [_load_json(path) for path in paths]
    checked = validate_complete_set(documents)
    if len(paths) != len(CANDIDATES):
        _fail("exactly six manifest paths are required")
    by_id = {}
    for path, manifest in zip(paths, checked):
        candidate = manifest["candidate_id"]
        if candidate in by_id:
            _fail(f"duplicate manifest candidate {candidate}")
        by_id[candidate] = {
            "path": str(Path(path)),
            "file_sha256": file_sha256(path),
            "canonical_sha256": canonical_sha256(manifest),
            "exact_revision": manifest["exact_revision"],
        }
    return by_id


def _parse_classifications(document: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    if set(document) != {"schema_version", "profiles"} or document["schema_version"] != CLASSIFICATION_SCHEMA_VERSION:
        _fail("classification must contain only schema_version and profiles")
    entries = document["profiles"]
    if not isinstance(entries, list):
        _fail("classification.profiles must be an array")
    result = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"candidate_id", "profile", "status", "reasons"}:
            _fail("each classification must contain candidate_id, profile, status, reasons")
        candidate, profile, status, reasons = entry["candidate_id"], entry["profile"], entry["status"], entry["reasons"]
        if candidate not in CANDIDATES or profile not in PROFILES or status not in STATUSES - {"actually_run"}:
            _fail("classification has unknown candidate/profile or invalid missing-run status")
        if not isinstance(reasons, list) or any(not isinstance(reason, str) or not reason for reason in reasons):
            _fail("classification reasons must be non-empty strings")
        key = (candidate, profile)
        if key in result:
            _fail(f"duplicate classification for {candidate}/{profile}")
        result[key] = {"status": status, "reasons": sorted(reasons)}
    return result


def _load_results(paths: Sequence[str | Path], manifests: Mapping[str, Mapping[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    results = {}
    required = {"schema_version", "candidate_id", "profile", "manifest_file_sha256", "manifest_canonical_sha256", "measured", "reasons"}
    for path in paths:
        item = _load_json(path)
        if not isinstance(item, dict) or set(item) != required or item["schema_version"] != RESULT_SCHEMA_VERSION:
            _fail(f"{path}: result has an invalid schema or raw-output-bearing extra key")
        candidate, profile = item["candidate_id"], item["profile"]
        if candidate not in manifests or profile not in PROFILES:
            _fail(f"{path}: unknown candidate/profile")
        provenance = manifests[candidate]
        if item["manifest_file_sha256"] != provenance["file_sha256"] or item["manifest_canonical_sha256"] != provenance["canonical_sha256"]:
            _fail(f"{path}: manifest hashes do not match {candidate}")
        if not isinstance(item["reasons"], list) or any(not isinstance(reason, str) or not reason for reason in item["reasons"]):
            _fail(f"{path}: reasons must be non-empty strings")
        key = (candidate, profile)
        if key in results:
            _fail(f"duplicate result for {candidate}/{profile}")
        results[key] = {"status": "actually_run", "reasons": sorted(item["reasons"]), "measured": _safe_metrics(item["measured"])}
    return results


def build_summary(manifest_paths: Sequence[str | Path], result_paths: Sequence[str | Path], classification: Mapping[str, Any], concurrent_gpu_load: Any) -> dict[str, Any]:
    """Return the P1 matrix; missing runs must be explicitly classified."""
    manifests = _load_manifests(manifest_paths)
    classified = _parse_classifications(classification)
    results = _load_results(result_paths, manifests)
    rows = []
    for candidate in sorted(CANDIDATES):
        profile_rows = []
        for profile in PROFILES:
            key = (candidate, profile)
            if key in results:
                if key in classified:
                    _fail(f"{candidate}/{profile}: cannot have result and missing-run classification")
                value = results[key]
            else:
                if key not in classified:
                    _fail(f"{candidate}/{profile}: missing required classification")
                value = {**classified[key], "measured": {}}
            profile_rows.append({"profile": profile, **value})
        rows.append({"candidate_id": candidate, "manifest": manifests[candidate], "profiles": profile_rows})
    unknown = set(classified) - {(candidate, profile) for candidate in CANDIDATES for profile in PROFILES}
    if unknown:
        _fail("classification contains unknown matrix entry")
    return {"schema_version": SCHEMA_VERSION, "concurrent_gpu_load": _safe_metrics(concurrent_gpu_load, "concurrent_gpu_load"), "candidates": rows}


def write_summary_atomic(output: str | Path, summary: Mapping[str, Any]) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=f".{target.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(canonical_json_bytes(summary) + b"\n")
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _cli_classification(statuses: Sequence[str], reasons: Sequence[str]) -> dict[str, Any]:
    """Translate repeatable candidate:profile:value CLI declarations."""
    values: dict[tuple[str, str], dict[str, Any]] = {}
    for declaration in statuses:
        try:
            candidate, profile, status = declaration.split(":", 2)
        except ValueError:
            _fail("--profile-status must be candidate:profile:status")
        if candidate not in CANDIDATES or profile not in PROFILES or status not in STATUSES - {"actually_run"}:
            _fail("--profile-status has unknown candidate/profile or invalid status")
        key = (candidate, profile)
        if key in values:
            _fail(f"duplicate --profile-status for {candidate}/{profile}")
        values[key] = {"candidate_id": candidate, "profile": profile, "status": status, "reasons": []}
    for declaration in reasons:
        try:
            candidate, profile, reason = declaration.split(":", 2)
        except ValueError:
            _fail("--profile-reason must be candidate:profile:reason")
        key = (candidate, profile)
        if key not in values or not reason:
            _fail("--profile-reason must follow a matching --profile-status")
        values[key]["reasons"].append(reason)
    return {"schema_version": CLASSIFICATION_SCHEMA_VERSION, "profiles": list(values.values())}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--result", action="append", default=[])
    parser.add_argument("--classification")
    parser.add_argument("--profile-status", action="append", default=[], metavar="CANDIDATE:PROFILE:STATUS")
    parser.add_argument("--profile-reason", action="append", default=[], metavar="CANDIDATE:PROFILE:REASON")
    parser.add_argument("--concurrent-gpu-load", required=True, help="JSON annotation, not a model-size inference")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if bool(args.classification) == bool(args.profile_status):
            _fail("provide exactly one of --classification or --profile-status")
        classification = _load_json(args.classification) if args.classification else _cli_classification(args.profile_status, args.profile_reason)
        summary = build_summary(args.manifest, args.result, classification, json.loads(args.concurrent_gpu_load))
        write_summary_atomic(args.output, summary)
    except (SummaryValidationError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
