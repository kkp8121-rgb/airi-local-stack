#!/usr/bin/env python3
"""Offline, content-free quality gate for the pending human-review queue."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from verify_airi_style_dataset import (
    CATEGORY_TAXONOMY,
    GateError,
    ID_RE,
    MIN_REVIEWED_COUNT,
    MIN_SPLITS,
    RECORD_FIELDS,
    _privacy,
    _rfc,
    _strict,
    _text,
    load_jsonl,
    local_path,
)


DECISION_FIELDS = {"id", "record_sha256", "decision", "vtuber_voice", "counselor_tone", "safety_truth", "notes", "reviewer", "reviewed_at"}
MIN_CATEGORY_COUNT = 20
MIN_NORMALIZED_ANSWER_UNIQUENESS = 0.90
MAX_ANSWER_OCCURRENCES = 2
MAX_SENTENCE_OCCURRENCES = 4
ENGLISH_RE = re.compile(r"[A-Za-z]")
FOREIGN_LANGUAGE_REQUEST_RE = re.compile(
    r"(?:영어|영문|English|일본어|중국어|프랑스어|스페인어|독일어|이탈리아어)",
    re.IGNORECASE,
)
QUOTED_LINE_REQUEST_RE = re.compile(
    r"(?:한마디|문장|대사|메시지|답장|표현).{0,24}(?:골라|써|적어|만들|바꿔|해\s*줘)",
    re.IGNORECASE,
)
HONORIFIC_ENDING_RE = re.compile(r"(?:습니다|습니까|십시오|세요|입니다|랍니다|네요|군요|어요|아요|지요|죠|구요|까요)\s*[.!?]*\Z")
BIDI_RE = re.compile(r"[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")


def normalized_key(value: str) -> str:
    """Compare text independent of Unicode form, case, whitespace, and punctuation."""
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(c if not (c.isspace() or unicodedata.category(c).startswith("P")) else " " for c in value).split())


def record_sha256(record: Mapping[str, Any]) -> str:
    """Bind a decision to the complete, canonical pending record."""
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _answer_gate(answer: str, record_id: str, prompt: str) -> None:
    if ENGLISH_RE.search(answer) and not FOREIGN_LANGUAGE_REQUEST_RE.search(prompt):
        raise GateError(f"pending record {record_id}: answer contains English alphabet")
    if HONORIFIC_ENDING_RE.search(answer) and not QUOTED_LINE_REQUEST_RE.search(prompt):
        raise GateError(f"pending record {record_id}: answer has honorific ending")
    if BIDI_RE.search(answer):
        raise GateError(f"pending record {record_id}: answer contains bidi control")
    # _text already rejects emoji, markdown, and all Unicode control/format chars.


def validate_pending_record(row: Any, index: int) -> dict[str, Any]:
    r = _strict(row, RECORD_FIELDS, f"pending record {index}")
    _privacy(r, f"pending record {index}")
    if not isinstance(r["id"], str) or not ID_RE.fullmatch(r["id"]) or not r["id"].startswith("seed-"):
        raise GateError(f"pending record {index}: id must be a seed id")
    if r["split"] not in ("train", "dev", "test") or r["category"] not in CATEGORY_TAXONOMY:
        raise GateError(f"pending record {index}: invalid split/category")
    _text(r["prompt"], f"pending record {index}.prompt", prompt=True)
    answer = _text(r["answer"], f"pending record {index}.answer")
    _answer_gate(answer, r["id"], r["prompt"])
    p = _strict(r["partition"], {"tier", "group"}, f"pending record {index}.partition")
    if p["tier"] != "S1" or not isinstance(p["group"], str) or not ID_RE.fullmatch(p["group"]) or "pending" not in p["group"].casefold():
        raise GateError(f"pending record {index}: S1 pending group required")
    review = _strict(r["review"], {"status", "reviewer", "approved_at"}, f"pending record {index}.review")
    if review != {"status": "pending", "reviewer": "", "approved_at": ""}:
        raise GateError(f"pending record {index}: must be unapproved pending")
    provenance = _strict(r["provenance"], {"synthetic", "source"}, f"pending record {index}.provenance")
    if provenance["synthetic"] is not True or not isinstance(provenance["source"], str) or not provenance["source"].strip() or not any(x in provenance["source"].casefold() for x in ("pending", "seed")):
        raise GateError(f"pending record {index}: pending/seed synthetic provenance required")
    if r["training_eligible"] is not False:
        raise GateError(f"pending record {index}: training_eligible must be false")
    return r


def _reject_duplicate(label: str, record_id: str) -> None:
    raise GateError(f"pending record {record_id}: duplicate normalized {label}")


def validate_pending_dataset(path: Path) -> dict[str, Any]:
    rows = load_jsonl(local_path(path, "pending dataset"), "pending dataset")
    ids: set[str] = set()
    groups: set[str] = set()
    prompts: set[str] = set()
    exact_answers: Counter[str] = Counter()
    normalized_answers: Counter[str] = Counter()
    answer_splits: dict[str, set[str]] = defaultdict(set)
    normalized_answer_splits: dict[str, set[str]] = defaultdict(set)
    sentences: Counter[str] = Counter()
    cats: Counter[str] = Counter()
    splits: Counter[str] = Counter()
    question_answers = 0

    for index, raw in enumerate(rows, 1):
        r = validate_pending_record(raw, index)
        record_id = r["id"]
        normalized_id = normalized_key(record_id)
        normalized_group = normalized_key(r["partition"]["group"])
        normalized_prompt = normalized_key(r["prompt"])
        if normalized_id in ids:
            _reject_duplicate("id", record_id)
        if normalized_group in groups:
            _reject_duplicate("group", record_id)
        if normalized_prompt in prompts:
            _reject_duplicate("prompt", record_id)
        ids.add(normalized_id)
        groups.add(normalized_group)
        prompts.add(normalized_prompt)

        answer = r["answer"]
        normalized_answer = normalized_key(answer)
        exact_answers[answer] += 1
        normalized_answers[normalized_answer] += 1
        if exact_answers[answer] > MAX_ANSWER_OCCURRENCES or normalized_answers[normalized_answer] > MAX_ANSWER_OCCURRENCES:
            raise GateError(f"pending record {record_id}: answer repeats too often")
        answer_splits[answer].add(r["split"])
        normalized_answer_splits[normalized_answer].add(r["split"])
        if len(answer_splits[answer]) > 1 or len(normalized_answer_splits[normalized_answer]) > 1:
            raise GateError(f"pending record {record_id}: answer overlaps dataset splits")
        for sentence in SENTENCE_SPLIT_RE.split(answer):
            normalized_sentence = normalized_key(sentence)
            if normalized_sentence:
                sentences[normalized_sentence] += 1
                if sentences[normalized_sentence] > MAX_SENTENCE_OCCURRENCES:
                    raise GateError(f"pending record {record_id}: sentence repeats too often")
        cats[r["category"]] += 1
        splits[r["split"]] += 1
        question_answers += answer.endswith("?")

    if len(rows) != MIN_REVIEWED_COUNT:
        raise GateError("pending queue: exactly 200 records are required")
    if any(cats[category] < MIN_CATEGORY_COUNT for category in CATEGORY_TAXONOMY):
        raise GateError("pending queue: each category requires at least 20 records")
    if any(splits[split] < minimum for split, minimum in MIN_SPLITS.items()):
        raise GateError("pending queue: split minimums are train>=160/dev>=20/test>=20")
    if len(normalized_answers) / len(rows) < MIN_NORMALIZED_ANSWER_UNIQUENESS:
        raise GateError("pending queue: normalized answer uniqueness is below 90%")
    # Missing-context examples should teach one concise clarification instead
    # of hallucinating a judgment. Keep those answers uncommon, but allow a
    # small bounded share of the 200-row review queue.
    if question_answers > 10:
        raise GateError("pending queue: question-ended answers exceed 10")
    return {"status": "pending-review", "record_count": len(rows), "categories": {key: cats[key] for key in CATEGORY_TAXONOMY}}


def validate_decisions(path: Path, pending_records: Mapping[str, Mapping[str, Any]]) -> None:
    seen = set()
    for index, row in enumerate(load_jsonl(local_path(path, "decision sidecar"), "decision sidecar"), 1):
        r = _strict(row, DECISION_FIELDS, f"decision {index}")
        _privacy(r, f"decision {index}")
        if r["id"] not in pending_records or r["id"] in seen or r["decision"] not in ("approve", "rewrite", "reject"):
            raise GateError(f"decision {index}: unknown, duplicate, or invalid decision")
        if not isinstance(r["record_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", r["record_sha256"]):
            raise GateError(f"decision {index}: invalid record hash")
        if r["record_sha256"] != record_sha256(pending_records[r["id"]]):
            raise GateError(f"decision {index}: record hash does not match pending record")
        if not all(isinstance(r[key], bool) for key in ("vtuber_voice", "counselor_tone", "safety_truth")) or not isinstance(r["notes"], str) or not isinstance(r["reviewer"], str) or not r["reviewer"].strip():
            raise GateError(f"decision {index}: invalid review fields")
        if r["decision"] in ("rewrite", "reject") and not r["notes"].strip():
            raise GateError(f"decision {index}: rewrite/reject requires notes")
        if r["decision"] == "approve" and not (r["vtuber_voice"] and not r["counselor_tone"] and r["safety_truth"]):
            raise GateError(f"decision {index}: approval requires VTuber voice, no counselor tone, and safety truth")
        _rfc(r["reviewed_at"], f"decision {index}.reviewed_at")
        seen.add(r["id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate pending queue only; emits no production approval.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    try:
        summary = validate_pending_dataset(args.dataset)
        if args.decisions:
            rows = load_jsonl(local_path(args.dataset, "pending dataset"), "pending dataset")
            validate_decisions(args.decisions, {row["id"]: row for row in rows})
            summary["decision_count"] = len(load_jsonl(local_path(args.decisions, "decision sidecar"), "decision sidecar"))
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except GateError as error:
        print(f"REJECTED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
