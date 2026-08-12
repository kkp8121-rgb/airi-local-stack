"""Deterministic, offline corpus scorer. Decoder loading is opt-in via --transcriber."""
from __future__ import annotations

import argparse
import importlib
import json
import time
import wave
from pathlib import Path
from typing import Callable


def normalize_transcript(text: str) -> str:
    return "".join(str(text).casefold().split())


def levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, 1):
        current = [index]
        for other_index, right_char in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[other_index] + 1,
                               previous[other_index - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def load_manifest(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != "airi-stt-corpus-v1":
        raise ValueError("manifest schema must be airi-stt-corpus-v1")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("manifest must contain non-empty items")
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("reference"), str):
            raise ValueError("each item requires string id and reference")
    return items


def resolve_transcriber(spec: str | None) -> Callable[[Path, int], str] | None:
    if not spec:
        return None
    module_name, separator, function_name = spec.partition(":")
    if not separator:
        raise ValueError("--transcriber must be package.module:function")
    callback = getattr(importlib.import_module(module_name), function_name)
    if not callable(callback):
        raise ValueError("transcriber is not callable")
    return callback


def validate_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as audio:
        if audio.getnframes() <= 0:
            raise ValueError(f"empty WAV: {path}")


def score(manifest: list[dict[str, object]], predictions: dict[str, str], beams: list[int],
          transcriber: Callable[[Path, int], str] | None, base: Path, warmup: int, repeats: int) -> dict[str, object]:
    if transcriber:
        for _ in range(warmup):
            for item in manifest:
                audio = base / str(item.get("audio", ""))
                if not item.get("audio"):
                    raise ValueError(f"decoder run requires audio for {item['id']}")
                validate_wav(audio)
                transcriber(audio, beams[0])
    matrix: dict[str, object] = {}
    for beam in beams:
        latencies: list[float] = []
        distance = reference_chars = noun_total = noun_hits = 0
        cases = []
        for item in manifest:
            item_id, reference = str(item["id"]), str(item["reference"])
            if transcriber:
                audio = base / str(item["audio"])
                outputs = []
                for _ in range(repeats):
                    started = time.perf_counter()
                    outputs.append(str(transcriber(audio, beam)))
                    latencies.append((time.perf_counter() - started) * 1000)
                predicted = outputs[-1]
            else:
                if item_id not in predictions:
                    raise ValueError(f"missing prediction for {item_id}; pass --predictions or --transcriber")
                predicted = str(predictions[item_id])
                latencies.extend([0.0] * repeats)
            expected, actual = normalize_transcript(reference), normalize_transcript(predicted)
            distance += levenshtein(expected, actual)
            reference_chars += len(expected)
            raw_nouns = item.get("proper_nouns", [])
            if not isinstance(raw_nouns, list) or not all(isinstance(noun, str) for noun in raw_nouns):
                raise ValueError(f"proper_nouns must be a string list for {item_id}")
            nouns = [normalize_transcript(noun) for noun in raw_nouns]
            noun_total += len(nouns)
            noun_hits += sum(noun in actual for noun in nouns)
            cases.append({"id": item_id, "prediction": predicted, "cer": levenshtein(expected, actual) / max(1, len(expected))})
        matrix[str(beam)] = {"cer": distance / max(1, reference_chars),
                              "proper_noun_recall": noun_hits / noun_total if noun_total else None,
                              "latency_ms": {"p50": percentile(latencies, .50), "p95": percentile(latencies, .95)},
                              "cases": cases}
    return {"schema": "airi-stt-benchmark-report-v1", "offline": transcriber is None,
            "warmup": warmup, "repeats": repeats, "beam_matrix": matrix}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, help="offline JSON object mapping item id to transcript")
    parser.add_argument("--transcriber", help="explicit local callback: package.module:function")
    parser.add_argument("--beams", default="1,3")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.warmup < 0 or args.repeats < 1:
        parser.error("warmup must be >= 0 and repeats >= 1")
    predictions = json.loads(args.predictions.read_text(encoding="utf-8")) if args.predictions else {}
    if not isinstance(predictions, dict):
        parser.error("predictions must be a JSON object")
    beams = [int(value) for value in args.beams.split(",") if value.strip()]
    if not beams or any(value < 1 for value in beams):
        parser.error("beams must contain positive integers")
    report = score(load_manifest(args.manifest), predictions,
                   beams,
                   resolve_transcriber(args.transcriber), args.manifest.parent, args.warmup, args.repeats)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
