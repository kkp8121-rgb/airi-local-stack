"""Teacher-judge the CHOSEN viewer_reaction of every turn in each run root.

usage: python eval_chosen.py TEACHER_URL OUT.jsonl RUN_ROOT [RUN_ROOT ...]
Prints one content-free line per run: accepted chosen reactions / turns with a reaction, plus flag counts.
"""
import asyncio
import collections
import json
import re
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\Projects\airi-local-stack\ollama-proxy\eval\broadcast_sim')
sys.path.insert(0, r'C:\Projects\airi-local-stack\ollama-proxy\eval\broadcast_chat')
import run_vod_storyline as vs  # noqa: E402
from teacher_prompt import SCHEMA, SYSTEM, accept_v2, user_prompt  # noqa: E402

teacher, out_path, roots = sys.argv[1].rstrip('/'), Path(sys.argv[2]), [Path(p) for p in sys.argv[3:]]
rows = []
for root in roots:
    report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
    for t in report['turns']:
        slots = json.loads(t.get('rewrite_raw') or '{}').get('slots', [])
        chosen = next((s for s in slots if s.get('selected')), None)
        if not chosen:
            continue
        body = chosen.get('response_body') or ''
        chat = vs.normalized_text(t['chat'])
        rows.append({'run': root.name, 'turn': t['turn_index'], 'scene_plot': t.get('scene_plot', ''),
                     'chat': chat, 'candidate': body, 'attempt': chosen.get('attempt'),
                     'system1_p': chosen.get('system1_p'),
                     'det_chat_run': vs.longest_common_run(body, chat),
                     'det_question': bool(re.search(r'[?？]\s*$', body))})


async def main():
    sem = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=120) as client:
        async def one(row):
            async with sem:
                body = {'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user_prompt(row)}],
                        'temperature': 0, 'max_tokens': 200, 'stop': ['<|eot_id|>', '<|im_end|>'],
                        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'judge', 'schema': SCHEMA}}}
                r = await client.post(f'{teacher}/v1/chat/completions', json=body)
                row['teacher'] = json.loads(r.json()['choices'][0]['message']['content'])
                row['label'] = int(accept_v2(row['teacher'], row['candidate']) and row['det_chat_run'] < 8 and not row['det_question'])
        await asyncio.gather(*(one(r) for r in rows))

asyncio.run(main())
out_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
by = collections.defaultdict(list)
for r in rows:
    by[r['run']].append(r)
for run, rs in by.items():
    flags = collections.Counter(k for r in rs for k, v in r['teacher'].items() if v and k not in ('specific_to_chat', 'natural_casual_korean'))
    print(json.dumps({'run': run, 'chosen': len(rs), 'accepted': sum(r['label'] for r in rs),
                      'specific': sum(r['teacher']['specific_to_chat'] for r in rs),
                      'defect_flags': dict(flags), 'question': sum(r['det_question'] for r in rs),
                      'copy8': sum(r['det_chat_run'] >= 8 for r in rs)}, ensure_ascii=False))
