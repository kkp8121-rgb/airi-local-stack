$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'external\GPT-SoVITS\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "GPT-SoVITS environment not found: $python" }

$env:PYTHONIOENCODING = 'utf-8'
$env:TEST_AIRI_SPEECH_URL = 'http://127.0.0.1:8880/v1/audio/speech'
$env:TEST_AIRI_SPEECH_OUTPUT = Join-Path $PSScriptRoot 'airi-speech-self-test.wav'
& $python -c @'
import os, time
from pathlib import Path
import requests

url = os.environ['TEST_AIRI_SPEECH_URL']
output = Path(os.environ['TEST_AIRI_SPEECH_OUTPUT'])
payload = {
    'model': 'tts-1-ko',
    'input': '아이리, 음성 연결 테스트야.',
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
print(f'url={url}')
print(f'status={response.status_code}')
print(f'first_chunk_ms={(first-started)*1000:.1f}')
print(f'total_ms={(finished-started)*1000:.1f}')
print(f'bytes={total} chunks={chunks}')
print(f'output={output}')
'@
