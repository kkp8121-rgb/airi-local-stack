# coding=utf-8
# SPDX-License-Identifier: Apache-2.0
"""CPU-oriented PyTorch backend for Qwen3-TTS."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

from .base import TTSBackend

logger = logging.getLogger(__name__)

try:
    import librosa

    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

IPEX_AVAILABLE = importlib.util.find_spec("intel_extension_for_pytorch") is not None


class PyTorchCPUBackend(TTSBackend):
    """Qwen3-TTS backend tuned for CPU inference.

    The default checkpoint is a CustomVoice model because ``generate_speech``
    uses preset speakers. Base checkpoints remain supported through the
    dedicated voice-clone endpoint.
    """

    def __init__(
        self,
        model_id: str = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        device: str = "cpu",
        dtype: str = "float32",
        attn_implementation: str = "sdpa",
        cpu_threads: int = 12,
        cpu_interop_threads: int = 2,
        use_ipex: bool = False,
    ):
        super().__init__()
        self.model_name = model_id
        self.device_name = device
        self.dtype_name = dtype
        self.attn_implementation = attn_implementation
        self.cpu_threads = max(1, int(cpu_threads))
        self.cpu_interop_threads = max(1, int(cpu_interop_threads))
        self.use_ipex = bool(use_ipex and IPEX_AVAILABLE)
        self._ready = False

        if self.device_name == "cpu":
            try:
                torch.set_num_threads(self.cpu_threads)
                torch.set_num_interop_threads(self.cpu_interop_threads)
            except RuntimeError as exc:
                logger.warning("Could not change PyTorch thread counts: %s", exc)

    async def initialize(self) -> None:
        """Load the model without blocking FastAPI's event loop."""
        if self._ready:
            return

        def _load_model():
            from qwen_tts import Qwen3TTSModel

            dtype_map = {
                "float32": torch.float32,
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
            }
            dtype = dtype_map.get(self.dtype_name.lower())
            if dtype is None:
                raise ValueError(
                    f"Unsupported TTS_DTYPE={self.dtype_name!r}; use float32, float16, or bfloat16"
                )
            if self.device_name == "cpu" and dtype != torch.float32:
                logger.warning(
                    "%s on CPU may be slower or unsupported; float32 is recommended",
                    self.dtype_name,
                )

            attention = self.attn_implementation.lower()
            if self.device_name == "cpu" and attention == "flash_attention_2":
                logger.warning("Flash Attention 2 is not a CPU path; using sdpa")
                attention = "sdpa"

            try:
                model = Qwen3TTSModel.from_pretrained(
                    self.model_name,
                    device_map=self.device_name,
                    dtype=dtype,
                    attn_implementation=attention,
                )
            except Exception as first_error:
                if attention == "eager":
                    raise
                logger.warning(
                    "Failed to load with %s attention (%s); retrying with eager",
                    attention,
                    first_error,
                )
                model = Qwen3TTSModel.from_pretrained(
                    self.model_name,
                    device_map=self.device_name,
                    dtype=dtype,
                    attn_implementation="eager",
                )

            if self.use_ipex:
                try:
                    import intel_extension_for_pytorch as ipex

                    model.model = ipex.optimize(model.model, dtype=dtype)
                except Exception as exc:
                    logger.warning("IPEX optimization failed; continuing without it: %s", exc)

            return model, dtype

        try:
            self.model, self.dtype = await asyncio.to_thread(_load_model)
            self.device = self.device_name
            self._ready = True
            logger.info(
                "CPU PyTorch backend loaded: model=%s device=%s dtype=%s",
                self.model_name,
                self.device,
                self.dtype_name,
            )
        except Exception as exc:
            self.model = None
            self._ready = False
            raise RuntimeError(f"Failed to initialize CPU PyTorch backend: {exc}") from exc

    async def _apply_speed(self, audio: np.ndarray, speed: float) -> np.ndarray:
        audio = np.asarray(audio, dtype=np.float32)
        if speed == 1.0:
            return audio
        if not LIBROSA_AVAILABLE:
            logger.warning("Speed adjustment requested but librosa is unavailable")
            return audio
        return await asyncio.to_thread(librosa.effects.time_stretch, audio, rate=speed)

    async def generate_speech(
        self,
        text: str,
        voice: str,
        language: str = "Auto",
        instruct: Optional[str] = None,
        speed: float = 1.0,
    ) -> Tuple[np.ndarray, int]:
        if not self._ready:
            await self.initialize()
        if self.get_model_type() == "base":
            raise RuntimeError(
                "Preset-voice speech requires a CustomVoice checkpoint. "
                "Use Qwen3-TTS-12Hz-0.6B-CustomVoice, or call /v1/audio/voice-clone "
                "with a Base checkpoint."
            )

        try:
            wavs, sample_rate = await asyncio.to_thread(
                self.model.generate_custom_voice,
                text=text,
                language=language,
                speaker=voice,
                instruct=instruct,
            )
            if not wavs:
                raise RuntimeError("Model returned no audio")
            audio = await self._apply_speed(np.asarray(wavs[0]), speed)
            return audio, int(sample_rate)
        except Exception as exc:
            raise RuntimeError(f"Speech generation failed: {exc}") from exc

    def get_backend_name(self) -> str:
        return "pytorch_cpu"

    def get_model_id(self) -> str:
        return self.model_name

    def get_supported_voices(self) -> List[str]:
        if self.get_model_type() == "base":
            return []
        fallback = ["Vivian", "Ryan", "Sophia", "Isabella", "Evan", "Lily"]
        if not self._ready or not self.model:
            return fallback
        try:
            getter = getattr(self.model.model, "get_supported_speakers", None)
            speakers = getter() if getter else None
            return list(speakers) if speakers else fallback
        except Exception as exc:
            logger.warning("Could not query supported speakers: %s", exc)
            return fallback

    def get_supported_languages(self) -> List[str]:
        fallback = [
            "English", "Chinese", "Japanese", "Korean", "German",
            "French", "Spanish", "Russian", "Portuguese", "Italian",
        ]
        if not self._ready or not self.model:
            return fallback
        try:
            getter = getattr(self.model.model, "get_supported_languages", None)
            languages = getter() if getter else None
            return list(languages) if languages else fallback
        except Exception as exc:
            logger.warning("Could not query supported languages: %s", exc)
            return fallback

    def is_ready(self) -> bool:
        return self._ready

    def get_device_info(self) -> Dict[str, Any]:
        return {
            "device": str(self.device) if self.device else self.device_name,
            "gpu_available": False,
            "gpu_name": None,
            "vram_total": None,
            "vram_used": None,
            "cpu_threads": self.cpu_threads,
            "cpu_interop_threads": self.cpu_interop_threads,
            "ipex_enabled": self.use_ipex,
        }

    def supports_voice_cloning(self) -> bool:
        return self.get_model_type() == "base"

    def get_model_type(self) -> str:
        lowered = self.model_name.lower()
        if "customvoice" in lowered:
            return "customvoice"
        if "base" in lowered:
            return "base"
        return "unknown"

    async def generate_voice_clone(
        self,
        text: str,
        ref_audio: np.ndarray,
        ref_audio_sr: int,
        ref_text: Optional[str] = None,
        language: str = "Auto",
        x_vector_only_mode: bool = False,
        speed: float = 1.0,
    ) -> Tuple[np.ndarray, int]:
        if not self._ready:
            await self.initialize()
        if not self.supports_voice_cloning():
            raise RuntimeError("Voice cloning requires a Qwen3-TTS Base checkpoint.")
        if not x_vector_only_mode and not ref_text:
            raise ValueError("ref_text is required when x_vector_only_mode is false")

        try:
            wavs, sample_rate = await asyncio.to_thread(
                self.model.generate_voice_clone,
                text=text,
                ref_audio=(np.asarray(ref_audio, dtype=np.float32), int(ref_audio_sr)),
                ref_text=ref_text,
                language=language,
                x_vector_only_mode=x_vector_only_mode,
            )
            if not wavs:
                raise RuntimeError("Model returned no audio")
            audio = await self._apply_speed(np.asarray(wavs[0]), speed)
            return audio, int(sample_rate)
        except Exception as exc:
            raise RuntimeError(f"Voice cloning failed: {exc}") from exc
