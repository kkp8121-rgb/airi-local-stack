"""Extract viewer_reaction candidates from harness reports and label them.

usage: python label_candidates.py OUT.jsonl TEACHER_URL REPORT_ROOT [REPORT_ROOT ...]
  - deterministic labels always (chat copy run, question ending, length)
  - teacher labels via an OpenAI-compatible llama-server (json_schema, temperature 0), 4 concurrent requests
Output rows are response-bearing: keep them outside Git.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, r'C:\Projects\airi-local-stack\ollama-proxy\eval\broadcast_sim')
sys.path.insert(0, r'C:\Projects\airi-local-stack\ollama-proxy\eval\broadcast_chat')
import run_vod_storyline as vs  # noqa: E402

out_path = Path(sys.argv[1])
teacher = sys.argv[2].rstrip('/')
roots = [Path(p) for p in sys.argv[3:]]

sys.path.insert(0, str(Path(__file__).parent))
from teacher_prompt import SCHEMA, SYSTEM, accept_v2, user_prompt  # noqa: E402


def extract():
    rows = []
    for root in roots:
        report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
        for t in report['turns']:
            try:
                slots = json.loads(t.get('rewrite_raw') or '{}').get('slots', [])
            except ValueError:
                slots = []
            for s in slots:
                body = s.get('response_body') or ''
                if not (s.get('ok') and s.get('parse_ok') and body):
                    continue
                chat = vs.normalized_text(t['chat'])
                rows.append({
                    'run': root.name, 'turn': t['turn_index'], 'scene_id': t['scene_id'],
                    'scene_plot': t.get('scene_plot', ''), 'chat': chat, 'candidate': body,
                    'attempt': s.get('attempt'), 'selected_by_heuristic': bool(s.get('selected')),
                    'heuristic_score': s.get('candidate_score'),
                    'det_chat_run': vs.longest_common_run(body, chat),
                    'det_question': bool(re.search(r'[?？]\s*$', body)),
                    'det_len': len(body),
                })
    return rows


async def label(rows):
    sem = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=120) as client:
        async def one(row):
            async with sem:
                body = {
                    'messages': [{'role': 'system', 'content': SYSTEM},
                                 {'role': 'user', 'content': user_prompt(row)}],
                    'temperature': 0, 'max_tokens': 200, 'stop': ['<|eot_id|>', '<|im_end|>'],
                    'response_format': {'type': 'json_schema', 'json_schema': {'name': 'judge', 'schema': SCHEMA}},
                }
                for _ in range(2):
                    try:
                        r = await client.post(f'{teacher}/v1/chat/completions', json=body)
                        row['teacher'] = json.loads(r.json()['choices'][0]['message']['content'])
                        return
                    except Exception as exc:  # retry once, then record the failure
                        row['teacher_error'] = type(exc).__name__
        await asyncio.gather(*(one(r) for r in rows))


def main():
    rows = extract()
    print(f'candidates={len(rows)} from {len(roots)} runs', flush=True)
    if teacher != 'none':
        asyncio.run(label(rows))
    with out_path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    for r in rows:
        if 'teacher' in r:
            r['label'] = int(accept_v2(r['teacher'], r['candidate']) and r['det_chat_run'] < 8 and not r['det_question'])
    with out_path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    labelled = sum(1 for r in rows if 'teacher' in r)
    print(f'labelled={labelled} errors={sum(1 for r in rows if "teacher_error" in r and "teacher" not in r)}')


main()
