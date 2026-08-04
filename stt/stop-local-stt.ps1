$ErrorActionPreference = 'Stop'
$server = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'openai_stt_server.py'))
$targets = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and
    $_.CommandLine.IndexOf($server, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

if (-not $targets) {
    Write-Output 'AIRI local STT server is not running.'
    exit 0
}

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force
    Write-Output "Stopped AIRI local STT server (PID $($target.ProcessId))."
}
