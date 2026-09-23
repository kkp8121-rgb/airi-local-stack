"""Deterministic counts over the chosen viewer_reaction of each run (content-free output).

usage: python count_patterns.py GROUP_ROOT_PREFIX [GROUP_ROOT_PREFIX ...]
Each prefix is expanded to <prefix>-r1..r3. Counts: advice-to-viewer pattern, second-person address,
knowledge-definition recitation, honorific ending, question ending, 8+ char chat copy.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, r'C:\Projects\airi-local-stack\ollama-proxy\eval\broadcast_sim')
sys.path.insert(0, r'C:\Projects\airi-local-stack\ollama-proxy\eval\broadcast_chat')
import run_vod_storyline as vs  # noqa: E402

SECOND = re.compile(r'(?<![가-힣])(?:너도|너는|너가|니가|너한테|너를|너의|네가|너\s|네\s(?:목|몸|몸이|목이|말))')
ADVICE = re.compile(r'(?:쉬어|조심해|무리하지|무리하진|아껴|챙겨|가\s*봐|해\s*봐|하는\s*게\s*(?:좋|어때|낫)|는\s*게\s*어때)')
DEFINITION = re.compile(r'(?:가리키는\s*말|을\s*뜻해|를\s*뜻해|뜻이야|의미해|라는\s*뜻|말이야\.?$|사탕이야|용어야|이란\s|란\s.*(?:이야|거야))')
HONOR = re.compile(r'(?:요|니다|세요)[.!?~…\s]*$')

for prefix in sys.argv[1:]:
    count, n = Counter(), 0
    for r in (1, 2, 3):
        root = Path(f'{prefix}-r{r}')
        report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
        for t in report['turns']:
            slots = json.loads(t.get('rewrite_raw') or '{}').get('slots', [])
            chosen = next((s for s in slots if s.get('selected')), None)
            if not chosen:
                continue
            body = chosen.get('response_body') or ''
            n += 1
            count['advice_pattern'] += bool(ADVICE.search(body))
            count['second_person'] += bool(SECOND.search(body))
            count['definition'] += bool(DEFINITION.search(body))
            count['honorific'] += bool(HONOR.search(body))
            count['question'] += bool(re.search(r'[?？]\s*$', body))
            count['copy8'] += vs.longest_common_run(body, vs.normalized_text(t['chat'])) >= 8
    print(json.dumps({'group': Path(prefix).name, 'reactions': n, **count}, ensure_ascii=False))
