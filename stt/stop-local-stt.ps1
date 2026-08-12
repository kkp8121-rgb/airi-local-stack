$ErrorActionPreference = 'Stop'
$server = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'openai_stt_server.py'))
$pythonExecutablePattern = '^python(?:w|3(?:\.\d+)*)?\.exe$'
$serverTokenPattern = '(?i)(?:^|\s)(?:"' + [Regex]::Escape($server) + '"|' + [Regex]::Escape($server) + ')(?=\s|$)'
$hostTokenPattern = '(?i)(?:^|\s)--host(?:\s+|=)"?127\.0\.0\.1"?(?=\s|$)'
$portTokenPattern = '(?i)(?:^|\s)--port(?:\s+|=)"?8890"?(?=\s|$)'
$targets = Get-CimInstance Win32_Process | Where-Object {
    $executableName = if ($_.ExecutablePath) { [IO.Path]::GetFileName($_.ExecutablePath) } else { '' }
    $executableName -match $pythonExecutablePattern -and
    $_.CommandLine -match $serverTokenPattern -and
    $_.CommandLine -match $hostTokenPattern -and
    $_.CommandLine -match $portTokenPattern
}

if (-not $targets) {
    Write-Output 'AIRI local STT server is not running.'
    exit 0
}

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force
    Write-Output "Stopped AIRI local STT server (PID $($target.ProcessId))."
}
