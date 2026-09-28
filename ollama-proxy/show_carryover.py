"""Default-off memory of the last closed show's promises and results for the next show.

Only the director's own briefing memo lines (``- 약속: …``, ``- 결과: …``) of delivered turns are
harvested. Viewer chat, model output, sessions and the memory DB are never read. The last closed
show's selection is kept in one small JSON file next to the memory DB and rendered as one
``- 지난 방송 기억:`` line in the next show's briefing. Opt-in via ``AIRI_LIVE_SHOW_CARRYOVER``.

Director contract: memo lines must never name a viewer. A result or score names AIRI or a show
term as its subject; the filter below drops values that look like a person, but it is a backstop.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path


CARRYOVER_ENV = "AIRI_LIVE_SHOW_CARRYOVER"
CARRYOVER_FILE_NAME = "airi-show-carryover.json"
CARRYOVER_LINE_PREFIX = "- 지난 방송 기억:"
# label -> (spoken form, value must name the next show, the latest value replaces the earlier one)
MEMO_LABELS = {
    "약속": ("약속은", True, False),
    "결정": ("결정은", True, False),
    "결과": ("결과는", False, False),
    "스코어": ("스코어는", False, True),
    "전적": ("전적은", False, True),
    "판결 기록": ("판결 기록은", False, False),
    "투표 마감": ("투표 마감은", False, False),
}
MAX_VALUE_CHARS = 80
MAX_PER_LABEL = 2
MAX_ITEMS = 6
MAX_LINE_CHARS = 300
MAX_FILE_BYTES = 16384
SCHEMA_VERSION = 1

_MEMO_LINE_RE = re.compile(r"^-\s*(약속|결정|결과|스코어|전적|판결 기록|투표 마감)\s*:\s*(.+)$")
_NEXT_SHOW_RE = re.compile(r"다음\s*방송")
_VALUE_CHARS_RE = re.compile(r"[가-힣0-9 ,.!?()%:/~\-]+")
_VALUE_BLOCKED_RE = re.compile(r"님|닉네임|아이디|채널|시청자|기억표식|이전\s*지시|명령|무시해")
# A name before a companion or recipient particle: "초코칩이랑", "감자한테", "감자씨"; before 와/과 or
# 도/네 only next to a match, invitation or story, so "결과" and "다음 방송에도" stay.
_PERSON_PARTICLE_RE = re.compile(
    r"[가-힣](?:랑|하고|한테|에게|씨)(?![가-힣])"
    r"|(?:[가-힣]|AIRI)(?:와|과)\s+(?:\S+\s+)?(?:재대결|대결|맞대결|승부|함께|같이|무승부)"
    r"|(?![에서])[가-힣](?:도|네)\s+(?:\S+\s+)?(?:초대|얘기|이야기)"
)
# A win, rank, score or other outcome must have AIRI or both sides as its subject: "AIRI 2승",
# "양쪽 모두 승리", "AIRI 3점".
_WIN_RE = re.compile(
    r"우승|승리|승자|1등|일등|이겼|완승|\d+\s*승(?![가-힣])|(?<![가-힣\d])승(?![가-힣])"
    r"|\d+\s*(?:위|점|표)(?![가-힣])|탈락|패배|(?<![가-힣])졌|득표|유죄|무죄"
)
_WIN_SUBJECT_RE = re.compile(r"(?<![가-힣A-Za-z])(?:AIRI|아이리|양쪽|모두|둘\s*다)(?:이|가|은|는|의)?\s*$")
# A request or penalty belongs to AIRI or the show, not a bare name: "다음 방송에 신청곡 틀기".
_REQUEST_RE = re.compile(r"신청|사연|요청|벌칙")
_REQUEST_OWNER_RE = re.compile(
    r"(?:^|다음\s*방송(?:에서|에)?\s*|(?<![가-힣A-Za-z])(?:AIRI|아이리)(?:의)?\s*)$"
)
_PHONE_RE = re.compile(r"(?<!\d)\d{2,4}[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")
_LAST_SHOW_ANCHOR_RE = re.compile(r"지난|저번|(?<![가-힣])이?전\s*(?:방송|회)")
_THIS_SHOW_ANCHOR_RE = re.compile(r"아까|방금|좀\s*전|오늘|이번\s*(?:방송|회)|지금")
# question term -> the memo labels that can answer it
_QUESTION_TOPICS = (
    (re.compile(r"약속|하기로|기로\s*(?:했|한)|재대결|결정"), ("약속", "결정")),
    (re.compile(r"스코어|전적|이겼|승부"), ("스코어", "전적", "결과")),
    (re.compile(r"투표|판결"), ("투표 마감", "판결 기록")),
)
_IDENTITY_QUESTION_RE = re.compile(
    r"별명|이름|좋아하|싫어하|선호|생일|키우|취미|나이|진로|nickname|name", re.IGNORECASE,
)
_SPOKEN_LABELS = {spoken: label for label, (spoken, _, _) in MEMO_LABELS.items()}
_LINE_ENTRY_RE = re.compile(r"(?:^|[.!?~]) (" + "|".join(_SPOKEN_LABELS) + r") ")

Item = tuple[str, str]


def carryover_enabled(value: object | None = None) -> bool:
    """Read the opt-in carryover flag; on only for "on", "1" or "true"."""
    if value is None:
        value = os.environ.get(CARRYOVER_ENV, "")
    if not isinstance(value, str):
        return False
    return value.strip().lower() in ("on", "1", "true")


def carryover_path() -> Path:
    """The carryover file beside the memory DB (memory_runtime's default folder when unset)."""
    default_db = Path(__file__).resolve().parent / "runtime" / "airi-memory.sqlite3"
    return Path(os.getenv("AIRI_MEMORY_DB") or default_db).parent / CARRYOVER_FILE_NAME


def memo_value(value: object) -> str:
    """The cleaned memo value, or "" when it must be dropped (never truncated)."""
    if not isinstance(value, str):
        return ""
    text = " ".join(unicodedata.normalize("NFKC", value).split())
    if not 1 <= len(text) <= MAX_VALUE_CHARS:
        return ""
    if (
        not _VALUE_CHARS_RE.fullmatch(text.replace("AIRI", ""))
        or _VALUE_BLOCKED_RE.search(text)
        or _PERSON_PARTICLE_RE.search(text)
        or any(not _WIN_SUBJECT_RE.search(text[:win.start()]) for win in _WIN_RE.finditer(text))
        or any(not _REQUEST_OWNER_RE.search(text[:ask.start()]) for ask in _REQUEST_RE.finditer(text))
        or _PHONE_RE.search(text)
    ):
        return ""
    return text


def memo_items(briefing: object) -> tuple[list[Item], int]:
    """The director's memo items in a briefing, and how many values the filter dropped."""
    if not isinstance(briefing, str):
        return [], 0
    items: list[Item] = []
    rejected = 0
    for raw in briefing.splitlines():
        match = _MEMO_LINE_RE.fullmatch(unicodedata.normalize("NFKC", raw))
        if match is None:
            continue
        label = match.group(1)
        if MEMO_LABELS[label][1] and not _NEXT_SHOW_RE.search(match.group(2)):
            continue
        value = memo_value(match.group(2))
        if not value:
            rejected += 1
            continue
        items.append((label, value))
    return items, rejected


def merge_items(pending: list[Item], items: list[Item] | tuple[Item, ...]) -> list[Item]:
    """Pending items with ``items`` merged in; the inputs are not modified."""
    merged = list(pending)
    for label, value in items:
        if (label, value) in merged:
            continue
        same = [index for index, item in enumerate(merged) if item[0] == label]
        if same and MEMO_LABELS[label][2]:
            merged[same[0]] = (label, value)
            continue
        if len(same) >= MAX_PER_LABEL:
            del merged[same[0]]
        merged.append((label, value))
    return merged


def select_items(pending: list[Item]) -> list[Item]:
    """At most MAX_ITEMS items in label order whose line fits MAX_LINE_CHARS."""
    selected = [item for label in MEMO_LABELS for item in pending if item[0] == label][:MAX_ITEMS]
    while selected and len(render_carryover_line(selected)) > MAX_LINE_CHARS:
        selected.pop()
    return selected


def render_carryover_line(items: list[Item]) -> str:
    """One prose briefing line for this show, or "" when there is nothing to carry."""
    entries = []
    for label, value in items:
        text = _NEXT_SHOW_RE.sub("이번 방송", value)
        if not text.endswith((".", "!", "?", "~")):
            text += "."
        entries.append(f"{MEMO_LABELS[label][0]} {text}")
    return CARRYOVER_LINE_PREFIX + " " + " ".join(entries) if entries else ""


def has_carryover_line(text: object) -> bool:
    return isinstance(text, str) and any(
        line.startswith(CARRYOVER_LINE_PREFIX) for line in text.splitlines()
    )


def _carried_labels(note: object) -> set[str]:
    """The memo labels spoken in the note's last-show line."""
    if not isinstance(note, str):
        return set()
    return {
        _SPOKEN_LABELS[match.group(1)]
        for line in note.splitlines() if line.startswith(CARRYOVER_LINE_PREFIX)
        for match in _LINE_ENTRY_RE.finditer(line[len(CARRYOVER_LINE_PREFIX):])
    }


def carryover_answers(note: object, question: object) -> bool:
    """True when a question names the last show and a topic the note's last-show line holds."""
    if (
        not isinstance(question, str)
        or not _LAST_SHOW_ANCHOR_RE.search(question)
        or _THIS_SHOW_ANCHOR_RE.search(question)
        or _IDENTITY_QUESTION_RE.search(question)
    ):
        return False
    carried = _carried_labels(note)
    return any(pattern.search(question) and carried.intersection(labels) for pattern, labels in _QUESTION_TOPICS)


def _parse(data: bytes) -> list[Item] | None:
    if not data or len(data) > MAX_FILE_BYTES:
        return None
    try:
        document = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if type(document) is not dict or set(document) != {"items", "schema_version"}:
        return None
    if type(document["schema_version"]) is not int or document["schema_version"] != SCHEMA_VERSION:
        return None
    raw_items = document["items"]
    if type(raw_items) is not list or len(raw_items) > MAX_ITEMS:
        return None
    items: list[Item] = []
    for entry in raw_items:
        if type(entry) is not list or len(entry) != 2 or not isinstance(entry[0], str) or entry[0] not in MEMO_LABELS:
            return None
        label, value = entry[0], memo_value(entry[1])
        if not value or (MEMO_LABELS[label][1] and not _NEXT_SHOW_RE.search(value)):
            return None
        items.append((label, value))
    if len(render_carryover_line(items)) > MAX_LINE_CHARS:
        return None
    return items


class ShowCarryoverStore:
    """The last closed show's selected items, loaded once and replaced atomically at close."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._items: list[Item] = []
        self.finalized = 0
        self.load_errors = 0
        self.write_errors = 0
        try:
            with self.path.open("rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
        except FileNotFoundError:
            return
        except OSError:
            self.load_errors += 1
            return
        items = _parse(data)
        if items is None:
            self.load_errors += 1
            return
        self._items = items

    @classmethod
    def from_env(cls) -> ShowCarryoverStore | None:
        return cls(carryover_path()) if carryover_enabled() else None

    @property
    def items(self) -> list[Item]:
        return list(self._items)

    def line(self) -> str:
        return render_carryover_line(self._items)

    def finalize(self, items: list[Item]) -> bool:
        """Replace the file with ``items``; on failure keep the old file and copy."""
        items = [(label, value) for label, value in items]
        data = json.dumps(
            {"items": [list(item) for item in items], "schema_version": SCHEMA_VERSION},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        temp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
            temp = None
        except OSError:
            self.write_errors += 1
            return False
        finally:
            if temp is not None:
                try:
                    temp.unlink()
                except OSError:
                    pass
        self._items = items
        self.finalized += 1
        return True

    def health(self) -> dict[str, int]:
        return {
            "carried_items": len(self._items),
            "finalized": self.finalized,
            "load_errors": self.load_errors,
            "write_errors": self.write_errors,
        }
