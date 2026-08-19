"""Deterministic guard against content-free memory claims.

The 100-viewer simulation showed the model answering "응, 기억해!" to "내 별명
기억나?" while holding no recalled fact — worse than forgetting, because the
failure hides itself. The rule here is deliberately narrow: it fires only when
the viewer asked a memory question AND the reply asserts remembering without
carrying any content beyond the assertion. A reply that states the remembered
fact ("새벽두시였지!") passes untouched, whether or not it is correct — factual
truth is the memory layer's job, not this guard's.

Pure functions only; the caller supplies the replacement line. Approved
2026-08-19 (결정 큐 3 — 포지 권고안 수용).
"""
from __future__ import annotations

import re

# 시청자가 기억을 묻는 형태. 과거 발화 지시(뭐랬지/뭐라고 했)도 포함한다.
_MEMORY_PROBE_RE = re.compile(
    r"기억\s*(?:나|해|났|하|안\s*나)|뭐\s*랬(?:지|어)|뭐라(?:고|구)?\s*(?:했|말했)|말했(?:잖아|는데)\s*기억"
)
# "응, 기억해!" 류 — 단정 외에 내용이 없는 응답만 잡는다.
_BARE_ASSERTION_RE = re.compile(
    r"^[응어아앙그럼당연히,.!~…\s]*(?:당연히\s*)?기억(?:해|하지|하고\s*있어|나|나지)[!.~…\s]*$"
)


def is_memory_probe(user_text: str) -> bool:
    """Did the viewer ask whether AIRI remembers something?"""
    return bool(_MEMORY_PROBE_RE.search(user_text or ""))


def is_bare_memory_assertion(response: str) -> bool:
    """Does the reply claim memory while carrying no recalled content at all?"""
    return bool(_BARE_ASSERTION_RE.match((response or "").strip()))


def guard_memory_claim(user_text: str, response: str, fallback: str) -> tuple[str, bool]:
    """Replace a content-free memory claim with the approved honest fallback.

    Returns ``(text, replaced)``. Anything that is not a probe answered by a
    bare assertion passes through byte-identical — including honest refusals
    ("기억 안 나"), which the assertion pattern deliberately does not match.
    """
    if is_memory_probe(user_text) and is_bare_memory_assertion(response):
        return fallback, True
    return response, False
