param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 11436,
    [int]$ExpectedPid = 0
)

$ErrorActionPreference = 'Stop'
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -eq 0) {
    if ($ExpectedPid -ne 0) { throw 'Expected memory extractor PID is not listening.' }
    Write-Output "Memory extractor Ollama is not listening on port $Port."
    exit 0
}
if (@($listeners | Where-Object LocalAddress -ne '127.0.0.1').Count -gt 0) {
    throw "Refusing to stop port $Port because it has a non-loopback listener."
}

$processIds = @($listeners.OwningProcess | Sort-Object -Unique)
if ($ExpectedPid -ne 0 -and ($processIds.Count -ne 1 -or [int]$processIds[0] -ne $ExpectedPid)) {
    throw 'Memory extractor PID ownership no longer matches the expected process.'
}
foreach ($processId in $processIds) {
    $target = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
    if (-not $target -or $target.Name -ne 'ollama.exe' -or $target.CommandLine -notmatch '(?i)\bserve\b') {
        throw "Refusing to stop PID $processId because it is not an Ollama serve process."
    }
}
foreach ($processId in $processIds) {
    Stop-Process -Id $processId -Force
    Write-Output "Stopped memory extractor Ollama on port $Port (PID $processId)."
}
