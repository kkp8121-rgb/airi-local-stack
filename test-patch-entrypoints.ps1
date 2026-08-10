#Requires -Version 5.1
<#
.SYNOPSIS
    Offline regression test for the supported AIRI patch entrypoint contract.

.DESCRIPTION
    Does not inspect or modify an AIRI installation. It verifies that every
    internal patch step rejects direct invocation before path access and that
    the orchestrator passes the explicit internal-call switch.
#>
$ErrorActionPreference = 'Stop'

$children = @(
    'patch-airi-audio-constraints.ps1'
    'patch-airi-native-media-recorder.ps1'
    'patch-airi-voice-input-segmentation.ps1'
    'patch-airi-reaction-latency.ps1'
    'patch-airi-playback-latency.ps1'
    'patch-airi-session-header.ps1'
)
$missingArchive = Join-Path ([IO.Path]::GetTempPath()) 'airi-entrypoint-contract-missing-app.asar'

foreach ($name in $children) {
    $path = Join-Path $PSScriptRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing child script: $name"
    }
    $source = Get-Content -LiteralPath $path -Raw
    if ($source -notmatch '\[switch\]\$InternalOrchestrator' -or
        $source -notmatch 'This patch step is internal') {
        throw "Child guard contract missing: $name"
    }

    $directRejected = $false
    try { & $path -AsarPath $missingArchive 2>$null }
    catch {
        if ($_.Exception.Message -match 'internal|apply-airi-patches') {
            $directRejected = $true
        }
        else { throw "Direct invocation reached archive logic: $name" }
    }
    if (-not $directRejected) { throw "Direct invocation unexpectedly succeeded: $name" }

    $internalReachedPathValidation = $false
    try { & $path -AsarPath $missingArchive -InternalOrchestrator 2>$null }
    catch {
        if ($_.Exception.Message -notmatch 'This patch step is internal') {
            $internalReachedPathValidation = $true
        }
    }
    if (-not $internalReachedPathValidation) { throw "Orchestrator switch was not accepted: $name" }
}

$orchestrator = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'apply-airi-patches.ps1') -Raw
if ($orchestrator -notmatch [regex]::Escape('& $scriptPath -AsarPath $resolvedAsar') -or
    $orchestrator -notmatch '-InternalOrchestrator') {
    throw 'Orchestrator does not forward the internal-call switch.'
}

Write-Output 'Patch entrypoint contract: PASS (offline, no archive access).'
