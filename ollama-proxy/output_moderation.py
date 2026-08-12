"""한국어 출력 모더레이션 게이트 — 방송 트랙 B3.

한국어를 지원하는 기성 가드 모델이 없다(Llama Guard·ShieldGemma·Detoxify 모두
한국어 미지원 확정). 그래서 금칙어 사전과 정규식 필터를 직접 구성하고, 문장이
TTS로 나가기 직전 지점에서만 판정한다.

설계 요약
- 사전은 코드가 아니라 데이터 파일(``moderation_terms_ko.json``)에 있고, 경로는
  런타임 env로 교체할 수 있다. 코드에는 어떤 금칙어도 하드코딩하지 않는다.
- 우회 표기 3종을 정규화 한 번으로 흡수한다.
  1. 자모 분리 — 음절을 자모로 풀어 쓴 표기
  2. 특수문자 삽입 — 글자 사이에 기호를 끼워 넣은 표기
  3. 띄어쓰기 변형 — 한 낱말을 공백으로 쪼갠 표기
  판정 문자열은 항상 "호환 자모로 완전히 푼 스트림"이라, 합성형·분해형이 섞여
  있어도 같은 결과가 나온다.
- 정상 단어 오차단(false positive)은 세 겹으로 막는다.
  1. 음절 경계 규칙 — 매치가 음절 시작에서 시작하고 음절 경계에서 끝나야 한다.
     자모 스트림에서만 우연히 이어 붙는 매치를 제거한다.
  2. 토큰 경계 규칙 — 공백을 건너뛴 매치는 토큰의 시작과 끝에 정렬돼야 한다.
     서로 다른 두 낱말의 꼬리와 머리가 붙어 만들어지는 매치를 제거한다.
  3. allowlist — 위 두 규칙으로도 남는 실제 낱말 충돌을 데이터로 예외 처리한다.
- 판정 결과는 원문을 보관하지 않는다. 카테고리와 규칙 종류만 남긴다.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TERMS_FILENAME = "moderation_terms_ko.json"
SUPPORTED_POLICY_VERSION = 1
MAX_TERM_CHARS = 64
MAX_PATTERN_CHARS = 512
MAX_DIALOGUE_CHARS = 120

_HANGUL_BASE = 0xAC00
_HANGUL_COUNT = 11172
_LEAD_JAMO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_VOWEL_JAMO = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_TAIL_JAMO = "ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

_LEAD_INDEX = {char: index for index, char in enumerate(_LEAD_JAMO)}
_VOWEL_INDEX = {char: index for index, char in enumerate(_VOWEL_JAMO)}
_TAIL_INDEX = {char: index + 1 for index, char in enumerate(_TAIL_JAMO)}

# NFKC는 낱개로 남은 조합용 자모(U+1100 블록)를 호환 자모로 바꾸지 않는다.
# 판정 스트림을 한 가지 표기로 모으기 위해 직접 대응시킨다.
_CONJOINING_JAMO = {}
for _index, _char in enumerate(_LEAD_JAMO):
    _CONJOINING_JAMO[chr(0x1100 + _index)] = _char
for _index, _char in enumerate(_VOWEL_JAMO):
    _CONJOINING_JAMO[chr(0x1161 + _index)] = _char
for _index, _char in enumerate(_TAIL_JAMO):
    _CONJOINING_JAMO[chr(0x11A8 + _index)] = _char

_WHITESPACE_RE = re.compile(r"\s+")


class ModerationPolicyError(RuntimeError):
    """사전 파일을 읽지 못했거나 스키마가 깨졌을 때 발생한다."""


@dataclass(frozen=True)
class ModerationVerdict:
    """한 문장에 대한 판정. 원문·매치 문자열은 일부러 담지 않는다."""

    blocked: bool
    category: str = ""
    rule: str = ""

    def as_signal(self) -> dict[str, object]:
        """클라이언트가 "필터당함"을 표시할 수 있는 최소 메타데이터."""
        return {
            "blocked": self.blocked,
            "category": self.category,
            "rule": self.rule,
        }


ALLOWED = ModerationVerdict(False)


@dataclass(frozen=True)
class _MatchView:
    """자모로 푼 판정 스트림과 그 경계 정보."""

    text: str
    syllable_start: tuple[bool, ...]
    token_start: tuple[bool, ...]
    token_end: tuple[bool, ...]


@dataclass(frozen=True)
class ModerationCategory:
    identifier: str
    label: str
    term_count: int
    pattern_count: int
    matchers: tuple[tuple[re.Pattern[str], tuple[str, ...], bool], ...]
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class ModerationPolicy:
    version: int
    source: str
    categories: tuple[ModerationCategory, ...]
    allowlist: tuple[str, ...]
    allowlist_count: int
    blocked_dialogue: tuple[str, ...]

    def counts(self) -> dict[str, dict[str, int]]:
        """카테고리별 사전 규모. 항목 원문은 노출하지 않는다."""
        return {
            category.identifier: {
                "terms": category.term_count,
                "patterns": category.pattern_count,
            }
            for category in self.categories
        }


def decompose_hangul(text: str) -> str:
    """한글 음절을 호환 자모로 푼다. 자모 분리 표기를 만들 때도 쓴다."""
    pieces: list[str] = []
    for char in text:
        code = ord(char) - _HANGUL_BASE
        if 0 <= code < _HANGUL_COUNT:
            lead, rest = divmod(code, 588)
            vowel, tail = divmod(rest, 28)
            pieces.append(_LEAD_JAMO[lead])
            pieces.append(_VOWEL_JAMO[vowel])
            if tail:
                pieces.append(_TAIL_JAMO[tail - 1])
        else:
            pieces.append(_CONJOINING_JAMO.get(char, char))
    return "".join(pieces)


def _syllable_starts(stream: str) -> list[bool]:
    """자모 스트림에서 각 위치가 음절의 첫 자모인지 표시한다."""
    length = len(stream)
    starts = [False] * length
    index = 0
    while index < length:
        starts[index] = True
        char = stream[index]
        if char in _LEAD_INDEX and index + 1 < length and stream[index + 1] in _VOWEL_INDEX:
            end = index + 2
            if (
                end < length
                and stream[end] in _TAIL_INDEX
                and not (end + 1 < length and stream[end + 1] in _VOWEL_INDEX)
            ):
                end += 1
            index = end
        else:
            index += 1
    return starts


def build_match_view(text: str) -> _MatchView:
    """판정용 자모 스트림과 음절·토큰 경계를 함께 만든다."""
    normalized = unicodedata.normalize("NFKC", text)
    stream: list[str] = []
    token_start: list[bool] = []
    token_open = False
    for char in normalized:
        if char.isspace():
            token_open = False
            continue
        if unicodedata.category(char)[0] not in ("L", "N"):
            # 글자 사이에 끼워 넣은 기호는 버리되 토큰을 끊지는 않는다.
            continue
        pieces = decompose_hangul(char)
        if pieces == char:
            lowered = char.lower()
            pieces = lowered if len(lowered) == 1 else char
        for offset, piece in enumerate(pieces):
            stream.append(piece)
            token_start.append(not token_open and offset == 0)
        token_open = True
    length = len(stream)
    token_end = [
        index + 1 == length or token_start[index + 1] for index in range(length)
    ]
    joined = "".join(stream)
    return _MatchView(
        text=joined,
        syllable_start=tuple(_syllable_starts(joined)),
        token_start=tuple(token_start),
        token_end=tuple(token_end),
    )


def normalize_for_match(text: str) -> str:
    """판정 스트림만 돌려준다. 진단·테스트용."""
    return build_match_view(text).text


def _needle(term: str) -> str:
    return build_match_view(term).text


def _compile_terms(terms: list[str]) -> tuple[re.Pattern[str], tuple[str, ...]] | None:
    """빠른 사전 필터 하나와 개별 검증용 needle 목록을 함께 만든다.

    교대(alternation) 하나로만 판정하면, 한 항목이 다른 항목의 앞부분일 때
    긴 쪽이 먼저 매치돼 경계 검사에서 탈락하고 짧은 쪽은 시도조차 되지
    않는다. 그래서 교대는 "이 문장에 볼 게 있는가"만 걸러내고, 실제 판정은
    항목별로 다시 확인한다.
    """
    needles = sorted({_needle(term) for term in terms if _needle(term)}, key=len, reverse=True)
    if not needles:
        return None
    pattern = re.compile("|".join(re.escape(needle) for needle in needles))
    return pattern, tuple(needles)


def _validated_terms(raw: object, field: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ModerationPolicyError(f"{field} must be a list")
    terms: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ModerationPolicyError(f"{field} must contain only strings")
        term = item.strip()
        if not term or len(term) > MAX_TERM_CHARS:
            raise ModerationPolicyError(f"{field} has an empty or oversized entry")
        terms.append(term)
    return terms


def _compiled_patterns(raw: object, field: str) -> tuple[re.Pattern[str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ModerationPolicyError(f"{field} must be a list")
    compiled: list[re.Pattern[str]] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ModerationPolicyError(f"{field} must contain non-empty strings")
        if len(item) > MAX_PATTERN_CHARS:
            raise ModerationPolicyError(f"{field} has an oversized pattern")
        try:
            compiled.append(re.compile(item))
        except re.error as exc:
            raise ModerationPolicyError(f"{field} has an invalid pattern") from exc
    return tuple(compiled)


def default_terms_path() -> Path:
    return Path(__file__).resolve().parent / DEFAULT_TERMS_FILENAME


def load_moderation_policy(path: str | Path | None = None) -> ModerationPolicy:
    """사전 파일을 읽어 판정 정책을 만든다. 스키마 위반은 즉시 예외."""
    resolved = Path(path) if path else default_terms_path()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModerationPolicyError(f"moderation terms unreadable: {resolved}") from exc
    except json.JSONDecodeError as exc:
        raise ModerationPolicyError(f"moderation terms are not valid JSON: {resolved}") from exc
    if not isinstance(raw, dict):
        raise ModerationPolicyError("moderation terms must be a JSON object")
    version = raw.get("version")
    if version != SUPPORTED_POLICY_VERSION:
        raise ModerationPolicyError(f"unsupported moderation policy version: {version!r}")

    raw_categories = raw.get("categories")
    if not isinstance(raw_categories, list) or not raw_categories:
        raise ModerationPolicyError("moderation policy needs at least one category")
    categories: list[ModerationCategory] = []
    seen: set[str] = set()
    for entry in raw_categories:
        if not isinstance(entry, dict):
            raise ModerationPolicyError("each category must be a JSON object")
        identifier = str(entry.get("id", "")).strip()
        if not identifier or identifier in seen:
            raise ModerationPolicyError("category ids must be present and unique")
        seen.add(identifier)
        terms = _validated_terms(entry.get("terms"), f"{identifier}.terms")
        token_start_terms = _validated_terms(
            entry.get("token_start_terms"), f"{identifier}.token_start_terms"
        )
        patterns = _compiled_patterns(entry.get("patterns"), f"{identifier}.patterns")
        matchers: list[tuple[re.Pattern[str], tuple[str, ...], bool]] = []
        free = _compile_terms(terms)
        if free is not None:
            matchers.append((free[0], free[1], False))
        anchored = _compile_terms(token_start_terms)
        if anchored is not None:
            matchers.append((anchored[0], anchored[1], True))
        categories.append(
            ModerationCategory(
                identifier=identifier,
                label=str(entry.get("label", identifier)),
                term_count=len(terms) + len(token_start_terms),
                pattern_count=len(patterns),
                matchers=tuple(matchers),
                patterns=patterns,
            )
        )

    allowlist_terms = _validated_terms(raw.get("allowlist"), "allowlist")
    compiled_allowlist = _compile_terms(allowlist_terms)
    allowlist = compiled_allowlist[1] if compiled_allowlist is not None else ()

    raw_dialogue = raw.get("blocked_dialogue")
    if not isinstance(raw_dialogue, list) or not raw_dialogue:
        raise ModerationPolicyError("blocked_dialogue must be a non-empty list")
    dialogue: list[str] = []
    for item in raw_dialogue:
        if not isinstance(item, str):
            raise ModerationPolicyError("blocked_dialogue must contain only strings")
        line = item.strip()
        if not line or len(line) > MAX_DIALOGUE_CHARS:
            raise ModerationPolicyError("blocked_dialogue has an empty or oversized line")
        dialogue.append(line)

    return ModerationPolicy(
        version=SUPPORTED_POLICY_VERSION,
        source=str(resolved),
        categories=tuple(categories),
        allowlist=allowlist,
        allowlist_count=len(allowlist_terms),
        blocked_dialogue=tuple(dialogue),
    )


class OutputModerator:
    """정책 하나를 들고 문장 단위 판정만 수행하는 순수 컴포넌트."""

    def __init__(self, policy: ModerationPolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> ModerationPolicy:
        return self._policy

    def inspect(self, text: str) -> ModerationVerdict:
        if not text or not text.strip():
            return ALLOWED
        tight = _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", text))
        view = build_match_view(text)
        allow_spans: tuple[tuple[int, int], ...] | None = None
        for category in self._policy.categories:
            for pattern in category.patterns:
                if pattern.search(tight):
                    return ModerationVerdict(True, category.identifier, "pattern")
            if not view.text:
                continue
            for prefilter, needles, require_token_start in category.matchers:
                if prefilter.search(view.text) is None:
                    continue
                for needle in needles:
                    position = view.text.find(needle)
                    while position >= 0:
                        end = position + len(needle)
                        if self._accepts(view, position, end, require_token_start):
                            if allow_spans is None:
                                allow_spans = self._allow_spans(view)
                            if not any(
                                span_start <= position and end <= span_end
                                for span_start, span_end in allow_spans
                            ):
                                return ModerationVerdict(True, category.identifier, "term")
                        position = view.text.find(needle, position + 1)
        return ALLOWED

    def _allow_spans(self, view: _MatchView) -> tuple[tuple[int, int], ...]:
        """예외 낱말도 같은 경계 규칙을 통과한 매치만 인정한다.

        경계 검사를 건너뛰면 예외 항목의 꼬리가 뒤 낱말의 머리와 우연히 이어
        붙어, 실제 차단 대상까지 덮어 버린다.
        """
        spans: list[tuple[int, int]] = []
        for needle in self._policy.allowlist:
            position = view.text.find(needle)
            while position >= 0:
                end = position + len(needle)
                if self._syllable_aligned(view, position, end):
                    spans.append((position, end))
                position = view.text.find(needle, position + 1)
        return tuple(spans)

    @staticmethod
    def _syllable_aligned(view: _MatchView, start: int, end: int) -> bool:
        """자모 스트림에서만 우연히 이어 붙은 매치를 걸러낸다."""
        if not view.syllable_start[start]:
            return False
        return end >= len(view.text) or view.syllable_start[end]

    @classmethod
    def _accepts(cls, view: _MatchView, start: int, end: int, require_token_start: bool) -> bool:
        if not cls._syllable_aligned(view, start, end):
            return False
        if require_token_start and not view.token_start[start]:
            return False
        crosses_token = any(view.token_start[index] for index in range(start + 1, end))
        if crosses_token and not (view.token_start[start] and view.token_end[end - 1]):
            return False
        return True


class OutputModerationRuntime:
    """프록시가 들고 다니는 게이트 상태 — 판정·폴백 대사·카운터."""

    def __init__(
        self,
        *,
        enabled: bool,
        policy: ModerationPolicy | None = None,
    ) -> None:
        if enabled and policy is None:
            raise ModerationPolicyError("an enabled moderation runtime needs a policy")
        self._enabled = bool(enabled)
        self._policy = policy
        self._moderator = OutputModerator(policy) if policy is not None else None
        self._lock = threading.Lock()
        self._inspected = 0
        self._blocked = 0
        self._by_category: dict[str, int] = {}
        self._dialogue_cursor = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def policy(self) -> ModerationPolicy | None:
        return self._policy

    def inspect(self, text: str) -> ModerationVerdict:
        if self._moderator is None:
            return ALLOWED
        verdict = self._moderator.inspect(text)
        with self._lock:
            self._inspected += 1
            if verdict.blocked:
                self._blocked += 1
                self._by_category[verdict.category] = (
                    self._by_category.get(verdict.category, 0) + 1
                )
        return verdict

    def next_blocked_dialogue(self) -> str:
        """차단 문장을 대신할 캐릭터 대사. 순환 선택이라 무음도, 같은 말 반복도 없다."""
        if self._policy is None or not self._policy.blocked_dialogue:
            return ""
        lines = self._policy.blocked_dialogue
        with self._lock:
            line = lines[self._dialogue_cursor % len(lines)]
            self._dialogue_cursor += 1
        return line

    def health(self) -> dict[str, object]:
        with self._lock:
            inspected = self._inspected
            blocked = self._blocked
            by_category = dict(self._by_category)
        return {
            "enabled": self._enabled,
            "ready": self._moderator is not None,
            "source": self._policy.source if self._policy is not None else "",
            "policy_version": self._policy.version if self._policy is not None else 0,
            "dictionary": self._policy.counts() if self._policy is not None else {},
            "allowlist": self._policy.allowlist_count if self._policy is not None else 0,
            "fallback_lines": (
                len(self._policy.blocked_dialogue) if self._policy is not None else 0
            ),
            "inspected": inspected,
            "blocked": blocked,
            "blocked_by_category": by_category,
        }
