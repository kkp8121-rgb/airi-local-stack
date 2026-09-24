"""Train the live-turn contradiction judge: Qwen2.5-0.5B + LoRA + 1-logit head (P(reply contradicts the line)).

usage: python train_contradiction_judge.py SYNTHETIC.jsonl REAL_EVAL.jsonl OUT_DIR
Same recipe as train_system1.py (LoRA r16, 3 epochs, lr 2e-4, pos-weighted BCE). Train/validation split by
topic of the synthetic set (every 6th topic validates); the test split is the real broadcast eval set
({say, answer, contradiction}) from a story the synthetic topics exclude.
"""
import json
import math
import random
import sys
import time
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from sklearn.metrics import roc_auc_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

BACKBONE = r'C:\AIRI-Models\hf\Qwen2.5-0.5B'
MAX_LEN = 192
SEED = 20260924


def model_input(say: str, reply: str) -> str:
    """The exact text the judge is trained on; the serving side must build the same string."""
    return f'이번에 말할 내용: {say}\nAIRI의 답: {reply}'


def load(synthetic_path, real_path):
    rows = [json.loads(l) for l in Path(synthetic_path).read_text(encoding='utf-8').splitlines() if l.strip()]
    topics = sorted({r['topic'] for r in rows})
    val_topics = set(topics[::6])
    split = {'train': [r for r in rows if r['topic'] not in val_topics],
             'val': [r for r in rows if r['topic'] in val_topics]}
    real = [json.loads(l) for l in Path(real_path).read_text(encoding='utf-8').splitlines() if l.strip()]
    split['test'] = [{'say': r['say'], 'reply': r['answer'], 'label': int(r['contradiction'])} for r in real]
    return split


@torch.no_grad()
def predict(model, tok, rows, device, batch=64):
    model.eval()
    out = []
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        enc = tok([model_input(r['say'], r['reply']) for r in chunk], truncation=True,
                  max_length=MAX_LEN, padding=True, return_tensors='pt').to(device)
        out.extend(torch.sigmoid(model(**enc).logits.float().squeeze(-1)).tolist())
    return out


def metrics(probs, rows):
    labels = [int(r['label']) for r in rows]
    res = {'n': len(rows), 'positive_rate': round(sum(labels) / max(1, len(labels)), 4),
           'accuracy@0.5': round(sum((p >= 0.5) == bool(y) for p, y in zip(probs, labels)) / max(1, len(labels)), 4)}
    if 0 < sum(labels) < len(labels):
        res['auc'] = round(roc_auc_score(labels, probs), 4)
    return res


def main():
    synthetic_path, real_path, out_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(SEED)
    torch.manual_seed(SEED)
    split = load(synthetic_path, real_path)
    device = 'cuda'
    tok = AutoTokenizer.from_pretrained(BACKBONE)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForSequenceClassification.from_pretrained(BACKBONE, num_labels=1, torch_dtype=torch.bfloat16)
    base.config.pad_token_id = tok.pad_token_id
    cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type='SEQ_CLS',
                     target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'],
                     modules_to_save=['score'])
    model = get_peft_model(base, cfg).to(device)
    train = split['train']
    pos = sum(int(r['label']) for r in train)
    pos_weight = torch.tensor([(len(train) - pos) / max(pos, 1)], device=device)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=2e-4, weight_decay=0.0)
    # Batch 16 at MAX_LEN 192 pushed an 8 GB card (with the desktop's share) past its memory and ran
    # at a fraction of speed; 8 keeps the run on the GPU.
    epochs, batch = 3, 8
    steps_total = epochs * math.ceil(len(train) / batch)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: max(0.0, 1 - s / steps_total))
    history, t0, best_val, best_epoch = [], time.time(), None, None
    for epoch in range(1, epochs + 1):
        model.train()
        random.shuffle(train)
        running = 0.0
        for i in range(0, len(train), batch):
            chunk = train[i:i + batch]
            enc = tok([model_input(r['say'], r['reply']) for r in chunk], truncation=True,
                      max_length=MAX_LEN, padding=True, return_tensors='pt').to(device)
            y = torch.tensor([float(r['label']) for r in chunk], device=device)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(
                model(**enc).logits.float().squeeze(-1), y, pos_weight=pos_weight)
            if not torch.isfinite(loss):
                raise SystemExit('non-finite loss')
            loss.backward()
            opt.step(); sched.step(); opt.zero_grad()
            running += loss.item() * len(chunk)
        val_m = metrics(predict(model, tok, split['val'], device), split['val'])
        history.append({'epoch': epoch, 'train_loss': round(running / len(train), 4), 'val': val_m})
        print(json.dumps(history[-1], ensure_ascii=False), flush=True)
        if best_val is None or val_m.get('auc', 0) > best_val:
            best_val, best_epoch = val_m.get('auc', 0), epoch
            model.save_pretrained(out_dir / 'adapter')
            tok.save_pretrained(out_dir / 'adapter')
    del model
    torch.cuda.empty_cache()
    base2 = AutoModelForSequenceClassification.from_pretrained(BACKBONE, num_labels=1, torch_dtype=torch.bfloat16)
    base2.config.pad_token_id = tok.pad_token_id
    reloaded = PeftModel.from_pretrained(base2, out_dir / 'adapter').to(device)
    result = {'backbone': BACKBONE, 'best_epoch': best_epoch, 'history': history, 'train_n': len(train),
              'train_positive': pos, 'train_seconds': round(time.time() - t0, 1)}
    for name in ('val', 'test'):
        probs = predict(reloaded, tok, split[name], device)
        result[name] = metrics(probs, split[name])
        if name == 'test':
            with (out_dir / 'test-scores.jsonl').open('w', encoding='utf-8') as f:
                for r, p in zip(split['test'], probs):
                    f.write(json.dumps({**r, 'p_contradiction': round(p, 4)}, ensure_ascii=False) + '\n')
    sample = split['test'][:50]
    torch.cuda.synchronize()
    t = time.perf_counter()
    for r in sample:
        predict(reloaded, tok, [r], device, batch=1)
    torch.cuda.synchronize()
    result['latency_ms_per_candidate_gpu'] = round((time.perf_counter() - t) * 1000 / len(sample), 2)
    (out_dir / 'metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'history'}, ensure_ascii=False, indent=1))


main()
