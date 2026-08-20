import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("build_extraction_review_form_test",
                                              HERE / "build_extraction_review_form.py")
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

NODE = shutil.which("node")

# Node 로 폼이 실제로 배포하는 <script> 원문을 그대로 실행해 검증한다 — 로직을
# 파이썬으로 재구현해 별도로 assert 하면 폼과 테스트가 따로 놀 위험이 있다.
_DOM_SHIM = """
'use strict';
const __store = {};
global.localStorage = {
  getItem: (k) => (k in __store ? __store[k] : null),
  setItem: (k, v) => { __store[k] = String(v); },
  removeItem: (k) => { delete __store[k]; },
};
const __elements = {};
function __fakeEl(id) {
  if (!__elements[id]) __elements[id] = { _html: '', _value: '', _text: '', _class: '', style: {} };
  const backing = __elements[id];
  return {
    get innerHTML() { return backing._html; }, set innerHTML(v) { backing._html = v; },
    get value() { return backing._value; }, set value(v) { backing._value = v; },
    get textContent() { return backing._text; }, set textContent(v) { backing._text = v; },
    get className() { return backing._class; }, set className(v) { backing._class = v; },
    style: backing.style, focus() {}, select() {},
  };
}
global.document = { getElementById: __fakeEl };
// Node 24 has a built-in read-only `navigator` global — replace it via defineProperty.
Object.defineProperty(global, 'navigator', {
  value: { clipboard: { writeText: () => {} } }, configurable: true,
});
global.confirm = () => true;
"""


def _run_js_driver(script: str, driver: str) -> list[dict]:
    """DOM 스텁 + 폼 스크립트 원문 + 시나리오 드라이버를 Node 로 실행한다.

    드라이버는 결과를 한 줄에 하나씩 ``console.log(JSON.stringify(...))`` 로
    찍는다고 가정하고, 그 줄들을 파싱해 dict 리스트로 돌려준다.
    """
    if NODE is None:
        raise unittest.SkipTest("node 실행파일을 찾을 수 없다 — JS 실행 검증을 건너뛴다")
    harness = _DOM_SHIM + "\n" + script + "\n" + driver
    result = subprocess.run([NODE, "-"], input=harness,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    if result.returncode != 0:
        raise AssertionError(f"node 실행 실패:\n{result.stderr}")
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


class ExtractionReviewFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.markup = builder.build_form(builder.DEFAULT_PENDING, "test-label")
        cls.records = [json.loads(line) for line in
                       builder.DEFAULT_PENDING.read_text(encoding="utf-8").splitlines() if line]

    def _payload(self) -> list[dict]:
        raw = self.markup.split("const RECORDS = ", 1)[1].split(";\n", 1)[0]
        return json.loads(raw)

    def test_every_pending_record_is_embedded(self) -> None:
        for record in self.records:
            self.assertIn(record["id"], self.markup)
        self.assertIn(f"({len(self.records)}건)", self.markup)

    def test_embedded_payload_round_trips_and_stays_content_faithful(self) -> None:
        embedded = self._payload()
        self.assertEqual(len(embedded), len(self.records))
        by_id = {record["id"]: record for record in self.records}
        for entry in embedded:
            source = by_id[entry["id"]]
            self.assertEqual(entry["scene"], source["scene"])
            self.assertEqual(entry["character"], source["character"])
            self.assertEqual(entry["turns"], source["turns"])
            self.assertEqual(entry["target"], source["target"])

    def test_every_target_carries_readable_items_with_evidence(self) -> None:
        # 검수자가 판단하려면 추출 항목과 그 근거 인용이 보여야 한다.
        embedded = self._payload()
        evidenced = 0
        for entry in embedded:
            items = json.loads(entry["target"])["extracted"]
            for item in items:
                self.assertIn("evidence", item)
                self.assertIn(item["evidence"], entry["turns"])
                evidenced += 1
        self.assertGreater(evidenced, 0)
        self.assertIn("evidence", self.markup.split("const RECORDS")[1])

    def test_every_scene_has_a_label(self) -> None:
        scenes = {record["scene"] for record in self.records}
        labels = self.markup.split("const SCENE_LABELS = ", 1)[1].split(";\n", 1)[0]
        for scene in scenes:
            self.assertIn(f'"{scene}"', labels)

    def test_reply_header_matches_the_applier_contract(self) -> None:
        # 헤더는 (c) 큐 sha 를 포함하도록 확장됐다 — 값 자체는 QUEUE_SHA 런타임 상수 참조.
        self.assertIn("[AIRI 추출 SFT 검수 회신 test-label queue=${QUEUE_SHA}]", self.markup)
        self.assertNotIn("__DATE__", self.markup)
        self.assertNotIn("__QUEUE_SHA__", self.markup)

    def test_form_never_claims_training_eligibility(self) -> None:
        # 폼은 검수 입력 수집용이지 승인·학습 권한이 아니다.
        self.assertNotIn("training_eligible", self.markup.split("const RECORDS")[0])
        self.assertIn("검수 회신", self.markup)

    def test_committed_form_matches_the_builder_output(self) -> None:
        committed = builder.DEFAULT_OUTPUT
        if committed.exists():
            self.assertEqual(committed.read_text(encoding="utf-8"),
                             builder.build_form(builder.DEFAULT_PENDING, builder.DEFAULT_DATE_LABEL))

    def test_empty_queue_fails_closed(self) -> None:
        empty = HERE / "tests" / "_empty_extraction_pending.jsonl"
        empty.write_text("", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                builder.build_form(empty, "x")
        finally:
            empty.unlink()


_JS_DRIVER = r"""
const rec0 = RECORDS[0];
function out(caseName, extra) { console.log(JSON.stringify(Object.assign({ case: caseName }, extra))); }

out('rec0_id', { id: rec0.id });

// (a) validateRewriteTarget: 순수 함수 시나리오 — 실제 큐 레코드로 검증한다.
out('valid_original_target', { result: validateRewriteTarget(rec0.target, rec0.turns) });

(function () {
  const parsed = JSON.parse(rec0.target);
  parsed.extracted[0].evidence = '턴 원문에 존재하지 않는 근거 문장이다';
  out('bad_evidence', { result: validateRewriteTarget(JSON.stringify(parsed), rec0.turns) });
})();

(function () {
  const parsed = JSON.parse(rec0.target);
  const item = parsed.extracted[0];
  if (item.kind === 'entity') item.name = '없는이름XYZ';
  else if (item.kind === 'fact') item.subjectNames = ['없는이름XYZ'];
  else { item.sourceName = '없는이름XYZ'; }
  out('bad_name', { result: validateRewriteTarget(JSON.stringify(parsed), rec0.turns) });
})();

out('malformed_json', { result: validateRewriteTarget('{not valid json', rec0.turns) });
out('wrong_shape_array', { result: validateRewriteTarget('[]', rec0.turns) });
out('wrong_shape_object', { result: validateRewriteTarget('{"foo":1}', rec0.turns) });
out('empty_extracted_ok', { result: validateRewriteTarget('{"extracted":[]}', rec0.turns) });

// (b) renderItems: target JSON 파싱 실패 vs skip_chatter 정답 — 구분 렌더 확인.
out('render_malformed_target', { html: renderItems({ target: '{not json' }) });
out('render_empty_extracted', { html: renderItems({ target: '{"extracted":[]}' }) });

// (a) buildResult: 위반 rewrite 는 미결정 취급, 유효 rewrite 는 회신에 포함.
setDecision(rec0.id, 'rewrite');
setRewriteText(rec0.id, '{"extracted":[{"evidence":"턴에 없는 근거"}]}');
buildResult();
out('invalid_rewrite_reply', { text: document.getElementById('out').value });

decisions = {};
localStorage.removeItem(KEY);
approveVisible();
setDecision(rec0.id, 'rewrite');
setRewriteText(rec0.id, rec0.target);
buildResult();
out('valid_rewrite_reply', { text: document.getElementById('out').value });
"""


class ExtractionReviewFormJsBehaviorTests(unittest.TestCase):
    """(a)(b) 폼이 실제로 배포하는 <script> 원문을 Node 로 실행해 검증한다.

    로직을 파이썬으로 재구현해 별도로 assert 하면 폼과 테스트가 따로 놀 위험이
    있으므로, 임베드된 실제 큐 레코드와 함께 스크립트를 그대로 실행한다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        markup = builder.build_form(builder.DEFAULT_PENDING, "test-label")
        cls.script = markup.split("<script>", 1)[1].split("</script>", 1)[0]
        cls.results = {row["case"]: row for row in _run_js_driver(cls.script, _JS_DRIVER)}

    def test_ssot_subset_comment_is_present(self) -> None:
        # 서버 게이트가 SSoT 이고 JS 는 그 보수적 부분집합이라는 사실을 주석으로 명시한다.
        self.assertIn("SSoT", self.script)
        self.assertIn("보수적 부분집합", self.script)

    def test_valid_original_target_passes_prevalidation(self) -> None:
        self.assertTrue(self.results["valid_original_target"]["result"]["ok"])

    def test_evidence_outside_turns_is_rejected(self) -> None:
        result = self.results["bad_evidence"]["result"]
        self.assertFalse(result["ok"])
        self.assertIn("근거", result["reason"])

    def test_name_outside_evidence_is_rejected(self) -> None:
        result = self.results["bad_name"]["result"]
        self.assertFalse(result["ok"])
        self.assertIn("이름", result["reason"])

    def test_malformed_json_is_rejected(self) -> None:
        self.assertFalse(self.results["malformed_json"]["result"]["ok"])

    def test_wrong_shape_is_rejected(self) -> None:
        self.assertFalse(self.results["wrong_shape_array"]["result"]["ok"])
        self.assertFalse(self.results["wrong_shape_object"]["result"]["ok"])

    def test_emptying_the_extraction_is_a_legitimate_rewrite(self) -> None:
        self.assertTrue(self.results["empty_extracted_ok"]["result"]["ok"])

    def test_target_parse_failure_renders_a_distinct_badge_from_skip_chatter(self) -> None:
        # Task 2 리뷰 Minor 1 — 파싱 실패가 "정답"과 같은 문구로 렌더되면 안 된다.
        malformed_html = self.results["render_malformed_target"]["html"]
        empty_html = self.results["render_empty_extracted"]["html"]
        self.assertIn("item err", malformed_html)
        self.assertNotIn("아무것도 뽑지 않는 것이 정답", malformed_html)
        self.assertIn("item none", empty_html)
        self.assertIn("아무것도 뽑지 않는 것이 정답", empty_html)

    def test_invalid_rewrite_is_excluded_from_the_reply_as_undecided(self) -> None:
        rec0_id = self.results["rec0_id"]["id"]
        text = self.results["invalid_rewrite_reply"]["text"]
        self.assertIn("(미결정", text)
        self.assertNotIn(f"rewrite: {rec0_id} =>", text)

    def test_valid_rewrite_is_included_in_the_reply(self) -> None:
        rec0_id = self.results["rec0_id"]["id"]
        text = self.results["valid_rewrite_reply"]["text"]
        self.assertNotIn("(미결정", text)
        self.assertIn(f"rewrite: {rec0_id} =>", text)


if __name__ == "__main__":
    unittest.main()
