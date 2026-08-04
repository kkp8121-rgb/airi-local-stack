$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$server = Join-Path $repo 'examples\openai_server.py'
$stdoutLog = Join-Path $repo 'tts-server.out.log'
$stderrLog = Join-Path $repo 'tts-server.err.log'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

$listener = Get-NetTCPConnection -LocalPort 8880 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output "Qwen3-TTS is already listening on port 8880 (PID $($listener.OwningProcess))."
    exit 0
}

$env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $server, '--model', 'Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', '--language', 'Korean', '--host', '127.0.0.1', '--port', '8880', '--device', 'cuda' `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output "Started faster Qwen3-TTS (PID $($process.Id)) on http://127.0.0.1:8880."
