"""Measure the MOSS-TTS-Nano ONNX CPU voice-clone gate on Windows."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOSS_ROOT = ROOT / "external" / "MOSS-TTS-Nano"
PYTHON = ROOT / "external" / "GPT-SoVITS" / ".venv" / "Scripts" / "python.exe"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="안녕하세요. 오늘은 어떤 이야기를 해볼까요?")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--output", default=str(MOSS_ROOT / "generated_audio" / "moss-gate.wav"))
    args = parser.parse_args()
    if not PYTHON.is_file():
        raise FileNotFoundError(PYTHON)
    reference = ROOT / "chatterbox" / "voices" / "airi-reference.wav"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(PYTHON),
        str(MOSS_ROOT / "infer_onnx.py"),
        "--prompt-audio-path",
        str(reference),
        "--text",
        args.text,
        "--output-audio-path",
        str(output),
        "--execution-provider",
        "cpu",
        "--cpu-threads",
        str(args.threads),
        "--disable-wetext-processing",
        "--realtime-streaming-decode",
        "1",
    ]
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=MOSS_ROOT, check=False, text=True)
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        return completed.returncode
    with wave.open(str(output), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    print(f"wall_seconds={elapsed:.3f}")
    print(f"audio_seconds={duration:.3f}")
    print(f"rtf={elapsed / duration:.3f}")
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
