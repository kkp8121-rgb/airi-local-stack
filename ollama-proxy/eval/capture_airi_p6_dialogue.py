"""Capture one safe 20-turn Korean P6 dialogue for blinded human review.

The capture JSON deliberately has the exact builder schema: its manifest hashes
are the provenance fields.  Timing and endpoint details are not persisted there
because the blinded-packet validator rejects any extra metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

from build_airi_p6_review_packet import CAPTURE_SCHEMA_VERSION
from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest
from run_airi_native_fit_probe import (
    ProbeError, _candidate_options, _require_local_snapshot, _verify_snapshot,
)


Transport = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
HEX64 = set("0123456789abcdef")
NATIVE_CANDIDATES = {"midm-2.0-mini-instruct", "granite-3.3-2b-instruct"}
# Fixed, synthetic, broadcast-safe Korean prompts.  Each includes Hangul so the
# downstream review packet independently rejects accidental non-dialogue data.
PROMPTS = (
    "안녕, 오늘 방송 시작 인사를 짧게 같이 해 줘.",
    "방송 준비를 끝냈어. 가볍게 응원해 줘.",
    "오늘 간식으로 붕어빵을 골랐어. 한마디 해 줘.",
    "게임에서 작은 목표를 달성했어. 같이 기뻐해 줘.",
    "채팅이 잠깐 조용해졌어. 편하게 말을 이어 줘.",
    "따뜻한 차를 마시고 있어. 짧게 반응해 줘.",
    "새로운 배경 음악을 골랐어. 기대된다고 말해 줘.",
    "오늘 방송 제목을 정해서 뿌듯해. 한마디 해 줘.",
    "잠깐 쉬었다가 다시 시작하려고 해. 편하게 답해 줘.",
    "오늘 같이 있어 준 사람들에게 고마운 마음이 들어. 한마디 해 줘.",
    "오늘 입은 옷 색이 마음에 들어. 가볍게 받아쳐 줘.",
    "재미있는 장면이 나와서 웃었어. 같이 웃어 줘.",
    "방송 중에 물을 챙겨 마셨어. 잘했다고 해 줘.",
    "다음 순서를 차분하게 준비하고 있어. 응원해 줘.",
    "좋아하는 노래를 들으니 기분이 좋아. 짧게 답해 줘.",
    "오늘 대화가 편안해서 좋아. 자연스럽게 이어 줘.",
    "작은 실수를 고쳤어. 부담 없이 격려해 줘.",
    "방송을 마치기 전에 한마디 더 나누고 싶어.",
    "오늘 함께해 줘서 고마워. 따뜻하게 답해 줘.",
    "이제 방송을 마칠 시간이야. 짧게 작별 인사해 줘.",
)


class CaptureError(ValueError):
    """Raised for unsafe capture configuration or response shape."""


def _atomic_json(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":")); handle.write("\n")
        staged = Path(handle.name)
    os.replace(staged, target)


def _unavailable(manifest_path: str | Path, manifest: Mapping[str, Any], profile: str, reason: str) -> dict[str, Any]:
    return {"schema_version": CAPTURE_SCHEMA_VERSION, "candidate_id": manifest["candidate_id"], "profile": profile, "status": "unrunnable", "manifest_file_sha256": file_sha256(manifest_path), "manifest_canonical_sha256": canonical_sha256(manifest), "turns": [], "reasons": [reason]}


def _valid_digest(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def _http_transport(endpoint: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
    request = urllib.request.Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise CaptureError("local capture transport failed") from exc
    if not isinstance(value, dict):
        raise CaptureError("local capture response is invalid")
    return value


def _proxy_transport(endpoint: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
    if body.get("options", {}).get("airi_p6_provenance_only") is True:
        health_url = endpoint.rsplit("/v1/", 1)[0] + "/health"
        with urllib.request.urlopen(health_url, timeout=10) as response:
            health = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as response:
            tags = json.loads(response.read().decode("utf-8"))
        model = body.get("model")
        matching = [item for item in tags.get("models", []) if isinstance(item, dict) and item.get("name") == model]
        observed = health.get("chat_model", {}).get("model") if isinstance(health, dict) else None
        if observed != model or len(matching) != 1:
            raise CaptureError("proxy provenance binding is not exact")
        return {"model": model, "digest": matching[0].get("digest")}
    payload = {"model": body.get("model"), "messages": body.get("messages"), "stream": False}
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AIRI-Turn-Origin": "local-quality-probe"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise CaptureError("local proxy capture transport failed") from exc
    if not isinstance(value, dict):
        raise CaptureError("local proxy capture response is invalid")
    return value


def _response_text(value: Mapping[str, Any]) -> str:
    message = value.get("message")
    text = message.get("content") if isinstance(message, dict) else value.get("response")
    choices = value.get("choices")
    if not isinstance(text, str) and isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice_message = choices[0].get("message")
        text = choice_message.get("content") if isinstance(choice_message, dict) else None
    done = value.get("done") is True or isinstance(choices, list)
    if not done or not isinstance(text, str) or not text.strip():
        raise CaptureError("local capture response is incomplete")
    return text


def _validate_local_endpoint(endpoint: str) -> None:
    if endpoint not in {"http://127.0.0.1:11434/api/chat", "http://localhost:11434/api/chat", "http://127.0.0.1:11435/v1/chat/completions", "http://localhost:11435/v1/chat/completions"}:
        raise CaptureError("endpoint must be an exact local AIRI or Ollama chat endpoint")


def _native_capture(manifest: Mapping[str, Any], *, manifest_path: Path, snapshot_path: str | Path | None, gpu_max_mib: int | None, cpu_max_gib: int | None) -> dict[str, Any]:
    """Run the supported native profile once, after all disk integrity checks."""
    if manifest["remote_code"]["required"]:
        return _unavailable(manifest_path, manifest, "native", "REMOTE_CODE_REQUIRED")
    if manifest["candidate_id"] not in NATIVE_CANDIDATES:
        return _unavailable(manifest_path, manifest, "native", "NATIVE_CANDIDATE_UNSUPPORTED")
    if snapshot_path is None or not isinstance(gpu_max_mib, int) or not isinstance(cpu_max_gib, int) or gpu_max_mib < 1 or cpu_max_gib < 1:
        raise CaptureError("native capture requires snapshot, positive gpu-max-mib, and positive cpu-max-gib")
    # This checks every manifest artifact, including selected weights, before
    # importing torch/transformers. It also refuses paths outside the snapshot.
    try:
        _verify_snapshot(manifest, snapshot_path)
        snapshot = _require_local_snapshot(snapshot_path)
    except ProbeError as exc:
        raise CaptureError("native snapshot preflight failed") from exc
    options, _, granite_thinking_false = _candidate_options(manifest["candidate_id"])
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"})
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    max_memory: dict[Any, str] = {0: f"{gpu_max_mib}MiB", "cpu": f"{cpu_max_gib}GiB"}
    tokenizer = None
    model = None
    try:
        tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=False,
            dtype=torch.bfloat16, device_map="auto", max_memory=max_memory,
            low_cpu_mem_usage=True,
        )
        turns = []
        for number, prompt in enumerate(PROMPTS, 1):
            messages = [{"role": "system", "content": "당신은 AIRI입니다. 방송용으로 짧고 친절한 한국어로 답하세요."}, {"role": "user", "content": prompt}]
            template_options: dict[str, Any] = {"add_generation_prompt": True, "return_tensors": "pt", "return_dict": True}
            if granite_thinking_false:
                template_options["thinking"] = False
            encoded = tokenizer.apply_chat_template(messages, **template_options)
            encoded.pop("token_type_ids", None)
            device = model.get_input_embeddings().weight.device
            encoded = {key: value.to(device) for key, value in encoded.items()}
            generated = model.generate(
                **encoded, max_new_tokens=128, use_cache=True,
                pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id,
                **options,
            )
            input_count = encoded["input_ids"].shape[-1]
            text = tokenizer.decode(generated[0][input_count:], skip_special_tokens=True)
            if not isinstance(text, str) or not text.strip():
                raise CaptureError("native capture produced an empty response")
            turns.append({"turn": number, "prompt": prompt, "response": text})
            del generated, encoded
        return {"schema_version": CAPTURE_SCHEMA_VERSION, "candidate_id": manifest["candidate_id"], "profile": "native", "status": "actually_run", "manifest_file_sha256": file_sha256(manifest_path), "manifest_canonical_sha256": canonical_sha256(manifest), "turns": turns, "reasons": []}
    finally:
        del model, tokenizer
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def capture_dialogue(*, manifest_path: str | Path, output_path: str | Path, profile: str, model: str | None = None, expected_digest: str | None = None, endpoint: str = "http://127.0.0.1:11434/api/chat", mode: str = "ollama", transport: Transport | None = None, proxy_test_origin: bool = False, proxy_nonpersistent: bool = False, snapshot_path: str | Path | None = None, gpu_max_mib: int | None = None, cpu_max_gib: int | None = None) -> dict[str, Any]:
    """Atomically write one builder-compatible capture; never contacts non-local endpoints."""
    manifest_file = Path(manifest_path)
    try:
        manifest = validate_manifest(json.loads(manifest_file.read_text(encoding="utf-8")))
        if profile not in {"native", "common"}:
            raise CaptureError("profile must be native or common")
        elif profile == "native":
            result = _native_capture(manifest, manifest_path=manifest_file, snapshot_path=snapshot_path, gpu_max_mib=gpu_max_mib, cpu_max_gib=cpu_max_gib)
        else:
            if mode not in {"ollama", "proxy"}:
                raise CaptureError("mode must be ollama or proxy")
            _validate_local_endpoint(endpoint)
            if not model or not _valid_digest(expected_digest or ""):
                raise CaptureError("common capture requires model and lowercase expected digest")
            if mode == "proxy" and (not proxy_test_origin or not proxy_nonpersistent):
                raise CaptureError("proxy capture requires asserted test-origin and nonpersistent semantics")
            effective_transport = transport or (_proxy_transport if mode == "proxy" else _http_transport)
            # Exact installed digest is asserted by the injected/local transport
            # before dialogue begins.  This avoids running an unpinned tag.
            provenance = effective_transport(endpoint, {"model": model, "stream": False, "messages": [], "options": {"airi_p6_provenance_only": True}})
            if provenance.get("model") != model or provenance.get("digest") != expected_digest:
                raise CaptureError("runtime model digest does not match expected digest")
            turns = []
            for number, prompt in enumerate(PROMPTS, 1):
                messages = [{"role": "system", "content": "당신은 AIRI입니다. 방송용으로 짧고 친절한 한국어로 답하세요."}, {"role": "user", "content": prompt}]
                body: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0, "seed": 42}}
                text = ""; elapsed = 0.0
                for _ in range(3):
                    started = time.monotonic(); response = effective_transport(endpoint, body); elapsed += time.monotonic() - started
                    try:
                        text = _response_text(response)
                        break
                    except CaptureError:
                        continue
                if not text:
                    raise CaptureError(f"local capture turn {number} remained empty after bounded retries")
                # Timing is observed solely to ensure the call completes; it is
                # intentionally excluded from the exact blinded-capture schema.
                if elapsed < 0: raise CaptureError("invalid capture timing")
                turns.append({"turn": number, "prompt": prompt, "response": text})
            result = {"schema_version": CAPTURE_SCHEMA_VERSION, "candidate_id": manifest["candidate_id"], "profile": profile, "status": "actually_run", "manifest_file_sha256": file_sha256(manifest_file), "manifest_canonical_sha256": canonical_sha256(manifest), "turns": turns, "reasons": []}
    except Exception:
        # A malformed manifest has no trustworthy candidate/provenance, so do
        # not invent a capture document that the review builder might accept.
        raise
    _atomic_json(output_path, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True); parser.add_argument("--output", required=True); parser.add_argument("--profile", choices=("native", "common"), required=True)
    parser.add_argument("--model"); parser.add_argument("--expected-digest"); parser.add_argument("--endpoint", default="http://127.0.0.1:11434/api/chat"); parser.add_argument("--mode", choices=("ollama", "proxy"), default="ollama")
    parser.add_argument("--proxy-test-origin", action="store_true"); parser.add_argument("--proxy-nonpersistent", action="store_true")
    parser.add_argument("--snapshot"); parser.add_argument("--gpu-max-mib", type=int); parser.add_argument("--cpu-max-gib", type=int)
    args = parser.parse_args(argv)
    try:
        capture_dialogue(manifest_path=args.manifest, output_path=args.output, profile=args.profile, model=args.model, expected_digest=args.expected_digest, endpoint=args.endpoint, mode=args.mode, proxy_test_origin=args.proxy_test_origin, proxy_nonpersistent=args.proxy_nonpersistent, snapshot_path=args.snapshot, gpu_max_mib=args.gpu_max_mib, cpu_max_gib=args.cpu_max_gib)
    except CaptureError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
