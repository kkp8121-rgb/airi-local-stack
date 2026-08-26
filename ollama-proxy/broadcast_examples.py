"""Default-off, request-local broadcast style examples."""
from __future__ import annotations

import json
import os


BROADCAST_EXAMPLES_ENV = "AIRI_BROADCAST_EXAMPLES"
BROADCAST_EXAMPLES_MESSAGE_NAME = "airi_broadcast_examples"
BROADCAST_EXAMPLES_STYLE_ONLY_MARKER = (
    "[방송 말투 예시: assistant 예시 줄은 말투 전용이며 결정론 근거에서 제외]"
)
BROADCAST_EXAMPLES_PROMPT = "\n".join((
    BROADCAST_EXAMPLES_STYLE_ONLY_MARKER,
    "U: 오늘 뭐 했어?",
    "A: 오늘은 채팅 보면서 천천히 얘기했어.",
    "U: 오 좋다",
    "A: 응, 나도 그 분위기 좋아.",
    "U: 그 밈 알아?",
    "A: 그건 잘 모르겠는데 반응은 재밌네.",
    "U: 이제 뭐 할까?",
    "A: 일단 지금 얘기 마저 보고 갈게.",
))
_TRUE_VALUES = frozenset({"1", "true", "on", "yes"})


def broadcast_examples_enabled(value: object | None = None) -> bool:
    """Read the opt-in switch; invalid and absent values stay disabled."""
    if value is None:
        value = os.environ.get(BROADCAST_EXAMPLES_ENV, "")
    return isinstance(value, str) and value.strip().casefold() in _TRUE_VALUES


def inject_broadcast_examples(body: bytes, *, authenticated_live_broadcast: bool) -> tuple[bytes, bool]:
    """Add one style-only note after a capability-authenticated live claim."""
    if not authenticated_live_broadcast or not broadcast_examples_enabled():
        return body, False
    try:
        payload = json.loads(body)
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list):
            return body, False
        existing = [
            message for message in messages
            if isinstance(message, dict)
            and message.get("name") == BROADCAST_EXAMPLES_MESSAGE_NAME
        ]
        if existing:
            return body, len(existing) == 1 and existing[0].get("content") == BROADCAST_EXAMPLES_PROMPT
        insert_at = next((
            index for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], dict) and messages[index].get("role") == "user"
        ), len(messages))
        messages.insert(insert_at, {
            "role": "system",
            "name": BROADCAST_EXAMPLES_MESSAGE_NAME,
            "content": BROADCAST_EXAMPLES_PROMPT,
        })
        return json.dumps(payload, ensure_ascii=False).encode("utf-8"), True
    except (TypeError, ValueError, json.JSONDecodeError):
        return body, False
