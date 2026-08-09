import unittest

from latency_trace import request_id


class RequestIdTests(unittest.TestCase):
    def test_round_id_is_authoritative_across_service_requests(self):
        headers = {
            "x-airi-round-id": "round-shared",
            "x-airi-request-id": "legacy-request",
            "x-request-id": "generic-request",
        }
        self.assertEqual(request_id(headers, "fallback"), "round-shared")

    def test_legacy_headers_and_fallback_remain_supported(self):
        self.assertEqual(
            request_id({"x-airi-request-id": "legacy"}, "fallback"),
            "legacy",
        )
        self.assertEqual(request_id({}, "fallback"), "fallback")

    def test_identifier_is_bounded(self):
        self.assertEqual(request_id({"x-airi-round-id": "r" * 200}, "fallback"), "r" * 128)


if __name__ == "__main__":
    unittest.main()
