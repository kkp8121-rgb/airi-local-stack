"""Render a read-only behavior pending queue as a human-review HTML form."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PENDING = HERE / "seed" / "airi_behavior_seed_pending.jsonl"
DEFAULT_OUTPUT = HERE.parent.parent / "airi_docs" / "진행예정" / "AIRI-BEHAVIOR-REVIEW-FORM-2026-08-19.html"
BEHAVIOR_LABELS = {
    "fact_recall": "기억 활용", "addressee": "수신자", "register": "반말", "substance": "실질 응답",
    "neutral": "중립", "curious": "호기심", "amused": "재미", "pleased": "기쁨", "proud": "자부심",
    "embarrassed": "당황", "skeptical": "의심", "playful_annoyed": "장난스런 짜증", "concerned": "걱정",
    "disappointed": "실망", "competitive": "승부욕", "relieved": "안도", "tired": "피곤",
}
for _affect_behavior in ("neutral", "curious", "amused", "pleased", "proud", "embarrassed",
                         "skeptical", "playful_annoyed", "concerned", "disappointed",
                         "competitive", "relieved", "tired"):
    # Older pending snapshots spell these as ``affect_<primary>``.  Keep them
    # reviewable without changing the embedded record's canonical behavior.
    BEHAVIOR_LABELS.setdefault("affect_" + _affect_behavior,
                               BEHAVIOR_LABELS[_affect_behavior])


def queue_digest(pending_path: Path) -> str:
    """Return 12 SHA-256 hex characters for LF-normalized UTF-8 queue text."""
    text = pending_path.read_text(encoding="utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:12]


PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIRI 행동 SFT 검수 — __DATE__ (__TOTAL__건)</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --ink:#1c2330; --sub:#5b6472; --line:#e3e6ea; --accent:#3b6ef5; --ok:#1a7f4b; --bad:#c0392b; --fix:#b25e09; }
  * { box-sizing:border-box; } body { margin:0; padding:20px 14px 90px; background:var(--bg); color:var(--ink); font-family:'Segoe UI','Malgun Gothic',system-ui,sans-serif; line-height:1.5; }
  .wrap { max-width:820px; margin:0 auto; } h1 { font-size:1.2rem; margin:0 0 4px; } .lead { color:var(--sub); font-size:.85rem; margin-bottom:14px; }
  .tabs,.buttons { display:flex; gap:6px; flex-wrap:wrap; } .tabs { margin-bottom:12px; }
  .tabs button,.buttons button,.toolbar button { padding:6px 12px; border:1px solid var(--line); border-radius:8px; background:var(--card); cursor:pointer; font:inherit; }
  .tabs button.active,.toolbar .primary { background:var(--accent); color:#fff; border-color:var(--accent); }
  .card { background:var(--card); border:1px solid var(--line); border-left:4px solid var(--line); border-radius:8px; padding:10px 12px; margin-bottom:8px; }
  .card.decided-approve { border-left-color:var(--ok); } .card.decided-reject { border-left-color:var(--bad); opacity:.75; } .card.decided-rewrite { border-left-color:var(--fix); }
  .buttons .b-approve.on { background:var(--ok); color:#fff; border-color:var(--ok); }
  .buttons .b-rewrite.on { background:var(--fix); color:#fff; border-color:var(--fix); }
  .buttons .b-reject.on { background:var(--bad); color:#fff; border-color:var(--bad); }
  .meta,.affect-hints { font-size:.75rem; color:var(--sub); margin:4px 0; } .briefing { font-size:.78rem; color:var(--sub); background:var(--bg); border-radius:6px; padding:6px 8px; white-space:pre-wrap; }
  .qa { margin:4px 0; font-size:.9rem; } .qa b { color:var(--accent); } textarea.rw { width:100%; margin-top:6px; padding:6px 8px; display:none; }
  .toolbar { position:fixed; bottom:0; left:0; right:0; background:var(--card); border-top:1px solid var(--line); padding:10px 14px; display:flex; gap:8px; justify-content:center; flex-wrap:wrap; }
  #out { width:100%; max-width:820px; height:150px; margin:8px auto; display:none; font-family:Consolas,monospace; } .prog { color:var(--sub); }
</style></head><body>
<div class="wrap"><h1>AIRI 행동 SFT 학습 데이터 검수 (__TOTAL__건)</h1>
<p class="lead">각 카드의 <b>답변(A)</b>이 AIRI가 배울 정답입니다. 괜찮으면 <b>승인</b>, 고치려면 <b>수정</b>, 빼려면 <b>거부</b>. 선택은 자동 저장되고 회신은 <b>예외(거부·수정)만</b> 나열합니다. 이 폼은 대기열을 변경하지 않습니다.</p>
<div class="tabs" id="tabs"></div><div id="list"></div><textarea id="out" readonly></textarea></div>
<div class="toolbar"><span class="prog" id="prog"></span><button onclick="approveVisible()">현재 탭 미결정 전부 승인</button><button class="primary" onclick="buildResult()">회신 만들기</button><button onclick="copyResult()">복사</button><button onclick="resetAll()">초기화</button></div>
<script>
const RECORDS = __RECORDS__;
const QUEUE_SHA = '__QUEUE_SHA__';
const KEY = 'airi-behavior-review-__DATE__-' + QUEUE_SHA;
const BEHAVIOR_LABELS = __LABELS__;
let decisions = {};
try { decisions = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
let activeTab = 'all';
function save() { localStorage.setItem(KEY, JSON.stringify(decisions)); refresh(); }
function setDecision(id, kind) { const current = decisions[id] || {}; if (current.kind === kind && kind !== 'rewrite') delete decisions[id]; else decisions[id] = { kind:kind, text:current.text || '' }; save(); render(); }
function setRewriteText(id, text) { decisions[id] = { kind:'rewrite', text:text }; save(); }
function approveVisible() { for (const record of RECORDS) { if (activeTab !== 'all' && record.behavior !== activeTab) continue; if (!decisions[record.id]) decisions[record.id] = { kind:'approve', text:'' }; } save(); render(); }
function tabCounts() { const counts = { all:RECORDS.length }; for (const record of RECORDS) counts[record.behavior] = (counts[record.behavior] || 0) + 1; return counts; }
function renderTabs() { const counts = tabCounts(); const tabs = ['all'].concat(Object.keys(BEHAVIOR_LABELS).filter(tab => counts[tab])); document.getElementById('tabs').innerHTML = tabs.map(tab => `<button class="${tab === activeTab ? 'active' : ''}" onclick="activeTab='${tab}';render()">${tab === 'all' ? '전체' : BEHAVIOR_LABELS[tab]} ${counts[tab] || 0}</button>`).join(''); }
function escapeHtml(text) { return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function affectHints(record) { if (!record.affect_state) return ''; const state = record.affect_state; const hints = [`상태: ${state.primary}`, `원인: ${state.cause}`, `drive: ${state.drive}`, `안전: ${record.safety_class}`, `유머 목표: ${record.humor_target}`]; if (record.must_include_any && record.must_include_any.length) hints.push(`필수: ${record.must_include_any.join(' / ')}`); if (record.must_not_include && record.must_not_include.length) hints.push(`금지: ${record.must_not_include.join(' / ')}`); return `<div class="affect-hints">${escapeHtml(hints.join(' · '))}</div>`; }
function render() { renderTabs(); const list = document.getElementById('list'); list.innerHTML = RECORDS.filter(record => activeTab === 'all' || record.behavior === activeTab).map(record => { const decision = decisions[record.id] || {}; const cls = decision.kind ? ' decided-' + decision.kind : ''; const briefing = record.briefing ? `<div class="briefing">${escapeHtml(record.briefing)}</div>` : ''; const rewriteShown = decision.kind === 'rewrite' ? 'style="display:block"' : ''; return `<div class="card${cls}" id="card-${record.id}"><div class="meta"><code>${record.id}</code> · ${BEHAVIOR_LABELS[record.behavior]}</div>${briefing}${affectHints(record)}<div class="qa"><b>Q</b> ${escapeHtml(record.prompt)}</div><div class="qa"><b>A</b> ${escapeHtml(record.answer)}</div><div class="buttons"><button class="b-approve ${decision.kind === 'approve' ? 'on' : ''}" onclick="setDecision('${record.id}','approve')">승인</button><button class="b-rewrite ${decision.kind === 'rewrite' ? 'on' : ''}" onclick="setDecision('${record.id}','rewrite')">수정</button><button class="b-reject ${decision.kind === 'reject' ? 'on' : ''}" onclick="setDecision('${record.id}','reject')">거부</button></div><textarea class="rw" ${rewriteShown} placeholder="수정 답변 (반말)" oninput="setRewriteText('${record.id}', this.value)">${escapeHtml(decision.text || '')}</textarea></div>`; }).join(''); refresh(); }
function refresh() { document.getElementById('prog').textContent = `${Object.keys(decisions).length} / ${RECORDS.length} 결정`; }
function buildResult() { const lines = ['[AIRI 행동 SFT 검수 회신 __DATE__ queue=' + QUEUE_SHA + ']']; let approved = 0; const rejected = []; const rewritten = []; const undecided = []; for (const record of RECORDS) { const decision = decisions[record.id]; if (!decision) { undecided.push(record.id); continue; } if (decision.kind === 'approve') approved += 1; else if (decision.kind === 'reject') rejected.push(record.id); else if (decision.kind === 'rewrite') rewritten.push(record.id + ' => ' + (decision.text || '').trim()); } lines.push(`approved=${approved}/${RECORDS.length}`); if (rejected.length) lines.push('rejected=' + rejected.join(', ')); for (const entry of rewritten) lines.push('rewrite: ' + entry); if (undecided.length) lines.push(`(미결정 ${undecided.length}건: ${undecided.slice(0, 10).join(', ')}${undecided.length > 10 ? ' …' : ''})`); const out = document.getElementById('out'); out.style.display = 'block'; out.value = lines.join('\\n'); }
function copyResult() { const out = document.getElementById('out'); if (out.style.display === 'none' || !out.value) buildResult(); out.focus(); out.select(); try { navigator.clipboard.writeText(out.value); } catch (e) { document.execCommand('copy'); } }
function resetAll() { if (!confirm('모든 검수 결정을 지울까요?')) return; decisions = {}; localStorage.removeItem(KEY); document.getElementById('out').style.display = 'none'; render(); }
render();
</script></body></html>
"""


def build_form(pending_path: Path, date_label: str) -> str:
    records = []
    for line in pending_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        full = json.loads(line)
        if full["behavior"] not in BEHAVIOR_LABELS:
            raise ValueError(f"unknown behavior in pending queue: {full['behavior']!r}")
        entry = {key: full[key] for key in ("id", "behavior", "briefing", "prompt", "answer")}
        for key in ("affect_state", "safety_class", "humor_target", "must_include_any", "must_not_include"):
            if key in full:
                entry[key] = full[key]
        records.append(entry)
    if not records:
        raise ValueError("pending queue is empty")
    return (PAGE.replace("__RECORDS__", json.dumps(records, ensure_ascii=False))
            .replace("__LABELS__", json.dumps(BEHAVIOR_LABELS, ensure_ascii=False))
            .replace("__QUEUE_SHA__", queue_digest(pending_path))
            .replace("__TOTAL__", str(len(records))).replace("__DATE__", date_label))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="behavior pending queue review form builder")
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--date-label", default="2026-08-19")
    args = parser.parse_args(argv)
    markup = build_form(args.pending, args.date_label)
    args.output.write_text(markup, encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "bytes": len(markup.encode("utf-8"))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
