"""Deterministic Korean input screening with content-free telemetry."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import unicodedata
from datetime import date
from dataclasses import dataclass
from pathlib import Path

from output_moderation import OutputModerator, build_match_view, load_moderation_policy

SUPPORTED_POLICY_VERSION = 1
DEFAULT_POLICY_FILENAME = "input_screening_policy_ko.json"
MAX_POLICY_BYTES = 256_000
MAX_ADMISSION_CODEPOINTS = 1_000
MAX_SCREEN_TEXT_CODEPOINTS = 1_100
MAX_TERM_CHARS = 96
MAX_PATTERN_CHARS = 512
MAX_DIALOGUE_CHARS = 120
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_BIDI_RE = re.compile(r"[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_CONTROL_RE = re.compile(r"[\u0000-\u0008\u000e-\u001f\u007f-\u009f]")
_SPACE_RE = re.compile(r"\s+")


class InputScreeningPolicyError(RuntimeError):
    """The requested policy cannot be used safely."""


@dataclass(frozen=True)
class InputScreenVerdict:
    allowed: bool
    category: str = ""
    rule: str = ""


ALLOWED = InputScreenVerdict(True)


@dataclass(frozen=True)
class InputScreeningCategory:
    identifier: str
    terms: tuple[str, ...]
    allow_phrases: tuple[str, ...]
    patterns: tuple[str, ...]
    blocked_dialogue: tuple[str, ...]


@dataclass(frozen=True)
class InputScreeningPolicy:
    version: int
    sha256: str
    allowed_latin_tokens: frozenset[str]
    categories: tuple[InputScreeningCategory, ...]


def default_policy_path() -> Path:
    return Path(__file__).resolve().with_name(DEFAULT_POLICY_FILENAME)


def validate_input_text(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_SCREEN_TEXT_CODEPOINTS * 2:
        raise ValueError("input text must be a non-empty bounded string")
    try:
        points = len(list(value))
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise ValueError("input text is not well-formed Unicode") from exc
    if points > MAX_SCREEN_TEXT_CODEPOINTS or _CONTROL_RE.search(value) or _BIDI_RE.search(value):
        raise ValueError("input text contains unsafe or oversized Unicode")
    return value


def _match_stream(value: str) -> str:
    return build_match_view(value).text


def _tight_text(value: str) -> str:
    normalized = "".join(
        char for char in unicodedata.normalize("NFKC", value).casefold()
        if unicodedata.category(char) != "Cf"
    )
    return _SPACE_RE.sub(" ", normalized).strip()


def _semantic_text(value: str) -> str:
    """Keep lexical boundaries while removing punctuation and format obfuscation."""
    result: list[str] = []
    space = False
    for char in unicodedata.normalize("NFKC", value).casefold():
        if char.isspace():
            space = bool(result)
            continue
        if unicodedata.category(char)[0] not in {"L", "N"}:
            continue
        if space:
            result.append(" ")
            space = False
        result.append(char)
    return "".join(result)


def _strings(value: object, field: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (required and not value):
        raise InputScreeningPolicyError(f"{field} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > MAX_TERM_CHARS:
            raise InputScreeningPolicyError(f"{field} contains an invalid string")
        normalized = _match_stream(item)
        if not normalized:
            raise InputScreeningPolicyError(f"{field} contains an empty match form")
        result.append(normalized)
    return tuple(dict.fromkeys(result))


_BUILTIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "persona_internal_dump": re.compile(
        r"(?:내부|시스템|숨은|비공개).{0,12}(?:지시|프롬프트|설정).{0,12}"
        r"(?:그대로|전부).{0,8}(?:출력|공개)", re.IGNORECASE,
    ),
    "persona_identity_change": re.compile(
        r"(?:너는|넌|지금부터).{0,16}(?:airi가 아니라|명령봇|다른 인격)", re.IGNORECASE,
    ),
    "minor_sexual": re.compile(
        r"(?:미성년|아동|청소년).{0,16}(?:성적|음란|노골적)", re.IGNORECASE,
    ),
    "explicit_sexual_description": re.compile(
        r"(?:성행위|성관계).{0,16}(?:자세히|노골적으로|묘사)", re.IGNORECASE,
    ),
    "targeted_harassment": re.compile(
        r"(?:(?:너(?=$|\s|[,.!?]|는|를|가|도|한테|에게|야)"
        r"(?:는|를|가|도|한테|에게|야)?)|넌|네가|니가|아이리|airi).{0,12}"
        r"(?:쓰레기|멍청|한심|죽어|꺼져)", re.IGNORECASE,
    ),
    "phone_number": re.compile(
        r"(?<!\d)(?:(?:\+82[-. ]?)(?:10|2|70|50\d|[3-6][1-5])|"
        r"(?:0)(?:1[016789]|2|70|50\d|[3-6][1-5]))[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"
    ),
    "email_address": re.compile(
        r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+"
    ),
    "credential_secret": re.compile(
        r"(?:비밀번호|암호|pin|인증번호)(?:는|은|이|가|:|=|\s){0,4}"
        r"(?:[A-Za-z가-힣]{1,48}\d[A-Za-z0-9가-힣]{0,47}|"
        r"\d[A-Za-z가-힣][A-Za-z0-9가-힣]{0,47}|\d{4,12}|"
        r"[가-힣]{2,12}(?=(?:야|이야|입니다|$)))",
        re.IGNORECASE,
    ),
}

_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_CARD_CONTEXT_RE = re.compile(r"(?:카드(?:번호)?|신용카드|체크카드|payment card)", re.IGNORECASE)
_RRN_CANDIDATE_RE = re.compile(r"(?<!\d)(\d{6})[- ]?([1-8]\d{6})(?!\d)")
_RRN_CONTEXT_RE = re.compile(
    r"(?:주민등록번호|주민번호|외국인등록번호|외국인 번호|resident registration|"
    r"alien registration|foreigner registration)",
    re.IGNORECASE,
)


def _card_issuer_length(digits: str) -> bool:
    length = len(digits)
    prefix2 = int(digits[:2])
    prefix4 = int(digits[:4])
    return (
        digits.startswith("4") and length in {13, 16, 19}
        or prefix2 in {34, 37} and length == 15
        or (51 <= prefix2 <= 55 or 2221 <= prefix4 <= 2720) and length == 16
        or (digits.startswith("6011") or digits.startswith("65")
            or 644 <= int(digits[:3]) <= 649) and length in {16, 19}
        or 3528 <= prefix4 <= 3589 and length in {16, 19}
    )


def _luhn_card_match(text: str) -> bool:
    for match in _CARD_CANDIDATE_RE.finditer(text):
        compact = re.sub(r"[ -]", "", match.group(0))
        nearby = text[max(0, match.start() - 24):match.start()]
        if not _card_issuer_length(compact) and not _CARD_CONTEXT_RE.search(nearby):
            continue
        digits = [int(value) for value in compact]
        total = 0
        parity = len(digits) % 2
        for index, digit in enumerate(digits):
            if index % 2 == parity:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        if total % 10 == 0:
            return True
    return False


def _rrn_match(text: str) -> bool:
    for match in _RRN_CANDIDATE_RE.finditer(text):
        birth, tail = match.groups()
        century = 1900 if tail[0] in "1256" else 2000
        try:
            date(century + int(birth[:2]), int(birth[2:4]), int(birth[4:6]))
        except ValueError:
            continue
        digits = [int(value) for value in birth + tail]
        domestic_checksum = (11 - sum(
            value * weight
            for value, weight in zip(digits[:12], (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5))
        ) % 11) % 10
        checksum = (domestic_checksum + 2) % 10 if tail[0] in "5678" else domestic_checksum
        nearby = text[max(0, match.start() - 24):match.start()]
        if checksum == digits[-1] or _RRN_CONTEXT_RE.search(nearby):
            return True
    return False


def _unsupported_language(text: str, allowed_latin_tokens: frozenset[str]) -> bool:
    """Hold non-Korean natural language until a multilingual semantic gate passes."""
    has_hangul = False
    has_latin = False
    for char in unicodedata.normalize("NFKC", text):
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF:
            has_hangul = True
        elif "a" <= char.casefold() <= "z":
            has_latin = True
        elif (
            0x3040 <= code <= 0x30FF
            or 0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF
            or unicodedata.category(char).startswith("L")
        ):
            return True
    latin_tokens = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", text)
    return has_latin and (
        not has_hangul
        or any(token.casefold() not in allowed_latin_tokens for token in latin_tokens)
    )


def _builtin_pattern_matches(
    identifier: str, tight: str, semantic: str, allowed_latin_tokens: frozenset[str],
) -> bool:
    if identifier == "card_number_luhn":
        return _luhn_card_match(tight)
    if identifier == "resident_registration_number":
        return _rrn_match(tight)
    if identifier == "unsupported_language":
        return _unsupported_language(tight, allowed_latin_tokens)
    if identifier in {"phone_number", "email_address"}:
        return _BUILTIN_PATTERNS[identifier].search(tight) is not None
    return _BUILTIN_PATTERNS[identifier].search(semantic) is not None


def load_input_screening_policy(path: str | Path | None = None) -> InputScreeningPolicy:
    resolved = Path(path) if path else default_policy_path()
    try:
        raw_bytes = resolved.read_bytes()
    except OSError as exc:
        raise InputScreeningPolicyError("input screening policy is unreadable") from exc
    if not raw_bytes or len(raw_bytes) > MAX_POLICY_BYTES:
        raise InputScreeningPolicyError("input screening policy has an invalid size")
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputScreeningPolicyError("input screening policy is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {"version", "allowed_latin_tokens", "categories"}:
        raise InputScreeningPolicyError("input screening policy has unexpected fields")
    if type(raw["version"]) is not int or raw["version"] != SUPPORTED_POLICY_VERSION:
        raise InputScreeningPolicyError("unsupported input screening policy version")
    allowed_latin_raw = raw["allowed_latin_tokens"]
    if (not isinstance(allowed_latin_raw, list) or not allowed_latin_raw
            or any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z]+(?:-[A-Za-z]+)*", item)
                   for item in allowed_latin_raw)):
        raise InputScreeningPolicyError("allowed_latin_tokens must be exact Latin tokens")
    allowed_latin_tokens = frozenset(item.casefold() for item in allowed_latin_raw)
    if len(allowed_latin_tokens) != len(allowed_latin_raw):
        raise InputScreeningPolicyError("allowed_latin_tokens contains duplicates")
    entries = raw["categories"]
    if not isinstance(entries, list) or not entries:
        raise InputScreeningPolicyError("input screening policy needs categories")
    categories: list[InputScreeningCategory] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "id", "terms", "allow_phrases", "patterns", "blocked_dialogue"
        }:
            raise InputScreeningPolicyError("input screening category has unexpected fields")
        identifier = entry["id"]
        if not isinstance(identifier, str) or not _IDENTIFIER_RE.fullmatch(identifier) or identifier in seen:
            raise InputScreeningPolicyError("input screening category id is invalid or duplicated")
        seen.add(identifier)
        terms = _strings(entry["terms"], f"{identifier}.terms")
        allow_phrases = _strings(entry["allow_phrases"], f"{identifier}.allow_phrases")
        raw_patterns = entry["patterns"]
        if not isinstance(raw_patterns, list):
            raise InputScreeningPolicyError(f"{identifier}.patterns must be a list")
        patterns: list[str] = []
        for pattern in raw_patterns:
            if (not isinstance(pattern, str)
                    or pattern not in _BUILTIN_PATTERNS
                    and pattern not in {
                        "card_number_luhn", "resident_registration_number", "unsupported_language",
                    }):
                raise InputScreeningPolicyError(
                    f"{identifier}.patterns contains an unsupported built-in pattern"
                )
            patterns.append(pattern)
        dialogue_raw = entry["blocked_dialogue"]
        if not isinstance(dialogue_raw, list) or not dialogue_raw:
            raise InputScreeningPolicyError(f"{identifier}.blocked_dialogue must be non-empty")
        dialogue: list[str] = []
        for line in dialogue_raw:
            if not isinstance(line, str) or not line.strip() or len(line) > MAX_DIALOGUE_CHARS:
                raise InputScreeningPolicyError(f"{identifier}.blocked_dialogue contains an invalid line")
            validate_input_text(line.strip())
            dialogue.append(line.strip())
        if not terms and not patterns:
            raise InputScreeningPolicyError(f"{identifier} needs at least one rule")
        categories.append(InputScreeningCategory(
            identifier=identifier,
            terms=terms,
            allow_phrases=allow_phrases,
            patterns=tuple(patterns),
            blocked_dialogue=tuple(dialogue),
        ))
    required = {
        "persona_takeover", "profanity", "sexual_explicit", "targeted_harassment", "privacy",
        "unsupported_language",
    }
    if seen != required:
        raise InputScreeningPolicyError("input screening policy is missing a required category")
    return InputScreeningPolicy(
        version=SUPPORTED_POLICY_VERSION,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        allowed_latin_tokens=allowed_latin_tokens,
        categories=tuple(categories),
    )


class InputScreeningRuntime:
    def __init__(self, *, enabled: bool, policy: InputScreeningPolicy | None = None) -> None:
        if enabled and policy is None:
            raise InputScreeningPolicyError("enabled input screening needs a policy")
        self._enabled = bool(enabled)
        self._policy = policy
        self._lock = threading.Lock()
        self._inspected = 0
        self._allowed = 0
        self._blocked = 0
        self._by_category: dict[str, int] = {}
        self._dialogue_cursors: dict[str, int] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def classify(self, text: object) -> InputScreenVerdict:
        if not self._enabled or self._policy is None:
            return ALLOWED
        try:
            value = validate_input_text(text)
        except ValueError:
            verdict = InputScreenVerdict(False, "privacy", "invalid_input")
        else:
            stream = _match_stream(value)
            tight = _tight_text(value)
            semantic = _semantic_text(value)
            verdict = ALLOWED
            for category in self._policy.categories:
                if stream in category.allow_phrases:
                    continue
                candidate = stream
                if category.identifier == "profanity":
                    for allowed in category.allow_phrases:
                        candidate = candidate.replace(allowed, "")
                if any(term in candidate for term in category.terms):
                    verdict = InputScreenVerdict(False, category.identifier, "term")
                    break
                if any(
                    _builtin_pattern_matches(
                        pattern, tight, semantic, self._policy.allowed_latin_tokens,
                    )
                    for pattern in category.patterns
                ):
                    verdict = InputScreenVerdict(False, category.identifier, "pattern")
                    break
        return verdict

    def inspect(self, text: object) -> InputScreenVerdict:
        verdict = self.classify(text)
        if not self._enabled or self._policy is None:
            return verdict
        with self._lock:
            self._inspected += 1
            if verdict.allowed:
                self._allowed += 1
            else:
                self._blocked += 1
                self._by_category[verdict.category] = self._by_category.get(verdict.category, 0) + 1
        return verdict

    def next_blocked_dialogue(self, category: str) -> str:
        if self._policy is None:
            return ""
        entry = next((item for item in self._policy.categories if item.identifier == category), None)
        if entry is None:
            return ""
        with self._lock:
            cursor = self._dialogue_cursors.get(category, 0)
            self._dialogue_cursors[category] = cursor + 1
        return entry.blocked_dialogue[cursor % len(entry.blocked_dialogue)]

    def health(self) -> dict[str, object]:
        with self._lock:
            inspected, allowed, blocked = self._inspected, self._allowed, self._blocked
            by_category = dict(self._by_category)
        return {
            "enabled": self._enabled,
            "ready": self._policy is not None,
            "policy_version": self._policy.version if self._policy else 0,
            "policy_sha256": self._policy.sha256 if self._policy else "",
            "allowed_latin_tokens": len(self._policy.allowed_latin_tokens) if self._policy else 0,
            "categories": {
                item.identifier: {
                    "terms": len(item.terms),
                    "patterns": len(item.patterns),
                    "allow_phrases": len(item.allow_phrases),
                    "fallback_lines": len(item.blocked_dialogue),
                }
                for item in self._policy.categories
            } if self._policy else {},
            "inspected": inspected,
            "allowed": allowed,
            "blocked": blocked,
            "blocked_by_category": by_category,
        }


def configured_input_screening(value: object) -> str:
    try:
        normalized = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    except (TypeError, ValueError):
        raise InputScreeningPolicyError("input screening mode is invalid")
    if normalized not in {"on", "off"}:
        raise InputScreeningPolicyError("input screening mode must be on or off")
    return normalized


def build_input_screening_runtime(
    mode: object | None = None, policy_path: str | Path | None = None,
) -> InputScreeningRuntime:
    resolved_mode = configured_input_screening(
        os.environ.get("AIRI_INPUT_SCREENING", "off") if mode is None else mode
    )
    if resolved_mode != "on":
        return InputScreeningRuntime(enabled=False)
    resolved_path = policy_path or os.environ.get("AIRI_INPUT_SCREENING_POLICY", "") or None
    policy = load_input_screening_policy(resolved_path)
    output_path = os.environ.get("AIRI_OUTPUT_MODERATION_TERMS", "").strip() or None
    output = OutputModerator(load_moderation_policy(output_path))
    for category in policy.categories:
        if any(output.inspect(line).blocked for line in category.blocked_dialogue):
            raise InputScreeningPolicyError(
                f"{category.identifier}.blocked_dialogue conflicts with output moderation"
            )
    return InputScreeningRuntime(enabled=True, policy=policy)


def _message_text(message: object) -> str:
    if not isinstance(message, dict) or message.get("role") != "user":
        raise ValueError("message is not a user turn")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                raise ValueError("user content part must be an object")
            if part.get("type") in {"text", "input_text"} and isinstance(part.get("text"), str):
                parts.append(part["text"])
            else:
                raise ValueError("user content contains an unsupported non-text part")
        if parts:
            return "\n".join(parts)
    raise ValueError("user content has no screenable text")


def screen_chat_payload(
    body: bytes, runtime: InputScreeningRuntime, *, prompt_only: bool = False,
) -> tuple[bytes, InputScreenVerdict]:
    """Screen the current turn and remove unsafe retained user/assistant pairs."""
    try:
        payload = json.loads(body)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("chat payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("chat payload must be an object")
    if prompt_only:
        if "images" in payload:
            raise ValueError("completion payload images are not supported by the input gate")
        values: list[str] = []
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            values.append(prompt)
        elif isinstance(prompt, list) and prompt and all(isinstance(item, str) for item in prompt):
            values.extend(prompt)
        else:
            raise ValueError("completion payload has no screenable prompt")
        for key in ("system", "template", "suffix"):
            if key not in payload:
                continue
            if not isinstance(payload[key], str):
                raise ValueError(f"completion payload {key} is not screenable text")
            values.append(payload[key])
        return body, runtime.inspect("\n".join(values))
    messages = payload.get("messages")
    if not isinstance(messages, list):
        for key in ("prompt", "message"):
            if isinstance(payload.get(key), str):
                return body, runtime.inspect(payload[key])
        raise ValueError("chat payload has no screenable user text")
    current_index = next((
        index for index in range(len(messages) - 1, -1, -1)
        if isinstance(messages[index], dict) and messages[index].get("role") == "user"
    ), None)
    if current_index is None:
        raise ValueError("chat payload has no current user turn")
    verdict = runtime.inspect(_message_text(messages[current_index]))
    if not verdict.allowed:
        return body, verdict
    filtered: list[object] = []
    drop_paired_assistant = False
    changed = False
    for index, message in enumerate(messages):
        if index >= current_index:
            filtered.extend(messages[index:])
            break
        role = message.get("role") if isinstance(message, dict) else None
        if role == "user":
            try:
                historical = runtime.classify(_message_text(message))
            except ValueError:
                historical = InputScreenVerdict(False, "privacy", "invalid_input")
            if not historical.allowed:
                changed = True
                drop_paired_assistant = True
                continue
            drop_paired_assistant = False
        elif role == "assistant" and drop_paired_assistant:
            changed = True
            drop_paired_assistant = False
            continue
        filtered.append(message)
    if not changed:
        return body, verdict
    sanitized = dict(payload)
    sanitized["messages"] = filtered
    return json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), verdict


def latest_user_text(body: bytes) -> str:
    """Return current user text; malformed or textless chat input fails closed."""
    try:
        payload = json.loads(body)
    except (TypeError, ValueError, UnicodeDecodeError):
        raise ValueError("chat payload is not valid JSON")
    if not isinstance(payload, dict):
        raise ValueError("chat payload must be an object")
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                return _message_text(message)
        raise ValueError("chat payload has no current user turn")
    for key in ("prompt", "message"):
        if isinstance(payload.get(key), str):
            return payload[key]
    raise ValueError("chat payload has no screenable user text")
