$ErrorActionPreference = 'Stop'

$listeners = Get-NetTCPConnection -LocalPort 8880 -State Listen -ErrorAction SilentlyContinue
if (-not $listeners) {
    Write-Output 'Qwen3-TTS is not running.'
    exit 0
}

foreach ($listener in $listeners) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    $parentInfo = if ($processInfo) {
        Get-CimInstance Win32_Process -Filter "ProcessId = $($processInfo.ParentProcessId)"
    }

    $isApiProcess = $processInfo -and $processInfo.CommandLine -match '-m\s+api\.main'
    $isRepoLauncher = $parentInfo -and $parentInfo.ExecutablePath -eq (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')

    if ($isApiProcess -and $isRepoLauncher) {
        Stop-Process -Id $processInfo.ProcessId
        Stop-Process -Id $parentInfo.ProcessId -ErrorAction SilentlyContinue
        Write-Output "Stopped Qwen3-TTS (PID $($processInfo.ProcessId))."
    }
    else {
        throw "Port 8880 is owned by an unexpected process (PID $($listener.OwningProcess)); refusing to stop it."
    }
}
