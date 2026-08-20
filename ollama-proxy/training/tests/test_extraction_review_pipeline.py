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
builder = _load("build_extraction_review_form")

PENDING_PATH = HERE / "seed" / "airi_extraction_seed_pending.jsonl"
PENDING = [json.loads(line) for line in
           PENDING_PATH.read_text(encoding="utf-8").splitlines() if line]
QUEUE_SHA = applier.queue_digest(PENDING_PATH)


def reply_text(rejected: str = "", rewrites: dict[str, str] | None = None,
               undecided: int = 0, approved: int | None = None,
               total: int | None = None, queue_sha: str | None = None) -> str:
    rewrites = rewrites or {}
    total = total if total is not None else len(PENDING)
    if approved is None:
        approved = total - len([x for x in rejected.split(",") if x.strip()]) - len(rewrites)
    queue_sha = queue_sha if queue_sha is not None else QUEUE_SHA
    lines = [f"[AIRI 추출 SFT 검수 회신 2026-08-20 queue={queue_sha}]", f"approved={approved}/{total}"]
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
        reviewed, counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)
        self.assertEqual(counts, {"approved": len(PENDING), "rewritten": 0, "rejected": 0})
        self.assertEqual(len(reviewed), len(PENDING))
        for entry in reviewed:
            self.assertIs(entry["training_eligible"], True)
            self.assertEqual(entry["review"]["status"], "approved")
            self.assertEqual(entry["review"]["reviewer"], "tester")
            self.assertEqual(entry["review"]["approved_at"], "2026-08-20")

    def test_pending_queue_is_never_mutated_in_place(self) -> None:
        before = compact(PENDING[0])
        applier.apply_reply(PENDING, applier.parse_reply(reply_text()), "tester", "2026-08-20", QUEUE_SHA)
        self.assertEqual(compact(PENDING[0]), before)
        self.assertIs(PENDING[0]["training_eligible"], False)

    def test_rejections_and_rewrites_are_exceptions_only(self) -> None:
        target = PENDING[0]
        victim = PENDING[1]["id"]
        parsed = json.loads(target["target"])
        parsed["extracted"][0]["content"] = "검수자가 고쳐 쓴 내용"
        reply = applier.parse_reply(reply_text(
            rejected=victim, rewrites={target["id"]: compact(parsed)}))
        reviewed, counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)
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
        reviewed, _counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)
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
                                "tester", "2026-08-20", QUEUE_SHA)
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, applier.parse_reply(
                reply_text(rejected="xseed-state_change-9999")), "tester", "2026-08-20", QUEUE_SHA)
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, applier.parse_reply(
                reply_text(approved=1)), "tester", "2026-08-20", QUEUE_SHA)

    def test_behavior_form_reply_is_not_accepted_here(self) -> None:
        # 두 큐가 같은 폼 UX를 쓰므로 헤더가 유일한 구분점이다.
        with self.assertRaises(applier.ReviewReplyError):
            applier.parse_reply("[AIRI 행동 SFT 검수 회신 2026-08-19]\napproved=181/181")


class RewriteSpanGateTests(unittest.TestCase):
    """수정 답변은 합성 때와 같은 스팬 검증을 통과해야 한다 — 한 건이라도 실패하면 전체 거부."""

    def _refuse(self, rewrite: str) -> None:
        reply = applier.parse_reply(reply_text(rewrites={PENDING[0]["id"]: rewrite}))
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)

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
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)

    def test_emptying_an_extraction_is_a_legitimate_rewrite(self) -> None:
        # "이건 뽑지 말았어야 한다" 는 거부가 아니라 빈 추출로도 표현될 수 있다.
        reply = applier.parse_reply(reply_text(rewrites={PENDING[0]["id"]: '{"extracted":[]}'}))
        reviewed, counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)
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
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)


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


class QueueBindingTests(unittest.TestCase):
    """(c) 회신이 큐 내용 sha 에 결속된다 — Task 2 리뷰 Minor 9 해소.

    큐 sha 결속은 apply_reply 의 필수 인자다(기본값 없음) — fail-closed 원칙상
    조용히 우회할 수 있는 경로를 두지 않는다. `test_export_extraction_sft_dataset.py`
    도 이 시그니처에 맞춰 함께 갱신했다.
    """

    def test_queue_digest_is_12_lowercase_hex_chars(self) -> None:
        self.assertRegex(QUEUE_SHA, r"^[0-9a-f]{12}$")

    def test_reply_without_queue_segment_is_refused_fail_closed(self) -> None:
        # 큐 결속은 선택이 아니라 강제다 — queue= 세그먼트가 없는 구 형식 회신을
        # 조용히 통과시키는 우회 경로를 두지 않는다. 오류에는 검수자가 원인을 알 수
        # 있도록 최신 폼 파일명을 안내한다.
        legacy = f"[AIRI 추출 SFT 검수 회신 2026-08-20]\napproved={len(PENDING)}/{len(PENDING)}"
        reply = applier.parse_reply(legacy)
        self.assertIsNone(reply["queue_sha"])
        with self.assertRaises(applier.ReviewReplyError) as ctx:
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)
        self.assertIn("AIRI-EXTRACTION-REVIEW-FORM-2026-08-20.html", str(ctx.exception))

    def test_matching_queue_sha_is_accepted(self) -> None:
        reply = applier.parse_reply(reply_text())
        self.assertEqual(reply["queue_sha"], QUEUE_SHA)
        reviewed, _counts = applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)
        self.assertEqual(len(reviewed), len(PENDING))

    def test_mismatched_queue_sha_is_refused_when_enforced(self) -> None:
        reply = applier.parse_reply(reply_text(queue_sha="0" * 12))
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)

    def test_missing_queue_sha_is_refused_when_enforcement_is_requested(self) -> None:
        legacy = f"[AIRI 추출 SFT 검수 회신 2026-08-20]\napproved={len(PENDING)}/{len(PENDING)}"
        reply = applier.parse_reply(legacy)
        with self.assertRaises(applier.ReviewReplyError):
            applier.apply_reply(PENDING, reply, "tester", "2026-08-20", QUEUE_SHA)

    def test_reply_sha_binds_to_queue_and_rejects_a_regenerated_queue(self) -> None:
        # 재생성된 큐(레코드 수·id 는 동일, 내용 일부만 다름)에 옛 회신을 적용하면
        # 총계·id 검사는 통과하지만 큐 sha 검사가 잡아야 한다 (Minor 9 의 핵심 시나리오).
        mutated = [json.loads(compact(record)) for record in PENDING]
        mutated[0]["partition"]["tier"] = "S9-regenerated"
        mutated_bytes = ("\n".join(compact(record) for record in mutated) + "\n").encode("utf-8")
        self.assertNotEqual(mutated_bytes, PENDING_PATH.read_bytes())
        tmp_path = HERE / "tests" / "_extraction_pending_regenerated.jsonl"
        tmp_path.write_bytes(mutated_bytes)
        try:
            new_sha = applier.queue_digest(tmp_path)
            self.assertNotEqual(new_sha, QUEUE_SHA)
            stale_reply = applier.parse_reply(reply_text(queue_sha=QUEUE_SHA))
            with self.assertRaises(applier.ReviewReplyError):
                applier.apply_reply(mutated, stale_reply, "tester", "2026-08-20", new_sha)
            fresh_reply = applier.parse_reply(reply_text(queue_sha=new_sha))
            reviewed, _counts = applier.apply_reply(mutated, fresh_reply, "tester", "2026-08-20", new_sha)
            self.assertEqual(len(reviewed), len(mutated))
        finally:
            tmp_path.unlink()

    def test_form_embeds_the_current_queue_sha_matching_the_applier(self) -> None:
        markup = builder.build_form(builder.DEFAULT_PENDING, "test-label")
        embedded = markup.split("const QUEUE_SHA = '", 1)[1].split("'", 1)[0]
        self.assertEqual(embedded, QUEUE_SHA)
        self.assertIn("queue=${QUEUE_SHA}", markup)


class ApplierCliQueueTests(unittest.TestCase):
    def test_cli_rejects_a_stale_queue_sha(self) -> None:
        reply_path = HERE / "tests" / "_extraction_reply_stale_queue.txt"
        reply_path.write_text(reply_text(queue_sha="0" * 12), encoding="utf-8")
        try:
            with self.assertRaises(applier.ReviewReplyError):
                applier.main(["--reply", str(reply_path), "--reviewer", "tester",
                              "--approved-at", "2026-08-20"])
        finally:
            reply_path.unlink()

    def test_cli_succeeds_with_the_matching_queue_sha(self) -> None:
        reply_path = HERE / "tests" / "_extraction_reply_ok_queue.txt"
        out_path = HERE / "tests" / "_extraction_reviewed_ok_queue.jsonl"
        reply_path.write_text(reply_text(), encoding="utf-8")
        try:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                code = applier.main(["--reply", str(reply_path), "--reviewer", "tester",
                                    "--approved-at", "2026-08-20", "--output", str(out_path)])
            self.assertEqual(code, 0)
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["records"], len(PENDING))
        finally:
            reply_path.unlink()
            out_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
