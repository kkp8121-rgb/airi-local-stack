"""System1 candidate-judge seam for the VOD storyline runner (evaluation only, default off).

Measured on 2026-09-23 (fixed 32 turns, spine mode): 16 of the 17 model calls per turn
are viewer_reaction candidates, and the heuristic that ranks them rewards copying the
viewer's chat, so it picked an 8+ character copy on 5 of 32 turns while the first valid
candidate did so on 0.  This module lets the runner stop at the first acceptable
candidate instead: either by rules alone, or by a small trained judge ("System1") that
scores each candidate as it arrives.  Rules stay outside the model; the model only
adds the semantic judgment rules cannot express, and it never grants anything.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Any, Callable, Sequence

CANDIDATE_SELECT_MODES = ("heuristic", "rule-early-exit", "system1-shadow", "system1-early-exit")
# The longest verbatim run the heuristic-selected reactions shared with the chat reached
# 8+ characters on 5/32 turns; a first-valid pick never did.  Shorter shared runs are
# names and topic words, which a reaction is expected to reuse.
RULE_MAX_CHAT_COPY_RUN = 8
QUESTION_END_RE = re.compile(r"[?？]\s*$")
DEFAULT_SYSTEM1_URL = "http://127.0.0.1:11510"
DEFAULT_SYSTEM1_THRESHOLD = 0.5
SYSTEM1_TIMEOUT_SECONDS = 5.0


def model_input(chat: str, candidate: str) -> str:
    """The exact text the judge was trained on; the service and trainer share it."""
    return f"채팅: {chat}\n반응: {candidate}"


def rule_reject_reason(
    candidate: str, viewer_text: str, common_run: Callable[[str, str], int],
) -> str | None:
    """Clear-cut rejections that need no model: a question back to the viewer, or a copy."""
    if QUESTION_END_RE.search(candidate):
        return "question"
    if common_run(candidate, viewer_text) >= RULE_MAX_CHAT_COPY_RUN:
        return "chat_copy"
    return None


def stop_here(mode: str, rule_reason: str | None, probability: float | None, threshold: float) -> bool:
    """Whether a valid candidate ends the candidate loop under the selected mode."""
    if mode == "rule-early-exit":
        return rule_reason is None
    if mode == "system1-early-exit":
        return rule_reason is None and probability is not None and probability >= threshold
    return False


def fallback_index(slot_calls: Sequence[dict[str, Any]], valid_indexes: Sequence[int]) -> int | None:
    """No candidate stopped the loop: prefer the highest judge score among rule-clean ones."""
    scored = [i for i in valid_indexes if slot_calls[i].get("system1_p") is not None]
    if not scored:
        return None
    clean = [i for i in scored if slot_calls[i].get("rule_reject") is None]
    pool = clean or scored
    return max(pool, key=lambda i: (slot_calls[i]["system1_p"], -int(slot_calls[i].get("attempt") or 0)))


class System1Client:
    """Loopback client for the judge service: POST /score {chat, candidate} -> {p}."""

    def __init__(self, url: str = DEFAULT_SYSTEM1_URL, timeout: float = SYSTEM1_TIMEOUT_SECONDS) -> None:
        self.url = url.rstrip("/") + "/score"
        self.timeout = timeout

    def score(self, chat: str, candidate: str) -> tuple[float, float]:
        body = json.dumps({"chat": chat, "candidate": candidate}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        probability = float(payload["p"])
        if not 0.0 <= probability <= 1.0:
            raise ValueError("judge probability out of range")
        return probability, round((time.perf_counter() - started) * 1000, 2)
