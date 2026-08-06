$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$venvPython = Join-Path $root 'stt\.venv\Scripts\python.exe'
$python = if (Test-Path $venvPython) { $venvPython } else { 'python' }
$outLog = Join-Path $here 'latency-monitor.out.log'
$errLog = Join-Path $here 'latency-monitor.err.log'
$listeners = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8892 -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    Write-Host "이미 실행 중입니다 (PID: $(@($listeners.OwningProcess | Sort-Object -Unique) -join ', '))."
    exit 0
}
$p = Start-Process -FilePath $python -ArgumentList 'monitor_server.py' -WorkingDirectory $here -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
Write-Host "시작됨: http://127.0.0.1:8892 (PID $($p.Id))"
