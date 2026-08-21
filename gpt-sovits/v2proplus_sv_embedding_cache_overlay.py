"""Fail-closed in-memory v2ProPlus speaker-embedding cache overlay."""
from __future__ import annotations

import hashlib
import importlib
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PINNED_TTS_SHA256 = "75398e84f6625044d794ebfc2f2ac6d6202f328259e13e032c405301e99efb6a"

class OverlayGuardError(RuntimeError): pass

@dataclass(frozen=True)
class CacheContext:
    ref_audio_path: str
    aux_ref_audio_paths: tuple[str, ...]
    device: str
    precision: str
    model_identity: int

def _tensor_identity(tensor: Any) -> tuple[int, int, tuple[int, ...], str, str]:
    """Identify the already-cached tensor without a GPU-to-CPU synchronization.

    GPT-SoVITS keeps the reference tensor in ``prompt_cache`` until an explicit
    reference/auxiliary-reference refresh.  Those refreshes are represented in
    ``CacheContext`` and clear the cache.  Hashing tensor bytes here would copy
    the same reference audio off the GPU for every streamed sentence and erase
    part of the latency win this overlay exists to measure.
    """
    pointer = int(tensor.data_ptr()) if callable(getattr(tensor, "data_ptr", None)) else id(tensor)
    try:
        version = int(getattr(tensor, "_version", 0))
    except RuntimeError:  # PyTorch inference tensors intentionally omit it.
        version = 0
    shape = tuple(int(item) for item in tensor.shape)
    return pointer, version, shape, str(tensor.dtype), str(getattr(tensor, "device", "unknown"))

class SpeakerEmbeddingCache:
    def __init__(self) -> None:
        self._values: dict[tuple[CacheContext, tuple[int, int, tuple[int, ...], str, str]], Any] = {}
        self._lock = threading.Lock()
    def get_or_compute(self, context: CacheContext, audio: Any, compute: Callable[[Any], Any]) -> Any:
        key = (context, _tensor_identity(audio))
        with self._lock:  # prevents duplicate GPU work; TTS is already serialized.
            if key not in self._values:
                self._values[key] = compute(audio)
            return self._values[key]
    def clear(self) -> None:
        with self._lock: self._values.clear()

def install_for_tts(tts_class: type, cache: SpeakerEmbeddingCache | None = None) -> SpeakerEmbeddingCache:
    if getattr(tts_class, "_airi_sv_cache_installed", False): return tts_class._airi_sv_cache
    cache = cache or SpeakerEmbeddingCache()
    original_init, original_run, original_set_ref = tts_class.__init__, tts_class.run, tts_class.set_ref_audio
    torch_module = getattr(original_run, "__globals__", {}).get("torch")
    def init(self: Any, *args: Any, **kwargs: Any):
        original_init(self, *args, **kwargs)
        model, compute = self.sv_model, self.sv_model.compute_embedding3
        def cached_compute(audio: Any):
            context = getattr(self, "_airi_sv_context", None)
            return compute(audio) if context is None else cache.get_or_compute(context, audio, compute)
        model.compute_embedding3 = cached_compute
    def run(self: Any, inputs: dict):
        old = getattr(self, "_airi_sv_context", None)
        self._airi_sv_context = CacheContext(str(inputs.get("ref_audio_path") or ""), tuple(map(str, inputs.get("aux_ref_audio_paths") or [])), str(self.configs.device), str(self.precision), id(self.sv_model))
        inference = torch_module.inference_mode() if torch_module is not None else nullcontext()
        try:
            with inference:
                yield from original_run(self, inputs)
        finally: self._airi_sv_context = old
    def set_ref(self: Any, path: str):
        cache.clear()  # explicit reference cache refresh/reset invalidates all entries.
        return original_set_ref(self, path)
    tts_class.__init__, tts_class.run, tts_class.set_ref_audio = init, run, set_ref
    tts_class._airi_sv_cache_installed, tts_class._airi_sv_cache = True, cache
    return cache

def install(external_root: Path, expected_sha256: str = PINNED_TTS_SHA256) -> SpeakerEmbeddingCache:
    path = external_root / "GPT_SoVITS" / "TTS_infer_pack" / "TTS.py"
    if not path.is_file(): raise OverlayGuardError(f"upstream TTS.py not found: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not expected_sha256 or actual.casefold() != expected_sha256.casefold():
        raise OverlayGuardError(f"upstream TTS.py digest mismatch: {actual}")
    return install_for_tts(importlib.import_module("GPT_SoVITS.TTS_infer_pack.TTS").TTS)
