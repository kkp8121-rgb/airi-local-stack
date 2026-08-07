"""Real-time retrieval path: gate, name scan, scoring, and block assembly.

Zero LLM calls, one embedding. Ported from the tech reference §2 (caps and the
score formula) and §4 (the retrieval gate and NameScanner), so the constants are
the ones that were already validated in production - they arrive here from
config rather than being hardcoded, but the defaults are the reference values.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from memory_embed import Embedder, cosine_many
from memory_store import KIND_ENTITY, KIND_FACT, MemoryStore

MEMORY_BLOCK_HEADER = "[Character Memory]"

# §4 - a question carrying any of these is an information request, so retrieval
# runs no matter how short it is.
INFO_SIGNALS = (
    "어떻게", "무엇", "뭐", "얼마", "몇", "사건", "일이", "있었", "기억",
    "관계", "어떤", "정체", "이유", "방법", "설명", "알려", "말해줘", "대해", "에 대한",
)


@dataclass(frozen=True)
class RetrievalCaps:
    """§2 cap table. Defaults are the reference's production-validated values."""

    traits: int = 8
    moments: int = 5
    scene_facts_raw: int = 20
    scene_facts_final: int = 8
    one_hop_relations: int = 5
    one_hop_facts: int = 3
    alpha: float = 0.7
    beta: float = 0.3
    decay_lambda: float = 0.05

    @classmethod
    def from_config(cls, config: Mapping[str, object] | None) -> "RetrievalCaps":
        section = config if isinstance(config, Mapping) else {}
        defaults = cls()

        def number(key: str, fallback: float) -> float:
            try:
                return float(section.get(key, fallback))
            except (TypeError, ValueError):
                return fallback

        return cls(
            traits=int(number("traits", defaults.traits)),
            moments=int(number("moments", defaults.moments)),
            scene_facts_raw=int(number("scene_facts_raw", defaults.scene_facts_raw)),
            scene_facts_final=int(number("scene_facts_final", defaults.scene_facts_final)),
            one_hop_relations=int(number("one_hop_relations", defaults.one_hop_relations)),
            one_hop_facts=int(number("one_hop_facts", defaults.one_hop_facts)),
            alpha=number("alpha", defaults.alpha),
            beta=number("beta", defaults.beta),
            decay_lambda=number("lambda", defaults.decay_lambda),
        )


class NameScanner:
    """Length-descending substring scan (§4).

    Korean has no spacing boundary a set lookup could rely on, so names are
    matched as substrings and a short name swallowed by a longer hit is dropped.
    Fine for dozens of names; swap in Aho-Corasick if that ever explodes.
    """

    def scan(self, question: str, names: Sequence[str]) -> list[str]:
        text = question or ""
        ordered = sorted({name for name in names if name}, key=len, reverse=True)
        hits = [name for name in ordered if name in text]
        return [
            name for name in hits if not any(name != other and name in other for other in hits)
        ]


_SCANNER = NameScanner()


def needs_retrieval(
    question: str, known_names: Sequence[str], attendees: Sequence[str] | None = None
) -> bool:
    """§4 gate. When in doubt say yes: a missed memory costs more than a scan."""
    text = (question or "").strip()
    if len(text) <= 3:  # 'ㅇㅇ', '안녕', 'ㅋㅋ'
        return False
    if any(signal in text for signal in INFO_SIGNALS):
        return True
    present = set(attendees or [])
    if any(name not in present for name in _SCANNER.scan(text, known_names)):
        return True
    return len(text) >= 25


def decay_for(row: Mapping[str, object] | sqlite3.Row, current_turn: int, lam: float) -> float:
    """exp(-lambda * turns since the memory) - canon rows are decay-exempt.

    A row with no turn_range_end is canon (persona traits): the reference is
    explicit that these keep decay = 1.0 so core identity never loses to fresh
    small talk. AIRI runs one continuous session today, so the canon-vs-session
    split is degenerate in practice - traits are stored range-less and every
    conversation moment carries its turn.
    """
    end = row["turn_range_end"]
    if end is None:
        return 1.0
    return math.exp(-lam * max(0, current_turn - int(end)))


def score_row(cosine_value: float, decay_value: float, caps: RetrievalCaps) -> float:
    return caps.alpha * cosine_value + caps.beta * decay_value


def _rank(
    rows: Sequence[sqlite3.Row],
    query_vector: Sequence[float],
    current_turn: int,
    caps: RetrievalCaps,
) -> list[tuple[float, float, sqlite3.Row]]:
    """Return (score, cosine, row) sorted by score, descending."""
    if not rows:
        return []
    cosines = cosine_many(query_vector, [row["vector"] for row in rows])
    scored = [
        (score_row(cosines[index], decay_for(row, current_turn, caps.decay_lambda), caps),
         cosines[index],
         row)
        for index, row in enumerate(rows)
    ]
    scored.sort(key=lambda entry: entry[0], reverse=True)
    return scored


@dataclass
class RetrievalResult:
    traits: list[sqlite3.Row]
    moments: list[sqlite3.Row]
    context: list[sqlite3.Row]
    relations: list[sqlite3.Row]
    matched_names: list[str]

    def is_empty(self) -> bool:
        return not (self.traits or self.moments or self.context or self.relations)

    def total(self) -> int:
        return len(self.traits) + len(self.moments) + len(self.context) + len(self.relations)


def retrieve(
    store: MemoryStore,
    embedder: Embedder,
    caps: RetrievalCaps,
    *,
    session_id: str | None,
    question: str,
    current_turn: int,
) -> RetrievalResult:
    """One embedding, brute-force cosine, decay re-rank, per-kind caps."""
    query_vector = embedder.embed_one(question)

    trait_rows = store.active_rows(session_id, kind=KIND_FACT, subtypes=("trait",))
    traits = [row for _score, _cos, row in _rank(trait_rows, query_vector, current_turn, caps)][
        : caps.traits
    ]

    moment_rows = store.active_rows(session_id, kind=KIND_FACT, subtypes=("moment",))
    moments = [row for _score, _cos, row in _rank(moment_rows, query_vector, current_turn, caps)][
        : caps.moments
    ]

    # "Relevant Context" is the scene bucket. AIRI's Stage A output has no
    # scene subtype (talkain fed it scene descriptions), so entity identity
    # rows ride this lane - they are exactly the "who/what this is" context the
    # section is for. Over-fetch by cosine, then re-rank by score and cut.
    scene_rows = [
        *store.active_rows(session_id, kind=KIND_FACT, subtypes=("scene",)),
        *store.active_rows(session_id, kind=KIND_ENTITY),
    ]
    if scene_rows:
        cosines = cosine_many(query_vector, [row["vector"] for row in scene_rows])
        over_fetched = sorted(
            range(len(scene_rows)), key=lambda index: cosines[index], reverse=True
        )[: caps.scene_facts_raw]
        context = [
            row
            for _score, _cos, row in _rank(
                [scene_rows[index] for index in over_fetched], query_vector, current_turn, caps
            )
        ][: caps.scene_facts_final]
    else:
        context = []

    # 1-hop expansion: only when the utterance actually names someone.
    name_rows = store.entity_names(session_id)
    names = [str(row["name"]) for row in name_rows]
    matched = _SCANNER.scan(question, names)
    relations: list[sqlite3.Row] = []
    if matched:
        matched_ids = [int(row["id"]) for row in name_rows if str(row["name"]) in matched]
        relations = store.relations_for(session_id, matched_ids, caps.one_hop_relations)
        seen = {int(row["id"]) for row in context}
        for row in store.facts_for_subjects(session_id, matched_ids, caps.one_hop_facts):
            if int(row["id"]) in seen:
                continue
            if any(int(row["id"]) == int(other["id"]) for other in traits + moments):
                continue
            context.append(row)
            seen.add(int(row["id"]))

    return RetrievalResult(
        traits=traits,
        moments=moments,
        context=context,
        relations=relations,
        matched_names=matched,
    )


def render_placeholders(text: str, *, char_name: str, user_name: str) -> str:
    """Placeholders live in the DB (universal storage); names appear only here.

    Full josa-aware substitution (reference §5) is not wired yet - both default
    names end in a consonant, so the particle a naive replace produces is the
    correct one today. Revisit before the display name becomes configurable to
    a vowel-final name.
    """
    return (text or "").replace("{{char}}", char_name).replace("{{user}}", user_name)


def _context_line(row: sqlite3.Row, content: str, char_name: str, user_name: str) -> str:
    name = render_placeholders(
        str(row["name"] or "").strip(), char_name=char_name, user_name=user_name
    )
    if row["kind"] == KIND_ENTITY and name and not content.startswith(name):
        return f"- {name}: {content}"
    return f"- {content}"


def _event_line(row: sqlite3.Row, content: str) -> str:
    day = row["story_day"]
    if day is None:
        return f"- {content}"
    time_of_day = str(row["time_of_day"] or "").strip()
    stamp = f"Day {int(day)} {time_of_day}".strip()
    return f"- ({stamp}) {content}"


def format_memory_block(
    result: RetrievalResult, *, char_name: str = "아이리", user_name: str = "사용자"
) -> str:
    """§2 serialization: plain text sections, never JSON. Empty in, empty out."""
    if result.is_empty():
        return ""

    def content_of(row: sqlite3.Row) -> str:
        return render_placeholders(
            str(row["content"] or "").strip(), char_name=char_name, user_name=user_name
        )

    lines = [MEMORY_BLOCK_HEADER]
    if result.traits:
        lines.append("Traits:")
        lines.extend(f"- {content_of(row)}" for row in result.traits)
    if result.moments:
        lines.append("Recent Events:")
        lines.extend(_event_line(row, content_of(row)) for row in result.moments)
    if result.context:
        lines.append("Relevant Context:")
        # An entity's identity is carried by its name, not only its content -
        # "사용자가 키우는 강아지" without "보리" is exactly the fact the model needs.
        lines.extend(_context_line(row, content_of(row), char_name, user_name) for row in result.context)
    if result.relations:
        lines.append("Relations:")
        lines.extend(f"- {content_of(row)}" for row in result.relations)
    return "\n".join(lines)
