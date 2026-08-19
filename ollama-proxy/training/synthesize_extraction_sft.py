"""Synthesize span-contract extraction training pairs — every target code-verified.

The span-contract measurement left a precise conclusion: verification kills
fabrication, but selection judgment stays with the model. Selection is a
behavior, and span-format targets are the rare kind of training data whose
correctness a machine can prove — every target here must survive
``parse_stage_a_span`` against its own turns with zero drops before it is
written, so a wrong evidence quote or a name outside its span cannot enter the
dataset at all.

Scenes deliberately mirror the measured failure classes with fresh content:
the subject-selection trap (extract who changed, not who was mentioned), the
{{user}} placeholder registration, and chatter where the correct answer is to
extract nothing. Names are disjoint from the gate fixtures so the extraction
gate remains a valid held-out evaluation, and disjoint from the behavior-SFT
value pools so memorization cannot masquerade as generalization there either.

Output is a pending queue (``training_eligible: false``) like the behavior
pipeline: code proves span validity, but whether an item is *worth* extracting
is a judgment the operator reviews.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "extraction_synthesis_config_v1.json"
DEFAULT_OUTPUT = HERE / "seed" / "airi_extraction_seed_pending.jsonl"

sys.path.insert(0, str(HERE.parent))
from benchmark_memory_track import parse_stage_a_span  # noqa: E402


class ExtractionSynthesisError(ValueError):
    """Fail closed when a target would not survive its own verification."""


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "airi.extraction-synthesis-config.v1":
        raise ExtractionSynthesisError("unexpected config schema")
    if config.get("synthetic_only") is not True:
        raise ExtractionSynthesisError("config must be synthetic_only")
    return config


def _fill(template: str, **values: str) -> str:
    """str.format이 {{user}}를 {user}로 삼키므로 리터럴을 보호하고 채운다."""
    protected = template.replace("{{user}}", "\x01USER\x01")
    return protected.format(**values).replace("\x01USER\x01", "{{user}}")


def _sentence(turns: str, marker: str) -> str:
    """Return the sentence of `turns` that contains `marker` (evidence span)."""
    for part in turns.replace("[turn", "\x00[turn").split("\x00"):
        if marker in part:
            text = part.strip()
            return text
    raise ExtractionSynthesisError(f"marker {marker!r} not in turns")


def iter_records(config: dict[str, Any]) -> Iterator[dict[str, Any]]:
    scenes = config["scenes"]

    template = scenes["state_change"]["turns"]
    for person in config["persons"]:
        for organization in config["organizations"]:
            for role in config["roles"][:2]:
                turns = _fill(template, p=person, org=organization, role=role)
                evidence = _sentence(turns, person)
                yield {
                    "scene": "state_change", "character": f"name: {person}", "turns": turns,
                    "target": {"extracted": [
                        {"turnNumber": 9, "kind": "entity", "subtype": "person",
                         "name": person, "content": f"{organization}의 {role}이 되었다",
                         "evidence": evidence},
                    ]},
                }

    template = scenes["placeholder_add"]["turns"]
    for person in config["persons"][:4]:
        for organization in config["organizations"]:
            item = config["items"][(config["persons"].index(person)) % len(config["items"])]
            turns = _fill(template, p=person, org=organization,
                                    role=config["roles"][0], item=item)
            first = _sentence(turns, organization)
            second = _sentence(turns, "{{user}}")
            yield {
                "scene": "placeholder_add", "character": f"name: {person}", "turns": turns,
                "target": {"extracted": [
                    {"turnNumber": 1, "kind": "entity", "subtype": "organization",
                     "name": organization, "content": f"{person}의 소속", "evidence": first},
                    {"turnNumber": 1, "kind": "relation", "subtype": "affiliation",
                     "sourceName": person, "targetName": organization,
                     "content": "소속 관계", "evidence": first},
                    {"turnNumber": 1, "kind": "entity", "subtype": "person",
                     "name": "{{user}}", "content": f"{person}의 조수", "evidence": second},
                    {"turnNumber": 1, "kind": "entity", "subtype": "item",
                     "name": item, "content": "{{user}}의 사용 도구", "evidence": second},
                    {"turnNumber": 1, "kind": "relation", "subtype": "uses",
                     "sourceName": "{{user}}", "targetName": item,
                     "content": "사용 관계", "evidence": second},
                ]},
            }

    turns = scenes["skip_chatter"]["turns"]
    for person in config["persons"]:
        yield {"scene": "skip_chatter", "character": f"name: {person}", "turns": turns,
               "target": {"extracted": []}}

    template = scenes["trait_fact"]["turns"]
    for person in config["persons"]:
        for trait in config["traits"]:
            turns = _fill(template, p=person, trait=trait)
            yield {"scene": "trait_fact", "character": f"name: {person}", "turns": turns,
                   "target": {"extracted": [
                       {"turnNumber": 5, "kind": "fact", "subtype": "trait",
                        "subjectNames": [person], "content": trait,
                        "turnRange": [5, 5], "evidence": _sentence(turns, person)},
                   ]}}

    template = scenes["moment_event"]["turns"]
    for person in config["persons"]:
        for event in config["events"]:
            turns = _fill(template, p=person, event=event)
            yield {"scene": "moment_event", "character": f"name: {person}", "turns": turns,
                   "target": {"extracted": [
                       {"turnNumber": 6, "kind": "fact", "subtype": "moment",
                        "subjectNames": [person], "content": f"{event}에서 우승했다",
                        "turnRange": [6, 6], "evidence": _sentence(turns, person)},
                   ]}}

    template = scenes["relation_pair"]["turns"]
    for person in config["persons"]:
        for partner in config["partners"]:
            turns = _fill(template, p=person, q=partner)
            yield {"scene": "relation_pair", "character": f"name: {person}", "turns": turns,
                   "target": {"extracted": [
                       {"turnNumber": 7, "kind": "relation", "subtype": "friendship",
                        "sourceName": person, "targetName": partner,
                        "content": "어릴 때부터 친구", "evidence": _sentence(turns, person)},
                   ]}}


def synthesize(config: dict[str, Any]) -> list[dict[str, Any]]:
    split_cycle = list(config["split_cycle"])
    records: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    for entry in iter_records(config):
        # 자기 검증: 타깃이 스팬 파서를 무손실 통과하지 못하면 데이터가 아니라 버그다.
        survivors, dropped = parse_stage_a_span(
            json.loads(json.dumps(entry["target"], ensure_ascii=False)), entry["turns"])
        if dropped != 0 or len(survivors["extracted"]) != len(entry["target"]["extracted"]):
            raise ExtractionSynthesisError(
                f"target fails its own span verification: {entry['scene']} / {entry['turns'][:40]}")
        scene = entry["scene"]
        counters[scene] = counters.get(scene, 0) + 1
        index = counters[scene]
        records.append({
            "id": f"xseed-{scene}-{index:04d}",
            "split": split_cycle[len(records) % len(split_cycle)],
            "task": "stage_a_span",
            "scene": scene,
            "character": entry["character"],
            "turns": entry["turns"],
            "target": json.dumps(entry["target"], ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")),
            "partition": {"tier": "S1", "group": f"xpending-{scene.replace('_', '-')}-{index:04d}"},
            "review": {"status": "pending", "reviewer": "", "approved_at": ""},
            "provenance": {"synthetic": True, "source": "extraction-synthesizer-v1",
                           "template": scene},
            "training_eligible": False,
        })
    identifiers = [record["id"] for record in records]
    if len(set(identifiers)) != len(identifiers):
        raise ExtractionSynthesisError("duplicate record id")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="extraction span-SFT pending queue synthesizer")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stats-only", action="store_true")
    args = parser.parse_args(argv)
    records = synthesize(load_config())
    counts: dict[str, int] = {}
    for record in records:
        counts[record["scene"]] = counts.get(record["scene"], 0) + 1
    summary = {"total": len(records), "scenes": counts,
               "splits": {split: sum(1 for record in records if record["split"] == split)
                          for split in ("train", "dev", "test")},
               "training_eligible": False}
    if not args.stats_only:
        payload = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")) for record in records) + "\n"
        args.output.write_text(payload, encoding="utf-8", newline="\n")
        summary["output"] = str(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
