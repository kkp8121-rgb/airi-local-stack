"""Pure, default-off opener realization for cheer / sincere chat receptions (P2-4b).

The only input is the director's existing priority classification
(``broadcast-director/priority-policy.mjs`` → ``cheer`` | ``sincere_reaction``).
This module never reads viewer text, never names anyone, and renders only the
pinned Korean templates below; the model continues with the actual content,
exactly like the P2-1 thank renderer and the P2-2 aggregation opener.

It is not wired into any runner.  ``select_reception_opener`` is gated by the
``AIRI_RECEPTION_OPENER`` environment flag (default off) so that every existing
path stays byte-identical until a user explicitly enables it.
"""
from __future__ import annotations

import json
import os
import unicodedata
from copy import deepcopy
from typing import Any, Mapping


FLAG_ENV = "AIRI_RECEPTION_OPENER"
_FLAG_ON = frozenset(("1", "true", "on", "yes"))
OUTPUT_SCHEMA_VERSION = "airi.reception-opener.v1"
SUPPORTED_PRIORITIES = ("cheer", "sincere_reaction")
MAX_RENDERED_BYTES = 256
_DIRECTION = "fixed_korean_template"
_POSTCONDITION = "exact_template_only"
# 반말 고정 문구. 이름·수치·새 사실 슬롯이 없고, 존댓말 어미를 쓰지 않는다.
# 호출자가 variant_index를 돌려 같은 문구의 연속 반복을 피한다.
OPENER_TEMPLATES: Mapping[str, tuple[str, ...]] = {
    "cheer": (
        "응원 고마워! 힘 받아서 더 해볼게.",
        "그 말에 힘 난다. 이 기세로 이어갈게.",
        "응원 받았어! 같이 가보자.",
    ),
    "sincere_reaction": (
        "그렇게 말해줘서 고마워. 진심으로 받을게.",
        "마음 전해졌어. 고마워, 이어서 얘기할게.",
        "진심 담긴 말 고마워. 그대로 받아둘게.",
    ),
}


class ReceptionOpenerError(ValueError):
    """Non-reflective failure suitable for evaluator logs."""


def _invalid() -> ReceptionOpenerError:
    return ReceptionOpenerError("reception opener rejected")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def reception_opener_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Default off; only an explicit truthy ``AIRI_RECEPTION_OPENER`` enables it."""
    source = os.environ if environ is None else environ
    return str(source.get(FLAG_ENV, "")).strip().lower() in _FLAG_ON


def render_reception_opener_text(priority: object, variant_index: object) -> str:
    """Return one pinned template; both slots are closed module constants."""
    if type(priority) is not str or priority not in SUPPORTED_PRIORITIES:
        raise _invalid()
    templates = OPENER_TEMPLATES[priority]
    if type(variant_index) is not int or not 0 <= variant_index < len(templates):
        raise _invalid()
    return templates[variant_index]


def render_reception_opener(priority: object, variant_index: object) -> dict[str, str]:
    """Return a fixed artifact; caller content is neither accepted nor copied."""
    text = render_reception_opener_text(priority, variant_index)
    rendered = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "priority": priority,
        "direction": _DIRECTION,
        "postcondition": _POSTCONDITION,
        "text": text,
    }
    return validate_rendered_reception_opener(rendered, expected_priority=priority)


def validate_rendered_reception_opener(value: object, *, expected_priority: object = None) -> dict[str, str]:
    """Structural postcondition only: the text must be exactly one pinned template."""
    if type(value) is not dict or list(value) != ["schema_version", "priority", "direction", "postcondition", "text"]:
        raise _invalid()
    if any(type(value[key]) is not str for key in value):
        raise _invalid()
    priority, text = value["priority"], value["text"]
    if (
        value["schema_version"] != OUTPUT_SCHEMA_VERSION
        or priority not in SUPPORTED_PRIORITIES
        or (expected_priority is not None and priority != expected_priority)
        or (value["direction"], value["postcondition"]) != (_DIRECTION, _POSTCONDITION)
        or unicodedata.normalize("NFC", text) != text
        or text not in OPENER_TEMPLATES[priority]
        or len(canonical_bytes(value)) > MAX_RENDERED_BYTES
    ):
        raise _invalid()
    return deepcopy(value)


def select_reception_opener(priority: object, variant_index: object,
                            environ: Mapping[str, str] | None = None) -> dict[str, str] | None:
    """Flag-gated entry point for a runner.

    Returns ``None`` when the flag is off or the director priority is one this
    module does not own (``question``, ``topic_expansion``, ``positive``), so an
    off path and an unsupported priority both leave the turn untouched.
    """
    if not reception_opener_enabled(environ):
        return None
    if type(priority) is not str:
        raise _invalid()
    if priority not in SUPPORTED_PRIORITIES:
        return None
    return render_reception_opener(priority, variant_index)
