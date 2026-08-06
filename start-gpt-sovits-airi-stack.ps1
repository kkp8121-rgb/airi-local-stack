param(
    [string]$SttModel = 'small',
    [ValidateRange(1, 32)]
    [int]$SttCpuThreads = 6
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

& powershell -ExecutionPolicy Bypass -File (Join-Path $root 'gpt-sovits\start-local-stack.ps1')
if ($LASTEXITCODE -ne 0) { throw "LLM/TTS stack startup failed with exit code $LASTEXITCODE" }

& powershell -ExecutionPolicy Bypass -File (Join-Path $root 'ollama-proxy\start-local-ollama-proxy.ps1')
if ($LASTEXITCODE -ne 0) { throw "Ollama compatibility proxy startup failed with exit code $LASTEXITCODE" }

& powershell -ExecutionPolicy Bypass -File (Join-Path $root 'stt\start-local-stt.ps1') -Model $SttModel -CpuThreads $SttCpuThreads
if ($LASTEXITCODE -ne 0) { throw "STT startup failed with exit code $LASTEXITCODE" }

$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8890/health' -TimeoutSec 5
if ($health.status -ne 'ok') { throw "STT health is $($health.status)" }
$llmHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/health' -TimeoutSec 5
if ($llmHealth.status -ne 'ok') { throw "Ollama compatibility proxy health is $($llmHealth.status)" }

Write-Output 'AIRI GPT-SoVITS local stack is ready:'
Write-Output '  STT:      http://127.0.0.1:8890'
Write-Output '  Ollama:   http://127.0.0.1:11434'
Write-Output '  LLM API:  http://127.0.0.1:11435'
Write-Output '  GPT API:  http://127.0.0.1:9880'
Write-Output '  AIRI TTS: http://127.0.0.1:8880/v1'
Write-Output '  Debug audio persistence: disabled by default'
