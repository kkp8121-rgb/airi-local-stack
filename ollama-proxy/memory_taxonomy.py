"""Deterministic alias resolution and the fixed extraction taxonomy.

Both tables live in ``memory_taxonomy.json`` so the runtime carries no magic
literals.  Nothing here calls a model: alias resolution is normalization plus a
registration table, and the taxonomy gate is a whitelist membership test.  The
extraction gate in :mod:`memory_runtime` is the only caller, and it is opt-in,
so importing this module costs nothing until a flag turns it on.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

TAXONOMY_PATH = Path(__file__).resolve().parent / "memory_taxonomy.json"
# The Stage A contract keeps this placeholder literal, so it must never be
# normalized, stripped, or folded into a registered person.
USER_PLACEHOLDER = "{{user}}"
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\ufeff")
_MISSING = object()


class TaxonomyError(ValueError):
    """Raised when the shipped tables are internally inconsistent."""


@dataclass(frozen=True)
class TaxonomyTables:
    suffixes: tuple[str, ...]
    min_stem_length: int
    max_suffix_strips: int
    edge_punctuation: str
    protected_names: frozenset[str]
    alias_canonical: Mapping[str, str]
    subtype_slots: Mapping[str, Mapping[str, str]]
    slot_ids: Mapping[str, tuple[str, ...]]


def _normalize_surface(value: str, edge_punctuation: str) -> str:
    # NFKC (rather than the NFC used for journal tokens) also folds fullwidth
    # and compatibility forms, which is exactly the variation an alias table
    # must absorb (e.g. ＡＩＲＩ and AIRI are one surface).
    text = unicodedata.normalize("NFKC", value)
    text = "".join(character for character in text
                   if character not in _ZERO_WIDTH and not character.isspace())
    return text.strip(edge_punctuation).casefold()


@lru_cache(maxsize=4)
def _load(path: str) -> TaxonomyTables:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise TaxonomyError("memory taxonomy schema_version must be 1")
    rules = payload["normalization"]
    edge_punctuation = str(rules["edge_punctuation"])
    suffixes = tuple(sorted(
        (_normalize_surface(str(suffix), edge_punctuation) for suffix in rules["suffixes"]),
        key=len, reverse=True))
    if not all(suffixes):
        raise TaxonomyError("suffixes must be non-empty")
    alias_canonical: dict[str, str] = {}
    for entry in payload["alias_registry"]:
        canonical = str(entry["canonical"])
        for surface in (canonical, *entry.get("aliases", ())):
            key = _normalize_surface(str(surface), edge_punctuation)
            if not key:
                raise TaxonomyError("registered alias normalizes to an empty key")
            if alias_canonical.setdefault(key, canonical) != canonical:
                raise TaxonomyError(f"alias {surface!r} is registered to two canonical names")
    subtype_slots: dict[str, dict[str, str]] = {}
    slot_ids: dict[str, tuple[str, ...]] = {}
    for kind, slots in payload["taxonomy"].items():
        mapping: dict[str, str] = {}
        for slot, surfaces in slots.items():
            for surface in (slot, *surfaces):
                key = _normalize_surface(str(surface), edge_punctuation)
                if not key:
                    raise TaxonomyError("taxonomy surface normalizes to an empty key")
                if mapping.setdefault(key, slot) != slot:
                    raise TaxonomyError(f"subtype {surface!r} maps to two {kind} slots")
        if not mapping:
            raise TaxonomyError(f"{kind} taxonomy must define at least one slot")
        subtype_slots[kind] = mapping
        slot_ids[kind] = tuple(slots)
    protected_names = frozenset(str(name) for name in payload["protected_names"])
    if USER_PLACEHOLDER not in protected_names:
        raise TaxonomyError("the user placeholder must stay protected")
    return TaxonomyTables(
        suffixes=suffixes,
        min_stem_length=int(rules["min_stem_length"]),
        max_suffix_strips=int(rules["max_suffix_strips"]),
        edge_punctuation=edge_punctuation,
        protected_names=protected_names,
        alias_canonical=alias_canonical,
        subtype_slots=subtype_slots,
        slot_ids=slot_ids,
    )


def load_tables(path: str | Path | None = None) -> TaxonomyTables:
    """Return the parsed tables, cached per resolved path."""
    return _load(str(Path(path).resolve()) if path is not None else str(TAXONOMY_PATH))


def normalize_key(value: Any, tables: Optional[TaxonomyTables] = None) -> str:
    """Return the lookup key for one surface form (never a stored value)."""
    if not isinstance(value, str):
        return ""
    return _normalize_surface(value, (tables or load_tables()).edge_punctuation)


def stem_key(value: Any, tables: Optional[TaxonomyTables] = None) -> str:
    """Strip trailing vocatives/particles for lookup only.

    Both the stored name and the incoming mention are reduced the same way, so
    "세라", "세라야", and "세라는" meet at one key without either side having to
    guess a form that was never written.
    """
    tables = tables or load_tables()
    key = normalize_key(value, tables)
    for _ in range(max(0, tables.max_suffix_strips)):
        for suffix in tables.suffixes:
            if key.endswith(suffix) and len(key) - len(suffix) >= tables.min_stem_length:
                key = key[: -len(suffix)]
                break
        else:
            break
    return key


def taxonomy_slot(kind: Any, subtype: Any, tables: Optional[TaxonomyTables] = None) -> str | None:
    """Return the fixed slot a (kind, subtype) pair belongs to, or ``None``."""
    tables = tables or load_tables()
    slots = tables.subtype_slots.get(kind) if isinstance(kind, str) else None
    if slots is None:
        return None
    return slots.get(normalize_key(subtype, tables))


def apply_taxonomy_gate(items: Iterable[Any],
                        tables: Optional[TaxonomyTables] = None) -> tuple[list[dict[str, Any]], int]:
    """Keep only items whose subtype is inside the fixed taxonomy.

    The gate never rewrites a survivor.  Rewriting would split the stored
    vocabulary between migrated and unmigrated rows, and this task deliberately
    touches new inflow only; an out-of-taxonomy item costs recall instead.
    """
    tables = tables or load_tables()
    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        if not isinstance(item, dict) or taxonomy_slot(item.get("kind"), item.get("subtype"), tables) is None:
            dropped += 1
            continue
        kept.append(dict(item))
    return kept, dropped


class AliasResolver:
    """Map every mention of one target onto a single already-known name.

    The resolver can only ever return a name that the registry, the store, or
    the batch itself already carries, so it never invents an identity.

    Known limitation (measured, pinned by
    ``test_known_limitation_unknown_names_collapse_inside_one_batch``): the
    ambiguity guard only fires when *both* colliding surfaces were already in
    the index.  A first-seen name is registered as this batch walks it, so a
    later, genuinely different person whose stem matches it is merged into it.
    Renames therefore carry a mis-merge risk and are counted separately from
    reference binding (see :meth:`apply`) so the two can be measured apart
    before this layer is ever turned on in production.
    """

    def __init__(self, known_names: Iterable[str] = (), tables: Optional[TaxonomyTables] = None):
        self._tables = tables or load_tables()
        self._index: dict[str, str | None] = {}
        self._registered: set[str] = set()
        for key, canonical in self._tables.alias_canonical.items():
            self._index[key] = canonical
            self._registered.add(key)
        for canonical in dict.fromkeys(self._tables.alias_canonical.values()):
            self._claim(stem_key(canonical, self._tables), canonical, registered=True)
        for name in known_names:
            self.register(name)

    def _claim(self, key: str, surface: str, *, registered: bool = False) -> None:
        if not key:
            return
        if key in self._registered and not registered:
            # The authored registry outranks whatever the store happens to hold.
            return
        current = self._index.get(key, _MISSING)
        if current is _MISSING or current == surface:
            self._index[key] = surface
        else:
            self._index[key] = None
        if registered:
            self._registered.add(key)

    def register(self, surface: Any) -> None:
        """Add one existing name (store row or batch entity) to the index."""
        if not isinstance(surface, str) or not surface or surface in self._tables.protected_names:
            return
        self._claim(normalize_key(surface, self._tables), surface)
        self._claim(stem_key(surface, self._tables), surface)

    def resolve(self, name: Any) -> Any:
        """Return the known name this mention refers to, or the mention itself."""
        if not isinstance(name, str) or not name or name in self._tables.protected_names:
            return name
        for key in (normalize_key(name, self._tables), stem_key(name, self._tables)):
            surface = self._index.get(key)
            if surface:
                return surface
        return name

    def apply(self, items: Iterable[Any]) -> tuple[list[Any], dict[str, int]]:
        """Resolve every name field of a Stage A batch; returns copies.

        The two counters are deliberately not summed.  Renaming an entity is
        the risky axis (it can merge two identities); binding a reference onto
        an entity this batch already names is the safe axis.  A greybox A/B
        that only saw one total could not tell an averted duplicate from an
        averted-but-wrong merge.
        """
        resolved: list[Any] = []
        counts = {"alias_entity_renamed": 0, "alias_reference_bound": 0}
        # Entity names settle first: a reference must attach to the identity
        # this batch just committed to, not to the raw surface it quoted.
        for item in items:
            if not isinstance(item, dict):
                resolved.append(item)
                continue
            copied = dict(item)
            if copied.get("kind") == "entity" and isinstance(copied.get("name"), str):
                name = self.resolve(copied["name"])
                if name != copied["name"]:
                    copied["name"] = name
                    counts["alias_entity_renamed"] += 1
                self.register(name)
            resolved.append(copied)
        for item in resolved:
            if not isinstance(item, dict):
                continue
            for field in ("sourceName", "targetName"):
                value = item.get(field)
                if isinstance(value, str):
                    bound = self.resolve(value)
                    if bound != value:
                        item[field] = bound
                        counts["alias_reference_bound"] += 1
            subjects = item.get("subjectNames")
            if isinstance(subjects, list):
                bound_subjects = [self.resolve(subject) for subject in subjects]
                counts["alias_reference_bound"] += sum(
                    1 for before, after in zip(subjects, bound_subjects) if before != after)
                if bound_subjects != subjects:
                    item["subjectNames"] = bound_subjects
        return resolved, counts
