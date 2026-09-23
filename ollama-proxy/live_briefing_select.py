"""Default-off candidate selection for live-broadcast turns whose briefing names what to say.

The 2.3B generator answers the viewer's literal words and drops or contradicts the showrunner's briefing
when the chat presupposes something else.  Prompt wording does not move it, but its samples differ, so
when the briefing carries a ``- 이번 턴에 말할 것:`` line the proxy may draw a few candidates and keep the
first fit one that covers that line.  Nothing here reads or writes proxy state; the caller owns drawing.
"""
from __future__ import annotations

import difflib
import os
import re
import threading
import unicodedata
from typing import Awaitable, Callable


LIVE_BRIEFING_CANDIDATES_ENV = "AIRI_LIVE_BRIEFING_CANDIDATES"
LIVE_BRIEFING_COVERAGE_ENV = "AIRI_LIVE_BRIEFING_COVERAGE"
MAX_CANDIDATES = 6
DEFAULT_COVERAGE = 0.3
SAY_LINE_PREFIX = "- 이번 턴에 말할 것:"
# A candidate sharing this many characters with the previous reply is a repeat, not a new beat.
REPEAT_RUN_CHARS = 20

_NON_TEXT_RE = re.compile(r"[^가-힣A-Za-z0-9]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?~])\s+|\n+")
_HONORIFIC_END_RE = re.compile(r"(?:요|습니다|세요|죠)\s*[.!?~]*\s*$")
# Staff-note narration copied as speech ("마라탕을 먹었다.", "운만 뗀다.").
_WRITTEN_END_RE = re.compile(r"(?:었다|았다|였다|했다|한다|뗀다|는다|샀다|갔다)\s*[.!]*\s*$")
_LEAKED_LABEL_RE = re.compile(r"이번 턴에|브리핑|스태프|\[")
_UNEXECUTED_LOOKUP_RE = re.compile(r"(?:검색|찾아|확인|알아)\s?(?:해\s?)?봤|검색했")


def candidate_budget(value: object | None = None) -> int:
    """Read the opt-in candidate count; absent, invalid or 1 keeps the single draw."""
    if value is None:
        value = os.environ.get(LIVE_BRIEFING_CANDIDATES_ENV, "")
    if not isinstance(value, str) or not value.strip().isdigit():
        return 0
    count = int(value.strip())
    return min(count, MAX_CANDIDATES) if count >= 2 else 0


def coverage_threshold(value: object | None = None) -> float:
    """Read the early-accept coverage; anything outside (0, 1] falls back to the default."""
    if value is None:
        value = os.environ.get(LIVE_BRIEFING_COVERAGE_ENV, "")
    try:
        threshold = float(value) if isinstance(value, str) and value.strip() else DEFAULT_COVERAGE
    except ValueError:
        return DEFAULT_COVERAGE
    return threshold if 0.0 < threshold <= 1.0 else DEFAULT_COVERAGE


def say_line(context_note: object) -> str:
    """Return the briefing's say line, or '' when the turn names nothing to say."""
    if not isinstance(context_note, str):
        return ""
    for line in context_note.splitlines():
        if line.startswith(SAY_LINE_PREFIX):
            return line[len(SAY_LINE_PREFIX):].strip()
    return ""


def _bigrams(text: str) -> set[str]:
    compact = _NON_TEXT_RE.sub("", unicodedata.normalize("NFKC", text))
    return {compact[index:index + 2] for index in range(len(compact) - 1)}


def briefing_coverage(answer: object, say: str) -> float:
    """Share of the say line's character bigrams that the answer reuses."""
    target = _bigrams(say)
    if not isinstance(answer, str) or not target:
        return 0.0
    return len(target & _bigrams(answer)) / len(target)


def candidate_is_unfit(answer: object, say: str, previous_reply: str = "") -> bool:
    """Reject register slips, copied staff notes, invented lookups and repeats of the previous reply.

    A repeated two-word opener is deliberately not a rejection: on 2026-09-24 show 05 the generator
    kept its '아, 그래서' opener across every redraw, so the rule spent the whole budget and fixed nothing.
    """
    if not isinstance(answer, str) or not answer.strip():
        return True
    text = unicodedata.normalize("NFKC", answer).strip()
    sentences = [part for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if any(_HONORIFIC_END_RE.search(part) or _WRITTEN_END_RE.search(part) for part in sentences):
        return True
    if _LEAKED_LABEL_RE.search(text):
        return True
    if _UNEXECUTED_LOOKUP_RE.search(text) and not _UNEXECUTED_LOOKUP_RE.search(say):
        return True
    previous = unicodedata.normalize("NFKC", previous_reply or "").strip()
    if previous:
        match = difflib.SequenceMatcher(None, text, previous, autojunk=False).find_longest_match(
            0, len(text), 0, len(previous),
        )
        if match.size >= REPEAT_RUN_CHARS:
            return True
    return False


def candidate_score(answer: object, say: str, previous_reply: str = "") -> tuple[bool, float]:
    """(fit, coverage); tuples order fit candidates first, then by coverage."""
    return (not candidate_is_unfit(answer, say, previous_reply), briefing_coverage(answer, say))


def accept_early(score: tuple[bool, float], threshold: float) -> bool:
    fit, coverage = score
    return fit and coverage >= threshold


def best_index(scores: list[tuple[bool, float]]) -> int:
    """Index of the best candidate; the first one wins ties so the draw order stays meaningful."""
    return max(range(len(scores)), key=lambda index: (scores[index], -index))


async def select_candidate(
    first_text: str,
    draw: Callable[[], Awaitable[tuple[str, object | None]]],
    *,
    say: str,
    previous_reply: str,
    budget: int,
    threshold: float,
) -> tuple[str, object | None, list[object]]:
    """Draw until a fit candidate covers the say line or the budget is spent.

    ``first_text`` is the already generated, already bounded dialogue.  ``draw`` returns one more bounded
    dialogue and its upstream payload.  Returns the chosen dialogue, the chosen payload (None when the
    first draft won) and the payloads that were drawn but not chosen.
    """
    texts: list[str] = [first_text]
    payloads: list[object | None] = [None]
    scores = [candidate_score(first_text, say, previous_reply)]
    while not accept_early(scores[-1], threshold) and len(texts) < budget:
        text, payload = await draw()
        texts.append(text)
        payloads.append(payload)
        scores.append(candidate_score(text, say, previous_reply))
    chosen = best_index(scores)
    live_briefing_select_telemetry.record(
        draws=len(texts) - 1, early=accept_early(scores[-1], threshold), replaced=chosen != 0,
    )
    unchosen = [payload for index, payload in enumerate(payloads) if index != chosen and payload is not None]
    return texts[chosen], payloads[chosen], unchosen


class LiveBriefingSelectTelemetry:
    """Content-free counters for the opt-in live briefing candidate selection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._turns = 0
        self._draws = 0
        self._early = 0
        self._replaced = 0

    def record(self, *, draws: int, early: bool, replaced: bool) -> None:
        with self._lock:
            self._turns += 1
            self._draws += draws
            self._early += int(early)
            self._replaced += int(replaced)

    def health(self) -> dict[str, object]:
        with self._lock:
            counts = {
                "turns": self._turns,
                "extra_draws": self._draws,
                "early_accepts": self._early,
                "first_draft_replaced": self._replaced,
            }
        return {"candidates": candidate_budget(), "coverage": coverage_threshold(), **counts}


live_briefing_select_telemetry = LiveBriefingSelectTelemetry()
