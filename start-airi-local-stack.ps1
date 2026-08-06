param(
    [string]$SttModel = 'small',
    [ValidateRange(1, 32)]
    [int]$SttCpuThreads = 6
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

Write-Output 'Starting Ollama, GPT-SoVITS, and AIRI speech proxy...'
& powershell -ExecutionPolicy Bypass -File (Join-Path $root 'gpt-sovits\start-local-stack.ps1')
if ($LASTEXITCODE -ne 0) { throw "LLM/TTS stack startup failed with exit code $LASTEXITCODE" }

Write-Output 'Starting local faster-whisper STT (debug audio persistence remains disabled)...'
& powershell -ExecutionPolicy Bypass -File (Join-Path $root 'stt\start-local-stt.ps1') -Model $SttModel -CpuThreads $SttCpuThreads
if ($LASTEXITCODE -ne 0) { throw "STT startup failed with exit code $LASTEXITCODE" }

$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8890/health' -TimeoutSec 5
if ($health.status -ne 'ok') { throw "STT health is $($health.status)" }

Write-Output 'AIRI local stack is ready:'
Write-Output '  STT:       http://127.0.0.1:8890'
Write-Output '  LLM:       http://127.0.0.1:11434'
Write-Output '  GPT API:   http://127.0.0.1:9880'
Write-Output '  AIRI TTS:  http://127.0.0.1:8880/v1'
Write-Output '  Debug audio persistence: disabled (use stt/start-local-stt.ps1 -EnableDebugAudio only for intentional debugging)'
