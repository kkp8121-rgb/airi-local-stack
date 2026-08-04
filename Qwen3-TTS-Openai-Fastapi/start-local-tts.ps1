$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
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
$env:HOST = '127.0.0.1'
$env:PORT = '8880'
$env:WORKERS = '1'
$env:TTS_BACKEND = 'optimized'
$env:TTS_MODEL_NAME = 'Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice'
$env:TTS_CONFIG = Join-Path $repo 'config.yaml'
$env:TTS_DEVICE = 'cuda:0'
$env:TTS_DTYPE = 'bfloat16'
$env:TTS_ATTN = 'sdpa'
$env:TTS_LAZY_LOAD = 'true'
$env:TTS_WARMUP_ON_START = 'false'
$env:TTS_MAX_CONCURRENT = '1'
$env:CORS_ORIGINS = '*'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'

$process = Start-Process `
    -FilePath $python `
    -ArgumentList '-m', 'api.main' `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output "Started Qwen3-TTS (PID $($process.Id)) on http://127.0.0.1:8880."
