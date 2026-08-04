$ErrorActionPreference = 'Stop'
$server = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'ollama_proxy.py'))
$targets = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and
    $_.CommandLine.IndexOf($server, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

if (-not $targets) {
    Write-Output 'AIRI Ollama compatibility proxy is not running.'
    exit 0
}

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force
    Write-Output "Stopped AIRI Ollama compatibility proxy (PID $($target.ProcessId))."
}
