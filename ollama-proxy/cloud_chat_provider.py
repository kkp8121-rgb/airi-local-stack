"""Opt-in direct cloud chat transport with conservative SSE decoding."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from provider_usage import UsageLedger, UsageRecord, utc_now

OFFICIAL_HOSTS = {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _base(provider: str, value: str, allowlist: frozenset[str]) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("cloud chat base URL must be HTTPS")
    if host != OFFICIAL_HOSTS[provider] and host not in allowlist:
        raise ValueError("cloud chat host is not approved")
    return value.rstrip("/")


@dataclass(frozen=True)
class CloudChatConfig:
    provider: str = "local"
    allow_external: bool = False
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    usage_ledger_path: str = ""

    @classmethod
    def from_env(cls) -> "CloudChatConfig":
        provider = os.getenv("AIRI_CHAT_PROVIDER", "local").strip().lower()
        if provider not in {"local", "openai", "anthropic"}:
            raise ValueError("AIRI_CHAT_PROVIDER must be local, openai, or anthropic")
        if provider == "local":
            return cls()
        allowlist = frozenset(item.strip().lower() for item in os.getenv(
            "AIRI_CHAT_EXTERNAL_ALLOWLIST", "").split(",") if item.strip())
        defaults = {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com/v1"}
        base = _base(provider, os.getenv(f"AIRI_CHAT_{provider.upper()}_BASE_URL", defaults[provider]), allowlist)
        return cls(provider, _bool("AIRI_ALLOW_EXTERNAL_CHAT"), os.getenv("AIRI_CHAT_MODEL", "").strip(),
                   os.getenv(f"{provider.upper()}_API_KEY", "").strip(), base,
                   os.getenv(
                       "AIRI_USAGE_LEDGER_PATH",
                       str(Path(__file__).resolve().parent / "runtime" / "provider-usage.sqlite3"),
                   ).strip())


@dataclass
class _StreamUsage:
    started_at: str
    started_monotonic: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None


class CloudChatProvider:
    def __init__(self, config: CloudChatConfig, client: Any = None, usage_ledger: UsageLedger | None = None):
        self.config, self.client = config, client
        self.usage_ledger = usage_ledger or (UsageLedger(config.usage_ledger_path) if config.usage_ledger_path else None)
        self._stream_usage: dict[int, _StreamUsage] = {}

    @property
    def external_approved(self) -> bool:
        return self.config.allow_external

    @property
    def configured(self) -> bool:
        return self.config.provider == "local" or bool(self.config.model and self.config.api_key)

    @property
    def ready(self) -> bool:
        return self.config.provider != "local" and self.external_approved and self.configured and self.client is not None

    def health(self) -> dict[str, object]:
        return {"provider": self.config.provider, "external_approved": self.external_approved,
                "configured": self.configured, "ready": self.ready}

    async def open_stream(self, payload: dict[str, Any]) -> Any:
        if not self.ready:
            raise RuntimeError("cloud chat provider is not approved/configured")
        usage = _StreamUsage(utc_now(), time.monotonic())
        if self.config.provider == "openai":
            headers = {"Authorization": "Bearer " + self.config.api_key, "Content-Type": "application/json"}
            body = {key: value for key, value in payload.items() if key not in {"options", "stream", "store"}}
            body.update({"model": self.config.model, "stream": True, "store": False,
                         "stream_options": {"include_usage": True}})
            url = self.config.base_url + "/chat/completions"
        else:
            headers = {"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
            system = []
            for message in messages:
                if not isinstance(message, dict) or message.get("role") != "system":
                    continue
                block: dict[str, Any] = {"type": "text", "text": str(message.get("content", ""))}
                # Memory and recent context follow this stable AIRI identity.
                if not system:
                    block["cache_control"] = {"type": "ephemeral"}
                system.append(block)
            body = {"model": self.config.model, "stream": True, "max_tokens": 1024,
                    "system": system, "messages": [message for message in messages if isinstance(message, dict) and message.get("role") != "system"]}
            url = self.config.base_url + "/messages"
        try:
            request = self.client.build_request("POST", url, headers=headers, content=json.dumps(body, ensure_ascii=False).encode("utf-8"))
            response = await self.client.send(request, stream=True)
            response.raise_for_status()
        except Exception:
            if "response" in locals():
                await response.aclose()
            self._record_usage(usage, "error")
            raise
        self._stream_usage[id(response)] = usage
        return response

    def _record_usage(self, usage: _StreamUsage, status: str) -> None:
        """Ledger is observability only: its failure must not affect chat."""
        if self.usage_ledger is None:
            return
        try:
            self.usage_ledger.record(UsageRecord(
                provider=self.config.provider, model=self.config.model,
                started_at=usage.started_at, ended_at=utc_now(),
                duration_ms=max(0, round((time.monotonic() - usage.started_monotonic) * 1000)),
                status=status, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens, cache_write_tokens=usage.cache_write_tokens))
        except Exception:
            pass

    @staticmethod
    def _set_usage(usage: _StreamUsage, values: Any, anthropic: bool = False) -> None:
        if not isinstance(values, dict):
            return
        if anthropic:
            usage.input_tokens = values.get("input_tokens", usage.input_tokens)
            usage.output_tokens = values.get("output_tokens", usage.output_tokens)
            usage.cache_read_tokens = values.get("cache_read_input_tokens", usage.cache_read_tokens)
            usage.cache_write_tokens = values.get("cache_creation_input_tokens", usage.cache_write_tokens)
        else:
            usage.input_tokens = values.get("prompt_tokens", usage.input_tokens)
            usage.output_tokens = values.get("completion_tokens", usage.output_tokens)
            details = values.get("prompt_tokens_details")
            if isinstance(details, dict):
                usage.cache_read_tokens = details.get("cached_tokens", usage.cache_read_tokens)

    async def deltas(self, response: Any) -> AsyncIterator[str]:
        """Yield text deltas from SSE, preserving UTF-8 and multiline data."""
        usage = self._stream_usage.pop(id(response), _StreamUsage(utc_now(), time.monotonic()))
        buffer = bytearray()
        terminal = False
        completed = False
        try:
            async for chunk in response.aiter_raw():
                buffer.extend(chunk)
                while True:
                    lf = buffer.find(b"\n\n")
                    crlf = buffer.find(b"\r\n\r\n")
                    candidates = [(index, separator) for index, separator in ((lf, b"\n\n"), (crlf, b"\r\n\r\n")) if index >= 0]
                    if not candidates:
                        break
                    index, separator = min(candidates, key=lambda item: item[0])
                    raw = bytes(buffer[:index])
                    del buffer[: index + len(separator)]
                    data = "\n".join(line[5:].lstrip() for line in raw.decode("utf-8").splitlines() if line.startswith("data:"))
                    if data == "[DONE]":
                        terminal = True
                        continue
                    if not data:
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict) and event.get("error"):
                        raise RuntimeError("cloud chat provider returned an error event")
                    if self.config.provider == "openai":
                        self._set_usage(usage, event.get("usage"))
                        choices = event.get("choices") or []
                        delta = choices[0].get("delta", {}) if choices and isinstance(choices[0], dict) else {}
                        text = delta.get("content") if isinstance(delta, dict) else ""
                        finish_reason = choices[0].get("finish_reason") if choices and isinstance(choices[0], dict) else None
                        if finish_reason is not None:
                            if finish_reason != "stop":
                                raise RuntimeError("OpenAI cloud chat did not finish normally")
                            completed = True
                    else:
                        self._set_usage(usage, event.get("usage"), anthropic=True)
                        message = event.get("message")
                        if isinstance(message, dict):
                            self._set_usage(usage, message.get("usage"), anthropic=True)
                        delta = event.get("delta", {}) if isinstance(event, dict) else {}
                        text = delta.get("text") if isinstance(delta, dict) else ""
                        if event.get("type") == "error":
                            raise RuntimeError("Anthropic cloud chat returned an error event")
                        if event.get("type") == "message_delta" and delta.get("stop_reason") is not None:
                            if delta.get("stop_reason") != "end_turn":
                                raise RuntimeError("Anthropic cloud chat did not finish normally")
                            completed = True
                        if event.get("type") == "message_stop":
                            terminal = True
                    if isinstance(text, str) and text:
                        yield text
            if not terminal or not completed:
                raise RuntimeError("cloud chat stream ended without a normal completion")
        except BaseException:
            self._record_usage(usage, "error")
            raise
        else:
            self._record_usage(usage, "completed")
