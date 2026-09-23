"""Build storyline variants: same scenes/beats/spine, different real (pseudonymized) viewer chats per scene.

usage: python make_variants.py OUT_DIR N_VARIANTS [SEED]
Chats come from the scene's own time window, pass the runner's signature sanitizer, and never reuse
the fixed evaluation storyline's staged messages (those stay held out for the step-4 comparison).
"""
import json
import random
import re
import sys
from pathlib import Path

REPO = Path(r'C:\Projects\airi-local-stack\ollama-proxy\eval')
sys.path.insert(0, str(REPO / 'broadcast_sim'))
sys.path.insert(0, str(REPO / 'broadcast_chat'))
import run_vod_storyline as vs  # noqa: E402

out_dir = Path(sys.argv[1])
n_variants = int(sys.argv[2])
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20260923
out_dir.mkdir(parents=True, exist_ok=True)

story = json.loads(vs.DEFAULT_STORYLINE.read_text(encoding='utf-8'))
origin = int(story['source']['capture_start_ms'])
rows, _ = vs.sanitize_rows(vs.read_jsonl(vs.DEFAULT_CHAT))
held_out = {vs.normalized_text(m['text']) for s in story['scenes'] for m in s['audience_messages']}
HANGUL = re.compile(r'[가-힣]')


def usable(text: str) -> bool:
    t = vs.normalized_text(text)
    if not (6 <= len(t) <= 60) or t in held_out:
        return False
    if len(HANGUL.findall(t)) < 0.5 * len(t.replace(' ', '')):
        return False
    return 'http' not in t and '@' not in t


pools = {}
for scene in story['scenes']:
    lo, hi = origin + scene['start_ms'], origin + scene['end_ms']
    seen, pool = set(), []
    for r in rows:
        if r.get('kind', 'chat') != 'chat' or not (lo <= int(r['offset_ms']) < hi):
            continue
        t = vs.normalized_text(r['text'])
        if usable(t) and t not in seen:
            seen.add(t)
            pool.append({'author': r['author'], 'text': t})
    pools[scene['id']] = pool

rng = random.Random(seed)
per_scene = 4
report = {'seed': seed, 'variants': n_variants, 'pool_sizes': {k: len(v) for k, v in pools.items()}}
for i in range(1, n_variants + 1):
    variant = json.loads(json.dumps(story))
    variant['story_id'] = f"{story['story_id']}-variant-{i:02d}"
    for scene in variant['scenes']:
        pool = pools[scene['id']]
        picks = rng.sample(pool, per_scene) if len(pool) >= per_scene else pool[:per_scene]
        authors = set()
        chosen = []
        for p in picks:
            author = p['author'] if p['author'] not in authors else f"{p['author']}-{len(chosen)}"
            authors.add(author)
            chosen.append({'author': author, 'text': p['text']})
        scene['audience_messages'] = chosen
    (out_dir / f'variant-{i:02d}.json').write_text(json.dumps(variant, ensure_ascii=False, indent=1), encoding='utf-8')
(out_dir / 'variants-manifest.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
print(json.dumps(report))
