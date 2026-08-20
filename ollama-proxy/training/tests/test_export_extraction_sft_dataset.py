import contextlib
import hashlib
import importlib.util
import io
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name + "_test", HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


applier = _load("apply_extraction_review_reply")
exporter = _load("export_extraction_sft_dataset")

# 익스포터가 sys.path 에 ollama-proxy 를 올린 뒤라야 벤치마크 런타임을 가져올 수 있다.
import benchmark_memory_track as bench  # noqa: E402

PENDING_PATH = HERE / "seed" / "airi_extraction_seed_pending.jsonl"
PENDING = [json.loads(line) for line in
           PENDING_PATH.read_text(encoding="utf-8").splitlines() if line]


def reviewed_records() -> list[dict]:
    reply = applier.parse_reply(
        f"[AIRI 추출 SFT 검수 회신 2026-08-20]\napproved={len(PENDING)}/{len(PENDING)}")
    reviewed, _counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20")
    return reviewed


def write_jsonl(path: Path, entries: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) for entry in entries) + "\n",
                    encoding="utf-8", newline="\n")
    return path


class RuntimeParityTests(unittest.TestCase):
    """학습 프롬프트는 런타임이 실제로 보내는 프롬프트와 바이트 단위로 같아야 한다."""

    def _runtime_call(self, record: dict) -> tuple[str, str]:
        seen: list[tuple[str, str]] = []

        def capture(*call):
            seen.append((call[2], call[3]))
            return '{"extracted":[]}'

        args = bench.build_parser().parse_args(
            ["--stage-a-contract", exporter.STAGE_A_CONTRACT])
        fixture = {"id": record["id"], "character": record["character"],
                   "turns": record["turns"], "candidates": [],
                   "expected_stage_a": [], "expected_stage_b": []}
        bench.run_extraction(args, {"extraction": [fixture]}, capture)
        self.assertEqual(len(seen), 1)
        return seen[0]

    def test_exported_messages_match_the_runtime_stage_a_call_byte_for_byte(self) -> None:
        for record in (PENDING[0], PENDING[40], PENDING[-1]):
            with self.subTest(record["id"]):
                system, user = self._runtime_call(record)
                messages = exporter.assemble_messages(record)
                self.assertEqual(messages[0]["role"], "system")
                self.assertEqual(messages[0]["content"], system)
                self.assertEqual(messages[1]["role"], "user")
                self.assertEqual(messages[1]["content"], user)
                self.assertEqual(messages[2]["role"], "assistant")
                self.assertEqual(messages[2]["content"], record["target"])

    def test_the_assembly_is_imported_not_duplicated(self) -> None:
        source = (HERE / "export_extraction_sft_dataset.py").read_text(encoding="utf-8")
        self.assertNotIn("<character>", source)
        self.assertNotIn("<turns>", source)
        self.assertIs(exporter.stage_a_user_input, bench.stage_a_user_input)
        self.assertIs(exporter.stage_a_prompt_for_contract, bench.stage_a_prompt_for_contract)

    def test_the_span_contract_prompt_is_the_one_exported(self) -> None:
        system = exporter.assemble_messages(PENDING[0])[0]["content"]
        self.assertEqual(system, bench.stage_a_prompt_for_contract("conversation-v3-span"))
        self.assertIn("evidence", system)


class ExportTests(unittest.TestCase):
    def test_export_covers_every_reviewed_record(self) -> None:
        path = write_jsonl(HERE / "tests" / "_xreviewed_ok.jsonl", reviewed_records())
        try:
            rows, summary = exporter.export(path)
        finally:
            path.unlink()
        self.assertEqual(summary["records"], len(PENDING))
        self.assertEqual(sum(summary["scenes"].values()), len(PENDING))
        self.assertEqual(sum(summary["splits"].values()), len(PENDING))
        self.assertEqual(summary["stage_a_contract"], exporter.STAGE_A_CONTRACT)
        self.assertEqual(summary["system_prompt_sha256"], hashlib.sha256(
            bench.stage_a_prompt_for_contract(exporter.STAGE_A_CONTRACT)
            .encode("utf-8")).hexdigest())
        self.assertEqual({row["id"] for row in rows}, {record["id"] for record in PENDING})
        for row in rows:
            self.assertEqual([message["role"] for message in row["messages"]],
                             ["system", "user", "assistant"])

    def test_export_refuses_pending_or_unattributed_records(self) -> None:
        with self.assertRaises(exporter.ExtractionExportError):
            exporter.export(PENDING_PATH)  # pending 그대로는 학습 불가
        for mutate in (lambda r: r["review"].update(reviewer=""),
                       lambda r: r["review"].update(approved_at=""),
                       lambda r: r["review"].update(status="pending"),
                       lambda r: r.update(training_eligible=False),
                       lambda r: r.update(task="stage_b_decision")):
            entries = reviewed_records()
            mutate(entries[0])
            path = write_jsonl(HERE / "tests" / "_xreviewed_broken.jsonl", entries)
            try:
                with self.assertRaises(exporter.ExtractionExportError):
                    exporter.export(path)
            finally:
                path.unlink()

    def test_export_refuses_a_target_that_lost_its_span_evidence(self) -> None:
        entries = reviewed_records()
        parsed = json.loads(entries[0]["target"])
        parsed["extracted"][0]["evidence"] = "턴 원문에 없는 인용"
        entries[0]["target"] = json.dumps(parsed, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":"))
        path = write_jsonl(HERE / "tests" / "_xreviewed_span.jsonl", entries)
        try:
            with self.assertRaises(exporter.ExtractionExportError):
                exporter.export(path)
        finally:
            path.unlink()

    def test_empty_dataset_fails_closed(self) -> None:
        path = HERE / "tests" / "_xreviewed_empty.jsonl"
        path.write_text("", encoding="utf-8")
        try:
            with self.assertRaises(exporter.ExtractionExportError):
                exporter.export(path)
        finally:
            path.unlink()

    def test_cli_output_is_deterministic_and_self_hashing(self) -> None:
        reviewed = write_jsonl(HERE / "tests" / "_xreviewed_cli.jsonl", reviewed_records())
        out = HERE / "tests" / "_xsft_cli.jsonl"
        try:
            digests = []
            for _ in range(2):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(exporter.main(
                        ["--reviewed", str(reviewed), "--output", str(out)]), 0)
                summary = json.loads(stdout.getvalue())
                self.assertEqual(summary["sha256"],
                                 hashlib.sha256(out.read_bytes()).hexdigest())
                self.assertEqual(summary["records"], len(PENDING))
                digests.append(summary["sha256"])
            self.assertEqual(digests[0], digests[1])
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), len(PENDING))
            self.assertEqual(json.loads(lines[0])["messages"][2]["content"],
                             PENDING[0]["target"])
        finally:
            out.unlink(missing_ok=True)
            reviewed.unlink()


if __name__ == "__main__":
    unittest.main()
