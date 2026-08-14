$ErrorActionPreference = 'Stop'
$MidmModel = 'midm-airi:2.0-mini'
$MotifModel = 'motif-airi:2.6b-v1.1-lc-nf4'
$RuntimeRoot = Join-Path $PSScriptRoot 'ollama-proxy\runtime'
$StatePath = Join-Path $RuntimeRoot 'airi-remote-model-test-state.json'
$ExpectedMotifScript = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'ollama-proxy\eval\run_airi_motif_local_backend.py'))
$ExpectedGatewayScript = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'ollama-proxy\eval\run_airi_remote_model_test_gateway.py'))

function Get-OwnedProcess {
    param([Parameter(Mandatory)][int]$ProcessId, [Parameter(Mandatory)][string]$ScriptPath, [Parameter(Mandatory)][int]$Port)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    if ($null -eq $process -or [string]::IsNullOrWhiteSpace($process.CommandLine)) { throw "Owned process $ProcessId cannot be verified." }
    $commandLine = [string]$process.CommandLine
    if ($commandLine.IndexOf($ScriptPath, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or $commandLine -notmatch ('(?<!\d)--port\s+' + [regex]::Escape([string]$Port) + '(?!\d)')) {
        throw "Owned process $ProcessId does not match its recorded script and port signature."
    }
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1') { throw "Owned process $ProcessId is not associated with the sole loopback listener on port $Port." }
    $listenerPid = [int]$listeners[0].OwningProcess
    if ($listenerPid -eq $ProcessId) {
        $listenerProcess = $process
    }
    else {
        $listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerPid" -ErrorAction Stop
        if ($null -eq $listenerProcess -or [int]$listenerProcess.ParentProcessId -ne $ProcessId -or
            [string]::IsNullOrWhiteSpace([string]$listenerProcess.CommandLine) -or
            ([string]$listenerProcess.CommandLine).IndexOf($ScriptPath, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw "Owned process $ProcessId is not the verified parent of listener $listenerPid on port $Port."
        }
    }
    return [pscustomobject]@{ Launcher = $process; Listener = $listenerProcess }
}

if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { throw 'Remote model test state is absent; refusing to target any process.' }
try { $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -ErrorAction Stop }
catch { throw 'Remote model test state is unreadable; refusing to target any process.' }
foreach ($name in 'schema_version', 'motif_pid', 'gateway_pid', 'motif_port', 'gateway_port', 'motif_script', 'gateway_script') {
    if ($null -eq $state.PSObject.Properties[$name] -or [string]::IsNullOrWhiteSpace([string]$state.$name)) { throw "Remote model test state lacks $name; refusing to target any process." }
}
if ($state.schema_version -ne 'airi.remote-model-test-state.v1' -or [int]$state.motif_port -ne 11437 -or [int]$state.gateway_port -ne 11439) { throw 'Remote model test state does not match this stack contract.' }
if (-not [string]::Equals([string]$state.motif_script, $ExpectedMotifScript, [StringComparison]::OrdinalIgnoreCase) -or -not [string]::Equals([string]$state.gateway_script, $ExpectedGatewayScript, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Remote model test state has unexpected process script paths.'
}
$motif = Get-OwnedProcess -ProcessId ([int]$state.motif_pid) -ScriptPath ([string]$state.motif_script) -Port 11437
$gateway = Get-OwnedProcess -ProcessId ([int]$state.gateway_pid) -ScriptPath ([string]$state.gateway_script) -Port 11439

# Best effort unloads run before stop; they intentionally carry no user content.
try { Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11437/api/show' -ContentType 'application/json' -Body (@{ name = $MotifModel; keep_alive = 0 } | ConvertTo-Json -Compress) -TimeoutSec 5 -ErrorAction Stop | Out-Null } catch { }
try { Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' -ContentType 'application/json' -Body (@{ model = $MidmModel; prompt = ''; keep_alive = 0; stream = $false } | ConvertTo-Json -Compress) -TimeoutSec 5 -ErrorAction Stop | Out-Null } catch { }
Stop-Process -Id ([int]$gateway.Listener.ProcessId) -ErrorAction Stop
Stop-Process -Id ([int]$motif.Listener.ProcessId) -ErrorAction Stop
if ([int]$gateway.Launcher.ProcessId -ne [int]$gateway.Listener.ProcessId) { Stop-Process -Id ([int]$gateway.Launcher.ProcessId) -ErrorAction SilentlyContinue }
if ([int]$motif.Launcher.ProcessId -ne [int]$motif.Listener.ProcessId) { Stop-Process -Id ([int]$motif.Launcher.ProcessId) -ErrorAction SilentlyContinue }
$retiredState = Join-Path $RuntimeRoot ('.airi-remote-model-test-state.' + [Guid]::NewGuid().ToString('N') + '.retired')
[IO.File]::Move($StatePath, $retiredState)
Remove-Item -LiteralPath $retiredState -Force
Write-Output 'Remote model test stack stopped. The local token file was preserved.'
