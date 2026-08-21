$ErrorActionPreference = 'Stop'
$proxy = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'openai_compatible_proxy.py'))
$config = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'tts-infer-v2proplus.yaml'))
$wrapper = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'run_v2proplus_with_sv_cache.py'))
$externalRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\external\GPT-SoVITS'))
$configPattern = '(?:^|[\s"])' + [regex]::Escape($config) + '(?=$|[\s"])'
$wrapperPattern = '(?:^|[\s"])' + [regex]::Escape($wrapper) + '(?=$|[\s"])'
$externalRootArgumentPattern = '(?<!\S)--external-root\s+"?' + [regex]::Escape($externalRoot) + '"?(?!\S)'

$targets = Get-CimInstance Win32_Process | Where-Object {
    if (-not $_.CommandLine) { return $false }

    $isProxy =
        $_.CommandLine.IndexOf($proxy, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.CommandLine -match '(?:^|\s)--port\s+8880(?:\s|$)'
    $isBackend =
        $_.CommandLine.IndexOf('api_v2.py', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.CommandLine.IndexOf($config, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $isCachedWrapperBackend =
        $_.CommandLine -match $wrapperPattern -and
        $_.CommandLine -match $configPattern -and
        $_.CommandLine -match $externalRootArgumentPattern -and
        $_.CommandLine -match '(?:^|\s)--\s+-a\s+127\.0\.0\.1(?:\s|$)' -and
        $_.CommandLine -match '(?:^|\s)-p\s+9880(?:\s|$)'
    return $isProxy -or $isBackend -or $isCachedWrapperBackend
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
