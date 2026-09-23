"""Score a teacher endpoint on the AI-authored gold set. usage: python teacher_gold_check.py URL NAME"""
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from teacher_prompt import SCHEMA, SYSTEM, accept_v2, user_prompt  # noqa: E402

url, name = sys.argv[1].rstrip('/'), sys.argv[2]
gold = [json.loads(l) for l in (Path(__file__).parent / 'teacher_gold.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
item_hits = item_total = accept_hits = 0
misses = []
for row in gold:
    body = {'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user_prompt(row)}],
            'temperature': 0, 'max_tokens': 200, 'stop': ['<|eot_id|>', '<|im_end|>'],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'judge', 'schema': SCHEMA}}}
    out = json.loads(httpx.post(f'{url}/v1/chat/completions', json=body, timeout=120).json()['choices'][0]['message']['content'])
    for key, want in row['gold'].items():
        if key == 'accept':
            continue
        item_total += 1
        item_hits += out[key] == want
        if out[key] != want:
            misses.append(f"{key} want={want} :: {row['candidate']}")
    accept_hits += accept_v2(out, row['candidate']) == row['gold']['accept']
    if accept_v2(out, row['candidate']) != row['gold']['accept']:
        misses.append(f"ACCEPT want={row['gold']['accept']} got flags={[k for k,v in out.items() if v]} :: {row['candidate']}")
print(json.dumps({'teacher': name, 'items': f'{item_hits}/{item_total}', 'accept': f'{accept_hits}/{len(gold)}'}, ensure_ascii=False))
for m in misses:
    print('  miss', m)
