"""Judge the chosen reaction of each run with the framing-neutral defect rubric.

usage: python eval_defects.py TEACHER_URL NAME OUT.jsonl RUN_ROOT [RUN_ROOT ...]
       python eval_defects.py TEACHER_URL NAME --gold      (score the rubric's gold set only)
Prints one content-free line per run (defect counts over 32 turns).
"""
import asyncio
import collections
import json
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\Projects\airi-local-stack\ollama-proxy\eval\broadcast_sim')
sys.path.insert(0, r'C:\Projects\airi-local-stack\ollama-proxy\eval\broadcast_chat')
import run_vod_storyline as vs  # noqa: E402
from defect_rubric import GOLD, SCHEMA, SYSTEM  # noqa: E402

url, name = sys.argv[1].rstrip('/'), sys.argv[2]


async def judge(client, chat, reaction):
    body = {'messages': [{'role': 'system', 'content': SYSTEM},
                         {'role': 'user', 'content': f'[시청자 채팅] {chat}\n[AIRI 반응 문장] {reaction}'}],
            'temperature': 0, 'max_tokens': 160, 'stop': ['<|eot_id|>', '<|im_end|>'],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'defects', 'schema': SCHEMA}}}
    r = await client.post(f'{url}/v1/chat/completions', json=body)
    return json.loads(r.json()['choices'][0]['message']['content'])


async def main():
    sem = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=120) as client:
        async def one(chat, reaction):
            async with sem:
                return await judge(client, chat, reaction)
        if sys.argv[3] == '--gold':
            outs = await asyncio.gather(*(one(c, r) for c, r, _ in GOLD))
            hits = total = 0
            for (c, r, want), got in zip(GOLD, outs):
                for k, v in want.items():
                    total += 1
                    hits += got[k] == v
                    if got[k] != v:
                        print(f'  miss {k} want={v} :: {r}')
            print(json.dumps({'judge': name, 'gold_items': f'{hits}/{total}'}))
            return
        out_path, roots = Path(sys.argv[3]), [Path(p) for p in sys.argv[4:]]
        rows = []
        for root in roots:
            report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
            for t in report['turns']:
                slots = json.loads(t.get('rewrite_raw') or '{}').get('slots', [])
                chosen = next((s for s in slots if s.get('selected')), None)
                if chosen:
                    rows.append({'run': root.name, 'turn': t['turn_index'], 'chat': vs.normalized_text(t['chat']),
                                 'reaction': chosen.get('response_body') or ''})
        verdicts = await asyncio.gather(*(one(r['chat'], r['reaction']) for r in rows))
        for r, v in zip(rows, verdicts):
            r['judge'] = name
            r['defects'] = v
        out_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
        by = collections.defaultdict(list)
        for r in rows:
            by[r['run']].append(r)
        for root in roots:
            rs = by.get(root.name, [])
            count = collections.Counter(k for r in rs for k, v in r['defects'].items() if v)
            print(json.dumps({'judge': name, 'run': root.name, 'turns_with_reaction': len(rs),
                              'role_reversal': count['role_reversal'], 'advice_to_viewer': count['advice_to_viewer'],
                              'asks_viewer': count['asks_viewer'], 'parrots_chat': count['parrots_chat'],
                              'specific_to_chat': count['specific_to_chat']}))

asyncio.run(main())
