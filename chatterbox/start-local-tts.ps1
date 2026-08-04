param(
    [string]$ReferenceAudio = (Join-Path $PSScriptRoot 'voices\airi-reference.wav'),
    [ValidateRange(0.25, 2.0)]
    [double]$Exaggeration = 0.65,
    [ValidateRange(0.0, 1.0)]
    [double]$CfgWeight = 0.00,
    [ValidateRange(0.1, 1.5)]
    [double]$Temperature = 0.80
)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$server = Join-Path $repo 'openai_server.py'
$stdoutLog = Join-Path $repo 'tts-server.out.log'
$stderrLog = Join-Path $repo 'tts-server.err.log'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Chatterbox Python environment not found: $python"
}
if (-not (Test-Path -LiteralPath $ReferenceAudio)) {
    throw "Reference audio not found. Copy a clean 5-15 second WAV to: $ReferenceAudio"
}

$listener = Get-NetTCPConnection -LocalPort 8880 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output "A service is already listening on port 8880 (PID $($listener.OwningProcess))."
    exit 0
}

$env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $server, '--reference-audio', $ReferenceAudio, '--exaggeration', $Exaggeration, '--cfg-weight', $CfgWeight, '--temperature', $Temperature, '--host', '127.0.0.1', '--port', '8880' `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output "Started Chatterbox Multilingual V3 loader (PID $($process.Id))."
