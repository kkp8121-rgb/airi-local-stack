import asyncio
import struct
import sys

import numpy as np
import pytest

from api.services.audio_encoding import (
    AudioEncodingError,
    convert_to_pcm,
    convert_to_wav,
    encode_audio,
)
from api.services.text_processing import normalize_text


def test_url_normalization_handles_normal_domains():
    normalized = normalize_text("Visit https://example.com/docs and example.nz now.")
    assert "example dot com slash docs" in normalized
    assert "example dot nz" in normalized


def test_currency_is_not_misread_as_inches():
    normalized = normalize_text("Pay -$1.50 in 1 min.")
    assert "minus" in normalized
    assert "dollar" in normalized
    assert "inch" not in normalized
    assert "minute" in normalized


def test_pcm_is_signed_16_bit_little_endian():
    payload = convert_to_pcm(np.array([-1.0, 0.0, 1.0], dtype=np.float32))
    assert struct.unpack("<hhh", payload) == (-32768, 0, 32767)


def test_wav_header_matches_stereo_payload():
    audio = np.zeros((10, 2), dtype=np.float32)
    payload = convert_to_wav(audio, sample_rate=24000)
    assert payload[:4] == b"RIFF"
    assert payload[8:12] == b"WAVE"
    assert struct.unpack("<H", payload[22:24])[0] == 2
    assert struct.unpack("<I", payload[40:44])[0] == 40
    assert len(payload) == 84


def test_empty_audio_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        convert_to_pcm(np.array([], dtype=np.float32))


def test_compressed_encoding_never_silently_returns_wav(monkeypatch):
    monkeypatch.setitem(sys.modules, "pydub", None)
    with pytest.raises(AudioEncodingError, match="pydub"):
        encode_audio(np.zeros(32, dtype=np.float32), "mp3", 24000)


@pytest.mark.asyncio
async def test_backend_initializes_only_once_under_concurrency(monkeypatch):
    from api.backends import factory

    class DummyBackend:
        def __init__(self):
            self.ready = False
            self.initialize_calls = 0
            self.load_voice_calls = 0

        def is_ready(self):
            return self.ready

        async def initialize(self):
            self.initialize_calls += 1
            await asyncio.sleep(0.02)
            self.ready = True

        async def load_custom_voices(self, _path):
            self.load_voice_calls += 1

        def get_backend_name(self):
            return "dummy"

        def get_model_id(self):
            return "dummy/model"

    dummy = DummyBackend()
    monkeypatch.setattr(factory, "_backend_instance", dummy)
    monkeypatch.setattr(factory, "_initialization_lock", None)

    first, second = await asyncio.gather(
        factory.initialize_backend(),
        factory.initialize_backend(),
    )

    assert first is dummy and second is dummy
    assert dummy.initialize_calls == 1
    assert dummy.load_voice_calls == 1


def test_invalid_integer_environment_falls_back(monkeypatch):
    from api.backends import factory

    monkeypatch.setenv("CPU_THREADS", "not-a-number")
    assert factory._env_int("CPU_THREADS", 12) == 12
