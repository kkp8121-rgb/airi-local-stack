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

& (Join-Path $PSScriptRoot 'ollama-proxy\start-local-ollama-proxy.ps1')
& (Join-Path $PSScriptRoot 'chatterbox\start-local-tts.ps1')
& (Join-Path $PSScriptRoot 'stt\start-local-stt.ps1')

$proxy = Wait-LocalHealth -Uri 'http://127.0.0.1:11435/health'
$tts = Wait-LocalHealth -Uri 'http://127.0.0.1:8880/health'
$stt = Wait-LocalHealth -Uri 'http://127.0.0.1:8890/health'

[pscustomobject]@{
    OllamaProxy = $proxy.status
    NumCtx = $proxy.num_ctx
    TTS = $tts.status
    VoiceReference = $tts.reference_audio
    STT = $stt.status
    STTModel = $stt.model
    STTDevice = $stt.device
}
