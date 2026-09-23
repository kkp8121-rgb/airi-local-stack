"""Train the System1 candidate judge: Qwen2.5-0.5B + LoRA + trainable 1-logit head (accept probability).

usage: python train_system1.py LABELS.jsonl OUT_DIR
Split by run: variant-01..10 train, variant-11..12 validation, everything else (the fixed 32-turn run) test.
Writes adapter + head, metrics.json (AUC, Brier, ECE, accuracy, per split), and verifies a reload.
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
MAX_LEN = 128
SEED = 20260923
TRAIN_RUNS = {f'variant-{i:02d}' for i in range(1, 11)}
VAL_RUNS = {'variant-11', 'variant-12'}


def model_input(chat: str, candidate: str) -> str:
    return f'채팅: {chat}\n반응: {candidate}'


def load(path):
    rows = [json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]
    rows = [r for r in rows if 'label' in r]
    split = {'train': [], 'val': [], 'test': []}
    for r in rows:
        key = 'train' if r['run'] in TRAIN_RUNS else 'val' if r['run'] in VAL_RUNS else 'test'
        split[key].append(r)
    return split


def ece(probs, labels, bins=10):
    total, err = len(probs), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if (lo <= p < hi) or (b == bins - 1 and p == 1.0)]
        if idx:
            conf = sum(probs[i] for i in idx) / len(idx)
            acc = sum(labels[i] for i in idx) / len(idx)
            err += len(idx) / total * abs(conf - acc)
    return round(err, 4)


@torch.no_grad()
def predict(model, tok, rows, device, batch=64):
    model.eval()
    out = []
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        enc = tok([model_input(r['chat'], r['candidate']) for r in chunk], truncation=True,
                  max_length=MAX_LEN, padding=True, return_tensors='pt').to(device)
        logits = model(**enc).logits.float().squeeze(-1)
        out.extend(torch.sigmoid(logits).tolist())
    return out


def metrics(probs, rows):
    labels = [int(r['label']) for r in rows]
    if not rows:
        return {}
    res = {'n': len(rows), 'positive_rate': round(sum(labels) / len(labels), 4),
           'accuracy@0.5': round(sum((p >= 0.5) == bool(y) for p, y in zip(probs, labels)) / len(labels), 4),
           'brier': round(sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(labels), 4),
           'ece': ece(probs, labels)}
    if 0 < sum(labels) < len(labels):
        res['auc'] = round(roc_auc_score(labels, probs), 4)
    return res


def main():
    labels_path, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(SEED)
    torch.manual_seed(SEED)
    split = load(labels_path)
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
    epochs, batch = 3, 16
    steps_total = epochs * math.ceil(len(train) / batch)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: max(0.0, 1 - s / steps_total))
    torch.cuda.reset_peak_memory_stats()
    history, t0 = [], time.time()
    best_val, best_epoch = None, None
    for epoch in range(1, epochs + 1):
        model.train()
        random.shuffle(train)
        running = 0.0
        for i in range(0, len(train), batch):
            chunk = train[i:i + batch]
            enc = tok([model_input(r['chat'], r['candidate']) for r in chunk], truncation=True,
                      max_length=MAX_LEN, padding=True, return_tensors='pt').to(device)
            y = torch.tensor([float(r['label']) for r in chunk], device=device)
            logits = model(**enc).logits.float().squeeze(-1)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, y, pos_weight=pos_weight)
            if not torch.isfinite(loss):
                raise SystemExit('non-finite loss')
            loss.backward()
            opt.step(); sched.step(); opt.zero_grad()
            running += loss.item() * len(chunk)
        val_probs = predict(model, tok, split['val'], device)
        val_m = metrics(val_probs, split['val'])
        history.append({'epoch': epoch, 'train_loss': round(running / len(train), 4), 'val': val_m})
        print(json.dumps(history[-1], ensure_ascii=False), flush=True)
        score = val_m.get('auc', 0)
        if best_val is None or score > best_val:
            best_val, best_epoch = score, epoch
            model.save_pretrained(out_dir / 'adapter')
            tok.save_pretrained(out_dir / 'adapter')
    peak = torch.cuda.max_memory_allocated() / 2 ** 20
    # reload check: base + saved adapter (must restore the trained head via modules_to_save)
    del model
    torch.cuda.empty_cache()
    base2 = AutoModelForSequenceClassification.from_pretrained(BACKBONE, num_labels=1, torch_dtype=torch.bfloat16)
    base2.config.pad_token_id = tok.pad_token_id
    reloaded = PeftModel.from_pretrained(base2, out_dir / 'adapter').to(device)
    result = {'backbone': BACKBONE, 'best_epoch': best_epoch, 'history': history,
              'train_n': len(train), 'train_positive': pos, 'peak_vram_mib': round(peak, 1),
              'train_seconds': round(time.time() - t0, 1)}
    for name in ('val', 'test'):
        probs = predict(reloaded, tok, split[name], device)
        result[name] = metrics(probs, split[name])
    # per-candidate latency, single request, GPU and CPU
    sample = (split['test'] or split['val'])[:50]
    torch.cuda.synchronize()
    t = time.perf_counter()
    for r in sample:
        predict(reloaded, tok, [r], device, batch=1)
    torch.cuda.synchronize()
    result['latency_ms_per_candidate_gpu'] = round((time.perf_counter() - t) * 1000 / len(sample), 2)
    cpu_model = reloaded.to('cpu').float()
    t = time.perf_counter()
    for r in sample[:20]:
        predict(cpu_model, tok, [r], 'cpu', batch=1)
    result['latency_ms_per_candidate_cpu'] = round((time.perf_counter() - t) * 1000 / min(20, len(sample)), 2)
    (out_dir / 'metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'history'}, ensure_ascii=False, indent=1))


main()
