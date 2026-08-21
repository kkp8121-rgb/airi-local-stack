$ErrorActionPreference = 'Stop'

$extractorRuntimeDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'ollama-proxy\runtime'))
$extractorOwnerPath = [IO.Path]::GetFullPath((Join-Path $extractorRuntimeDir 'memory-extractor-owner.json'))
if (-not $extractorOwnerPath.StartsWith($extractorRuntimeDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Memory extractor owner record path must stay under the repository runtime directory.'
}
if (Test-Path -LiteralPath $extractorOwnerPath -PathType Leaf) {
    try {
        $owner = Get-Content -LiteralPath $extractorOwnerPath -Raw -Encoding utf8 | ConvertFrom-Json -ErrorAction Stop
        $ownerPort = 0
        $ownerPid = 0
        if (-not [int]::TryParse([string]$owner.port, [ref]$ownerPort) -or $ownerPort -lt 1024 -or $ownerPort -gt 65535 -or
                -not [int]::TryParse([string]$owner.pid, [ref]$ownerPid) -or $ownerPid -le 0) {
            throw 'owner record has an invalid port or PID'
        }
        # The helper verifies the loopback listener and exact PID before it
        # stops anything.  Never fall back to a broad port or process kill.
        & (Join-Path $PSScriptRoot 'ollama-proxy\stop-memory-extractor.ps1') -Port $ownerPort -ExpectedPid $ownerPid
        Remove-Item -LiteralPath $extractorOwnerPath -Force -ErrorAction Stop
    }
    catch {
        Write-Warning ("Memory extractor owner record was retained: " + $_.Exception.Message)
    }
}

& (Join-Path $PSScriptRoot 'stt\stop-local-stt.ps1')
& (Join-Path $PSScriptRoot 'gpt-sovits\stop-local-stack.ps1')
& (Join-Path $PSScriptRoot 'ollama-proxy\stop-local-ollama-proxy.ps1')
& (Join-Path $PSScriptRoot 'latency-monitor\stop-latency-monitor.ps1')

Write-Output 'Stopped AIRI local STT, GPT-SoVITS TTS, Ollama proxy, and latency monitor services.'
Write-Output 'Ollama and the AIRI desktop app were left running.'
