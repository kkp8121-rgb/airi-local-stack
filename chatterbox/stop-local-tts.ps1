$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath($PSScriptRoot)
$targets = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and
    $_.CommandLine.IndexOf(
        (Join-Path $repo 'openai_server.py'),
        [StringComparison]::OrdinalIgnoreCase
    ) -ge 0
}

if (-not $targets) {
    Write-Output 'Chatterbox TTS is not running.'
    exit 0
}

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force
    Write-Output "Stopped Chatterbox TTS (PID $($target.ProcessId))."
}
