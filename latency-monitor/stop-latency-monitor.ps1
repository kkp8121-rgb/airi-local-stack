$listeners = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8892 -State Listen -ErrorAction SilentlyContinue
if (-not $listeners) {
    Write-Host '실행 중인 Latency monitor가 없습니다.'
    exit 0
}

$processIds = @($listeners.OwningProcess | Sort-Object -Unique)
foreach ($processId in $processIds) {
    $target = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    if (-not $target.CommandLine -or $target.CommandLine.IndexOf('monitor_server.py', [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "포트 8892가 예상하지 않은 프로세스에 의해 사용 중입니다 (PID $processId). 중지를 거부합니다."
    }
    Stop-Process -Id $processId -Force
}
Write-Host "Latency monitor를 중지했습니다 (PID: $($processIds -join ', '))."
