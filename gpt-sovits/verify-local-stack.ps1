param(
  [switch]$SkipSpeech
)

$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8880'
$root = Split-Path -Parent $PSScriptRoot
$speechTest = Join-Path $PSScriptRoot 'test-airi-speech.ps1'

function Assert-Listening([int]$Port) {
  $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if (-not $connection) { throw "Port $Port is not listening" }
  Write-Output "port=$Port pid=$($connection.OwningProcess)"
}

Assert-Listening 11434
Assert-Listening 11435
Assert-Listening 9880
Assert-Listening 8880

$health = Invoke-RestMethod -Uri "$base/health" -Method Get -TimeoutSec 5
if ($health.status -ne 'ok') { throw "speech proxy health is $($health.status)" }
Write-Output "speech_health=ok engine=$($health.engine)"

$llmHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/health' -Method Get -TimeoutSec 5
if ($llmHealth.status -ne 'ok') { throw "Ollama compatibility proxy health is $($llmHealth.status)" }
Write-Output "llm_proxy_health=ok num_ctx=$($llmHealth.num_ctx)"

$models = Invoke-RestMethod -Uri "$base/v1/models" -Method Get -TimeoutSec 5
$model = @($models.data | Where-Object { $_.id -eq 'tts-1-ko' })
if ($model.Count -ne 1) { throw 'tts-1-ko was not advertised by the speech proxy' }
Write-Output 'model=tts-1-ko'

if (-not $SkipSpeech) {
  & powershell -ExecutionPolicy Bypass -File $speechTest
  if ($LASTEXITCODE -ne 0) { throw "speech contract test failed with exit code $LASTEXITCODE" }
}

Write-Output 'stack_verification=passed'
