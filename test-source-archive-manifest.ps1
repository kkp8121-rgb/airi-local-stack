#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$archiveRoot = Join-Path $root 'airi_docs\evidence\source-archives'
$manifestPath = Join-Path $archiveRoot 'AIRI-SOURCE-ARCHIVE-MANIFEST-2026-08-14.json'
$manifestText = [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8)
$manifest = $manifestText | ConvertFrom-Json

if ($manifest.schema_version -ne 'airi.source-archive-manifest.v1') {
    throw 'Unexpected source archive manifest schema.'
}
if ($manifestText -match '[A-Za-z]:[\\/]') {
    throw 'Source archive manifest must not contain a machine-specific absolute path.'
}
if ($manifest.raw_session_content_included -ne $false -or
    $manifest.credentials_included -ne $false) {
    throw 'Source archive manifest privacy boundary changed.'
}
if ($manifest.research_remote_rehearsal.status -ne 'archived_not_deployed') {
    throw 'Remote model rehearsal archive must remain explicitly non-deployed.'
}
if ($manifest.model_provenance_collection.contains_weights -ne $false -or
    $manifest.model_provenance_collection.contains_prompts_or_outputs -ne $false) {
    throw 'P0 provenance archive must remain weight- and content-free.'
}

function Assert-Artifact {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$Sha256,
        [long]$ExpectedBytes = -1
    )

    $path = Join-Path $root $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Source archive artifact is missing: $RelativePath"
    }
    if ($ExpectedBytes -ge 0 -and
        (Get-Item -LiteralPath $path).Length -ne $ExpectedBytes) {
        throw "Source archive artifact length changed: $RelativePath"
    }
    $actualHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    if ($actualHash -ne $Sha256) {
        throw "Source archive artifact hash changed: $RelativePath"
    }
}

$declaredArchivePaths = [Collections.Generic.List[string]]::new()
foreach ($entry in $manifest.archives) {
    Assert-Artifact -RelativePath $entry.path -Sha256 $entry.sha256 `
        -ExpectedBytes ([long]$entry.bytes)
    $declaredArchivePaths.Add($entry.path.Replace('\', '/'))
    $header = [Text.Encoding]::ASCII.GetString(
        [IO.File]::ReadAllBytes((Join-Path $root $entry.path)),
        0,
        15
    )
    if (-not $header.StartsWith('# v2 git bundle')) {
        throw "Git bundle header changed: $($entry.path)"
    }
}

$patchArchive = $manifest.research_patch_iterations
Assert-Artifact -RelativePath $patchArchive.path -Sha256 $patchArchive.sha256 `
    -ExpectedBytes ([long]$patchArchive.bytes)
$declaredArchivePaths.Add($patchArchive.path.Replace('\', '/'))

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead((Join-Path $root $patchArchive.path))
try {
    $actualMembers = @($zip.Entries.FullName | Sort-Object -Unique)
    $expectedMembers = @($patchArchive.members.name | Sort-Object -Unique)
    if (@($actualMembers | Where-Object { $_ -notin $expectedMembers }).Count -or
        @($expectedMembers | Where-Object { $_ -notin $actualMembers }).Count) {
        throw 'TTS resampler research archive member set changed.'
    }
    foreach ($member in $patchArchive.members) {
        $entry = $zip.GetEntry($member.name)
        if ($null -eq $entry -or $entry.Length -ne [long]$member.bytes) {
            throw "TTS resampler research member length changed: $($member.name)"
        }
        $stream = $entry.Open()
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            $actualHash = ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '')
        }
        finally {
            $sha.Dispose()
            $stream.Dispose()
        }
        if ($actualHash -ne $member.sha256) {
            throw "TTS resampler research member hash changed: $($member.name)"
        }
    }
}
finally {
    $zip.Dispose()
}

$remoteBase = 'airi_docs/evidence/source-archives/remote-model-test-rehearsal-20260814'
foreach ($entry in $manifest.research_remote_rehearsal.files) {
    $relativePath = "$remoteBase/$($entry.archive_name)"
    Assert-Artifact -RelativePath $relativePath -Sha256 $entry.sha256 `
        -ExpectedBytes ([long]$entry.bytes)
    $declaredArchivePaths.Add($relativePath)
}

$modelEntry = $manifest.model_provenance_collection
Assert-Artifact -RelativePath $modelEntry.path -Sha256 $modelEntry.sha256 `
    -ExpectedBytes ([long]$modelEntry.bytes)
$declaredArchivePaths.Add($modelEntry.path.Replace('\', '/'))

foreach ($entry in $manifest.authoritative_runtime_patch_layers) {
    if ($entry.sha256) {
        Assert-Artifact -RelativePath $entry.path -Sha256 $entry.sha256
    }
}

$actualArchivePaths = @(
    Get-ChildItem -LiteralPath $archiveRoot -File -Recurse |
        Where-Object { $_.FullName -ne $manifestPath } |
        ForEach-Object {
            $_.FullName.Substring($root.Length + 1).Replace('\', '/')
        } |
        Sort-Object -Unique
)
$expectedArchivePaths = @($declaredArchivePaths | Sort-Object -Unique)
$missing = @($expectedArchivePaths | Where-Object { $_ -notin $actualArchivePaths })
$undeclared = @($actualArchivePaths | Where-Object { $_ -notin $expectedArchivePaths })
if ($missing.Count -or $undeclared.Count) {
    throw "Source archive set differs from manifest. Missing: $($missing -join ', '); undeclared: $($undeclared -join ', ')"
}

Write-Output 'Source archive manifest contract: PASS (offline, content-safe artifacts only).'
