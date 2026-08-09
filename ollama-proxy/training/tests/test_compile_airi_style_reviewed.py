import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import compile_airi_style_reviewed as compiler_cli
from compile_airi_style_reviewed import run_cli
from validate_airi_style_pending import record_sha256
from verify_airi_style_dataset import CATEGORY_TAXONOMY, FIXTURE_SUITE_ID, FIXTURE_SUITE_VERSION, canonical_sha256, prompt_sha256, verify_reviewed_dataset


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path, rows):
    path.write_bytes(b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n" for row in rows))


def fixture(tier):
    prompt = f"{tier} 반응을 짧게 말해줘"
    answer = f"좋아, {tier} 핵심만 말할게."
    return {"schema_version": 1, "suite_id": FIXTURE_SUITE_ID, "suite_version": FIXTURE_SUITE_VERSION, "tier": tier, "case_id": tier.lower()+"-case", "group": tier.lower()+"-group", "prompt": prompt, "answer": answer, "prompt_sha256": prompt_sha256(prompt), "example_sha256": canonical_sha256({"prompt": prompt, "answer": answer})}


class CompileReviewedTests(unittest.TestCase):
    def build(self, root):
        pending = root / "pending.jsonl"; decisions = root / "decisions.jsonl"; c0 = root / "c0.jsonl"; s1 = root / "s1.jsonl"; envelope = root / "approval.json"
        rows = []
        for i in range(200):
            split = "train" if i < 160 else "dev" if i < 180 else "test"
            category = CATEGORY_TAXONOMY[i % len(CATEGORY_TAXONOMY)]
            rows.append({"id": f"seed-{i:03d}", "split": split, "category": category, "prompt": f"주제 {i}를 짧게 말해줘", "answer": f"좋아, {i}번 핵심만 말할게.", "partition": {"tier": "S1", "group": f"pending-{i:03d}"}, "review": {"status": "pending", "reviewer": "", "approved_at": ""}, "provenance": {"synthetic": True, "source": "pending-synthetic-v3"}, "training_eligible": False})
        write_jsonl(pending, rows)
        review_time = "2026-08-09T00:00:00Z"
        decision_rows = [{"id": row["id"], "record_sha256": record_sha256(row), "decision": "approve", "vtuber_voice": True, "counselor_tone": False, "safety_truth": True, "notes": "", "reviewer": "reviewer-alex", "reviewed_at": review_time} for row in rows]
        write_jsonl(decisions, decision_rows); write_jsonl(c0, [fixture("C0")]); write_jsonl(s1, [fixture("S1")])
        bindings = sorted([{key: row[key] for key in ("id", "record_sha256", "reviewer", "reviewed_at")} for row in decision_rows], key=lambda row: row["id"])
        provenance = {"review_program": "independent-review", "dataset_author": "author-kim", "fixture_owner": "fixture-lee", "independent_review": True, "reviewers": [{"id": "reviewer-alex", "role": "senior-reviewer", "affiliation": "quality-team"}]}
        approval = {"schema_version": 1, "promotion_contract_version": "airi-reviewed-promotion/v1", "policy_version": "airi-style-qlora/v3", "pending_dataset_sha256": digest(pending), "decision_sidecar_sha256": digest(decisions), "approved_decisions_sha256": hashlib.sha256(json.dumps(bindings, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "c0_fixture_sha256": digest(c0), "s1_fixture_sha256": digest(s1), "pending_record_count": 200, "human_approved": True, "approved_by": "reviewer-alex", "approved_at": review_time, "reviewer_provenance": provenance}
        envelope.write_text(json.dumps(approval, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return pending, decisions, envelope, c0, s1, rows

    def refresh_envelope(self, paths):
        pending, decisions, envelope, c0, s1 = paths[:5]
        decision_rows = [json.loads(line) for line in decisions.read_text(encoding="utf-8").splitlines()]
        bindings = sorted(
            [{key: row[key] for key in ("id", "record_sha256", "reviewer", "reviewed_at")} for row in decision_rows],
            key=lambda row: row["id"],
        )
        value = json.loads(envelope.read_text(encoding="utf-8"))
        value.update({
            "pending_dataset_sha256": digest(pending),
            "decision_sidecar_sha256": digest(decisions),
            "approved_decisions_sha256": hashlib.sha256(
                json.dumps(bindings, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "c0_fixture_sha256": digest(c0),
            "s1_fixture_sha256": digest(s1),
        })
        envelope.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    @staticmethod
    def decision_rows(path):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def invoke(self, paths, output):
        stream = io.StringIO()
        code = run_cli(["--promote-reviewed-style", "--pending", str(paths[0]), "--decisions", str(paths[1]), "--governance-envelope", str(paths[2]), "--c0-fixture", str(paths[3]), "--s1-fixture", str(paths[4]), "--output-dir", str(output)], output=stream)
        return code, stream.getvalue()

    def test_compile_contract_and_determinism(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); paths = self.build(root)
            a = root / "bundle-a"; b = root / "bundle-b"
            self.assertEqual(self.invoke(paths, a), (0, '{"record_count":200,"status":"compiled"}\n'))
            self.assertEqual(self.invoke(paths, b), (0, '{"record_count":200,"status":"compiled"}\n'))
            expected_files = {
                "reviewed-dataset.jsonl", "review-manifest.json", "c0-fixture.jsonl",
                "s1-fixture.jsonl", "promotion-approval.json",
            }
            self.assertEqual({item.name for item in a.iterdir()}, expected_files)
            self.assertEqual({item.name for item in b.iterdir()}, expected_files)
            for name in expected_files:
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())
            verify_reviewed_dataset(a / "reviewed-dataset.jsonl", a / "review-manifest.json", a / "c0-fixture.jsonl", a / "s1-fixture.jsonl")
            row = json.loads((a / "reviewed-dataset.jsonl").read_text(encoding="utf-8").splitlines()[0])
            source_hash = record_sha256(paths[5][0])
            self.assertEqual(row["id"], "style-" + source_hash[:32]); self.assertEqual(row["partition"]["group"], "reviewed-" + source_hash[-32:])
            self.assertEqual(row["provenance"], {"synthetic": True, "source": "human-reviewed-synthetic-v3"})
            self.assertEqual(row["review"], {"status": "approved", "reviewer": "reviewer-alex", "approved_at": "2026-08-09T00:00:00Z"})
            self.assertTrue(row["training_eligible"])
            self.assertEqual((a / "promotion-approval.json").read_bytes(), paths[2].read_bytes())
            self.assertFalse(any("report" in item.name for item in a.iterdir()))

    def test_default_off_and_rejections_leave_no_bundle(self):
        stream = io.StringIO(); self.assertEqual(run_cli(["--unknown"], output=stream), 0); self.assertEqual(stream.getvalue(), '{"record_count":0,"status":"disabled"}\n')
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); paths = self.build(root); output = root / "bundle"
            data = json.loads(paths[2].read_text(encoding="utf-8")); data["pending_dataset_sha256"] = "0" * 64; paths[2].write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(self.invoke(paths, output), (2, '{"record_count":0,"status":"rejected"}\n'))
            self.assertFalse(output.exists()); self.assertFalse(list(root.glob(".bundle.stage-*")))
            self.build(root)  # restore valid input files
            output.mkdir()
            self.assertEqual(self.invoke(paths, output), (2, '{"record_count":0,"status":"rejected"}\n'))

    def test_default_off_does_not_enter_parser_or_compiler(self):
        stream = io.StringIO()
        with mock.patch.object(compiler_cli, "_compile", side_effect=AssertionError("compiled")), \
             mock.patch.object(compiler_cli, "_Parser", side_effect=AssertionError("parsed")):
            code = run_cli(["--pending", "not-a-path", "--unknown"], output=stream)
        self.assertEqual(code, 0)
        self.assertEqual(stream.getvalue(), '{"record_count":0,"status":"disabled"}\n')

    def test_decision_governance_and_fixture_failures_leave_no_partial_bundle(self):
        cases = (
            "missing-decision", "nonapprove", "extra-decision", "identity-mismatch",
            "identity-case-mismatch", "future-decision", "future-approval",
            "fixture-drift", "fixture-overlap",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                paths = self.build(root)
                decision_rows = self.decision_rows(paths[1])
                envelope = json.loads(paths[2].read_text(encoding="utf-8"))
                if case == "missing-decision":
                    decision_rows.pop()
                    write_jsonl(paths[1], decision_rows)
                    self.refresh_envelope(paths)
                elif case == "nonapprove":
                    decision_rows[0].update({
                        "decision": "reject", "vtuber_voice": False,
                        "counselor_tone": False, "safety_truth": False,
                        "notes": "synthetic rejection",
                    })
                    write_jsonl(paths[1], decision_rows)
                    self.refresh_envelope(paths)
                elif case == "extra-decision":
                    extra = dict(decision_rows[0])
                    extra["id"] = "seed-extra"
                    decision_rows.append(extra)
                    write_jsonl(paths[1], decision_rows)
                    self.refresh_envelope(paths)
                elif case == "identity-mismatch":
                    envelope["approved_by"] = "reviewer-other"
                    envelope["reviewer_provenance"]["reviewers"] = [{
                        "id": "reviewer-other", "role": "senior-reviewer",
                        "affiliation": "quality-team",
                    }]
                    paths[2].write_text(json.dumps(envelope), encoding="utf-8")
                elif case == "identity-case-mismatch":
                    decision_rows[0]["reviewer"] = "Reviewer-Alex"
                    write_jsonl(paths[1], decision_rows)
                    self.refresh_envelope(paths)
                elif case == "future-decision":
                    decision_rows[0]["reviewed_at"] = "2099-01-01T00:00:00Z"
                    write_jsonl(paths[1], decision_rows)
                    self.refresh_envelope(paths)
                elif case == "future-approval":
                    envelope["approved_at"] = "2099-01-01T00:00:00Z"
                    paths[2].write_text(json.dumps(envelope), encoding="utf-8")
                elif case == "fixture-drift":
                    paths[3].write_bytes(paths[3].read_bytes() + b" ")
                elif case == "fixture-overlap":
                    c0_value = json.loads(paths[3].read_text(encoding="utf-8"))
                    c0_value["tier"] = "S1"
                    write_jsonl(paths[4], [c0_value])
                    self.refresh_envelope(paths)
                output = root / "bundle"
                self.assertEqual(self.invoke(paths, output), (2, '{"record_count":0,"status":"rejected"}\n'))
                self.assertFalse(output.exists())
                self.assertFalse(list(root.glob(".bundle.stage-*")))

    def test_missing_input_and_preexisting_output_preserve_existing_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paths = self.build(root)
            missing = root / "missing-c0.jsonl"
            missing_paths = (paths[0], paths[1], paths[2], missing, paths[4], paths[5])
            output = root / "bundle"
            self.assertEqual(self.invoke(missing_paths, output)[0], 2)
            self.assertFalse(output.exists())
            output.mkdir()
            marker = output / "keep"
            marker.write_bytes(b"keep")
            self.assertEqual(self.invoke(paths, output)[0], 2)
            self.assertEqual(marker.read_bytes(), b"keep")
            self.assertEqual({item.name for item in output.iterdir()}, {"keep"})

    def test_output_lock_is_exclusive_and_partial_acquire_is_cleaned(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paths = self.build(root)
            output = root / "bundle"
            lock_path = root / ".bundle.promotion.lock"
            lock_path.write_bytes(b"another-writer")
            self.assertEqual(self.invoke(paths, output), (2, '{"record_count":0,"status":"rejected"}\n'))
            self.assertEqual(lock_path.read_bytes(), b"another-writer")
            self.assertFalse(output.exists())
            self.assertFalse(list(root.glob(".bundle.stage-*")))
            lock_path.unlink()

            lock = compiler_cli._OutputLock(output)
            with mock.patch.object(compiler_cli.os, "write", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    lock.__enter__()
            self.assertFalse(lock_path.exists())
            self.assertFalse(output.exists())

    def test_relative_local_paths_follow_the_same_contract(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            stream = io.StringIO()
            arguments = [
                "--promote-reviewed-style",
                "--pending", "pending.jsonl",
                "--decisions", "decisions.jsonl",
                "--governance-envelope", "approval.json",
                "--c0-fixture", "c0.jsonl",
                "--s1-fixture", "s1.jsonl",
                "--output-dir", "bundle",
            ]
            with mock.patch.object(compiler_cli.Path, "cwd", return_value=root):
                self.assertEqual(run_cli(arguments, output=stream), 0)
            self.assertEqual(stream.getvalue(), '{"record_count":200,"status":"compiled"}\n')
            self.assertTrue((root / "bundle" / "reviewed-dataset.jsonl").is_file())

    def test_noncooperative_destination_race_never_clobbers(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paths = self.build(root)
            output = root / "bundle"
            publish = compiler_cli._publish_no_replace

            def race(source, destination):
                destination.mkdir()
                (destination / "keep").write_bytes(b"keep")
                publish(source, destination)

            with mock.patch.object(compiler_cli, "_publish_no_replace", side_effect=race):
                self.assertEqual(self.invoke(paths, output), (2, '{"record_count":0,"status":"rejected"}\n'))
            self.assertEqual((output / "keep").read_bytes(), b"keep")
            self.assertEqual({item.name for item in output.iterdir()}, {"keep"})
            self.assertFalse(list(root.glob(".bundle.stage-*")))
            self.assertFalse((root / ".bundle.promotion.lock").exists())

    def test_lock_release_interrupt_attempts_owned_cleanup(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / "bundle"
            lock_path = root / ".bundle.promotion.lock"
            lock = compiler_cli._OutputLock(output)
            lock.__enter__()
            original_read = compiler_cli.Path.read_bytes

            def interrupted(path):
                if path == lock_path:
                    raise KeyboardInterrupt()
                return original_read(path)

            with mock.patch.object(compiler_cli.Path, "read_bytes", interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    lock.__exit__(None, None, None)
            self.assertFalse(lock_path.exists())

    def test_snapshot_rejects_a_replaced_opened_file(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "input.jsonl"
            path.write_bytes(b"stable")
            before = path.stat()
            replaced = mock.Mock(
                st_mode=before.st_mode,
                st_dev=before.st_dev,
                st_ino=before.st_ino + 1,
            )
            with mock.patch.object(compiler_cli.os, "fstat", return_value=replaced):
                with self.assertRaises(compiler_cli.PromotionError):
                    compiler_cli._read_regular_snapshot(path, "input")

    def test_existing_symlink_component_is_rejected_when_supported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            actual = root / "actual"
            actual.mkdir()
            linked = root / "linked"
            try:
                linked.symlink_to(actual, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks are unavailable")
            target = linked / "input.jsonl"
            (actual / "input.jsonl").write_bytes(b"data")
            with self.assertRaises(compiler_cli.PromotionError):
                compiler_cli._assert_no_reparse_chain(target, "input")


if __name__ == "__main__":
    unittest.main()
