$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'external\GPT-SoVITS\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  throw "GPT-SoVITS Python environment not found: $python"
}
$env:PYTHONIOENCODING = 'utf-8'
$env:GPT_SOVITS_TTS_URL = 'http://127.0.0.1:9880/tts'
$env:GPT_SOVITS_REFERENCE_AUDIO = (Join-Path $projectRoot 'chatterbox\voices\airi-reference.wav')
$env:PYTHONPATH = (Join-Path $projectRoot 'external\GPT-SoVITS')
& $python (Join-Path $PSScriptRoot 'openai_compatible_proxy.py') --host 127.0.0.1 --port 8891
