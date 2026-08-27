"""공개 채팅 리플레이 가명화 도구의 오프라인 계약 테스트. 네트워크·GPU 없이 돈다."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import import_public_chat as importer  # noqa: E402


def run_main(argv: list[str]) -> tuple[int, str, str]:
    """CLI 를 in-process 로 돌리고 (exit code, stdout, stderr) 를 돌려준다."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = importer.main(argv)
    return code, out.getvalue(), err.getvalue()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def chzzk_chat(
    *,
    offset_ms: int,
    content: str,
    type_code: str | int,
    user_id: str,
    nickname: str,
    pay_amount: int | None = None,
) -> dict:
    extras = {"payAmount": pay_amount} if pay_amount is not None else {}
    return {
        "playerMessageTime": str(offset_ms),
        "content": content,
        "messageTypeCode": type_code,
        "userIdHash": user_id,
        "profile": json.dumps({"nickname": nickname, "userIdHash": user_id}, ensure_ascii=False),
        "extras": json.dumps(extras, ensure_ascii=False),
    }


CHZZK_RAW = {
    "videoNo": 918273,
    "videoChats": [
        chzzk_chat(
            offset_ms=1000,
            content="안녕하세요 반가워요",
            type_code="1",
            user_id="u1hash",
            nickname="닉네임1",
        ),
        chzzk_chat(
            offset_ms=2000,
            content="{:heart:}",
            type_code=1,
            user_id="u2hash",
            nickname="닉네임2",
        ),
        chzzk_chat(
            offset_ms=3000,
            content="후원 감사합니다 화이팅",
            type_code="10",
            user_id="u3hash",
            nickname="닉네임3",
            pay_amount=5000,
        ),
        chzzk_chat(
            offset_ms=4000,
            content="안녕하세요 반가워요",
            type_code="1",
            user_id="u1hash",
            nickname="닉네임1",
        ),
        chzzk_chat(
            offset_ms=5000,
            content="http://example.com 링크에요 확인점",
            type_code="1",
            user_id="u4hash",
            nickname="닉네임4",
        ),
        chzzk_chat(
            offset_ms=6000,
            content="공지사항입니다",
            type_code="0",
            user_id="u5hash",
            nickname="닉네임5",
        ),
    ],
}


def youtube_text_item(
    *, video_offset_ms: str | None, timestamp_usec: str, text: str, author_id: str, msg_id: str
) -> dict:
    envelope = {
        "replayChatItemAction": {
            "actions": [
                {
                    "addChatItemAction": {
                        "item": {
                            "liveChatTextMessageRenderer": {
                                "message": {"runs": [{"text": text}]},
                                "authorName": {"simpleText": "@" + author_id},
                                "authorExternalChannelId": "UC_" + author_id,
                                "id": msg_id,
                                "timestampUsec": timestamp_usec,
                            }
                        }
                    }
                }
            ]
        }
    }
    if video_offset_ms is not None:
        envelope["videoOffsetTimeMsec"] = video_offset_ms
    return envelope


YOUTUBE_TEXT_LINE = youtube_text_item(
    video_offset_ms="1000",
    timestamp_usec="1700000000000000",
    text="안녕하세요 반가워요",
    author_id="user1",
    msg_id="msg1",
)
YOUTUBE_EMOJI_ONLY_LINE = {
    "replayChatItemAction": {
        "actions": [
            {
                "addChatItemAction": {
                    "item": {
                        "liveChatTextMessageRenderer": {
                            "message": {"runs": [{"emoji": {"emojiId": "smile"}}]},
                            "authorName": {"simpleText": "@user2"},
                            "authorExternalChannelId": "UC_user2",
                            "id": "msg2",
                            "timestampUsec": "1700000002000000",
                        }
                    }
                }
            }
        ]
    },
    "videoOffsetTimeMsec": "2000",
}
YOUTUBE_PLACEHOLDER_LINE = {
    "replayChatItemAction": {
        "actions": [
            {"addChatItemAction": {"item": {"liveChatPlaceholderItemRenderer": {"id": "ph1"}}}}
        ]
    },
    "videoOffsetTimeMsec": "3000",
}
YOUTUBE_PAID_LINE = {
    "replayChatItemAction": {
        "actions": [
            {
                "addChatItemAction": {
                    "item": {
                        "liveChatPaidMessageRenderer": {
                            "message": {"runs": [{"text": "후원 감사합니다 화이팅"}]},
                            "purchaseAmountText": {"simpleText": "₩5,000"},
                            "authorName": {"simpleText": "@user3"},
                            "authorExternalChannelId": "UC_user3",
                            "id": "msg4",
                            "timestampUsec": "1700000004000000",
                        }
                    }
                }
            }
        ]
    }
    # videoOffsetTimeMsec 의도적으로 없음: timestampUsec 기반 파생 경로를 검증한다.
}

YOUTUBE_LINES = [
    json.dumps(YOUTUBE_TEXT_LINE, ensure_ascii=False),
    json.dumps(YOUTUBE_EMOJI_ONLY_LINE, ensure_ascii=False),
    json.dumps(YOUTUBE_PLACEHOLDER_LINE, ensure_ascii=False),
    json.dumps(YOUTUBE_PAID_LINE, ensure_ascii=False),
]


class ChzzkParseTest(unittest.TestCase):
    def test_keeps_only_normal_and_donation_type_codes(self) -> None:
        records, stats = importer.parse_chzzk(CHZZK_RAW)
        self.assertEqual(stats["system_type"], 1)
        self.assertEqual(len(records), 5)
        self.assertEqual([r.kind for r in records], ["chat", "chat", "donation", "chat", "chat"])

    def test_donation_amount_label_from_extras(self) -> None:
        records, _stats = importer.parse_chzzk(CHZZK_RAW)
        donation = next(r for r in records if r.kind == "donation")
        self.assertEqual(donation.amount_label, "5000")

    def test_video_id_override(self) -> None:
        records, _stats = importer.parse_chzzk(CHZZK_RAW, video_id_override="override-id")
        self.assertTrue(all(r.video_id_raw == "override-id" for r in records))


class YoutubeParseTest(unittest.TestCase):
    def test_ignores_placeholder_and_skips_emoji_runs(self) -> None:
        records, stats = importer.parse_youtube(YOUTUBE_LINES, video_id_override="yt-video-1")
        self.assertEqual(stats["not_message"], 1)
        # emoji-only 는 records 로는 만들어지되(내용 필터는 normalize 단계) 텍스트가 빈 문자열이어야 한다.
        self.assertEqual(len(records), 3)
        by_id = {r.user_id_raw: r for r in records}
        self.assertEqual(by_id["UC_user1"].text, "안녕하세요 반가워요")
        self.assertEqual(by_id["UC_user2"].text, "")

    def test_offset_derived_from_timestamp_when_missing(self) -> None:
        records, _stats = importer.parse_youtube(YOUTUBE_LINES, video_id_override="yt-video-1")
        by_id = {r.user_id_raw: r for r in records}
        self.assertEqual(by_id["UC_user1"].offset_ms, 1000)
        self.assertEqual(by_id["UC_user3"].offset_ms, 4000)
        self.assertEqual(by_id["UC_user3"].kind, "donation")
        self.assertEqual(by_id["UC_user3"].amount_label, "₩5,000")


class NormalizeMessagesTest(unittest.TestCase):
    def test_chzzk_pipeline_counts_and_drops(self) -> None:
        records, parse_stats = importer.parse_chzzk(CHZZK_RAW)
        rows, filter_stats = importer.normalize_messages(
            records,
            source="chzzk",
            hmac_key=b"k" * 32,
            min_chars=2,
            max_chars=160,
            drop_links=True,
            dedupe_window=20,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(filter_stats["empty"], 1)
        self.assertEqual(filter_stats["link"], 1)
        self.assertEqual(filter_stats["duplicate"], 1)
        self.assertEqual(filter_stats["no_hangul"], 0)
        self.assertEqual(filter_stats["length"], 0)
        self.assertEqual(parse_stats["system_type"], 1)
        kinds = {row["kind"] for row in rows}
        self.assertEqual(kinds, {"chat", "donation"})

    def test_no_hangul_only_latin_or_punctuation_is_dropped(self) -> None:
        records = [
            importer.RawMessage("v", "u1", 0, "chat", "hello!! 123", ""),
            importer.RawMessage("v", "u2", 1, "chat", "안녕하세요 다들", ""),
        ]
        rows, stats = importer.normalize_messages(
            records,
            source="chzzk",
            hmac_key=b"k" * 32,
            min_chars=2,
            max_chars=160,
            drop_links=True,
            dedupe_window=20,
        )
        self.assertEqual(stats["no_hangul"], 1)
        self.assertEqual(len(rows), 1)

    def test_keep_links_flag_disables_link_drop(self) -> None:
        records = [importer.RawMessage("v", "u1", 0, "chat", "여기 확인 www.example.com 부탁", "")]
        rows, stats = importer.normalize_messages(
            records,
            source="chzzk",
            hmac_key=b"k" * 32,
            min_chars=2,
            max_chars=160,
            drop_links=False,
            dedupe_window=20,
        )
        self.assertEqual(stats["link"], 0)
        self.assertEqual(len(rows), 1)


class PseudonymTest(unittest.TestCase):
    def test_video_ref_is_stable_sha256_prefix(self) -> None:
        expected = hashlib.sha256(b"918273").hexdigest()[:12]
        self.assertEqual(importer.hash_video_ref("918273"), expected)

    def test_author_stable_for_same_user_and_source(self) -> None:
        key = b"k" * 32
        first = importer.hash_author(key, "chzzk", "u1hash")
        second = importer.hash_author(key, "chzzk", "u1hash")
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("v"))

    def test_author_differs_across_users_and_sources(self) -> None:
        key = b"k" * 32
        a = importer.hash_author(key, "chzzk", "u1hash")
        b = importer.hash_author(key, "chzzk", "u2hash")
        c = importer.hash_author(key, "youtube", "u1hash")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)

    def test_unknown_nickname_style_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            importer.hash_author(b"k" * 32, "chzzk", "u1hash", style="real")


class KoreanNicknameTest(unittest.TestCase):
    KEY = b"k" * 32

    def test_word_pool_is_large_distinct_and_two_syllable_hangul(self) -> None:
        pool = importer.KOREAN_NICKNAME_WORDS
        self.assertGreaterEqual(len(pool), 40)
        self.assertEqual(len(set(pool)), len(pool))
        for word in pool:
            self.assertRegex(word, r"^[가-힣]{2}$")

    def test_nickname_is_stable_for_the_same_key_source_and_user(self) -> None:
        first = importer.hash_author(self.KEY, "chzzk", "u1hash", style="korean")
        second = importer.hash_author(self.KEY, "chzzk", "u1hash", style="korean")
        self.assertEqual(first, second)

    def test_nickname_shape_stays_short_and_readable(self) -> None:
        for user in ("u1hash", "u2hash", "u3hash", "UC_user1", "UC_user2"):
            nickname = importer.hash_author(self.KEY, "chzzk", user, style="korean")
            with self.subTest(user=user):
                self.assertRegex(nickname, r"^[가-힣]{4}[0-9]{2}$")
                self.assertLessEqual(len(nickname), 8)

    def test_nickname_differs_across_users_sources_and_keys(self) -> None:
        base = importer.hash_author(self.KEY, "chzzk", "u1hash", style="korean")
        self.assertNotEqual(base, importer.hash_author(self.KEY, "chzzk", "u2hash", style="korean"))
        self.assertNotEqual(base, importer.hash_author(self.KEY, "youtube", "u1hash", style="korean"))
        self.assertNotEqual(base, importer.hash_author(b"j" * 32, "chzzk", "u1hash", style="korean"))

    def test_nickname_never_reuses_the_hash_style_value(self) -> None:
        hashed = importer.hash_author(self.KEY, "chzzk", "u1hash")
        korean = importer.hash_author(self.KEY, "chzzk", "u1hash", style="korean")
        self.assertTrue(hashed.startswith("v"))
        self.assertNotIn(hashed[1:], korean)


class NormalizeCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.key_file = self.root / "key.bin"

    def _write_chzzk_input(self) -> Path:
        path = self.root / "raw-chzzk.json"
        path.write_text(json.dumps(CHZZK_RAW, ensure_ascii=False), encoding="utf-8")
        return path

    def _write_youtube_input(self) -> Path:
        path = self.root / "raw-youtube.jsonl"
        path.write_text("\n".join(YOUTUBE_LINES) + "\n", encoding="utf-8")
        return path

    def test_chzzk_normalize_end_to_end(self) -> None:
        input_path = self._write_chzzk_input()
        output_path = self.root / "out.jsonl"
        code, stdout, _err = run_main(
            [
                "normalize", "--format", "chzzk",
                "--input", str(input_path), "--output", str(output_path),
                "--hmac-key-file", str(self.key_file),
            ]
        )
        self.assertEqual(code, 0)
        rows = read_jsonl(output_path)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["offset_ms"] for row in rows], sorted(row["offset_ms"] for row in rows))
        for row in rows:
            self.assertEqual(row["source"], "chzzk")
            self.assertEqual(set(row), {"source", "video_ref", "offset_ms", "author", "kind", "text", "amount_label"})
        self.assertIn("in=5", stdout)
        self.assertIn("out=2", stdout)
        self.assertIn("unique_authors=2", stdout)
        self.assertTrue(self.key_file.is_file())

    def test_output_never_contains_nickname_or_raw_ids(self) -> None:
        input_path = self._write_chzzk_input()
        output_path = self.root / "out.jsonl"
        run_main(
            [
                "normalize", "--format", "chzzk",
                "--input", str(input_path), "--output", str(output_path),
                "--hmac-key-file", str(self.key_file),
            ]
        )
        raw_text = output_path.read_text(encoding="utf-8")
        for forbidden in ("닉네임1", "닉네임3", "u1hash", "u3hash", "userIdHash", "nickname"):
            self.assertNotIn(forbidden, raw_text)

    def test_key_file_created_then_reused_yields_same_pseudonyms(self) -> None:
        input_path = self._write_chzzk_input()
        first_output = self.root / "first.jsonl"
        second_output = self.root / "second.jsonl"
        self.assertFalse(self.key_file.exists())
        code1, _out1, _err1 = run_main(
            [
                "normalize", "--format", "chzzk",
                "--input", str(input_path), "--output", str(first_output),
                "--hmac-key-file", str(self.key_file),
            ]
        )
        self.assertEqual(code1, 0)
        self.assertTrue(self.key_file.is_file())
        key_bytes_after_first = self.key_file.read_bytes()

        code2, _out2, _err2 = run_main(
            [
                "normalize", "--format", "chzzk",
                "--input", str(input_path), "--output", str(second_output),
                "--hmac-key-file", str(self.key_file),
            ]
        )
        self.assertEqual(code2, 0)
        self.assertEqual(self.key_file.read_bytes(), key_bytes_after_first)

        first_authors = [row["author"] for row in read_jsonl(first_output)]
        second_authors = [row["author"] for row in read_jsonl(second_output)]
        self.assertEqual(first_authors, second_authors)

    def test_korean_nickname_style_is_opt_in_and_stable(self) -> None:
        input_path = self._write_chzzk_input()
        default_output = self.root / "default.jsonl"
        korean_output = self.root / "korean.jsonl"
        again_output = self.root / "korean-again.jsonl"
        base = [
            "normalize", "--format", "chzzk", "--input", str(input_path),
            "--hmac-key-file", str(self.key_file),
        ]
        self.assertEqual(run_main(base + ["--output", str(default_output)])[0], 0)
        self.assertEqual(
            run_main(base + ["--output", str(korean_output), "--nickname-style", "korean"])[0], 0)
        self.assertEqual(
            run_main(base + ["--output", str(again_output), "--nickname-style", "korean"])[0], 0)

        default_authors = [row["author"] for row in read_jsonl(default_output)]
        korean_authors = [row["author"] for row in read_jsonl(korean_output)]
        self.assertTrue(all(author.startswith("v") for author in default_authors))
        for author in korean_authors:
            self.assertRegex(author, r"^[가-힣]{4}[0-9]{2}$")
        self.assertEqual(len(set(korean_authors)), len(set(default_authors)))
        # 같은 키로 다시 돌리면 같은 가명이 나온다.
        self.assertEqual(korean_authors, [row["author"] for row in read_jsonl(again_output)])
        # 실제 닉네임·원본 id 는 여기서도 절대 나오지 않는다.
        raw_text = korean_output.read_text(encoding="utf-8")
        for forbidden in ("닉네임1", "닉네임3", "u1hash", "u3hash", "userIdHash", "nickname"):
            self.assertNotIn(forbidden, raw_text)

    def test_never_prints_the_hmac_key(self) -> None:
        input_path = self._write_chzzk_input()
        output_path = self.root / "out.jsonl"
        code, stdout, err = run_main(
            [
                "normalize", "--format", "chzzk",
                "--input", str(input_path), "--output", str(output_path),
                "--hmac-key-file", str(self.key_file),
            ]
        )
        self.assertEqual(code, 0)
        key_hex = self.key_file.read_bytes().hex()
        self.assertNotIn(key_hex, stdout)
        self.assertNotIn(key_hex, err)

    def test_youtube_requires_video_id(self) -> None:
        input_path = self._write_youtube_input()
        output_path = self.root / "out.jsonl"
        code, _stdout, err = run_main(
            [
                "normalize", "--format", "youtube",
                "--input", str(input_path), "--output", str(output_path),
                "--hmac-key-file", str(self.key_file),
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("--video-id", err)
        self.assertFalse(output_path.exists())

    def test_youtube_normalize_end_to_end(self) -> None:
        input_path = self._write_youtube_input()
        output_path = self.root / "out.jsonl"
        stats_path = self.root / "stats.json"
        code, stdout, _err = run_main(
            [
                "normalize", "--format", "youtube",
                "--input", str(input_path), "--output", str(output_path),
                "--hmac-key-file", str(self.key_file),
                "--video-id", "yt-video-1",
                "--stats-output", str(stats_path),
            ]
        )
        self.assertEqual(code, 0)
        rows = read_jsonl(output_path)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["kind"] for row in rows], ["chat", "donation"])
        self.assertEqual([row["offset_ms"] for row in rows], [1000, 4000])
        expected_ref = hashlib.sha256(b"yt-video-1").hexdigest()[:12]
        self.assertTrue(all(row["video_ref"] == expected_ref for row in rows))
        self.assertIn("in=3", stdout)
        self.assertIn("out=2", stdout)
        self.assertIn("not_message=1", stdout)

        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        self.assertEqual(stats["in"], 3)
        self.assertEqual(stats["out"], 2)
        self.assertEqual(stats["not_message"], 1)
        self.assertEqual(stats["unique_authors"], 2)

    def test_refuses_output_inside_repository(self) -> None:
        input_path = self._write_chzzk_input()
        inside = importer.REPO_ROOT / "import-public-chat-should-not-exist.jsonl"
        code, _stdout, err = run_main(
            [
                "normalize", "--format", "chzzk",
                "--input", str(input_path), "--output", str(inside),
                "--hmac-key-file", str(self.key_file),
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing", err)
        self.assertFalse(inside.exists())

    def test_allow_repo_path_overrides_refusal(self) -> None:
        input_path = self._write_chzzk_input()
        output_path = self.root / "inside.jsonl"
        with patch.object(importer, "REPO_ROOT", self.root):
            refused_code, _stdout, err = run_main(
                [
                    "normalize", "--format", "chzzk",
                    "--input", str(input_path), "--output", str(output_path),
                    "--hmac-key-file", str(self.key_file),
                ]
            )
            self.assertEqual(refused_code, 1)
            self.assertIn("refusing", err)
            allowed_code, _stdout2, _err2 = run_main(
                [
                    "normalize", "--format", "chzzk",
                    "--input", str(input_path), "--output", str(output_path),
                    "--hmac-key-file", str(self.key_file),
                    "--allow-repo-path",
                ]
            )
        self.assertEqual(allowed_code, 0)
        self.assertEqual(len(read_jsonl(output_path)), 2)


def audio_playback(*, m3u: str | None, mime: str = "audio/mp4") -> dict:
    """실제 Chzzk playback 응답의 모양만 최소로 재현한다."""
    representation = {"id": "aud-1", "otherAttributes": {}}
    if m3u is not None:
        representation["otherAttributes"]["m3u"] = m3u
    return {"period": [{"adaptationSet": [
        {"mimeType": "video/mp4", "representation": [{"id": "vid-1", "otherAttributes": {}}]},
        {"mimeType": mime, "representation": [representation]},
    ]}]}


class ChzzkAudioTest(unittest.TestCase):
    SIGNED = "https://cdn.example/base/dir/media.m3u8?_lsu_sa_=TOKEN"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def fake_json(self, playback: dict, duration: float = 120.0):
        def fetch(url: str) -> dict:
            if "/service/v2/videos/" in url:
                return {"content": {"videoId": "VID", "inKey": "KEY", "duration": duration}}
            self.assertIn("playback/VID?key=KEY", url)
            return playback
        return fetch

    def test_resolved_url_keeps_the_signing_token_on_the_segment_file(self) -> None:
        # 서명 토큰은 플레이리스트 URL 에만 붙는다.  세그먼트 상대경로에 옮겨 붙이지 않으면
        # 실제로 400 이 난다(2026-08-27 실측).
        url, duration = resolve_url(self.fake_json(audio_playback(m3u=self.SIGNED)))
        self.assertEqual(url, "https://cdn.example/base/dir/aud-1.m4a?_lsu_sa_=TOKEN")
        self.assertEqual(duration, 120.0)

    def test_video_track_is_not_mistaken_for_audio(self) -> None:
        playback = audio_playback(m3u=self.SIGNED, mime="video/mp4")
        with self.assertRaises(ValueError):
            resolve_url(self.fake_json(playback))

    def test_missing_playlist_attribute_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_url(self.fake_json(audio_playback(m3u=None)))

    def test_private_video_without_keys_is_rejected(self) -> None:
        def fetch(_url: str) -> dict:
            return {"content": {}}
        with self.assertRaises(ValueError):
            importer.resolve_chzzk_audio_url(1, fetch_json=fetch)

    def test_download_streams_to_disk_and_refuses_repo_paths(self) -> None:
        payload = b"\x00\x01" * 4096

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        destination = self.root / "audio.m4a"
        written = importer.download_chzzk_audio(
            7, destination,
            fetch_json=self.fake_json(audio_playback(m3u=self.SIGNED)),
            opener=lambda _url: FakeResponse(payload),
        )
        self.assertEqual(written, len(payload))
        self.assertEqual(destination.read_bytes(), payload)

    def test_cli_refuses_to_write_inside_the_repo(self) -> None:
        inside = Path(importer.REPO_ROOT) / "should-not-exist.m4a"
        code, _out, err = run_main(["chzzk-audio", "--video-no", "7", "--output", str(inside)])
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertFalse(inside.exists())


def resolve_url(fetch_json):
    return importer.resolve_chzzk_audio_url(1, fetch_json=fetch_json)


class ChzzkFetchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_pagination_stops_after_three_pages(self) -> None:
        calls: list[int] = []
        pages = {
            0: {"code": 200, "content": {"videoChats": [{"a": 1}, {"a": 2}], "nextPlayerMessageTime": 1000}},
            1000: {"code": 200, "content": {"videoChats": [{"a": 3}, {"a": 4}], "nextPlayerMessageTime": 2000}},
            2000: {"code": 200, "content": {"videoChats": [{"a": 5}], "nextPlayerMessageTime": None}},
        }

        def fake_fetch(video_no: int, cursor: int) -> dict:
            calls.append(cursor)
            return pages[cursor]

        output_path = self.root / "raw.json"
        with patch.object(importer, "_http_fetch_chzzk_page", fake_fetch):
            code, stdout, _err = run_main(
                [
                    "chzzk-fetch", "--video-no", "999", "--output", str(output_path),
                    "--sleep", "0",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(calls, [0, 1000, 2000])
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"videoNo": 999, "videoChats": [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}, {"a": 5}]})
        self.assertIn("chats=5", stdout)

    def test_stops_when_no_chats_in_page(self) -> None:
        def fake_fetch(video_no: int, cursor: int) -> dict:
            return {"code": 200, "content": {"videoChats": [], "nextPlayerMessageTime": 999}}

        output_path = self.root / "raw.json"
        with patch.object(importer, "_http_fetch_chzzk_page", fake_fetch):
            code, _stdout, _err = run_main(
                ["chzzk-fetch", "--video-no", "1", "--output", str(output_path), "--sleep", "0"]
            )
        self.assertEqual(code, 0)
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["videoChats"], [])

    def test_refuses_output_inside_repository(self) -> None:
        inside = importer.REPO_ROOT / "chzzk-fetch-should-not-exist.json"
        code, _stdout, err = run_main(
            ["chzzk-fetch", "--video-no", "1", "--output", str(inside), "--sleep", "0"]
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing", err)
        self.assertFalse(inside.exists())


if __name__ == "__main__":
    unittest.main()
