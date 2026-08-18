"""Offline A/B of Korean memory-recall embedders on a pinned synthetic set.

The stock `benchmark_memory_track.py --mode embedding` fixture is four documents
and three queries, which cannot separate two strong Korean embedders — both score
a perfect MRR.  This runner uses a larger authored set whose distractors are the
point: same entity with a different attribute, the superseded version of a fact,
and paraphrase targets that share almost no surface tokens with their query.

Scoring is plain cosine ranking over the whole corpus.  It reports per-category
results because an aggregate mean hides exactly the trade-off worth knowing —
one model can win on paraphrase while losing on entity disambiguation.

Loading a model is the only step that can touch the network, and it is refused
unless `--allow-download` is passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Sequence


HERE = Path(__file__).resolve().parent
FIXTURE_PATH = HERE / "korean_memory_recall_v1.json"
FIXTURE_SCHEMA_VERSION = "airi.embedding-ab-fixture.v1"
FIXTURE_SHA256 = "1c2d295c7200739f19619cac6a9323c9367f2b5be490c040a1367c4ef6ab17ac"
REPORT_SCHEMA_VERSION = "airi.embedding-ab-report.v1"
CATEGORIES = ("lexical", "paraphrase", "disambiguation", "supersede")
RECALL_AT = (1, 3, 5)

Encoder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


class EmbeddingAbError(ValueError):
    """Fail-closed error for a malformed fixture or model spec."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def validate_fixture(value: Any) -> dict[str, Any]:
    """Structural validation only; it makes no claim that the labels are correct."""
    if not isinstance(value, dict) or value.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise EmbeddingAbError("unexpected fixture schema")
    if value.get("synthetic_only") is not True:
        raise EmbeddingAbError("fixture must be marked synthetic_only")
    corpus, queries = value.get("corpus"), value.get("queries")
    if not isinstance(corpus, list) or not isinstance(queries, list) or not corpus or not queries:
        raise EmbeddingAbError("fixture needs a non-empty corpus and queries")
    ids = [item["id"] for item in corpus]
    if len(set(ids)) != len(ids):
        raise EmbeddingAbError("duplicate corpus id")
    known = set(ids)
    for query in queries:
        if query.get("category") not in CATEGORIES:
            raise EmbeddingAbError(f"unknown category: {query.get('category')}")
        relevant = query.get("relevant")
        if not isinstance(relevant, list) or not relevant or not set(relevant) <= known:
            raise EmbeddingAbError(f"query {query.get('id')} references an unknown document")
    return value


def load_fixture(path: Path = FIXTURE_PATH, *, verify_digest: bool = True) -> dict[str, Any]:
    fixture = validate_fixture(json.loads(path.read_text(encoding="utf-8")))
    digest = hashlib.sha256(canonical_bytes(fixture)).hexdigest()
    if verify_digest and FIXTURE_SHA256 != "PENDING" and digest != FIXTURE_SHA256:
        raise EmbeddingAbError("fixture digest does not match the pinned value")
    return fixture


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Normalize here so a caller's encoder need not return unit vectors."""
    dot = sum(a * b for a, b in zip(left, right))
    scale = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / scale if scale else 0.0


def rank_of_first_relevant(scores: Sequence[tuple[str, float]], relevant: Sequence[str]) -> int | None:
    """1-based rank of the best-placed relevant document, or None if it never appears."""
    ordered = sorted(range(len(scores)), key=lambda index: -scores[index][1])
    wanted = set(relevant)
    for position, index in enumerate(ordered, start=1):
        if scores[index][0] in wanted:
            return position
    return None


def _summarize(ranks: Sequence[int | None]) -> dict[str, float]:
    total = len(ranks)
    found = [rank for rank in ranks if rank is not None]
    return {
        "queries": total,
        "mrr": round(sum(1 / rank for rank in found) / total, 4) if total else 0.0,
        **{f"recall_at_{k}": round(sum(1 for rank in found if rank <= k) / total, 4) if total else 0.0
           for k in RECALL_AT},
        "median_rank": statistics.median(found) if found else None,
    }


def evaluate(encode: Encoder, fixture: dict[str, Any], *, name: str = "model") -> dict[str, Any]:
    """Rank the whole corpus per query; returns aggregate plus per-category detail."""
    corpus = fixture["corpus"]
    corpus_texts = [item["text"] for item in corpus]
    corpus_started = time.perf_counter()
    corpus_vectors = list(encode(corpus_texts))
    corpus_ms = (time.perf_counter() - corpus_started) * 1000
    if len(corpus_vectors) != len(corpus_texts):
        raise EmbeddingAbError("encoder returned the wrong number of corpus vectors")
    ranks: list[int | None] = []
    per_category: dict[str, list[int | None]] = {category: [] for category in CATEGORIES}
    misses: list[dict[str, Any]] = []
    query_times: list[float] = []
    for query in fixture["queries"]:
        started = time.perf_counter()
        vector = list(encode([query["text"]]))[0]
        query_times.append((time.perf_counter() - started) * 1000)
        scores = [(corpus[index]["id"], cosine(vector, corpus_vectors[index])) for index in range(len(corpus))]
        rank = rank_of_first_relevant(scores, query["relevant"])
        ranks.append(rank)
        per_category[query["category"]].append(rank)
        if rank is None or rank > 1:
            top = max(scores, key=lambda pair: pair[1])
            misses.append({"query_id": query["id"], "category": query["category"], "rank": rank,
                           "expected": list(query["relevant"]), "top_id": top[0], "top_score": round(top[1], 4)})
    sorted_times = sorted(query_times)
    return {
        "name": name,
        "overall": _summarize(ranks),
        "by_category": {category: _summarize(values) for category, values in per_category.items()},
        "misses": misses,
        "latency": {
            "corpus_encode_ms": round(corpus_ms, 3),
            "query_encode_p50_ms": round(sorted_times[len(sorted_times) // 2], 3) if sorted_times else None,
            "query_encode_p95_ms": round(sorted_times[min(len(sorted_times) - 1, int(len(sorted_times) * 0.95))], 3) if sorted_times else None,
        },
    }


def parse_model_specs(values: Sequence[str]) -> list[tuple[str, str]]:
    specs = []
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name.strip() or not path.strip():
            raise EmbeddingAbError(f"expected name=path, got: {value}")
        specs.append((name.strip(), path.strip()))
    if not specs:
        raise EmbeddingAbError("at least one --model name=path is required")
    return specs


def sentence_transformer_encoder(path: str, *, device: str | None, allow_download: bool) -> Encoder:
    """Load a local SentenceTransformer; downloading stays opt-in."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(path, device=device, local_files_only=not allow_download)

    def encode(texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [list(map(float, vector)) for vector in
                model.encode(list(texts), batch_size=16, normalize_embeddings=True)]

    return encode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A/B Korean memory-recall embedders offline.")
    parser.add_argument("--model", action="append", default=[], help="name=path, repeatable")
    parser.add_argument("--device", default=None, help="torch device; default lets sentence-transformers choose")
    parser.add_argument("--allow-download", action="store_true", help="permit fetching a model that is not cached")
    parser.add_argument("--report", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)

    fixture = load_fixture()
    results = []
    for name, path in parse_model_specs(args.model):
        try:
            encode = sentence_transformer_encoder(path, device=args.device, allow_download=args.allow_download)
            results.append({"status": "measured", "path": path,
                            **evaluate(encode, fixture, name=name)})
        except Exception as error:  # a failed model must not hide the other arm's result
            results.append({"status": "error", "name": name, "path": path, "reason": type(error).__name__,
                            "detail": str(error)[:200]})
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "fixture_sha256": hashlib.sha256(canonical_bytes(fixture)).hexdigest(),
        "corpus_size": len(fixture["corpus"]),
        "query_count": len(fixture["queries"]),
        "network_allowed": bool(args.allow_download),
        "models": results,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if any(item["status"] == "measured" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
