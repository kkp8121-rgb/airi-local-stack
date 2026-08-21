"""Find review windows in a local YouTube JSON3 auto-caption file.

This is a research triage tool, not a transcript importer.  It emits only time
bands, coarse cue categories, and hit counts.  Raw captions, names, amounts,
URLs, and quoted speech never enter the report or any training dataset.  A
human still has to inspect the official VOD image/audio and code abstract beats.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "airi.broadcast-reference-candidates.v1"
CUE_TERMS = {
    "support_event": ("후원", "도네", "구독", "별풍", "고마워", "감사"),
    "audience_address": ("채팅", "챗창", "여러분", "얘들아", "시청자"),
    "continuity": ("아까", "전에", "기억", "다시", "처음에", "앞에서"),
    "correction": ("아니래", "정정", "잘못", "아니었", "맞네", "착각"),
    "playful_friction": ("놀리", "또 들켰", "내 탓", "너희 탓", "억울"),
}


class CandidateExtractionError(ValueError):
    """Local caption input is malformed or unsafe to identify in output."""


def _event_text(event: dict[str, Any]) -> str:
    return "".join(
        str(segment.get("utf8", ""))
        for segment in event.get("segs", [])
        if isinstance(segment, dict)
    )


def _contains_identifier(value: str) -> bool:
    return bool(re.search(r"https?://|youtube\.com|youtu\.be|chzzk|@[A-Za-z0-9_]", value, re.I))


def extract(
    payload: dict[str, Any], *, source_ref: str,
    merge_gap_seconds: int = 20, min_hits: int = 1,
) -> dict[str, Any]:
    if not re.fullmatch(r"refscan-[a-z0-9-]{3,64}", source_ref):
        raise CandidateExtractionError("source_ref must be an opaque refscan id")
    if _contains_identifier(source_ref):
        raise CandidateExtractionError("source_ref may not contain a URL or handle")
    events = payload.get("events")
    if not isinstance(events, list):
        raise CandidateExtractionError("JSON3 events are missing")
    if not 0 <= merge_gap_seconds <= 120 or not 1 <= min_hits <= 100:
        raise CandidateExtractionError("candidate merge bounds are invalid")

    hits: list[tuple[int, tuple[str, ...]]] = []
    for event in events:
        if not isinstance(event, dict):
            raise CandidateExtractionError("JSON3 event is malformed")
        text = _event_text(event)
        categories = tuple(sorted(
            category for category, terms in CUE_TERMS.items()
            if any(term in text for term in terms)
        ))
        if categories:
            start_ms = event.get("tStartMs", 0)
            if not isinstance(start_ms, (int, float)) or start_ms < 0:
                raise CandidateExtractionError("JSON3 timestamp is malformed")
            hits.append((int(start_ms) // 1000, categories))

    groups: list[dict[str, Any]] = []
    for second, categories in hits:
        if not groups or second - groups[-1]["end_seconds"] > merge_gap_seconds:
            groups.append({
                "start_seconds": second,
                "end_seconds": second,
                "cue_categories": set(categories),
                "cue_hits": 1,
            })
        else:
            groups[-1]["end_seconds"] = second
            groups[-1]["cue_categories"].update(categories)
            groups[-1]["cue_hits"] += 1
    candidates = []
    for index, group in enumerate(groups, 1):
        if group["cue_hits"] < min_hits:
            continue
        candidates.append({
            "candidate_id": f"{source_ref}-c{index:04d}",
            "start_seconds": group["start_seconds"],
            "end_seconds": group["end_seconds"],
            "cue_categories": sorted(group["cue_categories"]),
            "cue_hits": group["cue_hits"],
            "human_video_review_required": True,
            "training_permitted": False,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_role": "research_triage_only",
        "source_ref": source_ref,
        "raw_caption_retained": False,
        "training_permitted": False,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="local JSON3 → content-free VOD review windows")
    parser.add_argument("--json3", type=Path, required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--merge-gap-seconds", type=int, default=20)
    parser.add_argument("--min-hits", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.json3.is_file():
        raise CandidateExtractionError("JSON3 must be an existing local file")
    report = extract(
        json.loads(args.json3.read_text(encoding="utf-8")),
        source_ref=args.source_ref,
        merge_gap_seconds=args.merge_gap_seconds,
        min_hits=args.min_hits,
    )
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8", newline="\n")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
