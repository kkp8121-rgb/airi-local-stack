param(
  [switch]$SkipWarmup,
  [ValidateSet('on', 'off')]
  [string]$ReferenceEmbeddingCache = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_GPT_SOVITS_SV_CACHE)) { 'off' } else { $env:AIRI_GPT_SOVITS_SV_CACHE })
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$ReferenceEmbeddingCache = $ReferenceEmbeddingCache.ToLowerInvariant()

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
  # Separate the two failure modes: a missing clone and a clone without a venv
  # need completely different fixes.
  if ($clone) { throw "GPT-SoVITS at $clone has no virtual environment at .venv\Scripts\python.exe" }
  throw 'GPT-SoVITS was not found. Clone GPT-SoVITS and set GPT_SOVITS_ROOT to the clone directory'
}

$gptRoot = Resolve-GptSovitsRoot $projectRoot
$python = Join-Path $gptRoot '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path (Join-Path $gptRoot 'GPT_SoVITS\pretrained_models\fast_langdetect') | Out-Null

# A clean worktree may intentionally reuse the approved reference voice from
# the stable checkout. Honour an explicit absolute override before falling
# back to the voice stored beside this launcher.
$referenceAudio = if (-not [string]::IsNullOrWhiteSpace($env:GPT_SOVITS_REFERENCE_AUDIO)) {
  [System.IO.Path]::GetFullPath($env:GPT_SOVITS_REFERENCE_AUDIO)
}
else {
  Join-Path $projectRoot 'chatterbox\voices\airi-reference.wav'
}
$env:GPT_SOVITS_REFERENCE_AUDIO = $referenceAudio
if (-not (Test-Path -LiteralPath $referenceAudio)) {
  Write-Warning "AIRI reference voice not found: $referenceAudio - speech synthesis fails until this file exists"
}

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

function Wait-ImmediateResponseCache {
  param(
    [string]$Uri = 'http://127.0.0.1:8880/health',
    [int]$TimeoutSeconds = 240
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  $lastObservation = 'health endpoint has not responded'
  do {
    try {
      $health = Invoke-RestMethod -Uri $Uri -Method Get -TimeoutSec 3 -ErrorAction Stop
      $cache = $health.immediate_response_cache
      $total = [int]$cache.total
      $ready = [int]$cache.ready
      $lastObservation = "ready=$ready total=$total"
      # A zero-sized cache is not a ready cache: it can otherwise make an
      # empty or malformed health response pass the startup gate.
      if ($total -gt 0 -and $ready -eq $total) {
        return $health
      }
    }
    catch {
      $lastObservation = "health request failed: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)

  throw "Speech proxy acknowledgement cache did not become ready within $TimeoutSeconds seconds ($lastObservation)"
}

if (-not (Test-Port 11434)) {
  $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
  if (-not $ollama) { throw 'ollama.exe was not found in PATH' }
  Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
  Start-Sleep -Seconds 2
}

$startedBackend = $false
if ((Test-Port 9880) -and $ReferenceEmbeddingCache -eq 'on') {
  throw 'ReferenceEmbeddingCache on requires a fresh 9880 backend; an existing backend cannot attest the overlay.'
}
if (-not (Test-Port 9880)) {
  $env:PYTHONPATH = "$gptRoot;$gptRoot\GPT_SoVITS"
  $env:PYTHONIOENCODING = 'utf-8'
  $out = Join-Path $PSScriptRoot 'api-v2proplus.out.log'
  $err = Join-Path $PSScriptRoot 'api-v2proplus.err.log'
  $backendArguments = if ($ReferenceEmbeddingCache -eq 'on') {
    @(
      '-u', (Join-Path $PSScriptRoot 'run_v2proplus_with_sv_cache.py'),
      '--external-root', $gptRoot, '--', '-a', '127.0.0.1', '-p', '9880',
      '-c', (Join-Path $PSScriptRoot 'tts-infer-v2proplus.yaml')
    )
  }
  else {
    @('-u', 'api_v2.py', '-a', '127.0.0.1', '-p', '9880', '-c', (Join-Path $PSScriptRoot 'tts-infer-v2proplus.yaml'))
  }
  Start-Process -FilePath $python -ArgumentList $backendArguments -WorkingDirectory $gptRoot -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
  $startedBackend = $true
}

# The speech proxy pre-generates fixed acknowledgement WAVs on a background
# thread. Wait until GPT-SoVITS can accept those requests before starting it.
Wait-Port 9880 120

if (-not (Test-Port 8880)) {
  $out = Join-Path $PSScriptRoot 'proxy.out.log'
  $err = Join-Path $PSScriptRoot 'proxy.err.log'
  Start-Process -FilePath $python -ArgumentList '-u',(Join-Path $PSScriptRoot 'openai_compatible_proxy.py'),'--host','127.0.0.1','--port','8880' -WorkingDirectory $projectRoot -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
}

Wait-Port 11434 10
# Do this even when 8880 was already occupied.  The proxy binds before its
# acknowledgement cache is generated, so a listening port alone is not ready.
$speechHealth = Wait-ImmediateResponseCache -TimeoutSeconds 240
Write-Output "Speech proxy acknowledgement cache is ready: $($speechHealth.immediate_response_cache.ready)/$($speechHealth.immediate_response_cache.total)"

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
