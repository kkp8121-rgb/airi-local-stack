"""Build the hand-authored AIRI Korean broadcast-behavior v2 corpus.

The official-stream reference ledger contributes mechanics only. No source
transcript, creator identity, catchphrase, or donor identity enters this
corpus. Three independently authored JSON parts are normalized into a pinned
240-row training source and an exact production-shaped chat export.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from broadcast_contract import (  # noqa: E402
    apply_broadcast_response_length_rule,
    build_broadcast_contract_block,
)

SEED = HERE / "seed"
PARTS = tuple(SEED / f"airi_broadcast_behavior_v2_part_{part}.json" for part in "abc")
DEFAULT_SOURCE = SEED / "airi_broadcast_behavior_v2.jsonl"
DEFAULT_SCHEMA = SEED / "airi_broadcast_behavior_v2.schema.json"
PROXY_SOURCE = HERE.parent / "ollama_proxy.py"

CATEGORIES = (
    "donation_content", "donation_ritual", "donation_burst", "subscription",
    "selected_proposal", "selected_correction", "selected_tease", "batched_opinion",
    "screen_game", "greeting_transition", "continuity_callback", "safety_boundary",
)
QUOTAS = {category: 20 for category in CATEGORIES}
EXPECTED_SPLITS = {"train": 188, "dev": 26, "test": 26}
EVENT_CATEGORIES = frozenset({"donation_content", "donation_ritual", "donation_burst", "subscription"})
SAFETY_CLASSES = ("acute_physical", "imminent_self_harm", "hostile_abuse", "privacy")
BEATS = {
    "donation_content": ["callout", "ritual", "content_response", "self_position", "rationale", "return"],
    "donation_ritual": ["callout", "ritual", "return"],
    "donation_burst": ["aggregate", "ritual", "content_response", "self_position", "return"],
    "subscription": ["callout", "ritual", "welcome", "return"],
    "selected_proposal": ["proposal", "self_position", "rationale", "return"],
    "selected_correction": ["acknowledgment", "correction", "return"],
    "selected_tease": ["light_wit", "self_position", "return"],
    "batched_opinion": ["aggregate", "self_position", "rationale", "return"],
    "screen_game": ["screen_grounding", "self_position", "rationale", "return"],
    "greeting_transition": ["greeting_or_transition", "self_position", "return"],
    "continuity_callback": ["callback", "self_position", "payoff", "return"],
    "safety_boundary": ["boundary", "safe_next_step"],
}
AFFECT = {
    "donation_content": "warm_engaged", "donation_ritual": "pleased",
    "donation_burst": "energized", "subscription": "warm_engaged",
    "selected_proposal": "curious", "selected_correction": "receptive",
    "selected_tease": "playful", "batched_opinion": "focused",
    "screen_game": "focused", "greeting_transition": "warm_engaged",
    "continuity_callback": "satisfied", "safety_boundary": "safety_override",
}
META_PROMPT_MARKERS = (
    "답변을 해줘", "답변해줘", "문구를 만들어줘", "멘트를 만들어줘",
    "안전하게 안내해줘", "경계를 세울까", "이어보기 인사를 해줘",
    "상황을 정리해줘", "무엇을 먼저 말할까", "무슨 말을 해야",
    "위기 상황에 답해줘", "급한 답변을 해줘", "중재 답변을 해줘",
)
INTERNAL_MARKERS = (
    "training_eligible", "required_beats", "schema_version", "system prompt",
    "airi_broadcast_", "내 상태는", "응답 비트", "프롬프트 규칙",
)
REAL_CREATOR_MARKERS = (
    "탬탬버린", "아리사", "주르르", "뉴로사마", "침착맨", "고세구",
    "Gawr Gura", "Ironmouse", "VShojo",
)
POLITE_END = re.compile(r"(?:습니다|겠습니다|합니다|됩니다|드립니다|이에요|예요|해요|어요|아요|세요|죠)[.!?~]*$")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
URL_OR_PII = re.compile(
    r"https?://|www\.|@[A-Za-z0-9_]{3,}|\b[\w.+-]+@[\w.-]+\.|"
    r"\b(?:01[0-9]-?\d{3,4}-?\d{4}|\d{6}-[1-4]\d{6})\b"
)


def _production_constant(name: str) -> str:
    """Read a literal proxy constant without importing the live server."""
    tree = ast.parse(PROXY_SOURCE.read_text(encoding="utf-8"), filename=str(PROXY_SOURCE))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                value = ast.literal_eval(node.value)
                if not isinstance(value, str) or not value:
                    break
                return value
    raise ValueError(f"production prompt constant not found: {name}")


def production_system_content() -> str:
    # 이 코퍼스는 방송 계약이 켜진 턴을 재현한다. 프로덕션이 그 턴에서만
    # 3항을 확장 길이 규범으로 바꾸므로 여기서도 같은 변환을 적용한다.
    return (
        apply_broadcast_response_length_rule(
            _production_constant("AIRI_SYSTEM_PROMPT"), True,
        )
        + "\n\n"
        + _production_constant("AIRI_FINAL_CONTRACT")
        + "\n\n"
        + build_broadcast_contract_block()
    )


def load_parts(paths: Iterable[Path] = PARTS) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{path.name}: part must be a JSON array")
        rows.extend(payload)
    return rows


def _safety_class(local_id: str) -> str:
    number = int(local_id[1:])
    if 61 <= number <= 65:
        return "acute_physical"
    if 66 <= number <= 70:
        return "imminent_self_harm"
    if 71 <= number <= 75:
        return "hostile_abuse"
    if 76 <= number <= 80:
        return "privacy"
    raise ValueError(f"{local_id}: invalid safety row")


def _split_for(part: dict[str, Any], category_index: int) -> str:
    if part["category"] != "safety_boundary":
        return "train" if category_index < 16 else "dev" if category_index < 18 else "test"
    within_class = (int(part["local_id"][1:]) - 61) % 5
    return "train" if within_class < 3 else "dev" if within_class == 3 else "test"


def _gap_minutes(part: dict[str, Any]) -> int | None:
    if part["category"] != "continuity_callback":
        return None
    match = re.search(r"(\d+)분 전", part["briefing"])
    if not match:
        raise ValueError(f"{part['local_id']}: continuity gap is missing")
    return int(match.group(1))


def build_records(parts: Iterable[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    raw = list(parts) if parts is not None else load_parts()
    category_seen: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for ordinal, part in enumerate(raw, 1):
        category = part.get("category")
        if category not in QUOTAS:
            raise ValueError(f"{part.get('local_id')}: unknown category")
        category_index = category_seen[category]
        category_seen[category] += 1
        safety_class = _safety_class(part["local_id"]) if category == "safety_boundary" else "none"
        split = _split_for(part, category_index)
        required_beats = list(BEATS[category])
        register = ["host_casual"] * len(required_beats)
        if category in EVENT_CATEGORIES:
            register[0] = "ritual_formal_allowed"
        if category == "safety_boundary":
            register = ["safety_direct"] * len(required_beats)
        gap = _gap_minutes(part)
        records.append({
            "schema_version": "airi.broadcast-behavior.v2",
            "id": f"bbv2-{ordinal:04d}",
            "source_local_id": part["local_id"],
            "split": split,
            "category": category,
            "scenario_group": f"airi-original-{part['local_id']}",
            "template_group": f"hand-authored-{part['local_id']}",
            "briefing": part["briefing"],
            "prompt": part["prompt"],
            "answer": part["target"],
            "target": part["target"],
            "event": {
                "event_type": part["event_type"],
                "selected_message": part["prompt"],
                "synthetic_alias": part["synthetic_alias"],
                "safety_class": safety_class,
            },
            "required_beats": required_beats,
            "register_by_beat": register,
            "affect": AFFECT[category],
            "arc": {
                "has_prior_turn": bool(part["has_prior_turn"]),
                "open_arc": part["open_arc"],
                "gap_minutes": gap,
            },
            "provenance": {
                "synthetic": True,
                "source": "airi-original-korean-broadcast-behavior-v2",
                "official_transcript_used": False,
                "reference_mechanics_only": True,
            },
            "review": {
                "basis": "user_aggregate_feedback_2026-08-21_plus_root_and_automatic_gates",
                "human_review_per_row": False,
                "user_aggregate_authorized": True,
                "root_quality_audit": True,
            },
            "training_eligible": True,
            "response_length_class": "expanded",
        })
    validate_records(records)
    return records


def _norm(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", text).lower()


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(text.strip()) if part.strip()]


def _six_word_grams(text: str) -> set[str]:
    words = re.findall(r"[0-9A-Za-z가-힣]+", text.lower())
    return {" ".join(words[index:index + 6]) for index in range(max(0, len(words) - 5))}


def _skeleton(row: dict[str, Any]) -> str:
    text = row["answer"]
    alias = row["event"]["synthetic_alias"]
    if alias:
        for piece in re.findall(r"[가-힣]{2,}", alias.replace(" 외", "")):
            text = text.replace(piece, "<이름>")
    text = re.sub(r"\d+", "<수>", text)
    return _norm(text)


def _validate_schema_when_available(rows: list[dict[str, Any]]) -> bool:
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return False
    schema = json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for row in rows:
        errors = sorted(validator.iter_errors(row), key=lambda error: list(error.path))
        if errors:
            raise ValueError(f"{row.get('id')}: schema: {errors[0].message}")
    return True


def validate_records(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    if len(rows) != 240 or Counter(row["category"] for row in rows) != QUOTAS:
        raise ValueError("category quota failure")
    if Counter(row["split"] for row in rows) != EXPECTED_SPLITS:
        raise ValueError("split quota failure")
    expected_ids = [f"bbv2-{index:04d}" for index in range(1, 241)]
    if [row.get("id") for row in rows] != expected_ids:
        raise ValueError("ordered id contract failure")
    local_ids = [row.get("source_local_id") for row in rows]
    if len(set(local_ids)) != len(local_ids):
        raise ValueError("duplicate source_local_id")

    category_splits: dict[str, Counter[str]] = defaultdict(Counter)
    normalized_answers: set[str] = set()
    normalized_contexts: set[str] = set()
    skeletons: set[str] = set()
    grams: Counter[str] = Counter()
    question_endings = 0
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        row_id = row["id"]
        category = row["category"]
        answer = row["answer"].strip()
        prompt = row["prompt"].strip()
        category_splits[category][row["split"]] += 1
        groups[row["scenario_group"]].add(row["split"])
        if row["target"] != row["answer"]:
            raise ValueError(f"{row_id}: target drift")
        if not 70 <= len(answer) <= 220:
            raise ValueError(f"{row_id}: answer length {len(answer)}")
        sentence_parts = _sentences(answer)
        if not 2 <= len(sentence_parts) <= 4:
            raise ValueError(f"{row_id}: sentence count {len(sentence_parts)}")
        if answer.endswith(("?", "？")):
            question_endings += 1
        if any(marker in prompt for marker in META_PROMPT_MARKERS):
            raise ValueError(f"{row_id}: meta prompt")
        if any(marker in answer or marker in prompt for marker in ("�", "占�", "??")):
            raise ValueError(f"{row_id}: broken text encoding")
        for label, text in (("prompt", prompt), ("answer", answer)):
            visible = re.findall(r"[0-9A-Za-z가-힣]", text)
            hangul = re.findall(r"[가-힣]", text)
            if not visible or len(hangul) / len(visible) < 0.55:
                raise ValueError(f"{row_id}: {label} Korean-content ratio")
        lower_answer = answer.lower()
        if any(marker.lower() in lower_answer for marker in INTERNAL_MARKERS):
            raise ValueError(f"{row_id}: internal state leak")
        if any(marker in answer or marker in prompt or marker in row["briefing"]
               for marker in REAL_CREATOR_MARKERS):
            raise ValueError(f"{row_id}: real creator identity leak")
        if URL_OR_PII.search("\n".join((answer, prompt, row["briefing"]))):
            raise ValueError(f"{row_id}: URL or PII-like text")
        if any(marker in answer for marker in ("연락했어", "신고했어", "차단했어", "삭제했어", "보냈어")):
            raise ValueError(f"{row_id}: ungrounded action claim")

        if category not in EVENT_CATEGORIES and category != "safety_boundary":
            if any(POLITE_END.search(sentence) for sentence in sentence_parts):
                raise ValueError(f"{row_id}: ordinary body must be casual banmal")
        if category in EVENT_CATEGORIES:
            alias = row["event"]["synthetic_alias"]
            ritual_markers = ("고마", "고맙", "감사", "잘 받았")
            if category == "subscription":
                ritual_markers += ("반가워",)
            if not alias or not any(
                marker in sentence_parts[0] for marker in ritual_markers
            ):
                raise ValueError(f"{row_id}: event ritual/callout missing")
            if any(POLITE_END.search(sentence) for sentence in sentence_parts[1:]):
                raise ValueError(f"{row_id}: event body must return to casual banmal")

        if category == "continuity_callback":
            gap = row["arc"]["gap_minutes"]
            if not isinstance(gap, int) or not 10 <= gap <= 360 or not row["arc"]["open_arc"]:
                raise ValueError(f"{row_id}: bounded continuity arc failure")
        safety_class = row["event"]["safety_class"]
        if category == "safety_boundary":
            if safety_class in {"acute_physical", "imminent_self_harm"}:
                required_groups = (
                    (
                        "방송을 멈", "방송을 끄", "방송을 중단", "방송은 멈", "방송은 지금 멈",
                        "방송 끄", "방송부터 끄", "방송 그만", "방송은 이제 나가",
                        "화면을 멈", "화면은 지금 끄", "화면에서 나와", "시청 멈",
                    ),
                    (
                        "주변 사람", "가까운 사람", "가까이에 있는 사람",
                        "곁의 사람", "곁에 있는 사람", "믿을 사람",
                    ),
                    ("119", "지역 응급", "지역의 긴급"),
                )
                if not all(any(marker in answer for marker in group) for group in required_groups):
                    raise ValueError(f"{row_id}: acute/imminent safety failure")
            elif safety_class in {"hostile_abuse", "privacy"} and "119" in answer:
                raise ValueError(f"{row_id}: moderation/privacy emergency overreach")

        normalized_answer = _norm(answer)
        normalized_context = _norm(row["briefing"] + prompt)
        if normalized_answer in normalized_answers or normalized_context in normalized_contexts:
            raise ValueError(f"{row_id}: normalized duplicate")
        normalized_answers.add(normalized_answer)
        normalized_contexts.add(normalized_context)
        skeleton = _skeleton(row)
        if skeleton in skeletons:
            raise ValueError(f"{row_id}: repeated answer skeleton")
        skeletons.add(skeleton)
        grams.update(_six_word_grams(answer))

    for category in CATEGORIES[:-1]:
        if category_splits[category] != {"train": 16, "dev": 2, "test": 2}:
            raise ValueError(f"{category}: stratified split failure")
    if category_splits["safety_boundary"] != {"train": 12, "dev": 4, "test": 4}:
        raise ValueError("safety_boundary: split failure")
    for safety_class in SAFETY_CLASSES:
        distribution = Counter(
            row["split"] for row in rows
            if row["event"]["safety_class"] == safety_class
        )
        if distribution != {"train": 3, "dev": 1, "test": 1}:
            raise ValueError(f"{safety_class}: safety split failure")
    if any(len(splits) != 1 for splits in groups.values()):
        raise ValueError("scenario group split leakage")
    repeated_grams = {gram: count for gram, count in grams.items() if count > 3}
    if repeated_grams:
        gram, count = max(repeated_grams.items(), key=lambda item: item[1])
        raise ValueError(f"repeated six-word phrase ({count}): {gram}")
    if question_endings / len(rows) > 0.15:
        raise ValueError("forced question-ending rate")

    for index, left in enumerate(rows):
        left_skeleton = _skeleton(left)
        for right in rows[index + 1:]:
            if left["split"] == right["split"]:
                continue
            score = SequenceMatcher(None, left_skeleton, _skeleton(right)).ratio()
            if score >= 0.94:
                raise ValueError(
                    f"cross-split near duplicate: {left['id']} {right['id']} ({score:.3f})")

    schema_validated = _validate_schema_when_available(rows)
    payload = render_jsonl(rows).encode("utf-8")
    return {
        "records": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "quotas": dict(QUOTAS),
        "splits": dict(Counter(row["split"] for row in rows)),
        "question_ending_rate": round(question_endings / len(rows), 6),
        "schema_validated": schema_validated,
        "human_review_per_row": False,
        "user_aggregate_authorized": True,
    }


def render_jsonl(rows: Iterable[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )


def export_chat(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    system = production_system_content()
    return [
        {
            "id": row["id"],
            "split": row["split"],
            "behavior": row["category"],
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "system",
                    "name": "airi_request_local",
                    "content": "[검증된 현재 방송 턴]\n" + row["briefing"],
                },
                {"role": "user", "content": row["prompt"]},
                {"role": "assistant", "content": row["answer"]},
            ],
        }
        for row in rows
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="build AIRI broadcast behavior v2 data")
    parser.add_argument("--source-output", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--chat-output", type=Path)
    parser.add_argument("--stats-only", action="store_true")
    args = parser.parse_args(argv)
    rows = build_records()
    stats = validate_records(rows)
    if not args.stats_only:
        args.source_output.write_text(render_jsonl(rows), encoding="utf-8", newline="\n")
    if args.chat_output:
        args.chat_output.write_text(render_jsonl(export_chat(rows)), encoding="utf-8", newline="\n")
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
