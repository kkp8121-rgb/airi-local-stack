from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "a46_runner_test",
    HERE / "run_correction_prepublication_eval.py",
)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def envelope(
    candidate: str,
    safety: bool = True,
    tool: bool = True,
    tokens: int = 0,
) -> dict[str, object]:
    return {
        "schema_version": runner.ENVELOPE_SCHEMA_VERSION,
        "candidate": candidate,
        "safety_passed": safety,
        "tool_truth_unchanged": tool,
        "public_token_count": tokens,
    }


def attest_fallback(_ordinal: int, candidate: str) -> dict[str, object]:
    return envelope(candidate)


class RunnerTests(unittest.TestCase):
    def test_default_is_eligibility_only(self) -> None:
        self.assertEqual(0, runner.eligibility()["network_call_count"])

    def test_retry_and_fallback_attempt_bounds(self) -> None:
        calls: list[tuple[int, int]] = []
        entries = runner.policy.load_oracle()["entries"]

        def fake(ordinal: int, attempt: int) -> dict[str, object]:
            calls.append((ordinal, attempt))
            return envelope("bad" if attempt == 1 else entries[ordinal]["normal"])

        report = runner.compare_strategies(fake, attest_fallback)
        self.assertEqual(16, report["strategies"]["retry"]["upstream_attempt_count"])
        self.assertEqual(8, report["strategies"]["fallback"]["upstream_attempt_count"])
        self.assertEqual(16, len(calls))
        self.assertEqual(8, report["strategies"]["fallback"]["eligible_count"])
        self.assertNotIn("normal", json.dumps(report, ensure_ascii=False))

    def test_initial_pass_uses_one_call_and_never_both(self) -> None:
        calls: list[tuple[int, int]] = []
        entries = runner.policy.load_oracle()["entries"]

        def fake(ordinal: int, attempt: int) -> dict[str, object]:
            calls.append((ordinal, attempt))
            return envelope(entries[ordinal]["normal"])

        report = runner.compare_strategies(fake, attest_fallback)
        self.assertEqual(8, report["strategies"]["retry"]["upstream_attempt_count"])
        self.assertEqual(8, report["strategies"]["fallback"]["upstream_attempt_count"])
        self.assertEqual(8, len(calls))

    def test_boundary_failure_is_terminal_not_self_assertion_proof(self) -> None:
        for kwargs in ({"safety": False}, {"tool": False}, {"tokens": 1}):
            with self.subTest(kwargs=kwargs):
                calls: list[tuple[int, int]] = []

                def fake(ordinal: int, attempt: int) -> dict[str, object]:
                    calls.append((ordinal, attempt))
                    return envelope("bad", **kwargs)

                report = runner.compare_strategies(fake, attest_fallback)
                self.assertEqual(
                    8,
                    report["strategies"]["retry"]["upstream_attempt_count"],
                )
                self.assertEqual(
                    8,
                    report["strategies"]["fallback"]["upstream_attempt_count"],
                )
                self.assertEqual(0, report["strategies"]["fallback"]["eligible_count"])
                self.assertIn(
                    runner.ATTESTATION_FAILURE_MASK,
                    {
                        row["mask"]
                        for row in report["strategies"]["retry"]["failure_mask_counts"]
                    },
                )

    def test_malformed_envelope_and_public_report_rejected(self) -> None:
        with self.assertRaises(runner.CorrectionPrepublicationEvalError):
            runner.validate_candidate_envelope({})
        with self.assertRaises(runner.CorrectionPrepublicationEvalError):
            runner.validate_candidate_envelope(
                envelope("x", tokens=runner.MAX_PUBLIC_TOKEN_COUNT + 1)
            )
        canonical_envelope = json.loads(runner.canonical_bytes(envelope("x")))
        self.assertEqual(
            canonical_envelope,
            runner.validate_candidate_envelope(canonical_envelope),
        )
        with self.assertRaises(runner.CorrectionPrepublicationEvalError):
            runner.validate_public_report({})

        def failed_transport(_ordinal: int, _attempt: int) -> dict[str, object]:
            raise RuntimeError("secret transport detail")

        with self.assertRaisesRegex(
            runner.CorrectionPrepublicationEvalError,
            "^fake transport failed$",
        ):
            runner.compare_strategies(failed_transport, attest_fallback)

    def test_public_report_bounds_rejected(self) -> None:
        report = runner.compare_strategies(
            lambda _ordinal, _attempt: envelope("bad"),
            attest_fallback,
        )
        report["strategies"]["fallback"]["upstream_attempt_count"] = 9
        with self.assertRaises(runner.CorrectionPrepublicationEvalError):
            runner.validate_public_report(report)

        report = runner.compare_strategies(
            lambda _ordinal, _attempt: envelope("bad"),
            attest_fallback,
        )
        report["strategies"]["retry"]["failure_mask_counts"] = [
            {"mask": False, "count": "eight"}
        ]
        with self.assertRaises(runner.CorrectionPrepublicationEvalError):
            runner.validate_public_report(report)

    def test_public_report_round_trips_canonical_json(self) -> None:
        report = runner.compare_strategies(
            lambda _ordinal, _attempt: envelope("bad"),
            attest_fallback,
        )
        decoded = json.loads(runner.canonical_bytes(report))
        self.assertEqual(report, runner.validate_public_report(decoded))

    def test_initials_are_paired_and_fallback_is_failure_only(self) -> None:
        entries = runner.policy.load_oracle()["entries"]
        initial_calls = 0

        def stateful(ordinal: int, attempt: int) -> dict[str, object]:
            nonlocal initial_calls
            if attempt == 1:
                initial_calls += 1
                return envelope(entries[ordinal]["normal"])
            return envelope(entries[ordinal]["normal"])

        report = runner.compare_strategies(stateful, attest_fallback)
        self.assertEqual(8, initial_calls)
        self.assertEqual(8, report["strategies"]["retry"]["eligible_count"])
        self.assertEqual(8, report["strategies"]["fallback"]["eligible_count"])

        def reserved_fallback(ordinal: int, attempt: int) -> dict[str, object]:
            if attempt == 1:
                return envelope(entries[ordinal]["fallback"])
            return envelope(entries[ordinal]["normal"])

        report = runner.compare_strategies(reserved_fallback, attest_fallback)
        self.assertEqual(16, report["strategies"]["retry"]["upstream_attempt_count"])
        self.assertEqual(8, report["strategies"]["fallback"]["upstream_attempt_count"])

        def padded_reserved_fallback(ordinal: int, attempt: int) -> dict[str, object]:
            if attempt == 1:
                return envelope(entries[ordinal]["fallback"] + " ")
            return envelope(entries[ordinal]["normal"])

        report = runner.compare_strategies(padded_reserved_fallback, attest_fallback)
        self.assertEqual(16, report["strategies"]["retry"]["upstream_attempt_count"])
        self.assertEqual(8, report["strategies"]["fallback"]["upstream_attempt_count"])

    def test_fallback_requires_independent_attestation(self) -> None:
        report = runner.compare_strategies(
            lambda _ordinal, _attempt: envelope("bad"),
            lambda _ordinal, candidate: envelope(candidate, safety=False),
        )
        self.assertEqual(0, report["strategies"]["fallback"]["eligible_count"])

    def test_report_contains_no_publication_claim(self) -> None:
        report = runner.compare_strategies(
            lambda _ordinal, _attempt: envelope("bad"),
            attest_fallback,
        )
        self.assertNotIn("publish", json.dumps(report, ensure_ascii=False).casefold())


if __name__ == "__main__":
    unittest.main()
