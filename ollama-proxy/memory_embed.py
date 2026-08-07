"""Pluggable text embedding for the AIRI memory layer.

Two modes, selected by `AIRI_EMBED_MODE` (or the `memory.embed_mode` config):

- `fake`  - dependency-free hashing-trick vectors. Deterministic across
            processes (hashlib, never the salted builtin hash), sub-millisecond,
            and similar Korean strings still land near each other because the
            tokenizer emits character bigrams. This is what runs on the AIRI
            machine and in the tests.
- `local` - sentence-transformers with KURE-v1 (Korean retrieval model). The
            reference is explicit that embeddings must stay local: an API
            embedding costs 200-400ms and blows the 150ms retrieval budget.

`local` is fail-open by design: a machine without sentence-transformers (or
without the model downloaded) logs a warning and degrades to `fake` rather than
taking the speech path down with it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections.abc import Sequence

try:  # numpy powers the brute-force cosine scan; pure Python is the fallback.
    import numpy as _np
except Exception:  # pragma: no cover - numpy is present on this machine
    _np = None

FAKE_DIM = 64
DEFAULT_LOCAL_MODEL = "nlpai-lab/KURE-v1"
FAKE_MODE = "fake"
LOCAL_MODE = "local"

# Words and Korean runs. Bigrams are added on top so "강아지" and "강아지가"
# overlap - Korean has no spacing boundary a plain word split could use.
_TOKEN_RE = re.compile(r"[0-9a-z_]+|[가-힣]+")


def _log(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _TOKEN_RE.findall(text.lower()):
        tokens.append(word)
        for index in range(len(word) - 1):
            tokens.append(word[index : index + 2])
    return tokens


def fake_vector(text: str, dim: int = FAKE_DIM) -> list[float]:
    """Hashing-trick vector: signed token counts folded into `dim` buckets."""
    vector = [0.0] * dim
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    return normalize(vector)


def normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return list(vector)
    return [value / norm for value in vector]


def pack_vector(vector: Sequence[float]) -> bytes:
    """Store as little-endian float32 so numpy can frombuffer it directly."""
    normalized = normalize(vector)
    return struct.pack(f"<{len(normalized)}f", *normalized)


def unpack_vector(blob: bytes | None) -> list[float] | None:
    if not blob:
        return None
    count = len(blob) // 4
    if count == 0:
        return None
    return list(struct.unpack(f"<{count}f", blob[: count * 4]))


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Both sides are stored L2-normalized, so the dot product is the cosine."""
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    return float(sum(left[index] * right[index] for index in range(size)))


def cosine_many(query: Sequence[float], blobs: Sequence[bytes | None]) -> list[float]:
    """Cosine of `query` against a column of stored vectors.

    Brute force on purpose: the reference measured <1ms at ~100 rows and calls
    for sqlite-vec only past 10k rows, which this deployment is nowhere near.
    """
    if _np is not None:
        query_vector = _np.asarray(query, dtype=_np.float32)
        scores: list[float] = []
        for blob in blobs:
            if not blob:
                scores.append(0.0)
                continue
            row = _np.frombuffer(blob, dtype="<f4")
            size = min(row.shape[0], query_vector.shape[0])
            scores.append(float(row[:size] @ query_vector[:size]) if size else 0.0)
        return scores
    return [cosine(query, unpack_vector(blob) or []) for blob in blobs]


class Embedder:
    """Encodes text to L2-normalized vectors. `mode` reports what actually ran."""

    def __init__(self, mode: str, dim: int, model_name: str = "", model: object = None) -> None:
        self.mode = mode
        self.dim = dim
        self.model_name = model_name
        self._model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._model is None:
            return [fake_vector(text, self.dim) for text in texts]
        vectors = self._model.encode(
            list(texts),
            batch_size=16,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [normalize([float(value) for value in vector]) for vector in vectors]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def build_embedder(mode: str = FAKE_MODE, model_name: str = DEFAULT_LOCAL_MODEL) -> Embedder:
    """Return the requested embedder, degrading to `fake` when local is unusable."""
    requested = (mode or FAKE_MODE).strip().lower()
    if requested != LOCAL_MODE:
        return Embedder(FAKE_MODE, FAKE_DIM)
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    except Exception as exc:
        _log("memory_embed", status="fallback", requested=LOCAL_MODE, reason=type(exc).__name__)
        return Embedder(FAKE_MODE, FAKE_DIM)
    try:
        model = SentenceTransformer(model_name)
        dim = int(model.get_sentence_embedding_dimension())
    except Exception as exc:
        _log(
            "memory_embed",
            status="fallback",
            requested=LOCAL_MODE,
            model=model_name,
            reason=type(exc).__name__,
        )
        return Embedder(FAKE_MODE, FAKE_DIM)
    _log("memory_embed", status="ok", mode=LOCAL_MODE, model=model_name, dim=dim)
    return Embedder(LOCAL_MODE, dim, model_name=model_name, model=model)
