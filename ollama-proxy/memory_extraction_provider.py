"""Approved, structured-output transports for memory extraction.

Cloud transports are deliberately inert until the runtime has both an explicit
approval and the provider credential.  This module never logs request data.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit

from provider_usage import UsageLedger, UsageRecord, utc_now

OFFICIAL_HOSTS = {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}


class ExtractionUnavailableError(RuntimeError):
    """The configured extractor cannot serve requests yet; do not dead-letter data."""


def _ollama_model_key(name: str) -> str:
    """Ollama resolves a tagless model name as the `latest` tag."""
    value = str(name or "").strip()
    leaf = value.rsplit("/", 1)[-1]
    return value if ":" in leaf else value + ":latest"


def approved_base_url(provider: str, base_url: str, allowlist: frozenset[str]) -> str:
    """Return a normalized HTTPS URL only for an official or opted-in host."""
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("external memory extraction base URL must be HTTPS")
    if host != OFFICIAL_HOSTS[provider] and host not in allowlist:
        raise ValueError("external memory extraction host is not approved")
    return base_url.rstrip("/")


class MemoryExtractionProvider:
    """Provider selection plus provider-specific request/response handling."""
    def __init__(self, config: Any, http_client: Any, usage_ledger: UsageLedger | None = None):
        self.config, self.http_client = config, http_client
        self._runtime_ready = bool(self.is_external and self.ready)
        self._availability = "ready" if self._runtime_ready else "unknown"
        ledger_path = str(getattr(config, "usage_ledger_path", "") or "")
        self.usage_ledger = usage_ledger or (UsageLedger(ledger_path) if ledger_path else None)

    @property
    def is_external(self) -> bool:
        return self.config.extraction_provider in {"openai", "anthropic"}

    @property
    def configured(self) -> bool:
        if not self.config.extraction_model:
            return False
        if not self.is_external:
            return True
        return bool(self.config.extraction_api_key)

    @property
    def approved(self) -> bool:
        return not self.is_external or self.config.allow_external_extraction

    @property
    def ready(self) -> bool:
        # Cloud readiness is configuration-only: health must never make a probe.
        return self.http_client is not None and self.approved and self.configured

    @property
    def can_extract(self) -> bool:
        return self.ready

    @property
    def runtime_ready(self) -> bool:
        return bool(self._runtime_ready)

    @property
    def availability(self) -> str:
        if not self.configured:
            return "unconfigured"
        if not self.approved:
            return "approval_required"
        return self._availability

    async def preflight(self, *, force: bool = False) -> bool:
        """Check only the local Ollama inventory; external health never makes a call."""
        if not self.ready:
            self._runtime_ready = False
            self._availability = "unavailable"
            return False
        if self.is_external:
            # Configuration is the only permissible preflight for external
            # providers. Preserve the last observed runtime state.
            return self.ready
        if self._runtime_ready and not force:
            return True
        try:
            response = await self.http_client.get(
                self.config.upstream_url + "/api/tags", timeout=1.0
            )
            response.raise_for_status()
            body = response.json()
            names = {
                str(item.get("name") or item.get("model") or "")
                for item in body.get("models", [])
                if isinstance(item, dict)
            }
        except Exception:
            self._runtime_ready = False
            self._availability = "unavailable"
            return False
        requested = _ollama_model_key(self.config.extraction_model)
        self._runtime_ready = any(_ollama_model_key(name) == requested for name in names)
        self._availability = "ready" if self._runtime_ready else "model_missing"
        return self._runtime_ready

    async def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        if not self.can_extract:
            raise RuntimeError("memory extraction provider is not approved/configured")
        if not await self.preflight():
            raise ExtractionUnavailableError("memory extraction provider is unavailable")
        if self.config.extraction_provider == "ollama":
            return await self._ollama(system, user, schema)
        started_at = utc_now()
        started = time.monotonic()
        usage: dict[str, int | None] = {}
        try:
            if self.config.extraction_provider == "openai":
                content = await self._openai(system, user, schema, usage)
            else:
                content = await self._anthropic(system, user, schema, usage)
        except BaseException:
            self._record_usage(started_at, started, "error", usage)
            raise
        self._record_usage(started_at, started, "completed", usage)
        return content

    def _record_usage(
        self,
        started_at: str,
        started: float,
        status: str,
        usage: dict[str, int | None],
    ) -> None:
        """Operational accounting is fail-soft and never receives prompt text."""
        if self.usage_ledger is None:
            return
        try:
            self.usage_ledger.record(UsageRecord(
                provider=self.config.extraction_provider,
                model=self.config.extraction_model,
                started_at=started_at,
                ended_at=utc_now(),
                duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                status=status,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                cache_read_tokens=usage.get("cache_read_tokens"),
                cache_write_tokens=usage.get("cache_write_tokens"),
            ))
        except Exception:
            pass

    async def _ollama(self, system: str, user: str, schema: dict[str, Any]) -> str:
        # Thinking-capable local models must emit only the structured answer.
        try:
            response = await self.http_client.post(self.config.upstream_url + "/api/chat", json={
                "model": self.config.extraction_model, "stream": False,
                "think": False,
                "keep_alive": self.config.extraction_keep_alive,
                "options": {"temperature": 0, "num_ctx": self.config.extraction_num_ctx,
                            "num_gpu": self.config.extraction_num_gpu,
                            "seed": self.config.extraction_seed,
                            "num_predict": self.config.extraction_max_tokens}, "format": schema,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            })
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            self._runtime_ready = False
            self._availability = "unavailable"
            raise ExtractionUnavailableError("local memory extractor request failed") from exc
        content = body.get("message", {}).get("content") if isinstance(body, dict) else None
        if not isinstance(content, str) or not content:
            raise ValueError("missing Ollama structured output")
        self._runtime_ready = True
        self._availability = "ready"
        return content

    async def _openai(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        usage: dict[str, int | None],
    ) -> str:
        try:
            response = await self.http_client.post(self.config.extraction_base_url + "/chat/completions", headers={
                "Authorization": "Bearer " + self.config.extraction_api_key,
                "Content-Type": "application/json",
            }, json={
                "model": self.config.extraction_model, "store": False, "temperature": 0,
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "memory_extraction", "strict": True, "schema": schema,
                }},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            })
        except Exception as exc:
            self._runtime_ready = False
            self._availability = "unavailable"
            raise ExtractionUnavailableError("OpenAI memory extractor request failed") from exc
        self._check_external_status(response, "OpenAI")
        body = response.json()
        raw_usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        details = raw_usage.get("prompt_tokens_details")
        usage.update({
            "input_tokens": raw_usage.get("prompt_tokens"),
            "output_tokens": raw_usage.get("completion_tokens"),
            "cache_read_tokens": details.get("cached_tokens") if isinstance(details, dict) else None,
            "cache_write_tokens": None,
        })
        choice = (body.get("choices") or [{}])[0]
        if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
            raise ValueError("OpenAI structured output did not finish normally")
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content or message.get("refusal"):
            raise ValueError("missing or refused OpenAI structured output")
        self._runtime_ready = True
        self._availability = "ready"
        return content

    async def _anthropic(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        usage: dict[str, int | None],
    ) -> str:
        try:
            response = await self.http_client.post(self.config.extraction_base_url + "/messages", headers={
                "x-api-key": self.config.extraction_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }, json={
                "model": self.config.extraction_model, "system": system, "temperature": 0,
                "max_tokens": self.config.extraction_max_tokens,
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
                "messages": [{"role": "user", "content": user}],
            })
        except Exception as exc:
            self._runtime_ready = False
            self._availability = "unavailable"
            raise ExtractionUnavailableError("Anthropic memory extractor request failed") from exc
        self._check_external_status(response, "Anthropic")
        body = response.json()
        raw_usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        usage.update({
            "input_tokens": raw_usage.get("input_tokens"),
            "output_tokens": raw_usage.get("output_tokens"),
            "cache_read_tokens": raw_usage.get("cache_read_input_tokens"),
            "cache_write_tokens": raw_usage.get("cache_creation_input_tokens"),
        })
        if body.get("stop_reason") != "end_turn":
            raise ValueError("Anthropic structured output did not finish normally")
        texts = [block.get("text") for block in body.get("content", [])
                 if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)]
        content = "".join(texts)
        if not content:
            raise ValueError("missing Anthropic structured output")
        self._runtime_ready = True
        self._availability = "ready"
        return content

    def _check_external_status(self, response: Any, provider: str) -> None:
        """Retry only transport/429/5xx; permanent 4xx enters the quality cap."""
        try:
            response.raise_for_status()
        except Exception as exc:
            status = getattr(response, "status_code", None)
            self._runtime_ready = False
            if status == 429 or (isinstance(status, int) and status >= 500):
                self._availability = "unavailable"
                raise ExtractionUnavailableError(
                    f"{provider} memory extractor is temporarily unavailable"
                ) from exc
            self._availability = "rejected"
            raise ValueError(
                f"{provider} memory extractor rejected its configuration"
            ) from exc
