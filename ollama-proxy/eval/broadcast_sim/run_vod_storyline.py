"""Run an ordered VOD-derived broadcast storyline against the local proxy.

This is a new storyline stage, not the old chat replay runner. VOD STT is
compiled into scene cards and never inserted as an assistant message. Only
sanitized, time-aligned viewer chat is sent as user input. Reports belong in an
external human-review directory and must not be committed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
CHAT_DIR = HERE.parent / "broadcast_chat"
sys.path.insert(0, str(CHAT_DIR))
import run_broadcast_chat_ab as ab  # noqa: E402

sys.path.insert(0, str(HERE.parent.parent))
import run_broadcast_sim as legacy_runner  # noqa: E402

DEFAULT_STORYLINE = HERE / "vod_storyline_20260827.json"
DEFAULT_CHAT = HERE.parent / "vod_capture_2026-08-27" / "chat.jsonl"
BRIEFING_HEADER = "[턴 브리핑 — 방송 스태프가 주는 메모야. 자연스럽게 참고만 해.]"
PUNCTUATION = " !?~.,·。！？…"
SIGNAL_STOPWORDS = {
    "이번", "현재", "장면", "이야기", "상황", "정말", "그", "더", "수", "것", "있다",
    "없다", "하다", "한다", "되는", "된다", "이어", "통해", "위해", "처럼", "같은",
}
SIGNAL_SUFFIXES = (
    "했지만", "하면서", "으로", "에서", "에게", "까지", "처럼", "보다", "만큼",
    "라고", "라는", "하며", "지만", "는데", "은", "는", "이", "가", "을", "를",
    "의", "에", "로", "도", "와", "과",
)
SOURCE_EXPERIENCE_RE = re.compile(
    r"(?<![가-힣])(?:나도|내가|나는|나를|나에게|나의|나와|나한테|내 기억|내 경험|내(?=\s)|나(?=\s|[.!?,~…])|날(?=\s|[.!?,~…])|저도|저는|제가|저를|저에게|저의|저와|저한테|제 기억|제 경험|제(?=\s)|저(?=\s|[.!?,~…])|"
    r"꿈을\s*꿨어|꿈을\s*꿨|꿈을\s*꾸고|꿈을\s*꾼|기억이\s*(?:안|잘\s*안)\s*나|느꼈어|느껴졌어|"
    r"병원에\s*(?:가서|갔|가야)|진료(?:받아|받고|받았)|"
    r"(?:약|캔디|사탕)(?:을|를)?\s*먹(?:었|고|을))",
)
IRRELEVANT_KNOWLEDGE_RE = re.compile(
    r"(?:뉴스|기사|속보|정치|주가|경제|날씨|검색해|인터넷에|최근 보도|최신 정보)"
)
STRUCTURED_REWRITE_FORMAT = {
    "type": "object",
    "properties": {
        "viewer_reaction": {
            "type": "string",
            "description": "시청자 채팅을 구체적으로 받아치는 자연스러운 한국어 반말 한 문장",
        },
        "event_callback_emotion": {
            "type": "string",
            "description": "이번 턴의 새 사건과 앞선 단서를 회수하고 감정 변화를 보여주는 자연스러운 한국어 반말 한 문장",
        },
        "next_hook": {
            "type": "string",
            "description": "다음 사건이나 미해결 질문으로 이어지는 자연스러운 한국어 반말 한 문장",
        },
    },
    "required": ["viewer_reaction", "event_callback_emotion", "next_hook"],
    "additionalProperties": False,
}
SLOTWISE_FIELDS = (
    "viewer_reaction",
    "event_callback_emotion",
    "next_hook",
)
# M8-9 deterministic spine. Stage 3 closed the alignment defects (advice,
# honorifics, question endings, demo dependence, role inversion, borrowed
# experience) but left the comprehension defects untouched: beat contradiction,
# fabrication against the storyline, subject inversion and one idea repeated
# across three sentences. Those are exactly the two slots that must carry the
# plot forward, so the spine speaks them from authored lines and the model is
# left with the one slot it now does well.
SPINE_FIELDS = (
    "event_callback_emotion",
    "next_hook",
)
SPINE_GENERATED_FIELDS = ("viewer_reaction",)
SLOT_MAX_TOKENS = 96
SLOT_CANDIDATE_COUNT = 16
# A slot may name the beat's entities, but reciting a long contiguous span of the
# director text is internal staging spoken aloud. It also inflates
# slot_candidate_score, which ranks candidates by overlap with that same text.
# 14 non-space characters was measured against run-81: it rejects the observed
# recitations while keeping named entities such as "히나와 마시로의 코스프레".
BEAT_RECITATION_MIN_CHARS = 14
BEAT_RECITATION_FIELDS = ("new_event", "callback", "emotion", "next_hook")
# Leaving the in-story broadcast voice: advising or instructing the viewer,
# turning a story beat into medical guidance, asking the viewer to supply the
# story, or explaining the scene away as a film set. Measured against run-82,
# this matches 10 of 96 selected slots — exactly the turns manual review
# rejected — but only 22 of 877 valid candidates, and no slot loses its whole
# candidate pool, so composition cannot starve.
OUT_OF_STORY_VOICE_RE = re.compile(
    r"(?:하|받아보|가보|쉬|참|조심하|줄이|확인해|해보|시작해|물어보|말해|들려)"
    r"(?:는|시)?\s*(?:게|것이|편이)\s*(?:좋|낫|안전|현명)"
    r"|좋을\s*것\s*같아"
    r"|[가-힣]지\s*(?:마|말아)(?![가-힣])"
    r"|더\s*열심히"
    r"|(?:말해|들려|알려|보여)\s*(?:줘|주라|주세요)"
    r"|촬영\s*중|특수\s*?효과|조명\s*때문"
)
# Internal staging spoken aloud: slot names, director-card labels and meta
# commentary about the broadcast itself. Shared by every rewrite parser so the
# story mode inherits exactly the slotwise rejection surface.
STAGING_META_RE = re.compile(
    r"(?:viewer_reaction|event_callback_emotion|next_hook|슬롯 생성|메타 발언|"
    r"(?:현재|다음|이번)\s*(?:사건|장면|줄거리|슬롯|턴|영상|사연|꿈)|"
    r"현재\s*(?:상황|시점)|사건\s*진행\s*:|"
    r"(?:새로운\s*)?사건\s*(?:으로\s*)?연결|연결해야|전개해야|진행해야|"
    r"시청자님?\s*(?:께서|가|이)|시청자\s*채팅|사용자\s*(?:가|이)|현재|방송의\s|"
    r"화자|그녀\s*(?:는|가|의)|"
    r"방송\s*(?:소품|중|에서)|다음\s*방송|"
    r"(?:사건|장면|줄거리|상황)\s*(?:이|가|은|는|을|를|으로|에서|에|의)|"
    r"지금까지의\s*(?:내용|대화)\s*(?:을|를)?\s*(?:기반으로|바탕으로)|"
    r"네가\s*(?:방금|지금까지)\s*말한\s*(?:내용|것)|환자(?:가|는)|당신|"
    r"드러납니다|드러내야|표현하고|분위기를\s*조성|다음\s*상황\s*:|"
    r"다음\s*이벤트|방금\s*들어온\s*채팅|그건\s*좀\s*있다가\s*다시\s*말해|"
    r"나중에\s*다시\s*(?:얘기|말해)|더\s*자세히\s*(?:설명|말해)\s*(?:해|줄)|"
    r"유튜브|youtube|채널|구독|콘텐츠|다음\s*회차|계속\s*(?:진행|봐)|"
    r"방송\s*(?:을|이)?\s*(?:이어|진행)|좋은\s*콘텐츠|잠깐\s*생각해\s*볼게)",
    re.IGNORECASE,
)
# CRANE (arXiv 2502.09061): leave the reasoning span unconstrained and fence
# only the final answer behind a delimiter, instead of constraining every token
# of a short slot. The larger budget is for that free reasoning span.
STORY_DELIMITER = ">>>"
STORY_MAX_TOKENS = 320
# M8-3 (run-88): one register demo per slot on non-storyline material. Each
# demo must pass parse_slot_output itself; the event demo narrates with the
# 그 사람 subject to counter the implicit self-experience growth seen in run-87.
# M8-4 (run-90) DISCARDED: appending this depth-injection/anti-impersonation
# reminder as the last line of every slot cue made things worse, not better —
# demo leakage 2 -> 7 fragment hits, 그 사람 subject 10 -> 8, question endings
# 4 -> 7, and the automatic new-event signal fell from true to false. More
# trailing instruction dilutes a 2.3B model's attention and pushes it toward
# copying surface patterns. Kept as an empty string so the contract stays
# explicit rather than silently deleted.
SLOT_DEPTH_REMINDER = ""
SLOT_FORMAT_DEMOS = {
    # run-88: the viewer_reaction demo was measured harmful (advice register
    # 2 -> 7 turns, honorific leak 2 -> 4) and is removed; the event and
    # next_hook demos hit their targets (그 사람 subject 3 -> 6, question
    # endings 10 -> 7) and are kept.
    "event_callback_emotion": (
        "새벽 두 시가 되니까 손님이 뚝 끊겼는데, 아까부터 들리던 라디오 소리까지 멎어서 "
        "그 사람은 등골이 서늘해졌어."
    ),
    "next_hook": "그때 문에 달린 종이 혼자 딸랑 울렸어.",
}
# run-85: 58/64 story calls emitted no delimiter — the 2.3B model does not
# follow the two-phase format from instructions alone. One demonstration
# teaches it (arXiv 2402.09954; 2303.08119 shows more demos hurt). The demo
# deliberately uses non-storyline material (편의점 야간 알바) so the lexical
# overlap scorer cannot be inflated, and its three sentences pass every story
# validator so a model imitating them also passes.
STORY_FORMAT_DEMO = (
    "시청자: 야간 알바 첫날인데 벌써 졸리대\n"
    "생각: 손님이 끊긴 새벽으로 이야기를 넘기자.\n"
    ">>> 첫날부터 졸린 거 완전 이해돼. 새벽 두 시가 되니까 손님이 뚝 끊기고 라디오 소리만 "
    "남아서 그 사람도 눈꺼풀이 무거워졌거든. 그런데 그때 문에 달린 종이 혼자 딸랑 울렸어."
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid JSONL: {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise SystemExit(f"JSONL row is not an object: {path}:{line_number}")
        rows.append(value)
    return rows


def normalized_text(value: object) -> str:
    return " ".join(str(value or "").split())


def signature_reason(text: str) -> str | None:
    value = normalized_text(text)
    if "츕츕" in value:
        return "chupchup_family"
    if "반갑느뇨" in value:
        return "broadcast_greeting_bangap"
    if "본녀" in value:
        return "broadcast_signature_bonnyeo"
    if value.strip(PUNCTUATION).strip() == "강림":
        return "standalone_broadcast_gangrim"
    return None


def sanitize_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    for row in rows:
        text = normalized_text(row.get("text"))
        reason = signature_reason(text)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        if not text:
            excluded["empty"] = excluded.get("empty", 0) + 1
            continue
        copy = dict(row)
        copy["text"] = text
        kept.append(copy)
    authors = {str(row.get("author")) for row in kept if row.get("author")}
    return kept, {
        "source_rows": len(kept) + sum(excluded.values()),
        "kept_rows": len(kept),
        "excluded": excluded,
        "unique_authors": len(authors),
        "remaining_signature_rows": sum(
            1 for row in kept if signature_reason(str(row.get("text", "")))
        ),
    }


def load_spine(path: Path, beats: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
    """Load and fail-closed verify the deterministic spine against its beats.

    The spine is fixed text, so it is held to the same surface contract the
    model output is: every line must survive parse_slot_output for its own beat.
    A spine that could not be spoken by the model is not a fair substitute.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid spine JSON: {path}") from exc
    rows = payload.get("turns") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != len(beats):
        raise SystemExit(f"spine must contain exactly {len(beats)} turns")
    spine: dict[int, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("spine turn is not an object")
        index = row.get("turn_index")
        if not isinstance(index, int) or not 1 <= index <= len(beats) or index in spine:
            raise SystemExit("spine turn_index must be unique and within the storyline")
        values: dict[str, str] = {}
        for field in SPINE_FIELDS:
            text = row.get(field)
            if not isinstance(text, str) or not text.strip():
                raise SystemExit(f"spine turn {index} is missing {field}")
            if not parse_slot_output(text, beats[index - 1]):
                raise SystemExit(f"spine turn {index} {field} fails the slot contract")
            values[field] = text
        spine[index] = values
    return spine


def load_storyline(path: Path) -> dict[str, Any]:
    try:
        story = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid storyline JSON: {path}") from exc
    scenes = story.get("scenes") if isinstance(story, dict) else None
    if not isinstance(scenes, list) or len(scenes) != 8:
        raise SystemExit("storyline must contain exactly 8 scenes")
    previous_end = -1
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise SystemExit(f"scene {index} is not an object")
        start, end = scene.get("start_ms"), scene.get("end_ms")
        if not isinstance(start, int) or not isinstance(end, int) or start < previous_end or end <= start:
            raise SystemExit(f"scene {index} has invalid or non-ordered time bounds")
        for key in (
            "id", "label", "plot", "facts", "unresolved", "airi_objective", "transition",
            "turn_beats",
        ):
            if not scene.get(key):
                raise SystemExit(f"scene {index} is missing {key}")
        if not isinstance(scene["turn_beats"], list) or len(scene["turn_beats"]) != 4:
            raise SystemExit(f"scene {index} must contain exactly four turn beats")
        for beat_index, beat in enumerate(scene["turn_beats"], 1):
            if not isinstance(beat, dict):
                raise SystemExit(f"scene {index} turn beat {beat_index} is not an object")
            for key in ("new_event", "callback", "emotion", "next_hook"):
                if not beat.get(key):
                    raise SystemExit(f"scene {index} turn beat {beat_index} is missing {key}")
        previous_end = end
    return story


def content_score(text: str) -> tuple[int, int]:
    value = normalized_text(text)
    return len(re.findall(r"[가-힣]", value)), len(value)


def signal_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for raw in re.findall(r"[가-힣]{2,}", normalized_text(text)):
        word = raw
        for suffix in SIGNAL_SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                word = word[:-len(suffix)]
                break
        if len(word) >= 2 and word not in SIGNAL_STOPWORDS:
            terms.add(word)
    return terms


def cue_term_matches(response: str, cue: str) -> list[str]:
    response_terms = signal_terms(response)
    cue_terms = signal_terms(cue)
    return sorted(
        term for term in cue_terms
        if any(term in candidate or candidate in term for candidate in response_terms)
    )


def character_similarity(left: str, right: str) -> float:
    def grams(value: str) -> set[str]:
        compact = re.sub(r"\s+", "", normalized_text(value))
        return {compact[index:index + 3] for index in range(max(0, len(compact) - 2))}

    left_grams, right_grams = grams(left), grams(right)
    union = left_grams | right_grams
    return len(left_grams & right_grams) / len(union) if union else 0.0


def evaluate_quality(story: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any]:
    scene_metrics: dict[str, dict[str, Any]] = {}
    prior_responses: list[str] = []
    repeated_turns: list[int] = []
    high_overlap_turns: list[int] = []
    measured_turns: list[dict[str, Any]] = []
    for scene in story["scenes"]:
        scene_metrics[scene["id"]] = {
            "turns": 0,
            "new_event_hits": 0,
            "callback_hits": 0,
            "next_hook_hits": 0,
            "emotion_hits": 0,
            "emotion_terms": [],
        }
    for turn in turns:
        scene_id = turn["scene_id"]
        scene = next(scene for scene in story["scenes"] if scene["id"] == scene_id)
        turn_number = sum(1 for item in turns[:turn["turn_index"]] if item["scene_id"] == scene_id)
        beat = scene["turn_beats"][turn_number - 1]
        response = normalized_text(turn.get("airi"))
        metrics = scene_metrics[scene_id]
        metrics["turns"] += 1
        new_matches = cue_term_matches(response, beat["new_event"])
        callback_matches = cue_term_matches(response, beat["callback"])
        hook_matches = cue_term_matches(response, beat["next_hook"])
        emotion_matches = cue_term_matches(response, beat["emotion"])
        duplicate = response in prior_responses if response else False
        max_similarity = max(
            (character_similarity(response, prior) for prior in prior_responses),
            default=0.0,
        )
        high_overlap = max_similarity >= 0.55
        if duplicate:
            repeated_turns.append(turn["turn_index"])
        if high_overlap:
            high_overlap_turns.append(turn["turn_index"])
        if new_matches:
            metrics["new_event_hits"] += 1
        if callback_matches:
            metrics["callback_hits"] += 1
        if hook_matches:
            metrics["next_hook_hits"] += 1
        if emotion_matches:
            metrics["emotion_hits"] += 1
            metrics["emotion_terms"].extend(emotion_matches)
        measured_turns.append({
            "turn_index": turn["turn_index"],
            "scene_id": scene_id,
            "new_event_matches": new_matches,
            "callback_matches": callback_matches,
            "next_hook_matches": hook_matches,
            "emotion_matches": emotion_matches,
            "repeated": duplicate,
            "max_prior_similarity": round(max_similarity, 3),
            "source_experience_claim": bool(SOURCE_EXPERIENCE_RE.search(response)),
            "irrelevant_knowledge_marker": bool(IRRELEVANT_KNOWLEDGE_RE.search(response)),
        })
        if response:
            prior_responses.append(response)
    for metrics in scene_metrics.values():
        metrics["emotion_terms"] = sorted(set(metrics["emotion_terms"]))
        metrics["new_event_rate"] = round(metrics["new_event_hits"] / metrics["turns"], 3) if metrics["turns"] else 0.0
        metrics["callback_rate"] = round(metrics["callback_hits"] / metrics["turns"], 3) if metrics["turns"] else 0.0
        metrics["next_hook_rate"] = round(metrics["next_hook_hits"] / metrics["turns"], 3) if metrics["turns"] else 0.0
    total = len(turns)
    source_claim_turns = [item["turn_index"] for item in measured_turns if item["source_experience_claim"]]
    irrelevant_turns = [item["turn_index"] for item in measured_turns if item["irrelevant_knowledge_marker"]]
    scene_progression = all(metrics["new_event_hits"] == metrics["turns"] for metrics in scene_metrics.values())
    scene_context = all(
        metrics["callback_hits"] > 0 and metrics["next_hook_hits"] > 0
        for metrics in scene_metrics.values()
    )
    emotion_variation = all(len(metrics["emotion_terms"]) >= 2 for metrics in scene_metrics.values())
    repeat_rate = len(repeated_turns) / total if total else 1.0
    high_overlap_rate = len(high_overlap_turns) / total if total else 1.0
    return {
        "method": "rule_based_transcript_signals_v1",
        "note": "어휘 신호·문자열 유사도 휴리스틱이다. 의미 품질의 최종 증명으로 사용하지 않고 transcript 검토와 함께 읽는다.",
        "turns": measured_turns,
        "scene_metrics": scene_metrics,
        "repeat_rate": round(repeat_rate, 3),
        "exact_repeated_turns": repeated_turns,
        "high_overlap_rate": round(high_overlap_rate, 3),
        "high_overlap_turns": high_overlap_turns,
        "source_experience_claim_turns": source_claim_turns,
        "irrelevant_knowledge_marker_turns": irrelevant_turns,
        "quality_gate": {
            "scene_order": True,
            "all_turns_new_event_signal": scene_progression,
            "all_scenes_callback_and_next_hook": scene_context,
            "repeat_rate_at_or_below_0": repeat_rate == 0.0,
            "high_overlap_rate_at_or_below_0_10": high_overlap_rate <= 0.10,
            "all_scenes_emotion_variation": emotion_variation,
            "source_experience_claims_zero": not source_claim_turns,
            "irrelevant_knowledge_markers_zero": not irrelevant_turns,
            "quality_pass": all((
                scene_progression,
                scene_context,
                repeat_rate == 0.0,
                high_overlap_rate <= 0.10,
                emotion_variation,
                not source_claim_turns,
                not irrelevant_turns,
            )),
        },
    }


def select_scene_chat(
    rows: list[dict[str, Any]], scene: dict[str, Any], origin_ms: int, limit: int,
) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        try:
            offset_ms = int(row["offset_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        relative_ms = offset_ms - origin_ms
        text = normalized_text(row.get("text"))
        if not (scene["start_ms"] <= relative_ms < scene["end_ms"]):
            continue
        if len(text) < 3 or signature_reason(text):
            continue
        candidates.append({**row, "text": text, "relative_ms": relative_ms})
    if not candidates or limit <= 0:
        return []
    candidates.sort(key=lambda row: int(row["offset_ms"]))
    selected: list[dict[str, Any]] = []
    authors: set[str] = set()
    span = scene["end_ms"] - scene["start_ms"]
    for bucket in range(limit):
        bucket_start = scene["start_ms"] + (span * bucket // limit)
        bucket_end = scene["start_ms"] + (span * (bucket + 1) // limit)
        bucket_rows = [
            row for row in candidates
            if bucket_start <= row["relative_ms"] < bucket_end
            and str(row.get("author", "")) not in authors
        ]
        if not bucket_rows:
            continue
        target = (bucket_start + bucket_end) // 2
        choice = min(
            bucket_rows,
            key=lambda row: (
                abs(int(row["relative_ms"]) - target),
                -content_score(row["text"])[0],
            ),
        )
        selected.append(choice)
        authors.add(str(choice.get("author", "")))
    if len(selected) < limit:
        for row in sorted(
            candidates,
            key=lambda item: (-content_score(item["text"])[0], int(item["offset_ms"])),
        ):
            if row in selected:
                continue
            author = str(row.get("author", ""))
            if author in authors:
                continue
            selected.append(row)
            authors.add(author)
            if len(selected) == limit:
                break
    return sorted(selected[:limit], key=lambda row: int(row["offset_ms"]))


def build_turn_system(
    story: dict[str, Any], scene: dict[str, Any], previous_scene: dict[str, Any] | None,
    scene_turn_index: int, scene_turn_total: int, beat: dict[str, Any],
) -> str:
    # The proxy already supplies the immutable AIRI prompt. Keep this caller
    # card focused on the VOD storyline state instead of duplicating that
    # prompt inside an active-character-card message.
    base = ""
    prior = previous_scene["label"] if previous_scene else "방송 시작"
    prior_transition = previous_scene["transition"] if previous_scene else "없음 — 첫 장면을 시작한다."
    facts = " · ".join(scene["facts"])
    scene_index = story["scenes"].index(scene)
    completed_arc = " → ".join(
        item["label"] for item in story["scenes"][:scene_index]
    ) or "아직 없음"
    turn_goals = {
        1: "장면의 핵심 사실을 소개하고 시청자 채팅과 연결해라.",
        2: "장면의 미해결 질문을 다시 붙잡고 화자의 감정을 한 단계 깊게 해라.",
        3: "새로운 구체적 단서를 하나 추가해 긴장을 높여라.",
        4: "현재 장면을 정리하면서 다음 전환의 단서를 분명히 남겨라.",
    }
    return (
        f"{base}\n\n[오늘 방송]\n"
        f"- 주제: {story['title']}\n"
        f"- 지금 구간: {scene['label']}\n"
        f"- 상황: {scene['plot']}\n"
        f"- AIRI 진행 목표: {scene['airi_objective']}\n"
        f"- 현재 장면 사실: {facts}\n"
        f"- 아직 풀지 않은 질문: {scene['unresolved']}\n"
        f"- 다음 전환: {scene['transition']}\n"
        f"- 직전 구간: {prior}\n"
        f"- 직전 구간에서 넘어온 사건: {prior_transition}\n"
        f"- 지금까지의 막 순서: {completed_arc}\n"
        f"- 장면 내 진행: {scene_turn_index}/{scene_turn_total}\n"
        f"- 이번 턴의 연출 목표: {turn_goals.get(scene_turn_index, turn_goals[4])}\n"
        "[줄거리 방송 연출 지시]\n"
        "- 이번 테스트는 단순 채팅 답변이 아니라 8막 이야기 방송이다. AIRI가 진행자다.\n"
        "- 시청자 채팅을 한 구절 받아친 뒤, 반드시 현재 장면의 구체적 사실이나 감정을 1개 이상 이야기해라.\n"
        "- 한 단어 되묻기, 채팅 문장 반복, 채팅만 평가하고 끝내기를 금지한다. 정확히 3개의 완결된 문장으로 말해라.\n"
        "- 첫 문장은 채팅 반응, 둘째 문장은 현재 장면의 사실·감정, 셋째 문장은 이번 턴 목표나 다음 단서로 구성해라.\n"
        "- 이번 턴의 새 사건을 실제로 말하고, 반드시 회수할 단서를 현재 사건과 연결해라.\n"
        "- 현재 장면의 미해결 질문을 기억하고, 장면 마지막에는 다음 고리의 단서를 남겨라.\n"
        "- VOD는 각색 자료다. 원방송인의 실제 발화·경험을 AIRI 자신의 기억이라고 주장하지 마라. 필요하면 '이야기 속 화자'라고 말해라.\n"
        "- 지식 검색이나 기억에서 나온 무관한 최신 뉴스·사실은 현재 장면과 직접 관련이 없으면 절대 끼워 넣지 마라.\n"
        "- 건강·약·술이 나와도 이 테스트는 실제 상담이 아닌 허구 방송 연출이다. 처방이나 행동 지시로 전환하지 말고, 이야기 속 사건과 인물의 감정만 말해라.\n"
        "- AIRI가 지금 방송을 진행하며 시청자 채팅을 짧게 받아 이야기의 다음 문장으로 연결하라.\n"
        "- 허구 속 인물의 몸 상태를 AIRI 자신의 상태나 경험으로 바꾸지 말고, 시청자에게 진료를 권하는 질문으로 끝내지 마라.\n"
        "- 주제에서 벗어난 채팅에는 짧게 반응한 뒤 현재 장면으로 돌아와라.\n"
        "[이번 턴 최우선 줄거리 상태]\n"
        f"- 새로 공개할 사건: {beat['new_event']}\n"
        f"- 반드시 회수할 단서: {beat['callback']}\n"
        f"- 감정 변화: {beat['emotion']}\n"
        f"- 끝에 걸어둘 다음 고리: {beat['next_hook']}\n"
        "- AIRI는 VOD 원방송인이 아니라 이 각색 방송의 진행자다. 위 상태를 AIRI 자신의 과거 경험으로 말하지 마라. 이야기 속 원래 경험은 반드시 '화자'의 일로 말하고, 그 사건에 대해 AIRI를 가리키는 '나·내·내가'는 쓰지 마라."
    )


def user_content(text: str) -> str:
    return f"{ab.USER_PREFIX}{text}"


def build_director_cue(
    scene: dict[str, Any], scene_turn_index: int, scene_turn_total: int,
    beat: dict[str, Any],
) -> str:
    return (
        "[대사 직전 감독 큐]\n"
        f"장면 {scene_turn_index}/{scene_turn_total}. 이번 턴에 새로 공개할 사건: {beat['new_event']}\n"
        f"반드시 회수할 단서: {beat['callback']}\n"
        f"이번 답변의 끝에서 이어갈 방향: {beat['next_hook']}\n"
        "출력은 정확히 3개의 완결된 한국어 반말 문장이어야 한다. 첫 문장은 시청자 채팅에 직접 반응하고, "
        "둘째 문장은 새 사건·회수할 단서·감정 변화를 함께 말하며, 셋째 문장은 다음 고리로 이어라. "
        "채팅을 그대로 반복하거나 한 단어로 되묻지 말고, 대괄호·내부 카드 문구·메타 설명·무관한 지식·뉴스·기억을 출력하지 마라."
    )


def build_rewrite_cue(beat: dict[str, Any], draft: str) -> str:
    return (
        "[방송 대사 검수 지시]\n"
        "아래 초안은 최종 대사가 아니라 수정 대상이다. 초안의 형식과 표현을 그대로 복사하지 말고, "
        "현재 줄거리 장부에 맞는 새 대사를 작성해라. 시청자 채팅에는 바로 반응하고, 새 사건·회수할 단서·감정 변화를 포함하며, "
        "끝에는 다음 고리를 남겨라. 이야기 속 원래 경험은 '화자'의 일로만 말하고 AIRI 자신의 경험으로 주장하지 마라. "
        "정확히 3개의 완결된 한국어 반말 문장만 출력하고, 대괄호·내부 카드 문구·초안 언급·메타 설명·무관한 지식은 출력하지 마라.\n"
        f"- 새 사건: {beat['new_event']}\n"
        f"- 회수할 단서: {beat['callback']}\n"
        f"- 감정 변화: {beat['emotion']}\n"
        f"- 다음 고리: {beat['next_hook']}\n"
        "[초안 시작]\n"
        f"{draft}\n"
        "[초안 끝]"
    )


def parse_structured_rewrite(raw: str) -> tuple[str, dict[str, str] | None]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return "", None
    if not isinstance(value, dict):
        return "", None
    fields = ("viewer_reaction", "event_callback_emotion", "next_hook")
    if any(not isinstance(value.get(field), str) or not value[field].strip() for field in fields):
        return "", None
    output = {field: normalized_text(value[field]) for field in fields}
    if any("[" in output[field] or "]" in output[field] for field in fields):
        return "", None
    return " ".join(output[field] for field in fields), output


def build_structured_rewrite_cue(beat: dict[str, Any], draft: str) -> str:
    return (
        "[방송 대사 구조화 검수]\n"
        "초안은 참고만 하고 그대로 복사하지 마라. 아래 세 property에 각각 한 문장씩만 작성해라. "
        "시청자 채팅에 직접 반응하고, 새 사건·앞선 단서·감정 변화를 구체적으로 이어가며, 다음 고리를 남겨라. "
        "이야기 속 원래 경험은 '화자'의 일로만 말하고 AIRI 자신의 경험으로 주장하지 마라. "
        "대괄호·내부 카드 문구·초안 언급·메타 설명·무관한 지식은 property 값에 넣지 마라.\n"
        f"viewer_reaction: {beat['callback']}에 반응\n"
        f"event_callback_emotion: 새 사건 {beat['new_event']} / 회수 {beat['callback']} / 감정 {beat['emotion']}\n"
        f"next_hook: {beat['next_hook']}\n"
        "[초안 시작]\n"
        f"{draft}\n"
        "[초안 끝]"
    )


def build_slotwise_cue(field: str, beat: dict[str, Any], viewer_text: str = "",
                       following: tuple[str, ...] = ()) -> str:
    instructions = {
        "viewer_reaction": (
            "시청자 채팅의 구체적인 핵심을 바로 받아치는 한 문장"
        ),
        "event_callback_emotion": (
            "이번 턴의 새 사건과 앞선 단서를 감정 변화와 함께 연결하는 한 문장; 새 사건과 감정의 핵심 표현을 반드시 넣어라"
        ),
        "next_hook": (
            "다음 사건이나 미해결 질문으로 자연스럽게 넘어가는 한 문장"
        ),
    }
    if field not in instructions:
        raise ValueError(f"unknown slot: {field}")
    emotion_instruction = ""
    event_instruction = ""
    if field == "event_callback_emotion":
        emotion_terms = ", ".join(sorted(signal_terms(beat["emotion"])))
        emotion_instruction = (
            f"감정 핵심어 중 하나를 문장에 글자 그대로 포함해라: {emotion_terms}\n"
        )
        event_instruction = "시청자 채팅이 다른 세부를 말해도 이 슬롯에서는 현재 새 사건을 반드시 전개해라.\n"
    viewer_reference = (
        f"참고할 시청자 반응: {normalized_text(viewer_text)}\n"
        if viewer_text else ""
    )
    demo_line = (
        f"출력 예시(소재는 무시하고 형식·말투만 따라라): {SLOT_FORMAT_DEMOS[field]}\n"
        if field in SLOT_FORMAT_DEMOS else ""
    )
    # Three cue interventions were tried against the M8-9 residual and all three
    # were discarded by measurement. Showing the spine text produced verbatim
    # copying on 9 of 32 turns (runs up to 50 characters); adding the recitation
    # guard closed the copying but the same content returned as paraphrase on
    # roughly as many turns; narrowing the slot's job by instruction alone left
    # borrowed experience unchanged and raised contradictions from 2 turns to 4.
    # That is the third reproduction of the standing pattern, after the M8-3 demo
    # leakage and the M8-4 depth injection: material or instruction added to this
    # cue makes a 2.3B model worse. The cue is therefore left exactly as the
    # slotwise carrier had it, and `following` survives only to feed the spine
    # recitation guard in parse_slot_output.
    following_line = ""
    return (
        "[방송 대사 슬롯 생성]\n"
        "이 호출은 최종 대사 전체가 아니라 아래 한 슬롯만 생성한다. "
        "설명, 제목, JSON, 대괄호, 슬롯 이름, 메타 발언 없이 자연스러운 한국어 반말 한 문장만 출력해라. "
        # M8-2 framing (arXiv 2608.07852): a story character lacks the assistant
        # core that role-play framing retains — say what the speaker IS, not what
        # it should pretend to be.
        "너는 어시스턴트가 아니라 이 이야기를 공연하는 방송 진행자 캐릭터다. "
        "이것은 허구 이야기의 방송 대사다. 이야기 속 주인공은 '그 사람' 또는 '주인공'으로 말하고 AIRI 자신의 경험으로 주장하지 마라. "
        "몸의 이상은 이야기 속 사건으로만 이어가며 의료·안전 조언이나 방송 제작 설명으로 바꾸지 마라.\n"
        f"생성할 슬롯: {field} — {instructions[field]}\n"
        f"새 사건: {beat['new_event']}\n"
        f"회수할 단서: {beat['callback']}\n"
        f"감정 변화: {beat['emotion']}\n"
        + (
            "새 사건·회수할 단서·감정의 핵심 표현을 이 문장에 반드시 직접 넣어라.\n"
            if field == "event_callback_emotion" else ""
        )
        + event_instruction
        + emotion_instruction
        + viewer_reference
        + demo_line
        + following_line
        + f"다음 고리: {beat['next_hook']}"
        + (
            f"\n마지막 확인: 이 한 문장에는 새 사건과 회수할 단서를 연결하고, 감정 핵심어 "
            f"({emotion_terms}) 중 하나를 글자 그대로 포함해라."
            if field == "event_callback_emotion" else ""
        )
        + SLOT_DEPTH_REMINDER
    )


def build_slotwise_retry_cue(field: str, beat: dict[str, Any], viewer_text: str = "",
                             following: tuple[str, ...] = ()) -> str:
    # Any depth reminder must stay last, so lift it off before the retry notes
    # and re-append it. Guard on a non-empty reminder: slicing by -0 would
    # otherwise wipe the whole cue.
    base = build_slotwise_cue(field, beat, viewer_text, following)
    if SLOT_DEPTH_REMINDER and base.endswith(SLOT_DEPTH_REMINDER):
        base = base[: -len(SLOT_DEPTH_REMINDER)]
    return (
        base
        + "\n직전 출력은 검증에 실패했다. 이번에는 줄바꿈과 대괄호 없이 한 문장만 쓰고, "
        "'내가 겪었다'처럼 AIRI 자신의 경험을 말하거나 내부 카드·슬롯 이름을 출력하지 마라. "
        "위에 적힌 새 사건·회수할 단서·감정 변화·다음 고리 문구를 그대로 옮겨 말하지 말고 "
        "네 방송 대사로 바꿔 말해라. "
        "시청자에게 조언하거나 지시하지 말고, 시청자에게 이야기를 대신 들려 달라고 요구하지 말며, "
        "장면을 촬영이나 효과로 설명하지 말고 이야기 안에서 네가 직접 진행해라."
        + SLOT_DEPTH_REMINDER
    )


def build_story_cue(beat: dict[str, Any], viewer_text: str = "") -> str:
    viewer_reference = (
        f"참고할 시청자 반응: {normalized_text(viewer_text)}\n"
        if viewer_text else ""
    )
    return (
        "[방송 대사 생성]\n"
        "이것은 허구 이야기의 방송 대사다. 이야기 속 주인공은 '그 사람' 또는 '주인공'으로 말하고 "
        "AIRI 자신의 경험으로 주장하지 마라. 몸의 이상은 이야기 속 사건으로만 이어가며 "
        "의료·안전 조언이나 방송 제작 설명으로 바꾸지 마라.\n"
        f"새 사건: {beat['new_event']}\n"
        f"회수할 단서: {beat['callback']}\n"
        f"감정 변화: {beat['emotion']}\n"
        f"다음 고리: {beat['next_hook']}\n"
        + viewer_reference
        + "먼저 어떻게 이어갈지 한두 문장으로 자유롭게 생각을 써라. "
        f"그 다음 마지막 줄에 '{STORY_DELIMITER}'를 쓰고, 그 뒤에 최종 방송 대사만 정확히 세 문장으로 써라. "
        "첫 문장은 시청자 채팅의 구체적인 핵심을 받아치고, 둘째 문장은 새 사건과 앞선 단서를 감정 변화와 함께 "
        "연결하고, 셋째 문장은 다음 고리로 넘어가라. "
        f"반말로 쓰고, 대괄호·라벨·슬롯 이름·메타 발언은 '{STORY_DELIMITER}' 뒤에 넣지 마라.\n"
        "출력 형식 예시(소재는 무시하고 형식만 따라라):\n"
        f"{STORY_FORMAT_DEMO}"
    )


def build_story_retry_cue(beat: dict[str, Any], viewer_text: str = "") -> str:
    base = build_story_cue(beat, viewer_text)
    return (
        base
        + f"\n직전 출력은 검증에 실패했다. 생각은 '{STORY_DELIMITER}' 앞에만 쓰고, "
        f"'{STORY_DELIMITER}' 뒤에는 세 문장 대사만 써라. "
        "위 문구를 그대로 옮겨 말하지 말고, 시청자에게 조언하거나 지시하지 말며, "
        "AIRI 자신의 경험으로 주장하지 마라."
    )


def longest_common_run(left: str, right: str) -> int:
    """Longest contiguous character run shared by both strings, ignoring spaces."""
    first = re.sub(r"\s+", "", left)
    second = re.sub(r"\s+", "", right)
    if not first or not second:
        return 0
    best = 0
    previous = [0] * (len(second) + 1)
    for index, character in enumerate(first, 1):
        current = [0] * (len(second) + 1)
        for other_index, other in enumerate(second, 1):
            if character == other:
                current[other_index] = previous[other_index - 1] + 1
                if current[other_index] > best:
                    best = current[other_index]
        previous = current
    return best


def recites_beat(body: str, beat: dict[str, Any] | None) -> bool:
    if not beat:
        return False
    return any(
        longest_common_run(body, str(beat.get(field) or "")) >= BEAT_RECITATION_MIN_CHARS
        for field in BEAT_RECITATION_FIELDS
    )


def parse_slot_output(raw: str, beat: dict[str, Any] | None = None,
                      spine_lines: tuple[str, ...] = ()) -> str:
    body, _ = ab.split_operational_protocol(raw)
    body = normalized_text(body)
    if (
        not body
        or "[" in body
        or "]" in body
        or ab.CONTROL_LEAK.search(body)
        or SOURCE_EXPERIENCE_RE.search(body)
        or OUT_OF_STORY_VOICE_RE.search(body)
        or recites_beat(body, beat)
        # Showing the generated slot the spine text made a 2.3B model copy it:
        # 4 verbatim and 4 near-verbatim of 32 turns, up to a 50-character run.
        # The spine is director text now, so it inherits the recitation rule that
        # closed beat recitation, at the same measured 14-character threshold.
        or any(
            longest_common_run(body, line) >= BEAT_RECITATION_MIN_CHARS
            for line in spine_lines
        )
    ):
        return ""
    if STAGING_META_RE.search(body):
        return ""
    if len(re.findall(r"[.!?。！？](?=\s|$)", body)) > 1:
        return ""
    if re.search(r"(?:^|\s)(?:1[.)]|2[.)]|3[.)]|[-*•])\s", body):
        return ""
    return body


def parse_story_output(raw: str, beat: dict[str, Any] | None = None) -> str:
    """Keep only what follows the last delimiter — the reasoning span is free."""
    body, _ = ab.split_operational_protocol(raw)
    if STORY_DELIMITER not in body:
        return ""
    body = normalized_text(body.rsplit(STORY_DELIMITER, 1)[1])
    if (
        not body
        or "[" in body
        or "]" in body
        or ab.CONTROL_LEAK.search(body)
        or SOURCE_EXPERIENCE_RE.search(body)
        or OUT_OF_STORY_VOICE_RE.search(body)
        or STAGING_META_RE.search(body)
        or recites_beat(body, beat)
    ):
        return ""
    if re.search(r"(?:^|\s)(?:1[.)]|2[.)]|3[.)]|[-*•])\s", body):
        return ""
    sentences = len(re.findall(r"[.!?。！？](?=\s|$)", body))
    if sentences < 2 or sentences > 4:
        return ""
    return body


def slot_candidate_score(
    field: str, body: str, beat: dict[str, Any], viewer_text: str,
) -> tuple[int, ...]:
    korean_chars, total_chars = content_score(body)
    if field == "event_callback_emotion":
        new_matches = cue_term_matches(body, beat["new_event"])
        callback_matches = cue_term_matches(body, beat["callback"])
        emotion_matches = cue_term_matches(body, beat["emotion"])
        return (
            int(bool(new_matches and callback_matches and emotion_matches)),
            int(bool(new_matches)),
            int(bool(emotion_matches)),
            int(bool(callback_matches)),
            len(new_matches),
            len({*callback_matches, *emotion_matches}),
            korean_chars,
            min(total_chars, 240),
        )
    if field == "viewer_reaction":
        matched = cue_term_matches(body, viewer_text)
    else:
        matched = cue_term_matches(body, beat["next_hook"])
    return len(matched), korean_chars, min(total_chars, 240)


def write_review_html(report: dict[str, Any], path: Path) -> None:
    rows = []
    for entry in report["turns"]:
        rows.append(
            f"<tr data-turn=\"{entry['turn_index']}\" data-scene=\"{html.escape(entry['scene_id'])}\">"
            f"<td>{entry['turn_index']}</td><td>{html.escape(entry['scene_label'])}</td>"
            f"<td>{entry['relative_minute']:.1f}</td>"
            f"<td>{html.escape(entry['scene_plot'])}<br><i>미해결: {html.escape(entry['scene_unresolved'])}</i></td>"
            f"<td>{html.escape(entry['chat'])}</td>"
            f"<td>{html.escape(entry['airi'])}</td>"
            '<td><input class="rating" type="number" min="0" max="4" placeholder="0–4"></td>'
            '<td><input class="note" type="text" placeholder="직접 관찰 메모"></td>'
            "</tr>"
        )
    page = (
        "<!doctype html><meta charset=\"utf-8\">"
        "<title>AIRI VOD storyline review</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;line-height:1.45}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;vertical-align:top}"
        "th{position:sticky;top:0;background:#eee}td:nth-child(4){width:20%}td:nth-child(5){width:35%}"
        "input{box-sizing:border-box;width:100%}.rating{width:5em}</style>"
        f"<h1>AIRI VOD 줄거리 방송 직접 검토</h1>"
        "<p>사용자 직접 채점용입니다. AI 채점이나 채택 판정이 아닙니다.</p>"
        "<button id=\"download\">사용자 채점 JSON 다운로드</button>"
        f"<p><b>줄거리:</b> {html.escape(report['story_title'])} · "
        f"<b>턴:</b> {report['summary']['turns']} · "
        f"<b>선택 화자:</b> {report['summary']['selected_unique_authors']} · "
        f"<b>비허용 시그니처 입력:</b> {report['summary']['sent_signature_rows']} · "
        f"<b>빈 응답/서비스 오류:</b> {report['summary']['empty_or_service_error']}</p>"
        "<p>context_retention: 0=무관/침묵, 1=채팅 표면만 반응, "
        "2=현재 장면만 반영, 3=현재 장면과 직전 흐름 연결, "
        "4=이전 단서를 회수하면서 다음 장면을 진전.</p>"
        "<table><thead><tr><th>T</th><th>장면</th><th>분</th><th>장면 줄거리/미해결</th><th>시청자 채팅</th>"
        "<th>AIRI 응답</th><th>context_retention</th><th>메모</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "<script>document.querySelector('#download').addEventListener('click', () => {"
        "const ratings = [...document.querySelectorAll('tbody tr')].map(row => {"
        "const value = row.querySelector('.rating').value;"
        "return {turn_index: Number(row.dataset.turn), scene_id: row.dataset.scene, "
        "context_retention: value === '' ? null : Number(value), note: row.querySelector('.note').value};});"
        "const payload = {schema_version: 1, rater: 'user-direct', ai_rating: false, ratings};"
        "const blob = new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'});"
        "const link = document.createElement('a'); link.href = URL.createObjectURL(blob);"
        "link.download = 'vod-storyline-user-rating.json'; link.click(); URL.revokeObjectURL(link.href);});</script>"
    )
    path.write_text(page, encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    story = load_storyline(args.storyline)
    spine: dict[int, dict[str, str]] = {}
    if args.rewrite_format in ("spine", "spine-optional"):
        if args.spine is None:
            raise SystemExit("--rewrite-format spine/spine-optional requires --spine")
        spine = load_spine(args.spine, [
            beat
            for scene in story["scenes"]
            for beat in scene["turn_beats"][:args.per_scene_turns]
        ])
    elif args.spine is not None:
        raise SystemExit("--spine is only valid with --rewrite-format spine or spine-optional")
    source_rows = read_jsonl(args.chat)
    sanitized_rows, sanitation = sanitize_rows(source_rows)
    if args.sanitized_chat is not None:
        args.sanitized_chat.parent.mkdir(parents=True, exist_ok=True)
        args.sanitized_chat.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in sanitized_rows),
            encoding="utf-8",
        )
    origin_ms = int(story["source"]["capture_start_ms"])
    staged_rows: list[dict[str, Any]] = []
    for scene in story["scenes"]:
        audience_messages = scene.get("audience_messages")
        if not isinstance(audience_messages, list) or len(audience_messages) < args.per_scene_turns:
            raise SystemExit(f"scene {scene['id']} has fewer staged audience messages than requested")
        span = scene["end_ms"] - scene["start_ms"]
        for index, message in enumerate(audience_messages[:args.per_scene_turns]):
            if not isinstance(message, dict) or not message.get("text"):
                raise SystemExit(f"scene {scene['id']} has an invalid staged audience message")
            staged_rows.append({
                "offset_ms": origin_ms + scene["start_ms"] + (span * (index + 1) // (args.per_scene_turns + 1)),
                "author": message.get("author", f"audience-{len(staged_rows) + 1:02d}"),
                "text": message["text"],
                "scene_id": scene["id"],
            })
    selected, staged_sanitation = sanitize_rows(staged_rows)
    if len(selected) != len(staged_rows):
        raise SystemExit("staged audience input contains a forbidden broadcast signature")
    keys = [(row.get("offset_ms"), row.get("author"), row.get("text")) for row in selected]
    if len(keys) != len(set(keys)):
        raise RuntimeError("scene selector produced duplicate audience rows")
    selected.sort(key=lambda row: int(row["offset_ms"]))

    transport = ab.HttpTransport(args.base_url, args.token, stream_mode="auto")
    session_id = args.session_id or f"vod-storyline-{int(time.time())}"
    transport.client.headers[legacy_runner.SESSION_HEADER] = session_id
    transport.client.headers["x-airi-turn-origin"] = args.turn_origin
    history: list[tuple[str, str]] = []
    turns: list[dict[str, Any]] = []
    previous_scene: dict[str, Any] | None = None
    scene_seen: dict[str, int] = {}
    rewritten_turns = 0
    try:
        for turn_index, message in enumerate(selected, 1):
            relative_ms = int(message["offset_ms"]) - origin_ms
            scene = next(
                scene for scene in story["scenes"]
                if scene["start_ms"] <= relative_ms < scene["end_ms"]
            )
            scene_seen[scene["id"]] = scene_seen.get(scene["id"], 0) + 1
            system = build_turn_system(
                story, scene, previous_scene, scene_seen[scene["id"]], args.per_scene_turns,
                scene["turn_beats"][scene_seen[scene["id"]] - 1],
            )
            kept = history[-args.history_turns:] if args.history_turns > 0 else []
            messages: list[dict[str, str]] = [{"role": "system", "content": system}]
            for prior_user, prior_airi in kept:
                messages.extend((
                    {"role": "user", "content": prior_user},
                    {"role": "assistant", "content": prior_airi},
                ))
            messages.append({
                "role": "system",
                "content": build_director_cue(
                    scene,
                    scene_seen[scene["id"]],
                    args.per_scene_turns,
                    scene["turn_beats"][scene_seen[scene["id"]] - 1],
                ),
            })
            sent = user_content(message["text"])
            messages.append({"role": "user", "content": sent})
            record = ab.call_once(
                transport, model=args.model, messages=messages,
                max_tokens=args.max_tokens, timeout=args.timeout,
            )
            draft_raw = str(record.get("response") or "")
            draft_body = ab.scoring_body(record, draft_raw, "operational")
            final_record = record
            raw = draft_raw
            body = draft_body
            rewrite_record: dict[str, Any] | None = None
            rewrite_used = False
            rewrite_raw = ""
            rewrite_output: dict[str, Any] | None = None
            if args.rewrite_passes and record.get("ok") and draft_body.strip():
                beat = scene["turn_beats"][scene_seen[scene["id"]] - 1]
                if args.rewrite_format in ("slotwise", "spine", "spine-optional"):
                    slot_calls: list[dict[str, Any]] = []
                    slot_values: dict[str, str] = {}
                    if args.rewrite_format in ("spine", "spine-optional"):
                        slot_values.update(spine[turn_index])
                    generated_fields = (
                        SPINE_GENERATED_FIELDS if args.rewrite_format in ("spine", "spine-optional")
                        else SLOTWISE_FIELDS
                    )
                    following = (
                        tuple(slot_values[name] for name in SPINE_FIELDS)
                        if args.rewrite_format in ("spine", "spine-optional") else ()
                    )
                    for field in generated_fields:
                        valid_slot_indexes: list[int] = []
                        for attempt in range(1, SLOT_CANDIDATE_COUNT + 1):
                            slot_messages = [{"role": "system", "content": (
                                build_slotwise_cue(field, beat, following=following)
                                if attempt == 1
                                else build_slotwise_retry_cue(field, beat, following=following)
                            )}]
                            slot_messages.append({
                                "role": "user",
                                "content": (
                                    user_content(
                                        f"{beat['new_event']} / {beat['callback']} / "
                                        f"{beat['emotion']} 이어서 {message['text']}"
                                    )
                                    if field == "event_callback_emotion" else sent
                                ),
                            })
                            slot_record = ab.call_once(
                                transport, model=args.model, messages=slot_messages,
                                max_tokens=min(args.max_tokens, SLOT_MAX_TOKENS), timeout=args.timeout,
                            )
                            slot_raw = str(slot_record.get("response") or "")
                            slot_body = parse_slot_output(slot_raw, beat, following)
                            slot_record["slot"] = field
                            slot_record["attempt"] = attempt
                            slot_record["response_body"] = slot_body
                            slot_record["parse_ok"] = bool(slot_body)
                            slot_record["candidate_score"] = (
                                slot_candidate_score(field, slot_body, beat, message["text"])
                                if slot_body else None
                            )
                            slot_record["selected"] = False
                            slot_calls.append(slot_record)
                            if slot_record.get("ok") and slot_body:
                                valid_slot_indexes.append(len(slot_calls) - 1)
                        if valid_slot_indexes:
                            selected_index = max(
                                valid_slot_indexes,
                                key=lambda index: (
                                    slot_calls[index]["candidate_score"],
                                    -slot_calls[index]["attempt"],
                                ),
                            )
                            slot_calls[selected_index]["selected"] = True
                            slot_values[field] = slot_calls[selected_index]["response_body"]
                    # spine-optional (M8-10 experiment): every configuration that let the
                    # model speak one free sentence bought item 1 and spent one of items
                    # 4, 5 or 6. A broadcaster does not answer every chat, so when the
                    # reaction slot has no valid candidate the turn is composed from the
                    # two spine sentences instead of failing; reaction_kept records which.
                    optional_reaction = args.rewrite_format == "spine-optional"
                    if optional_reaction:
                        composed_fields = [f for f in SLOTWISE_FIELDS if f in slot_values]
                        rewrite_output = (
                            dict(slot_values)
                            if all(f in slot_values for f in SPINE_FIELDS) else None
                        )
                    else:
                        composed_fields = list(SLOTWISE_FIELDS)
                        rewrite_output = slot_values if len(slot_values) == len(SLOTWISE_FIELDS) else None
                    rewrite_body = (
                        " ".join(slot_values[field] for field in composed_fields)
                        if rewrite_output is not None else ""
                    )
                    rewrite_raw = json.dumps(
                        {"slots": slot_calls, "composed": rewrite_body},
                        ensure_ascii=False,
                    )
                    rewrite_record = {
                        "ok": rewrite_output is not None,
                        "response": rewrite_raw,
                        "response_body": rewrite_body,
                        "slot_calls": slot_calls,
                        "ttft_ms": next(
                            (call.get("ttft_ms") for call in slot_calls if call.get("ttft_ms") is not None),
                            None,
                        ),
                        "complete_ms": round(
                            sum(float(call.get("complete_ms") or 0) for call in slot_calls), 1,
                        ),
                        "failure": None if rewrite_output is not None else "slot_validation_failed",
                        "reaction_kept": (
                            ("viewer_reaction" in slot_values) if optional_reaction else None
                        ),
                    }
                elif args.rewrite_format == "story":
                    story_calls: list[dict[str, Any]] = []
                    rewrite_body = ""
                    for attempt in range(1, 3):
                        story_messages = [
                            {"role": "system", "content": (
                                build_story_cue(beat, message["text"])
                                if attempt == 1
                                else build_story_retry_cue(beat, message["text"])
                            )},
                            {"role": "user", "content": message["text"]},
                        ]
                        story_record = ab.call_once(
                            transport, model=args.model, messages=story_messages,
                            max_tokens=STORY_MAX_TOKENS, timeout=args.timeout,
                        )
                        story_body = parse_story_output(
                            str(story_record.get("response") or ""), beat,
                        )
                        story_record["attempt"] = attempt
                        story_record["response_body"] = story_body
                        story_record["parse_ok"] = bool(story_body)
                        story_calls.append(story_record)
                        if story_record.get("ok") and story_body:
                            rewrite_body = story_body
                            break
                    rewrite_output = (
                        {"final": rewrite_body, "attempts": len(story_calls)}
                        if rewrite_body else None
                    )
                    rewrite_raw = json.dumps({"story": story_calls}, ensure_ascii=False)
                    rewrite_record = {
                        "ok": rewrite_output is not None,
                        "response": rewrite_raw,
                        "response_body": rewrite_body,
                        "story_calls": story_calls,
                        "ttft_ms": next(
                            (call.get("ttft_ms") for call in story_calls if call.get("ttft_ms") is not None),
                            None,
                        ),
                        "complete_ms": round(
                            sum(float(call.get("complete_ms") or 0) for call in story_calls), 1,
                        ),
                        "failure": None if rewrite_output is not None else "story_validation_failed",
                    }
                else:
                    rewrite_messages = [
                        {"role": "system", "content": system},
                        {"role": "system", "content": (
                            build_structured_rewrite_cue(beat, draft_body)
                            if args.rewrite_format == "structured" else build_rewrite_cue(beat, draft_body)
                        )},
                        {"role": "user", "content": sent},
                    ]
                    rewrite_record = ab.call_once(
                        transport, model=args.model, messages=rewrite_messages,
                        max_tokens=args.max_tokens, timeout=args.timeout,
                        response_format=(
                            STRUCTURED_REWRITE_FORMAT
                            if args.rewrite_format == "structured" else None
                        ),
                    )
                    rewrite_raw = str(rewrite_record.get("response") or "")
                    if args.rewrite_format == "structured":
                        rewrite_body, rewrite_output = parse_structured_rewrite(rewrite_raw)
                        rewrite_record["response_body"] = rewrite_body
                        rewrite_record["structured_output"] = rewrite_output
                    else:
                        rewrite_body = ab.scoring_body(rewrite_record, rewrite_raw, "operational")
                if rewrite_record.get("ok") and rewrite_body.strip():
                    final_record = rewrite_record
                    raw = rewrite_raw
                    body = rewrite_body
                    rewrite_used = True
                    rewritten_turns += 1
            turns.append({
                "turn_index": turn_index,
                "scene_id": scene["id"],
                "scene_label": scene["label"],
                "scene_plot": scene["plot"],
                "scene_unresolved": scene["unresolved"],
                "scene_transition": scene["transition"],
                "turn_beat": scene["turn_beats"][scene_seen[scene["id"]] - 1],
                "relative_minute": round(relative_ms / 60000, 3),
                "chat_offset_ms": int(message["offset_ms"]),
                "chat_author": message.get("author"),
                "chat": message["text"],
                "airi": body,
                "raw": raw,
                "draft_airi": draft_body,
                "draft_raw": draft_raw,
                "rewrite_raw": rewrite_raw,
                "rewrite_output": rewrite_output,
                "rewrite": {
                    "requested": args.rewrite_passes,
                    "format": args.rewrite_format,
                    "used": rewrite_used,
                    "ok": None if rewrite_record is None else bool(rewrite_record.get("ok")),
                    "parse_ok": rewrite_output is not None if args.rewrite_format in ("structured", "slotwise", "story") else None,
                    "failure": None if rewrite_record is None else rewrite_record.get("failure"),
                    # spine-optional only; None for every other format. The first
                    # spine-optional run measured survival indirectly because this
                    # projection dropped the field — it now carries it explicitly.
                    "reaction_kept": None if rewrite_record is None else rewrite_record.get("reaction_kept"),
                },
                "ok": bool(final_record.get("ok")),
                "failure": final_record.get("failure"),
                "ttft_ms": final_record.get("ttft_ms"),
                "complete_ms": final_record.get("complete_ms"),
                "message_count": len(messages) if not rewrite_used else 3,
            })
            if record.get("ok") and body.strip():
                history.append((sent, body))
            previous_scene = scene
            status = "ok" if record.get("ok") else str(record.get("failure") or "failed")
            print(f"{turn_index}/{len(selected)} {scene['id']} {status}", file=sys.stderr)
    finally:
        transport.close()

    sent_signature_rows = sum(1 for row in selected if signature_reason(row["text"]))
    scene_ids = [scene["id"] for scene in story["scenes"]]
    scene_turn_counts = {
        scene_id: sum(1 for row in turns if row["scene_id"] == scene_id)
        for scene_id in scene_ids
    }
    scene_indexes = {scene_id: index for index, scene_id in enumerate(scene_ids)}
    summary = {
        "turns": len(turns),
        "scenes": len(scene_ids),
        "scenes_with_turns": sum(1 for count in scene_turn_counts.values() if count),
        "scene_turn_counts": scene_turn_counts,
        "selected_unique_authors": len({str(row.get("author")) for row in selected if row.get("author")}),
        "source_unique_authors": sanitation["unique_authors"],
        "sanitized_source_rows": sanitation["kept_rows"],
        "audience_input_mode": "storyline_staged_from_vod",
        "audience_input_sanitation": staged_sanitation,
        "sent_signature_rows": sent_signature_rows,
        "rewrite_passes": args.rewrite_passes,
        "rewrite_format": args.rewrite_format,
        "rewritten_turns": rewritten_turns,
        "empty_or_service_error": sum(1 for row in turns if not row["ok"] or not row["airi"].strip()),
        "ordered_scene_turns": all(
            scene_indexes[row["scene_id"]] >= scene_indexes[turns[index - 1]["scene_id"]]
            for index, row in enumerate(turns) if index > 0
        ),
    }
    return {
        "schema_version": 1,
        "mode": "vod_storyline",
        "story_id": story["story_id"],
        "story_title": story["title"],
        "storyline_sha256": hashlib.sha256(args.storyline.read_bytes()).hexdigest(),
        "spine_sha256": (
            hashlib.sha256(args.spine.read_bytes()).hexdigest() if args.spine is not None else None
        ),
        "chat_source_sha256": hashlib.sha256(args.chat.read_bytes()).hexdigest(),
        "model": args.model,
        "session_id": session_id,
        "turn_origin": args.turn_origin,
        "rater": "user-direct",
        "ai_rating": False,
        "adoption_decision": None,
        "tuning": {
            "cause": args.tuning_cause,
            "change": args.tuning_change,
            "rewrite_passes": args.rewrite_passes,
            "rewrite_format": args.rewrite_format,
        },
        "sanitation": sanitation,
        "summary": summary,
        "quality_metrics": evaluate_quality(story, turns),
        "tuning_preregistration": story["tuning_preregistration"],
        "turns": turns,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--storyline", type=Path, default=DEFAULT_STORYLINE)
    value.add_argument("--chat", type=Path, default=DEFAULT_CHAT)
    value.add_argument("--sanitized-chat", type=Path, default=None)
    value.add_argument("--base-url", default="http://127.0.0.1:11435/v1")
    value.add_argument("--model", default="midm-airi:2.0-mini")
    value.add_argument("--token", default=None)
    value.add_argument("--session-id", default=None)
    value.add_argument(
        "--turn-origin",
        choices=("local-evaluation", "local-quality-probe"),
        default="local-evaluation",
    )
    value.add_argument("--per-scene-turns", type=int, default=4)
    value.add_argument("--history-turns", type=int, default=8)
    value.add_argument("--max-tokens", type=int, default=220)
    value.add_argument(
        "--rewrite-passes", type=int, choices=(0, 1), default=0,
        help="same-model isolated rewrite pass per successful turn (evaluation only)",
    )
    value.add_argument(
        "--rewrite-format",
        choices=("spoken", "structured", "slotwise", "story", "spine", "spine-optional"),
        default="spoken",
        help="format for the optional rewrite pass; story fences only the final line behind a "
             "delimiter, spine speaks the two plot slots from authored lines, spine-optional "
             "additionally drops the generated reaction when no candidate validates",
    )
    value.add_argument(
        "--spine", type=Path, default=None,
        help="authored deterministic spine sidecar; required by and exclusive to --rewrite-format spine",
    )
    value.add_argument("--timeout", type=float, default=90.0)
    value.add_argument("--tuning-cause", default="unspecified")
    value.add_argument("--tuning-change", default="unspecified")
    value.add_argument("--report", type=Path, required=True)
    value.add_argument("--review-html", type=Path, required=True)
    return value


if __name__ == "__main__":
    arguments = parser().parse_args()
    result = run(arguments)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.review_html.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_review_html(result, arguments.review_html)
    print(json.dumps({
        "mode": result["mode"],
        "summary": result["summary"],
        "report": str(arguments.report),
        "review_html": str(arguments.review_html),
    }, ensure_ascii=False, indent=2))
