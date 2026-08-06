param(
    [ValidateRange(512, 32768)]
    [int]$NumCtx = 2048
)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$python = Join-Path $repo '..\chatterbox\.venv\Scripts\python.exe'
$server = Join-Path $repo 'ollama_proxy.py'
$stdoutLog = Join-Path $repo 'ollama-proxy.out.log'
$stderrLog = Join-Path $repo 'ollama-proxy.err.log'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output "A service is already listening on port 11435 (PID $($listener.OwningProcess))."
    exit 0
}

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $server, '--host', '127.0.0.1', '--port', '11435', '--upstream', 'http://127.0.0.1:11434', '--num-ctx', $NumCtx `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output "Started AIRI Ollama compatibility proxy (PID $($process.Id))."
