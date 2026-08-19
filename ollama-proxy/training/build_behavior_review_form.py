"""Render the behavior pending queue as a standalone human-review HTML form.

The style pipeline reviews through a CLI; the project's operator reviews faster
through the click-form pattern already used for decision sheets, so this emits
one self-contained HTML file per queue — records embedded inline, decisions
kept in localStorage, and a compact reply text that lists only exceptions
(rejections and rewrites) so 181 approvals paste back as a few lines.

Rendering is read-only with respect to governance: the form never edits the
queue, and its output is a human decision record to be applied by a separate
compile step after the user pastes it back.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PENDING = HERE / "seed" / "airi_behavior_seed_pending.jsonl"
DEFAULT_OUTPUT = HERE.parent.parent / "airi_docs" / "진행예정" / "AIRI-BEHAVIOR-REVIEW-FORM-2026-08-19.html"

PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIRI 행동 SFT 검수 — __DATE__ (__TOTAL__건)</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --ink:#1c2330; --sub:#5b6472; --line:#e3e6ea;
          --accent:#3b6ef5; --ok:#1a7f4b; --bad:#c0392b; --fix:#b25e09; }
  * { box-sizing:border-box; }
  body { margin:0; padding:20px 14px 90px; background:var(--bg); color:var(--ink);
         font-family:'Segoe UI','Malgun Gothic',system-ui,sans-serif; line-height:1.5; }
  .wrap { max-width:820px; margin:0 auto; }
  h1 { font-size:1.2rem; margin:0 0 4px; }
  .lead { color:var(--sub); font-size:.85rem; margin-bottom:14px; }
  .tabs { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px; }
  .tabs button { padding:6px 12px; border:1px solid var(--line); border-radius:16px;
                 background:var(--card); cursor:pointer; font-size:.82rem; font-family:inherit; }
  .tabs button.active { background:var(--accent); color:#fff; border-color:var(--accent); }
  .card { background:var(--card); border:1px solid var(--line); border-left:4px solid var(--line);
          border-radius:8px; padding:10px 12px; margin-bottom:8px; }
  .card.decided-approve { border-left-color:var(--ok); }
  .card.decided-reject { border-left-color:var(--bad); opacity:.75; }
  .card.decided-rewrite { border-left-color:var(--fix); }
  .meta { font-size:.72rem; color:var(--sub); margin-bottom:4px; }
  .meta code { background:var(--bg); padding:0 4px; border-radius:3px; }
  .briefing { font-size:.78rem; color:var(--sub); background:var(--bg); border-radius:6px;
              padding:6px 8px; margin:4px 0; white-space:pre-wrap; }
  .qa { margin:4px 0; font-size:.9rem; }
  .qa b { color:var(--accent); }
  .buttons { display:flex; gap:6px; margin-top:8px; }
  .buttons button { padding:5px 14px; border-radius:6px; border:1px solid var(--line);
                    background:var(--card); cursor:pointer; font-size:.84rem; font-family:inherit; }
  .buttons .b-approve.on { background:var(--ok); color:#fff; border-color:var(--ok); }
  .buttons .b-rewrite.on { background:var(--fix); color:#fff; border-color:var(--fix); }
  .buttons .b-reject.on { background:var(--bad); color:#fff; border-color:var(--bad); }
  textarea.rw { width:100%; margin-top:6px; padding:6px 8px; border:1px solid var(--line);
                border-radius:6px; font-family:inherit; font-size:.86rem; display:none; }
  .toolbar { position:fixed; bottom:0; left:0; right:0; background:var(--card);
             border-top:1px solid var(--line); padding:10px 14px; display:flex; gap:8px;
             justify-content:center; align-items:center; box-shadow:0 -2px 10px rgba(0,0,0,.06);
             flex-wrap:wrap; }
  .toolbar button { padding:8px 18px; border-radius:8px; border:1px solid var(--line);
                    background:var(--card); cursor:pointer; font-size:.86rem; font-family:inherit; }
  .toolbar .primary { background:var(--accent); color:#fff; border-color:var(--accent); font-weight:600; }
  #out { width:100%; max-width:820px; height:150px; margin:8px auto 0; display:none;
         font-family:Consolas,monospace; font-size:.78rem; border:1px solid var(--line);
         border-radius:8px; padding:8px; white-space:pre; }
  .prog { font-size:.84rem; color:var(--sub); }
</style>
</head>
<body>
<div class="wrap">
  <h1>AIRI 행동 SFT 학습 데이터 검수 (__TOTAL__건)</h1>
  <p class="lead">각 카드의 <b>답변(A)</b>이 AIRI가 배울 정답입니다 — 톤·반말·내용이 괜찮으면
  <b>승인</b>, 고치고 싶으면 <b>수정</b> 후 텍스트 입력, 빼고 싶으면 <b>거부</b>.
  선택은 자동 저장되고, [회신 만들기]는 <b>예외(거부·수정)만</b> 나열하므로 대부분 승인이면 회신이 짧습니다.
  일괄 버튼: 현재 탭의 미결정 건을 전부 승인.</p>
  <div class="tabs" id="tabs"></div>
  <div id="list"></div>
  <textarea id="out" readonly></textarea>
</div>
<div class="toolbar">
  <span class="prog" id="prog"></span>
  <button onclick="approveVisible()">현재 탭 미결정 전부 승인</button>
  <button class="primary" onclick="buildResult()">회신 만들기</button>
  <button onclick="copyResult()">복사</button>
  <button onclick="resetAll()">초기화</button>
</div>
<script>
const RECORDS = __RECORDS__;
const KEY = 'airi-behavior-review-__DATE__';
const BEHAVIOR_LABELS = { fact_recall:'기억 활용', addressee:'수신자', register:'반말', substance:'실질 응답' };
let decisions = {};
try { decisions = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
let activeTab = 'all';

function save() { localStorage.setItem(KEY, JSON.stringify(decisions)); refresh(); }

function setDecision(id, kind) {
  const current = decisions[id] || {};
  if (current.kind === kind && kind !== 'rewrite') { delete decisions[id]; }
  else { decisions[id] = { kind: kind, text: current.text || '' }; }
  save(); render();
}
function setRewriteText(id, text) {
  decisions[id] = { kind: 'rewrite', text: text };
  save();
}
function approveVisible() {
  for (const record of RECORDS) {
    if (activeTab !== 'all' && record.behavior !== activeTab) continue;
    if (!decisions[record.id]) decisions[record.id] = { kind: 'approve', text: '' };
  }
  save(); render();
}
function tabCounts() {
  const counts = { all: RECORDS.length };
  for (const record of RECORDS) counts[record.behavior] = (counts[record.behavior] || 0) + 1;
  return counts;
}
function renderTabs() {
  const counts = tabCounts();
  const tabs = ['all'].concat(Object.keys(BEHAVIOR_LABELS));
  document.getElementById('tabs').innerHTML = tabs.map(tab =>
    `<button class="${tab === activeTab ? 'active' : ''}" onclick="activeTab='${tab}';render()">` +
    `${tab === 'all' ? '전체' : BEHAVIOR_LABELS[tab]} ${counts[tab] || 0}</button>`).join('');
}
function render() {
  renderTabs();
  const list = document.getElementById('list');
  list.innerHTML = RECORDS.filter(record => activeTab === 'all' || record.behavior === activeTab)
    .map(record => {
      const decision = decisions[record.id] || {};
      const cls = decision.kind ? ' decided-' + decision.kind : '';
      const briefing = record.briefing
        ? `<div class="briefing">${escapeHtml(record.briefing)}</div>` : '';
      const rewriteShown = decision.kind === 'rewrite' ? 'style="display:block"' : '';
      return `<div class="card${cls}" id="card-${record.id}">
        <div class="meta"><code>${record.id}</code> · ${BEHAVIOR_LABELS[record.behavior]}</div>
        ${briefing}
        <div class="qa"><b>Q</b> ${escapeHtml(record.prompt)}</div>
        <div class="qa"><b>A</b> ${escapeHtml(record.answer)}</div>
        <div class="buttons">
          <button class="b-approve ${decision.kind === 'approve' ? 'on' : ''}" onclick="setDecision('${record.id}','approve')">승인</button>
          <button class="b-rewrite ${decision.kind === 'rewrite' ? 'on' : ''}" onclick="setDecision('${record.id}','rewrite')">수정</button>
          <button class="b-reject ${decision.kind === 'reject' ? 'on' : ''}" onclick="setDecision('${record.id}','reject')">거부</button>
        </div>
        <textarea class="rw" ${rewriteShown} placeholder="수정 답변 (반말)"
          oninput="setRewriteText('${record.id}', this.value)">${escapeHtml(decision.text || '')}</textarea>
      </div>`;
    }).join('');
  refresh();
}
function escapeHtml(text) {
  return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function refresh() {
  const done = Object.keys(decisions).length;
  document.getElementById('prog').textContent = `${done} / ${RECORDS.length} 결정`;
}
function buildResult() {
  const lines = ['[AIRI 행동 SFT 검수 회신 __DATE__]'];
  let approved = 0; const rejected = []; const rewritten = []; const undecided = [];
  for (const record of RECORDS) {
    const decision = decisions[record.id];
    if (!decision) { undecided.push(record.id); continue; }
    if (decision.kind === 'approve') approved += 1;
    else if (decision.kind === 'reject') rejected.push(record.id);
    else if (decision.kind === 'rewrite') rewritten.push(record.id + ' => ' + (decision.text || '').trim());
  }
  lines.push(`approved=${approved}/${RECORDS.length}`);
  if (rejected.length) lines.push('rejected=' + rejected.join(', '));
  for (const entry of rewritten) lines.push('rewrite: ' + entry);
  if (undecided.length) lines.push(`(미결정 ${undecided.length}건: ${undecided.slice(0, 10).join(', ')}${undecided.length > 10 ? ' …' : ''})`);
  const out = document.getElementById('out');
  out.style.display = 'block';
  out.value = lines.join('\\n');
}
function copyResult() {
  const out = document.getElementById('out');
  if (out.style.display === 'none' || !out.value) buildResult();
  out.focus(); out.select();
  try { navigator.clipboard.writeText(out.value); } catch (e) { document.execCommand('copy'); }
}
function resetAll() {
  if (!confirm('모든 검수 결정을 지울까요?')) return;
  decisions = {}; localStorage.removeItem(KEY);
  document.getElementById('out').style.display = 'none';
  render();
}
render();
</script>
</body>
</html>
"""


def build_form(pending_path: Path, date_label: str) -> str:
    records = []
    for line in pending_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        full = json.loads(line)
        records.append({"id": full["id"], "behavior": full["behavior"],
                        "briefing": full["briefing"], "prompt": full["prompt"],
                        "answer": full["answer"]})
    if not records:
        raise ValueError("pending queue is empty")
    payload = json.dumps(records, ensure_ascii=False)
    return (PAGE
            .replace("__RECORDS__", payload)
            .replace("__TOTAL__", str(len(records)))
            .replace("__DATE__", date_label))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="behavior pending queue review form builder")
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--date-label", default="2026-08-19")
    args = parser.parse_args(argv)
    markup = build_form(args.pending, args.date_label)
    args.output.write_text(markup, encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "bytes": len(markup.encode("utf-8"))},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
