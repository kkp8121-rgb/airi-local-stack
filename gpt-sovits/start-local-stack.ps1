param(
  [switch]$SkipWarmup
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$gptRoot = Join-Path $projectRoot 'external\GPT-SoVITS'
$python = Join-Path $gptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "GPT-SoVITS environment not found: $python" }
New-Item -ItemType Directory -Force -Path (Join-Path $gptRoot 'GPT_SoVITS\pretrained_models\fast_langdetect') | Out-Null

# GPT-SoVITS imports its English frontend lazily after the streaming response
# has started. Missing data therefore looks like HTTP 200 followed by a broken
# or one-syllable stream, so verify the complete mixed-language runtime here.
$wordsegment = & $python -c "import importlib.util; print('ok' if importlib.util.find_spec('wordsegment') else 'missing')"
if ($LASTEXITCODE -ne 0) { throw 'Failed to inspect the GPT-SoVITS Python environment' }
if (($wordsegment | Select-Object -Last 1).Trim() -ne 'ok') {
  & $python -m pip install wordsegment
  if ($LASTEXITCODE -ne 0) { throw 'Failed to install the GPT-SoVITS wordsegment dependency' }
}

$nltkData = Join-Path $gptRoot '.venv\nltk_data'
& $python -c "import nltk; nltk.data.path.insert(0, r'$nltkData'); nltk.data.find('taggers/averaged_perceptron_tagger_eng')"
if ($LASTEXITCODE -ne 0) {
  & $python -m nltk.downloader -d $nltkData averaged_perceptron_tagger_eng
  if ($LASTEXITCODE -ne 0) { throw 'Failed to install the GPT-SoVITS English POS tagger data' }
}
$env:NLTK_DATA = $nltkData

function Test-Port([int]$Port) {
  return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Wait-Port([int]$Port, [int]$TimeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    if (Test-Port $Port) { return }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  throw "Local stack timed out waiting for port $Port after $TimeoutSeconds seconds"
}

if (-not (Test-Port 11434)) {
  $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
  if (-not $ollama) { throw 'ollama.exe was not found in PATH' }
  Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
  Start-Sleep -Seconds 2
}

$startedBackend = $false
if (-not (Test-Port 9880)) {
  $env:PYTHONPATH = "$gptRoot;$gptRoot\GPT_SoVITS"
  $env:PYTHONIOENCODING = 'utf-8'
  $out = Join-Path $PSScriptRoot 'api-v2proplus.out.log'
  $err = Join-Path $PSScriptRoot 'api-v2proplus.err.log'
  Start-Process -FilePath $python -ArgumentList '-u','api_v2.py','-a','127.0.0.1','-p','9880','-c',(Join-Path $PSScriptRoot 'tts-infer-v2proplus.yaml') -WorkingDirectory $gptRoot -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
  $startedBackend = $true
}

# The speech proxy pre-generates fixed acknowledgement WAVs during startup.
# Wait until GPT-SoVITS can accept those requests before starting the proxy.
Wait-Port 9880 120

if (-not (Test-Port 8880)) {
  $out = Join-Path $PSScriptRoot 'proxy.out.log'
  $err = Join-Path $PSScriptRoot 'proxy.err.log'
  Start-Process -FilePath $python -ArgumentList '-u',(Join-Path $PSScriptRoot 'openai_compatible_proxy.py'),'--host','127.0.0.1','--port','8880' -WorkingDirectory $projectRoot -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
}

Wait-Port 11434 10
Wait-Port 8880 30

if ($startedBackend -and -not $SkipWarmup) {
  $previousProgressPreference = $ProgressPreference
  $ProgressPreference = 'SilentlyContinue'
  try {
    $warmupBody = @{
      model = 'tts-1-ko'
      voice = 'airi-vtuber'
      input = 'Airi is ready.'
      response_format = 'wav'
    } | ConvertTo-Json -Compress
    $warmup = Invoke-WebRequest `
      -Uri 'http://127.0.0.1:8880/v1/audio/speech' `
      -Method Post `
      -ContentType 'application/json; charset=utf-8' `
      -Body $warmupBody `
      -UseBasicParsing `
      -TimeoutSec 180
    if ($warmup.RawContentLength -lt 44) {
      throw "GPT-SoVITS warmup returned only $($warmup.RawContentLength) bytes"
    }
    Write-Output "GPT-SoVITS warmup completed: $($warmup.RawContentLength) bytes"
  }
  finally {
    $ProgressPreference = $previousProgressPreference
  }
}

$ports = 11434, 9880, 8880 | ForEach-Object { [pscustomobject]@{ Port = $_; Listening = Test-Port $_ } }
$ports | Format-Table -AutoSize
if (@($ports | Where-Object { -not $_.Listening }).Count -gt 0) {
  $missing = ($ports | Where-Object { -not $_.Listening } | ForEach-Object Port) -join ', '
  throw "Local stack failed to open port(s): $missing"
}
Write-Output 'AIRI OpenAI Compatible Speech Base URL: http://127.0.0.1:8880/v1'
