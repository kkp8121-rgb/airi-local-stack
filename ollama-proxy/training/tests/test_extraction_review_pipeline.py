import contextlib
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

PENDING = [json.loads(line) for line in
           (HERE / "seed" / "airi_extraction_seed_pending.jsonl")
           .read_text(encoding="utf-8").splitlines() if line]


def reply_text(rejected: str = "", rewrites: dict[str, str] | None = None,
               undecided: int = 0, approved: int | None = None,
               total: int | None = None) -> str:
    rewrites = rewrites or {}
    total = total if total is not None else len(PENDING)
    if approved is None:
        approved = total - len([x for x in rejected.split(",") if x.strip()]) - len(rewrites)
    lines = ["[AIRI 추출 SFT 검수 회신 2026-08-20]", f"approved={approved}/{total}"]
    if rejected:
        lines.append("rejected=" + rejected)
    for record_id, text in rewrites.items():
        lines.append(f"rewrite: {record_id} => {text}")
    if undecided:
        lines.append(f"(미결정 {undecided}건: xseed-state_change-0001)")
    return "\n".join(lines)


def compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ReplyParsingTests(unittest.TestCase):
    def test_full_approval_reply_round_trips(self) -> None:
        reply = applier.parse_reply(reply_text())
        reviewed, counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20")
        self.assertEqual(counts, {"approved": len(PENDING), "rewritten": 0, "rejected": 0})
        self.assertEqual(len(reviewed), len(PENDING))
        for entry in reviewed:
            self.assertIs(entry["training_eligible"], True)
            self.assertEqual(entry["review"]["status"], "approved")
            self.assertEqual(entry["review"]["reviewer"], "tester")
            self.assertEqual(entry["review"]["approved_at"], "2026-08-20")

    def test_pending_queue_is_never_mutated_in_place(self) -> None:
        before = compact(PENDING[0])
        applier.apply_reply(PENDING, applier.parse_reply(reply_text()), "tester", "2026-08-20")
        self.assertEqual(compact(PENDING[0]), before)
        self.assertIs(PENDING[0]["training_eligible"], False)

    def test_rejections_and_rewrites_are_exceptions_only(self) -> None:
        target = PENDING[0]
        victim = PENDING[1]["id"]
        parsed = json.loads(target["target"])
        parsed["extracted"][0]["content"] = "검수자가 고쳐 쓴 내용"
        reply = applier.parse_reply(reply_text(
            rejected=victim, rewrites={target["id"]: compact(parsed)}))
        reviewed, counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20")
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["rewritten"], 1)
        by_id = {entry["id"]: entry for entry in reviewed}
        self.assertNotIn(victim, by_id)
        self.assertEqual(json.loads(by_id[target["id"]]["target"])["extracted"][0]["content"],
                         "검수자가 고쳐 쓴 내용")
        self.assertIn("operator-rewrite", by_id[target["id"]]["provenance"]["template"])

    def test_accepted_rewrite_is_stored_in_canonical_form(self) -> None:
        # 합성 타깃과 같은 직렬화가 아니면 같은 내용이 다른 학습 문자열이 된다.
        target = PENDING[0]
        parsed = json.loads(target["target"])
        loose = json.dumps(parsed, ensure_ascii=False, indent=None, sort_keys=False)
        reply = applier.parse_reply(reply_text(rewrites={target["id"]: loose}))
        reviewed, _counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20")
        stored = next(e for e in reviewed if e["id"] == target["id"])["target"]
        self.assertEqual(stored, compact(parsed))
        self.assertEqual(stored, target["target"])

    def test_incomplete_or_inconsistent_replies_fail_closed(self) -> None:
        with self.assertRaises(applier.ReviewReplyError):
            applier.parse_reply(reply_text(undecided=3))
        with self.assertRaises(applier.ReviewReplyError):
            applier.parse_reply("그냥 텍스트")
        with self.assertRaises(applier.ReviewReplyError):
            applier.parse_reply("[AIRI 추출 SFT 검수 회신 2026-08-20]\n결정 끝")
        # 총계 불일치 · 미지 id · approved 수 불일치
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, applier.parse_reply(reply_text(total=99, approved=99)),
                                "tester", "2026-08-20")
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, applier.parse_reply(
                reply_text(rejected="xseed-state_change-9999")), "tester", "2026-08-20")
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, applier.parse_reply(
                reply_text(approved=1)), "tester", "2026-08-20")

    def test_behavior_form_reply_is_not_accepted_here(self) -> None:
        # 두 큐가 같은 폼 UX를 쓰므로 헤더가 유일한 구분점이다.
        with self.assertRaises(applier.ReviewReplyError):
            applier.parse_reply("[AIRI 행동 SFT 검수 회신 2026-08-19]\napproved=181/181")


class RewriteSpanGateTests(unittest.TestCase):
    """수정 답변은 합성 때와 같은 스팬 검증을 통과해야 한다 — 한 건이라도 실패하면 전체 거부."""

    def _refuse(self, rewrite: str) -> None:
        reply = applier.parse_reply(reply_text(rewrites={PENDING[0]["id"]: rewrite}))
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20")

    def test_evidence_absent_from_turns_is_refused(self) -> None:
        parsed = json.loads(PENDING[0]["target"])
        parsed["extracted"][0]["evidence"] = "대화에 존재하지 않는 근거 문장이다."
        self._refuse(compact(parsed))

    def test_name_outside_its_own_evidence_is_refused(self) -> None:
        parsed = json.loads(PENDING[0]["target"])
        parsed["extracted"][0]["name"] = "없는사람"
        self._refuse(compact(parsed))

    def test_missing_evidence_field_is_refused(self) -> None:
        parsed = json.loads(PENDING[0]["target"])
        del parsed["extracted"][0]["evidence"]
        self._refuse(compact(parsed))

    def test_schema_violating_rewrite_is_refused(self) -> None:
        parsed = json.loads(PENDING[0]["target"])
        parsed["extracted"][0]["kind"] = "person"
        self._refuse(compact(parsed))

    def test_malformed_json_and_empty_rewrites_are_refused(self) -> None:
        self._refuse("{extracted: broken}")
        self._refuse("[]")
        reply = applier.parse_reply(
            f"[AIRI 추출 SFT 검수 회신 2026-08-20]\napproved={len(PENDING) - 1}/{len(PENDING)}\n"
            f"rewrite: {PENDING[0]['id']} => ")
        # 빈 수정 답변은 rewrite 로 인식되지 않으므로 approved 정합 검증이 먼저 잡는다.
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20")

    def test_emptying_an_extraction_is_a_legitimate_rewrite(self) -> None:
        # "이건 뽑지 말았어야 한다" 는 거부가 아니라 빈 추출로도 표현될 수 있다.
        reply = applier.parse_reply(reply_text(rewrites={PENDING[0]["id"]: '{"extracted":[]}'}))
        reviewed, counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20")
        self.assertEqual(counts["rewritten"], 1)
        stored = next(e for e in reviewed if e["id"] == PENDING[0]["id"])["target"]
        self.assertEqual(json.loads(stored), {"extracted": []})

    def test_one_bad_rewrite_rejects_the_whole_reply(self) -> None:
        good = json.loads(PENDING[0]["target"])
        good["extracted"][0]["content"] = "괜찮은 수정"
        bad = json.loads(PENDING[2]["target"])
        for item in bad["extracted"]:
            item["evidence"] = "턴에 없는 근거"
        reply = applier.parse_reply(reply_text(rewrites={
            PENDING[0]["id"]: compact(good), PENDING[2]["id"]: compact(bad)}))
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20")


class ApplierCliTests(unittest.TestCase):
    def test_reviewer_and_approved_at_are_required(self) -> None:
        reply_path = HERE / "tests" / "_extraction_reply_cli.txt"
        reply_path.write_text(reply_text(), encoding="utf-8")
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    applier.main(["--reply", str(reply_path)])
                with self.assertRaises(SystemExit):
                    applier.main(["--reply", str(reply_path), "--reviewer", "  ",
                                  "--approved-at", "2026-08-20"])
        finally:
            reply_path.unlink()


if __name__ == "__main__":
    unittest.main()
