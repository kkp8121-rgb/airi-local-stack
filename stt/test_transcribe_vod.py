"""배치 트랜스크립션의 오프라인 계약 테스트. faster-whisper 없이도 돈다."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import transcribe_vod as batch  # noqa: E402

# run_broadcast_sim.TRANSCRIPT_ROW_KEYS 와 같아야 한다. 어긋나면 --replay-transcript 가 거부한다.
REQUIRED_KEYS = {"start_ms", "end_ms", "text"}


@dataclass
class FakeSegment:
    start: float
    end: float
    text: str


class WriteTranscriptTests(unittest.TestCase):
    def write(self, segments, *, max_segment_seconds: float = 30.0):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.jsonl"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                result = batch.write_transcript(
                    segments, out, max_segment_seconds=max_segment_seconds,
                    started=time.perf_counter())
            rows = [json.loads(line) for line in out.read_text("utf-8").splitlines() if line.strip()]
            return result, rows, buffer.getvalue()

    def test_rows_match_the_replay_transcript_contract(self):
        (count, chars, _long), rows, _out = self.write(
            [FakeSegment(1.25, 3.5, " 안녕 "), FakeSegment(4.0, 5.0, "반가워")])
        self.assertEqual(count, 2)
        self.assertEqual(chars, len("안녕") + len("반가워"))
        self.assertEqual(set(rows[0]), REQUIRED_KEYS)
        self.assertEqual(rows[0], {"start_ms": 1250, "end_ms": 3500, "text": "안녕"})

    def test_blank_segments_are_dropped(self):
        (count, _chars, _long), rows, _out = self.write(
            [FakeSegment(0.0, 1.0, "   "), FakeSegment(1.0, 2.0, "응")])
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]["text"], "응")

    def test_overlong_segment_is_counted_but_kept(self):
        # VAD 가 대기화면 구간을 통째로 뭉개는 일이 있다(실측 296초). 버리지 말고 알린다.
        (count, _chars, long_segments), rows, _out = self.write(
            [FakeSegment(21.0, 318.0, "개꿈꾼 리제가 왔어"), FakeSegment(320.0, 322.0, "응")])
        self.assertEqual(count, 2)
        self.assertEqual(long_segments, 1)
        self.assertEqual(len(rows), 2)


class PinTests(unittest.TestCase):
    def test_defaults_match_the_streaming_server(self):
        server = (Path(__file__).resolve().parent / "openai_stt_server.py").read_text("utf-8")
        self.assertIn(f'MODEL_NAME = "{batch.MODEL_NAME}"', server)
        self.assertIn(f"BEAM_SIZE = {batch.BEAM_SIZE}", server)


class CliTests(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = batch.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_missing_audio_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _out, err = self.run_main(
                ["--input", str(Path(tmp) / "nope.wav"), "--output", str(Path(tmp) / "t.jsonl")])
        self.assertEqual(code, 1)
        self.assertIn("오디오 파일이 없다", err)

    def test_cpu_defaults_are_the_gpu_free_override(self):
        args = batch.build_parser().parse_args(["--input", "a", "--output", "b"])
        self.assertEqual((args.device, args.compute_type), ("cpu", "int8"))


if __name__ == "__main__":
    unittest.main()
