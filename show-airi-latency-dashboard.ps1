$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'latency-monitor\start-latency-monitor.ps1')
$deadline = (Get-Date).AddSeconds(15)
do {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8892/health' -TimeoutSec 2
        if ($health.status -eq 'ok') { break }
    }
    catch {
        Start-Sleep -Milliseconds 250
    }
} while ((Get-Date) -lt $deadline)

if ($health.status -ne 'ok') {
    throw 'AIRI latency monitor did not become ready on port 8892.'
}

Start-Process 'http://127.0.0.1:8892/'
