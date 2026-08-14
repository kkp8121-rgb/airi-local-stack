param(
    [Parameter(Mandatory)]
    [string]$MotifSnapshot,
    [Parameter(Mandatory)]
    [string]$MotifPython,
    [string]$MotifManifest = (Join-Path $PSScriptRoot 'ollama-proxy\eval\model-usage-manifests\motif-2.6b-v1.1-lc.json')
)

$ErrorActionPreference = 'Stop'
$MidmModel = 'midm-airi:2.0-mini'
$MidmDigest = '92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f'
$MotifModel = 'motif-airi:2.6b-v1.1-lc-nf4'
$MotifDigest = '2753574351457fd11b22ecd2e3b35ddc28350389843fbe1cc0b427e2b84f6be6'
$MotifPort = 11437
$GatewayPort = 11439
$Repo = $PSScriptRoot
$EvalRoot = Join-Path $Repo 'ollama-proxy\eval'
$RuntimeRoot = Join-Path $Repo 'ollama-proxy\runtime'
$StatePath = Join-Path $RuntimeRoot 'airi-remote-model-test-state.json'
$MotifScript = Join-Path $EvalRoot 'run_airi_motif_local_backend.py'
$GatewayScript = Join-Path $EvalRoot 'run_airi_remote_model_test_gateway.py'

function Get-RegularFilePath {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Description)
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.PSIsContainer -or $item -isnot [IO.FileInfo] -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "$Description must be a regular file."
    }
    return [IO.Path]::GetFullPath($item.FullName)
}

function Assert-PortIsFree {
    param([Parameter(Mandatory)][int]$Port)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) { throw "Port $Port is already listening; refusing to reuse or replace it." }
}

function Stop-StartedProcessTree {
    param([Diagnostics.Process]$Launcher, [Parameter(Mandatory)][string]$ScriptPath)
    if ($null -eq $Launcher) { return }
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($Launcher.Id)" -ErrorAction SilentlyContinue | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$_.CommandLine) -and
        ([string]$_.CommandLine).IndexOf($ScriptPath, [StringComparison]::OrdinalIgnoreCase) -ge 0
    })
    foreach ($child in $children) { Stop-Process -Id ([int]$child.ProcessId) -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $Launcher.Id -Force -ErrorAction SilentlyContinue
}

function Quote-ProcessArgument {
    param([Parameter(Mandatory)][string]$Value)
    return '"' + ($Value -replace '(\\*)"', '$1$1\\"' -replace '(\\*)$', '$1$1') + '"'
}

function Write-AtomicJson {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][object]$Value)
    $directory = Split-Path -Parent $Path
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 5 -Compress), [Text.UTF8Encoding]::new($false))
        [IO.File]::Move($temporary, $Path)
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-OrCreateTokenFile {
    $localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if ([string]::IsNullOrWhiteSpace($localAppData)) { throw 'LOCALAPPDATA is unavailable.' }
    $directory = Join-Path $localAppData 'ai.moeru.airi'
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $tokenPath = Join-Path $directory 'airi-remote-model-test.token'
    $replaceToken = -not (Test-Path -LiteralPath $tokenPath)
    if (-not $replaceToken) {
        try { $replaceToken = ([Convert]::FromBase64String([IO.File]::ReadAllText($tokenPath, [Text.Encoding]::UTF8).Trim())).Length -lt 32 }
        catch { $replaceToken = $true }
    }
    if ($replaceToken) {
        $bytes = [byte[]]::new(48)
        $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $generator.GetBytes($bytes) }
        finally { $generator.Dispose() }
        [IO.File]::WriteAllText($tokenPath, [Convert]::ToBase64String($bytes), [Text.UTF8Encoding]::new($false))
    }
    $tokenItem = Get-Item -LiteralPath $tokenPath -Force
    if ($tokenItem.PSIsContainer -or ($tokenItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $tokenItem.Length -lt 32) {
        throw 'Remote model test token file is invalid.'
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $identity) { throw 'Current Windows identity is unavailable.' }
    $acl = $tokenItem.GetAccessControl()
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRuleSpecific($rule) }
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity, [Security.AccessControl.FileSystemRights]::FullControl, [Security.AccessControl.AccessControlType]::Allow))
    $tokenItem.SetAccessControl($acl)
    return $tokenPath
}

function Assert-LoopbackMidm {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0 -or @($listeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }).Count -gt 0) {
        throw 'Existing Ollama must listen only on loopback port 11434.'
    }
    try { $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 -ErrorAction Stop }
    catch { throw 'Existing loopback Ollama tags endpoint is unavailable.' }
    $matches = @($tags.models | Where-Object { ([string]$_.name).Trim().ToLowerInvariant() -eq $MidmModel -or ([string]$_.model).Trim().ToLowerInvariant() -eq $MidmModel })
    if ($matches.Count -ne 1 -or ([string]$matches[0].digest).Trim().ToLowerInvariant() -ne $MidmDigest) {
        throw "Existing Ollama must expose exactly '$MidmModel' with its approved digest."
    }
}

if (-not (Test-Path -LiteralPath $MotifSnapshot -PathType Container)) { throw 'MotifSnapshot must be an existing pinned local directory.' }
$resolvedMotifSnapshot = [IO.Path]::GetFullPath((Get-Item -LiteralPath $MotifSnapshot).FullName)
if ((Get-Item -LiteralPath $resolvedMotifSnapshot).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'MotifSnapshot must not be a reparse point.' }
$resolvedPython = Get-RegularFilePath -Path $MotifPython -Description 'MotifPython'
$resolvedManifest = Get-RegularFilePath -Path $MotifManifest -Description 'Motif manifest'
$resolvedMotifScript = Get-RegularFilePath -Path $MotifScript -Description 'Motif backend script'
$resolvedGatewayScript = Get-RegularFilePath -Path $GatewayScript -Description 'Remote model test gateway script'
if (Test-Path -LiteralPath $StatePath) { throw "Remote model test state already exists: $StatePath. Run the matching stop script or investigate it; startup will not replace it." }
Assert-PortIsFree -Port $MotifPort
Assert-PortIsFree -Port $GatewayPort
Assert-LoopbackMidm
$tokenPath = Get-OrCreateTokenFile
[IO.Directory]::CreateDirectory($RuntimeRoot) | Out-Null
$motifOut = Join-Path $RuntimeRoot 'airi-remote-model-test-motif.out.log'
$motifErr = Join-Path $RuntimeRoot 'airi-remote-model-test-motif.err.log'
$gatewayOut = Join-Path $RuntimeRoot 'airi-remote-model-test-gateway.out.log'
$gatewayErr = Join-Path $RuntimeRoot 'airi-remote-model-test-gateway.err.log'
$motifArgs = @((Quote-ProcessArgument $resolvedMotifScript), '--host', '127.0.0.1', '--port', "$MotifPort", '--manifest', (Quote-ProcessArgument $resolvedManifest), '--snapshot', (Quote-ProcessArgument $resolvedMotifSnapshot), '--audit-report', (Quote-ProcessArgument (Join-Path $RuntimeRoot 'airi-remote-model-test-motif-audit.json'))) -join ' '
$gatewayArgs = @((Quote-ProcessArgument $resolvedGatewayScript), '--port', "$GatewayPort", '--token-file', (Quote-ProcessArgument $tokenPath), '--midm-url', 'http://127.0.0.1:11434', '--motif-url', "http://127.0.0.1:$MotifPort", '--midm-digest', $MidmDigest, '--motif-digest', $MotifDigest) -join ' '
$motif = $null
$gateway = $null
try {
    $motif = Start-Process -FilePath $resolvedPython -ArgumentList $motifArgs -WindowStyle Hidden -RedirectStandardOutput $motifOut -RedirectStandardError $motifErr -PassThru
    $motifDeadline = [DateTime]::UtcNow.AddSeconds(45)
    $motifReady = $false
    while ([DateTime]::UtcNow -lt $motifDeadline) {
        try {
            $motifShow = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$MotifPort/api/show" -ContentType 'application/json' -Body (@{ name = $MotifModel } | ConvertTo-Json -Compress) -TimeoutSec 2 -ErrorAction Stop
            if ($motifShow.digest -eq $MotifDigest) { $motifReady = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 300
    }
    if (-not $motifReady) { throw 'Pinned Motif backend did not become ready.' }
    $gateway = Start-Process -FilePath $resolvedPython -ArgumentList $gatewayArgs -WindowStyle Hidden -RedirectStandardOutput $gatewayOut -RedirectStandardError $gatewayErr -PassThru
    $token = [IO.File]::ReadAllText($tokenPath, [Text.Encoding]::UTF8).Trim()
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    $healthy = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$GatewayPort/health" -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 2 -ErrorAction Stop
            if ($health -and ($health.status -eq 'ok' -or $health.healthy -eq $true)) { $healthy = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 300
    }
    if (-not $healthy) { throw 'Authenticated remote model test gateway health check did not become ready.' }
    Write-AtomicJson -Path $StatePath -Value ([ordered]@{ schema_version = 'airi.remote-model-test-state.v1'; motif_pid = $motif.Id; gateway_pid = $gateway.Id; motif_port = $MotifPort; gateway_port = $GatewayPort; motif_script = $resolvedMotifScript; gateway_script = $resolvedGatewayScript; motif_python = $resolvedPython; started_utc = [DateTime]::UtcNow.ToString('o') })
    Write-Output "Remote model test stack is ready on loopback port $GatewayPort."
}
catch {
    Stop-StartedProcessTree -Launcher $gateway -ScriptPath $resolvedGatewayScript
    Stop-StartedProcessTree -Launcher $motif -ScriptPath $resolvedMotifScript
    throw
}
