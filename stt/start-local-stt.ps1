param(
    [string]$Model = 'base',
    [ValidateRange(1, 32)]
    [int]$CpuThreads = 6
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

$listener = Get-NetTCPConnection -LocalPort 8890 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output "A service is already listening on port 8890 (PID $($listener.OwningProcess))."
    exit 0
}

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $server, '--host', '127.0.0.1', '--port', '8890', '--model', $Model, '--model-root', $modelRoot, '--cpu-threads', $CpuThreads `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output "Started AIRI local STT server (PID $($process.Id))."
