$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

# GPT-SoVITS is a separate clone that this repository does not vendor, so accept
# an explicit GPT_SOVITS_ROOT first and fall back to the known checkout layouts.
function Resolve-GptSovitsRoot([string]$ProjectRoot) {
  $clone = $null
  $candidates = @(
    $env:GPT_SOVITS_ROOT,
    (Join-Path $ProjectRoot 'external\GPT-SoVITS'),
    (Join-Path (Split-Path -Parent $ProjectRoot) 'external\GPT-SoVITS'),
    'C:\Projects\airi\external\GPT-SoVITS'
  )
  foreach ($candidate in $candidates) {
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    if (-not (Test-Path -LiteralPath (Join-Path $candidate 'api_v2.py'))) { continue }
    if (Test-Path -LiteralPath (Join-Path $candidate '.venv\Scripts\python.exe')) { return $candidate }
    if (-not $clone) { $clone = $candidate }
  }
  if ($clone) { throw "GPT-SoVITS at $clone has no virtual environment at .venv\Scripts\python.exe" }
  throw 'GPT-SoVITS was not found. Clone GPT-SoVITS and set GPT_SOVITS_ROOT to the clone directory'
}

$python = Join-Path (Resolve-GptSovitsRoot $projectRoot) '.venv\Scripts\python.exe'

$env:PYTHONIOENCODING = 'utf-8'
$env:TEST_AIRI_SPEECH_URL = 'http://127.0.0.1:8880/v1/audio/speech'
$env:TEST_AIRI_SPEECH_OUTPUT = Join-Path $PSScriptRoot 'airi-speech-self-test.wav'
& $python -c @'
import math, os, struct, time
from array import array
from pathlib import Path
import requests

url = os.environ['TEST_AIRI_SPEECH_URL']
output = Path(os.environ['TEST_AIRI_SPEECH_OUTPUT'])
payload = {
    'model': 'tts-1-ko',
    # Keep this source ASCII-safe while exercising the mixed English/Korean path.
    'input': 'Hello \uc544\uc774\ub9ac, \uc74c\uc131 \uc5f0\uacb0 \ud14c\uc2a4\ud2b8\uc57c.',
    'voice': 'airi-vtuber',
    'response_format': 'wav',
    'speed': 1.0,
}
started = time.perf_counter()
response = requests.post(url, json=payload, stream=True, timeout=180)
response.raise_for_status()
first = None
chunks = total = 0
with output.open('wb') as stream:
    for chunk in response.iter_content(4096):
        if first is None:
            first = time.perf_counter()
        stream.write(chunk)
        chunks += 1
        total += len(chunk)
finished = time.perf_counter()

data = output.read_bytes()
if len(data) < 44 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
    raise RuntimeError('speech response is not a WAV file')

fmt_offset = data.find(b'fmt ')
data_offset = data.find(b'data')
if fmt_offset < 0 or data_offset < 0:
    raise RuntimeError('speech response is missing a WAV fmt or data chunk')

audio_format, channels, sample_rate = struct.unpack_from('<HHI', data, fmt_offset + 8)
bits_per_sample = struct.unpack_from('<H', data, fmt_offset + 22)[0]
if audio_format != 1 or bits_per_sample != 16 or channels < 1 or sample_rate < 8000:
    raise RuntimeError(
        f'unsupported WAV format: format={audio_format} channels={channels} '
        f'sample_rate={sample_rate} bits={bits_per_sample}'
    )

# GPT-SoVITS streams a placeholder data length, so validate all bytes after the data header.
pcm = data[data_offset + 8:]
pcm = pcm[:len(pcm) - (len(pcm) % 2)]
samples = array('h')
samples.frombytes(pcm)
if not samples:
    raise RuntimeError('speech response contains no PCM samples')

rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768.0
peak = max(abs(sample) for sample in samples) / 32768.0
duration = len(samples) / (sample_rate * channels)
if duration < 0.25:
    raise RuntimeError(f'speech response is too short: {duration:.3f}s')
if rms < 0.005 or peak < 0.02:
    raise RuntimeError(f'speech response is effectively silent: rms={rms:.6f} peak={peak:.6f}')

print(f'url={url}')
print(f'status={response.status_code}')
print(f'first_chunk_ms={(first-started)*1000:.1f}')
print(f'total_ms={(finished-started)*1000:.1f}')
print(f'bytes={total} chunks={chunks}')
print(f'duration_s={duration:.3f} sample_rate={sample_rate} channels={channels}')
print(f'rms={rms:.6f} peak={peak:.6f}')
print(f'output={output}')
'@
