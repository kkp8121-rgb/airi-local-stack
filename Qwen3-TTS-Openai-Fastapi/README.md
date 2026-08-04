# Qwen3-TTS OpenAI-Compatible FastAPI Server

Serve Qwen3-TTS behind the OpenAI `POST /v1/audio/speech` interface, with optional voice cloning, saved voice profiles, real-time PCM streaming, CUDA/ROCm/CPU backends, and native Apple Silicon support.

This repository is based on the Qwen3-TTS implementation from the Alibaba Qwen team and adds an API/deployment layer intended for local applications and self-hosted services.

## Highlights

- OpenAI-compatible `POST /v1/audio/speech`
- Model and voice discovery under `/v1/models` and `/v1/voices`
- MP3, Opus, AAC, FLAC, WAV, and signed 16-bit PCM output
- Official, optimized, vLLM-Omni, PyTorch CPU, OpenVINO, and MLX backends
- Base-model voice cloning through `/v1/audio/voice-clone`
- Persistent voice-library profiles through `voice="clone:ProfileName"`
- Lazy model loading, bounded generation concurrency, warmup, and health checks
- Automatic long-text chunking with punctuation-aware boundaries
- Docker, NVIDIA GPU, AMD ROCm, CPU, and Apple Silicon deployment paths
- Optional Gradio Voice Studio and browser interface

## Important: choose the correct model type

Qwen3-TTS exposes different checkpoint families with different generation methods.

| Checkpoint type | Use it for | Do not use it for |
|---|---|---|
| `*-CustomVoice` | Preset speakers such as Vivian, Ryan, Serena, Dylan, and others | Reference-audio voice cloning |
| `*-Base` | `/v1/audio/voice-clone` and saved `clone:` profiles | Preset-speaker `/v1/audio/speech` requests |
| `*-VoiceDesign` | Voice design workflows supported by the underlying model/backend | Assuming preset-speaker or Base-model semantics |

For normal OpenAI-style TTS, start with a **CustomVoice** checkpoint. For voice cloning, run a **Base** checkpoint and call the clone endpoint.

## Requirements

- Python 3.10-3.12 recommended
- FFmpeg for MP3, Opus, AAC, or FLAC responses
- A backend-appropriate PyTorch/CUDA/ROCm installation for GPU use
- Enough RAM/VRAM for the selected checkpoint

WAV and PCM output do not require FFmpeg.

## Quick start

```bash
git clone https://github.com/groxaxo/Qwen3-TTS-Openai-Fastapi.git
cd Qwen3-TTS-Openai-Fastapi

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[api]"

# Default backend: official, 1.7B CustomVoice
python -m api.main
```

The server listens on `http://localhost:8880` by default.

Useful URLs:

- Web interface: `http://localhost:8880/`
- Swagger: `http://localhost:8880/docs`
- Health: `http://localhost:8880/health`
- Models: `http://localhost:8880/v1/models`
- Voices: `http://localhost:8880/v1/voices`

The backend loads lazily by default, so `/health` can report `initializing` until the first synthesis request.

## OpenAI Python client

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8880/v1",
    api_key="not-needed",
)

response = client.audio.speech.create(
    model="tts-1",
    voice="Ryan",
    input="Hello from a local Qwen3-TTS server.",
    response_format="mp3",
    speed=1.0,
)
response.stream_to_file("speech.mp3")
```

OpenAI voice aliases are accepted:

| Alias | Qwen voice |
|---|---|
| `alloy` | Vivian |
| `echo` | Ryan |
| `fable` | Sophia |
| `nova` | Isabella |
| `onyx` | Evan |
| `shimmer` | Lily |

The exact native speaker list depends on the selected checkpoint and backend. Query `/v1/voices` rather than hard-coding the table above.

## cURL

```bash
curl --fail --show-error \
  http://localhost:8880/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "tts-1",
    "voice": "Ryan",
    "input": "This response is a WAV file.",
    "response_format": "wav"
  }' \
  --output speech.wav
```

## Language-specific model aliases

The API accepts aliases such as `tts-1-es` and `tts-1-hd-fr`. The suffix forces the language passed to the backend.

Supported suffixes:

- `en` English
- `zh` Chinese
- `ja` Japanese
- `ko` Korean
- `de` German
- `fr` French
- `es` Spanish
- `ru` Russian
- `pt` Portuguese
- `it` Italian

Example:

```python
response = client.audio.speech.create(
    model="tts-1-es",
    voice="Ryan",
    input="Hola, esta solicitud fuerza la salida en español.",
    response_format="wav",
)
response.stream_to_file("hola.wav")
```

## Audio formats

| `response_format` | MIME type | Notes |
|---|---|---|
| `mp3` | `audio/mpeg` | Requires FFmpeg |
| `opus` | `audio/opus` | Requires FFmpeg with Opus support |
| `aac` | `audio/aac` | ADTS AAC; requires FFmpeg |
| `flac` | `audio/flac` | Requires an available encoder |
| `wav` | `audio/wav` | PCM WAV container |
| `pcm` | `audio/pcm` | Headerless mono signed 16-bit little-endian PCM |

Encoding errors fail clearly. The server does **not** return WAV bytes while claiming a compressed content type.

## Real-time PCM streaming

The optimized backend can yield PCM while the model is generating. Use `stream=true` and `response_format="pcm"`.

```python
import httpx
import numpy as np
import sounddevice as sd

request = {
    "model": "tts-1",
    "voice": "Ryan",
    "input": "This audio is streamed as signed sixteen-bit PCM.",
    "response_format": "pcm",
    "stream": True,
}

with httpx.stream(
    "POST",
    "http://localhost:8880/v1/audio/speech",
    json=request,
    timeout=None,
) as response:
    response.raise_for_status()
    pcm = np.frombuffer(b"".join(response.iter_bytes()), dtype="<i2")

sd.play(pcm, samplerate=24000)
sd.wait()
```

For backends without native generation streaming, `stream=true` sends chunks from the completely encoded result. Compressed output is encoded once and then byte-chunked; separate compressed files are never concatenated.

## Backend selection

Set `TTS_BACKEND` before starting the server.

| Backend | Value | Recommended use |
|---|---|---|
| Official | `official` | Default, broad feature compatibility |
| Optimized | `optimized` | GPU production, model switching, native PCM streaming, voice library |
| vLLM-Omni | `vllm_omni` | Dedicated high-throughput vLLM deployment |
| PyTorch CPU | `pytorch` | CPU-only systems |
| OpenVINO | `openvino` | Experimental exported-model path |
| Apple MLX | `mlx` | Native Apple Silicon deployment |

### Official backend

```bash
export TTS_BACKEND=official
export TTS_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
python -m api.main
```

### Optimized backend

The optimized backend reads `config.yaml` from `~/qwen3-tts/config.yaml` unless `TTS_CONFIG` points elsewhere.

```bash
mkdir -p ~/qwen3-tts
cp config.yaml ~/qwen3-tts/config.yaml

TTS_BACKEND=optimized python -m api.main
```

Edit the model entries in `config.yaml` to use Hugging Face IDs or local paths. The configured `type` must match the checkpoint: `customvoice` or `base`.

### vLLM-Omni

Use the dedicated environment/image because vLLM has strict CUDA and package compatibility requirements.

```bash
TTS_BACKEND=vllm_omni \
TTS_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice \
TTS_WARMUP_ON_START=true \
python -m api.main
```

See `docs/vllm-backend.md` and `VLLM_BACKEND_STATUS.md` for backend-specific constraints.

### CPU backend

The default CPU checkpoint is the smaller 0.6B **CustomVoice** model, which supports normal preset-speaker TTS.

```bash
export TTS_BACKEND=pytorch
export TTS_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
export TTS_DEVICE=cpu
export TTS_DTYPE=float32
export TTS_ATTN=sdpa
export CPU_THREADS=12
export CPU_INTEROP=2
python -m api.main
```

A Base checkpoint is valid for `/v1/audio/voice-clone`, but it cannot serve preset-speaker `/v1/audio/speech` calls.

## Voice cloning

Run a Base checkpoint:

```bash
TTS_BACKEND=official \
TTS_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-1.7B-Base \
python -m api.main
```

Then send base64-encoded reference audio:

```python
import base64
import requests

with open("reference.wav", "rb") as file:
    reference = base64.b64encode(file.read()).decode("ascii")

response = requests.post(
    "http://localhost:8880/v1/audio/voice-clone",
    json={
        "input": "This sentence uses the reference speaker.",
        "ref_audio": reference,
        "ref_text": "The exact transcript spoken in reference.wav.",
        "x_vector_only_mode": False,
        "language": "English",
        "response_format": "wav",
        "speed": 1.0,
    },
    timeout=300,
)
response.raise_for_status()
open("clone.wav", "wb").write(response.content)
```

Modes:

- ICL: `x_vector_only_mode=false`; requires an accurate `ref_text`
- X-vector: `x_vector_only_mode=true`; transcript optional, usually lower fidelity

Only clone voices you have permission to use. Do not use the service to impersonate people deceptively.

## Voice library

Saved profiles are discovered under:

```text
$VOICE_LIBRARY_DIR/profiles/
└── alice/
    ├── meta.json
    └── reference.wav
```

Example `meta.json`:

```json
{
  "name": "Alice",
  "profile_id": "alice",
  "ref_audio_filename": "reference.wav",
  "ref_text": "Transcript of the reference clip.",
  "x_vector_only_mode": false,
  "language": "English"
}
```

Use the profile through the normal OpenAI endpoint:

```python
response = client.audio.speech.create(
    model="tts-1",
    voice="clone:Alice",
    input="This uses the saved Alice profile.",
    response_format="wav",
)
response.stream_to_file("alice.wav")
```

The active backend/checkpoint must support voice cloning. See `docs/voice-library.md` for details.

## Apple Silicon / MLX

Use a dedicated virtual environment because `mlx-audio` can require a different Transformers version from the official backend stack.

```bash
brew install python@3.12 ffmpeg
python3.12 -m venv .venv-mlx
source .venv-mlx/bin/activate
pip install --upgrade pip
pip install -e ".[api,mlx]"

TTS_BACKEND=mlx \
MLX_MODEL_ID=mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit \
python -m api.main
```

The included launcher manages isolated 0.6B and 1.7B MLX instances:

```bash
./run_tts.sh          # 1.7B HQ on port 18882
./run_tts.sh fast     # 0.6B on port 18881
./run_tts.sh both
./run_tts.sh status
./run_tts.sh stop
```

## Docker

### NVIDIA GPU

```bash
docker compose up --build qwen3-tts-gpu
```

Override the host port or model without editing Compose:

```bash
TTS_PORT=9000 \
TTS_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice \
docker compose up --build qwen3-tts-gpu
```

The Compose file requests one GPU instead of hard-coding a host GPU index.

### vLLM

```bash
docker compose --profile vllm up --build qwen3-tts-vllm
```

### CPU

```bash
CPU_THREADS=12 docker compose --profile cpu up --build qwen3-tts-cpu
```

### AMD ROCm

```bash
docker compose -f docker-compose.rocm.yml up --build qwen3-tts-rocm
```

Review device mappings in `docker-compose.rocm.yml`; render-node names vary between hosts.

## Configuration reference

| Variable | Default | Purpose |
|---|---:|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8880` | Listen port |
| `WORKERS` | `1` | Uvicorn worker processes; each process loads its own model |
| `TTS_BACKEND` | `official` | Backend selector |
| `TTS_MODEL_NAME` / `TTS_MODEL_ID` | backend-specific | Hugging Face ID or local model path |
| `TTS_LAZY_LOAD` | `true` | Load on first synthesis request |
| `TTS_WARMUP_ON_START` | `false` | Warm regular and supported streaming paths |
| `TTS_WARMUP_MAX_SECONDS` | `10` | Timeout per warmup request |
| `TTS_MAX_CONCURRENT` | `1` | Concurrent generation limit per process |
| `TTS_IDLE_TIMEOUT_SECONDS` | `0` | Opt-in idle shutdown; `0` disables it |
| `CORS_ORIGINS` | `*` | Comma-separated allowed browser origins |
| `ENABLE_VOICE_STUDIO` | `false` | Mount Gradio at `/voice-studio` |
| `VOICE_LIBRARY_DIR` | `./voice_library` | Saved profile root |
| `TTS_CUSTOM_VOICES` | `./custom_voices` | Legacy/custom voice directory |
| `TTS_CONFIG` | `~/qwen3-tts/config.yaml` | Optimized-backend YAML |
| `GPU_KEEPALIVE_INTERVAL` | `0` | Optional GPU keepalive interval in seconds |
| `TTS_AUTOCHUNK` | `true` | Enable punctuation-aware input splitting |
| `TTS_MIN_CHUNK_CHARS` | `20` | Soft minimum chunk length |
| `TTS_MAX_CHUNK_CHARS` | `70` | Target maximum chunk length |
| `TTS_CHUNK_GAP_MS` | `120` | Silence inserted between generated chunks |
| `CPU_THREADS` | `12` | PyTorch CPU thread count |
| `CPU_INTEROP` | `2` | PyTorch inter-op thread count |
| `USE_IPEX` | `false` | Attempt Intel Extension for PyTorch |
| `MLX_MODEL_ID` | 0.6B CustomVoice 8-bit | MLX checkpoint |

Invalid integer settings fall back to safe defaults instead of crashing module import.

## CORS and network exposure

`CORS_ORIGINS=*` is convenient for local development. For a service exposed beyond localhost, set explicit origins:

```bash
CORS_ORIGINS=https://app.example.com,https://admin.example.com python -m api.main
```

The server does not implement authentication. Put it behind an authenticated reverse proxy or private network before exposing it to the internet. Keep `WORKERS=1` on a single GPU unless you intentionally have enough VRAM for one full model per worker.

## Development and tests

```bash
pip install -e ".[api,dev]"
pytest -q
```

The regression suite covers URL normalization, currency/unit interactions, PCM/WAV correctness, truthful compressed-encoding failures, invalid environment values, and concurrent cold-start initialization.

## Troubleshooting

### Compressed output fails

Install FFmpeg and confirm the codec is available:

```bash
ffmpeg -version
ffmpeg -encoders | grep -E 'mp3|opus|aac|flac'
```

Use `response_format="wav"` while diagnosing. The API now reports an encoding error rather than silently returning a different format.

### Base model rejects a normal speech request

Base checkpoints clone reference voices. Switch to a `*-CustomVoice` checkpoint for preset speakers, or use `/v1/audio/voice-clone`.

### First request is slow

Model download, load, compilation, and graph capture can make the first request much slower. Use:

```bash
TTS_LAZY_LOAD=false TTS_WARMUP_ON_START=true python -m api.main
```

### Out of memory

- Use the 0.6B checkpoint
- Keep `WORKERS=1`
- Keep `TTS_MAX_CONCURRENT=1`
- Stop other GPU workloads
- Avoid running both MLX launch profiles when unified memory is constrained

### Server exits while idle

Idle shutdown is disabled by default. Check that your environment does not set a positive `TTS_IDLE_TIMEOUT_SECONDS`.

## Project layout

```text
api/
├── backends/                 Backend implementations and factory
├── routers/                  OpenAI-compatible endpoints
├── services/                 Text normalization and audio encoding
├── static/                   Browser UI
└── structures/               Pydantic request/response schemas
config.yaml                   Optimized-backend model/performance config
docker-compose.yml            NVIDIA and CPU services
docker-compose.rocm.yml       AMD ROCm service
gradio_voice_studio.py        Voice Studio
run_tts.sh                    Isolated MLX launch helper
tests/                        Regression and API tests
```

## Upstream and license

Qwen3-TTS is developed by the Alibaba Qwen team. This repository's API and deployment additions retain the Apache-2.0 license. Review the upstream model cards and licenses for every checkpoint you deploy.
