import base64
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

import openai_stt_server as stt


class StreamingTranscriptionTests(unittest.TestCase):
    def test_pcm16_stream_emits_partial_then_final_with_injected_transcriber(self):
        client = TestClient(stt.app, client=("127.0.0.1", 50000))
        seen = []

        def fake(samples, sample_rate, language):
            seen.append((len(samples), sample_rate, language))
            return "hello" if len(seen) == 1 else "hello world"

        pcm = np.zeros(int(stt.STREAM_MIN_DECODE_SECONDS * stt.STREAM_SAMPLE_RATE), dtype="<i2").tobytes()
        with patch.object(stt, "STREAM_TRANSCRIBER", fake):
            with client.websocket_connect("/v1/audio/transcriptions/stream") as ws:
                ws.send_json({"type": "start", "format": "pcm16", "sample_rate": 16000, "language": "en"})
                self.assertEqual(ws.receive_json()["type"], "started")
                ws.send_json({"type": "pcm16", "data": base64.b64encode(pcm).decode()})
                self.assertEqual(ws.receive_json(), {"type": "partial", "delta": "hello", "text": "hello"})
                ws.send_json({"type": "end"})
                self.assertEqual(ws.receive_json(), {"type": "final", "text": "hello world"})
        self.assertEqual(seen[0][1:], (16000, "en"))

    def test_stream_rejects_oversize_frame_before_transcribing(self):
        client = TestClient(stt.app, client=("127.0.0.1", 50000))
        with client.websocket_connect("/v1/audio/transcriptions/stream") as ws:
            ws.send_json({"type": "start"})
            ws.receive_json()
            ws.send_json({"type": "pcm16", "data": base64.b64encode(b"\0" * (stt.STREAM_MAX_FRAME_BYTES + 2)).decode()})
            self.assertEqual(ws.receive_json()["code"], "frame_too_large")

    def test_partial_uses_rolling_window_but_final_receives_full_utterance(self):
        client = TestClient(stt.app, client=("127.0.0.1", 50000))
        seen_sample_counts = []

        def fake(samples, _sample_rate, _language):
            seen_sample_counts.append(len(samples))
            return f"samples-{len(samples)}"

        # A two-second turn arrives in one frame. The partial retains one
        # second, while the final must receive all two seconds.
        # A tiny test-only sample rate avoids coupling this protocol test to
        # the TestClient websocket implementation's large-message behavior.
        first = np.zeros(200, dtype="<i2").tobytes()
        with patch.object(stt, "STREAM_TRANSCRIBER", fake), \
             patch.object(stt, "STREAM_SAMPLE_RATE", 100), \
             patch.object(stt, "STREAM_WINDOW_SECONDS", 1), \
             patch.object(stt, "STREAM_MIN_DECODE_SECONDS", 0.1):
            with client.websocket_connect("/v1/audio/transcriptions/stream") as ws:
                ws.send_json({"type": "start"})
                ws.receive_json()
                ws.send_json({"type": "pcm16", "data": base64.b64encode(first).decode()})
                self.assertEqual(ws.receive_json()["text"], "samples-100")
                ws.send_json({"type": "end"})
                self.assertEqual(ws.receive_json(), {"type": "final", "text": "samples-200"})

        self.assertEqual(seen_sample_counts, [100, 200])
