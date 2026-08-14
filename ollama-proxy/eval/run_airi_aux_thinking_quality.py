"""Run isolated common-Ollama thinking quality rows for Qwen3 and Granite.

These rows are auxiliary quality observations only.  They are never consumed
as AIRI history, P5 proxy latency, or production-context measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest
from run_airi_baseline import build_case_system_prompt, load_system_prompt
from run_airi_candidate_baseline import (
    FIXTURE,
    RunnerError,
    _fixture,
    _read_stream,
    _request,
    _require_loopback,
    _safe_show,
    _score,
    local_ollama_transport,
)


SCHEMA_VERSION = "airi.aux-thinking-quality.v1"
CASE_COUNT = 16
MODEL_OPTIONS: dict[str, dict[str, float | int]] = {
    "qwen3-4b": {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0},
    # The pinned Granite card does not publish thinking-mode sampling values.
    "granite-3.3-2b-instruct": {},
}


class ThinkingQualityError(ValueError):
    pass


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        staged = Path(handle.name)
    os.replace(staged, target)


def _summary_options(candidate_id: str) -> dict[str, Any]:
    options = MODEL_OPTIONS[candidate_id]
    if options:
        return dict(options)
    return {
        "unsupported_options": ["temperature", "top_p", "top_k", "min_p"],
        "reason": "official thinking-mode sampling is unknown in the pinned manifest",
    }


def run_thinking_quality(
    *,
    manifest_path: str | Path,
    runtime_model: str,
    expected_digest: str,
    report_path: str | Path,
    endpoint: str = "http://127.0.0.1:11434",
    fixture_path: str | Path = FIXTURE,
    transport=local_ollama_transport,
    num_predict: int = 1024,
) -> dict[str, Any]:
    _require_loopback(endpoint)
    if len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest):
        raise ThinkingQualityError("expected digest must be lowercase 64-hex")
    manifest_file = Path(manifest_path)
    manifest = validate_manifest(json.loads(manifest_file.read_text(encoding="utf-8")))
    candidate_id = manifest["candidate_id"]
    if candidate_id not in MODEL_OPTIONS:
        raise ThinkingQualityError("only Qwen3 and Granite have auxiliary thinking rows")
    if not isinstance(num_predict, int) or not 256 <= num_predict <= 4096:
        raise ThinkingQualityError("num_predict must be an integer from 256 through 4096")
    fixture, fixture_sha256 = _fixture(Path(fixture_path))
    tags = _request(transport, "GET", endpoint, "/api/tags")
    installed = next(
        (
            item
            for item in tags.get("models", [])
            if isinstance(item, dict) and item.get("name") == runtime_model
        ),
        None,
    )
    if not isinstance(installed, dict) or installed.get("digest") != expected_digest:
        raise ThinkingQualityError("/api/tags exact runtime digest mismatch")
    show = _request(transport, "POST", endpoint, "/api/show", {"name": runtime_model})
    if not isinstance(show, dict) or show.get("digest") not in {None, expected_digest}:
        raise ThinkingQualityError("/api/show conflicts with the pinned runtime digest")

    options: dict[str, Any] = {
        "num_ctx": 2048,
        "num_predict": num_predict,
        **MODEL_OPTIONS[candidate_id],
    }
    system_prompt = load_system_prompt()
    rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "incomplete",
        "scope": "auxiliary_common_ollama_thinking_only_not_history_P5_or_latency",
        "candidate_id": candidate_id,
        "profile": "common",
        "runtime_model": runtime_model,
        "expected_digest": expected_digest,
        "manifest": {
            "file_sha256": file_sha256(manifest_file),
            "canonical_sha256": canonical_sha256(manifest),
        },
        "fixture": {"sha256": fixture_sha256, "case_count": CASE_COUNT},
        "system_prompt_sha256": _hash(system_prompt),
        "think": True,
        "runs_per_case": 1,
        "sampling": _summary_options(candidate_id),
        "requested_options": options,
        "runtime_show": _safe_show(show),
        "rows": rows,
    }
    _atomic(report_path, report)
    try:
        for case in fixture["cases"]:
            case_system = build_case_system_prompt(system_prompt, case)
            payload = {
                "model": runtime_model,
                "messages": [{"role": "system", "content": case_system}, *case["messages"]],
                "stream": True,
                "think": True,
                "keep_alive": "30m",
                "options": options,
            }
            text, timing = _read_stream(
                _request(transport, "POST", endpoint, "/api/chat", payload), runtime_model
            )
            rows.append(
                {
                    "case_id": case["id"],
                    "response": {"sha256": _hash(text), "char_count": len(text)},
                    "checks": _score(text, case["checks"]),
                    "timing": timing,
                }
            )
            _atomic(report_path, report)
        _request(
            transport,
            "POST",
            endpoint,
            "/api/generate",
            {"model": runtime_model, "keep_alive": 0, "stream": False, "prompt": ""},
        )
        report["status"] = "complete"
        report["cleanup"] = {"requested_keep_alive_zero": True}
    except (OSError, TypeError, ValueError, RunnerError) as exc:
        report["status"] = "error"
        report["error"] = str(exc)
    _atomic(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--runtime-model", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--fixture", default=str(FIXTURE))
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--report", required=True)
    parser.add_argument("--num-predict", type=int, default=1024)
    args = parser.parse_args(argv)
    result = run_thinking_quality(
        manifest_path=args.manifest,
        runtime_model=args.runtime_model,
        expected_digest=args.expected_digest,
        fixture_path=args.fixture,
        endpoint=args.endpoint,
        report_path=args.report,
        num_predict=args.num_predict,
    )
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
