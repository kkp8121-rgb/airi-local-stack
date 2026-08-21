import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
def _load(name: str):
    spec = importlib.util.spec_from_file_location(name + "_test", HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
applier = _load("apply_behavior_review_reply")
exporter = _load("export_behavior_chat_dataset")
PENDING_PATH = HERE / "seed" / "airi_behavior_seed_pending.jsonl"
PENDING = [json.loads(line) for line in PENDING_PATH.read_text(encoding="utf-8").splitlines() if line]
QUEUE_SHA = applier.queue_digest(PENDING_PATH)

def reply_text(rejected: str = "", rewrites: dict[str, str] | None = None, undecided: int = 0, approved: int | None = None, total: int | None = None, queue_sha: str = QUEUE_SHA) -> str:
    rewrites = rewrites or {}; total = total if total is not None else len(PENDING)
    if approved is None: approved = total - len([x for x in rejected.split(",") if x.strip()]) - len(rewrites)
    lines = [f"[AIRI 행동 SFT 검수 회신 2026-08-19 queue={queue_sha}]", f"approved={approved}/{total}"]
    if rejected: lines.append("rejected=" + rejected)
    lines.extend(f"rewrite: {record_id} => {answer}" for record_id, answer in rewrites.items())
    if undecided: lines.append(f"(미결정 {undecided}건: bseed-register-0001)")
    return "\n".join(lines)

class ReplyParsingTests(unittest.TestCase):
    def apply(self, reply): return applier.apply_reply(PENDING, reply, "tester", "2026-08-19", QUEUE_SHA)
    def test_full_approval_reply_round_trips(self) -> None:
        reviewed, counts = self.apply(applier.parse_reply(reply_text()))
        self.assertEqual(counts, {"approved":len(PENDING), "rewritten":0, "rejected":0})
        for entry in reviewed: self.assertIs(entry["training_eligible"], True); self.assertEqual(entry["review"]["reviewer"], "tester")
    def test_rejections_and_rewrites_are_exceptions_only(self) -> None:
        target, victim = PENDING[0], PENDING[1]
        reviewed, counts = self.apply(applier.parse_reply(reply_text(rejected=victim["id"], rewrites={target["id"]:target["answer"]})))
        self.assertEqual(counts["rejected"], 1); self.assertEqual(counts["rewritten"], 1)
        self.assertNotIn(victim["id"], {entry["id"] for entry in reviewed})
    def test_incomplete_or_inconsistent_replies_fail_closed(self) -> None:
        with self.assertRaises(applier.ReviewReplyError): applier.parse_reply(reply_text(undecided=3))
        with self.assertRaises(applier.ReviewReplyError): applier.parse_reply("그냥 텍스트")
        with self.assertRaises(applier.ReviewReplyError): self.apply(applier.parse_reply(reply_text(total=99, approved=99)))
        with self.assertRaises(applier.ReviewReplyError): self.apply(applier.parse_reply(reply_text(rejected="bseed-substance-9999")))
        with self.assertRaises(applier.ReviewReplyError): self.apply(applier.parse_reply(reply_text(approved=1)))
    def test_polite_rewrite_is_refused(self) -> None:
        with self.assertRaises(applier.ReviewReplyError): self.apply(applier.parse_reply(reply_text(rewrites={PENDING[0]["id"]:"네, 기억하고 있어요!"})))
    def test_missing_mismatched_and_changed_same_count_queue_fail_closed(self) -> None:
        with self.assertRaises(applier.ReviewReplyError): applier.parse_reply("[AIRI 행동 SFT 검수 회신 2026-08-19]\napproved=1/1")
        with self.assertRaises(applier.ReviewReplyError): self.apply(applier.parse_reply(reply_text(queue_sha="0" * 12)))
        changed = json.loads(json.dumps(PENDING)); changed[0]["answer"] += "x"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changed.jsonl"; path.write_text("\n".join(json.dumps(row) for row in changed), encoding="utf-8")
            with self.assertRaises(applier.ReviewReplyError): applier.apply_reply(changed, applier.parse_reply(reply_text()), "tester", "date", applier.queue_digest(path))
    def test_duplicate_rejected_rewrite_overlap_and_queue_ids_fail_closed(self) -> None:
        target = PENDING[0]["id"]
        for reply in (reply_text(rejected=target + ", " + target), reply_text(rejected=target, rewrites={target:"x"}), reply_text() + f"\nrewrite: {target} => x\nrewrite: {target} => y"):
            with self.assertRaises(applier.ReviewReplyError): applier.parse_reply(reply)
        duplicate = PENDING + [PENDING[0]]
        with self.assertRaises(applier.ReviewReplyError): applier.apply_reply(duplicate, applier.parse_reply(reply_text(total=len(duplicate), approved=len(duplicate))), "tester", "date", QUEUE_SHA)

class ExportTests(unittest.TestCase):
    def _reviewed_file(self, tmp_name: str) -> Path:
        reviewed, _counts = applier.apply_reply(PENDING, applier.parse_reply(reply_text()), "tester", "2026-08-19", QUEUE_SHA)
        path = HERE / "tests" / tmp_name
        path.write_text("\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for entry in reviewed) + "\n", encoding="utf-8")
        return path
    def test_export_assembles_the_operational_conversation_shape(self) -> None:
        path = self._reviewed_file("_reviewed_ok.jsonl")
        try: rows, summary = exporter.export(path)
        finally: path.unlink()
        self.assertEqual(summary["records"], len(PENDING)); fact = next(row for row in rows if row["behavior"] == "fact_recall")
        self.assertEqual(fact["messages"][0]["role"], "system"); self.assertIn("[턴 브리핑", fact["messages"][0]["content"]); self.assertTrue(fact["messages"][1]["content"].startswith("[YouTube] "))
        register_row = next(row for row in rows if row["behavior"] == "register"); self.assertNotIn("[턴 브리핑", register_row["messages"][0]["content"])
    def test_export_refuses_pending_or_unattributed_records(self) -> None:
        with self.assertRaises(exporter.BehaviorExportError): exporter.export(PENDING_PATH)
        broken = self._reviewed_file("_reviewed_broken.jsonl")
        lines = broken.read_text(encoding="utf-8").splitlines(); first = json.loads(lines[0]); first["review"]["reviewer"] = ""; lines[0] = json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")); broken.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            with self.assertRaises(exporter.BehaviorExportError): exporter.export(broken)
        finally: broken.unlink()

if __name__ == "__main__": unittest.main()
