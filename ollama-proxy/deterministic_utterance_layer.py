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
  its own answer and is left to the model.
- P4 ``suppress_rejected_branch``: for every "A 말고/아니라 B" decision visible
  in the pool, response sentences that repeat the rejected A-branch are
  dropped; when the current user message itself carries such a proposal and
  the surviving text no longer names its subject, a deterministic
  acknowledgement of subject+B is prepended.
- P5 ``ensure_donation_engagement``: on a donation-continuation turn whose
  draft shares no content token with the donation message, a deterministic
  thanks line quoting the message is appended.

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
    r"뭐였|뭐라|뭐랬|무슨|무엇|어떻게|어떤|어디|언제|누구|누가|몇|얼마|왜|기억\s*(?:나|해|하니|나니)"
)

# "S는 … A 말고/아니라 B …" — capture the phrase right before 말고/아니라 (the
# rejected branch) and the phrase right after (the affirmed branch).
_REJECTED_BRANCH_RE = re.compile(
    r"([가-힣0-9a-z ]{1,24}?)([가-힣0-9a-z]{2,12})\s*(?:말고|(?:이|가)?\s*아니라)\s*([가-힣0-9a-z]{2,12})"
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
            rejected = match.group(2)
            affirmed = _JOSA_STRIP_RE.sub("", match.group(3))
            prefix = (match.group(1) or "").strip()
            subject_match = re.match(r"([가-힣0-9a-z]{2,12})", prefix)
            subject = _JOSA_STRIP_RE.sub("", subject_match.group(1)) if subject_match else ""
            if rejected in _COMMON_STOPWORDS or len(rejected) < 2:
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


def suppress_rejected_branch(
    text: str, *, pool_text: str, user_text: str,
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
            result = f"{lead} {result}".strip() if result else lead
            ack_added = True
    if not result:
        result = _RECALL_FALLBACK
    return result, dropped, ack_added


def ensure_donation_engagement(text: str, *, user_text: str) -> tuple[str, bool]:
    """P5: guarantee token overlap with, and thanks for, the donation message."""
    message_tokens = _content_tokens(user_text)
    if not message_tokens:
        return text, False
    if _content_tokens(text) & message_tokens:
        return text, False
    clip = (user_text or "").strip()
    for prefix in ("[YouTube]", "[후원]"):
        if clip.startswith(prefix):
            clip = clip[len(prefix):].strip()
    clip = clip[:40].strip()
    if not clip:
        return text, False
    addition = f"'{clip}' 이렇게 보내 줘서 진짜 고마워!"
    combined = f"{text} {addition}".strip() if text else addition
    return combined, True


DONATION_CONTINUATION_MARKER = "[후원 본문 이어말하기]"


def build_layer_inputs(
    *,
    user_text: str | None,
    briefing_evidence: str | None,
    memory_result: Any = None,
    history_texts: Iterable[str] | None = None,
    session_id: str | None = None,
    original_messages: Iterable[dict[str, Any]] | None = None,
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


def apply_deterministic_utterance_layer(
    content: str,
    *,
    user_text: str,
    prompt_text: str,
    pool_text: str,
    past_tokens: frozenset[str] | set[str],
    donation_turn: bool,
) -> tuple[str, dict[str, object] | None]:
    """Apply P3 → P4 → P2 → P5 to one complete public dialogue candidate."""
    if not content:
        return content, None
    signal: dict[str, object] = {}
    text = content

    recall_answer = answer_recall_question(user_text, pool_text)
    if recall_answer is not None:
        signal["recall"] = "answered"
        text = recall_answer
    elif is_recall_probe(user_text):
        # No pool decision matched a question that asked for a value the user
        # did not supply.  Answering anyway would be a guess.
        signal["recall"] = "fallback"
        text = _RECALL_FALLBACK

    if signal.get("recall") != "answered":
        text, dropped, ack_added = suppress_rejected_branch(
            text, pool_text=pool_text, user_text=user_text,
        )
        if dropped:
            signal["rejected_branch_dropped"] = sorted(set(dropped))
        if ack_added:
            signal["proposal_ack_added"] = True

    if signal.get("recall") is None:
        text, replaced = guard_session_past_tokens(
            text, past_tokens=past_tokens, prompt_text=prompt_text,
        )
        if replaced:
            signal["past_only_replaced"] = sorted(set(replaced))

    if donation_turn:
        text, echo_added = ensure_donation_engagement(text, user_text=user_text)
        if echo_added:
            signal["donation_echo_added"] = True

    return text, (signal or None)
