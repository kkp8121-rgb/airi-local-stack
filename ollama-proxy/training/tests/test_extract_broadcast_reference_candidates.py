import json
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from extract_broadcast_reference_candidates import (  # noqa: E402
    CandidateExtractionError,
    extract,
)


def event(second: int, text: str) -> dict:
    return {"tStartMs": second * 1000, "segs": [{"utf8": text}]}


class ExtractBroadcastReferenceCandidatesTest(unittest.TestCase):
    def test_emits_only_time_categories_and_counts(self) -> None:
        raw_secret = "가상시청자99님 후원 고마워, 아까 그 선택 다시 보자"
        payload = {
            "events": [
                event(10, raw_secret),
                event(18, "채팅이 정정해 줬네"),
                event(70, "여러분 또 들켰다"),
            ]
        }
        report = extract(payload, source_ref="refscan-korean-vod-a")
        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["candidates"][0]["start_seconds"], 10)
        self.assertEqual(report["candidates"][0]["end_seconds"], 18)
        self.assertEqual(
            report["candidates"][0]["cue_categories"],
            ["audience_address", "continuity", "correction", "support_event"],
        )
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(raw_secret, serialized)
        self.assertNotIn("가상시청자99", serialized)
        self.assertNotIn("후원 고마워", serialized)
        self.assertFalse(report["raw_caption_retained"])
        self.assertFalse(report["training_permitted"])

    def test_min_hits_filters_weak_windows_without_changing_group_ids(self) -> None:
        payload = {"events": [event(5, "고마워"), event(50, "아까"), event(55, "다시")]}
        report = extract(payload, source_ref="refscan-korean-vod-b", min_hits=2)
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["candidates"][0]["candidate_id"], "refscan-korean-vod-b-c0002")

    def test_source_reference_and_json3_shape_fail_closed(self) -> None:
        for source_ref in ("video123", "refscan-https://youtube.com/x", "refscan-@handle"):
            with self.subTest(source_ref=source_ref):
                with self.assertRaises(CandidateExtractionError):
                    extract({"events": []}, source_ref=source_ref)
        with self.assertRaises(CandidateExtractionError):
            extract({}, source_ref="refscan-valid-source")
        with self.assertRaises(CandidateExtractionError):
            extract({"events": [{"tStartMs": -1, "segs": [{"utf8": "후원"}]}]}, source_ref="refscan-valid-source")

    def test_is_deterministic(self) -> None:
        payload = {"events": [event(1, "채팅"), event(2, "아까"), event(30, "감사")]}
        self.assertEqual(
            extract(payload, source_ref="refscan-determinism"),
            extract(payload, source_ref="refscan-determinism"),
        )


if __name__ == "__main__":
    unittest.main()
