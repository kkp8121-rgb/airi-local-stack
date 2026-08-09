"""Strict local contracts for reviewed discovery policies and human curation."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from topic_review_contract import (
    CONTROL_RE,
    UNSAFE_TEXT_RE,
    TopicReviewError,
    canonical_json,
    load_pending,
    read_jsonl,
    record_sha256,
    review_input_path,
    validate_pending_record,
)

POLICY_ROOT_FIELDS = {"schema_version", "policies"}
POLICY_FIELDS = {
    "policy_id", "source_kind", "source", "feed_url", "article_host",
    "article_path_prefix", "license", "approved", "reviewer", "reviewed_at",
}
LICENSE_FIELDS = {"spdx", "license_url", "attribution", "attribution_url"}
RAW_FIELDS = {
    "discovery_schema_version", "discovery_id", "source_policy_id",
    "source_kind", "source", "feed_url", "source_url", "published_at",
    "discovered_at", "source_title", "source_snippet", "license",
    "source_body_sha256", "source_policy_sha256",
}
CURATION_FIELDS = {
    "curation_schema_version", "discovery_id", "raw_record_sha256",
    "source_metadata_sha256", "disposition", "notes", "pending_record",
    "pending_record_sha256", "curator", "curated_at",
}
SOURCE_KINDS = {"feed", "article", "notice"}
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
Z_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
PROMPT_RE = re.compile(r"<\||\[\s*(?:system|prompt|tool)\b", re.IGNORECASE)
POLICY_FILE_RE = re.compile(r"source-policies(?:-[A-Za-z0-9._-]+)?\.json\Z")


def _time(value: Any, *, future_rejected: bool = False) -> str:
    if not isinstance(value, str) or not Z_TIME_RE.fullmatch(value):
        raise TopicReviewError("invalid discovery time")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TopicReviewError("invalid discovery time") from exc
    if future_rejected and parsed > datetime.now(timezone.utc):
        raise TopicReviewError("invalid discovery time")
    return value


def _text(value: Any, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > limit
        or CONTROL_RE.search(value)
        or UNSAFE_TEXT_RE.search(value)
        or PROMPT_RE.search(value)
    ):
        raise TopicReviewError("invalid discovery text")
    return value.strip()


def _url(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or CONTROL_RE.search(value)
        or UNSAFE_TEXT_RE.search(value)
    ):
        raise TopicReviewError("invalid discovery url")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise TopicReviewError("invalid discovery url") from exc
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.fragment
        or port is not None
        or host.casefold() == "localhost"
    ):
        raise TopicReviewError("invalid discovery url")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise TopicReviewError("invalid discovery url")
    return value


def discovery_id(policy_id: str, source_url: str, published_at: str) -> str:
    value = {
        "source_policy_id": policy_id,
        "source_url": source_url,
        "published_at": published_at,
    }
    return hashlib.sha256(canonical_json(value)).hexdigest()[:32]


def source_metadata(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: raw[key]
        for key in (
            "source_policy_id", "source_kind", "source", "feed_url",
            "source_url", "published_at", "discovered_at", "source_title",
            "source_snippet", "license", "source_body_sha256",
            "source_policy_sha256",
        )
    }


def load_source_policies(path: str | Path) -> dict[str, dict[str, Any]]:
    policy_path = review_input_path(path)
    if not POLICY_FILE_RE.fullmatch(policy_path.name):
        raise TopicReviewError("invalid source policies")
    try:
        root = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TopicReviewError("invalid source policies") from exc
    if (
        not isinstance(root, dict)
        or set(root) != POLICY_ROOT_FIELDS
        or type(root.get("schema_version")) is not int
        or root["schema_version"] != 1
        or not isinstance(root.get("policies"), list)
    ):
        raise TopicReviewError("invalid source policies")
    result: dict[str, dict[str, Any]] = {}
    for policy in root["policies"]:
        if not isinstance(policy, dict) or set(policy) != POLICY_FIELDS:
            raise TopicReviewError("invalid source policy")
        policy_id = _text(policy["policy_id"], 120)
        if policy_id in result or policy["source_kind"] not in SOURCE_KINDS:
            raise TopicReviewError("invalid source policy")
        _text(policy["source"], 160)
        feed_url = _url(policy["feed_url"])
        article_host = _text(policy["article_host"], 253).casefold()
        if article_host == "localhost":
            raise TopicReviewError("invalid source policy")
        try:
            ipaddress.ip_address(article_host)
        except ValueError:
            pass
        else:
            raise TopicReviewError("invalid source policy")
        prefix = policy["article_path_prefix"]
        if (
            not isinstance(prefix, str)
            or not prefix.startswith("/")
            or "?" in prefix
            or "#" in prefix
            or CONTROL_RE.search(prefix)
            or UNSAFE_TEXT_RE.search(prefix)
        ):
            raise TopicReviewError("invalid source policy")
        license_value = policy["license"]
        if not isinstance(license_value, dict) or set(license_value) != LICENSE_FIELDS:
            raise TopicReviewError("invalid source policy")
        _text(license_value["spdx"], 100)
        _url(license_value["license_url"])
        _text(license_value["attribution"], 300)
        _url(license_value["attribution_url"])
        if policy["approved"] is not True:
            raise TopicReviewError("invalid source policy")
        _text(policy["reviewer"], 500)
        _time(policy["reviewed_at"], future_rejected=True)
        if feed_url != policy["feed_url"]:
            raise TopicReviewError("invalid source policy")
        result[policy_id] = policy
    return result


def policy_sha256(policy: Mapping[str, Any]) -> str:
    return record_sha256(policy)


def validate_raw_record(raw: Any, policies: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if (
        not isinstance(raw, dict)
        or set(raw) != RAW_FIELDS
        or type(raw.get("discovery_schema_version")) is not int
        or raw["discovery_schema_version"] != 1
    ):
        raise TopicReviewError("invalid discovery")
    policy_id = _text(raw["source_policy_id"], 120)
    policy = policies.get(policy_id)
    if policy is None:
        raise TopicReviewError("unknown source policy")
    source_url = _url(raw["source_url"])
    published_at = _time(raw["published_at"])
    discovered_at = _time(raw["discovered_at"], future_rejected=True)
    if published_at > discovered_at:
        raise TopicReviewError("invalid discovery time")
    if raw["discovery_id"] != discovery_id(policy_id, source_url, published_at):
        raise TopicReviewError("invalid discovery")
    if raw["source_policy_sha256"] != policy_sha256(policy):
        raise TopicReviewError("source policy mismatch")
    if (
        raw["source_kind"] != policy["source_kind"]
        or raw["source"] != policy["source"]
        or raw["feed_url"] != policy["feed_url"]
        or raw["license"] != policy["license"]
    ):
        raise TopicReviewError("source policy mismatch")
    parsed = urlsplit(source_url)
    if (
        parsed.hostname is None
        or parsed.hostname.casefold() != policy["article_host"].casefold()
        or not parsed.path.startswith(policy["article_path_prefix"])
    ):
        raise TopicReviewError("source policy mismatch")
    _text(raw["source_title"], 300)
    _text(raw["source_snippet"], 1200)
    if not isinstance(raw["source_body_sha256"], str) or not HASH_RE.fullmatch(raw["source_body_sha256"]):
        raise TopicReviewError("invalid discovery")
    return raw


def load_raw(path: str | Path, policies_path: str | Path) -> list[dict[str, Any]]:
    policies = load_source_policies(policies_path)
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    hashes: set[str] = set()
    axes: set[tuple[str, str, str]] = set()
    for raw in read_jsonl(review_input_path(path)):
        row = validate_raw_record(raw, policies)
        digest = record_sha256(row)
        axis = (row["source_policy_id"], row["source_url"], row["published_at"])
        if row["discovery_id"] in ids or digest in hashes or axis in axes:
            raise TopicReviewError("duplicate discovery")
        ids.add(row["discovery_id"])
        hashes.add(digest)
        axes.add(axis)
        rows.append(row)
    return rows


def validate_curation(curation: Any, raw: Mapping[str, Any]) -> dict[str, Any]:
    if (
        not isinstance(curation, dict)
        or set(curation) != CURATION_FIELDS
        or type(curation.get("curation_schema_version")) is not int
        or curation["curation_schema_version"] != 1
    ):
        raise TopicReviewError("invalid curation")
    if (
        curation["discovery_id"] != raw["discovery_id"]
        or curation["raw_record_sha256"] != record_sha256(raw)
        or curation["source_metadata_sha256"] != record_sha256(source_metadata(raw))
    ):
        raise TopicReviewError("stale curation")
    _text(curation["curator"], 500)
    _time(curation["curated_at"], future_rejected=True)
    disposition = curation["disposition"]
    if (
        disposition not in {"curate", "reject"}
        or not isinstance(curation["notes"], str)
        or len(curation["notes"]) > 500
        or CONTROL_RE.search(curation["notes"])
        or UNSAFE_TEXT_RE.search(curation["notes"])
        or PROMPT_RE.search(curation["notes"])
    ):
        raise TopicReviewError("invalid curation")
    if disposition == "reject":
        _text(curation["notes"], 500)
        if curation["pending_record"] is not None or curation["pending_record_sha256"] is not None:
            raise TopicReviewError("invalid curation")
        return curation
    if curation["notes"]:
        raise TopicReviewError("invalid curation")
    pending = validate_pending_record(curation["pending_record"])
    if (
        pending["source"] != raw["source"]
        or pending["source_url"] != raw["source_url"]
        or pending["published_at"] != raw["published_at"]
        or curation["pending_record_sha256"] != record_sha256(pending)
    ):
        raise TopicReviewError("immutable source mismatch")
    return curation


def materialize_curations(
    raw: list[Mapping[str, Any]],
    curations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(curations) > len(raw):
        raise TopicReviewError("partial curation")
    pending: list[dict[str, Any]] = []
    pending_ids: set[str] = set()
    for index, value in enumerate(curations):
        curation = validate_curation(value, raw[index])
        if curation["discovery_id"] != raw[index]["discovery_id"]:
            raise TopicReviewError("partial curation")
        if curation["disposition"] != "curate":
            continue
        record = curation["pending_record"]
        if record["id"] in pending_ids:
            raise TopicReviewError("duplicate pending record")
        pending_ids.add(record["id"])
        pending.append(record)
    return pending


def load_curated_pending(
    raw_path: str | Path,
    policies_path: str | Path,
    curations_path: str | Path,
    pending_path: str | Path,
) -> list[dict[str, Any]]:
    raw = load_raw(raw_path, policies_path)
    curations = read_jsonl(review_input_path(curations_path))
    pending = load_pending(pending_path)
    curated = materialize_curations(raw, curations)
    if curated != pending:
        raise TopicReviewError("partial curation")
    return pending
