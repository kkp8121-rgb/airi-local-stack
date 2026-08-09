"""Explicitly enabled, pending-only topic candidate collector.

There are deliberately no production sources or network implementation here.
Callers must inject an exact source policy and a bounded fetcher.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import time
import ipaddress
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from topic_review_contract import (
    TopicReviewError, atomic_write_jsonl, load_pending,
    record_sha256, review_output_path, validate_pending_record,
)

MAX_REDIRECTS = 3
MAX_BODY_BYTES = 256 * 1024
MAX_DECOMPRESSED_BYTES = 512 * 1024
MAX_ENTRIES_PER_SOURCE = 32
LOCK_WAIT_SECONDS = 5.0
SOURCE_TOTAL_TIMEOUT = 8.0
MONOTONIC = time.monotonic


@dataclass(frozen=True)
class SourcePolicy:
    host: str
    path: str


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    peer_ip: str
    redirect_to: str | None = None


Fetcher = Callable[[str, float, float, float], FetchResponse]


class CollectionError(ValueError):
    pass


def _allowed_url(url: str, policy: SourcePolicy) -> str:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username or parsed.password
                or parsed.fragment or parsed.port is not None or parsed.path != policy.path
                or parsed.query or host.casefold() != policy.host.casefold()):
            raise CollectionError("source policy rejected")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise CollectionError("source policy rejected")
        if host.casefold() == "localhost":
            raise CollectionError("source policy rejected")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, CollectionError):
            raise
        raise CollectionError("source policy rejected") from exc
    return url


def _global_peer(peer_ip: str) -> None:
    try:
        if not ipaddress.ip_address(peer_ip).is_global:
            raise CollectionError("peer rejected")
    except ValueError as exc:
        if isinstance(exc, CollectionError):
            raise
        raise CollectionError("peer rejected") from exc


def _decode(response: FetchResponse) -> list[dict[str, Any]]:
    if not isinstance(response.body, bytes) or not isinstance(response.headers, dict):
        raise CollectionError("invalid source response")
    if len(response.body) > MAX_BODY_BYTES:
        raise CollectionError("body limit")
    headers: dict[str, str] = {}
    for key, value in response.headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise CollectionError("invalid source response")
        normalized_key = key.strip().casefold()
        if not normalized_key or normalized_key in headers:
            raise CollectionError("invalid source response")
        headers[normalized_key] = value.strip()
    encoding = headers.get("content-encoding", "").casefold()
    if encoding not in {"", "identity", "gzip"}:
        raise CollectionError("unsupported encoding")
    body = response.body
    if encoding == "gzip":
        try:
            inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
            body = inflater.decompress(body, MAX_DECOMPRESSED_BYTES + 1)
            if (len(body) > MAX_DECOMPRESSED_BYTES or not inflater.eof
                    or inflater.unconsumed_tail or inflater.unused_data):
                raise CollectionError("body limit")
        except (OSError, zlib.error) as exc:
            raise CollectionError("invalid compressed body") from exc
    if len(body) > MAX_DECOMPRESSED_BYTES:
        raise CollectionError("body limit")
    try:
        rows = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CollectionError("invalid source payload") from exc
    if not isinstance(rows, list) or len(rows) > MAX_ENTRIES_PER_SOURCE or not all(isinstance(row, dict) for row in rows):
        raise CollectionError("entry limit")
    return rows


class _SidecarLock:
    def __init__(self, target: Path) -> None:
        self.path = target.with_name(f".{target.name}.collect.lock")
        self.fd: int | None = None
        self.token = secrets.token_hex(16)
        self.identity: tuple[int, int] | None = None

    def __enter__(self) -> "_SidecarLock":
        deadline = MONOTONIC() + LOCK_WAIT_SECONDS
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                stat = os.fstat(self.fd)
                self.identity = (stat.st_dev, stat.st_ino)
                encoded = self.token.encode("ascii")
                if os.write(self.fd, encoded) != len(encoded):
                    raise OSError("incomplete lock write")
                return self
            except FileExistsError:
                if MONOTONIC() >= deadline:
                    raise CollectionError("lock unavailable")
                time.sleep(0.01)
            except OSError:
                if self.fd is not None:
                    os.close(self.fd)
                    self.fd = None
                try:
                    stat = self.path.stat()
                    if self.identity == (stat.st_dev, stat.st_ino):
                        self.path.unlink()
                except (FileNotFoundError, OSError):
                    pass
                raise

    def __exit__(self, *_: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            stat = self.path.stat()
            if (self.identity != (stat.st_dev, stat.st_ino)
                    or self.path.read_text(encoding="ascii") != self.token):
                raise CollectionError("lock ownership")
            self.path.unlink()
        except FileNotFoundError:
            pass


def _existing(path: Path) -> list[dict[str, Any]]:
    return load_pending(path) if path.exists() else []


def collect_candidates(pending_path: str | Path, policies: Iterable[SourcePolicy], fetcher: Fetcher) -> dict[str, int]:
    """Fetch injected-policy payloads and atomically merge strict pending rows."""
    output = review_output_path(pending_path)
    policies = tuple(policies)
    if not policies:
        raise CollectionError("no source policy")
    candidates: list[dict[str, Any]] = []
    for policy in policies:
        url = _allowed_url(f"https://{policy.host}{policy.path}", policy)
        started = MONOTONIC()
        for _ in range(MAX_REDIRECTS + 1):
            remaining = SOURCE_TOTAL_TIMEOUT - (MONOTONIC() - started)
            if remaining <= 0:
                raise CollectionError("source timeout")
            response = fetcher(url, min(3.0, remaining), min(5.0, remaining), remaining)
            if MONOTONIC() - started > SOURCE_TOTAL_TIMEOUT:
                raise CollectionError("source timeout")
            _allowed_url(response.url, policy)
            _global_peer(response.peer_ip)
            if response.redirect_to is None:
                if response.status != 200:
                    raise CollectionError("source failure")
                decoded = _decode(response)
                if MONOTONIC() - started > SOURCE_TOTAL_TIMEOUT:
                    raise CollectionError("source timeout")
                for raw in decoded:
                    row = validate_pending_record(raw)
                    if row["source_url"] != response.url:
                        raise CollectionError("provenance mismatch")
                    candidates.append(row)
                if MONOTONIC() - started > SOURCE_TOTAL_TIMEOUT:
                    raise CollectionError("source timeout")
                break
            if response.status not in {301, 302, 303, 307, 308}:
                raise CollectionError("redirect failure")
            url = _allowed_url(response.redirect_to, policy)
        else:
            raise CollectionError("redirect limit")
    with _SidecarLock(output):
        existing = _existing(output)
        by_id = {row["id"]: row for row in existing}
        seen_keys = {(row["source_url"], row["published_at"]) for row in existing}
        seen_hashes = {record_sha256(row) for row in existing}
        merged = list(existing)
        added = 0
        for row in candidates:
            digest = record_sha256(row); key = (row["source_url"], row["published_at"])
            prior = by_id.get(row["id"])
            if prior is not None and record_sha256(prior) != digest:
                raise CollectionError("id collision")
            if prior is not None or key in seen_keys or digest in seen_hashes:
                continue
            by_id[row["id"]] = row; seen_keys.add(key); seen_hashes.add(digest); merged.append(row); added += 1
        if added:
            atomic_write_jsonl(output, merged)
    return {"existing_count": len(existing), "added_count": added, "pending_count": len(existing) + added}


def _no_network_fetcher(*_: object) -> FetchResponse:
    raise CollectionError("network fetcher unavailable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--enable-collection", action="store_true")
    parser.add_argument("--pending")
    try:
        args, unknown = parser.parse_known_args(argv)
        if not args.enable_collection:
            print('{"status":"disabled","added_count":0,"pending_count":0}')
            return 0
        if unknown or not args.pending:
            raise CollectionError("invalid request")
        # No built-in source policy or network client exists. Production use
        # must supply a reviewed integration, not an implicit default.
        collect_candidates(args.pending, (), _no_network_fetcher)
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError, TopicReviewError, json.JSONDecodeError):
        print('{"status":"rejected","added_count":0,"pending_count":0}')
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
