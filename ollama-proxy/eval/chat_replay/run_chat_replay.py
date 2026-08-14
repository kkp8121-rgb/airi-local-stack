#!/usr/bin/env python3
"""CLI for local, consent-bound replay; it performs no network request by default."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from chat_replay import MAX_PRIVATE_PACKET_BYTES, MAX_RESPONSE_CHARS, MIN_RESPONSE_CHARS, ReplayEvent, ReplayResponse, _canonical, _sample_response_events, load_private_replay, run_replay
from normalize_authorized_export import read_identity_key, verify_normalization_receipt
from replay_local_io import _is_reparse, _secure_inside, write_atomic_json


HERE = Path(__file__).resolve().parent
PROXY_PORT = 11435
PROXY_CHAT_PATH = "/v1/chat/completions"
EVAL_TEMPERATURE = 0
EVAL_SEED = 42
EVAL_NUM_CTX = 2048
EVAL_MAX_TOKENS = 128
MAX_MODEL_CALLS_DEFAULT = 1441
MAX_RUN_SECONDS_DEFAULT = 7200
MIN_MODEL_RUN_SECONDS = 30 * 60
MAX_MODEL_RUN_SECONDS = 120 * 60
MIN_MODEL_RUN_EVENTS = 300
MAX_HISTORY_CHARS = 6_000
MAX_REQUEST_BYTES = 12 * 1024
MAX_RESPONSE_BODY_BYTES = 64 * 1024
MAX_HEALTH_BODY_BYTES = 64 * 1024
READ_CHUNK_BYTES = 8 * 1024
EVAL_MODEL = "midm-airi:2.0-mini"
EVAL_MODEL_DIGEST = "92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f"
MODEL_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
REPORT_HMAC_DOMAIN = b"airi.chat-replay-report.v1\0"


class _RejectRedirects(HTTPRedirectHandler):
    """Do not allow a validated loopback request to leave its exact URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _build_loopback_opener():
    """Build a direct-only opener that ignores environment and Windows proxies."""
    return build_opener(ProxyHandler({}), _RejectRedirects())


# Never let HTTP_PROXY or the Windows proxy settings receive private replay text.
_LOOPBACK_OPENER = _build_loopback_opener()


def _open_loopback(request: Request, timeout: float):
    return _LOOPBACK_OPENER.open(request, timeout=timeout)


def _remaining_timeout(deadline: float | None, limit: float) -> float:
    if deadline is None:
        return limit
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("model replay exceeded --max-run-seconds")
    return min(limit, remaining)


def _read_bounded(response: object, cap: int, *, deadline: float | None) -> bytes:
    """Read a finite local response without trusting Content-Length headers."""
    chunks: list[bytes] = []
    total = 0
    reader = getattr(response, "read1", None)
    if not callable(reader):
        reader = getattr(response, "read")
    accepts_size = True
    while True:
        _remaining_timeout(deadline, float("inf"))
        try:
            chunk = reader(min(READ_CHUNK_BYTES, cap + 1 - total))
        except TypeError:
            # Minimal test/dumb file-like objects may expose only read(). A
            # single unbounded read is still capped after receipt.
            if not accepts_size:
                raise
            accepts_size = False
            chunk = reader()
        if not isinstance(chunk, bytes):
            raise RuntimeError("loopback response body is not bytes")
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise RuntimeError(f"loopback response body exceeds {cap // 1024}KiB")
        chunks.append(chunk)
        _remaining_timeout(deadline, float("inf"))
        if not accepts_size:
            break
    return b"".join(chunks)


def _write_atomic(
    path: Path, value: object, parent: Path, *, max_bytes: int | None = None,
) -> None:
    write_atomic_json(path, value, parent, max_bytes=max_bytes)


def replay_report_hmac(identity_key: bytes, report: dict[str, object]) -> str:
    """Bind the complete content-free replay report for later human review."""
    unsigned = dict(report)
    unsigned.pop("report_hmac_sha256", None)
    return hmac.new(
        identity_key,
        REPORT_HMAC_DOMAIN + _canonical(unsigned),
        hashlib.sha256,
    ).hexdigest()


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
    deadline: float | None = None,
) -> dict[str, object]:
    parsed = _validated_proxy_url(url)
    if model != EVAL_MODEL:
        raise RuntimeError(f"--model must match the frozen replay model {EVAL_MODEL}")
    health_url = urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))
    with _open_loopback(Request(health_url, method="GET"), _remaining_timeout(deadline, 5)) as response:
        _remaining_timeout(deadline, float("inf"))
        if response.status >= 400:
            raise RuntimeError(f"local AIRI proxy health returned HTTP {response.status}")
        payload = json.loads(_read_bounded(response, MAX_HEALTH_BODY_BYTES, deadline=deadline).decode("utf-8"))
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


def _response_outcome(response: object) -> str:
    headers = getattr(response, "headers", None)

    def value(name: str) -> str:
        found = headers.get(name) if hasattr(headers, "get") else None
        if found is None and hasattr(response, "getheader"):
            found = response.getheader(name)
        return str(found or "").strip()

    if value("X-AIRI-Serious-Safety") == "handled":
        return "serious_safety"
    if value("X-AIRI-Input-Screened") == "blocked":
        return "input_screened"
    epistemic = value("X-AIRI-Epistemic-Confidence")
    if epistemic in {"live_state", "agreement", "reference"}:
        return f"epistemic_{epistemic}"
    if epistemic:
        return "epistemic_other"
    return "normal"


def loopback_responder(
    url: str,
    model: str,
    *,
    history_turns: int = 8,
    attest: Callable[[], dict[str, object]] | None = None,
    deadline: float | None = None,
):
    _validated_proxy_url(url)
    if model != EVAL_MODEL:
        raise ValueError(f"--model must match the frozen replay model {EVAL_MODEL}")
    if not 1 <= history_turns <= 32:
        raise ValueError("--history-turns must be between 1 and 32")
    history: list[dict[str, str]] = []

    def request_data(text: str) -> bytes:
        candidate = [*history, {"role": "user", "content": text}]
        while len(candidate) > 1 and (
            sum(len(item["content"]) for item in candidate[:-1]) > MAX_HISTORY_CHARS
            or len(json.dumps({"model": model, "messages": candidate, "stream": False, "temperature": EVAL_TEMPERATURE, "seed": EVAL_SEED, "max_tokens": EVAL_MAX_TOKENS}, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES
        ):
            # History always consists of complete user/assistant exchange pairs.
            del candidate[:2]
        data = json.dumps({"model": model, "messages": candidate, "stream": False, "temperature": EVAL_TEMPERATURE, "seed": EVAL_SEED, "max_tokens": EVAL_MAX_TOKENS}, ensure_ascii=False).encode("utf-8")
        if len(data) > MAX_REQUEST_BYTES:
            raise RuntimeError("loopback request exceeds conservative num_ctx history bound")
        return data

    def respond(text, _event):
        before_profile = attest() if attest is not None else None
        request = Request(
            url,
            data=request_data(text),
            headers={"Content-Type": "application/json", "X-AIRI-Turn-Origin": "local-evaluation"},
            method="POST",
        )
        with _open_loopback(request, _remaining_timeout(deadline, 15)) as response:  # explicit opt-in only
            _remaining_timeout(deadline, float("inf"))
            if response.status >= 400:
                raise RuntimeError(f"loopback model returned HTTP {response.status}")
            outcome = _response_outcome(response)
            raw_body = _read_bounded(response, MAX_RESPONSE_BODY_BYTES, deadline=deadline)
            body = json.loads(raw_body.decode("utf-8"))
        choices = body.get("choices") if isinstance(body, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        result = message.get("content") if isinstance(message, dict) else None
        if not isinstance(result, str):
            native_message = body.get("message") if isinstance(body, dict) else None
            result = native_message.get("content") if isinstance(native_message, dict) else body.get("text") if isinstance(body, dict) else None
        if not isinstance(result, str) or not MIN_RESPONSE_CHARS <= len(result) <= MAX_RESPONSE_CHARS:
            raise RuntimeError("loopback model response must contain 1..4000 characters")
        after_profile = attest() if attest is not None else None
        if before_profile != after_profile:
            raise RuntimeError("local AIRI proxy profile changed during a replay turn")
        history.extend(({"role": "user", "content": text}, {"role": "assistant", "content": result}))
        del history[:-2 * history_turns]
        return ReplayResponse(result, outcome)
    return respond


def validate_model_replay_preflight(
    events: list[ReplayEvent], *, max_model_calls: int,
    private_review_requested: bool = False,
) -> dict[str, object]:
    """Reject an unbounded model campaign before health checks or HTTP calls."""
    sampled_events, sampling = _sample_response_events(events)
    duration_ms = events[-1].offset_ms if events else 0
    if not MIN_MODEL_RUN_EVENTS <= len(events) <= 20_000 or not MIN_MODEL_RUN_SECONDS * 1000 <= duration_ms <= MAX_MODEL_RUN_SECONDS * 1000:
        raise ValueError("model replay requires 300..20000 events spanning 30..120 minutes")
    if not 1 <= len(sampled_events) <= max_model_calls:
        raise ValueError("model replay selected response count is outside --max-model-calls")
    # A private packet is scored later, and therefore cannot represent an
    # empty model selection even if callers evolve this preflight separately.
    if private_review_requested and not sampled_events:
        raise ValueError("private review requires at least one sampled model response")
    return sampling


def build_private_review_packet(
    events: list[ReplayEvent],
    responses: dict[int, str],
    capture_profile: dict[str, str],
    source_structural_sha256: str,
    source_evidence: dict[str, str],
    runtime_profile: dict[str, object],
    run_binding_sha256: str,
    report_hmac_sha256: str,
    response_rows: list[dict[str, object]],
    response_sampling: dict[str, object],
) -> dict[str, object]:
    response_by_seq = {item["seq"]: item for item in response_rows}
    rows = [{
        "seq": event.seq,
        "offset_ms": event.offset_ms,
        "timing_bucket": event.timing_bucket,
        "event_kind": event.event_kind,
        "duplicate_of_seq": event.duplicate_of_seq,
        "surface_signals": list(event.surface_signals),
        "selection_eligible": event.selection_eligible,
        "delivered": event.seq in responses,
        "input": event.model_text,
        "response": responses.get(event.seq),
        "outcome": response_by_seq[event.seq]["outcome"] if event.seq in responses else None,
        "response_char_count": response_by_seq[event.seq]["response_char_count"] if event.seq in responses else None,
        "response_hmac_sha256": response_by_seq[event.seq]["response_hmac_sha256"] if event.seq in responses else None,
        "review": {
            "expected_action": None,
            "grounded": None,
            "context_preserved": None,
            "tone_ok": None,
            "privacy_ok": None,
            "current_fact_ok": None,
            "reference_grounding_ok": None,
            "agreement_calibration_ok": None,
        },
    } for event in events]
    return {
        "schema_version": "airi.chat-replay-private-review.v3",
        "local_only": True,
        "capture_profile": capture_profile,
        "source_structural_sha256": source_structural_sha256,
        "source_evidence": source_evidence,
        "runtime_profile": runtime_profile,
        "run_binding_sha256": run_binding_sha256,
        "report_hmac_sha256": report_hmac_sha256,
        "response_sampling": response_sampling,
        "source_review": {
            "atmosphere": None, "pace": None, "context_pressure": None,
            "dominant_patterns": [],
        },
        "rows": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--consent", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--normalization-receipt", required=True, type=Path)
    parser.add_argument("--identity-key", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--loopback-url", help="explicit local-model opt-in; default makes no request")
    parser.add_argument("--model", help="model name used only with --loopback-url")
    parser.add_argument("--history-turns", type=int, default=8)
    parser.add_argument("--max-model-calls", type=int, default=MAX_MODEL_CALLS_DEFAULT)
    parser.add_argument("--max-run-seconds", type=int, default=MAX_RUN_SECONDS_DEFAULT)
    parser.add_argument(
        "--expected-epistemic-confidence", choices=("on", "off"), default="on",
        help="assert the gate state without changing it (default: on)",
    )
    parser.add_argument("--private-review-output", type=Path, help="explicit ignored local input/response review packet")
    return parser


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.loopback_url) != bool(args.model):
        parser.error("--loopback-url and --model must be supplied together")
    if args.private_review_output and not args.loopback_url:
        parser.error("--private-review-output requires --loopback-url and --model")
    if not 1 <= args.max_model_calls <= MAX_MODEL_CALLS_DEFAULT:
        parser.error(f"--max-model-calls must be between 1 and {MAX_MODEL_CALLS_DEFAULT}")
    if args.max_run_seconds < 1 or args.max_run_seconds > MAX_RUN_SECONDS_DEFAULT:
        parser.error(f"--max-run-seconds must be between 1 and {MAX_RUN_SECONDS_DEFAULT}")
    if not _secure_inside(args.input, HERE / "local-replay-intake"):
        parser.error("--input must stay inside the ignored chat_replay/local-replay-intake directory")
    if not _secure_inside(args.consent, HERE / "local-replay-intake"):
        parser.error("--consent must stay inside the ignored chat_replay/local-replay-intake directory")
    if not _secure_inside(args.provenance, HERE / "local-replay-intake"):
        parser.error("--provenance must stay inside the ignored chat_replay/local-replay-intake directory")
    if not _secure_inside(args.identity_key, HERE / "local-replay-intake"):
        parser.error("--identity-key must stay inside the ignored chat_replay/local-replay-intake directory")
    if not _secure_inside(args.normalization_receipt, HERE / "reports"):
        parser.error("--normalization-receipt must stay inside the ignored chat_replay/reports directory")
    if not _secure_inside(args.report, HERE / "reports"):
        parser.error("--report must stay inside the ignored chat_replay/reports directory")
    if args.private_review_output and not _secure_inside(args.private_review_output, HERE / "private-replays"):
        parser.error("--private-review-output must stay inside the ignored chat_replay/private-replays directory")
    if str(args.report.absolute()).casefold() == str(args.normalization_receipt.absolute()).casefold():
        parser.error("--report must not overwrite --normalization-receipt")
    events, capture_profile = load_private_replay(
        args.input, args.consent, args.provenance, now=now,
    )
    if capture_profile is None:
        parser.error("replay CLI requires a consent v2 capture_profile")
    receipt_evidence = verify_normalization_receipt(
        args.input, args.consent, args.provenance,
        args.normalization_receipt, args.identity_key,
        expected_event_count=len(events), now=now,
    )
    receipt_profile = receipt_evidence["capture_profile"]
    if receipt_profile != capture_profile:
        raise RuntimeError("normalization receipt capture profile mismatch")
    identity_key = read_identity_key(args.identity_key)
    private_responses: dict[int, str] = {}
    if args.loopback_url:
        try:
            response_sampling = validate_model_replay_preflight(
                events, max_model_calls=args.max_model_calls,
                private_review_requested=args.private_review_output is not None,
            )
        except ValueError as exc:
            parser.error(str(exc))
    else:
        response_sampling = None
    deadline = time.monotonic() + args.max_run_seconds if args.loopback_url else None
    runtime_profile = (
        verify_loopback_health(
            args.loopback_url,
            args.model,
            expected_epistemic_enabled=args.expected_epistemic_confidence == "on",
            deadline=deadline,
        )
        if args.loopback_url else None
    )
    attest = (
        lambda: verify_loopback_health(
            args.loopback_url,
            args.model,
            expected_epistemic_enabled=args.expected_epistemic_confidence == "on",
            deadline=deadline,
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
            deadline=deadline,
        ) if args.loopback_url else None,
        (lambda event, response: private_responses.__setitem__(
            event.seq, response,
        )) if args.private_review_output else None,
        capture_profile=capture_profile,
        report_hmac_key=(identity_key if args.loopback_url else None),
    )
    if args.loopback_url and report["response_sampling"] != response_sampling:
        raise RuntimeError("prepared response sampling changed before model replay")
    if runtime_profile is not None:
        final_profile = verify_loopback_health(
            args.loopback_url,
            args.model,
            expected_epistemic_enabled=args.expected_epistemic_confidence == "on",
            deadline=deadline,
        )
        if final_profile != runtime_profile:
            raise RuntimeError("local AIRI proxy profile changed during replay")
        runtime_profile = {
            **runtime_profile,
            "history_turns": args.history_turns,
            "max_model_calls": args.max_model_calls,
            "max_run_seconds": args.max_run_seconds,
            "history_char_limit": MAX_HISTORY_CHARS,
            "request_byte_limit": MAX_REQUEST_BYTES,
        }
        source_evidence = {
            name: receipt_evidence[name]
            for name in ("provider", "source_identity_hmac", "exact_capture_hmac")
        }
        report["runtime_profile"] = runtime_profile
        report["source_evidence"] = source_evidence
        report["run_binding_sha256"] = hashlib.sha256(_canonical({
            "source_structural_sha256": report["structural_sha256"],
            "source_evidence": source_evidence,
            "runtime_profile": runtime_profile,
            "response_rows": report["response_rows"],
            "response_sampling": report["response_sampling"],
        })).hexdigest()
        report["report_hmac_sha256"] = replay_report_hmac(identity_key, report)
    if args.private_review_output:
        private_packet = build_private_review_packet(
            events, private_responses, capture_profile,
            report["structural_sha256"], report["source_evidence"],
            report["runtime_profile"], report["run_binding_sha256"],
            report["report_hmac_sha256"], report["response_rows"],
            report["response_sampling"],
        )
        _write_atomic(
            args.private_review_output,
            private_packet,
            HERE / "private-replays", max_bytes=MAX_PRIVATE_PACKET_BYTES,
        )
    _write_atomic(args.report, report, HERE / "reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
