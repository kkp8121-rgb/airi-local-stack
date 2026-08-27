"""응답 짝짓기의 오프라인 계약 테스트. 네트워크·모델 없이 돈다."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pair_streamer_response as pairer  # noqa: E402


def chat(offset_ms: int, text: str, author: str = "vaaaaaaaa") -> dict:
    return {"offset_ms": offset_ms, "text": text, "author": author, "kind": "chat"}


def speech(start_ms: int, text: str, length_ms: int = 4_000) -> dict:
    return {"start_ms": start_ms, "end_ms": start_ms + length_ms, "text": text}


class PairingTests(unittest.TestCase):
    def test_streamer_answering_a_viewer_is_paired(self):
        result = pairer.pair_responses(
            [chat(10_000, "미세결절은 머징")],
            [speech(15_000, "미세결절은 뭐야 아직 결절이 온 건 아닌데")])
        self.assertEqual(result["stats"]["responded"], 1)
        pair = result["pairs"][0]
        self.assertIn("미세결절", " ".join(pair["shared_terms"]))
        self.assertEqual(pair["delay_ms"], 5_000)

    def test_viewer_echoing_the_streamer_is_not_a_response(self):
        # 방향 오탐. 스트리머가 먼저 말하고 시청자가 따라한 뒤 스트리머가 또 말한 경우다.
        result = pairer.pair_responses(
            [chat(10_000, "본능에 충실한편")],
            [speech(4_000, "좀 본능에 충실한 편이라"), speech(12_000, "본능에 충실하죠")])
        self.assertEqual(result["stats"]["responded"], 0)
        self.assertEqual(result["stats"]["viewer_echoed_streamer"], 1)

    def test_speech_before_the_chat_is_not_a_response(self):
        result = pairer.pair_responses(
            [chat(20_000, "스트랩실 유명하지")], [speech(1_000, "스트랩실 진짜 별로야")])
        self.assertEqual(result["stats"]["responded"], 0)

    def test_speech_after_the_window_is_not_a_response(self):
        result = pairer.pair_responses(
            [chat(0, "녹음 조심해야겠네")], [speech(60_000, "녹음 더 조심해야겠네")],
            response_window_ms=20_000)
        self.assertEqual(result["stats"]["responded"], 0)

    def test_overlong_segment_is_excluded(self):
        # 실측에서 대기화면 구간이 296초짜리 한 세그먼트로 뭉개졌다.
        result = pairer.pair_responses(
            [chat(30_000, "위기감지를 했구나")],
            [speech(21_000, "위기감지를 하고", length_ms=296_000)])
        self.assertEqual(result["stats"]["speech_dropped_overlong"], 1)
        self.assertEqual(result["stats"]["responded"], 0)

    def test_common_words_alone_do_not_pair(self):
        result = pairer.pair_responses(
            [chat(0, "그럼 오늘 우리")], [speech(3_000, "그럼 오늘 우리 시작할게")])
        self.assertEqual(result["stats"]["responded"], 0)

    def test_best_match_is_the_segment_sharing_most_terms(self):
        result = pairer.pair_responses(
            [chat(0, "스트랩실 사탕 맛있어")],
            [speech(2_000, "사탕 얘기가 나와서"), speech(6_000, "스트랩실 사탕은 진짜")])
        self.assertEqual(result["pairs"][0]["speech_start_ms"], 6_000)
        self.assertGreaterEqual(len(result["pairs"][0]["shared_terms"]), 2)

    def test_chats_after_the_audio_window_are_ignored(self):
        result = pairer.pair_responses(
            [chat(1_000, "염증 조심해"), chat(999_000, "나중에 온 채팅")],
            [speech(3_000, "염증은 약 먹고 있어")])
        self.assertEqual(result["stats"]["chats_in_audio_window"], 1)
        self.assertEqual(result["stats"]["chats_total"], 2)


class CliTests(unittest.TestCase):
    def test_cli_writes_pairs_and_reports_content_free_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "chat.jsonl").write_text(
                json.dumps(chat(10_000, "미세결절은 머징"), ensure_ascii=False) + "\n",
                encoding="utf-8")
            (root / "speech.jsonl").write_text(
                json.dumps(speech(15_000, "미세결절은 뭐야"), ensure_ascii=False) + "\n",
                encoding="utf-8")
            out = root / "pairs.jsonl"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = pairer.main(["--chat", str(root / "chat.jsonl"),
                                    "--transcript", str(root / "speech.jsonl"),
                                    "--output", str(out)])
            printed = buffer.getvalue()
            rows = [json.loads(line) for line in out.read_text("utf-8").splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 1)
        self.assertIn("스트리머가 반응한 채팅: 1건", printed)
        # 통계 출력에 대화 원문이 새지 않아야 한다.
        self.assertNotIn("미세결절", printed)


if __name__ == "__main__":
    unittest.main()
