"""Stage A/B memory extraction: prompt assembly, parsing, and op application.

The prompts themselves live verbatim in memory_prompts.py - this module only
wraps the conversation in the `<character>`/`<turns>` and
`<extracted>`/`<candidates>` envelopes the reference specifies, parses the JSON
back, and writes the result through MemoryStore.

Everything here is fail-soft. A malformed Stage A response leaves the watermark
where it was so the same batch is retried on the next trigger (the reference's
"no retry queue needed" rule). A malformed Stage B response degrades to the
ADD-only fast path the reference already defines for candidate-free input,
because re-running a Stage A that already succeeded would only burn the
extraction LLM again for the same items.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

from memory_embed import Embedder, cosine_many, pack_vector
from memory_prompts import STAGE_A_SYSTEM_PROMPT, STAGE_B_SYSTEM_PROMPT
from memory_store import (
    CONFIDENCE_VALUES,
    KIND_ENTITY,
    KIND_FACT,
    KIND_RELATION,
    MemoryStore,
)

ENTITY_SUBTYPES = frozenset({"person", "location", "item", "organization", "event"})
FACT_SUBTYPES = frozenset({"trait", "moment", "scene"})
KIND_ORDER = {KIND_ENTITY: 0, KIND_FACT: 1, KIND_RELATION: 2}
ALIAS_PREFIX = {KIND_ENTITY: "e", KIND_FACT: "f", KIND_RELATION: "r"}
# A small model routinely puts a subtype where the prompt demands a kind - the
# prompt itself calls this out as the #1 failure mode. Repair it instead of
# throwing the whole batch away.
SUBTYPE_TO_KIND = {
    **{subtype: KIND_ENTITY for subtype in ENTITY_SUBTYPES},
    **{subtype: KIND_FACT for subtype in FACT_SUBTYPES},
}
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")


def build_stage_a_user_message(character_name: str, turns: Sequence[Mapping[str, object]]) -> str:
    """`<character>` orientation + `<turns>` body, numbered from 1 per batch."""
    lines: list[str] = []
    for index, turn in enumerate(turns, start=1):
        lines.append(f"[turn {index}]")
        user_text = str(turn.get("user_text") or "").strip()
        assistant_text = str(turn.get("assistant_text") or "").strip()
        if user_text:
            lines.append(f"사용자: {user_text}")
        if assistant_text:
            lines.append(f"{character_name}: {assistant_text}")
    body = "\n".join(lines)
    return f"<character>name: {character_name}</character>\n<turns>\n{body}\n</turns>"


def build_stage_b_user_message(
    items: Sequence[Mapping[str, object]], candidates: Sequence[Mapping[str, object]]
) -> str:
    extracted = json.dumps(list(items), ensure_ascii=False, indent=None)
    candidate_lines = [
        f"{candidate['alias']} ({candidate['kind']}"
        + (f"/{candidate['subtype']}" if candidate.get("subtype") else "")
        + (f", name={candidate['name']}" if candidate.get("name") else "")
        + f"): {candidate['content']}"
        for candidate in candidates
    ]
    body = "\n".join(candidate_lines) if candidate_lines else "(none)"
    return f"<extracted>\n{extracted}\n</extracted>\n<candidates>\n{body}\n</candidates>"


def parse_json_object(raw: str) -> dict[str, object]:
    """Strip code fences and prose, then read the outermost JSON object.

    The reference notes the original never used structured output either: it
    stripped fences and parsed fail-soft, which is what small local models need.
    """
    text = _FENCE_RE.sub("", (raw or "").strip())
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in extraction response")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("extraction response is not a JSON object")
    return payload


def normalize_item(raw: object) -> dict[str, object] | None:
    """Coerce one Stage A item into the shape the store can write, or drop it."""
    if not isinstance(raw, Mapping):
        return None
    kind = str(raw.get("kind") or "").strip().lower()
    subtype = str(raw.get("subtype") or "").strip().lower()
    if kind not in KIND_ORDER:
        repaired = SUBTYPE_TO_KIND.get(kind)
        if repaired is None:
            return None
        subtype = subtype or kind
        kind = repaired
    content = str(raw.get("content") or "").strip()
    name = str(raw.get("name") or "").strip()

    if kind == KIND_ENTITY:
        if not name:
            return None
        if subtype not in ENTITY_SUBTYPES:
            subtype = "person"
        content = content or name
    elif kind == KIND_FACT:
        if not content:
            return None
        if subtype not in FACT_SUBTYPES:
            subtype = "moment"
    else:
        source_name = str(raw.get("sourceName") or "").strip()
        target_name = str(raw.get("targetName") or "").strip()
        if not source_name or not target_name:
            return None
        subtype = str(raw.get("subtype") or "").strip() or "관계"
        content = content or f"{source_name} - {target_name}"

    turn_range = raw.get("turnRange")
    if isinstance(turn_range, Sequence) and not isinstance(turn_range, str) and len(turn_range) == 2:
        try:
            local_range = (int(turn_range[0]), int(turn_range[1]))
        except (TypeError, ValueError):
            local_range = None
    else:
        local_range = None

    subject_names = raw.get("subjectNames")
    subjects = [
        str(value).strip()
        for value in (subject_names if isinstance(subject_names, Sequence) and not isinstance(subject_names, str) else [])
        if str(value).strip()
    ]
    confidence = str(raw.get("confidence") or "knows").strip().lower()
    if confidence not in CONFIDENCE_VALUES:
        confidence = "knows"

    item: dict[str, object] = {
        "kind": kind,
        "subtype": subtype,
        "name": name,
        "content": content,
        "subjectNames": subjects,
        "sourceName": str(raw.get("sourceName") or "").strip(),
        "targetName": str(raw.get("targetName") or "").strip(),
        "confidence": confidence,
        "localTurnRange": local_range,
        "turnNumber": raw.get("turnNumber"),
    }
    return item


def parse_stage_a(raw: str) -> list[dict[str, object]]:
    payload = parse_json_object(raw)
    extracted = payload.get("extracted")
    if not isinstance(extracted, list):
        raise ValueError("stage A response has no 'extracted' array")
    items = [normalize_item(entry) for entry in extracted]
    return [item for item in items if item is not None]


def parse_stage_b(raw: str) -> list[dict[str, object]]:
    payload = parse_json_object(raw)
    operations = payload.get("operations")
    if not isinstance(operations, list):
        raise ValueError("stage B response has no 'operations' array")
    parsed: list[dict[str, object]] = []
    for entry in operations:
        if not isinstance(entry, Mapping):
            continue
        op = str(entry.get("op") or "").strip().upper()
        if not op:
            continue
        parsed.append({**entry, "op": op})
    return parsed


def select_candidates(
    store: MemoryStore,
    embedder: Embedder,
    session_id: str | None,
    items: Sequence[Mapping[str, object]],
    *,
    per_item: int = 5,
    total_cap: int = 20,
) -> list[dict[str, object]]:
    """Top-`per_item` existing rows per extracted item, aliased e0/f1/r2 style."""
    rows = store.active_rows(session_id)
    if not rows or not items:
        return []
    blobs = [row["vector"] for row in rows]
    chosen: list[int] = []
    seen: set[int] = set()
    for item in items:
        query = embedder.embed_one(_item_text(item))
        scores = cosine_many(query, blobs)
        ranked = sorted(range(len(rows)), key=lambda index: scores[index], reverse=True)
        for index in ranked[:per_item]:
            row_id = int(rows[index]["id"])
            if row_id in seen:
                continue
            seen.add(row_id)
            chosen.append(index)
            if len(chosen) >= total_cap:
                break
        if len(chosen) >= total_cap:
            break
    candidates: list[dict[str, object]] = []
    for alias_index, row_index in enumerate(chosen):
        row = rows[row_index]
        prefix = ALIAS_PREFIX.get(str(row["kind"]), "e")
        candidates.append(
            {
                "alias": f"{prefix}{alias_index}",
                "id": int(row["id"]),
                "kind": str(row["kind"]),
                "subtype": row["subtype"],
                "name": row["name"],
                "content": row["content"],
            }
        )
    return candidates


def _item_text(item: Mapping[str, object]) -> str:
    name = str(item.get("name") or "")
    content = str(item.get("content") or "")
    return f"{name} {content}".strip() if name else content


def _global_range(
    item: Mapping[str, object], turn_ids: Sequence[int]
) -> tuple[int | None, int | None]:
    """Map a batch-local [start, end] onto the global conversation turn ids."""
    local_range = item.get("localTurnRange")
    if not local_range or not turn_ids:
        return (None, None)
    start, end = local_range

    def resolve(value: int) -> int:
        index = max(1, min(int(value), len(turn_ids))) - 1
        return turn_ids[index]

    return (resolve(start), resolve(end))


class ExtractionApplier:
    """Writes Stage A items (and Stage B operations) into the store."""

    def __init__(
        self,
        store: MemoryStore,
        embedder: Embedder,
        *,
        session_id: str | None,
        source: str = "conversation",
        turn_ids: Sequence[int] = (),
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.session_id = session_id
        self.source = source
        self.turn_ids = list(turn_ids)
        self.summary = {"added": 0, "updated": 0, "superseded": 0, "noop": 0, "skipped": 0}

    # ------------------------------------------------------------- utilities

    def _vector(self, text: str) -> bytes | None:
        try:
            return pack_vector(self.embedder.embed_one(text))
        except Exception:
            # Embedding failure stores the row with vector = NULL, which the
            # retrieval scan simply scores as 0 - fail-soft rule #1.
            return None

    def _entity_id(self, name: str, *, create: bool = True) -> int | None:
        if not name:
            return None
        row = self.store.find_entity(self.session_id, name)
        if row is not None:
            return int(row["id"])
        if not create:
            return None
        # Connectivity rule: a relation or fact whose entity was never emitted
        # would otherwise dangle. A stub keeps the 1-hop expansion usable.
        row_id, inserted = self.store.insert_memory(
            session_id=self.session_id,
            source=self.source,
            kind=KIND_ENTITY,
            subtype="person",
            name=name,
            content=name,
            vector=self._vector(name),
        )
        if inserted:
            self.summary["added"] += 1
        return row_id

    def _insert_item(self, item: Mapping[str, object]) -> int | None:
        kind = str(item.get("kind"))
        content = str(item.get("content") or "")
        name = str(item.get("name") or "")
        start, end = _global_range(item, self.turn_ids)
        source_ref = target_ref = None
        if kind == KIND_RELATION:
            source_ref = self._entity_id(str(item.get("sourceName") or ""))
            target_ref = self._entity_id(str(item.get("targetName") or ""))
            if source_ref is None or target_ref is None:
                self.summary["skipped"] += 1
                return None
        # Traits are canon: leaving the turn range NULL exempts them from decay
        # so a core persona trait never loses to fresh small talk.
        if kind == KIND_FACT and item.get("subtype") == "trait":
            start = end = None
        row_id, inserted = self.store.insert_memory(
            session_id=self.session_id,
            source=self.source,
            kind=kind,
            subtype=str(item.get("subtype") or ""),
            name=name or None,
            content=content,
            source_ref=source_ref,
            target_ref=target_ref,
            confidence=str(item.get("confidence") or "knows"),
            turn_range=(start, end),
            vector=self._vector(_item_text(item)),
        )
        if inserted:
            self.summary["added"] += 1
        else:
            self.summary["noop"] += 1
        if kind == KIND_FACT:
            for subject in item.get("subjectNames") or []:
                entity_id = self._entity_id(str(subject))
                if entity_id is not None:
                    self.store.link_fact_subject(row_id, entity_id)
        return row_id

    # ------------------------------------------------------------ entry points

    def apply_items(self, items: Sequence[Mapping[str, object]]) -> dict[str, int]:
        """ADD-only fast path: entities first so facts and relations can link."""
        for item in sorted(items, key=lambda entry: KIND_ORDER.get(str(entry.get("kind")), 9)):
            self._insert_item(item)
        return dict(self.summary)

    def apply_operations(
        self,
        operations: Sequence[Mapping[str, object]],
        items: Sequence[Mapping[str, object]],
        candidates: Sequence[Mapping[str, object]],
    ) -> dict[str, int]:
        """Apply the 9-op alias protocol (ADD/UPDATE/SUPERSEDE/NOOP)."""
        alias_to_id = {str(candidate["alias"]): int(candidate["id"]) for candidate in candidates}
        # ops[i] answers items[i]; SUPERSEDE carries no content of its own, so
        # the replacement text has to come from the extracted item it answers.
        paired = [
            (operation, items[index] if index < len(items) else None)
            for index, operation in enumerate(operations)
        ]
        paired.sort(key=lambda entry: KIND_ORDER.get(_op_kind(entry[0]), 9))

        for operation, item in paired:
            op = str(operation.get("op"))
            verb = op.split("_")[0]
            if verb == "NOOP":
                self.summary["noop"] += 1
                continue
            if verb == "ADD":
                row_id = self._insert_from_operation(operation, item, alias_to_id)
                alias = str(operation.get("alias") or "")
                if alias and row_id is not None:
                    alias_to_id[alias] = row_id
                continue
            target_id = alias_to_id.get(str(operation.get("alias") or ""))
            if target_id is None:
                # Alias the model invented out of thin air: treat it as an ADD
                # rather than dropping the item.
                row_id = self._insert_from_operation(operation, item, alias_to_id)
                alias = str(operation.get("alias") or "")
                if alias and row_id is not None:
                    alias_to_id[alias] = row_id
                continue
            if verb == "UPDATE":
                content = str(operation.get("content") or (item or {}).get("content") or "").strip()
                if not content:
                    self.summary["skipped"] += 1
                    continue
                self.store.update_memory(
                    target_id,
                    content=content,
                    subtype=str(operation.get("subtype") or "") or None,
                    name=str(operation.get("name") or "") or None,
                    vector=self._vector(content),
                )
                self.summary["updated"] += 1
                continue
            if verb == "SUPERSEDE":
                replacement_id = None
                if item is not None:
                    replacement_id = self._insert_item(item)
                self.store.supersede(target_id, replacement_id)
                self.summary["superseded"] += 1
                continue
            self.summary["skipped"] += 1
        return dict(self.summary)

    def _insert_from_operation(
        self,
        operation: Mapping[str, object],
        item: Mapping[str, object] | None,
        alias_to_id: Mapping[str, int],
    ) -> int | None:
        """Build an item from the op fields, backfilled from the Stage A item."""
        kind = _op_kind(operation)
        merged: dict[str, object] = dict(item or {})
        merged["kind"] = kind
        for field in ("subtype", "content", "name"):
            value = operation.get(field)
            if isinstance(value, str) and value.strip():
                merged[field] = value.strip()
        merged.setdefault("subtype", "")
        merged.setdefault("content", "")
        merged.setdefault("name", "")
        if kind == KIND_RELATION:
            for alias_field, name_field in (
                ("sourceAlias", "sourceName"),
                ("targetAlias", "targetName"),
            ):
                alias = str(operation.get(alias_field) or "")
                row_id = alias_to_id.get(alias)
                if row_id is not None:
                    row = self.store.connect().execute(
                        "SELECT name FROM memory WHERE id = ?", (row_id,)
                    ).fetchone()
                    if row is not None and row["name"]:
                        merged[name_field] = row["name"]
        if kind == KIND_FACT:
            subjects = list(merged.get("subjectNames") or [])
            for alias in operation.get("subjectAliases") or []:
                row_id = alias_to_id.get(str(alias))
                if row_id is None:
                    continue
                row = self.store.connect().execute(
                    "SELECT name FROM memory WHERE id = ?", (row_id,)
                ).fetchone()
                if row is not None and row["name"] and row["name"] not in subjects:
                    subjects.append(row["name"])
            merged["subjectNames"] = subjects
        normalized = normalize_item(merged)
        if normalized is None:
            self.summary["skipped"] += 1
            return None
        normalized["localTurnRange"] = merged.get("localTurnRange")
        return self._insert_item(normalized)


def _op_kind(operation: Mapping[str, object]) -> str:
    op = str(operation.get("op") or "")
    if op.endswith("_ENTITY"):
        return KIND_ENTITY
    if op.endswith("_FACT"):
        return KIND_FACT
    if op.endswith("_RELATION"):
        return KIND_RELATION
    alias = str(operation.get("alias") or "")
    for kind, prefix in ALIAS_PREFIX.items():
        if alias.startswith(prefix):
            return kind
    return KIND_FACT


__all__ = [
    "STAGE_A_SYSTEM_PROMPT",
    "STAGE_B_SYSTEM_PROMPT",
    "ExtractionApplier",
    "build_stage_a_user_message",
    "build_stage_b_user_message",
    "normalize_item",
    "parse_json_object",
    "parse_stage_a",
    "parse_stage_b",
    "select_candidates",
]
