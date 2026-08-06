param(
    [string]$Model = 'small',
    [ValidateRange(1, 32)]
    [int]$CpuThreads = 6,
    [switch]$EnableDebugAudio
)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$server = Join-Path $repo 'openai_stt_server.py'
$modelRoot = Join-Path $repo 'models'
$stdoutLog = Join-Path $repo 'stt-server.out.log'
$stderrLog = Join-Path $repo 'stt-server.err.log'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8890 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output "A service is already listening on port 8890 (PID $($listener.OwningProcess))."
    exit 0
}

$serverArguments = @($server, '--host', '127.0.0.1', '--port', '8890', '--model', $Model, '--model-root', $modelRoot, '--cpu-threads', $CpuThreads)
if ($EnableDebugAudio) {
    $debugAudioRoot = Join-Path $repo 'debug-recordings'
    $serverArguments += @('--debug-audio-dir', $debugAudioRoot)
    Write-Warning 'Debug audio persistence is enabled. Uploaded microphone audio will be saved locally.'
}

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $serverArguments `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output "Started AIRI local STT server (PID $($process.Id))."

$ready = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8890/health' -TimeoutSec 2
        if ($health.status -eq 'ok') {
            $ready = $true
            Write-Output "AIRI local STT ready (model=$($health.model), device=$($health.device), threads=$($health.cpu_threads))."
            break
        }
    } catch {
        # The model may still be loading; keep polling until the bounded timeout.
    }
}
if (-not $ready) {
    throw 'AIRI local STT did not become ready within 60 seconds. Check stt-server.err.log.'
}
