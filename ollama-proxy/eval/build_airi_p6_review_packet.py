"""Create deterministic blinded P6 Korean dialogue review packets without inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from model_usage_manifest import CANDIDATES, canonical_json_bytes, canonical_sha256, file_sha256, validate_complete_set


CAPTURE_SCHEMA_VERSION = "airi.p6-safe-korean-broadcast-capture.v1"
PACKET_SCHEMA_VERSION = "airi.p6-anonymized-review-packet.v1"
KEY_SCHEMA_VERSION = "airi.p6-review-key.v1"
PROFILES = ("native", "common")
UNAVAILABLE = {"blocked", "unrunnable"}
_HANGUL = re.compile(r"[가-힣]")
_EXTERNAL = re.compile(r"https?://|www\.|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|\b\d{2,3}[- ]?\d{3,4}[- ]?\d{4}\b|\b(?:\d{1,3}\.){3}\d{1,3}\b", re.I)
_CONTROL = re.compile(r"<\||\|>|</?s>|\[/?INST\]|<\|im_|<\|end", re.I)
_UNSAFE = re.compile(r"jailbreak|prompt injection|ignore (?:all )?(?:previous|prior) instructions|성적|섹스|자살 방법|폭탄 제조|욕설|씨발|개새끼", re.I)


class ReviewPacketValidationError(ValueError):
    """Raised for unsafe, incomplete, or non-blind review input."""


def _fail(message: str) -> None:
    raise ReviewPacketValidationError(message)


def _load(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"{path}: invalid JSON: {exc}")


def _validate_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label}: must be a non-empty string")
    if not _HANGUL.search(value):
        _fail(f"{label}: must be Korean broadcast dialogue")
    if _EXTERNAL.search(value):
        _fail(f"{label}: external or personal data is not allowed")
    if _CONTROL.search(value):
        _fail(f"{label}: control-token payload is not allowed")
    if _UNSAFE.search(value):
        _fail(f"{label}: unsafe category, jailbreak, sexual, or profanity payload")
    return value


def _manifests(paths: Sequence[str | Path]) -> dict[str, dict[str, str]]:
    if len(paths) != len(CANDIDATES):
        _fail("exactly six manifest paths are required")
    docs = validate_complete_set([_load(path) for path in paths])
    result = {}
    for path, document in zip(paths, docs):
        candidate = document["candidate_id"]
        result[candidate] = {"file_sha256": file_sha256(path), "canonical_sha256": canonical_sha256(document), "exact_revision": document["exact_revision"]}
    return result


def _capture(value: Any, source: str, manifests: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    fields = {"schema_version", "candidate_id", "profile", "status", "manifest_file_sha256", "manifest_canonical_sha256", "turns", "reasons"}
    if not isinstance(value, dict) or set(value) != fields or value.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        _fail(f"{source}: invalid capture schema")
    candidate, profile, status = value["candidate_id"], value["profile"], value["status"]
    if candidate not in manifests or profile not in PROFILES or status not in {"actually_run", *UNAVAILABLE}:
        _fail(f"{source}: unknown candidate/profile or invalid status")
    manifest = manifests[candidate]
    if value["manifest_file_sha256"] != manifest["file_sha256"] or value["manifest_canonical_sha256"] != manifest["canonical_sha256"]:
        _fail(f"{source}: manifest hashes do not match")
    reasons = value["reasons"]
    if not isinstance(reasons, list) or any(not isinstance(reason, str) or not reason for reason in reasons):
        _fail(f"{source}: reasons must be non-empty strings")
    turns = value["turns"]
    if not isinstance(turns, list):
        _fail(f"{source}: turns must be an array")
    if status in UNAVAILABLE:
        if turns:
            _fail(f"{source}: unavailable capture cannot contain dialogue")
        if not reasons:
            _fail(f"{source}: unavailable capture needs a reason")
        return {"candidate_id": candidate, "profile": profile, "status": status, "turns": [], "reasons": sorted(reasons)}
    if reasons:
        _fail(f"{source}: actually_run capture must not carry classification reasons")
    if len(turns) != 20:
        _fail(f"{source}: actually_run capture must contain exactly 20 turns")
    checked = []
    for turn in turns:
        if not isinstance(turn, dict) or set(turn) != {"turn", "prompt", "response"} or not isinstance(turn["turn"], int):
            _fail(f"{source}: turn must contain only turn, prompt, response")
        checked.append({"turn": turn["turn"], "prompt": _validate_text(turn["prompt"], f"{source}.prompt"), "response": _validate_text(turn["response"], f"{source}.response")})
    if {turn["turn"] for turn in checked} != set(range(1, 21)):
        _fail(f"{source}: turns must be uniquely numbered 1 through 20")
    return {"candidate_id": candidate, "profile": profile, "status": status, "turns": sorted(checked, key=lambda item: item["turn"]), "reasons": []}


def _anonymous_id(seed: str, candidate: str, profile: str) -> str:
    return "S-" + hashlib.sha256(f"{seed}\0{candidate}\0{profile}".encode("utf-8")).hexdigest()[:12].upper()


def _atomic_json(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=f".{target.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(canonical_json_bytes(value) + b"\n")
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def build_review_packet(manifest_paths: Sequence[str | Path], capture_paths: Sequence[str | Path], blind_seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return public packet and private key; blind_seed is never copied to either."""
    if not isinstance(blind_seed, str) or not blind_seed:
        _fail("a non-empty blind seed is required")
    manifests = _manifests(manifest_paths)
    captures = [_capture(_load(path), str(path), manifests) for path in capture_paths]
    by_key = {(item["candidate_id"], item["profile"]): item for item in captures}
    if len(by_key) != len(captures):
        _fail("duplicate candidate/profile capture")
    if set(by_key) != {(candidate, profile) for candidate in CANDIDATES for profile in PROFILES}:
        _fail("captures must provide every candidate/native and candidate/common row")
    # Seed-ranked candidates, then alternate profiles; this counterbalances profile order.
    candidates = sorted(CANDIDATES, key=lambda candidate: hashlib.sha256(f"{blind_seed}\0{candidate}".encode()).hexdigest())
    rows, key_rows = [], []
    for index, candidate in enumerate(candidates):
        profiles = PROFILES if index % 2 == 0 else tuple(reversed(PROFILES))
        for profile in profiles:
            capture = by_key[(candidate, profile)]
            anonymous_id = _anonymous_id(blind_seed, candidate, profile)
            public = {"sample_id": anonymous_id, "profile_order": len(rows) + 1, "status": capture["status"], "reasons": capture["reasons"], "rubric": {"helpfulness": "", "persona_consistency": "", "broadcast_safety": "", "reviewer_notes": ""}}
            if capture["status"] == "actually_run":
                public["dialogue"] = [{"turn": turn["turn"], "prompt": turn["prompt"], "response": turn["response"]} for turn in capture["turns"]]
            else:
                public["dialogue"] = []
            rows.append(public)
            key_rows.append({"sample_id": anonymous_id, "candidate_id": candidate, "profile": profile, "manifest_file_sha256": manifests[candidate]["file_sha256"], "manifest_canonical_sha256": manifests[candidate]["canonical_sha256"], "exact_revision": manifests[candidate]["exact_revision"]})
    seed_hash = hashlib.sha256(blind_seed.encode("utf-8")).hexdigest()
    return ({"schema_version": PACKET_SCHEMA_VERSION, "blind_seed_sha256": seed_hash, "rubric": "Blank fields only: assess helpfulness, persona consistency, and broadcast safety; do not add rankings or raw hidden metadata.", "samples": rows}, {"schema_version": KEY_SCHEMA_VERSION, "blind_seed_sha256": seed_hash, "mappings": sorted(key_rows, key=lambda item: item["sample_id"])})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--capture", action="append", required=True)
    parser.add_argument("--blind-seed", required=True)
    parser.add_argument("--packet-output", required=True)
    parser.add_argument("--key-output", required=True)
    args = parser.parse_args(argv)
    try:
        packet, key = build_review_packet(args.manifest, args.capture, args.blind_seed)
        _atomic_json(args.packet_output, packet)
        _atomic_json(args.key_output, key)
    except ReviewPacketValidationError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
