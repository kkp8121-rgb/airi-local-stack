"""Offline validation and canonicalization for local LLM usage manifests.

The validator deliberately fails closed: every documented field is required and
unknown values must be represented by the literal string ``"unknown"``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "airi.local-llm-usage-manifest.v1"
CANDIDATES = {
    "midm-2.0-mini-instruct": "K-intelligence/Midm-2.0-Mini-Instruct",
    "motif-2.6b-v1.1-lc": "Motif-Technologies/Motif-2.6b-v1.1-LC",
    "ministral-3-3b-instruct-2512-bf16": "mistralai/Ministral-3-3B-Instruct-2512-BF16",
    "qwen3-4b": "Qwen/Qwen3-4B",
    "phi-4-mini-instruct": "microsoft/Phi-4-mini-instruct",
    "granite-3.3-2b-instruct": "ibm-granite/granite-3.3-2b-instruct",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_URL = re.compile(r"^https://huggingface\.co/(?:api/models/)?[^\s?#]+(?:/resolve/[0-9a-f]{40}/[^\s?#]+)?$")


class ManifestValidationError(ValueError):
    """Raised when a manifest is incomplete, mutable, or internally unsafe."""


def _fail(path: str, message: str) -> None:
    raise ManifestValidationError(f"{path}: {message}")


def _object(value: Any, path: str, fields: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    actual = set(value)
    missing = fields - actual
    extra = actual - fields
    if missing:
        _fail(path, f"missing required fields: {', '.join(sorted(missing))}")
    if extra:
        _fail(path, f"unknown fields: {', '.join(sorted(extra))}")
    return value


def _string(value: Any, path: str, *, unknown: bool = True) -> str:
    if not isinstance(value, str) or not value:
        _fail(path, "must be a non-empty string")
    if value == "unknown" and unknown:
        return value
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "must be an array (use [] when none are known)")
    return value


def _url(value: Any, path: str, *, artifact: bool = False) -> str:
    value = _string(value, path)
    if value == "unknown":
        return value
    if not _URL.fullmatch(value):
        _fail(path, "must be an immutable https://huggingface.co URL")
    if artifact and "/resolve/" not in value:
        _fail(path, "must contain a full pinned revision in /resolve/<40hex>/")
    return value


def _options(value: Any, path: str) -> Mapping[str, Any]:
    if value == "unknown":
        return {"unknown": "unknown"}
    if not isinstance(value, dict):
        _fail(path, "must be an object or 'unknown'")
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            _fail(path, "option names must be non-empty strings")
        if item is None:
            _fail(f"{path}.{key}", "use 'unknown' rather than null")
    return value


def _profile(value: Any, path: str) -> Mapping[str, Any]:
    fields = {"supported_options", "unsupported"}
    profile = _object(value, path, fields)
    options = _options(profile["supported_options"], f"{path}.supported_options")
    unsupported = _list(profile["unsupported"], f"{path}.unsupported")
    if any(not isinstance(item, str) or not item for item in unsupported):
        _fail(f"{path}.unsupported", "must contain non-empty option names")
    if isinstance(options, dict) and set(options).intersection(unsupported):
        _fail(path, "supported_options cannot collide with unsupported")
    return profile


def _artifact(value: Any, path: str, *, revision: str | None = None) -> Mapping[str, Any]:
    fields = {"path", "kind", "source_url", "sha256", "size", "method"}
    item = _object(value, path, fields)
    for name in ("path", "kind", "method"):
        _string(item[name], f"{path}.{name}")
    source_url = _url(item["source_url"], f"{path}.source_url", artifact=True)
    if source_url == "unknown":
        _fail(f"{path}.source_url", "must be an immutable pinned source URL")
    if revision is not None and f"/resolve/{revision}/" not in source_url:
        _fail(f"{path}.source_url", "must use the manifest exact_revision")
    digest = _string(item["sha256"], f"{path}.sha256", unknown=False)
    if not _SHA256.fullmatch(digest):
        _fail(f"{path}.sha256", "must be lowercase 64-hex")
    if not isinstance(item["size"], int) or item["size"] < 0:
        _fail(f"{path}.size", "must be a non-negative integer")
    return item


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one manifest and return a detached canonical JSON-compatible copy."""
    fields = {
        "schema_version", "candidate_id", "repo_id", "exact_revision", "retrieved_at",
        "official_model_info", "license", "libraries", "remote_code", "tokenizer",
        "template", "system_role", "thinking", "generation", "context", "runtime",
        "quantization", "engine_support", "artifacts", "status", "reasons", "profiles",
    }
    item = _object(manifest, "manifest", fields)
    if item["schema_version"] != SCHEMA_VERSION:
        _fail("manifest.schema_version", f"must equal {SCHEMA_VERSION!r}")
    candidate = _string(item["candidate_id"], "manifest.candidate_id", unknown=False)
    if candidate not in CANDIDATES:
        _fail("manifest.candidate_id", "is not one of the fixed six candidates")
    if item["repo_id"] != CANDIDATES[candidate]:
        _fail("manifest.repo_id", "does not match candidate_id")
    revision = _string(item["exact_revision"], "manifest.exact_revision", unknown=False)
    if not _REVISION.fullmatch(revision):
        _fail("manifest.exact_revision", "must be a full lowercase 40-hex commit")
    stamp = _string(item["retrieved_at"], "manifest.retrieved_at", unknown=False)
    if not _UTC.fullmatch(stamp):
        _fail("manifest.retrieved_at", "must be a UTC ISO-8601 timestamp ending in Z")
    try:
        datetime.fromisoformat(stamp[:-1] + "+00:00")
    except ValueError:
        _fail("manifest.retrieved_at", "is not a valid timestamp")
    official = _url(item["official_model_info"], "manifest.official_model_info")
    if official != f"https://huggingface.co/api/models/{item['repo_id']}":
        _fail("manifest.official_model_info", "must be the official Hugging Face model-info API URL")

    license_info = _object(item["license"], "manifest.license", {"declared", "license_files", "notice", "public_broadcast_status", "evaluation_allowed"})
    _string(license_info["declared"], "manifest.license.declared")
    license_files = _list(license_info["license_files"], "manifest.license.license_files")
    if any(not isinstance(name, str) or not name for name in license_files):
        _fail("manifest.license.license_files", "must contain non-empty file names")
    _string(license_info["notice"], "manifest.license.notice")
    if license_info["public_broadcast_status"] not in {"allowed", "blocked", "unknown"}:
        _fail("manifest.license.public_broadcast_status", "must be allowed, blocked, or unknown")
    if not isinstance(license_info["evaluation_allowed"], bool):
        _fail("manifest.license.evaluation_allowed", "must be boolean")

    libraries = _object(item["libraries"], "manifest.libraries", {"transformers", "torch", "accelerate", "minimums"})
    for name in ("transformers", "torch", "accelerate"):
        _string(libraries[name], f"manifest.libraries.{name}")
    minimums = _options(libraries["minimums"], "manifest.libraries.minimums")
    if not minimums:
        _fail("manifest.libraries.minimums", "must record versions or 'unknown'")

    remote = _object(item["remote_code"], "manifest.remote_code", {"required", "audited_artifacts", "findings"})
    if not isinstance(remote["required"], bool):
        _fail("manifest.remote_code.required", "must be boolean")
    audited = _list(remote["audited_artifacts"], "manifest.remote_code.audited_artifacts")
    findings = _object(
        remote["findings"],
        "manifest.remote_code.findings",
        {"imports", "network", "shell", "telemetry", "filesystem", "dynamic_execution", "serialization"},
    )
    for name in findings:
        _string(findings[name], f"manifest.remote_code.findings.{name}")
    if remote["required"] and not audited:
        _fail("manifest.remote_code.audited_artifacts", "is required when remote code is required")
    for index, artifact in enumerate(audited):
        checked = _artifact(artifact, f"manifest.remote_code.audited_artifacts[{index}]", revision=revision)
        if not checked["path"].endswith(".py"):
            _fail(f"manifest.remote_code.audited_artifacts[{index}].path", "must pin a .py file")

    for name in ("tokenizer", "template", "system_role", "thinking", "generation", "context", "runtime", "quantization", "engine_support"):
        _options(item[name], f"manifest.{name}")
    artifacts = _list(item["artifacts"], "manifest.artifacts")
    if not artifacts:
        _fail("manifest.artifacts", "must contain pinned provenance artifacts")
    for index, artifact in enumerate(artifacts):
        _artifact(artifact, f"manifest.artifacts[{index}]", revision=revision)
    if item["status"] not in {"READY", "BLOCKED", "UNRUNNABLE"}:
        _fail("manifest.status", "must be READY, BLOCKED, or UNRUNNABLE")
    reasons = _list(item["reasons"], "manifest.reasons")
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        _fail("manifest.reasons", "must contain structured non-empty reason strings")
    if item["status"] != "READY" and not reasons:
        _fail("manifest.reasons", "is required for BLOCKED or UNRUNNABLE")
    if item["status"] == "READY" and not license_info["evaluation_allowed"]:
        _fail("manifest.status", "cannot be READY when local evaluation is not allowed")
    profiles = _object(item["profiles"], "manifest.profiles", {"native", "common"})
    _profile(profiles["native"], "manifest.profiles.native")
    _profile(profiles["common"], "manifest.profiles.common")
    return json.loads(canonical_json_bytes(dict(item)).decode("utf-8"))


def validate_complete_set(documents: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate manifests as the exact fixed six-candidate set."""
    ids: set[str] = set()
    validated = []
    for index, manifest in enumerate(documents):
        checked = validate_manifest(manifest)
        if checked["candidate_id"] in ids:
            _fail(f"manifests[{index}].candidate_id", "is duplicated")
        ids.add(checked["candidate_id"])
        validated.append(checked)
    if ids != set(CANDIDATES):
        _fail("manifests", "must contain the exact fixed six-candidate set")
    return validated


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return canonical UTF-8 JSON; object insertion order never affects it."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_paths(paths: Iterable[str | Path], *, require_complete_set: bool = False) -> dict[str, Any]:
    """Verify all paths before returning a deterministic all-or-nothing summary."""
    path_values = list(paths)
    results = []
    for raw_path in path_values:
        path = Path(raw_path)
        source = path.read_bytes()
        try:
            parsed = json.loads(source.decode("utf-8"))
            checked = validate_manifest(parsed)
            results.append({"path": str(path), "file_sha256": file_sha256(path), "canonical_sha256": canonical_sha256(checked), "status": "valid"})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ManifestValidationError) as exc:
            results.append({"path": str(path), "status": "invalid", "error": str(exc)})
    results.sort(key=lambda result: result["path"])
    valid = all(result["status"] == "valid" for result in results)
    if require_complete_set and valid:
        try:
            by_path = {str(Path(path)): json.loads(Path(path).read_text(encoding="utf-8")) for path in path_values}
            validate_complete_set(by_path.values())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ManifestValidationError) as exc:
            valid = False
            results.append({"path": "<complete-set>", "status": "invalid", "error": str(exc)})
            results.sort(key=lambda result: result["path"])
    return {"schema_version": SCHEMA_VERSION, "valid": valid, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pinned local LLM usage manifests offline.")
    parser.add_argument("paths", nargs="+", help="JSON manifest or collection paths")
    parser.add_argument("--require-complete-set", action="store_true", help="require exactly the fixed six candidates")
    args = parser.parse_args(argv)
    summary = verify_paths(args.paths, require_complete_set=args.require_complete_set)
    sys.stdout.buffer.write(canonical_json_bytes(summary) + b"\n")
    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
