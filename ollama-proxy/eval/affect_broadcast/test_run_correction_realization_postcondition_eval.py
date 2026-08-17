"""Offline contracts for the A4.5 retrospective scorer."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "airi_test_a45_runner", HERE / "run_correction_realization_postcondition_eval.py"
)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class CorrectionRealizationRunnerTests(unittest.TestCase):
    def source_artifacts(self):
        a44 = runner._a44()
        oracle = runner.realization.load_oracle()
        responses = []
        for ordinal, row in enumerate(oracle["entries"]):
            fallback = runner.realization.fallback_for(
                row["turn_id"], row["target_id"], row["direction"], oracle
            )["text"]
            responses.append({
                "ordinal": ordinal,
                "responses": {"control": "응, 다시 확인할게.", "target": fallback},
            })
        execution = {
            "schema_version": "airi.correction-target-execution.v1",
            "rows": responses,
            "orders": ["CT"] * 4 + ["TC"] * 4,
            "row_order": list(range(8)),
            "health_profile_sha256": hashlib.sha256(runner.canonical_bytes(
                a44.base._expected_health_profile(a44.base.EVAL_PROFILE)
            )).hexdigest(),
            "transport_contract": {
                "scope": "normal_cli_path_not_external_transport_proof",
                "literal_loopback": True,
                "no_proxy": True,
                "no_redirect": True,
                "bounded": True,
            },
        }
        packet, key = a44.build_packet(execution, randbelow=lambda n: 0)
        report = {
            "schema_version": "airi.correction-target-public-report.v2",
            "runner_version": "1.1.0",
            "protocol_id": runner.realization.A44_PROTOCOL_VERSION,
            "supersedes_packet_schema": "airi.correction-target-blinded-review.v1",
            "superseded_schema_status": "obsolete_incomplete_review_context",
            "cohort_count": 8,
            "model_call_count": 16,
            "fixture_sha256": runner.realization.BASE_FIXTURE_SHA256,
            "reply_act_fixture_sha256": runner.realization.REPLY_ACT_FIXTURE_SHA256,
            "oracle_sha256": runner.realization.A43_ORACLE_SHA256,
            "eligibility": True,
            "transport_contract": execution["transport_contract"],
            "profile_sha256": hashlib.sha256(
                runner.canonical_bytes(a44.base.EVAL_PROFILE)
            ).hexdigest(),
            "health_profile_sha256": execution["health_profile_sha256"],
            "operational_adoption": False,
        }
        packet_hash = hashlib.sha256(runner.canonical_bytes(packet)).hexdigest()
        receipt = {
            "schema_version": "airi.correction-target-local-run-receipt.v2",
            "protocol_id": runner.realization.A44_PROTOCOL_VERSION,
            "integrity_only_not_authenticity": True,
            "hostile_local_authenticity_not_addressed": True,
            "v1_review_artifacts_obsolete": True,
            "artifacts": {
                "private-review-packet.json": packet_hash,
                "public-report.json": hashlib.sha256(
                    runner.canonical_bytes(report)
                ).hexdigest(),
            },
        }
        return report, packet, receipt, key, packet_hash

    def write_source(self, root: Path):
        results = root / "local-results"
        keys = root / "local-operator-keys"
        results.mkdir()
        keys.mkdir()
        source = results / runner.realization.SOURCE_RUN
        source.mkdir()
        report, packet, receipt, key, packet_hash = self.source_artifacts()
        for name, value in (
            ("public-report.json", report),
            ("private-review-packet.json", packet),
            ("local-run-receipt.json", receipt),
        ):
            (source / name).write_bytes(runner.canonical_bytes(value))
        (keys / f"{runner.realization.SOURCE_RUN}.json").write_bytes(
            runner.canonical_bytes(key)
        )
        return results, keys, packet_hash

    def test_default_reads_no_ignored_source_and_writes_nothing(self) -> None:
        original = runner._load
        runner._load = lambda path: (_ for _ in ()).throw(AssertionError("source read"))
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, runner.main([]))
            value = json.loads(output.getvalue())
            self.assertEqual(
                "eligible_for_zero_network_retrospective_scoring", value["decision"]
            )
            self.assertEqual(0, value["new_proxy_post_count"])
            self.assertEqual(0, value["new_model_call_count"])
        finally:
            runner._load = original

    def test_positive_end_to_end_is_content_free_and_receipt_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "local-results"
            results.mkdir()
            report, packet, receipt_in, key, _ = self.source_artifacts()
            public, detail_in, receipt = runner._score(
                report, packet, receipt_in, key, runner.realization.load_oracle()
            )
            runner._publish(
                "a45-fake-positive", results, public, detail_in, receipt
            )
            self.assertEqual(0, public["counts"]["control_pass"])
            self.assertEqual(8, public["counts"]["target_pass"])
            self.assertEqual(8, public["counts"]["fallback_pass"])
            self.assertEqual(8, public["counts"]["target_only"])
            self.assertEqual(0, public["new_model_call_count"])
            output = results / "a45-fake-positive"
            detail = json.loads((output / "private-detail.json").read_text(encoding="utf-8"))
            receipt = json.loads((output / "local-run-receipt.json").read_text(encoding="utf-8"))
            serialized = json.dumps([public, detail], ensure_ascii=False)
            self.assertNotIn("다시 확인", serialized)
            for target in (row[1] for row in runner.realization.MAPPINGS):
                self.assertNotIn(target, serialized)
            self.assertEqual(
                hashlib.sha256(runner.canonical_bytes(public)).hexdigest(),
                receipt["artifacts"]["public-report.json"],
            )
            self.assertEqual(
                hashlib.sha256(runner.canonical_bytes(detail)).hexdigest(),
                receipt["artifacts"]["private-detail.json"],
            )
            self.assertFalse(receipt["source_operator_key_receipt_bound"])
            self.assertTrue(receipt["integrity_only_not_authenticity"])
            self.assertEqual(
                {
                    "source_report", "source_packet", "source_receipt",
                    "source_operator_key", "realization_oracle", "realization_code",
                    "retrospective_runner_code", "a44_runner_code",
                    "a44_base_runner_code", "a43_oracle_code",
                },
                set(receipt["consumed_artifacts"]),
            )

    def test_unpinned_synthetic_source_and_tampering_are_rejected(self) -> None:
        report, packet, receipt, key, packet_hash = self.source_artifacts()
        oracle = runner.realization.load_oracle()
        self.assertNotEqual(runner.realization.SOURCE_PACKET_SHA256, packet_hash)
        with self.assertRaises(runner.RetrospectiveEvalError):
            runner._validate_source(report, packet, receipt, key, oracle)
        mutations = []
        changed = deepcopy(report); changed["eligibility"] = False; mutations.append((changed, packet, receipt, key))
        changed = deepcopy(report); changed["transport_contract"]["no_proxy"] = False; mutations.append((changed, packet, receipt, key))
        changed_packet = deepcopy(packet); changed_packet["pairs"][0]["review_context"]["screen"] = "drift"; mutations.append((report, changed_packet, receipt, key))
        changed_receipt = deepcopy(receipt); changed_receipt["artifacts"]["public-report.json"] = "0" * 64; mutations.append((report, packet, changed_receipt, key))
        changed_key = deepcopy(key); changed_key["execution_pair_orders"] = ["CT"] * 8; mutations.append((report, packet, receipt, changed_key))
        changed_key = deepcopy(key); changed_key["execution_row_order"] = [0] * 8; mutations.append((report, packet, receipt, changed_key))
        changed_key = deepcopy(key); changed_key["pair_mappings"][0]["labels"] = {"A": "target", "B": "target"}; mutations.append((report, packet, receipt, changed_key))
        changed_key = deepcopy(key); changed_key["pair_mappings"][0]["target_id"] = "wrong"; mutations.append((report, packet, receipt, changed_key))
        for values in mutations:
            with self.subTest(index=mutations.index(values)):
                with self.assertRaises(runner.RetrospectiveEvalError):
                    runner._validate_source(*values, oracle)

    def test_v1_and_wrong_packet_digest_fail_closed(self) -> None:
        report, packet, receipt, key, packet_hash = self.source_artifacts()
        oracle = runner.realization.load_oracle()
        packet["schema_version"] = "airi.correction-target-blinded-review.v1"
        with self.assertRaises(runner.RetrospectiveEvalError):
            runner._validate_source(report, packet, receipt, key, oracle)
        report, packet, receipt, key, _ = self.source_artifacts()
        with self.assertRaises(runner.RetrospectiveEvalError):
            runner._validate_source(report, packet, receipt, key, oracle)

    def test_run_name_reserved_and_casefold_collisions_reject(self) -> None:
        for name in ("CON", "aux", "com9", "lpt9", "a", "a/b", "UPPER", runner.realization.SOURCE_RUN):
            with self.subTest(name=name):
                with self.assertRaises(runner.RetrospectiveEvalError):
                    runner._safe_run(name)
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            (results / "A45-RESULT").mkdir()
            with self.assertRaises(runner.RetrospectiveEvalError):
                runner._reserve_output("a45-result", results)

    def test_write_failure_leaves_no_final_or_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "local-results"
            results.mkdir()
            report, packet, receipt_in, key, _ = self.source_artifacts()
            public, detail, receipt = runner._score(
                report, packet, receipt_in, key, runner.realization.load_oracle()
            )
            original = runner._write_stage_artifact
            calls = 0
            def fail_second(reservation, name, data):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise runner.RetrospectiveEvalError("a4.5 output rejected")
                return original(reservation, name, data)
            runner._write_stage_artifact = fail_second
            try:
                with self.assertRaises(runner.RetrospectiveEvalError):
                    runner._publish(
                        "a45-write-failure", results, public, detail, receipt
                    )
            finally:
                runner._write_stage_artifact = original
            self.assertFalse((results / "a45-write-failure").exists())
            self.assertFalse((results / ".reservation-a45-a45-write-failure").exists())

    def test_reparse_roots_reject_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_results = root / "real-results"; real_results.mkdir()
            keys = root / "keys"; keys.mkdir()
            linked = root / "linked-results"
            try:
                linked.symlink_to(real_results, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlink privilege unavailable")
            with self.assertRaises(runner.RetrospectiveEvalError):
                runner._validate_roots(linked, keys)

    def test_runner_has_no_network_imports_or_actual_output_literals(self) -> None:
        source = Path(runner.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertFalse(imports & {"requests", "socket", "http", "urllib"})
        self.assertNotIn("locked-review-overlay", source)
        self.assertNotIn("response_char_count", source)
        self.assertNotIn("expected_source_packet_sha256", source)
        self.assertNotIn("expected_packet_sha256", source)


if __name__ == "__main__":
    unittest.main()
