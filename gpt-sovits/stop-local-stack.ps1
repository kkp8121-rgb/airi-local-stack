$ErrorActionPreference = 'Stop'
$proxy = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'openai_compatible_proxy.py'))
$config = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'tts-infer-v2proplus.yaml'))

$targets = Get-CimInstance Win32_Process | Where-Object {
    if (-not $_.CommandLine) { return $false }

    $isProxy =
        $_.CommandLine.IndexOf($proxy, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.CommandLine -match '(?:^|\s)--port\s+8880(?:\s|$)'
    $isBackend =
        $_.CommandLine.IndexOf('api_v2.py', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.CommandLine.IndexOf($config, [StringComparison]::OrdinalIgnoreCase) -ge 0
    return $isProxy -or $isBackend
}

if (-not $targets) {
    Write-Output 'AIRI GPT-SoVITS local stack is not running.'
    exit 0
}

foreach ($target in ($targets | Sort-Object ParentProcessId -Descending)) {
    $process = Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    Stop-Process -Id $target.ProcessId -Force
    Write-Output "Stopped AIRI GPT-SoVITS process $($target.Name) (PID $($target.ProcessId))."
}
