#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$ArtifactPath,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$InstallDir,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ExpectedArtifactSha256,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ExpectedCurrentSha256,
    [switch]$EnableTestHooks,
    [switch]$TestOnlyFailAfterReplace
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'airi-source-asar-deploy-common.ps1')

if ($TestOnlyFailAfterReplace -and -not $EnableTestHooks) {
    throw 'TestOnlyFailAfterReplace requires EnableTestHooks.'
}

function Resolve-AiriInstallLayout {
    param([Parameter(Mandatory)][string]$RequestedInstallDir)

    $install = Get-AiriNormalPath -Path $RequestedInstallDir -Description 'InstallDir' -Directory
    $resources = Get-AiriNormalPath -Path (Join-Path $install.FullName 'resources') -Description 'resources directory' -Directory
    $executable = Get-AiriNormalPath -Path (Join-Path $install.FullName 'airi.exe') -Description 'airi.exe'
    $target = Get-AiriNormalPath -Path (Join-Path $resources.FullName 'app.asar') -Description 'target app.asar'
    [pscustomobject]@{
        Install = $install
        Resources = $resources
        Executable = $executable
        Target = $target
    }
}

$expectedArtifact = $ExpectedArtifactSha256.ToLowerInvariant()
$expectedCurrent = $ExpectedCurrentSha256.ToLowerInvariant()
$initialLayout = Resolve-AiriInstallLayout -RequestedInstallDir $InstallDir
$initialArtifact = Get-AiriNormalPath -Path $ArtifactPath -Description 'ArtifactPath'
if (Test-AiriSameFile -First $initialArtifact.FullName -Second $initialLayout.Target.FullName) {
    throw 'ArtifactPath must not be the installed target app.asar.'
}

$initialArtifactDigest = Get-AiriFileDigest -Path $initialArtifact.FullName
if ($initialArtifactDigest.Sha256 -ne $expectedArtifact) {
    throw 'ArtifactPath SHA-256 does not match ExpectedArtifactSha256.'
}
Assert-AiriAsar -Path $initialArtifact.FullName -Description 'ArtifactPath'
Assert-AiriAsar -Path $initialLayout.Target.FullName -Description 'target app.asar'
Assert-AiriStopped -ExecutablePath $initialLayout.Executable.FullName -Operation 'deployment'

$mutexState = $null
$barrier = $null
$stagePath = $null
$backupPath = $null
$currentDigest = $null
try {
    $mutexState = Enter-AiriDeploymentMutex -CanonicalTargetPath $initialLayout.Target.CanonicalKey

    # Resolve every caller-controlled path again after acquiring the lock. The
    # no-reparse-ancestor rule makes the canonical string a stable path owner.
    $layout = Resolve-AiriInstallLayout -RequestedInstallDir $InstallDir
    $artifact = Get-AiriNormalPath -Path $ArtifactPath -Description 'ArtifactPath'
    if ($layout.Target.CanonicalKey -ne $initialLayout.Target.CanonicalKey -or
        $artifact.CanonicalKey -ne $initialArtifact.CanonicalKey) {
        throw 'A deployment path changed while waiting for the deployment lock.'
    }
    if (Test-AiriSameFile -First $artifact.FullName -Second $layout.Target.FullName) {
        throw 'ArtifactPath must not be the installed target app.asar.'
    }

    $barrier = Enter-AiriExecutableBarrier -ExecutablePath $layout.Executable.FullName -Operation 'deployment'

    $artifactDigest = Get-AiriFileDigest -Path $artifact.FullName
    if ($artifactDigest.Sha256 -ne $expectedArtifact) {
        throw 'ArtifactPath changed or does not match ExpectedArtifactSha256.'
    }
    Assert-AiriAsar -Path $artifact.FullName -Description 'ArtifactPath'

    $currentDigest = Get-AiriFileDigest -Path $layout.Target.FullName
    Assert-AiriAsar -Path $layout.Target.FullName -Description 'target app.asar'
    if ($currentDigest.Sha256 -eq $artifactDigest.Sha256 -and $currentDigest.Length -eq $artifactDigest.Length) {
        [pscustomobject]@{
            Action = 'AlreadyInstalled'
            ArtifactSha256 = $artifactDigest.Sha256
            TargetSha256 = $currentDigest.Sha256
            BackupPath = $null
        }
        return
    }
    if ($currentDigest.Sha256 -ne $expectedCurrent) {
        throw 'Current app.asar SHA-256 does not match ExpectedCurrentSha256.'
    }

    $stage = New-AiriVerifiedStage -Source $artifact.FullName -TargetDirectory $layout.Resources.FullName `
        -Prefix '.app.asar.install-stage-' -ExpectedLength $artifactDigest.Length `
        -ExpectedSha256 $artifactDigest.Sha256
    $stagePath = $stage.Path

    # A non-cooperating writer can ignore our mutex. Pin the target again at
    # the final boundary; File.Replace's persistent backup closes the remaining
    # race interval and captures the exact displaced bytes.
    $targetRecheck = Get-AiriFileDigest -Path $layout.Target.FullName
    if ($targetRecheck.Sha256 -ne $currentDigest.Sha256 -or $targetRecheck.Length -ne $currentDigest.Length) {
        throw 'Target app.asar changed before replacement.'
    }
    Assert-AiriAsar -Path $layout.Target.FullName -Description 'target app.asar'

    $backupPath = Join-Path $layout.Resources.FullName (
        'app.asar.airi-rollback-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfffffff') + '-' +
        $currentDigest.Sha256.Substring(0, 16) + '-' + [guid]::NewGuid().ToString('N') + '.bak')

    try {
        [IO.File]::Replace($stagePath, $layout.Target.FullName, $backupPath, $true)
        $stagePath = $null

        $displaced = Get-AiriNormalPath -Path $backupPath -Description 'exact displaced rollback archive'
        $displacedDigest = Get-AiriFileDigest -Path $displaced.FullName
        if ($displacedDigest.Sha256 -ne $currentDigest.Sha256 -or $displacedDigest.Length -ne $currentDigest.Length) {
            throw 'The exact displaced archive does not match the pinned current app.asar.'
        }
        Assert-AiriAsar -Path $displaced.FullName -Description 'exact displaced rollback archive'

        $installedDigest = Get-AiriFileDigest -Path $layout.Target.FullName
        Assert-AiriAsar -Path $layout.Target.FullName -Description 'installed app.asar'
        if ($installedDigest.Sha256 -ne $artifactDigest.Sha256 -or $installedDigest.Length -ne $artifactDigest.Length) {
            throw 'Installed app.asar does not match the staged artifact.'
        }
        if ($TestOnlyFailAfterReplace) {
            throw 'Test-only post-replace failure requested.'
        }
    }
    catch {
        $deploymentError = $_
        if (Test-Path -LiteralPath $backupPath) {
            $exactDisplacedDigest = Get-AiriFileDigest -Path $backupPath
            $targetNow = Get-AiriFileDigest -Path $layout.Target.FullName
            $failedCandidatePath = $null
            if ($targetNow.Sha256 -ne $exactDisplacedDigest.Sha256 -or $targetNow.Length -ne $exactDisplacedDigest.Length) {
                $rollback = Restore-AiriExactDisplacedFile -DisplacedPath $backupPath `
                    -TargetPath $layout.Target.FullName -TargetDirectory $layout.Resources.FullName `
                    -DisplacedDigest $exactDisplacedDigest
                $failedCandidatePath = $rollback.FailedCandidatePath
            }
            $rolledBack = Get-AiriFileDigest -Path $layout.Target.FullName
            if ($rolledBack.Sha256 -ne $exactDisplacedDigest.Sha256 -or $rolledBack.Length -ne $exactDisplacedDigest.Length) {
                throw "Deployment failed and exact rollback verification failed. $($deploymentError.Exception.Message)"
            }
            throw "Deployment failed; the exact displaced archive was restored and retained at '$backupPath'. Failed candidate: '$failedCandidatePath'. $($deploymentError.Exception.Message)"
        }

        $targetAfterFailure = Get-AiriFileDigest -Path $layout.Target.FullName
        if ($null -eq $currentDigest -or $targetAfterFailure.Sha256 -ne $currentDigest.Sha256 -or
            $targetAfterFailure.Length -ne $currentDigest.Length) {
            throw "Deployment failed without an exact displaced backup and target identity changed. $($deploymentError.Exception.Message)"
        }
        throw "Deployment failed before target replacement. $($deploymentError.Exception.Message)"
    }

    [pscustomobject]@{
        Action = 'Installed'
        ArtifactSha256 = $artifactDigest.Sha256
        TargetSha256 = $artifactDigest.Sha256
        BackupPath = $backupPath
        BackupSha256 = $currentDigest.Sha256
    }
}
finally {
    if ($null -ne $stagePath -and (Test-Path -LiteralPath $stagePath)) {
        Remove-Item -LiteralPath $stagePath -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $barrier) { $barrier.Dispose() }
    Exit-AiriDeploymentMutex -MutexState $mutexState
}
