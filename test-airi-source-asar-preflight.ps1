#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$ArtifactPath,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$CandidateUnpackedPath,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$InstallDir,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$EvidencePath,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ExpectedEvidenceSha256,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$RepositoryRoot,
    [switch]$EnableTestHooks,
    [scriptblock]$ProcessProvider,
    [scriptblock]$BeforeFinalRehash
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'airi-source-asar-deploy-common.ps1')
if (($null -ne $ProcessProvider -or $null -ne $BeforeFinalRehash) -and -not $EnableTestHooks) {
    throw 'ProcessProvider and BeforeFinalRehash require EnableTestHooks.'
}

function Assert-EqualValue { param($Actual, $Expected, [string]$What)
    if ($Actual -cne $Expected) { throw "$What does not match the pinned evidence." }
}
function Get-DigestCheckedPath { param([string]$Path,[string]$What,[switch]$Directory)
    Get-AiriNormalPath -Path $Path -Description $What -Directory:$Directory
}
function Assert-HashShape { param($Value,[string]$What)
    if ($Value -isnot [string] -or $Value -notmatch '^[A-Fa-f0-9]{64}$') { throw "$What must be a SHA-256 digest." }
}
function Assert-EvidenceInteger { param($Value,[string]$What)
    if ($Value -isnot [Int64] -and $Value -isnot [Int32]) { throw "$What must be an integer, not a string or fraction." }
    if ([Int64]$Value -lt 0) { throw "$What must be nonnegative." }
}
function Assert-EvidenceBoolean { param($Value,[bool]$Expected,[string]$What)
    if ($Value -isnot [bool] -or $Value -ne $Expected) { throw "$What must be the boolean $Expected." }
}
function Get-UnpackedManifest {
    param([Parameter(Mandatory)][string]$Path,[Parameter(Mandatory)][string]$Description)
    $root = Get-DigestCheckedPath $Path $Description -Directory
    $rows = New-Object System.Collections.Generic.List[string]
    $identities = New-Object 'System.Collections.Generic.Dictionary[string,string]' -ArgumentList ([StringComparer]::Ordinal)
    foreach ($directory in @(Get-ChildItem -LiteralPath $root.FullName -Directory -Recurse -Force)) {
        Assert-AiriNoReparseAncestors -Path $directory.FullName -Description "$Description directory"
    }
    foreach ($file in @(Get-ChildItem -LiteralPath $root.FullName -File -Recurse -Force)) {
        Assert-AiriNoReparseAncestors -Path $file.FullName -Description "$Description file"
        $relative = $file.FullName.Substring($root.FullName.TrimEnd('\').Length).TrimStart('\').Replace('\','/')
        if ($relative.Length -eq 0 -or $relative.Contains("`t") -or $relative.Contains("`n") -or $relative.Contains("`r")) { throw "$Description contains an unsafe relative path." }
        $digest = Get-AiriFileDigest $file.FullName
        $identities.Add($relative, (Get-AiriFileIdentity $file.FullName))
        $rows.Add($relative + "`t" + $digest.Length.ToString([Globalization.CultureInfo]::InvariantCulture) + "`t" + $digest.Sha256.ToUpperInvariant())
    }
    # The evidence format explicitly specifies ordinal ordering, rather than
    # the current user's culture-sensitive PowerShell sort behavior.
    $orderedList = New-Object 'System.Collections.Generic.List[string]'
    foreach ($row in $rows) { $orderedList.Add($row) }
    $orderedList.Sort([StringComparer]::Ordinal)
    $ordered = @($orderedList)
    $payload = [Text.Encoding]::UTF8.GetBytes((($ordered -join "`n") + $(if ($ordered.Count -gt 0) { "`n" } else { '' })))
    $sha = [Security.Cryptography.SHA256]::Create(); try { $hash = ([BitConverter]::ToString($sha.ComputeHash($payload))).Replace('-','') } finally { $sha.Dispose() }
    [pscustomobject]@{ Sha256 = $hash; Files = $ordered.Count; Bytes = [Int64](($ordered | ForEach-Object { [Int64](($_ -split "`t")[1]) } | Measure-Object -Sum).Sum); Identities = $identities }
}
function Assert-UnpackedSnapshotStable {
    param($Before,$After,[string]$What)
    if ($Before.Sha256 -cne $After.Sha256 -or $Before.Files -ne $After.Files -or $Before.Bytes -ne $After.Bytes -or $Before.Identities.Count -ne $After.Identities.Count) {
        throw "$What changed during preflight."
    }
    foreach ($relative in $Before.Identities.Keys) {
        if (-not $After.Identities.ContainsKey($relative) -or $Before.Identities[$relative] -cne $After.Identities[$relative]) {
            throw "$What file identity changed during preflight."
        }
    }
}
function Assert-NoCrossTreeUnpackedAlias {
    param($Candidate,$Installed)
    foreach ($candidateIdentity in $Candidate.Identities.Values) {
        foreach ($installedIdentity in $Installed.Identities.Values) {
            if ($candidateIdentity -ceq $installedIdentity) {
                throw 'Candidate and installed app.asar.unpacked contain a cross-tree hard-link alias.'
            }
        }
    }
}
function Assert-PatchLayers {
    param($Layers,[string]$Root)
    if ($null -eq $Layers -or @($Layers).Count -eq 0) { throw 'Evidence source.patch_layers is required.' }
    $rootPath = Get-DigestCheckedPath $Root 'RepositoryRoot' -Directory
    $snapshots = New-Object System.Collections.Generic.List[object]
    foreach ($layer in @($Layers)) {
        $path = Get-AiriJsonProperty $layer path 'patch layer'; $bytes = Get-AiriJsonProperty $layer bytes 'patch layer'; $expected = Get-AiriJsonProperty $layer sha256 'patch layer'
        if ($path -isnot [string] -or [IO.Path]::IsPathRooted($path) -or $path -match '(^|[\\/])\.\.([\\/]|$)' -or $path -match '[:<>\x00-\x1f]') { throw 'Evidence patch layer path must be a repository-relative non-escaping path.' }
        Assert-HashShape $expected 'Evidence patch layer SHA-256'
        Assert-EvidenceInteger $bytes 'Evidence patch layer bytes'
        $candidate = Join-Path $rootPath.FullName $path
        $normal = Get-DigestCheckedPath $candidate 'Evidence patch layer'
        if (-not $normal.FullName.StartsWith($rootPath.FullName.TrimEnd('\') + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence patch layer escapes RepositoryRoot.' }
        $actual = Get-AiriFileDigest $normal.FullName
        if ($actual.Length -ne [Int64]$bytes -or $actual.Sha256 -cne $expected.ToLowerInvariant()) { throw 'Evidence patch layer does not match its pinned bytes or SHA-256.' }
        $snapshots.Add([pscustomobject]@{ Path=$normal.FullName; Length=$actual.Length; Sha256=$actual.Sha256 })
    }
    return $snapshots.ToArray()
}
function Assert-NoAiriProcess {
    param([string]$Executable,[scriptblock]$Provider)
    $processes = if ($null -ne $Provider) { & $Provider } else { Get-Process -ErrorAction SilentlyContinue }
    try { $exeId = Get-AiriFileIdentity $Executable }
    catch { throw 'Could not inspect the installed AIRI executable identity; refusing ASAR-only preflight.' }
    foreach ($process in @($processes)) {
        try { $path = $process.Path } catch { if ($process.ProcessName -eq 'airi') { throw 'Could not inspect an AIRI process path; refusing ASAR-only preflight.' }; continue }
        if ([string]::IsNullOrWhiteSpace($path)) { if ($process.ProcessName -eq 'airi') { throw 'Could not inspect an AIRI process path; refusing ASAR-only preflight.' }; continue }
        $samePath = ([IO.Path]::GetFullPath($path)).Equals($Executable,[StringComparison]::OrdinalIgnoreCase)
        $sameIdentity = $false
        if (-not $samePath) { try { $sameIdentity = ((Get-AiriFileIdentity $path) -eq $exeId) } catch { throw 'Could not inspect an accessible process executable identity; refusing ASAR-only preflight.' } }
        if ($samePath -or $sameIdentity) { throw 'AIRI is running from the requested InstallDir; refusing ASAR-only preflight.' }
    }
}

$evidence = Get-DigestCheckedPath $EvidencePath 'EvidencePath'
$evidenceDigest = Get-AiriFileDigest $evidence.FullName
if ($evidenceDigest.Sha256 -cne $ExpectedEvidenceSha256.ToLowerInvariant()) { throw 'EvidencePath SHA-256 does not match ExpectedEvidenceSha256.' }
try { $report = (Get-Content -LiteralPath $evidence.FullName -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop) } catch { throw "EvidencePath is not valid JSON. $($_.Exception.Message)" }
Assert-EqualValue $report.schema 'airi.source-asar-build-provenance.v1' 'Evidence schema'
foreach ($required in 'candidate','installed_baseline','deployment_gate','unpacked_compatibility','executable_compatibility','source','build') { [void](Get-AiriJsonProperty $report $required 'Evidence') }
$gate = $report.deployment_gate; $candidateEvidence = $report.candidate; $baseline = $report.installed_baseline
Assert-EvidenceBoolean $candidateEvidence.validator_passed $true 'Evidence candidate.validator_passed'; Assert-EvidenceBoolean $gate.asar_candidate_validated $true 'Evidence deployment_gate.asar_candidate_validated'
foreach ($bool in @(@($report.source.tracked_clean_after_build,$true,'Evidence source.tracked_clean_after_build'),@($report.build.source_build.passed,$true,'Evidence build.source_build.passed'),@($report.build.packaging.candidate_asar_created,$true,'Evidence build.packaging.candidate_asar_created'),@($report.build.packaging.asar_content_affected_by_failure,$false,'Evidence build.packaging.asar_content_affected_by_failure'),@($baseline.read_only_validation_passed,$true,'Evidence installed_baseline.read_only_validation_passed'),@($baseline.modified_by_this_batch,$false,'Evidence installed_baseline.modified_by_this_batch'),@($gate.runtime_tts_duration_pitch_verified,$false,'Evidence deployment_gate.runtime_tts_duration_pitch_verified'),@($gate.install_performed,$false,'Evidence deployment_gate.install_performed'),@($gate.requires_explicit_installed_app_authorization,$true,'Evidence deployment_gate.requires_explicit_installed_app_authorization'))) { Assert-EvidenceBoolean $bool[0] $bool[1] $bool[2] }
foreach ($commitName in 'base_commit','commit','tree') { if ($report.source.$commitName -isnot [string] -or $report.source.$commitName -notmatch '^[a-f0-9]{40}$') { throw "Evidence source.$commitName must be a lowercase 40-hex Git id." } }
if ($candidateEvidence.package.name -ne 'ai.moeru.airi' -or $candidateEvidence.package.version -ne '0.11.3') { throw 'Evidence candidate package identity is not AIRI 0.11.3.' }
foreach ($flag in 'out/main/index.js','out/preload/index.mjs','out/renderer/index.html','renderer_pages_bundle') {
    $flagValue = Get-AiriJsonProperty $candidateEvidence.fresh_output_matches $flag 'Evidence candidate fresh_output_matches'
    Assert-EvidenceBoolean $flagValue $true "Evidence candidate fresh_output_matches.$flag"
}
$pcmMarker = Get-AiriJsonProperty $candidateEvidence 'pcm_ack_write_tail_contract_markers_present' 'Evidence candidate'
Assert-EvidenceBoolean $pcmMarker $true 'Evidence candidate PCM marker state'
Assert-EvidenceBoolean $gate.full_portable_distribution_validated $false 'Evidence deployment_gate.full_portable_distribution_validated'; Assert-EvidenceBoolean $report.build.packaging.full_win_unpacked_build_passed $false 'Evidence build.packaging.full_win_unpacked_build_passed'
foreach ($pair in @(@($candidateEvidence.sha256,$gate.expected_artifact_sha256,'candidate'),@($baseline.sha256,$gate.expected_current_sha256,'installed baseline'))) { Assert-HashShape $pair[0] $pair[2]; Assert-HashShape $pair[1] ($pair[2] + ' deployment gate'); Assert-EqualValue $pair[0].ToLowerInvariant() $pair[1].ToLowerInvariant() ($pair[2] + ' hash') }
Assert-HashShape $report.executable_compatibility.installed.sha256 'Evidence installed executable SHA-256'; Assert-HashShape $report.executable_compatibility.candidate.sha256 'Evidence candidate executable SHA-256'; Assert-HashShape $report.unpacked_compatibility.candidate_manifest_sha256 'Evidence candidate unpacked manifest SHA-256'; Assert-HashShape $report.unpacked_compatibility.installed_manifest_sha256 'Evidence installed unpacked manifest SHA-256'
Assert-EvidenceInteger $report.executable_compatibility.candidate.bytes 'Evidence candidate executable bytes'; Assert-EvidenceInteger $candidateEvidence.entry_count 'Evidence candidate entry_count'
foreach ($numeric in @(@($candidateEvidence.bytes,'candidate bytes'),@($baseline.bytes,'installed baseline bytes'),@($report.executable_compatibility.installed.bytes,'installed executable bytes'),@($report.unpacked_compatibility.candidate_files,'candidate unpacked files'),@($report.unpacked_compatibility.installed_files,'installed unpacked files'),@($report.unpacked_compatibility.candidate_bytes,'candidate unpacked bytes'),@($report.unpacked_compatibility.installed_bytes,'installed unpacked bytes'))) { Assert-EvidenceInteger $numeric[0] $numeric[1] }

$artifact = Get-DigestCheckedPath $ArtifactPath 'ArtifactPath'; $candidateUnpacked = Get-DigestCheckedPath $CandidateUnpackedPath 'CandidateUnpackedPath' -Directory
$install = Get-DigestCheckedPath $InstallDir 'InstallDir' -Directory
$resources = Get-DigestCheckedPath (Join-Path $install.FullName 'resources') 'resources directory' -Directory
$current = Get-DigestCheckedPath (Join-Path $resources.FullName 'app.asar') 'installed app.asar'
$installedExe = Get-DigestCheckedPath (Join-Path $install.FullName 'airi.exe') 'installed airi.exe'
if ($artifact.CanonicalKey -eq $current.CanonicalKey -or (Test-AiriSameFile $artifact.FullName $current.FullName)) { throw 'ArtifactPath must not equal or hard-link the installed app.asar.' }
Assert-AiriAsar $artifact.FullName 'ArtifactPath'; Assert-AiriAsar $current.FullName 'installed app.asar'
$artifactDigest = Get-AiriFileDigest $artifact.FullName; $currentDigest = Get-AiriFileDigest $current.FullName; $exeDigest = Get-AiriFileDigest $installedExe.FullName
foreach ($check in @(@($artifactDigest,$candidateEvidence,'candidate app.asar'),@($currentDigest,$baseline,'installed app.asar'),@($exeDigest,$report.executable_compatibility.installed,'installed airi.exe'))) { if ($check[0].Length -ne [Int64]$check[1].bytes -or $check[0].Sha256 -cne $check[1].sha256.ToLowerInvariant()) { throw "$($check[2]) does not match evidence bytes or SHA-256." } }
Assert-EvidenceBoolean $report.executable_compatibility.fuses_equal $true 'Evidence executable_compatibility.fuses_equal'; if ($report.executable_compatibility.enable_embedded_asar_integrity_validation -ne 'Disabled' -or $report.executable_compatibility.only_load_app_from_asar -ne 'Disabled') { throw 'Evidence does not establish the required disabled Electron fuse compatibility.' }
$patchSnapshots = Assert-PatchLayers $report.source.patch_layers $RepositoryRoot
$candidateManifest = Get-UnpackedManifest $candidateUnpacked.FullName 'CandidateUnpackedPath'
$installedUnpacked = Get-DigestCheckedPath (Join-Path $resources.FullName 'app.asar.unpacked') 'installed app.asar.unpacked' -Directory
$installedManifest = Get-UnpackedManifest $installedUnpacked.FullName 'installed app.asar.unpacked'
if ($report.unpacked_compatibility.manifest_algorithm -cne 'relative path with forward slashes, TAB, decimal byte size, TAB, uppercase file SHA-256, LF; ordinal path sort; final LF; UTF-8; then SHA-256') { throw 'Evidence app.asar.unpacked manifest algorithm is not the required exact algorithm.' }
if ($candidateManifest.Sha256 -cne $report.unpacked_compatibility.candidate_manifest_sha256 -or $installedManifest.Sha256 -cne $report.unpacked_compatibility.installed_manifest_sha256 -or $candidateManifest.Files -ne [Int64]$report.unpacked_compatibility.candidate_files -or $installedManifest.Files -ne [Int64]$report.unpacked_compatibility.installed_files -or $candidateManifest.Bytes -ne [Int64]$report.unpacked_compatibility.candidate_bytes -or $installedManifest.Bytes -ne [Int64]$report.unpacked_compatibility.installed_bytes) { throw 'app.asar.unpacked manifest does not match evidence.' }
Assert-EvidenceBoolean $report.unpacked_compatibility.all_relative_paths_sizes_and_hashes_equal $true 'Evidence unpacked compatibility equality'
# Equal manifests are not enough: a cross-tree hard link would make the
# candidate validation observe bytes controlled by the installed tree.
Assert-NoCrossTreeUnpackedAlias $candidateManifest $installedManifest
$initialIdentities=[pscustomobject]@{Evidence=(Get-AiriFileIdentity $evidence.FullName);Artifact=(Get-AiriFileIdentity $artifact.FullName);Current=(Get-AiriFileIdentity $current.FullName);Exe=(Get-AiriFileIdentity $installedExe.FullName)}
Assert-NoAiriProcess $installedExe.FullName $ProcessProvider
if ($null -ne $BeforeFinalRehash) { & $BeforeFinalRehash }
foreach ($again in @(@($evidence.FullName,$evidenceDigest,'EvidencePath'),@($artifact.FullName,$artifactDigest,'ArtifactPath'),@($current.FullName,$currentDigest,'installed app.asar'),@($installedExe.FullName,$exeDigest,'installed airi.exe'))) { $now = Get-AiriFileDigest $again[0]; if ($now.Length -ne $again[1].Length -or $now.Sha256 -cne $again[1].Sha256) { throw "$($again[2]) changed during preflight." } }
$finalCandidateManifest = Get-UnpackedManifest $candidateUnpacked.FullName 'CandidateUnpackedPath'
$finalInstalledManifest = Get-UnpackedManifest $installedUnpacked.FullName 'installed app.asar.unpacked'
Assert-UnpackedSnapshotStable $candidateManifest $finalCandidateManifest 'CandidateUnpackedPath'
Assert-UnpackedSnapshotStable $installedManifest $finalInstalledManifest 'installed app.asar.unpacked'
foreach ($snapshot in $patchSnapshots) { $now=Get-DigestCheckedPath $snapshot.Path 'Evidence patch layer'; $digest=Get-AiriFileDigest $now.FullName; if ($digest.Length -ne $snapshot.Length -or $digest.Sha256 -cne $snapshot.Sha256) { throw 'Evidence patch layer changed during preflight.' } }
foreach ($identity in @(@($evidence.FullName,$initialIdentities.Evidence,'EvidencePath'),@($artifact.FullName,$initialIdentities.Artifact,'ArtifactPath'),@($current.FullName,$initialIdentities.Current,'installed app.asar'),@($installedExe.FullName,$initialIdentities.Exe,'installed airi.exe'))) { $resolved=Get-DigestCheckedPath $identity[0] $identity[2]; if ((Get-AiriFileIdentity $resolved.FullName) -ne $identity[1]) { throw "$($identity[2]) identity changed during preflight." } }
if (Test-AiriSameFile $artifact.FullName $current.FullName) { throw 'ArtifactPath became an installed app.asar alias during preflight.' }
Assert-NoCrossTreeUnpackedAlias $finalCandidateManifest $finalInstalledManifest
Assert-NoAiriProcess $installedExe.FullName $ProcessProvider
[pscustomobject]@{ AsarOnlyPreflightPassed=$true; ReadyForAuthorizedAsarOnlyInstall=$true; InstallAuthorized=$false; InstallationPerformed=$false; RequiresInstallerRevalidationAndLaunchBarrier=$true; ArtifactSha256=$artifactDigest.Sha256; ArtifactBytes=$artifactDigest.Length; CurrentSha256=$currentDigest.Sha256; CurrentBytes=$currentDigest.Length; EvidenceSha256=$evidenceDigest.Sha256; PendingExplicitInstallationAuthorization=$true; PendingRuntimeTtsDurationPitchVerification=$true; PendingTextToRenderVerification=$true; PendingPortablePackagingVerification=$true; PendingGodotVerification=$true; PendingPortableBuildVerification=$true; Scope='ASAR-only; no installation performed' }
