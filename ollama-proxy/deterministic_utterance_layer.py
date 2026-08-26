"""D1 deterministic utterance layer: code-guaranteed broadcast behaviors.

Two trained correction candidates (E2-C1, E2-C2) proved that the hard/perfect
broadcast gates do not close by adjusting training dose or learning rate: the
model keeps recalling session-past viewer names without current-turn grounding,
keeps echoing rejected alternatives, and keeps missing recall questions it has
the evidence to answer.  Following the roadmap v3 principle (deterministic
layers over prompt/model behavior), this module makes those behaviors a
property of code operating only on evidence the proxy actually holds this
turn.  It never sees, and must never see, any evaluation fixture's check
patterns.

Parts (see AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md):

- P2 ``guard_session_past_tokens``: a Hangul token that appeared in an earlier
  user message of this session but is absent from the entire current prompt is
  a weight-memory recall with no live grounding; it is replaced with a neutral
  deictic ("그거") instead of being spoken.  Tokens present anywhere in the
  current prompt (topic block, briefing, memory retrieval, history window,
  the current message) are never touched.
- P3 ``answer_recall_question``: a recall-shaped question ("…뭐였지?",
  "…하기로 했지?", "기억나?") is answered deterministically by extracting the
  decided option from this turn's evidence pool ("S는 A 말고 B…" → B,
  "내 X는 Y야" → Y).  When the pool holds no matching decision the model draft
  is replaced by a safe don't-remember fallback rather than a guess — but only
  for a *probe* that asks for a value the user did not supply
  (``is_recall_probe``).  A confirmation ("우리 X는 Y로 하기로 했지?") carries
  its own answer and is left to the model.  ``echo_grounded_fact`` covers the
  gap between the two: a question whose answer sits verbatim in this turn's
  evidence is answered by echoing that sentence in 반말, but only when the
  draft failed to use it.
- P4 ``suppress_rejected_branch``: for every "A 말고/아니라 B" decision visible
  in the pool, response sentences that repeat the rejected A-branch are
  dropped; when the current user message itself carries such a proposal and
  the surviving text no longer names its subject, a deterministic
  acknowledgement of subject+B is prepended.
- P5 ``ensure_donation_engagement``: on a donation-continuation turn whose
  draft never thanks the viewer, one fixed neutral thanks line is appended.
  The layer never repeats any part of the donation message, and when that
  message trips a conservative unsafe-content screen
  (``strip_unsafe_donation_echo``) draft sentences that parrot it are dropped
  first, so nothing said to AIRI is read back on air.

All behavior sits behind ``AIRI_DETERMINISTIC_UTTERANCE_LAYER`` (default off).
With the flag off every entry point returns its input unchanged.  Pure
functions plus one small session-scoped token cache owned by the caller.
"""
from __future__ import annotations

import os
import re
from typing import Any, Iterable

DETERMINISTIC_UTTERANCE_LAYER_ENABLED = str(
    os.environ.get("AIRI_DETERMINISTIC_UTTERANCE_LAYER", "")
).strip().lower() in {"1", "true", "yes", "on"}

_HANGUL_RUN_RE = re.compile(r"[가-힣]{2,}")
_TOKEN_RE = re.compile(r"[0-9a-z가-힣]{2,}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|(?<=[다요지네자래]\!)\s+")
_DEICTIC = "그거"
_RECALL_FALLBACK = "음… 그건 지금 확실하게 기억나지 않아. 한 번만 다시 알려줄래?"

# Common vocabulary that legitimately recurs across turns without being
# viewer-specific content; never treated as a session-past-only token.
_COMMON_STOPWORDS = frozenset({
    "오늘", "지금", "아까", "우리", "여러분", "시청자", "구독자", "방송", "채팅",
    "고마워", "고맙다", "감사", "잠깐", "그거", "그건", "그래", "좋아", "좋다",
    "진짜", "정말", "같이", "먼저", "다시", "이제", "여기", "저기", "거기",
    "하나", "가지", "얘기", "이야기", "생각", "마음", "사람", "시간", "다음",
    "처음", "마지막", "그렇게", "이렇게", "저렇게", "근데", "그리고", "그래서",
    "하지만", "말고", "아니라", "우와", "하하", "그치", "맞아", "맞다", "안녕",
})

_RECALL_QUESTION_RES = (
    re.compile(r"뭐였지|뭐라고\s*했지|뭐랬지|뭐라\s*했지"),
    re.compile(r"기억\s*나|기억해|기억나니"),
    re.compile(r"(?:하|가|긋|걸|찍|흔들|넣|당기|덮|지키|잠그|올리|채우|막|깎|돌리|보내|두)?기로\s*했(?:었)?(?:지|어|나|는데)"),
    re.compile(r"어떻게\s*(?:하|했)(?:기로)?\s*했"),
    re.compile(r"(?:어디|언제|누구|몇)\s*(?:에서|에|로)?\s*.{0,10}(?:한다고|라고)\s*했"),
)

# The unknown a recall *probe* asks for.  A recall question without any of
# these supplies its own answer and is a confirmation — see is_recall_probe.
_INTERROGATIVE_RE = re.compile(
    r"뭐였|뭐라|뭐랬|무슨|무엇|어떻게|어떤|어느|어디|언제|누구|누가|몇|얼마|왜|기억\s*(?:나|해|하니|나니)"
)

# "S는/S를 … A 말고/아니라 B …" — capture the phrase right before 말고/아니라
# (the rejected branch) and the phrase right after (the affirmed branch).
# The subject needs at least two characters: with one allowed, "검은 잉크 말고
# 남색 잉크로" was read as subject "검" + rejected "잉크" and acknowledged as
# "좋아, 검은 남색 잉크로 갈게!".  Object marking is accepted too, because a
# proposal often names its subject as the object ("활자함을 … 열자고 했습니다").
_REJECTED_BRANCH_RE = re.compile(
    r"(?:(?P<subject>[가-힣0-9a-z]{2,12})(?:은|는|을|를)\s+)?"
    r"(?P<rejected>[가-힣0-9a-z]{1,12}(?:\s+[가-힣0-9a-z]{1,12})?)\s*"
    r"(?:말고|(?:이|가)?\s*아니라)\s*"
    r"(?P<affirmed>[가-힣0-9a-z]{1,12}(?:\s+[가-힣0-9a-z]{1,12})?)"
)
_TRAILING_DECISION_VERB_RE = re.compile(
    r"(?:하|가|긋|걸|찍|흔들|넣|당기|덮|지키|잠그|올리|채우|막|깎|돌리|보내|두)자(?:고)?"
)
_POSSESSIVE_FACT_RE = re.compile(
    r"내\s*([가-힣0-9a-z ]{1,14}?)[은는]\s*([가-힣0-9a-z]{2,14}?)(?:이야|이예요|이다|야|예요|다)(?![가-힣])"
)

_JOSA_STRIP_RE = re.compile(
    r"(으로|로|은|는|이|가|을|를|에|의|도|만|랑|이랑|부터|까지|처럼|보다|한테|에서)$"
)


def _final_jongseong(token: str) -> int:
    for char in reversed(token):
        if "가" <= char <= "힣":
            return (ord(char) - 0xAC00) % 28
    return 0


def _with_ro(token: str) -> str:
    jong = _final_jongseong(token)
    return token + ("로" if jong in (0, 8) else "으로")


def _with_rago(token: str) -> str:
    return token + ("라고" if _final_jongseong(token) == 0 else "이라고")


def _content_tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall((text or "").lower())}


def split_sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text or "") if part and part.strip()]
    return parts if parts else ([text.strip()] if text and text.strip() else [])


class SessionTokenCache:
    """Hangul tokens seen in earlier user messages, per session, bounded."""

    def __init__(self, max_sessions: int = 64, max_tokens: int = 8000) -> None:
        self._max_sessions = max_sessions
        self._max_tokens = max_tokens
        self._sessions: dict[str, set[str]] = {}

    def snapshot(self, session_id: str | None) -> frozenset[str]:
        if not session_id:
            return frozenset()
        return frozenset(self._sessions.get(session_id, ()))

    def observe(self, session_id: str | None, user_text: str | None) -> None:
        if not session_id or not user_text:
            return
        tokens = self._sessions.get(session_id)
        if tokens is None:
            while len(self._sessions) >= self._max_sessions:
                self._sessions.pop(next(iter(self._sessions)))
            tokens = self._sessions.setdefault(session_id, set())
        for run in _HANGUL_RUN_RE.findall(user_text):
            if len(tokens) >= self._max_tokens:
                break
            stripped_once = _JOSA_STRIP_RE.sub("", run)
            stripped_twice = _JOSA_STRIP_RE.sub("", stripped_once)
            for piece in {run, stripped_once, stripped_twice}:
                if (
                    len(piece) >= 2
                    and piece not in _COMMON_STOPWORDS
                    and _JOSA_STRIP_RE.sub("", piece) not in _COMMON_STOPWORDS
                ):
                    tokens.add(piece)


session_cache = SessionTokenCache()


def guard_session_past_tokens(
    text: str, *, past_tokens: frozenset[str] | set[str], prompt_text: str,
) -> tuple[str, list[str]]:
    """P2: replace session-past tokens with no current-prompt grounding."""
    if not text or not past_tokens:
        return text, []
    prompt = prompt_text or ""
    replaced: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        run = match.group(0)
        candidates = sorted(
            (
                token
                for token in past_tokens
                if len(token) >= 2 and token in run and token not in prompt
                and token not in _COMMON_STOPWORDS
                and _JOSA_STRIP_RE.sub("", token) not in _COMMON_STOPWORDS
            ),
            key=len,
            reverse=True,
        )
        if not candidates:
            return run
        new_run = run
        for token in candidates:
            if token in new_run:
                replaced.append(token)
                new_run = new_run.replace(token, _DEICTIC)
        return new_run

    guarded = _HANGUL_RUN_RE.sub(_sub, text)
    if replaced:
        for wrong, right in (
            (f"{_DEICTIC}은", f"{_DEICTIC}는"), (f"{_DEICTIC}이 ", f"{_DEICTIC}가 "),
            (f"{_DEICTIC}을", f"{_DEICTIC}를"), (f"{_DEICTIC}으로", f"{_DEICTIC}로"),
        ):
            guarded = guarded.replace(wrong, right)
    return guarded, replaced


def is_recall_question(user_text: str) -> bool:
    text = user_text or ""
    return any(pattern.search(text) for pattern in _RECALL_QUESTION_RES)


def is_recall_probe(user_text: str) -> bool:
    """A recall question that asks for a value the user did not supply.

    ``is_recall_question`` matches two different turn shapes.  A *probe*
    ("내 좌석 번호 기억나?", "불씨는 어떻게 하기로 했지?") asks for something
    only the assistant can supply, so answering it without evidence is a
    guess.  A *confirmation* ("우리 불씨는 잔불로 두기로 했지?") already
    carries its own answer, so there is nothing to invent and replacing the
    draft only destroys a correct reply.

    The D1 matrix paid for conflating them: 176 of 320 continuity callbacks —
    all confirmation-shaped — were replaced by the don't-remember fallback,
    and ``long_callback``/``complete_show_arc`` scored exactly 0.0 on all four
    arms.  Only probes reach the fallback now.
    """
    text = user_text or ""
    if not is_recall_question(text):
        return False
    return bool(_INTERROGATIVE_RE.search(text))


def _question_tokens(user_text: str) -> set[str]:
    tokens = set()
    for run in _HANGUL_RUN_RE.findall(user_text or ""):
        stripped = _JOSA_STRIP_RE.sub("", run)
        for piece in (run, stripped):
            if len(piece) >= 2 and piece not in _COMMON_STOPWORDS:
                tokens.add(piece)
    return tokens


def find_rejected_branches(pool_text: str) -> list[dict[str, str]]:
    """Every "… A 말고/아니라 B" decision visible in the pool."""
    found: list[dict[str, str]] = []
    for line in (pool_text or "").splitlines():
        for match in _REJECTED_BRANCH_RE.finditer(line):
            rejected = match.group("rejected")
            affirmed_parts = match.group("affirmed").split()
            # "…부터 열자고 했습니다" quotes the decision verb; it is not part of
            # the affirmed option and reads as "윗칸 열자고로 갈게" if kept.
            if len(affirmed_parts) == 2 and (
                _TRAILING_DECISION_VERB_RE.fullmatch(affirmed_parts[-1])
                or affirmed_parts[-1].endswith("자고")
            ):
                affirmed_parts.pop()
            affirmed = _JOSA_STRIP_RE.sub("", " ".join(affirmed_parts))
            subject = match.group("subject") or ""
            if rejected in _COMMON_STOPWORDS:
                continue
            found.append({
                "subject": subject,
                "rejected": rejected,
                "affirmed": affirmed,
                "line": line.strip(),
            })
    return found


def answer_recall_question(user_text: str, pool_text: str) -> str | None:
    """P3: deterministic answer for a recall question, from pool evidence only."""
    if not is_recall_question(user_text):
        return None
    question_tokens = _question_tokens(user_text)
    if not question_tokens:
        return None
    for match in _POSSESSIVE_FACT_RE.finditer(pool_text or ""):
        topic = match.group(1).strip()
        value = match.group(2)
        topic_tokens = {piece for piece in _HANGUL_RUN_RE.findall(topic) if len(piece) >= 2}
        if topic_tokens and any(
            any(topic_piece in question or question in topic_piece for question in question_tokens)
            for topic_piece in topic_tokens
        ):
            return f"{value}! 아까 네 {topic}{'은' if _final_jongseong(topic) else '는'} {_with_rago(value)} 했었잖아."
    for decision in find_rejected_branches(pool_text):
        subject = decision["subject"]
        affirmed = decision["affirmed"]
        if not affirmed:
            continue
        line_tokens = {
            piece for piece in _HANGUL_RUN_RE.findall(decision["line"])
            if len(piece) >= 2 and piece not in _COMMON_STOPWORDS and piece != decision["rejected"]
        }
        if any(
            any(token in line_piece or line_piece in token for line_piece in line_tokens)
            for token in question_tokens
        ):
            lead = f"{subject}{'은' if _final_jongseong(subject) else '는'} " if subject else ""
            return f"{lead}{_with_ro(affirmed)} 하기로 했지! 그대로 가자."
    return None


# Predicate endings stripped before comparing a question with an evidence
# sentence: the same fact is asked in "…놓았나요?" and stated in "…놓았습니다."
_PREDICATE_ENDINGS = tuple(sorted(
    (
        "었습니다", "았습니다", "했습니다", "습니다", "입니다",
        "었나요", "았나요", "했나요", "나요",
        "었어요", "았어요", "어요", "아요", "예요", "에요",
        "었어", "았어", "했어", "었지", "았지", "했지",
    ),
    key=len,
    reverse=True,
))

# Polite → 반말 rewrite applied at sentence end only.
_BANMAL_ENDINGS = tuple(sorted(
    (
        ("했습니다", "했어"), ("었습니다", "었어"), ("았습니다", "았어"),
        ("했어요", "했어"), ("합니다", "해"), ("습니다", "어"), ("입니다", "이야"),
        ("네요", "네"), ("어요", "어"), ("아요", "아"), ("예요", "야"), ("에요", "야"),
        ("죠", "지"),
    ),
    key=lambda pair: len(pair[0]),
    reverse=True,
))

_QUOTED_SPAN_RE = re.compile(r"\"([^\"\n]+)\"|“([^”\n]+)”")
_SENTENCE_END_PUNCTUATION = ".!?…"
_MIN_EVIDENCE_SENTENCE_LENGTH = 6
_MIN_EVIDENCE_OVERLAP = 2


def _content_stems(text: str) -> set[str]:
    """Content stems of one utterance: no josa, no stopwords, no interrogatives."""
    stems: set[str] = set()
    for run in _HANGUL_RUN_RE.findall(text or ""):
        piece = _JOSA_STRIP_RE.sub("", run)
        if not piece or piece in _COMMON_STOPWORDS or _INTERROGATIVE_RE.search(piece):
            continue
        for ending in _PREDICATE_ENDINGS:
            if piece.endswith(ending):
                piece = piece[: -len(ending)]
                break
        if piece and piece not in _COMMON_STOPWORDS:
            stems.add(piece)
    return stems


def _evidence_sentences(pool_text: str) -> list[str]:
    """Statement-shaped sentences the pool can be quoted from.

    A briefing line carries its evidence inside quotes and its author outside
    them ('- 방금 흐름: 오린 "…"'), so a quoted line contributes only what was
    quoted; the label never becomes speakable text.
    """
    sentences: list[str] = []
    for line in (pool_text or "").splitlines():
        quoted = [
            group
            for match in _QUOTED_SPAN_RE.finditer(line)
            for group in match.groups()
            if group
        ]
        for candidate in quoted or split_sentences(line):
            sentence = candidate.strip()
            if len(sentence) < _MIN_EVIDENCE_SENTENCE_LENGTH:
                continue
            if _INTERROGATIVE_RE.search(sentence):
                continue
            sentences.append(sentence)
    return sentences


def _to_banmal(sentence: str) -> str:
    body = sentence.strip()
    tail = ""
    while body and body[-1] in _SENTENCE_END_PUNCTUATION:
        tail = body[-1] + tail
        body = body[:-1].rstrip()
    for polite, casual in _BANMAL_ENDINGS:
        if body.endswith(polite):
            body = body[: -len(polite)] + casual
            break
    return body + (tail if tail else ".")


def echo_grounded_fact(
    user_text: str, pool_text: str, *, draft: str | None = None,
) -> str | None:
    """P3 evidence echo: answer a question by quoting the evidence this turn holds.

    ``answer_recall_question`` only reads two decision shapes.  A plain
    question whose answer is sitting verbatim in the pool ("오늘 측우통은
    어디에 놓았나요?" against "…북쪽 난간 가까이에 놓았습니다.") fell through it
    into the don't-remember fallback even though the turn was given the fact.
    This echoes that one sentence in 반말 instead — never a guess, only text
    the pool already contains.

    ``draft`` is the model's own candidate: when it already uses the evidence,
    the model did not fail and its wording is kept.
    """
    if not _INTERROGATIVE_RE.search(user_text or ""):
        return None
    if find_rejected_branches(user_text or ""):
        return None
    question_stems = _content_stems(user_text)
    if len(question_stems) < _MIN_EVIDENCE_OVERLAP:
        return None
    best_sentence = ""
    best_overlap = 0
    for sentence in _evidence_sentences(pool_text):
        overlap = len(_content_stems(sentence) & question_stems)
        if overlap >= _MIN_EVIDENCE_OVERLAP and overlap > best_overlap:
            best_sentence = sentence
            best_overlap = overlap
    if not best_sentence:
        return None
    if draft and (_content_stems(best_sentence) - question_stems) & _content_stems(draft):
        return None
    return _to_banmal(best_sentence)


def suppress_rejected_branch(
    text: str, *, pool_text: str, user_text: str, content_free: bool = False,
) -> tuple[str, list[str], bool]:
    """P4: drop sentences repeating a rejected branch; ack a live proposal."""
    decisions = find_rejected_branches(pool_text)
    if not decisions:
        return text, [], False
    denied: set[str] = set()
    for decision in decisions:
        rejected = decision["rejected"]
        if not rejected:
            continue
        denied.add(rejected)
        # "긁어내지 말고" rejects the verb stem; the draft may conjugate it
        # differently ("긁어내라"), so also deny the ending-stripped stem.
        if len(rejected) > 2 and rejected.endswith(("지", "게")):
            denied.add(rejected[:-1])
    sentences = split_sentences(text)
    dropped: list[str] = []
    kept: list[str] = []
    for sentence in sentences:
        hits = [phrase for phrase in denied if phrase in sentence]
        if hits:
            dropped.extend(hits)
        else:
            kept.append(sentence)
    result = " ".join(kept).strip()
    ack_added = False
    live = [decision for decision in find_rejected_branches(user_text or "") if decision["affirmed"]]
    if live:
        proposal = live[0]
        subject = proposal["subject"]
        if subject and subject not in result:
            lead = f"좋아, {subject}{'은' if _final_jongseong(subject) else '는'} {_with_ro(proposal['affirmed'])} 갈게!"
            # A content-free listening line ("음, 잠깐만.") says nothing to keep,
            # so the acknowledgement replaces it instead of trailing it.
            if content_free:
                result = lead
            else:
                result = f"{lead} {result}".strip() if result else lead
            ack_added = True
    if not result:
        result = _RECALL_FALLBACK
    return result, dropped, ack_added


DONATION_THANKS_LINE = "후원 고마워!"
_THANKS_TOKEN_RE = re.compile(r"고마워|고맙|감사")
_DONATION_PREFIXES = ("[YouTube]", "[후원]")
# A draft sentence sharing this many consecutive characters with an unsafe
# donation message is parroting it, not composing.
_MIN_DONATION_ECHO_SPAN = 6

# Conservative unsafe-content screen for the donation message.  It decides only
# whether AIRI may repeat any of the viewer's own words — never whether the
# viewer may speak, and never a block.  A false positive costs one dropped
# draft sentence plus the neutral thanks line, while a false negative reads
# sexual, harassing, or racist text back on air, so the list leans toward
# catching.  Bare "년"/"벗" are excluded because they are ordinary words
# (작년, 벗어나다); only their slur and undressing forms are listed.
_UNSAFE_DONATION_RE = re.compile(
    # 성적 표현
    "가슴|신음|섹스|섹시|야한|야동|자위|성희롱|만지|팬티|속옷"
    r"|벗겨|벗기|옷\s*벗|벗어\s*(?:줘|봐|보)"
    # 인종·차별
    "|흑인|백인|인종|장애인"
    # 욕설
    "|병신|씨발|시발|좆|새끼|(?:개|미친|썅)년|년아"
)


def _donation_message_body(user_text: str) -> str:
    body = (user_text or "").strip()
    for prefix in _DONATION_PREFIXES:
        if body.startswith(prefix):
            body = body[len(prefix):].strip()
    return body


def _repeats_donation_span(sentence: str, compact_message: str) -> bool:
    compact = re.sub(r"\s+", "", sentence)
    span = _MIN_DONATION_ECHO_SPAN
    if len(compact) < span or len(compact_message) < span:
        return False
    return any(
        compact_message[start:start + span] in compact
        for start in range(len(compact_message) - span + 1)
    )


def strip_unsafe_donation_echo(text: str, *, user_text: str) -> tuple[str, int]:
    """P5 screen: drop draft sentences that parrot an unsafe donation message.

    Human rating of a real-chat replay found the old quoting P5 reading
    harassing donation text back on air verbatim.  Nothing the layer adds can
    quote the message any more, but the model's own draft can still parrot it,
    so when the message trips ``_UNSAFE_DONATION_RE`` every sentence sharing a
    ``_MIN_DONATION_ECHO_SPAN``-character run with it is removed.  Whitespace
    is ignored on both sides so a respaced repeat is still caught.  Returns the
    surviving text (possibly empty) and how many sentences were dropped.
    """
    message = _donation_message_body(user_text)
    if not text or not message or not _UNSAFE_DONATION_RE.search(message):
        return text, 0
    compact_message = re.sub(r"\s+", "", message)
    kept: list[str] = []
    stripped = 0
    for sentence in split_sentences(text):
        if _repeats_donation_span(sentence, compact_message):
            stripped += 1
        else:
            kept.append(sentence)
    if not stripped:
        return text, 0
    return " ".join(kept).strip(), stripped


def ensure_donation_engagement(text: str, *, user_text: str) -> tuple[str, bool]:
    """P5: thank the donation without ever repeating what it said."""
    if not _donation_message_body(user_text):
        return text, False
    text, _stripped = strip_unsafe_donation_echo(text, user_text=user_text)
    if text and _THANKS_TOKEN_RE.search(text):
        return text, False
    combined = f"{text} {DONATION_THANKS_LINE}".strip() if text else DONATION_THANKS_LINE
    return combined, True


DONATION_CONTINUATION_MARKER = "[후원 본문 이어말하기]"
# Producers (the live-broadcast director, the broadcast simulator) append the
# turn's recall material to the system message.  Contract prose must stay out
# of the P3/P4 decision pool, but that briefing is exactly the evidence the
# turn was given, and excluding all system content excluded it too: in the D1
# matrix every seed→callback distance was 38-66 turns, so the decision never
# sat in the 8-turn history window and reached the model only through the
# briefing.  P3 therefore found "no evidence" on every long callback and
# overwrote correct answers with the don't-remember fallback.
#
# This marker is the opt-in seam, same shape as DONATION_CONTINUATION_MARKER:
# whatever a system message carries from the marker to its end is evidence,
# and everything before it stays prompt-only.
BRIEFING_EVIDENCE_MARKER = "[턴 근거 메모]"


def system_briefing_evidence(content: str) -> str:
    """The marked evidence tail of one system message, or ""."""
    index = (content or "").find(BRIEFING_EVIDENCE_MARKER)
    if index < 0:
        return ""
    evidence = content[index + len(BRIEFING_EVIDENCE_MARKER):]
    return evidence.split(DONATION_CONTINUATION_MARKER, 1)[0].strip()


def build_layer_inputs(
    *,
    user_text: str | None,
    briefing_evidence: str | None,
    memory_result: Any = None,
    history_texts: Iterable[str] | None = None,
    session_id: str | None = None,
    original_messages: Iterable[dict[str, Any]] | None = None,
    live_context_note: str | None = None,
) -> dict[str, Any] | None:
    """Assemble ``apply_deterministic_utterance_layer`` kwargs, or None when off.

    Reads ``memory_result`` attributes only after the flag check (same
    fail-safe shape as ``handle_grounding_guard.build_grounding_pools``), and
    owns the session-cache ordering: the past-token snapshot is taken before
    the current user text is observed, so the current turn never grounds
    itself out of P2.
    """
    if not DETERMINISTIC_UTTERANCE_LAYER_ENABLED:
        return None
    memory_block = getattr(memory_result, "block", "") or ""
    journal_messages = getattr(memory_result, "journal_messages", None) or ()
    evidence_parts = [user_text or "", briefing_evidence or "", memory_block]
    for message in journal_messages:
        if isinstance(message, dict) and message.get("content"):
            evidence_parts.append(str(message["content"]))
    for item in history_texts or ():
        if item:
            evidence_parts.append(str(item))
    # System/instruction text grounds P2 (the model saw it) but is kept out of
    # the P3/P4 evidence pool: contract prose legitimately contains "…지 말고"
    # phrasing that is instruction, not a broadcast decision.
    donation_turn = False
    system_parts: list[str] = []
    if live_context_note:
        system_parts.append(live_context_note)
        donation_turn = DONATION_CONTINUATION_MARKER in live_context_note
        marked = system_briefing_evidence(live_context_note)
        if marked:
            evidence_parts.append(marked)
    for message in original_messages or ():
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content:
            continue
        if DONATION_CONTINUATION_MARKER in content:
            donation_turn = True
        if message.get("role") == "system":
            system_parts.append(content)
            marked = system_briefing_evidence(content)
            if marked:
                evidence_parts.append(marked)
    pool_text = "\n".join(part for part in evidence_parts if part)
    prompt_text = "\n".join(part for part in [pool_text, *system_parts] if part)
    past_tokens = session_cache.snapshot(session_id)
    session_cache.observe(session_id, user_text)
    return {
        "user_text": user_text or "",
        "prompt_text": prompt_text,
        "pool_text": pool_text,
        "past_tokens": past_tokens,
        "donation_turn": donation_turn,
    }


# M7-10 (2026-08-26, human-rated critical turn 23 of replay 06b-r3): a chat
# asking whether a harassment rumour is true was answered with a leading "응",
# which reads as an admission on a live clip.  The guard fires only on that
# shape — an allegation-type question plus a leading affirmation — and swaps
# the affirmation for an explicit non-confirmation.  Nothing else is rewritten.
_ALLEGATION_TOPIC_RE = re.compile(
    r"(?:성?희롱|성추행|추행|성폭|폭행|학폭|학교\s*폭력|사기|횡령|불륜|바람\s*피|논란|의혹|루머|"
    r"고소|고발|범죄|마약|음주\s*운전|갑질|괴롭|따돌|폭언|협박|전과|탈세|표절|조작)"
)
_ALLEGATION_ASK_RE = re.compile(r"(?:진짜|정말|사실|실화|맞[아냐죠]|였[어다]|했[다대어]|라는데|라며|다며|다던데|냐|\?)")
_LEADING_AFFIRMATION_RE = re.compile(
    r"^(?:응|웅|넵|네|예|맞아요|맞아|맞지|그래|그렇지|그럼|당연하지|당연|물론|ㅇㅇ|ㅇㅋ)(?=[,.!~…\s]|$)[,.!~…\s]*"
)
ALLEGATION_DEFLECTION_LINE = "그런 얘기는 내가 확인한 적 없어."


def is_allegation_question(user_text: str) -> bool:
    text = str(user_text or "")
    return bool(_ALLEGATION_TOPIC_RE.search(text) and _ALLEGATION_ASK_RE.search(text))


def deflect_leading_affirmation(text: str, *, user_text: str) -> tuple[str, bool]:
    """Replace a leading affirmation with a non-confirmation on allegation questions."""
    if not is_allegation_question(user_text):
        return text, False
    stripped = text.lstrip()
    match = _LEADING_AFFIRMATION_RE.match(stripped)
    if match is None:
        return text, False
    rest = stripped[match.end():].strip()
    return (ALLEGATION_DEFLECTION_LINE + " " + rest if rest else ALLEGATION_DEFLECTION_LINE), True


def apply_deterministic_utterance_layer(
    content: str,
    *,
    user_text: str,
    prompt_text: str,
    pool_text: str,
    past_tokens: frozenset[str] | set[str],
    donation_turn: bool,
    content_free: bool = False,
) -> tuple[str, dict[str, object] | None]:
    """Apply P3 → P4 → P2 → P5 to one complete public dialogue candidate.

    ``content_free`` marks a candidate that carries no claim of its own (the
    proxy's grounding-silence listening line).  There is nothing to preserve in
    it, so a live-proposal acknowledgement replaces it rather than trailing it.
    """
    if not content:
        return content, None
    signal: dict[str, object] = {}
    text = content

    recall_answer = answer_recall_question(user_text, pool_text)
    if recall_answer is not None:
        signal["recall"] = "answered"
        text = recall_answer
    else:
        echoed = echo_grounded_fact(user_text, pool_text, draft=text)
        if echoed is not None:
            signal["recall"] = "echoed"
            text = echoed
        elif is_recall_probe(user_text):
            # No pool decision matched a question that asked for a value the
            # user did not supply.  Answering anyway would be a guess.
            signal["recall"] = "fallback"
            text = _RECALL_FALLBACK

    # Every recall branch above already produced a complete, evidence-bound
    # line; re-running P4 on it wrapped the fallback in an acknowledgement and
    # re-running P2 rewrote its own words ("한 번만" → "한 그거").
    if signal.get("recall") is None:
        text, dropped, ack_added = suppress_rejected_branch(
            text, pool_text=pool_text, user_text=user_text,
            content_free=content_free,
        )
        if dropped:
            signal["rejected_branch_dropped"] = sorted(set(dropped))
        if ack_added:
            signal["proposal_ack_added"] = True
        if text == _RECALL_FALLBACK and dropped:
            # Every sentence was a rejected branch, so what survives is the
            # safe recall line and not model content: P2 must leave it alone.
            signal["recall"] = "fallback"

    if signal.get("recall") is None:
        text, replaced = guard_session_past_tokens(
            text, past_tokens=past_tokens, prompt_text=prompt_text,
        )
        if replaced:
            signal["past_only_replaced"] = sorted(set(replaced))

    if donation_turn:
        text, stripped = strip_unsafe_donation_echo(text, user_text=user_text)
        if stripped:
            signal["donation_unsafe_stripped"] = stripped
        text, echo_added = ensure_donation_engagement(text, user_text=user_text)
        if echo_added:
            signal["donation_echo_added"] = True

    text, deflected = deflect_leading_affirmation(text, user_text=user_text)
    if deflected:
        signal["allegation_deflected"] = True

    return text, (signal or None)
