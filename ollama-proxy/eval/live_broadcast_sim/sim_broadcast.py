"""Turn-by-turn live broadcast simulator: a person or an agent plays the viewers and the showrunner.

AIRI runs through the real live-broadcast path of a running proxy (-LiveBroadcast): control start,
issue_turn with a broadcast_context, the chat through /v1/chat/completions streamed like the AIRI app's
provider, the renderer receipt, close. Each viewer chat is written after reading AIRI's previous answer,
and the history accumulates the way the app keeps it. Used for the 2026-09-23/24 live tuning shows.

usage:
  python sim_broadcast.py ROOT init [--show ID]        # new tokens in ROOT/secrets.json (never printed)
  python sim_broadcast.py ROOT start | close
  python sim_broadcast.py ROOT turn --chat TEXT [--turn-type selected_chat] [--topic T] [--segment S]
                                    [--situation S] [--briefing-text TEXT | --briefing-file F]
  python sim_broadcast.py ROOT replay --source SHOW_ROOT --contexts CONTEXTS.json [--capture CAPTURE.jsonl]
The proxy must be started with ROOT/secrets.json's tokens. turn appends ROOT/turns.jsonl (response-bearing:
keep ROOT outside Git). replay re-asks every turn of SHOW_ROOT/turns.jsonl with that show's own earlier
turns as history (forced history), so variants of the stack can be compared on the same conversation.
"""
import argparse
import hashlib
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER  # noqa: E402

BASE = 'http://127.0.0.1:11435'
MODEL = 'midm-airi:2.0-mini'
CHAT_PREFIX = '[YouTube] '
ACT_MARKER = re.compile(r'<\|ACT [^|]*\|>')


def receipt_answer(raw: str, ack_mode: str | None) -> str:
    """The receipt binds to the public answer minus the one ACT marker the x-airi-immediate-ack header attests."""
    if ack_mode == 'marker':
        match = ACT_MARKER.match(raw)
        if match:
            raw = raw[match.end():]
    return raw.strip()


def briefing(text: str) -> str:
    return BROADCAST_BRIEFING_HEADER + '\n' + text.strip() if text.strip() else ''


def broadcast_context(topic: str, segment: str, situation: str, briefing_text: str) -> dict:
    return {'schema_version': 1, 'topic_title': topic, 'segment_label': segment, 'situation': situation,
            'briefing': briefing(briefing_text), 'donation_continuation': False}


def forced_history(rows: list[dict], index: int) -> list[dict]:
    """The conversation before rows[index], as the app would send it."""
    history = []
    for prior in rows[:index]:
        history += [{'role': 'user', 'content': CHAT_PREFIX + prior['chat']},
                    {'role': 'assistant', 'content': prior['answer']}]
    return history


def post(url, payload, headers):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST',
                                 headers={'Content-Type': 'application/json; charset=utf-8', **headers})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8') or '{}')


def post_chat(messages, headers):
    """Stream the chat like the app's /v1 provider; returns status, answer, marker ms, dialogue ms, raw."""
    body = json.dumps({'model': MODEL, 'messages': messages, 'stream': True}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(f'{BASE}/v1/chat/completions', data=body, method='POST',
                                 headers={'Content-Type': 'application/json; charset=utf-8', **headers})
    started, marker_ms, dialogue_ms, chunks = time.perf_counter(), None, None, []
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            mode = r.headers.get('x-airi-immediate-ack')
            for raw_line in r:
                line = raw_line.decode('utf-8').strip()
                if not line.startswith('data:') or line[5:].strip() == '[DONE]':
                    continue
                for choice in json.loads(line[5:].strip()).get('choices') or []:
                    piece = (choice.get('delta') or {}).get('content')
                    if not piece:
                        continue
                    elapsed = round((time.perf_counter() - started) * 1000)
                    marker_ms = elapsed if marker_ms is None else marker_ms
                    chunks.append(piece)
                    if dialogue_ms is None and ACT_MARKER.sub('', ''.join(chunks)).strip():
                        dialogue_ms = elapsed
            raw = ''.join(chunks)
            return r.status, receipt_answer(raw, mode), marker_ms, dialogue_ms, raw
    except urllib.error.HTTPError as e:
        return e.code, '', None, None, ''


def run_turn(sec, show, action, turn_type, context, history, chat):
    """issue_turn, stream the chat, send the renderer receipt; returns a result row."""
    master = {'x-airi-broadcast-master-token': sec['master']}
    status, issued = post(f'{BASE}/v1/airi/broadcast/control',
                          {'action': 'issue_turn', 'show_id': show, 'action_id': action, 'turn_type': turn_type,
                           'required_delivery': 'renderer', 'broadcast_context': context}, master)
    if status != 200 or 'turn_token' not in issued:
        raise SystemExit(f"issue_turn failed {status} {({k: v for k, v in issued.items() if 'token' not in k})}")
    user = CHAT_PREFIX + (chat or '(채팅 없음)')
    trace = f'{show}-{action}'
    started = time.perf_counter()
    status, answer, marker_ms, dialogue_ms, raw = post_chat(
        history + [{'role': 'user', 'content': user}],
        {'x-airi-broadcast-turn-token': issued['turn_token'], 'x-airi-request-id': trace, 'x-airi-session-id': show})
    elapsed = round((time.perf_counter() - started) * 1000)
    answer = answer if status == 200 else ''
    sha = lambda s: hashlib.sha256(s.encode('utf-8')).hexdigest()
    receipt = None
    if answer:
        for _ in range(8):
            receipt, _ = post(f'{BASE}/v1/airi/broadcast/receipt',
                              {'delivery_token': issued['delivery_token'], 'delivery_status': 'delivered',
                               'required_delivery': 'renderer', 'trace_id': trace, 'query_sha256': sha(user),
                               'user_sha256': sha(user), 'answer_sha256': sha(answer)},
                              {'x-airi-broadcast-observer-token': sec['observer']})
            if receipt != 202:
                break
            time.sleep(0.05)
    return {'user': user, 'answer': answer, 'status': status, 'receipt': receipt, 'ms': elapsed,
            'marker_ms': marker_ms, 'dialogue_ms': dialogue_ms, 'raw': raw}


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    ap.add_argument('cmd', choices=('init', 'start', 'turn', 'close', 'replay'))
    ap.add_argument('--chat', default='')
    ap.add_argument('--turn-type', default='selected_chat')
    ap.add_argument('--topic')
    ap.add_argument('--segment')
    ap.add_argument('--situation')
    ap.add_argument('--briefing-file', type=Path)
    ap.add_argument('--briefing-text', default='')
    ap.add_argument('--show', default='airi-first-show')
    ap.add_argument('--source', type=Path, help='replay: show root whose turns.jsonl is replayed')
    ap.add_argument('--contexts', type=Path, help='replay: JSON {segment: {topic_title, situation}}')
    ap.add_argument('--capture', type=Path, help='replay: optional upstream capture file to index per turn')
    a = ap.parse_args()
    root = a.root
    root.mkdir(parents=True, exist_ok=True)
    sec_p, st_p, hist_p = root / 'secrets.json', root / 'state.json', root / 'history.json'
    if a.cmd == 'init':
        save(sec_p, {'master': secrets.token_urlsafe(48), 'observer': secrets.token_urlsafe(48)})
        save(st_p, {'show': a.show, 'turn': 0, 'context': None})
        save(hist_p, [])
        print('initialized', root)
        return
    sec, st = load(sec_p, None), load(st_p, None)
    if a.cmd in ('start', 'close'):
        status, body = post(f'{BASE}/v1/airi/broadcast/control', {'action': a.cmd, 'show_id': st['show']},
                            {'x-airi-broadcast-master-token': sec['master']})
        print(a.cmd, status, json.dumps({k: v for k, v in body.items() if 'token' not in k}, ensure_ascii=False))
        return
    if a.cmd == 'replay':
        rows = [json.loads(l) for l in (a.source / 'turns.jsonl').read_text(encoding='utf-8').splitlines()]
        contexts = json.loads(a.contexts.read_text(encoding='utf-8-sig'))
        count = lambda: len(a.capture.read_text(encoding='utf-8').splitlines()) if a.capture and a.capture.exists() else 0
        with (root / 'replay.jsonl').open('a', encoding='utf-8') as out:
            for index, row in enumerate(rows):
                seg = contexts[row['segment']]
                before = count()
                result = run_turn(sec, st['show'], f"r{row['turn']:03d}", row['turn_type'],
                                  broadcast_context(seg['topic_title'], row['segment'], seg['situation'], row['briefing']),
                                  forced_history(rows, index), row['chat'])
                out.write(json.dumps({'turn': row['turn'], 'capture_from': before, 'capture_to': count(),
                                      **{k: result[k] for k in ('answer', 'status', 'receipt', 'ms', 'dialogue_ms')}},
                                     ensure_ascii=False) + '\n')
                out.flush()
                print(f"R{row['turn']:02d} {result['ms']} ms status={result['status']} receipt={result['receipt']}")
        return
    ctx = st.get('context') or {}
    for key, value in (('topic_title', a.topic), ('segment_label', a.segment), ('situation', a.situation)):
        if value:
            ctx[key] = value
    text = a.briefing_file.read_text(encoding='utf-8') if a.briefing_file else a.briefing_text
    st['context'] = ctx
    st['turn'] += 1
    history = load(hist_p, [])
    result = run_turn(sec, st['show'], f"t{st['turn']:03d}", a.turn_type,
                      broadcast_context(ctx['topic_title'], ctx['segment_label'], ctx['situation'], text), history, a.chat)
    if result['answer']:
        save(hist_p, history + [{'role': 'user', 'content': result['user']}, {'role': 'assistant', 'content': result['answer']}])
    save(st_p, st)
    with (root / 'turns.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps({'turn': st['turn'], 'turn_type': a.turn_type, 'segment': ctx['segment_label'], 'chat': a.chat,
                            'briefing': text.strip(), **{k: v for k, v in result.items() if k != 'user'}},
                           ensure_ascii=False) + '\n')
    print(f"T{st['turn']:02d} [{a.turn_type}] {result['ms']} ms (marker {result['marker_ms']} ms, dialogue "
          f"{result['dialogue_ms']} ms) status={result['status']} receipt={result['receipt']}")
    print('AIRI:', result['answer'])


if __name__ == '__main__':
    main()
