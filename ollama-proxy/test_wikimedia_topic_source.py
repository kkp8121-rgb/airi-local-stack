"""Synthetic-only regression tests for the opt-in Wikimedia evidence adapter."""

import gzip
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import topic_review_contract as contract
import wikimedia_topic_source as wiki


UTC_NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
USER_AGENT = "adapter/1 (https://contact.example/)"


def reviewed_policy():
    return {
        "policy_id": "ko-wiki", "source_kind": "feed", "source": "Korean Wikimedia",
        "feed_url": wiki.API_URL, "article_host": wiki.ARTICLE_HOST,
        "article_path_prefix": wiki.ARTICLE_PREFIX,
        "license": {
            "spdx": wiki.SPDX, "license_url": wiki.LICENSE_URL,
            "attribution": "Wikipedia contributors",
            "attribution_url": wiki.PORTAL_URL,
        },
        "approved": True, "reviewer": "reviewer", "reviewed_at": "2026-01-01T00:00:00Z",
    }


class FakeTransport:
    """A response queue which cannot make a real connection."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers, timeout, approved_ips):
        self.calls.append((url, dict(headers), timeout, frozenset(approved_ips)))
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        return self.responses.pop(0)


class FakeResolver:
    def __init__(self, addresses=frozenset({"8.8.8.8"})):
        self.addresses = frozenset(addresses)
        self.hosts = []

    def resolve(self, host, timeout):
        self.hosts.append((host, timeout))
        return self.addresses


class WikimediaTopicSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "topic-review"
        self.root.mkdir()
        patch = mock.patch.object(contract, "TOPIC_REVIEW_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.policies = self.root / "source-policies.json"
        self.raw = self.root / "raw.jsonl"
        self.cache = self.root / ".wikimedia-topic-cache.json"
        self.write_policy()

    def write_policy(self, value=None):
        self.policies.write_text(json.dumps({"schema_version": 1, "policies": [value or reviewed_policy()]}), encoding="utf-8")

    def urls(self, revid=7):
        metadata = wiki.API_URL + "?action=query&format=json&formatversion=2&maxlag=5&redirects=1&prop=revisions&rvprop=ids%7Ctimestamp&rvslots=main&rvlimit=1&titles=%ED%8F%AC%ED%84%B8%3A%EC%9A%94%EC%A6%98+%ED%99%94%EC%A0%9C"
        parsed = wiki.API_URL + f"?action=parse&format=json&formatversion=2&maxlag=5&oldid={revid}&prop=text%7Crevid%7Cdisplaytitle"
        return metadata, parsed

    def response(self, status, url, payload=b"", *, peer="8.8.8.8", headers=None):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload).encode("utf-8")
        return wiki.Response(status, url, headers or {}, payload, peer)

    def metadata(self, *, revid=7, timestamp="2026-01-01T00:00:00Z", headers=None):
        url, _ = self.urls(revid)
        return self.response(200, url, {"query": {"pages": [{
            "pageid": 1, "title": wiki.PAGE_TITLE,
            "revisions": [{"revid": revid, "timestamp": timestamp}],
        }]}}, headers={"ETag": "tag"} if headers is None else headers)

    def parsed(self, html, *, revid=7):
        _, url = self.urls(revid)
        return self.response(200, url, {"parse": {
            "pageid": 1, "revid": revid, "title": wiki.PAGE_TITLE,
            "displaytitle": wiki.PAGE_TITLE, "text": html,
        }})

    def collect(self, transport=None, **kwargs):
        return wiki.collect_wikimedia(
            policies_path=self.policies, raw_path=self.raw, cache_path=self.cache,
            policy_id="ko-wiki", user_agent=USER_AGENT,
            transport=transport or self.good_transport(), resolver=FakeResolver(), now=UTC_NOW, **kwargs,
        )

    def good_transport(self, html=None):
        html = html or "<div class='mw-parser-output'><ul><li><a href='/wiki/A'>A title</a> snippet</li></ul></div>"
        return FakeTransport([self.metadata(), self.parsed(html)])

    def test_default_off_and_invalid_enable_do_not_write(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(wiki.main([]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "disabled")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(wiki.main(["--enable-wikimedia"]), 2)
        self.assertFalse(self.raw.exists())

    def test_real_list_structure_excludes_nested_and_non_content_sections(self):
        html = """<div class='mw-parser-output'>
          <ul><li>Before <a href='/wiki/Outer'>Outer</a><br> after <img src=x>
            <ul><li><a href='/wiki/Nested'>Nested</a></li></ul>
            <sup><a href='/wiki/Sup'>Sup</a></sup><span class='reference'><a href='/wiki/Ref'>Ref</a></span>
          </li><li><a href='/wiki/Second'>Second</a> two</li></ul>
          <nav><ul><li><a href='/wiki/Nav'>Nav</a></li></ul></nav>
          <script><a href='/wiki/Script'>Script</a></script><style>bad</style>
        </div>"""
        rows = wiki._parse_items(html)
        self.assertEqual([item[0] for item in rows], ["https://ko.wikipedia.org/wiki/Outer", "https://ko.wikipedia.org/wiki/Second"])
        self.assertEqual(rows[0][1], "Outer")
        self.assertIn("Before Outer after", rows[0][2])

    def test_encoded_namespace_and_slash_are_not_article_urls(self):
        html = """<div class='mw-parser-output'><ul>
          <li><a href='/wiki/%3AHelp'>namespace</a></li>
          <li><a href='/wiki/A%2FB'>slash</a></li>
          <li><a href='/wiki/A'>safe</a></li>
        </ul></div>"""
        self.assertEqual(wiki._parse_items(html), [("https://ko.wikipedia.org/wiki/A", "safe", "safe")])

    def test_duplicate_urls_keep_the_first_item_only(self):
        html = """<div class='mw-parser-output'><ul>
          <li><a href='/wiki/A'>first</a> one</li><li><a href='/wiki/A'>second</a> two</li>
        </ul></div>"""
        self.assertEqual(wiki._parse_items(html), [("https://ko.wikipedia.org/wiki/A", "first", "first one")])

    def test_exact_utc_page_and_revision_shapes_are_required(self):
        invalid_metadata = [
            {"query": {"pages": []}},
            {"query": {"pages": [{"pageid": True, "title": wiki.PAGE_TITLE, "revisions": [{"revid": 7, "timestamp": "2026-01-01T00:00:00Z"}]}]}},
            {"query": {"pages": [{"pageid": 1, "title": wiki.PAGE_TITLE, "revisions": [{"revid": 7, "timestamp": "2026-01-01T00:00:00+00:00"}]}]}},
            {"query": {"pages": [{"pageid": 1, "title": "other", "revisions": [{"revid": 7, "timestamp": "2026-01-01T00:00:00Z"}]}]}},
        ]
        metadata_url, _ = self.urls()
        for value in invalid_metadata:
            with self.subTest(value=value), self.assertRaises(wiki.WikimediaError):
                self.collect(FakeTransport([self.response(200, metadata_url, value, headers={"etag": "tag"})]))

    def test_policy_license_and_attribution_must_match_exactly(self):
        for field, value in (("spdx", "CC-BY-SA-3.0"), ("license_url", "https://example.test/license"), ("attribution", "Other contributors"), ("attribution_url", "https://ko.wikipedia.org/wiki/Other")):
            altered = reviewed_policy()
            altered["license"][field] = value
            self.write_policy(altered)
            with self.subTest(field=field), self.assertRaises(wiki.WikimediaError):
                self.collect()
            self.write_policy()

    def test_user_agent_requires_named_version_and_public_contact(self):
        for value in (
            "adapter/1 (ops@example.test)",
            "adapter/1 (https://contact.example/path)",
        ):
            self.assertEqual(wiki._user_agent(value), value)
        for value in (
            "adapter contact@example.test",
            "adapter/1 contact@example.test",
            "adapter/1 (http://contact.example/)",
            "adapter/1 (https://localhost/)",
            "adapter/1 (https://127.0.0.1/)",
            "adapter/1 (https://contact.example:443/)",
        ):
            with self.subTest(value=value), self.assertRaises(wiki.WikimediaError):
                wiki._user_agent(value)

    def test_socket_resolver_rejects_any_private_answer(self):
        public = [(2, 1, 6, "", ("8.8.8.8", 443))]
        with mock.patch.object(wiki.socket, "getaddrinfo", return_value=public):
            self.assertEqual(
                wiki.SocketResolver().resolve(wiki.ARTICLE_HOST, 1.0),
                frozenset({"8.8.8.8"}),
            )
        mixed = public + [(2, 1, 6, "", ("127.0.0.1", 443))]
        with mock.patch.object(wiki.socket, "getaddrinfo", return_value=mixed):
            with self.assertRaises(wiki.WikimediaError):
                wiki.SocketResolver().resolve(wiki.ARTICLE_HOST, 1.0)

    def test_transport_connects_to_an_approved_ip_and_rechecks_peer(self):
        class Result:
            status = 200

            @staticmethod
            def getheaders():
                return []

            @staticmethod
            def read(_limit):
                return b"{}"

        class Socket:
            @staticmethod
            def settimeout(_timeout):
                pass

            @staticmethod
            def getpeername():
                return ("8.8.8.8", 443)

        class Connection:
            instances = []

            def __init__(self, host, pinned_ip, *, timeout):
                self.host, self.pinned_ip, self.timeout = host, pinned_ip, timeout
                self.sock, self.requests = Socket(), []
                self.instances.append(self)

            def connect(self):
                pass

            def request(self, method, path, headers):
                self.requests.append((method, path, headers))

            def getresponse(self):
                return Result()

            def close(self):
                pass

        with mock.patch.object(wiki, "_PinnedHTTPSConnection", Connection):
            response = wiki.HttpxTransport().get(
                wiki.API_URL,
                {"User-Agent": USER_AGENT},
                1.0,
                frozenset({"8.8.8.8"}),
            )
        self.assertEqual(response.peer_ip, "8.8.8.8")
        self.assertEqual(Connection.instances[0].pinned_ip, "8.8.8.8")
        self.assertEqual(Connection.instances[0].requests[0][2]["Host"], wiki.ARTICLE_HOST)

    def test_response_requires_public_resolved_address_equal_to_connected_peer(self):
        response = self.response(200, "https://expected/", b"{}", peer="8.8.8.8")
        self.assertEqual(wiki._check_response(response, "https://expected/", {200}, {"8.8.8.8"}), b"{}")
        for resolved, peer in (({"1.1.1.1"}, "8.8.8.8"), ({"127.0.0.1"}, "127.0.0.1"), ({"8.8.8.8"}, "10.0.0.1")):
            with self.subTest(resolved=resolved, peer=peer), self.assertRaises(wiki.WikimediaError):
                wiki._check_response(self.response(200, "https://expected/", b"{}", peer=peer), "https://expected/", {200}, resolved)

    def test_content_encoding_rejects_compression_and_accepts_identity(self):
        url, _ = self.urls()
        payload = {"query": {"pages": []}}
        for encoding in ("gzip", "br", "gzip, identity", "identity, gzip"):
            with self.subTest(encoding=encoding), self.assertRaises(wiki.WikimediaError):
                self.collect(FakeTransport([self.response(200, url, gzip.compress(json.dumps(payload).encode()), headers={"etag": "tag", "content-encoding": encoding})]))
        for headers in ({"etag": "tag"}, {"etag": "tag", "Content-Encoding": ""}, {"etag": "tag", "content-encoding": "identity"}):
            with self.subTest(headers=headers):
                transport = FakeTransport([self.metadata(headers=headers), self.parsed("<div class='mw-parser-output'><ul><li><a href='/wiki/A'>A</a></li></ul></div>")])
                self.assertIn("raw_count", self.collect(transport))

    def test_etag_is_optional_on_first_fetch_case_insensitive_and_never_unsafe(self):
        for headers in ({}, {"ETAG": "tag"}, {"etag": "bad\nvalue"}):
            with self.subTest(headers=headers):
                transport = FakeTransport([self.metadata(headers=headers), self.parsed("<div class='mw-parser-output'><ul><li><a href='/wiki/A'>A</a></li></ul></div>")])
                if "\n" in next(iter(headers.values()), ""):
                    with self.assertRaises(wiki.WikimediaError): self.collect(transport)
                else:
                    self.assertEqual(self.collect(transport)["raw_count"], 1)

        self.raw.unlink(missing_ok=True)
        self.cache.unlink(missing_ok=True)
        first = FakeTransport([
            self.metadata(headers={}),
            self.parsed("<div class='mw-parser-output'><ul><li><a href='/wiki/A'>A</a></li></ul></div>"),
        ])
        self.collect(first)
        second = FakeTransport([
            self.metadata(headers={}),
            self.parsed("<div class='mw-parser-output'><ul><li><a href='/wiki/A'>A</a></li></ul></div>"),
        ])
        self.assertEqual(self.collect(second), {"raw_count": 1, "added_count": 0})
        self.assertNotIn("If-None-Match", second.calls[0][1])

    def test_304_uses_canonical_raw_snapshot_and_does_not_mutate_cache_or_raw(self):
        self.collect()
        before_raw, before_cache = self.raw.read_bytes(), self.cache.read_bytes()
        metadata_url, _ = self.urls()
        result = self.collect(FakeTransport([self.response(304, metadata_url, b"", headers={})]))
        self.assertEqual(result, {"raw_count": 1, "added_count": 0})
        self.assertEqual(self.raw.read_bytes(), before_raw)
        self.assertEqual(self.cache.read_bytes(), before_cache)

    def test_304_rejects_a_valid_but_mutated_raw_snapshot_without_rewriting_either_file(self):
        self.collect()
        cache_before = self.cache.read_bytes()
        row = json.loads(self.raw.read_text(encoding="utf-8"))
        row["source_title"] = "Changed title"
        self.raw.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")
        raw_before = self.raw.read_bytes()
        metadata_url, _ = self.urls()
        with self.assertRaises(wiki.WikimediaError):
            self.collect(FakeTransport([self.response(304, metadata_url, b"", headers={})]))
        self.assertEqual(self.raw.read_bytes(), raw_before)
        self.assertEqual(self.cache.read_bytes(), cache_before)

    def test_global_deadline_prevents_a_second_request(self):
        transport = FakeTransport([self.metadata()])
        moments = iter([0.0, 0.0, 0.0, 0.0, 0.0, 1.1])
        clock = lambda: next(moments)
        with self.assertRaises(wiki.WikimediaError):
            self.collect(transport, timeout=1.0, clock=clock)
        self.assertEqual(len(transport.calls), 1)

    def test_timeout_after_parse_merge_or_cache_preserves_raw_and_cache(self):
        # Each injected stage consumes the global deadline before the adapter may commit.
        for stage in ("_parse_items", "collect_raw_discoveries"):
            with self.subTest(stage=stage):
                transport = self.good_transport()
                original = getattr(wiki, stage)
                expired = [False]
                def clock(): return 2.0 if expired[0] else 0.0
                def expire(*args, _original=original, **kwargs):
                    result = _original(*args, **kwargs)
                    expired[0] = True
                    return result
                with mock.patch.object(wiki, stage, side_effect=expire):
                    with self.assertRaises(wiki.WikimediaError):
                        self.collect(transport, timeout=1.0, clock=clock)
                self.assertFalse(self.cache.exists())

        transport = self.good_transport()
        original_write = wiki._write_cache
        expired = [False]

        def clock():
            return 2.0 if expired[0] else 0.0

        def expire_before_cache_replace(path, value, before_replace):
            def check():
                expired[0] = True
                before_replace()
            return original_write(path, value, check)

        with mock.patch.object(wiki, "_write_cache", side_effect=expire_before_cache_replace):
            with self.assertRaises(wiki.WikimediaError):
                self.collect(transport, timeout=1.0, clock=clock)
        self.assertFalse(self.cache.exists())

    def test_no_pending_decision_or_runtime_artifacts_are_created(self):
        self.collect()
        names = {path.name for path in self.root.iterdir()}
        self.assertEqual(names, {"source-policies.json", "raw.jsonl", ".wikimedia-topic-cache.json"})


if __name__ == "__main__":
    unittest.main()
