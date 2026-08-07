param([int]$Port = 8880)
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

$gptRoot = Resolve-GptSovitsRoot $projectRoot
$python = Join-Path $gptRoot '.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:GPT_SOVITS_TTS_URL = 'http://127.0.0.1:9880/tts'
$env:GPT_SOVITS_REFERENCE_AUDIO = (Join-Path $projectRoot 'chatterbox\voices\airi-reference.wav')
$env:PYTHONPATH = $gptRoot
& $python (Join-Path $PSScriptRoot 'openai_compatible_proxy.py') --host 127.0.0.1 --port $Port
