"""Render the extraction pending queue as a standalone human-review HTML form.

Code already proved every target survives ``parse_stage_a_span`` against its own
turns, so nothing here re-litigates evidence validity. What the operator decides
is the remaining judgment the parser cannot make: whether an item is *worth*
extracting at all. The form therefore shows the turns verbatim next to each
extracted item and the exact span it quotes, and collects only the exceptions —
rejections and rewrites — so 102 approvals paste back as a few lines.

Rendering is read-only with respect to governance: the form never edits the
queue, and its output is a human decision record to be applied by a separate
compile step after the user pastes it back.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PENDING = HERE / "seed" / "airi_extraction_seed_pending.jsonl"
DEFAULT_DATE_LABEL = "2026-08-20"
DEFAULT_OUTPUT = (HERE.parent.parent / "airi_docs" / "진행예정" /
                  f"AIRI-EXTRACTION-REVIEW-FORM-{DEFAULT_DATE_LABEL}.html")

PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIRI 추출 SFT 검수 — __DATE__ (__TOTAL__건)</title>
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
  .turns { font-size:.82rem; background:var(--bg); border-radius:6px; padding:6px 8px;
           margin:4px 0; white-space:pre-wrap; }
  .items { margin:6px 0 0; }
  .item { border-left:3px solid var(--accent); padding:2px 0 2px 8px; margin:6px 0; }
  .item .head { font-size:.78rem; color:var(--accent); font-weight:600; }
  .item .body { font-size:.88rem; }
  .item .evid { font-size:.76rem; color:var(--sub); margin-top:2px; }
  .item.none { border-left-color:var(--sub); color:var(--sub); font-size:.85rem; }
  .item.err { border-left-color:var(--bad); color:var(--bad); font-size:.85rem; }
  .card.invalid-rewrite { border-left-color:var(--bad); }
  .rw-err { font-size:.74rem; color:var(--bad); margin-top:4px; }
  .buttons { display:flex; gap:6px; margin-top:8px; }
  .buttons button { padding:5px 14px; border-radius:6px; border:1px solid var(--line);
                    background:var(--card); cursor:pointer; font-size:.84rem; font-family:inherit; }
  .buttons .b-approve.on { background:var(--ok); color:#fff; border-color:var(--ok); }
  .buttons .b-rewrite.on { background:var(--fix); color:#fff; border-color:var(--fix); }
  .buttons .b-reject.on { background:var(--bad); color:#fff; border-color:var(--bad); }
  textarea.rw { width:100%; margin-top:6px; padding:6px 8px; border:1px solid var(--line);
                border-radius:6px; font-family:Consolas,monospace; font-size:.78rem; display:none;
                min-height:74px; }
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
  <h1>AIRI 추출 SFT 학습 데이터 검수 (__TOTAL__건)</h1>
  <p class="lead">각 카드의 <b>추출 항목</b>이 AIRI가 대화에서 뽑아내도록 배울 정답입니다 —
  근거 인용이 대화 원문에 실재하는지는 코드가 이미 검증했으니, 판단할 것은 <b>이걸 뽑는 게 맞는가</b>입니다.
  괜찮으면 <b>승인</b>, 항목을 고치고 싶으면 <b>수정</b>(현재 target JSON이 채워져 있으니 그 줄을 고쳐 쓰기 —
  evidence는 대화 원문의 정확한 부분 문자열이어야 하고 이름은 evidence 안에 있어야 합니다),
  통째로 빼려면 <b>거부</b>.
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
const SCENE_LABELS = __SCENE_LABELS__;
const QUEUE_SHA = '__QUEUE_SHA__';
const KEY = 'airi-extraction-review-__DATE__';
const BY_ID = {};
for (const record of RECORDS) BY_ID[record.id] = record;
let decisions = {};
try { decisions = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
let activeTab = 'all';

function save() { localStorage.setItem(KEY, JSON.stringify(decisions)); refresh(); }

function setDecision(id, kind) {
  const current = decisions[id] || {};
  if (current.kind === kind && kind !== 'rewrite') { delete decisions[id]; }
  else {
    // 수정은 현재 target에서 출발한다 — 스팬 JSON을 맨손으로 다시 쓰게 하지 않는다.
    const seed = kind === 'rewrite' ? (current.text || BY_ID[id].target) : (current.text || '');
    decisions[id] = { kind: kind, text: seed };
  }
  save(); render();
}
function setRewriteText(id, text) {
  decisions[id] = { kind: 'rewrite', text: text };
  save();
  updateRewriteFeedback(id);
}
function updateRewriteFeedback(id) {
  // 카드 전체를 다시 그리면 타이핑 중 커서 위치를 잃는다 — 오류 배지만 직접 갱신한다.
  const card = document.getElementById('card-' + id);
  const err = document.getElementById('rwerr-' + id);
  if (!card || !err) return;
  const check = validateRewriteTarget(decisions[id].text || '', BY_ID[id].turns);
  card.className = 'card' + (check.ok ? ' decided-rewrite' : ' invalid-rewrite');
  if (check.ok) { err.style.display = 'none'; err.textContent = ''; }
  else {
    err.style.display = 'block';
    err.textContent = '⚠ ' + check.reason + ' — 이 건은 미결정으로 취급됩니다(회신에 포함되지 않음)';
  }
}
function approveVisible() {
  for (const record of RECORDS) {
    if (activeTab !== 'all' && record.scene !== activeTab) continue;
    if (!decisions[record.id]) decisions[record.id] = { kind: 'approve', text: '' };
  }
  save(); render();
}
function tabCounts() {
  const counts = { all: RECORDS.length };
  for (const record of RECORDS) counts[record.scene] = (counts[record.scene] || 0) + 1;
  return counts;
}
function renderTabs() {
  const counts = tabCounts();
  const tabs = ['all'].concat(Object.keys(SCENE_LABELS));
  document.getElementById('tabs').innerHTML = tabs.map(tab =>
    `<button class="${tab === activeTab ? 'active' : ''}" onclick="activeTab='${tab}';render()">` +
    `${tab === 'all' ? '전체' : SCENE_LABELS[tab]} ${counts[tab] || 0}</button>`).join('');
}
function describeItem(item) {
  let head;
  if (item.kind === 'entity') head = `entity / ${item.subtype} · ${item.name}`;
  else if (item.kind === 'fact') head = `fact / ${item.subtype} · ${(item.subjectNames || []).join(', ')}`;
  else head = `relation / ${item.subtype} · ${item.sourceName} → ${item.targetName}`;
  return `<div class="item">
    <div class="head">[turn ${item.turnNumber}] ${escapeHtml(head)}</div>
    <div class="body">${escapeHtml(item.content)}</div>
    <div class="evid">근거 인용(evidence): “${escapeHtml(item.evidence)}”</div>
  </div>`;
}
function renderItems(record) {
  // target JSON 파싱 실패는 "추출 항목 없음(정답)" 과 다른 오류다 — 같은 문구로
  // 렌더하면 검수자가 데이터 결함을 정상 케이스로 오인한다 (Task 2 리뷰 Minor 1).
  let parsed;
  try { parsed = JSON.parse(record.target); }
  catch (e) {
    return `<div class="item err">⚠ target JSON 파싱 실패 — 데이터 오류(정답 아님, 개발자에게 보고할 것): ${escapeHtml(e.message)}</div>`;
  }
  const items = (parsed && Array.isArray(parsed.extracted)) ? parsed.extracted : [];
  if (!items.length) return `<div class="item none">추출 항목 없음 — 아무것도 뽑지 않는 것이 정답</div>`;
  return items.map(describeItem).join('');
}
// (a) 수정(rewrite) 입력 사전 검증 — 서버(파이썬) `parse_stage_a_span` 이 최종 SSoT다.
// 여기서는 그 게이트의 보수적 부분집합만 확인한다: JSON 파싱 가능·{"extracted":[...]}
// 형태·evidence 가 해당 record.turns 의 부분 문자열·이름 필드(name/subjectNames/
// sourceName/targetName)가 evidence 안에 포함. 통과해도 서버가 다시 전부 검증하며,
// 서버가 잡는 위반(스키마 세부 규칙 등)을 여기서 전부 재현하지는 않는다 — 목적은
// 흔한 실수를 왕복 없이 그 자리에서 잡아 재작업 비용을 줄이는 것이다.
function validateRewriteTarget(text, turnsText) {
  let parsed;
  try { parsed = JSON.parse(text); }
  catch (e) { return { ok: false, reason: 'JSON 파싱 실패: ' + e.message }; }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !Array.isArray(parsed.extracted)) {
    return { ok: false, reason: '{"extracted":[...]} 형태가 아니다' };
  }
  for (const item of parsed.extracted) {
    if (!item || typeof item !== 'object' || typeof item.evidence !== 'string' || !item.evidence) {
      return { ok: false, reason: '항목에 evidence 문자열이 없다' };
    }
    if (!turnsText.includes(item.evidence)) {
      return { ok: false, reason: `근거 인용이 원문에 없다: "${item.evidence}"` };
    }
    const names = [];
    if (typeof item.name === 'string') names.push(item.name);
    if (Array.isArray(item.subjectNames)) names.push(...item.subjectNames);
    if (typeof item.sourceName === 'string') names.push(item.sourceName);
    if (typeof item.targetName === 'string') names.push(item.targetName);
    for (const name of names) {
      if (!item.evidence.includes(name)) {
        return { ok: false, reason: `이름 "${name}" 이 근거 인용 안에 없다` };
      }
    }
  }
  return { ok: true };
}
function render() {
  renderTabs();
  const list = document.getElementById('list');
  list.innerHTML = RECORDS.filter(record => activeTab === 'all' || record.scene === activeTab)
    .map(record => {
      const decision = decisions[record.id] || {};
      const rewriteCheck = decision.kind === 'rewrite'
        ? validateRewriteTarget(decision.text || '', record.turns) : null;
      const invalidRewrite = !!(rewriteCheck && !rewriteCheck.ok);
      const cls = !decision.kind ? '' : (invalidRewrite ? ' invalid-rewrite' : ' decided-' + decision.kind);
      const rewriteShown = decision.kind === 'rewrite' ? 'style="display:block"' : '';
      const errShown = invalidRewrite ? 'style="display:block"' : 'style="display:none"';
      const errText = invalidRewrite
        ? '⚠ ' + escapeHtml(rewriteCheck.reason) + ' — 이 건은 미결정으로 취급됩니다(회신에 포함되지 않음)' : '';
      return `<div class="card${cls}" id="card-${record.id}">
        <div class="meta"><code>${record.id}</code> · ${SCENE_LABELS[record.scene]} · ${escapeHtml(record.character)}</div>
        <div class="turns">${escapeHtml(record.turns)}</div>
        <div class="items">${renderItems(record)}</div>
        <div class="buttons">
          <button class="b-approve ${decision.kind === 'approve' ? 'on' : ''}" onclick="setDecision('${record.id}','approve')">승인</button>
          <button class="b-rewrite ${decision.kind === 'rewrite' ? 'on' : ''}" onclick="setDecision('${record.id}','rewrite')">수정</button>
          <button class="b-reject ${decision.kind === 'reject' ? 'on' : ''}" onclick="setDecision('${record.id}','reject')">거부</button>
        </div>
        <textarea class="rw" ${rewriteShown} placeholder="수정 target JSON — 한 줄, {&quot;extracted&quot;:[…]} 형태"
          oninput="setRewriteText('${record.id}', this.value)">${escapeHtml(decision.text || '')}</textarea>
        <div class="rw-err" id="rwerr-${record.id}" ${errShown}>${errText}</div>
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
  const lines = [`[AIRI 추출 SFT 검수 회신 __DATE__ queue=${QUEUE_SHA}]`];
  let approved = 0; const rejected = []; const rewritten = []; const undecided = [];
  for (const record of RECORDS) {
    const decision = decisions[record.id];
    if (!decision) { undecided.push(record.id); continue; }
    if (decision.kind === 'approve') approved += 1;
    else if (decision.kind === 'reject') rejected.push(record.id);
    else if (decision.kind === 'rewrite') {
      // (a) 위반 시 이 건은 회신 텍스트에서 빠지고 미결정으로 취급된다 —
      // 서버가 fail-closed 로 전체 회신을 거부하는 것과 결과가 정합한다.
      const check = validateRewriteTarget(decision.text || '', record.turns);
      if (check.ok) rewritten.push(record.id + ' => ' + (decision.text || '').trim());
      else undecided.push(record.id);
    }
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

SCENE_LABELS = {
    "state_change": "상태 변화",
    "placeholder_add": "{{user}} 등록",
    "skip_chatter": "추출 없음",
    "trait_fact": "특성 fact",
    "moment_event": "사건 moment",
    "relation_pair": "관계",
}


def queue_digest(pending_path: Path) -> str:
    """Pending 큐 파일 내용의 sha256 단축(12자).

    apply_extraction_review_reply.py 의 동명 함수와 정의가 같아야 한다 — 폼이
    임베드한 값과 적용기가 재계산한 값이 같은 큐 스냅샷일 때만 일치한다(Minor 9).
    """
    return hashlib.sha256(pending_path.read_bytes()).hexdigest()[:12]


def build_form(pending_path: Path, date_label: str) -> str:
    records = []
    for line in pending_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        full = json.loads(line)
        records.append({"id": full["id"], "scene": full["scene"],
                        "character": full["character"], "turns": full["turns"],
                        "target": full["target"]})
    if not records:
        raise ValueError("pending queue is empty")
    unknown = {record["scene"] for record in records} - set(SCENE_LABELS)
    if unknown:
        raise ValueError(f"unlabelled scene in queue: {sorted(unknown)}")
    payload = json.dumps(records, ensure_ascii=False)
    return (PAGE
            .replace("__RECORDS__", payload)
            .replace("__SCENE_LABELS__", json.dumps(SCENE_LABELS, ensure_ascii=False))
            .replace("__TOTAL__", str(len(records)))
            .replace("__QUEUE_SHA__", queue_digest(pending_path))
            .replace("__DATE__", date_label))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="extraction pending queue review form builder")
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    args = parser.parse_args(argv)
    markup = build_form(args.pending, args.date_label)
    args.output.write_text(markup, encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "bytes": len(markup.encode("utf-8"))},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
