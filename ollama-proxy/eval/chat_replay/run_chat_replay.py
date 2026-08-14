#!/usr/bin/env python3
"""CLI for local, consent-bound replay; it performs no network request by default."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from chat_replay import import_private_replay, run_replay


HERE = Path(__file__).resolve().parent
PROXY_PORT = 11435
PROXY_CHAT_PATH = "/v1/chat/completions"
EVAL_TEMPERATURE = 0
EVAL_SEED = 42
EVAL_NUM_CTX = 2048
EVAL_MAX_TOKENS = 128
EVAL_MODEL = "midm-airi:2.0-mini"
EVAL_MODEL_DIGEST = "92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f"
MODEL_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


def _is_reparse(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _secure_inside(path: Path, parent: Path) -> bool:
    candidate = Path(os.path.abspath(path))
    trusted_parent = Path(os.path.abspath(parent))
    trusted_root = Path(os.path.abspath(HERE))
    try:
        candidate.relative_to(trusted_parent)
        relative = candidate.relative_to(trusted_root)
    except ValueError:
        return False
    current = trusted_root
    if _is_reparse(current):
        return False
    for part in relative.parts:
        current /= part
        if os.path.lexists(current) and _is_reparse(current):
            return False
    return True


def _write_atomic(path: Path, value: object, parent: Path) -> None:
    if not _secure_inside(path, parent):
        raise RuntimeError("output path escaped its local ignored directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _secure_inside(path, parent):
        raise RuntimeError("output path became unsafe")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    try:
        if not _secure_inside(path, parent):
            raise RuntimeError("output path became unsafe")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validated_proxy_url(url: str):
    parsed = urlsplit(url)
    try:
        loopback = bool(parsed.hostname) and ipaddress.ip_address(parsed.hostname).is_loopback
        port = parsed.port
    except ValueError as exc:
        raise ValueError("--loopback-url must use a literal loopback http address") from exc
    if (
        parsed.scheme != "http"
        or not loopback
        or port != PROXY_PORT
        or parsed.path.rstrip("/") != PROXY_CHAT_PATH
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "--loopback-url must be the local AIRI proxy "
            f"http://<literal-loopback>:{PROXY_PORT}{PROXY_CHAT_PATH}"
        )
    return parsed


def verify_loopback_health(
    url: str, model: str, *, expected_epistemic_enabled: bool = True,
) -> dict[str, object]:
    parsed = _validated_proxy_url(url)
    if model != EVAL_MODEL:
        raise RuntimeError(f"--model must match the frozen replay model {EVAL_MODEL}")
    health_url = urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))
    with urlopen(Request(health_url, method="GET"), timeout=5) as response:
        if response.status >= 400:
            raise RuntimeError(f"local AIRI proxy health returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise RuntimeError("local AIRI proxy health is not ready")
    if type(payload.get("num_ctx")) is not int or payload["num_ctx"] != EVAL_NUM_CTX:
        raise RuntimeError(f"local AIRI proxy num_ctx must be {EVAL_NUM_CTX}")
    chat_model = payload.get("chat_model")
    if not isinstance(chat_model, dict) or chat_model.get("model") != model:
        raise RuntimeError("local AIRI proxy chat model differs from --model")
    digest_state = chat_model.get("digest")
    digest = digest_state.get("digest") if isinstance(digest_state, dict) else None
    digest_status = digest_state.get("status") if isinstance(digest_state, dict) else None
    if (
        not isinstance(digest, str)
        or MODEL_DIGEST_RE.fullmatch(digest) is None
        or digest != EVAL_MODEL_DIGEST
        or digest_status != "pinned"
        or digest_state.get("verified") is not True
    ):
        raise RuntimeError("local AIRI proxy model digest is not the frozen verified pin")
    epistemic = payload.get("epistemic_confidence")
    if (
        not isinstance(epistemic, dict)
        or epistemic.get("enabled") is not expected_epistemic_enabled
    ):
        expected = "on" if expected_epistemic_enabled else "off"
        raise RuntimeError(f"local AIRI proxy epistemic-confidence gate must be {expected}")
    return {
        "model": model,
        "model_digest": digest,
        "model_digest_status": digest_status,
        "num_ctx": EVAL_NUM_CTX,
        "temperature": EVAL_TEMPERATURE,
        "seed": EVAL_SEED,
        "max_tokens": EVAL_MAX_TOKENS,
        "epistemic_confidence_enabled": expected_epistemic_enabled,
    }


def loopback_responder(
    url: str,
    model: str,
    *,
    history_turns: int = 8,
    attest: Callable[[], dict[str, object]] | None = None,
):
    _validated_proxy_url(url)
    if model != EVAL_MODEL:
        raise ValueError(f"--model must match the frozen replay model {EVAL_MODEL}")
    if not 1 <= history_turns <= 32:
        raise ValueError("--history-turns must be between 1 and 32")
    history: list[dict[str, str]] = []

    def respond(text, _event):
        before_profile = attest() if attest is not None else None
        messages = [*history, {"role": "user", "content": text}]
        request = Request(
            url,
            data=json.dumps({
                "model": model,
                "messages": messages,
                "stream": False,
                "temperature": EVAL_TEMPERATURE,
                "seed": EVAL_SEED,
                "max_tokens": EVAL_MAX_TOKENS,
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-AIRI-Turn-Origin": "local-evaluation"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:  # explicit opt-in only
            if response.status >= 400:
                raise RuntimeError(f"loopback model returned HTTP {response.status}")
            body = json.loads(response.read().decode("utf-8"))
        choices = body.get("choices") if isinstance(body, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        result = message.get("content") if isinstance(message, dict) else None
        if not isinstance(result, str):
            native_message = body.get("message") if isinstance(body, dict) else None
            result = native_message.get("content") if isinstance(native_message, dict) else body.get("text") if isinstance(body, dict) else None
        if not isinstance(result, str):
            raise RuntimeError("loopback model response has no assistant text")
        after_profile = attest() if attest is not None else None
        if before_profile != after_profile:
            raise RuntimeError("local AIRI proxy profile changed during a replay turn")
        history.extend(({"role": "user", "content": text}, {"role": "assistant", "content": result}))
        del history[:-2 * history_turns]
        return result
    return respond


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--consent", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--loopback-url", help="explicit local-model opt-in; default makes no request")
    parser.add_argument("--model", help="model name used only with --loopback-url")
    parser.add_argument("--history-turns", type=int, default=8)
    parser.add_argument(
        "--expected-epistemic-confidence", choices=("on", "off"), default="on",
        help="assert the gate state without changing it (default: on)",
    )
    parser.add_argument("--private-review-output", type=Path, help="explicit ignored local input/response review packet")
    args = parser.parse_args()
    if bool(args.loopback_url) != bool(args.model):
        parser.error("--loopback-url and --model must be supplied together")
    if args.private_review_output and not args.loopback_url:
        parser.error("--private-review-output requires --loopback-url and --model")
    if not _secure_inside(args.input, HERE / "local-replay-intake"):
        parser.error("--input must stay inside the ignored chat_replay/local-replay-intake directory")
    if not _secure_inside(args.consent, HERE / "local-replay-intake"):
        parser.error("--consent must stay inside the ignored chat_replay/local-replay-intake directory")
    if not _secure_inside(args.provenance, HERE / "local-replay-intake"):
        parser.error("--provenance must stay inside the ignored chat_replay/local-replay-intake directory")
    if not _secure_inside(args.report, HERE / "reports"):
        parser.error("--report must stay inside the ignored chat_replay/reports directory")
    if args.private_review_output and not _secure_inside(args.private_review_output, HERE / "private-replays"):
        parser.error("--private-review-output must stay inside the ignored chat_replay/private-replays directory")
    events = import_private_replay(args.input, args.consent, args.provenance)
    private_rows: list[dict[str, object]] = []
    runtime_profile = (
        verify_loopback_health(
            args.loopback_url,
            args.model,
            expected_epistemic_enabled=args.expected_epistemic_confidence == "on",
        )
        if args.loopback_url else None
    )
    attest = (
        lambda: verify_loopback_health(
            args.loopback_url,
            args.model,
            expected_epistemic_enabled=args.expected_epistemic_confidence == "on",
        )
        if args.loopback_url else None
    )
    report = run_replay(
        events,
        loopback_responder(
            args.loopback_url,
            args.model,
            history_turns=args.history_turns,
            attest=attest,
        ) if args.loopback_url else None,
        (lambda event, response: private_rows.append({
            "seq": event.seq, "offset_ms": event.offset_ms,
            "event_kind": event.event_kind, "input": event.model_text,
            "response": response,
        })) if args.private_review_output else None,
    )
    if runtime_profile is not None:
        final_profile = verify_loopback_health(
            args.loopback_url,
            args.model,
            expected_epistemic_enabled=args.expected_epistemic_confidence == "on",
        )
        if final_profile != runtime_profile:
            raise RuntimeError("local AIRI proxy profile changed during replay")
        report["runtime_profile"] = runtime_profile
    _write_atomic(args.report, report, HERE / "reports")
    if args.private_review_output:
        _write_atomic(args.private_review_output, {
            "schema_version": "airi.chat-replay-private-review.v1",
            "local_only": True,
            "rows": private_rows,
        }, HERE / "private-replays")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
