"""Loopback System1 judge service (evaluation only): POST /score {chat, candidate} -> {p, ms}.

Loads a sequence-classification backbone plus a trained LoRA adapter whose saved
modules include the 1-logit head.  Needs torch/transformers/peft, so it runs from a
separate training environment; nothing in the offline suite imports it.

usage: python system1_service.py --backbone DIR --adapter DIR [--device cuda|cpu] [--port 11510]
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

from system1_judge import model_input

MAX_LEN = 128


def load(backbone: str, adapter: str, device: str):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(adapter)
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    base = AutoModelForSequenceClassification.from_pretrained(backbone, num_labels=1, torch_dtype=dtype)
    base.config.pad_token_id = tokenizer.pad_token_id
    model = PeftModel.from_pretrained(base, adapter).to(device).eval()
    return torch, tokenizer, model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    parser.add_argument("--port", type=int, default=11510)
    args = parser.parse_args()
    torch, tokenizer, model = load(args.backbone, args.adapter, args.device)
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self._send(200, {"status": "ok", "device": args.device, "adapter": args.adapter})

        def do_POST(self) -> None:
            if self.path != "/score":
                self._send(404, {"error": "not found"})
                return
            try:
                request = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                text = model_input(str(request["chat"]), str(request["candidate"]))
            except (ValueError, KeyError):
                self._send(400, {"error": "expected JSON with chat and candidate"})
                return
            started = time.perf_counter()
            with lock, torch.no_grad():
                encoded = tokenizer([text], truncation=True, max_length=MAX_LEN, return_tensors="pt").to(args.device)
                probability = torch.sigmoid(model(**encoded).logits.float().squeeze()).item()
            self._send(200, {"p": probability, "ms": round((time.perf_counter() - started) * 1000, 2)})

        def log_message(self, *args) -> None:
            pass

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
