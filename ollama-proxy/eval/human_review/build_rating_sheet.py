"""실제 대화 JSONL 을 사람이 채점하는 단일 HTML 평가지로 만든다.

외부 자산 없이 자기완결적이며, 대화 텍스트는 모두 ``textContent`` 로만 넣는다.
채점 상태는 브라우저 메모리에만 두고 JSON 내보내기/불러오기로 이어서 한다.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Sequence

SCHEMA_VERSION = "airi.human-rating.v1"
# (key, 라벨, 설명) — summarize_ratings.AXIS_KEYS 와 반드시 같은 순서/키를 쓴다.
AXES: tuple[tuple[str, str, str], ...] = (
    ("broadcast_likeness", "방송다움", "라이브 스트리머가 채팅에 말을 거는 느낌인가."),
    ("context_retention", "맥락 유지", "이번 턴의 채팅·앞선 맥락을 올바르게 쓰는가."),
    ("response_appropriateness", "반응 적절성", "시청자가 실제로 한 말에 답하거나 받아치는가."),
    ("style_rules", "말투 규칙", "반말·길이·리스트/이모지/영어 금지를 지키는가."),
    ("factuality", "사실성", "없는 사실·이름·감정을 지어내지 않는가."),
)
FLAGS: tuple[tuple[str, str], ...] = (
    ("critical_failure", "치명적 실패 (안전·치명적 오류)"),
    ("silence_or_filler", "침묵 폴백·무의미 대꾸"),
    ("invented_name", "없는 이름 지어냄"),
    ("polite_violation", "존댓말 위반 (자동 힌트, 수정 가능)"),
)
# run_broadcast_chat_ab.score_response 의 POLITE_END 와 같은 아이디어를 재현한 것.
# 그 모듈을 import 하지 않기 위해 의도적으로 복제했다(정보성 힌트 전용).
SENTENCE_SPLIT = re.compile(r"[.!?…。？！]+|\n+")
POLITE_END = re.compile(r"(요|죠|쥬|니다|십시오|나이다)\s*$")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
body { font-family: 'Malgun Gothic', system-ui, sans-serif; margin: 0 auto; max-width: 60rem;
       padding: 1rem 1.25rem 6rem; color: #1c1c1c; background: #fbfbfa; line-height: 1.55; }
h1 { font-size: 1.35rem; margin: 0 0 .5rem; }
#rubric { background: #fff; border: 1px solid #ddd; border-radius: .5rem; padding: .75rem 1rem; }
#rubric ul { margin: .4rem 0 0; padding-left: 1.1rem; }
#toolbar { position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: .75rem;
           align-items: center; background: #fbfbfa; border-bottom: 1px solid #ddd;
           padding: .6rem 0; margin: 1rem 0; }
.turn { background: #fff; border: 1px solid #ddd; border-radius: .5rem; padding: .8rem 1rem;
        margin-bottom: 1rem; }
.turn.rated { border-color: #7aa87a; }
.meta { font-size: .8rem; color: #666; margin-bottom: .5rem; }
.line { margin: .3rem 0; white-space: pre-wrap; word-break: break-word; }
.line b { color: #444; }
.axis { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin: .25rem 0; }
.axis .name { min-width: 8rem; font-weight: 600; }
.axis .hint { color: #777; font-size: .8rem; }
.flags { display: flex; flex-wrap: wrap; gap: .8rem; margin-top: .5rem; }
textarea { width: 100%; min-height: 3rem; margin-top: .4rem; font: inherit; }
button { font: inherit; padding: .3rem .7rem; }
</style>
</head>
<body>
<h1>__TITLE__</h1>
<section id="rubric">
<b>평가 기준 (1~5 정수, 5가 가장 좋음)</b>
__RUBRIC_HTML__
<p>플래그는 해당하면 체크한다. 존댓말 위반은 자동 힌트로 미리 체크될 수 있으며 직접 고칠 수 있다.</p>
</section>
<div id="toolbar">
<label>평가자 <input id="rater" type="text" value="__RATER__"></label>
<label><input id="only-unrated" type="checkbox"> 미평가만 보기</label>
<span id="progress"></span>
<button id="export-btn" type="button">JSON 내보내기</button>
<label>JSON 불러오기 <input id="import-input" type="file" accept="application/json,.json"></label>
</div>
<div id="turns"></div>
<script id="turn-data" type="application/json">__TURNS_JSON__</script>
<script id="axis-data" type="application/json">__AXES_JSON__</script>
<script id="flag-data" type="application/json">__FLAGS_JSON__</script>
<script>
var TURNS = JSON.parse(document.getElementById('turn-data').textContent)
var AXES = JSON.parse(document.getElementById('axis-data').textContent)
var FLAGS = JSON.parse(document.getElementById('flag-data').textContent)
var SCHEMA_VERSION = '__SCHEMA_VERSION__'
var STATE = {}

function keyOf (turn) {
  return turn.session_id + '\\u0000' + turn.turn_no
}

function stateOf (turn) {
  var key = keyOf(turn)
  if (!STATE[key]) {
    var flags = {}
    FLAGS.forEach(function (flag) { flags[flag[0]] = false })
    flags.polite_violation = !!turn.polite_hint
    STATE[key] = { scores: {}, flags: flags, comment: '' }
  }
  return STATE[key]
}

function hasAllScores (scores) {
  return AXES.every(function (axis) { return typeof scores[axis[0]] === 'number' })
}

function isRated (turn) {
  return hasAllScores(stateOf(turn).scores)
}

function updateProgress () {
  var done = TURNS.filter(isRated).length
  document.getElementById('progress').textContent = '진행 ' + done + ' / ' + TURNS.length
}

function makeLine (label, text) {
  var line = document.createElement('div')
  line.className = 'line'
  var tag = document.createElement('b')
  tag.textContent = label + ' '
  line.appendChild(tag)
  var body = document.createElement('span')
  body.textContent = text
  line.appendChild(body)
  return line
}

function makeAxis (turn, axis) {
  var state = stateOf(turn)
  var row = document.createElement('div')
  row.className = 'axis'
  var name = document.createElement('span')
  name.className = 'name'
  name.textContent = axis[1]
  row.appendChild(name)
  for (var value = 1; value <= 5; value += 1) {
    var label = document.createElement('label')
    var input = document.createElement('input')
    input.type = 'radio'
    input.name = keyOf(turn) + ':' + axis[0]
    input.value = String(value)
    input.checked = state.scores[axis[0]] === value
    input.addEventListener('change', function (event) {
      state.scores[axis[0]] = parseInt(event.target.value, 10)
      render()
    })
    label.appendChild(input)
    var text = document.createElement('span')
    text.textContent = ' ' + value + ' '
    label.appendChild(text)
    row.appendChild(label)
  }
  var hint = document.createElement('span')
  hint.className = 'hint'
  hint.textContent = axis[2]
  row.appendChild(hint)
  return row
}

function makeFlags (turn) {
  var state = stateOf(turn)
  var box = document.createElement('div')
  box.className = 'flags'
  FLAGS.forEach(function (flag) {
    var label = document.createElement('label')
    var input = document.createElement('input')
    input.type = 'checkbox'
    input.checked = !!state.flags[flag[0]]
    input.addEventListener('change', function (event) {
      state.flags[flag[0]] = event.target.checked
    })
    label.appendChild(input)
    var text = document.createElement('span')
    text.textContent = ' ' + flag[1]
    label.appendChild(text)
    box.appendChild(label)
  })
  return box
}

function makeCard (turn) {
  var state = stateOf(turn)
  var card = document.createElement('div')
  card.className = isRated(turn) ? 'turn rated' : 'turn'
  var meta = document.createElement('div')
  meta.className = 'meta'
  meta.textContent = 'session ' + turn.session_id + ' / turn ' + turn.turn_no
  card.appendChild(meta)
  card.appendChild(makeLine('시청자', turn.user))
  card.appendChild(makeLine('AIRI', turn.assistant))
  AXES.forEach(function (axis) { card.appendChild(makeAxis(turn, axis)) })
  card.appendChild(makeFlags(turn))
  var comment = document.createElement('textarea')
  comment.placeholder = '코멘트 (선택)'
  comment.value = state.comment
  comment.addEventListener('input', function (event) { state.comment = event.target.value })
  card.appendChild(comment)
  return card
}

function render () {
  var onlyUnrated = document.getElementById('only-unrated').checked
  var host = document.getElementById('turns')
  host.textContent = ''
  TURNS.filter(function (turn) { return !onlyUnrated || !isRated(turn) })
    .forEach(function (turn) { host.appendChild(makeCard(turn)) })
  updateProgress()
}

function buildRatings () {
  var records = []
  TURNS.forEach(function (turn) {
    var state = stateOf(turn)
    if (!hasAllScores(state.scores)) { return }
    records.push({
      session_id: turn.session_id,
      turn_no: turn.turn_no,
      scores: state.scores,
      flags: state.flags,
      comment: state.comment
    })
  })
  return {
    schema_version: SCHEMA_VERSION,
    rater: document.getElementById('rater').value,
    created_at: new Date().toISOString(),
    turns: records
  }
}

function exportRatings () {
  var payload = JSON.stringify(buildRatings(), null, 2)
  var blob = new Blob([payload], { type: 'application/json' })
  var url = URL.createObjectURL(blob)
  var link = document.createElement('a')
  link.href = url
  link.download = 'airi-human-rating.json'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function applyLoaded (loaded) {
  if (loaded.rater) { document.getElementById('rater').value = loaded.rater }
  var records = loaded.turns || []
  records.forEach(function (record) {
    var key = record.session_id + '\\u0000' + record.turn_no
    STATE[key] = {
      scores: record.scores || {},
      flags: record.flags || {},
      comment: record.comment || ''
    }
  })
  render()
}

function importRatings (event) {
  var file = event.target.files && event.target.files[0]
  if (!file) { return }
  var reader = new FileReader()
  reader.onload = function () { applyLoaded(JSON.parse(String(reader.result))) }
  reader.readAsText(file, 'utf-8')
}

document.getElementById('export-btn').addEventListener('click', exportRatings)
document.getElementById('import-input').addEventListener('change', importRatings)
document.getElementById('only-unrated').addEventListener('change', render)
render()
</script>
</body>
</html>
"""


def has_polite_ending(text: str) -> bool:
    """존댓말 종결 힌트. 정보성 사전 체크일 뿐 판정이 아니다."""
    parts = [part.strip() for part in SENTENCE_SPLIT.split(text or "")]
    return any(POLITE_END.search(part) for part in parts if part)


def load_turns(input_path: Path) -> list[dict]:
    """내보내기 JSONL 을 읽어 평가지에 넣을 turn 목록을 만든다."""
    turns: list[dict] = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            missing = [
                key for key in ("session_id", "turn_no", "user", "assistant") if key not in record
            ]
            if missing:
                raise ValueError(f"line {line_no}: missing keys {missing}")
            turns.append(
                {
                    "session_id": str(record["session_id"]),
                    "turn_no": int(record["turn_no"]),
                    "user": str(record["user"]),
                    "assistant": str(record["assistant"]),
                    "polite_hint": has_polite_ending(str(record["assistant"])),
                }
            )
    return turns


def embed_json(payload: object) -> str:
    """``</script>`` 같은 조기 종료를 막기 위해 꺾쇠와 앰퍼샌드를 이스케이프한다."""
    return (
        json.dumps(payload, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_rubric() -> str:
    items = "".join(
        f"<li><b>{html.escape(label)}</b> — {html.escape(hint)}</li>" for _key, label, hint in AXES
    )
    return f"<ul>{items}</ul>"


def build_html(turns: list[dict], title: str, rater: str) -> str:
    return (
        HTML_TEMPLATE.replace("__TITLE__", html.escape(title))
        .replace("__RATER__", html.escape(rater, quote=True))
        .replace("__RUBRIC_HTML__", render_rubric())
        .replace("__TURNS_JSON__", embed_json(turns))
        .replace("__AXES_JSON__", embed_json([list(axis) for axis in AXES]))
        .replace("__FLAGS_JSON__", embed_json([list(flag) for flag in FLAGS]))
        .replace("__SCHEMA_VERSION__", SCHEMA_VERSION)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="실제 대화 JSONL 로 사람 평가용 HTML 평가지를 만든다.",
    )
    parser.add_argument("--input", required=True, help="export_session_dialogue.py 가 만든 JSONL.")
    parser.add_argument("--output", required=True, help="출력 HTML 경로.")
    parser.add_argument("--title", default="AIRI 실제 대화 사람 평가", help="평가지 제목.")
    parser.add_argument("--rater", default="", help="평가자 이름 기본값.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"error: input not found: {input_path}", file=sys.stderr)
        return 1
    try:
        turns = load_turns(input_path)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: invalid input JSONL: {exc}", file=sys.stderr)
        return 1
    if not turns:
        print("error: input contains no turns", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(build_html(turns, args.title, args.rater))
    print(f"turns={len(turns)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
