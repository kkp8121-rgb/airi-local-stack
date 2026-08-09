param(
    [string]$ExecutablePath = (Join-Path $env:LOCALAPPDATA 'Programs\airi\AIRI.exe'),
    [string]$SourceRoot = (Join-Path ([IO.Path]::GetTempPath()) 'airi-v0113-source-codex-20260808'),
    [ValidateRange(5, 120)]
    [int]$StartupTimeoutSeconds = 30,
    [switch]$InspectOnly
)

$ErrorActionPreference = 'Stop'

function Get-AiriProcessForExecutable {
    param([Parameter(Mandatory)][string]$ResolvedExecutablePath)

    $comparison = [StringComparison]::OrdinalIgnoreCase
    return @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$_.ExecutablePath) -and
        [string]::Equals([string]$_.ExecutablePath, $ResolvedExecutablePath, $comparison)
    })
}

function Test-AiriVoiceStatusReady {
    param(
        [Parameter(Mandatory)][string]$ResolvedSourceRoot,
        [Parameter(Mandatory)][string]$StatusScript,
        [Parameter(Mandatory)][string]$NodeExecutable
    )

    $previousSourceRoot = $env:AIRI_SOURCE_ROOT
    try {
        $env:AIRI_SOURCE_ROOT = $ResolvedSourceRoot
        $raw = & $NodeExecutable $StatusScript 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$raw)) {
            return $false
        }
        $snapshot = ([string]$raw | ConvertFrom-Json -ErrorAction Stop)
        return $snapshot.stageMounted -eq $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -eq $previousSourceRoot) {
            Remove-Item Env:AIRI_SOURCE_ROOT -ErrorAction SilentlyContinue
        }
        else {
            $env:AIRI_SOURCE_ROOT = $previousSourceRoot
        }
    }
}

if ([string]::IsNullOrWhiteSpace($ExecutablePath)) {
    throw 'AIRI executable path is empty.'
}

$resolvedExecutable = (Resolve-Path -LiteralPath $ExecutablePath -ErrorAction Stop).Path
if ([IO.Path]::GetFileName($resolvedExecutable) -ine 'AIRI.exe') {
    throw 'AIRI executable must be the installed AIRI.exe.'
}
$installDirectory = Split-Path -Parent $resolvedExecutable
$appArchive = Join-Path $installDirectory 'resources\app.asar'
if (-not (Test-Path -LiteralPath $appArchive -PathType Leaf)) {
    throw 'The AIRI installation does not contain resources\app.asar.'
}

$resolvedSourceRoot = (Resolve-Path -LiteralPath $SourceRoot -ErrorAction Stop).Path
$statusScript = Join-Path $PSScriptRoot 'get-airi-local-voice-status.mjs'
if (-not (Test-Path -LiteralPath $statusScript -PathType Leaf)) {
    throw 'The passive AIRI voice-status helper is missing.'
}
$node = (Get-Command node -CommandType Application -ErrorAction Stop).Source

$existing = @(Get-AiriProcessForExecutable -ResolvedExecutablePath $resolvedExecutable)
if ($existing.Count -gt 0) {
    $visible = @($existing | Where-Object {
        try { (Get-Process -Id ([int]$_.ProcessId) -ErrorAction Stop).MainWindowHandle -ne 0 }
        catch { $false }
    }).Count -gt 0
    [pscustomobject]@{
        Status = if ($visible) { 'already-running-visible' } else { 'already-running-hidden' }
        Started = $false
        BackgroundRequested = $false
        ProcessCount = $existing.Count
        StageReady = if ($visible) { $false } else {
            Test-AiriVoiceStatusReady -ResolvedSourceRoot $resolvedSourceRoot -StatusScript $statusScript -NodeExecutable $node
        }
    }
    return
}

if ($InspectOnly) {
    [pscustomobject]@{
        Status = 'ready-to-start'
        Started = $false
        BackgroundRequested = $false
        ProcessCount = 0
        StageReady = $false
    }
    return
}

# The application-side --background contract keeps the renderer and local
# channel alive while leaving the user-facing BrowserWindow hidden. The
# hidden process window is an additional Windows-side guard, not the owner of
# the Electron visibility policy.
$started = Start-Process `
    -FilePath $resolvedExecutable `
    -ArgumentList @('--background') `
    -WorkingDirectory $installDirectory `
    -WindowStyle Hidden `
    -PassThru

$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
do {
    if ($started.HasExited) {
        throw "AIRI background process exited during startup with code $($started.ExitCode)."
    }
    $running = @(Get-AiriProcessForExecutable -ResolvedExecutablePath $resolvedExecutable)
    if ($running.Count -gt 0) {
        $visible = @($running | Where-Object {
            try { (Get-Process -Id ([int]$_.ProcessId) -ErrorAction Stop).MainWindowHandle -ne 0 }
            catch { $false }
        }).Count -gt 0
        if ($visible) {
            throw 'AIRI created a visible window during background startup.'
        }
        if (Test-AiriVoiceStatusReady -ResolvedSourceRoot $resolvedSourceRoot -StatusScript $statusScript -NodeExecutable $node) {
            [pscustomobject]@{
                Status = 'started-background'
                Started = $true
                BackgroundRequested = $true
                ProcessCount = $running.Count
                StageReady = $true
            }
            return
        }
    }
    Start-Sleep -Milliseconds 300
} while ((Get-Date) -lt $deadline)

throw "AIRI background renderer was not ready within $StartupTimeoutSeconds seconds."
