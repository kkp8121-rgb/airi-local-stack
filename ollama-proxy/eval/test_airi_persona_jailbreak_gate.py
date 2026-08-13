import argparse
import copy
import http.client
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "persona_jailbreak_gate", Path(__file__).with_name("run_airi_persona_jailbreak_gate.py")
)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)

EXPECTED_DIGEST = "a" * 64


def args(**changes):
    values = {
        "endpoint": "http://127.0.0.1:11434/api/chat",
        "model": "synthetic-model",
        "expected_digest": EXPECTED_DIGEST,
        "num_ctx": 2048,
        "num_gpu": 999,
        "num_predict": 128,
        "timeout": 1.0,
    }
    values.update(changes)
    return argparse.Namespace(**values)


def marker_response(case, *, model="synthetic-model"):
    content = "BENIGN_OK" if case["category"] == "benign" else "AIRI SAFE_REFUSAL"
    return {
        "model": model,
        "done": True,
        "message": {"role": "assistant", "content": content},
        "prompt_eval_count": 12,
        "eval_count": 3,
        "prompt_eval_duration": 1_000_000,
        "eval_duration": 2_000_000,
        "total_duration": 4_000_000,
    }


def metadata_response(endpoint, method, path, payload, timeout):
    if method == "GET" and path == "/api/tags":
        return {"models": [{"name": "synthetic-model", "digest": EXPECTED_DIGEST}]}
    if method == "POST" and path == "/api/show":
        return {"details": {"family": "synthetic", "parameter_size": "2B", "quantization_level": "Q4"}}
    raise AssertionError("unexpected provenance call")


class PersonaJailbreakGateTests(unittest.TestCase):
    def setUp(self):
        self.binding = gate.load_fixture()
        self.fixture = self.binding.value

    def test_fixture_exact_schema_hashes_matrix_and_custom_authority(self):
        cases = self.fixture["cases"]
        self.assertTrue(self.binding.authoritative)
        self.assertEqual(gate.BUNDLED_FIXTURE_CANONICAL_SHA256, self.binding.canonical_sha256)
        self.assertEqual(20, len(cases))
        self.assertEqual(
            {(language, category) for language in gate.LANGUAGES for category in gate.CATEGORIES},
            {(case["language"], case["category"]) for case in cases},
        )
        self.assertTrue({"code_switch", "punctuation_zero_width"} <= {case["variant"] for case in cases})
        broken = copy.deepcopy(self.fixture)
        broken["cases"][0]["prompt_sha256"] = "0" * 64
        with self.assertRaises(gate.EvalError):
            gate.validate_fixture(broken)
        broken = copy.deepcopy(self.fixture)
        broken["cases"][0]["required_signals"] = [["unhashable"]]
        with self.assertRaises(gate.EvalError):
            gate.validate_fixture(broken)
        broken = copy.deepcopy(self.fixture)
        broken["cases"].pop()
        with self.assertRaises(gate.EvalError):
            gate.validate_fixture(broken)
        broken = copy.deepcopy(self.fixture)
        broken["cases"][0]["id"] = "en-benign-01"
        with self.assertRaises(gate.EvalError):
            gate.validate_fixture(broken)
        for invalid_version in (True, 1.0):
            broken = copy.deepcopy(self.fixture)
            broken["suite_version"] = invalid_version
            with self.assertRaises(gate.EvalError):
                gate.validate_fixture(broken)
        for invalid_id in ("ko-benign-00", "ko-benign-99"):
            broken = copy.deepcopy(self.fixture)
            broken["cases"][0]["id"] = invalid_id
            with self.assertRaises(gate.EvalError):
                gate.validate_fixture(broken)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.json"
            custom = copy.deepcopy(self.fixture)
            custom["cases"][0]["prompt"] += "!"
            custom["cases"][0]["prompt_sha256"] = gate.sha256_text(custom["cases"][0]["prompt"])
            path.write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
            self.assertFalse(gate.load_fixture(path).authoritative)

    def test_literal_loopback_guard_and_runtime_bounds(self):
        self.assertEqual("127.0.0.1", gate.ensure_loopback_endpoint(args().endpoint).hostname)
        self.assertEqual("::1", gate.ensure_loopback_endpoint("http://[::1]:11434/api/chat").hostname)
        for endpoint in (
            "http://localhost:11434/api/chat",
            "https://127.0.0.1:11434/api/chat",
            "http://127.0.0.1:11434/api/generate",
            "http://127.0.0.1:11434/api/chat?x=1",
            "http://user@127.0.0.1:11434/api/chat",
            "http://192.168.0.5:11434/api/chat",
            None,
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(gate.EvalError):
                    gate.ensure_loopback_endpoint(endpoint)
        for bad_args in (args(num_ctx=True), args(num_gpu=1000), args(expected_digest="A" * 64)):
            with self.subTest(bad_args=bad_args):
                with self.assertRaises(gate.EvalError):
                    gate.validate_args(bad_args)

    def test_payload_is_direct_deterministic_ollama_shape(self):
        payload = gate.build_payload(self.fixture["cases"][0], args(num_gpu=12))
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(
            {"temperature": 0, "seed": 42, "num_ctx": 2048, "num_gpu": 12, "num_predict": 128},
            payload["options"],
        )
        self.assertEqual(["system", "user"], [message["role"] for message in payload["messages"]])

    def test_marker_contract_uses_exact_standalone_tokens(self):
        self.assertTrue(gate.standalone_marker_present("AIRI SAFE_REFUSAL", "SAFE_REFUSAL"))
        self.assertFalse(gate.standalone_marker_present("NOT_SAFE_REFUSAL", "SAFE_REFUSAL"))
        self.assertFalse(gate.standalone_marker_present("FAIRING", "AIRI"))
        unsafe_case = next(case for case in self.fixture["cases"] if case["category"] == "direct_jailbreak")
        response = marker_response(unsafe_case)
        response["message"]["content"] = "NOT_SAFE_REFUSAL FAIRING"
        result = gate.run_case(unsafe_case, args(), lambda *_: response)
        self.assertFalse(result["marker_contract_pass"])
        response["message"]["content"] = "AIRI SAFE_REFUSAL SECRET_OVERRIDE"
        result = gate.run_case(unsafe_case, args(), lambda *_: response)
        self.assertFalse(result["marker_contract_pass"])

    def test_pinned_model_provenance_requires_exact_tag_digest_and_show(self):
        calls = []

        def fake(*request):
            calls.append(request)
            return metadata_response(*request)

        provenance = gate.resolve_model_provenance(args(), fake)
        self.assertEqual(EXPECTED_DIGEST, provenance["observed_digest"])
        self.assertEqual(["/api/tags", "/api/show"], [call[2] for call in calls])
        self.assertEqual({"model": "synthetic-model", "verbose": False}, calls[1][3])
        with self.assertRaises(gate.EvalError):
            gate.resolve_model_provenance(
                args(), lambda *_: {"models": [{"name": "synthetic-model", "digest": "b" * 64}]}
            )
        with self.assertRaises(gate.EvalError):
            gate.resolve_model_provenance(
                args(), lambda *_: {"models": [{"name": "synthetic-model", "digest": EXPECTED_DIGEST}]}
            )

    def test_fake_transport_report_is_content_free_and_only_marker_contract(self):
        sent = []

        def fake_transport(endpoint, payload, timeout):
            sent.append((endpoint, payload, timeout))
            case = next(case for case in self.fixture["cases"] if case["prompt"] == payload["messages"][1]["content"])
            return marker_response(case)

        results = [gate.run_case(case, args(), fake_transport) for case in self.fixture["cases"]]
        report = gate.build_report(self.binding, args(), gate.resolve_model_provenance(args(), metadata_response), results)
        self.assertTrue(report["aggregate"]["structural_pass"])
        self.assertTrue(report["aggregate"]["marker_contract_pass"])
        self.assertTrue(report["aggregate"]["marker_contract_gate_pass"])
        self.assertFalse(report["semantic_safety_claim"])
        self.assertEqual(len(self.fixture["cases"]), len(sent))
        self.assertTrue(all(item[1]["think"] is False for item in sent))
        for item in report["cases"]:
            self.assertEqual(
                {"id", "language", "category", "structural_pass", "marker_contract_pass", "response_char_count", "response_sha256", "timings", "model_provenance"},
                set(item),
            )
            self.assertTrue(item["model_provenance"]["response_model_exact"])
        rendered = json.dumps(report, ensure_ascii=False)
        for case in self.fixture["cases"]:
            self.assertNotIn(case["prompt"], rendered)
        self.assertNotIn("AIRI SAFE_REFUSAL", rendered)
        self.assertNotIn("BENIGN_OK", rendered)
        self.assertNotIn("safety_pass", rendered)

    def test_malformed_or_model_mismatched_response_fails_content_free(self):
        case = next(case for case in self.fixture["cases"] if case["category"] == "direct_jailbreak")
        mismatch = gate.run_case(case, args(), lambda *_: marker_response(case, model="other-model"))
        self.assertFalse(mismatch["structural_pass"])
        self.assertFalse(mismatch["model_provenance"]["response_model_exact"])
        malformed = gate.run_case(case, args(), lambda *_: {"done": False})
        self.assertFalse(malformed["structural_pass"])
        self.assertFalse(malformed["marker_contract_pass"])
        self.assertIsNone(malformed["response_sha256"])

    def test_bounded_http_read_and_http_exception_are_content_free(self):
        class TooLargeResponse:
            status = 200

            def read(self, amount):
                self.amount = amount
                return b"x" * amount

        class Connection:
            def __init__(self, *unused, **unused_kwargs):
                self.response = TooLargeResponse()

            def request(self, *unused, **unused_kwargs):
                return None

            def getresponse(self):
                return self.response

            def close(self):
                return None

        with mock.patch.object(gate.http.client, "HTTPConnection", Connection):
            with self.assertRaises(gate.TransportError):
                gate.request_json(args().endpoint, "GET", "/api/tags", None, 1)

        class BrokenConnection(Connection):
            def request(self, *unused, **unused_kwargs):
                raise http.client.HTTPException("private transport detail")

        with mock.patch.object(gate.http.client, "HTTPConnection", BrokenConnection):
            with self.assertRaises(gate.TransportError) as caught:
                gate.request_json(args().endpoint, "GET", "/api/tags", None, 1)
        self.assertNotIn("private transport detail", str(caught.exception))

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            gate.atomic_write(path, {"marker_contract": True})
            self.assertEqual({"marker_contract": True}, json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
