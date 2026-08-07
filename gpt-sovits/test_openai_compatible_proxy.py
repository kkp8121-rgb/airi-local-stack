import unittest

import openai_compatible_proxy as proxy


class ImmediateResponseCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = dict(proxy._WAV_CACHE)
        self.status = dict(proxy._WAV_CACHE_STATUS)

    def tearDown(self):
        with proxy._WAV_CACHE_LOCK:
            proxy._WAV_CACHE.clear(); proxy._WAV_CACHE.update(self.cache)
            proxy._WAV_CACHE_STATUS.clear(); proxy._WAV_CACHE_STATUS.update(self.status)

    def test_cache_only_matches_wav_default_speed_and_known_phrase(self):
        with proxy._WAV_CACHE_LOCK:
            proxy._WAV_CACHE["응!"] = b"RIFFcached"
        self.assertEqual(proxy.cached_wav_for_request("응!", "wav", 1.0), b"RIFFcached")
        self.assertIsNone(proxy.cached_wav_for_request("응!", "pcm", 1.0))
        self.assertIsNone(proxy.cached_wav_for_request("응!", "wav", 1.1))
        self.assertIsNone(proxy.cached_wav_for_request("다른 사용자 문장", "wav", 1.0))

    def test_warmup_keeps_success_and_marks_failure_for_safe_fallback(self):
        original = proxy._fetch_wav_from_backend
        calls = []
        def fake_fetch(payload):
            calls.append(payload["text"])
            if payload["text"] == "응!": return b"RIFFok"
            raise RuntimeError("backend unavailable")
        try:
            proxy._fetch_wav_from_backend = fake_fetch
            proxy.warm_immediate_response_cache()
        finally:
            proxy._fetch_wav_from_backend = original
        self.assertEqual(proxy.cached_wav_for_request("응!", "wav", 1.0), b"RIFFok")
        self.assertEqual(proxy.cache_health()["states"]["바로 찾아볼게."], "failed")
        self.assertEqual(calls, list(proxy.IMMEDIATE_RESPONSE_TEXTS))

    def test_payload_preserves_existing_generation_options(self):
        payload = proxy.build_backend_payload("응!", 1.25)
        self.assertEqual(payload["text_lang"], "ko")
        self.assertEqual(payload["speed_factor"], 1.25)
        self.assertFalse(payload["parallel_infer"])


if __name__ == "__main__":
    unittest.main()
