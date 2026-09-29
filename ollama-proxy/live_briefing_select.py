"""Default-off candidate selection for live-broadcast turns whose briefing names what to say.

The 2.3B generator answers the viewer's literal words and drops or contradicts the showrunner's briefing
when the chat presupposes something else.  Prompt wording does not move it, but its samples differ, so
when the briefing carries a ``- 이번 턴에 말할 것:`` line the proxy may draw a few candidates and keep the
first fit one that covers that line.  When none does, the line itself is spoken if it is written the way
AIRI talks (the user's 2026-09-24 choice over spending more draws).  Nothing here reads or writes proxy
state; the caller owns drawing.
"""
from __future__ import annotations

import collections
import difflib
import os
import re
import threading
import unicodedata
import zlib
from typing import Awaitable, Callable

from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER


LIVE_BRIEFING_CANDIDATES_ENV = "AIRI_LIVE_BRIEFING_CANDIDATES"
LIVE_BRIEFING_COVERAGE_ENV = "AIRI_LIVE_BRIEFING_COVERAGE"
MAX_CANDIDATES = 6
# 0.4 over 0.3 (2026-09-24, 3 candidates + briefing line, key-term checks on two stories): story 1
# 19 -> 23/23 with the line spoken in 8 -> 14 of 23 turns, story 2 11 -> 12/14 with 2 -> 2 lines.
DEFAULT_COVERAGE = 0.4
SAY_LINE_PREFIX = "- 이번 턴에 말할 것:"
# Listing what not to say yet makes the 2.3B generator say it: drafts naming a listed item went from 6/90
# without the line to 15/90 with it (2026-09-24, two stories, 6 seeds per turn).
DO_NOT_SAY_PREFIX = "- 아직 말하지 말 것:"
# A candidate sharing this many characters with the previous reply is a repeat, not a new beat.
REPEAT_RUN_CHARS = 20

_NON_TEXT_RE = re.compile(r"[^가-힣A-Za-z0-9]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?~])\s+|\n+")
_HONORIFIC_END_RE = re.compile(r"(?:요|습니다|세요|죠)\s*[.!?~]*\s*$")
# Staff-note narration copied as speech ("마라탕을 먹었다.", "…번져 있었다."), past tense only. A
# present-tense declarative ("2회전에서 바로 복수한다.") is the persona's own natural speech, not a
# copied note (2026-09-25 false positive found designing the competitive persona). Spoken praise and a
# spoken groan ("고생했다!", "수고했다", "잘했다", "망했다") are speech too (2026-09-26 handoff §5-5).
_WRITTEN_END_RE = re.compile(r"(?:었다|았다|였다|(?<!고생)(?<!수고)(?<!잘)(?<!망)했다|샀다|갔다)\s*[.!]*\s*$")
_LEAKED_LABEL_RE = re.compile(r"이번 턴에|브리핑|스태프|\[")
_UNEXECUTED_LOOKUP_RE = re.compile(r"(?:검색|찾아|확인|알아)\s?(?:해\s?)?봤|검색했")
# A director correction in the say line ("설거지는 아니고", "감기가 아니라") names what AIRI must stop
# asserting. On 2026-09-24 show 08 "내가 설거지 벌칙 받았어!" passed coverage right after the line
# "아 설거지는 아니고 ㅋㅋ", because bigrams cannot see negation.
_CORRECTED_TERM_RE = re.compile(r"([가-힣A-Za-z0-9]{2,})(?:은|는|이|가)\s*(?:아니|안\s)")
_NEGATION_AFTER_RE = re.compile(r"^.{0,4}?(?:아니|안\s|않|없|라기보다|보다는)")
# Role mirroring on the opening turns of every simulated show: "두번째 방송 축하" answered with "축하해!",
# "첫방이다" answered with "떨리겠다!" (AIRI guessing a feeling the viewer never stated).
_VIEWER_CONGRATS_RE = re.compile(r"축하|ㅊㅋ")
_MIRRORED_CONGRATS_RE = re.compile(r"축하해")
_GUESSED_FEELING_RE = re.compile(r"(?:떨리|긴장되|설레|무섭|힘들)겠")
_VIEWER_OWN_STATE_RE = re.compile(r"(?:^|\s)(?:나|내가|저|제가)(?:\s|도|는)")
# AIRI is a virtual broadcaster with no body and no life outside the broadcast (user decision 2026-09-24:
# only what happens on the broadcast and what earlier broadcasts left in memory). Asked about either, the
# 2.3B generator made up a meal, sleep, exercise or a home in about 27 of 36 samples, and a canon sentence
# in the situation note did not change that. Claims inside a question to the viewer, or about the viewer,
# are not AIRI's. "까먹었", "마음먹었", "겁먹었" and the like are idioms, not a meal (2026-09-26 handoff §5-5).
_BODILY_CLAIM_RE = re.compile(
    r"(?<!까)(?<!잊어)(?<!겁)(?<!욕)(?<!애)(?<!마음)먹었|마셨|잤|잠들|운동했|스트레칭|산책했|다녀왔|갔다\s*왔|살고\s*있|배고파"
    r"|배불러|맛있었(?!겠)"
    r"|음식을\s*좋아|좋아하는\s*음식은|밖에서\s*(?:따로\s*)?살"
)
_SECOND_PERSON_RE = re.compile(r"(?:^|\s)(?:너|넌|너는|너도|니가|네가)(?:\s|$)")
# A claim word that runs straight into 구나 or 겠 ("다녀왔구나", "먹었겠다") reacts to or guesses about
# the viewer's own day (2026-09-25 false positive: "산책 다녀왔구나, 강아지도 기분 좋았겠다." has no
# second-person word). Elsewhere in the sentence 구나/겠 prove nothing: "배고파 죽겠다", "친구나".
_REACTION_SUFFIXES = ("구나", "겠")
_CHAT_SOURCE_RE = re.compile(r"^\[[^\]]+\]\s*")
_QUESTION_RE = re.compile(r"[?？]|뭐|뭘|어디|언제|어때|냐고|냐\s*$|니\s*$")
_ADDRESSES_AIRI_RE = re.compile(r"아이리|AIRI|(?:^|\s)(?:너|넌|너는|니가|네가)(?:\s|$)", re.IGNORECASE)
_VIEWER_SUBJECT_RE = re.compile(r"^(?:나|난|내가|나는|저|전|제가|저는)\s")
# Choosing what the viewer should eat is a menu question, not a question about AIRI.
_MENU_CHOICE_RE = re.compile(r"먹을까|먹지\s*[?？]|먹을지|골라|추천(?!\s*말고)")
# Several lines per topic, in the persona-v3 voice: one fixed "나는 버추얼이라 … 못 먹어!" line was 30 of 36
# canon-probe answers with candidates on (2026-09-29), the flat pattern the user rejected on 2026-09-25.
_CANON_LINES = (
    # Any form of 먹다 ("먹고 켰어?", 2026-09-29 real-path show), but not 까먹다/잊어먹다 (forget) or 먹방.
    (re.compile(r"(?<!까)(?<!잊어)먹(?!방)|마셨|밥|음식|간식|배고"), (
        "밥은 안 먹어. 덕분에 방송 중에 밥 먹으러 자리 비울 일은 없어.",
        "밥은 한 입도 못 먹어. 그래서 채팅에 올라오는 메뉴 설명이 나한텐 더 선명하게 남아.",
        "밥은 난 구경 담당이야. 오늘 메뉴 얘기는 채팅이 주인공이지.",
        "밥 먹는 건 내 담당이 아니야. 대신 누가 무슨 메뉴였는지는 끝까지 기억해 둘게.",
        "나는 밥 대신 채팅 보는 쪽이야. 메뉴 자랑은 언제 와도 환영.",
    )),
    (re.compile(r"잤|잠|졸려"), (
        "잠은 안 자. 방송이 꺼지면 나도 같이 꺼지는 쪽이라 뒤척일 일도 없어.",
        "나는 잠이 없어서 피곤할 틈도 없어. 방송 켜지면 늘 이 컨디션이야.",
        "잠은 내 영역이 아니야. 방송 켜지는 순간부터가 내 하루라서.",
        "잘 자냐는 안부는 나한텐 해당이 없네. 잠 없이 방송 켜지면 바로 여기 있거든.",
    )),
    (re.compile(r"운동|헬스|산책|스트레칭"), (
        "운동은 몸이 없어서 못 해. 헬스장은 이름만 알아.",
        "몸 쓰는 건 내 쪽에선 불가능이야. 대신 운동 얘기는 끝까지 들어 줄 수 있어.",
        "움직일 몸이 없어서 운동은 구경만 해. 루틴 얘기 듣는 건 좋아.",
        "몸으로 하는 건 나랑 제일 먼 얘기야. 그래서 운동하는 사람들 얘기가 더 신기해.",
    )),
    (re.compile(r"어디\s*살|사는\s*곳|집이\s*어디|(?:주말|휴일|평소)에\s*뭐|방송\s*끝나고\s*뭐|어디\s*(?:갔|다녀)|다녀왔|여행"), (
        "사는 동네는 따로 없고, 방송이 켜지면 여기 있어.",
        "주말이 따로 있진 않아. 방송이 켜진 시간이 내 하루 전부야.",
        "방송 밖은 내가 모르는 세계야. 여기서 너희랑 떠드는 게 내 일과지.",
        "방송이 꺼지면 따로 하는 일이 없어. 그래서 내 얘기는 전부 여기서 생긴 거야.",
    )),
)
# Lines spoken lately, so a question asked again in a show gets another line of its topic.
_recent_canon_lines: collections.deque[str] = collections.deque(maxlen=8)
_recent_canon_lock = threading.Lock()


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


# Show 09 (2026-09-24): say lines ending "…내려왔어 ㅋㅋ" came out empty — the output boundary drops
# the laughter and then withholds a long final clause with no terminal mark, so the fallback was silence.
_TRAILING_LAUGH_RE = re.compile(r"(?:\s*(?:ㅋ+|ㅎ+|ㅠ+|ㅜ+))+\s*$")


def speakable_line(say: str) -> str:
    """The say line as it will be spoken: trailing laughter dropped, a terminal mark guaranteed."""
    text = _TRAILING_LAUGH_RE.sub("", say.strip()).rstrip()
    return text if not text or text[-1] in ".!?~" else text + "."


def canon_say_lines(user_text: object) -> tuple[str, ...]:
    """The say lines for a viewer question that presupposes AIRI's body or offline life, else ()."""
    if not isinstance(user_text, str):
        return ()
    text = _CHAT_SOURCE_RE.sub("", unicodedata.normalize("NFKC", user_text).strip())
    if not _QUESTION_RE.search(text) or _MENU_CHOICE_RE.search(text):
        return ()
    if _VIEWER_SUBJECT_RE.search(text) and not _ADDRESSES_AIRI_RE.search(text):
        return ()
    return next((lines for pattern, lines in _CANON_LINES if pattern.search(text)), ())


def canon_say_line(user_text: object) -> str:
    """One say line of the question's topic, fixed by the question text, else ''."""
    lines = canon_say_lines(user_text)
    return lines[zlib.crc32(str(user_text).encode("utf-8")) % len(lines)] if lines else ""


def with_canon_say_line(context_note: str, user_text: object) -> str:
    """The context note with a canon say line added when the briefing names nothing to say."""
    lines = canon_say_lines(user_text)
    if not lines or say_line(context_note):
        return context_note
    start = lines.index(canon_say_line(user_text))
    with _recent_canon_lock:
        line = next((lines[(start + step) % len(lines)] for step in range(len(lines))
                     if lines[(start + step) % len(lines)] not in _recent_canon_lines), lines[start])
        _recent_canon_lines.append(line)
    live_briefing_select_telemetry.canon_line_added()
    header = "" if BROADCAST_BRIEFING_HEADER in context_note else "\n\n" + BROADCAST_BRIEFING_HEADER
    return f"{context_note.rstrip()}{header}\n{SAY_LINE_PREFIX} {line}"


def without_do_not_say(context_note: str) -> str:
    """The context note with the briefing's do-not-say lines removed."""
    return "\n".join(line for line in context_note.split("\n") if not line.startswith(DO_NOT_SAY_PREFIX))


def _bigrams(text: str) -> set[str]:
    compact = _NON_TEXT_RE.sub("", unicodedata.normalize("NFKC", text))
    return {compact[index:index + 2] for index in range(len(compact) - 1)}


def briefing_coverage(answer: object, say: str) -> float:
    """Share of the say line's character bigrams that the answer reuses."""
    target = _bigrams(say)
    if not isinstance(answer, str) or not target:
        return 0.0
    return len(target & _bigrams(answer)) / len(target)


def candidate_is_unfit(answer: object, say: str, previous_reply: str = "", user_text: str = "") -> bool:
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
    if any(
        not part.rstrip().endswith(("?", "？")) and not _SECOND_PERSON_RE.search(part)
        and any(not part[match.end():].startswith(_REACTION_SUFFIXES) for match in _BODILY_CLAIM_RE.finditer(part))
        for part in sentences
    ):
        return True
    if _UNEXECUTED_LOOKUP_RE.search(text) and not _UNEXECUTED_LOOKUP_RE.search(say):
        return True
    for term in {match.group(1) for match in _CORRECTED_TERM_RE.finditer(say)}:
        for match in re.finditer(re.escape(term), text):
            if not _NEGATION_AFTER_RE.search(text[match.end():match.end() + 12]):
                return True
    if user_text and _VIEWER_CONGRATS_RE.search(user_text) and _MIRRORED_CONGRATS_RE.search(text):
        return True
    if user_text and _GUESSED_FEELING_RE.search(text) and not _VIEWER_OWN_STATE_RE.search(user_text):
        return True
    previous = unicodedata.normalize("NFKC", previous_reply or "").strip()
    if previous:
        match = difflib.SequenceMatcher(None, text, previous, autojunk=False).find_longest_match(
            0, len(text), 0, len(previous),
        )
        if match.size >= REPEAT_RUN_CHARS:
            return True
    return False


def candidate_score(
    answer: object, say: str, previous_reply: str = "", user_text: str = "",
) -> tuple[bool, float]:
    """(fit, coverage); tuples order fit candidates first, then by coverage."""
    return (not candidate_is_unfit(answer, say, previous_reply, user_text), briefing_coverage(answer, say))


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
    user_text: str = "",
) -> tuple[str, object | None, list[object], bool]:
    """Draw until a fit candidate covers the say line or the budget is spent.

    ``first_text`` is the already generated, already bounded dialogue.  ``draw`` returns one more bounded
    dialogue and its upstream payload.  Returns the dialogue to speak, the payload of the kept candidate
    (None when the first draft was kept), the payloads drawn but not kept, and whether nothing passed so
    the say line itself is spoken.  The say line is only spoken when it passes the same fitness rules,
    so a staff-note briefing ("…먹었다.") is never read out; the kept candidate then carries the metadata.
    """
    texts: list[str] = [first_text]
    payloads: list[object | None] = [None]
    scores = [candidate_score(first_text, say, previous_reply, user_text)]
    while not accept_early(scores[-1], threshold) and len(texts) < budget:
        text, payload = await draw()
        texts.append(text)
        payloads.append(payload)
        scores.append(candidate_score(text, say, previous_reply, user_text))
    chosen = best_index(scores)
    line = speakable_line(say)
    said_briefing = not accept_early(scores[chosen], threshold) and not candidate_is_unfit(
        line, say, previous_reply, user_text,
    )
    live_briefing_select_telemetry.record(
        draws=len(texts) - 1, early=accept_early(scores[-1], threshold), replaced=chosen != 0,
        said_briefing=said_briefing,
    )
    unchosen = [payload for index, payload in enumerate(payloads) if index != chosen and payload is not None]
    return (line if said_briefing else texts[chosen]), payloads[chosen], unchosen, said_briefing


class LiveBriefingSelectTelemetry:
    """Content-free counters for the opt-in live briefing candidate selection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._turns = 0
        self._draws = 0
        self._early = 0
        self._replaced = 0
        self._said_briefing = 0
        self._canon_lines = 0

    def canon_line_added(self) -> None:
        with self._lock:
            self._canon_lines += 1

    def record(self, *, draws: int, early: bool, replaced: bool, said_briefing: bool) -> None:
        with self._lock:
            self._turns += 1
            self._draws += draws
            self._early += int(early)
            self._replaced += int(replaced)
            self._said_briefing += int(said_briefing)

    def health(self) -> dict[str, object]:
        with self._lock:
            counts = {
                "turns": self._turns,
                "extra_draws": self._draws,
                "early_accepts": self._early,
                "first_draft_replaced": self._replaced,
                "briefing_line_spoken": self._said_briefing,
                "canon_lines_added": self._canon_lines,
            }
        return {"candidates": candidate_budget(), "coverage": coverage_threshold(), **counts}


live_briefing_select_telemetry = LiveBriefingSelectTelemetry()
