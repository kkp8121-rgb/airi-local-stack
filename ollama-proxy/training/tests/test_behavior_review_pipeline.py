import importlib.util
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


applier = _load("apply_behavior_review_reply")
exporter = _load("export_behavior_chat_dataset")

PENDING = [json.loads(line) for line in
           (HERE / "seed" / "airi_behavior_seed_pending.jsonl")
           .read_text(encoding="utf-8").splitlines() if line]


def reply_text(rejected: str = "", rewrites: dict[str, str] | None = None,
               undecided: int = 0, approved: int | None = None,
               total: int | None = None) -> str:
    rewrites = rewrites or {}
    total = total if total is not None else len(PENDING)
    if approved is None:
        approved = total - len([x for x in rejected.split(",") if x.strip()]) - len(rewrites)
    lines = ["[AIRI 행동 SFT 검수 회신 2026-08-19]", f"approved={approved}/{total}"]
    if rejected:
        lines.append("rejected=" + rejected)
    for record_id, text in rewrites.items():
        lines.append(f"rewrite: {record_id} => {text}")
    if undecided:
        lines.append(f"(미결정 {undecided}건: bseed-register-0001)")
    return "\n".join(lines)


class ReplyParsingTests(unittest.TestCase):
    def test_full_approval_reply_round_trips(self) -> None:
        reply = applier.parse_reply(reply_text())
        reviewed, counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-19")
        self.assertEqual(counts, {"approved": len(PENDING), "rewritten": 0, "rejected": 0})
        self.assertEqual(len(reviewed), len(PENDING))
        for entry in reviewed:
            self.assertIs(entry["training_eligible"], True)
            self.assertEqual(entry["review"]["status"], "approved")
            self.assertEqual(entry["review"]["reviewer"], "tester")

    def test_rejections_and_rewrites_are_exceptions_only(self) -> None:
        target = PENDING[0]["id"]
        victim = PENDING[1]["id"]
        reply = applier.parse_reply(reply_text(
            rejected=victim, rewrites={target: "새 답변으로 간다!"}))
        reviewed, counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-19")
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["rewritten"], 1)
        by_id = {entry["id"]: entry for entry in reviewed}
        self.assertNotIn(victim, by_id)
        self.assertEqual(by_id[target]["answer"], "새 답변으로 간다!")
        self.assertIn("operator-rewrite", by_id[target]["provenance"]["template"])

    def test_incomplete_or_inconsistent_replies_fail_closed(self) -> None:
        with self.assertRaises(applier.ReviewReplyError):
            applier.parse_reply(reply_text(undecided=3))
        with self.assertRaises(applier.ReviewReplyError):
            applier.parse_reply("그냥 텍스트")
        # 총계 불일치 · 미지 id · approved 수 불일치
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, applier.parse_reply(reply_text(total=99, approved=99)),
                                "tester", "2026-08-19")
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, applier.parse_reply(
                reply_text(rejected="bseed-substance-9999")), "tester", "2026-08-19")
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, applier.parse_reply(
                reply_text(approved=1)), "tester", "2026-08-19")

    def test_polite_rewrite_is_refused(self) -> None:
        target = PENDING[0]["id"]
        reply = applier.parse_reply(reply_text(rewrites={target: "네, 기억하고 있어요!"}))
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, reply, "tester", "2026-08-19")


class ExportTests(unittest.TestCase):
    def _reviewed_file(self, tmp_name: str) -> Path:
        reply = applier.parse_reply(reply_text())
        reviewed, _counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-19")
        path = HERE / "tests" / tmp_name
        path.write_text("\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")) for entry in reviewed) + "\n",
                        encoding="utf-8")
        return path

    def test_export_assembles_the_operational_conversation_shape(self) -> None:
        path = self._reviewed_file("_reviewed_ok.jsonl")
        try:
            rows, summary = exporter.export(path)
        finally:
            path.unlink()
        self.assertEqual(summary["records"], len(PENDING))
        by_id = {row["id"]: row for row in rows}
        fact = next(row for row in rows if row["behavior"] == "fact_recall")
        system = fact["messages"][0]
        self.assertEqual(system["role"], "system")
        self.assertIn("[턴 브리핑", system["content"])          # 브리핑이 시스템에 실린다
        self.assertIn("AIRI", system["content"])
        user = fact["messages"][1]
        self.assertTrue(user["content"].startswith("[YouTube] "))  # 런타임 프리픽스
        self.assertEqual(fact["messages"][2]["role"], "assistant")
        register_row = next(row for row in rows if row["behavior"] == "register")
        self.assertNotIn("[턴 브리핑", register_row["messages"][0]["content"])

    def test_export_refuses_pending_or_unattributed_records(self) -> None:
        pending_path = HERE / "seed" / "airi_behavior_seed_pending.jsonl"
        with self.assertRaises(exporter.BehaviorExportError):
            exporter.export(pending_path)  # pending 그대로는 학습 불가
        broken = self._reviewed_file("_reviewed_broken.jsonl")
        lines = broken.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["review"]["reviewer"] = ""
        lines[0] = json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        broken.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            with self.assertRaises(exporter.BehaviorExportError):
                exporter.export(broken)
        finally:
            broken.unlink()


if __name__ == "__main__":
    unittest.main()
