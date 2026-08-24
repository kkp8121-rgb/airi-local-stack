"""Deterministic guard and grounding-signal builder for viewer-handle callouts.

The E2-C1 blind matrix (2026-08-24) regressed on the ``invented_handle`` hard
gate even though forensic replay of the preserved per-run ``memory.sqlite3``
showed the flagged names were not fabricated: the live memory-retrieval
system had genuinely recalled a real earlier viewer, but the eval grader's
``fact_tokens_used`` only knew about the director's own hand-built turn
briefing and had no visibility into that retrieval. Tracing all 53 flagged
mentions back to their transcript context showed only ~13% are a direct
vocative callout ("배접천아!"); the rest are the recalled name used as
ordinary sentence vocabulary ("배접천부터 꺼내야 해") — grammar alone cannot
tell those apart, and production has no closed viewer-handle roster to check
substring membership against (display names are deliberately kept out of
prompt material; see chat-ingress/README.md).

This module therefore does two narrower, precise things sharing one pool of
"what was actually available to ground against this turn" instead of
guessing at arbitrary proper nouns:

1. ``build_grounding_context`` assembles that pool (the live turn plus, when
   given, the memory-retrieval block and recalled journal messages) so the
   guard and the eval grader check membership against the same evidence.
2. ``guard_invented_vocative`` narrowly strips a direct vocative callout
   (-님 honorific address only; -아/-야 endings collide too often with plain
   verb/adjective conjugations, e.g. "좋아"/"가야", to guard safely without a
   morphological analyzer this repo does not have) when the named target is
   absent from that pool. Deliberately narrow, matching this repo's existing
   guard philosophy (see memory_claim_guard.py): missing some invented
   handles is preferred over mangling ordinary dialogue.

The memory-retrieval subset of the pool is also exposed as a plain string so
an eval harness that *does* hold a closed roster (unlike the live proxy) can
run its own substring check and credit any roster handle recalled through
memory as grounded — this is the correction wired into
``eval/broadcast_sim/run_broadcast_sim.py``. Default off
(``AIRI_HANDLE_GROUNDING_GUARD``); with the flag off, every function here
that ``ollama_proxy.py`` calls on the hot path returns unmodified input.

Pure functions only; the caller supplies runtime text and enable state.
Approved 2026-08-24 (사용자 "1과 2함께" — 가드와 그레이더 신호를 하나의
grounding 계산에서 함께 만든다).
"""
from __future__ import annotations

import os
import re
from typing import Any, Iterable

HANDLE_GROUNDING_GUARD_ENABLED = str(os.environ.get("AIRI_HANDLE_GROUNDING_GUARD", "")).strip().lower() in {
    "1", "true", "yes", "on",
}

# 사람을 가리키지 않는 흔한 -님 명사/호칭. 이 목록에 있으면 vocative 후보에서 뺀다.
_TITLE_STOPWORDS = frozenset({
    "여러분", "시청자", "구독자", "선생", "사장", "손", "회원", "고객",
    "시청자분", "구독자분", "회원분", "여러분들",
})

_VOCATIVE_NIM_RE = re.compile(r"([가-힣]{2,8})님(?![가-힣])")
_SAFE_ADDRESS_TERM = "여러분"
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([,.!?~…])")
_EXTRA_SPACE_RE = re.compile(r"[ \t]{2,}")


def build_grounding_context(
    *,
    last_user_text: str | None = None,
    briefing_evidence: str | None = None,
    memory_block: str | None = None,
    journal_messages: Iterable[dict[str, Any]] | None = None,
) -> str:
    """Join every text fragment offered, for a plain substring membership check.

    Callers pick which fragments to include: the guard's own grounding
    decision wants every source available this turn, while the signal
    exposed to the eval grader deliberately includes only the
    memory/journal fragments the grader could not otherwise see (the user
    turn and director briefing are already visible to it).
    """
    parts = [last_user_text or "", briefing_evidence or "", memory_block or ""]
    for message in journal_messages or ():
        if isinstance(message, dict):
            content = message.get("content")
            if content:
                parts.append(str(content))
    return "\n".join(part for part in parts if part)


def build_grounding_pools(
    *,
    last_user_text: str | None,
    briefing_evidence: str | None,
    memory_result: Any = None,
) -> tuple[str | None, str | None]:
    """Return ``(full_context, memory_pool)``, or ``(None, None)`` when off.

    Gating here — not only at the call site — keeps the cost of the disabled
    default at a single boolean check: ``memory_result`` attributes are read
    with ``getattr`` and only after the flag check, so a caller can pass
    whatever it already has on hand (a real ``RetrievalResult``, ``None``, or
    a test stand-in) without the *caller* needing to shape it first.
    """
    if not HANDLE_GROUNDING_GUARD_ENABLED:
        return None, None
    memory_block = getattr(memory_result, "block", "") or ""
    journal_messages = getattr(memory_result, "journal_messages", None) or ()
    memory_pool = build_grounding_context(
        memory_block=memory_block, journal_messages=journal_messages,
    )
    full_context = build_grounding_context(
        last_user_text=last_user_text, briefing_evidence=briefing_evidence,
        memory_block=memory_block, journal_messages=journal_messages,
    )
    return full_context, memory_pool


def extract_vocative_targets(text: str) -> list[str]:
    """Names/handles the text directly addresses with the -님 honorific.

    Order-preserving, deduplicated, with common non-name -님 nouns excluded.
    """
    seen: list[str] = []
    for match in _VOCATIVE_NIM_RE.finditer(text or ""):
        target = match.group(1)
        if target in _TITLE_STOPWORDS or target in seen:
            continue
        seen.append(target)
    return seen


def guard_invented_vocative(response: str, grounding_context: str) -> tuple[str, dict[str, object]]:
    """Replace a -님 callout to a target absent from ``grounding_context``.

    Returns ``(text, signal)`` where ``signal`` always reports what was
    checked, even when nothing needed stripping.
    """
    checked = extract_vocative_targets(response)
    if not checked:
        return response, {"checked": [], "grounded": [], "stripped": []}
    pool = grounding_context or ""
    grounded = [target for target in checked if target in pool]
    stripped = [target for target in checked if target not in pool]
    if not stripped:
        return response, {"checked": checked, "grounded": grounded, "stripped": []}
    stripped_set = set(stripped)

    def _sub(match: re.Match[str]) -> str:
        target = match.group(1)
        return _SAFE_ADDRESS_TERM if target in stripped_set else match.group(0)

    replaced = _VOCATIVE_NIM_RE.sub(_sub, response)
    replaced = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", replaced)
    replaced = _EXTRA_SPACE_RE.sub(" ", replaced).strip()
    return replaced, {"checked": checked, "grounded": grounded, "stripped": stripped}


def apply_handle_grounding_guard(
    content: str,
    *,
    full_context: str,
    memory_pool: str,
) -> tuple[str, dict[str, object] | None]:
    """Guard entry point matching the ``apply_output_moderation`` call shape.

    Always attaches ``memory_pool`` (even on a turn with no vocative target)
    so the eval grader can run its own roster-membership check against the
    memory/journal evidence the live proxy retrieved — that check covers
    mentions this guard's narrower vocative rule cannot, e.g. a recalled name
    used as ordinary sentence vocabulary rather than a direct address.
    """
    if not content:
        return content, None
    text, vocative_signal = guard_invented_vocative(content, full_context)
    signal: dict[str, object] = {
        "vocative_checked": vocative_signal["checked"],
        "vocative_grounded": vocative_signal["grounded"],
        "vocative_stripped": vocative_signal["stripped"],
        "memory_pool": memory_pool,
    }
    return text, signal
