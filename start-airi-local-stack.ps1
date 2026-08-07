$ErrorActionPreference = 'Stop'

function Wait-LocalHealth {
    param(
        [Parameter(Mandatory)]
        [string]$Uri,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            return Invoke-RestMethod -Uri $Uri -TimeoutSec 3
        }
        catch {
            Start-Sleep -Seconds 1
        }
    } while ((Get-Date) -lt $deadline)

    throw "Local service did not become ready within $TimeoutSeconds seconds: $Uri"
}

$ollamaListener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if (-not $ollamaListener) {
    $ollama = Get-Command ollama -ErrorAction Stop
    Start-Process `
        -FilePath $ollama.Source `
        -ArgumentList 'serve' `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $PSScriptRoot 'ollama-proxy\ollama-serve.out.log') `
        -RedirectStandardError (Join-Path $PSScriptRoot 'ollama-proxy\ollama-serve.err.log')
}

& (Join-Path $PSScriptRoot 'latency-monitor\start-latency-monitor.ps1')
$latencyMonitor = Wait-LocalHealth -Uri 'http://127.0.0.1:8892/health' -TimeoutSeconds 15

& (Join-Path $PSScriptRoot 'ollama-proxy\start-local-ollama-proxy.ps1')
& (Join-Path $PSScriptRoot 'gpt-sovits\start-local-stack.ps1')
& (Join-Path $PSScriptRoot 'stt\start-local-stt.ps1')

$proxy = Wait-LocalHealth -Uri 'http://127.0.0.1:11435/health'
$tts = Wait-LocalHealth -Uri 'http://127.0.0.1:8880/health'
$stt = Wait-LocalHealth -Uri 'http://127.0.0.1:8890/health'

# Load Ollama's model before the first user turn. Without this request, an
# unloaded model adds roughly four seconds to the next reply on this PC.
$warmupJson = @{
    model = 'exaone-airi:2.4b'
    stream = $false
    messages = @(@{ role = 'user'; content = '준비 확인.' })
} | ConvertTo-Json -Depth 5 -Compress
$warmupBytes = [Text.Encoding]::UTF8.GetBytes($warmupJson)
$previousProgressPreference = $ProgressPreference
$ProgressPreference = 'SilentlyContinue'
try {
    $warmup = Invoke-WebRequest `
        -Uri 'http://127.0.0.1:11435/v1/chat/completions' `
        -Method Post `
        -ContentType 'application/json; charset=utf-8' `
        -Body $warmupBytes `
        -UseBasicParsing `
        -TimeoutSec 120
}
finally {
    $ProgressPreference = $previousProgressPreference
}

[pscustomobject]@{
    LatencyMonitor = $latencyMonitor.status
    LatencyDashboard = 'http://127.0.0.1:8892/'
    OllamaProxy = $proxy.status
    LLMWarmup = $warmup.StatusCode
    NumCtx = $proxy.num_ctx
    TTS = $tts.status
    TTSEngine = $tts.engine
    VoiceReferenceFound = $tts.reference_audio_found
    STT = $stt.status
    STTModel = $stt.model
    STTDevice = $stt.device
}
