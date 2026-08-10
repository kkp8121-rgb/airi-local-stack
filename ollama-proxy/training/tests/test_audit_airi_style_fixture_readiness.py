"""Synthetic-only tests for the read-only fixture readiness CLI."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import audit_airi_style_fixture_readiness as audit
from verify_airi_style_dataset import FIXTURE_SUITE_ID, FIXTURE_SUITE_VERSION, canonical_sha256, load_jsonl, load_jsonl_bytes, prompt_sha256, validate_fixture, validate_fixture_rows


def fixture(tier, *, case_id=None, group=None, prompt=None):
    prompt = prompt or f"fixture prompt {tier}"
    answer = f"fixture answer {tier}"
    return {
        "schema_version": 1,
        "suite_id": FIXTURE_SUITE_ID,
        "suite_version": FIXTURE_SUITE_VERSION,
        "tier": tier,
        "case_id": case_id or f"{tier.lower()}-case-001",
        "group": group or f"{tier.lower()}-group-001",
        "prompt": prompt,
        "answer": answer,
        "prompt_sha256": prompt_sha256(prompt),
        "example_sha256": canonical_sha256({"prompt": prompt, "answer": answer}),
    }


def write_jsonl(path, rows):
    path.write_bytes(b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows))


class FixtureReadinessTests(unittest.TestCase):
    def build(self, root):
        c0 = root / "c0.jsonl"
        s1 = root / "s1.jsonl"
        write_jsonl(c0, [fixture("C0")])
        write_jsonl(s1, [fixture("S1")])
        return c0, s1

    def invoke(self, *arguments):
        stream = io.StringIO()
        code = audit.run_cli(list(arguments), output=stream)
        return code, json.loads(stream.getvalue())

    def test_default_off_is_inert_before_parser_or_path_access(self):
        with mock.patch.object(audit, "_Parser", side_effect=AssertionError("parsed")), \
             mock.patch.object(audit, "_audit", side_effect=AssertionError("accessed")):
            code, result = self.invoke("--c0-fixture", "missing.jsonl", "--unknown")
        self.assertEqual(code, 0)
        self.assertEqual(result, {"c0_cases": 0, "c0_sha256": None, "s1_cases": 0,
                                  "s1_sha256": None, "stage": "fixture-readiness", "status": "disabled"})

    def test_shared_byte_helpers_match_existing_path_helpers(self):
        with tempfile.TemporaryDirectory() as raw:
            c0, _ = self.build(Path(raw))
            rows = load_jsonl(c0, "C0 fixture")
            self.assertEqual(rows, load_jsonl_bytes(c0.read_bytes(), "C0 fixture"))
            self.assertEqual(validate_fixture(c0, "C0"), validate_fixture_rows(rows, "C0"))

    def test_duplicate_enable_or_unexpected_loader_failure_is_content_free(self):
        code, result = self.invoke(audit.ENABLE_FLAG, audit.ENABLE_FLAG)
        self.assertEqual((code, result["status"]), (2, "not-ready"))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); c0, s1 = self.build(root)
            with mock.patch.object(audit, "load_jsonl_bytes", side_effect=UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")):
                code, result = self.invoke(audit.ENABLE_FLAG, "--c0-fixture", str(c0), "--s1-fixture", str(s1))
            self.assertEqual((code, result["status"], result["c0_cases"], result["s1_cases"]), (2, "not-ready", 0, 0))
            self.assertNotIn(str(root), json.dumps(result))

    def test_missing_or_rejected_fixtures_are_content_free_and_write_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            c0, s1 = self.build(root)
            original = {path: path.read_bytes() for path in (c0, s1)}
            code, result = self.invoke(audit.ENABLE_FLAG, "--c0-fixture", str(root / "missing.jsonl"), "--s1-fixture", str(s1))
            self.assertEqual(code, 2); self.assertEqual(result["status"], "not-ready")
            self.assertEqual({path: path.read_bytes() for path in original}, original)
            self.assertEqual(list(root.iterdir()), [c0, s1])
            text = json.dumps(result)
            self.assertNotIn(str(root), text); self.assertNotIn("fixture prompt", text)

    def test_same_lexically_normalized_fixture_path_is_not_ready(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); c0, _ = self.build(root)
            alias = root / "." / c0.name
            code, result = self.invoke(audit.ENABLE_FLAG, "--c0-fixture", str(c0), "--s1-fixture", str(alias))
            self.assertEqual((code, result["status"]), (2, "not-ready"))

    def test_valid_fixtures_are_only_a_candidate_with_exact_byte_hashes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); c0, s1 = self.build(root)
            before = {path: path.read_bytes() for path in (c0, s1)}
            code, result = self.invoke(audit.ENABLE_FLAG, "--c0-fixture", str(c0), "--s1-fixture", str(s1))
            self.assertEqual(code, 0); self.assertEqual(result["status"], "candidate")
            self.assertEqual((result["c0_cases"], result["s1_cases"]), (1, 1))
            self.assertEqual(result["c0_sha256"], hashlib.sha256(before[c0]).hexdigest())
            self.assertEqual(result["s1_sha256"], hashlib.sha256(before[s1]).hexdigest())
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            rendered = json.dumps(result)
            for forbidden in (str(root), "fixture prompt", "c0-case-001", "c0-group-001", "approved", "training-ready"):
                self.assertNotIn(forbidden, rendered)

    def test_mutation_after_capture_cannot_mix_validation_and_hash_snapshots(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); c0, s1 = self.build(root)
            original = audit.validate_fixture_rows
            original_s1 = s1.read_bytes()
            replacement = fixture("S1", prompt="replacement fixture prompt")

            def mutate_then_validate(path, tier):
                result = original(path, tier)
                if tier == "S1":
                    write_jsonl(s1, [replacement])
                return result

            with mock.patch.object(audit, "validate_fixture_rows", side_effect=mutate_then_validate):
                code, result = self.invoke(audit.ENABLE_FLAG, "--c0-fixture", str(c0), "--s1-fixture", str(s1))
            self.assertEqual((code, result["status"]), (0, "candidate"))
            self.assertEqual(result["s1_sha256"], hashlib.sha256(original_s1).hexdigest())

    def test_empty_wrong_suite_version_tier_and_hash_are_not_ready(self):
        cases = ("empty", "suite", "version", "tier", "hash")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw:
                root = Path(raw); c0, s1 = self.build(root)
                if case == "empty":
                    c0.write_bytes(b"")
                else:
                    item = fixture("C0")
                    if case == "suite": item["suite_id"] = "other-suite"
                    if case == "version": item["suite_version"] = "2.0"
                    if case == "tier": item["tier"] = "S1"
                    if case == "hash": item["prompt_sha256"] = "0" * 64
                    write_jsonl(c0, [item])
                code, result = self.invoke(audit.ENABLE_FLAG, "--c0-fixture", str(c0), "--s1-fixture", str(s1))
                self.assertEqual((code, result["status"], result["c0_cases"], result["s1_cases"]), (2, "not-ready", 0, 0))

    def test_symlink_and_unc_style_paths_fail_closed_when_available(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); c0, s1 = self.build(root); linked = root / "linked-c0.jsonl"
            try:
                linked.symlink_to(c0)
            except OSError:
                pass
            else:
                code, result = self.invoke(audit.ENABLE_FLAG, "--c0-fixture", str(linked), "--s1-fixture", str(s1))
                self.assertEqual((code, result["status"]), (2, "not-ready"))
        with mock.patch.object(audit, "_absolute_without_resolving", return_value=Path("//server/share/c0.jsonl")):
            with self.assertRaises(audit.ReadinessError):
                audit._assert_no_reparse_chain(Path("unused"), "C0 fixture")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "fixture.jsonl"; path.write_bytes(b"data")
            with mock.patch.object(audit, "_is_reparse", return_value=True):
                with self.assertRaises(audit.ReadinessError):
                    audit._read_regular_snapshot(path, "fixture")

    def test_snapshot_identity_and_same_size_restored_mtime_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "fixture.jsonl"; path.write_bytes(b"stable")
            base = path.stat()

            def stat_value(*, inode=base.st_ino, ctime=getattr(base, "st_ctime_ns", 0)):
                return SimpleNamespace(st_mode=base.st_mode, st_dev=base.st_dev, st_ino=inode,
                                       st_size=base.st_size, st_mtime_ns=getattr(base, "st_mtime_ns", 0),
                                       st_ctime_ns=ctime)

            with mock.patch.object(audit.os, "fstat", side_effect=[stat_value(inode=base.st_ino + 1)]):
                with self.assertRaises(audit.ReadinessError):
                    audit._read_regular_snapshot(path, "fixture")
            with mock.patch.object(audit.os, "fstat", side_effect=[stat_value(), stat_value(ctime=getattr(base, "st_ctime_ns", 0) + 1)]):
                with self.assertRaises(audit.ReadinessError):
                    audit._read_regular_snapshot(path, "fixture")

    def test_duplicate_and_cross_suite_identifier_group_and_normalized_prompt_overlap_fail(self):
        cases = ("duplicate", "id", "group", "prompt")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw:
                root = Path(raw); c0, s1 = self.build(root)
                if case == "duplicate":
                    write_jsonl(c0, [fixture("C0"), fixture("C0")])
                else:
                    c0_item = fixture("C0")
                    s1_item = fixture("S1")
                    if case == "id": s1_item["case_id"] = c0_item["case_id"]
                    if case == "group": s1_item["group"] = c0_item["group"]
                    if case == "prompt":
                        s1_item = fixture("S1", prompt="  FIXTURE prompt c0  ")
                    write_jsonl(c0, [c0_item]); write_jsonl(s1, [s1_item])
                code, result = self.invoke(audit.ENABLE_FLAG, "--c0-fixture", str(c0), "--s1-fixture", str(s1))
                self.assertEqual((code, result["status"]), (2, "not-ready"))


if __name__ == "__main__":
    unittest.main()
