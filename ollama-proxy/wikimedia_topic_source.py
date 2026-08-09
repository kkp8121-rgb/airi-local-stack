"""Default-off Korean Wikimedia adapter that emits policy-bound raw evidence."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import math
import os
import queue
import re
import socket
import ssl
import tempfile
import threading
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from collections.abc import Callable
from typing import Any, Mapping, Protocol
from urllib.parse import unquote, urlencode, urlsplit

from collect_topic_candidates import collect_raw_discoveries
from topic_discovery_contract import (
    discovery_id, load_raw, load_source_policies, policy_sha256,
)
from topic_review_contract import (
    CONTROL_RE, OwnershipLock, TopicReviewError, canonical_json,
    canonical_jsonl_bytes,
    review_output_path,
)

API_URL = "https://ko.wikipedia.org/w/api.php"
ARTICLE_HOST = "ko.wikipedia.org"
ARTICLE_PREFIX = "/wiki/"
PAGE_TITLE = "포털:요즘 화제"
SPDX = "CC-BY-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
PORTAL_URL = (
    "https://ko.wikipedia.org/wiki/"
    "%ED%8F%AC%ED%84%B8:%EC%9A%94%EC%A6%98_%ED%99%94%EC%A0%9C"
)
MAX_BODY_BYTES = 512 * 1024
MAX_JSON_BYTES = 128 * 1024
MAX_HTML_BYTES = 384 * 1024
MAX_ITEMS = 24
MAX_TITLE = 300
MAX_SNIPPET = 1200
MAX_ETAG = 256
MAX_UA = 240
DEFAULT_TIMEOUT = 10.0
MAX_TIMEOUT = 30.0
BIDI_RE = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
ASCII_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\Z")
UA_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{1,79}/"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,39} "
    r"\(([^()]+)\)(?: [\x20-\x7e]{1,80})?\Z"
)
Z_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class WikimediaError(ValueError):
    """Content-free adapter failure."""


class Response:
    """Small injectable HTTP response shape used by tests and transport."""

    def __init__(self, status: int, url: str, headers: Mapping[str, str],
                 body: bytes, peer_ip: str | None):
        self.status = status
        self.url = url
        self.headers = headers
        self.body = body
        self.peer_ip = peer_ip


class Transport(Protocol):
    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
        approved_ips: frozenset[str],
    ) -> Response:
        ...


class Resolver(Protocol):
    def resolve(self, host: str, timeout: float) -> frozenset[str]:
        ...


def _global_ip(value: Any) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise WikimediaError("invalid network address") from exc
    if not address.is_global:
        raise WikimediaError("invalid network address")
    return address.compressed


class SocketResolver:
    """Resolve once before connect; every returned address must be public."""

    def resolve(self, host: str, timeout: float) -> frozenset[str]:
        output: queue.Queue[object] = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                output.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
            except BaseException as exc:  # daemon result is converted at the boundary
                output.put(exc)

        thread = threading.Thread(target=worker, name="wikimedia-dns", daemon=True)
        thread.start()
        try:
            result = output.get(timeout=timeout)
        except queue.Empty as exc:
            raise WikimediaError("request timeout") from exc
        if isinstance(result, BaseException):
            raise WikimediaError("request failed") from result
        addresses: set[str] = set()
        try:
            for entry in result:
                addresses.add(_global_ip(entry[4][0]))
                if len(addresses) > 16:
                    raise WikimediaError("invalid network address")
        except (IndexError, TypeError) as exc:
            raise WikimediaError("invalid network address") from exc
        if not addresses:
            raise WikimediaError("invalid network address")
        return frozenset(addresses)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a reviewed address while retaining hostname TLS validation."""

    def __init__(self, host: str, pinned_ip: str, *, timeout: float) -> None:
        super().__init__(
            host,
            port=443,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        deadline = time.monotonic() + float(self.timeout)
        raw = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WikimediaError("request timeout")
            raw.settimeout(remaining)
            raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class HttpxTransport:
    """Pinned HTTPS transport retained under its original public class name."""

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
        approved_ips: frozenset[str],
    ) -> Response:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != ARTICLE_HOST
            or parsed.port is not None
            or parsed.username
            or parsed.password
            or parsed.fragment
            or not approved_ips
        ):
            raise WikimediaError("invalid request")
        approved = frozenset(_global_ip(value) for value in approved_ips)
        pinned_ip = sorted(approved)[0]
        connection = _PinnedHTTPSConnection(ARTICLE_HOST, pinned_ip, timeout=timeout)
        deadline = time.monotonic() + timeout

        def remaining() -> float:
            value = deadline - time.monotonic()
            if value <= 0:
                raise WikimediaError("request timeout")
            return value

        try:
            request_headers = dict(headers)
            request_headers["Host"] = ARTICLE_HOST
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            connection.connect()
            if connection.sock is None:
                raise WikimediaError("request failed")
            connection.sock.settimeout(remaining())
            connection.request("GET", path, headers=request_headers)
            peer = connection.sock.getpeername()[0] if connection.sock else None
            peer = _global_ip(peer)
            if peer not in approved:
                raise WikimediaError("invalid network address")
            connection.sock.settimeout(remaining())
            result = connection.getresponse()
            response_headers: dict[str, str] = {}
            for name, value in result.getheaders():
                key = name.casefold()
                if key in response_headers:
                    raise WikimediaError("invalid response")
                response_headers[key] = value
            length = response_headers.get("content-length")
            if length is not None and (
                not length.isdecimal() or int(length) > MAX_BODY_BYTES
            ):
                raise WikimediaError("invalid response")
            connection.sock.settimeout(remaining())
            body = result.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise WikimediaError("invalid response")
            return Response(result.status, url, response_headers, body, peer)
        except WikimediaError:
            raise
        except Exception as exc:
            raise WikimediaError("request failed") from exc
        finally:
            connection.close()


def _utc(value: datetime | None = None) -> str:
    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise WikimediaError("invalid time")
    return moment.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _parse_z_time(value: Any) -> datetime:
    if not isinstance(value, str) or not Z_TIME_RE.fullmatch(value):
        raise WikimediaError("invalid time")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise WikimediaError("invalid time") from exc


def _safe_text(value: Any, limit: int) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value.strip()) > limit
            or CONTROL_RE.search(value) or BIDI_RE.search(value)):
        raise WikimediaError("invalid content")
    return " ".join(value.split())


def _user_agent(value: str) -> str:
    if (not isinstance(value, str) or not (12 <= len(value.strip()) <= MAX_UA)
            or any(ord(char) < 32 or ord(char) > 126 for char in value)):
        raise WikimediaError("invalid user agent")
    normalized = value.strip()
    match = UA_RE.fullmatch(normalized)
    if match is None:
        raise WikimediaError("invalid user agent")
    contact = match.group(1)
    if EMAIL_RE.fullmatch(contact) is None:
        try:
            parsed = urlsplit(contact)
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise WikimediaError("invalid user agent") from exc
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.fragment
            or port is not None
            or host.casefold() == "localhost"
        ):
            raise WikimediaError("invalid user agent")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise WikimediaError("invalid user agent")
    return normalized


def _valid_etag(value: Any) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= MAX_ETAG
            and not ASCII_CONTROL_RE.search(value)
            and not BIDI_RE.search(value))


def _check_response(
    response: Response,
    expected_url: str,
    statuses: set[int],
    approved_ips: frozenset[str],
) -> bytes:
    try:
        peer = _global_ip(response.peer_ip)
    except WikimediaError:
        peer_ok = False
    else:
        peer_ok = peer in approved_ips
    if (
        response.status not in statuses
        or response.url != expected_url
        or not peer_ok
        or not isinstance(response.body, bytes)
        or len(response.body) > MAX_BODY_BYTES
    ):
        raise WikimediaError("invalid response")
    headers = _normalized_headers(response)
    if headers.get("content-encoding", "").casefold() not in {"", "identity"}:
        raise WikimediaError("invalid response")
    length = headers.get("content-length")
    if response.status == 304:
        if response.body or (
            length is not None
            and (not length.isdecimal() or int(length) > MAX_BODY_BYTES)
        ):
            raise WikimediaError("invalid response")
    elif length is not None and (
        not length.isdecimal() or int(length) != len(response.body)
    ):
        raise WikimediaError("invalid response")
    return response.body


def _normalized_headers(response: Response) -> dict[str, str]:
    try:
        pairs = response.headers.items()
    except AttributeError as exc:
        raise WikimediaError("invalid response") from exc
    headers: dict[str, str] = {}
    for name, value in pairs:
        if (
            not isinstance(name, str)
            or not isinstance(value, str)
            or ASCII_CONTROL_RE.search(name + value)
            or BIDI_RE.search(name + value)
        ):
            raise WikimediaError("invalid response")
        key = name.strip().casefold()
        if not key or key in headers:
            raise WikimediaError("invalid response")
        headers[key] = value.strip()
    return headers


def _decode_json(body: bytes) -> dict[str, Any]:
    if len(body) > MAX_JSON_BYTES:
        raise WikimediaError("invalid response")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WikimediaError("invalid response") from exc
    if not isinstance(value, dict) or "error" in value:
        raise WikimediaError("invalid response")
    return value


def _article_url(href: str | None) -> str | None:
    if not isinstance(href, str) or CONTROL_RE.search(href) or BIDI_RE.search(href):
        return None
    if not href.startswith(ARTICLE_PREFIX) or any(char in href for char in "?#\\"):
        return None
    tail = href[len(ARTICLE_PREFIX):]
    if re.search(r"%(?![0-9A-Fa-f]{2})", tail):
        return None
    decoded_tail = unquote(tail)
    if (
        not decoded_tail
        or decoded_tail.startswith(":")
        or ":" in decoded_tail
        or "/" in decoded_tail
        or CONTROL_RE.search(decoded_tail)
        or BIDI_RE.search(decoded_tail)
    ):
        return None
    url = "https://" + ARTICLE_HOST + href
    parsed = urlsplit(url)
    if parsed.hostname != ARTICLE_HOST or not parsed.path.startswith(ARTICLE_PREFIX):
        return None
    return url


class EvidenceParser(HTMLParser):
    """Collect only top-level list items in the parser output container."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str, str]] = []
        self.stack: list[str] = []
        self.container_depth: int | None = None
        self.skip_depths: list[int] = []
        self.list_depth: int | None = None
        self.li_depth: int | None = None
        self.nested_list_depths: list[int] = []
        self.parts: list[str] = []
        self.link: str | None = None
        self.anchor_parts: list[str] = []
        self.anchor_depth: int | None = None
        self.invalid = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        try:
            attributes = dict(attrs)
        except (TypeError, ValueError):
            self.invalid = True
            return
        classes = (attributes.get("class") or "").split()
        if tag in VOID_TAGS:
            if tag == "br" and self._collecting_text():
                self.parts.append(" ")
            return
        self.stack.append(tag)
        depth = len(self.stack)
        if tag == "div" and self.container_depth is None and "mw-parser-output" in classes:
            self.container_depth = depth
            return
        if self.container_depth is None:
            return
        if (
            tag in {"script", "style", "nav", "sup"}
            or "reference" in classes
            or "references" in classes
        ):
            self.skip_depths.append(depth)
            return
        if self.skip_depths:
            return
        if tag in {"ul", "ol"}:
            if self.li_depth is not None:
                self.nested_list_depths.append(depth)
            elif self.list_depth is None:
                self.list_depth = depth
            return
        if (
            tag == "li"
            and self.list_depth is not None
            and self.li_depth is None
            and depth == self.list_depth + 1
        ):
            self.li_depth = depth
            self.parts, self.anchor_parts, self.link = [], [], None
        elif (
            tag == "a"
            and self.li_depth is not None
            and not self.nested_list_depths
            and not self.skip_depths
            and self.link is None
        ):
            link = _article_url(attributes.get("href"))
            if link:
                self.link = link
                self.anchor_depth = depth

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in VOID_TAGS:
            return
        if not self.stack or self.stack[-1] != tag:
            self.invalid = True
            return
        depth = len(self.stack)
        if self.anchor_depth == depth and tag == "a":
            self.anchor_depth = None
        if self.nested_list_depths and self.nested_list_depths[-1] == depth:
            self.nested_list_depths.pop()
        elif tag == "li" and self.li_depth == depth:
            if self.link:
                self.items.append((self.link, " ".join(self.anchor_parts), " ".join(self.parts)))
            self.li_depth = None
            self.nested_list_depths = []
            self.anchor_depth = None
        if self.list_depth == depth and tag in {"ul", "ol"}:
            self.list_depth = None
        if self.container_depth == depth and tag == "div":
            self.container_depth = None
            self.list_depth = None
        if self.skip_depths and self.skip_depths[-1] == depth:
            self.skip_depths.pop()
        self.stack.pop()

    def _collecting_text(self) -> bool:
        return (
            self.li_depth is not None
            and not self.nested_list_depths
            and not self.skip_depths
        )

    def handle_data(self, data: str) -> None:
        if self._collecting_text():
            self.parts.append(data)
            if self.anchor_depth is not None:
                self.anchor_parts.append(data)


def _parse_items(html: str) -> list[tuple[str, str, str]]:
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise WikimediaError("invalid response")
    try:
        parser = EvidenceParser()
        parser.feed(html)
        parser.close()
    except ValueError as exc:
        raise WikimediaError("invalid response") from exc
    if parser.invalid or parser.stack:
        raise WikimediaError("invalid response")
    result: list[tuple[str, str, str]] = []
    seen_urls: set[str] = set()
    for url, title, snippet in parser.items:
        try:
            clean_title = _safe_text(title, MAX_TITLE)
            clean_snippet = _safe_text(snippet, MAX_SNIPPET)
        except WikimediaError:
            continue
        if url not in seen_urls:
            result.append((url, clean_title, clean_snippet))
            seen_urls.add(url)
        if len(result) > MAX_ITEMS:
            raise WikimediaError("too many items")
    if not result:
        raise WikimediaError("no evidence")
    return result


def _cache_path(path: str | Path) -> Path:
    output = review_output_path(path)
    if not re.fullmatch(r"\.wikimedia-topic-cache[\w.-]*\.json", output.name):
        raise WikimediaError("invalid cache")
    return output


def _read_cache(path: Path, policy_hash: str, metadata_url: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WikimediaError("invalid cache") from exc
    fields = {
        "schema_version",
        "source_policy_sha256",
        "etag",
        "revision_id",
        "revision_timestamp",
        "metadata_url",
        "raw_snapshot_sha256",
        "raw_record_count",
        "source_body_sha256",
    }
    if (not isinstance(value, dict) or set(value) != fields
            or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("source_policy_sha256") != policy_hash or value.get("metadata_url") != metadata_url
            or (value.get("etag") is not None and not _valid_etag(value.get("etag")))
            or type(value.get("revision_id")) is not int
            or value["revision_id"] <= 0
            or type(value.get("raw_record_count")) is not int
            or value["raw_record_count"] <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("raw_snapshot_sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("source_body_sha256", ""))):
        raise WikimediaError("invalid cache")
    try:
        if _utc(_parse_z_time(value["revision_timestamp"])) != value["revision_timestamp"]:
            raise ValueError
    except (AttributeError, ValueError) as exc:
        raise WikimediaError("invalid cache") from exc
    if raw != canonical_json(value):
        raise WikimediaError("invalid cache")
    return value


def _raw_snapshot_sha256(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_jsonl_bytes(rows)).hexdigest()


def _cache_matches_raw(
    cached: Mapping[str, Any],
    rows: list[dict[str, Any]],
    policy_id: str,
) -> bool:
    return (
        len(rows) == cached["raw_record_count"]
        and _raw_snapshot_sha256(rows) == cached["raw_snapshot_sha256"]
        and any(
            row["source_policy_id"] == policy_id
            and row["published_at"] == cached["revision_timestamp"]
            and row["source_body_sha256"] == cached["source_body_sha256"]
            for row in rows
        )
    )


def _write_cache(
    path: Path,
    value: dict[str, Any],
    before_replace: Callable[[], Any] | None = None,
) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".wikimedia-topic-cache-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_json(value))
            handle.flush()
            os.fsync(handle.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def collect_wikimedia(*, policies_path: str | Path, raw_path: str | Path,
                      cache_path: str | Path, policy_id: str, user_agent: str,
                      transport: Transport | None = None, now: datetime | None = None,
                      timeout: float = DEFAULT_TIMEOUT,
                      resolver: Resolver | None = None,
                      clock: Callable[[], float] = time.monotonic) -> dict[str, int]:
    """Fetch fixed page evidence, merge raw rows, then atomically cache its ETag."""
    user_agent = _user_agent(user_agent)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0.1 <= timeout <= MAX_TIMEOUT
    ):
        raise WikimediaError("invalid timeout")
    policies = load_source_policies(policies_path)
    policy = policies.get(policy_id)
    if (not policy or policy["source_kind"] != "feed" or policy["feed_url"] != API_URL
            or policy["article_host"] != ARTICLE_HOST or policy["article_path_prefix"] != ARTICLE_PREFIX
            or policy["license"].get("spdx") != SPDX or policy["license"].get("license_url") != LICENSE_URL
            or policy["license"].get("attribution") != "Wikipedia contributors"
            or policy["license"].get("attribution_url") != PORTAL_URL):
        raise WikimediaError("invalid policy")
    raw = review_output_path(raw_path)
    cache = _cache_path(cache_path)
    policy_hash = policy_sha256(policy)
    metadata_url = API_URL + "?" + urlencode({
        "action": "query", "format": "json", "formatversion": "2", "maxlag": "5",
        "redirects": "1", "prop": "revisions", "rvprop": "ids|timestamp",
        "rvslots": "main", "rvlimit": "1", "titles": PAGE_TITLE,
    })
    deadline = clock() + float(timeout)

    def remaining() -> float:
        value = deadline - clock()
        if value <= 0:
            raise WikimediaError("timeout")
        return value

    client = transport or HttpxTransport()
    address_resolver = resolver or SocketResolver()
    with OwnershipLock(cache):
        cached = _read_cache(cache, policy_hash, metadata_url)
        cached_rows: list[dict[str, Any]] | None = None
        if cached is not None:
            if not raw.exists():
                raise WikimediaError("invalid cache")
            cached_rows = load_raw(raw, policies_path)
            if not _cache_matches_raw(cached, cached_rows, policy_id):
                raise WikimediaError("invalid cache")
        remaining()
        approved_ips = frozenset(
            _global_ip(value)
            for value in address_resolver.resolve(ARTICLE_HOST, remaining())
        )
        if not approved_ips:
            raise WikimediaError("invalid network address")
        remaining()
        headers = {"User-Agent": user_agent, "Accept-Encoding": "identity", "Accept": "application/json"}
        if cached is not None and cached["etag"] is not None:
            headers["If-None-Match"] = cached["etag"]
        response = client.get(metadata_url, headers, remaining(), approved_ips)
        remaining()
        if response.status == 304:
            if cached is None or cached_rows is None or "If-None-Match" not in headers:
                raise WikimediaError("invalid response")
            _check_response(response, metadata_url, {304}, approved_ips)
            remaining()
            return {"raw_count": len(cached_rows), "added_count": 0}
        metadata_response = response
        metadata = _decode_json(
            _check_response(metadata_response, metadata_url, {200}, approved_ips)
        )
        metadata_headers = _normalized_headers(metadata_response)
        etag = metadata_headers.get("etag")
        if etag is not None and not _valid_etag(etag):
            raise WikimediaError("invalid response")
        try:
            pages = metadata["query"]["pages"]
            if not isinstance(pages, list) or len(pages) != 1:
                raise ValueError
            page = pages[0]
            revisions = page["revisions"]
            if (
                not isinstance(page, dict)
                or "missing" in page
                or not isinstance(revisions, list)
                or len(revisions) != 1
            ):
                raise ValueError
            revision = revisions[0]
            pageid, revid, page_title = page["pageid"], revision["revid"], page["title"]
            published_at = _utc(_parse_z_time(revision["timestamp"]))
            if (type(pageid) is not int or pageid <= 0
                    or type(revid) is not int or revid <= 0
                    or page_title != PAGE_TITLE):
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise WikimediaError("invalid response") from exc
        remaining()
        parse_url = API_URL + "?" + urlencode({
            "action": "parse", "format": "json", "formatversion": "2", "maxlag": "5",
            "oldid": str(revid), "prop": "text|revid|displaytitle",
        })
        response = client.get(
            parse_url,
            {"User-Agent": user_agent, "Accept-Encoding": "identity", "Accept": "application/json"},
            remaining(),
            approved_ips,
        )
        remaining()
        try:
            parsed = _decode_json(
                _check_response(response, parse_url, {200}, approved_ips)
            )["parse"]
            html = parsed["text"]
            if (type(parsed["pageid"]) is not int or parsed["pageid"] != pageid
                    or type(parsed["revid"]) is not int or parsed["revid"] != revid
                    or parsed["title"] != PAGE_TITLE
                    or not isinstance(parsed["displaytitle"], str)
                    or not parsed["displaytitle"].strip()
                    or not isinstance(html, str)):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise WikimediaError("invalid response") from exc
        remaining()
        body_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        rows: list[dict[str, Any]] = []
        for source_url, source_title, source_snippet in _parse_items(html):
            row = {
                "discovery_schema_version": 1, "discovery_id": "", "source_policy_id": policy_id,
                "source_kind": "feed", "source": policy["source"], "feed_url": API_URL,
                "source_url": source_url, "published_at": published_at, "discovered_at": _utc(now),
                "source_title": source_title, "source_snippet": source_snippet,
                "license": policy["license"], "source_body_sha256": body_hash,
                "source_policy_sha256": policy_hash,
            }
            row["discovery_id"] = discovery_id(policy_id, source_url, published_at)
            rows.append(row)
        remaining()
        result = collect_raw_discoveries(raw, policies_path, rows)
        remaining()
        merged_rows = load_raw(raw, policies_path)
        cache_value = {
            "schema_version": 1,
            "source_policy_sha256": policy_hash,
            "etag": etag,
            "revision_id": revid,
            "revision_timestamp": published_at,
            "metadata_url": metadata_url,
            "raw_snapshot_sha256": _raw_snapshot_sha256(merged_rows),
            "raw_record_count": len(merged_rows),
            "source_body_sha256": body_hash,
        }
        remaining()
        _write_cache(cache, cache_value, remaining)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--enable-wikimedia", action="store_true")
    parser.add_argument("--source-policies")
    parser.add_argument("--raw-discoveries")
    parser.add_argument("--cache")
    parser.add_argument("--policy-id")
    parser.add_argument("--user-agent")
    try:
        args, unknown = parser.parse_known_args(argv)
        if not args.enable_wikimedia:
            print('{"status":"disabled","added_count":0,"raw_count":0}')
            return 0
        if unknown or not all((args.source_policies, args.raw_discoveries, args.cache, args.policy_id, args.user_agent)):
            raise WikimediaError("invalid request")
        result = collect_wikimedia(policies_path=args.source_policies, raw_path=args.raw_discoveries,
                                   cache_path=args.cache, policy_id=args.policy_id,
                                   user_agent=args.user_agent)
        print(json.dumps({"status": "complete", **result}, separators=(",", ":")))
        return 0
    except (
        argparse.ArgumentError,
        OSError,
        RuntimeError,
        ValueError,
        TopicReviewError,
        json.JSONDecodeError,
    ):
        print('{"status":"rejected","added_count":0,"raw_count":0}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
