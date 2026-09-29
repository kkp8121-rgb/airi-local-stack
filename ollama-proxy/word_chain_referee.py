"""Default-off 끝말잇기 (Korean word chain) referee for live-broadcast turns.

On 2026-09-29 the 2.3B persona model failed every 끝말잇기 turn of a simulated show ("기차차"): it cannot
find a valid next word. A staff referee judges the viewer's word and names AIRI's word in the turn briefing
instead, in exactly the lines the persona-v4 training data uses. Opt-in via ``AIRI_LIVE_WORD_CHAIN_WORDS``
(path to a UTF-8 TSV noun list). The list is a 3,035-noun learner list, so it can pick AIRI's word but can
never prove a viewer's word does not exist: no word is ever rejected as missing from it.
"""
from __future__ import annotations

import os
import re
import threading
import zlib
from collections import OrderedDict
from pathlib import Path
from typing import Container, Mapping, Sequence

from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER, DONATION_CONTINUATION_CONTRACT
from live_briefing_select import REQUIRED_WORD_PREFIX, accepted_word


WORD_CHAIN_WORDS_ENV = "AIRI_LIVE_WORD_CHAIN_WORDS"
WORD_CHAIN_MARK = "끝말잇기"
WORD_LIST_HEADER = "word\trank\tlevel"
# Rounds are kept per show; the live runtime itself holds at most 16 shows.
MAX_SHOWS = 32
AIRI_CHOICES = 3

# Only the segment decides: a show titled 끝말잇기 still has an opening and a 마무리 (2026-09-29).
_SEGMENT_LINE_PREFIX = "- 지금 구간:"
_SOURCE_TAGS_RE = re.compile(r"^[ \t]*(?:\[[^\]\n]*\][ \t]*)+", re.MULTILINE)
_LAUGH_RE = re.compile(r"[ㅋㅎㅠㅜ]+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]|_")
_WORD_RE = re.compile(r"[가-힣]{2,5}")
_HANGUL_RUN_RE = re.compile(r"[가-힣]+")
# On a live show a false judgment is worse than none, so a chat of several words is a move only when
# it says it is one. Cue words are never the move themselves.
_START_CUES = ("먼저", "시작", "간다", "갈게", "한다", "할게", "고고")
_MOVE_CUES = _START_CUES + ("이거", "받아", "정답", "판정")
# A viewer asking for a ruling hears it (2026-09-29 ep07 T15: "션샤인 이거 되냐? 판정 ㄱ" -> "인물로 받을게.").
_VERDICT_ASK_RE = re.compile(r"판정|되냐|되나|돼\s*[?？]|되는\s*거|인정\s*[?？]|가능\s*[?？]")


def _cue_re(words: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"(?<!\S)(?:(?:" + "|".join(words) + r")요?|첫\s*단어[은는]?|ㄱ+)(?!\S)")


_START_CUE_RE = _cue_re(_START_CUES)
_MOVE_CUE_RE = _cue_re(_MOVE_CUES)
# Chat reacts with one word all the time ("대박", "진짜"); a reaction is never a move, even when the list has it.
_REACTIONS = frozenset((
    "대박", "진짜", "정말", "레알", "인정", "실화", "실화냐", "미쳤다", "미쳤어", "미쳤네", "역시", "최고", "굿굿",
    "오케이", "에바", "웃겨", "개웃겨", "맞아", "그치", "그렇지", "아니", "뭐야", "뭐임", "우와", "와우", "나이스",
    "좋아", "좋다", "헐랭", "킹받네", "귀엽다", "천재", "천재네", "잘한다", "화이팅", "파이팅",
))
# One trailing particle, longest first; dropped only when a list noun of 2+ syllables remains.
_PARTICLES = ("으로", "이야", "이요", "로", "야", "요", "임", "은", "는", "이", "가", "을", "를")

_HANGUL_BASE, _HANGUL_LAST = 0xAC00, 0xD7A3
_INITIAL_NIEUN, _INITIAL_RIEUL, _INITIAL_IEUNG = 2, 5, 11
# ㅑ ㅕ ㅖ ㅛ ㅠ ㅣ
_Y_OR_I_MEDIALS = frozenset((2, 6, 7, 12, 17, 20))
_FINAL_RIEUL = 8


class WordListError(ValueError):
    """The word list is not in the documented shape."""


def _syllable(initial: int, medial: int, final: int) -> str:
    return chr(_HANGUL_BASE + (initial * 21 + medial) * 28 + final)


def chain_starts(word: str) -> set[str]:
    """Syllables the next word may start with: the last syllable and its initial-sound-rule form."""
    if not word:
        return set()
    last = word[-1]
    if not _HANGUL_BASE <= ord(last) <= _HANGUL_LAST:
        return {last}
    code = ord(last) - _HANGUL_BASE
    initial, medial, final = code // 588, (code % 588) // 28, code % 28
    if initial == _INITIAL_RIEUL:
        initial = _INITIAL_IEUNG if medial in _Y_OR_I_MEDIALS else _INITIAL_NIEUN
    elif initial == _INITIAL_NIEUN and medial in _Y_OR_I_MEDIALS:
        initial = _INITIAL_IEUNG
    return {last, _syllable(initial, medial, final)}


def ro_particle(syllable: str) -> str:
    """"으로" after a final consonant other than ㄹ, else "로"."""
    code = ord(syllable) - _HANGUL_BASE if syllable else -1
    if not 0 <= code <= _HANGUL_LAST - _HANGUL_BASE:
        return "로"
    final = code % 28
    return "으로" if final and final != _FINAL_RIEUL else "로"


def _noun_form(token: str, nouns: Container[str]) -> str:
    """The token, or the list noun left after dropping one trailing particle."""
    if token in nouns:
        return token
    for particle in _PARTICLES:
        stem = token[:-len(particle)]
        if token.endswith(particle) and len(stem) >= 2 and stem in nouns:
            return stem
    return token


def parse_move(chat: object, previous: str, nouns: Container[str]) -> str:
    """The viewer's word in one chat, or '' when the chat names none."""
    if not isinstance(chat, str):
        return ""
    text = _PUNCTUATION_RE.sub(" ", _LAUGH_RE.sub(" ", _SOURCE_TAGS_RE.sub("", chat)))
    tokens = [
        _noun_form(run, nouns) for run in _HANGUL_RUN_RE.findall(_MOVE_CUE_RE.sub(" ", text))
        if _WORD_RE.fullmatch(run) and run not in _REACTIONS
    ]
    starts = chain_starts(previous) if previous else set()
    pieces = text.split()
    if len(pieces) == 1 and _WORD_RE.fullmatch(pieces[0]):
        if pieces[0] in _REACTIONS:
            return ""
        lone = _noun_form(pieces[0], nouns)
        # A lone cue word ("시작!", "고고") is a move only when it chains.
        return lone if tokens or lone[0] in starts else ""
    if not previous:
        if not _START_CUE_RE.search(text):
            return ""
        return next((token for token in reversed(tokens) if token in nouns), "")
    last = next((token for token in reversed(tokens) if token[0] in starts), "")
    return last if last and (last in nouns or _MOVE_CUE_RE.search(text)) else ""


def load_words(path: str | Path) -> dict[str, int]:
    """Read the TSV noun list: '#' comments, the header, then word/rank/level rows."""
    words: dict[str, int] = {}
    header_seen = False
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if not header_seen:
            if line != WORD_LIST_HEADER:
                raise WordListError("missing header")
            header_seen = True
            continue
        fields = line.split("\t")
        if len(fields) != 3 or not _WORD_RE.fullmatch(fields[0]) or not fields[1].isdigit():
            raise WordListError("malformed row")
        word, rank = fields[0], int(fields[1])
        words[word] = min(rank, words.get(word, rank))
    if not words:
        raise WordListError("no words")
    return words


def word_chain_segment(context_note: object) -> bool:
    """True when the note's segment line names the game."""
    if not isinstance(context_note, str):
        return False
    return any(
        line.startswith(_SEGMENT_LINE_PREFIX) and WORD_CHAIN_MARK in line
        for line in context_note.splitlines()
    )


def verdict_asked(chat: object) -> bool:
    """True when the viewer asks whether a word counts."""
    return isinstance(chat, str) and bool(_VERDICT_ASK_RE.search(chat))


def referee_say_line(lines: Sequence[str], asked: bool = False) -> str:
    """A spoken line carrying AIRI's word ("차표로 받을게."), or '' when the lines name none.

    Asked for a ruling, the line leads with it ("기차 인정! 차표로 받을게.").
    """
    word = next((line[len(REQUIRED_WORD_PREFIX):].strip() for line in lines if line.startswith(REQUIRED_WORD_PREFIX)), "")
    if not word:
        return ""
    line = f"{word}{ro_particle(word[-1])} 받을게."
    ruled = accepted_word("\n".join(lines)) if asked else ""
    return f"{ruled} 인정! {line}" if ruled else line


def with_referee_lines(context_note: str, lines: Sequence[str]) -> str:
    """The note with the referee lines at the end of the turn briefing, adding its header if needed."""
    if not lines:
        return context_note
    contract = "\n\n" + DONATION_CONTINUATION_CONTRACT
    note, tail = (context_note[:-len(contract)], contract) if context_note.endswith(contract) else (context_note, "")
    header = "" if BROADCAST_BRIEFING_HEADER in note else "\n\n" + BROADCAST_BRIEFING_HEADER
    return f"{note.rstrip()}{header}\n" + "\n".join(lines) + tail


class _Round:
    __slots__ = ("previous", "used")

    def __init__(self) -> None:
        self.previous = ""
        self.used: set[str] = set()


class WordChainReferee:
    """Per-show 끝말잇기 rounds judged against a ranked noun list; disabled without a list."""

    def __init__(self, words: Mapping[str, int] | None = None, *, load_error: int = 0) -> None:
        self._words = dict(words or {})
        self._by_start: dict[str, list[tuple[int, str]]] = {}
        for word, rank in self._words.items():
            self._by_start.setdefault(word[0], []).append((rank, word))
        for ranked in self._by_start.values():
            ranked.sort()
        self._load_error = load_error
        self._lock = threading.Lock()
        self._rounds: OrderedDict[str, _Round] = OrderedDict()
        self._counters = {key: 0 for key in ("turns", "accepted", "rejected", "airi_losses")}

    @classmethod
    def from_path(cls, path: str | Path) -> WordChainReferee:
        """Load the list; an unreadable or malformed file leaves the referee off and counted."""
        try:
            return cls(load_words(path))
        except (OSError, UnicodeDecodeError, WordListError):
            return cls(load_error=1)

    @classmethod
    def from_env(cls) -> WordChainReferee:
        path = os.environ.get(WORD_CHAIN_WORDS_ENV, "").strip()
        return cls.from_path(path) if path else cls()

    @property
    def enabled(self) -> bool:
        return bool(self._words)

    def _airi_word(self, show_id: str, word: str, used: set[str]) -> str:
        ranked = sorted(
            entry for start in chain_starts(word) for entry in self._by_start.get(start, ())
            if entry[1] not in used
        )[:AIRI_CHOICES]
        if not ranked:
            return ""
        return ranked[zlib.crc32((show_id + word).encode("utf-8")) % len(ranked)][1]

    def judge(self, show_id: str, chat: object) -> tuple[str, ...]:
        """The referee lines for one viewer chat in a 끝말잇기 segment; () when there is no move."""
        if not self.enabled:
            return ()
        with self._lock:
            self._counters["turns"] += 1
            game = self._rounds.get(show_id)
            if game is None:
                game = self._rounds[show_id] = _Round()
                while len(self._rounds) > MAX_SHOWS:
                    self._rounds.popitem(last=False)
            self._rounds.move_to_end(show_id)
            word = parse_move(chat, game.previous, self._words)
            if not word:
                return ()
            if game.previous and word[0] not in chain_starts(game.previous):
                self._counters["rejected"] += 1
                return (f"- 심판 판정: {word} 무효(끝 글자와 안 이어짐), 다시",)
            if word in game.used:
                self._counters["rejected"] += 1
                return (f"- 심판 판정: {word} 무효(이미 나옴), 다시",)
            self._counters["accepted"] += 1
            accepted = f"- 심판 판정: {word} 유효, AIRI 차례"
            reply = self._airi_word(show_id, word, game.used | {word})
            if not reply:
                self._counters["airi_losses"] += 1
                game.previous, game.used = "", set()
                last = word[-1]
                return (accepted, f"- 심판 판정: {last}{ro_particle(last)} 이을 단어 없음, AIRI 패")
            game.used |= {word, reply}
            game.previous = reply
            return (accepted, f"{REQUIRED_WORD_PREFIX} {reply}")

    def close_show(self, show_id: str) -> None:
        with self._lock:
            self._rounds.pop(show_id, None)

    def health(self) -> dict[str, int | bool]:
        """Content-free counters with the same keys whether on or off."""
        with self._lock:
            return {
                "enabled": self.enabled, "words": len(self._words), "load_error": self._load_error,
                **self._counters,
            }
