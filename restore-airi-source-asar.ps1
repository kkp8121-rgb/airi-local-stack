#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$InstallDir,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$BackupPath,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ExpectedBackupSha256,
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

function Resolve-AiriRestoreLayout {
    param(
        [Parameter(Mandatory)][string]$RequestedInstallDir,
        [Parameter(Mandatory)][string]$RequestedBackupPath
    )

    $install = Get-AiriNormalPath -Path $RequestedInstallDir -Description 'InstallDir' -Directory
    $resources = Get-AiriNormalPath -Path (Join-Path $install.FullName 'resources') -Description 'resources directory' -Directory
    $executable = Get-AiriNormalPath -Path (Join-Path $install.FullName 'airi.exe') -Description 'airi.exe'
    $target = Get-AiriNormalPath -Path (Join-Path $resources.FullName 'app.asar') -Description 'target app.asar'
    $backup = Get-AiriNormalPath -Path $RequestedBackupPath -Description 'BackupPath'
    if ($backup.CanonicalKey -eq $target.CanonicalKey -or
        (Test-AiriSameFile -First $backup.FullName -Second $target.FullName)) {
        throw 'BackupPath must not be the target app.asar or a hard-link alias of it.'
    }
    [pscustomobject]@{
        Install = $install
        Resources = $resources
        Executable = $executable
        Target = $target
        Backup = $backup
    }
}

$expectedBackup = $ExpectedBackupSha256.ToLowerInvariant()
$expectedCurrent = $ExpectedCurrentSha256.ToLowerInvariant()
$initial = Resolve-AiriRestoreLayout -RequestedInstallDir $InstallDir -RequestedBackupPath $BackupPath
Assert-AiriStopped -ExecutablePath $initial.Executable.FullName -Operation 'restore'

$mutexState = $null
$barrier = $null
$stagePath = $null
$preRestoreBackupPath = $null
$currentDigest = $null
try {
    # All archive reads, including the idempotent decision, occur under the
    # same cross-session lock as install.
    $mutexState = Enter-AiriDeploymentMutex -CanonicalTargetPath $initial.Target.CanonicalKey
    $layout = Resolve-AiriRestoreLayout -RequestedInstallDir $InstallDir -RequestedBackupPath $BackupPath
    if ($layout.Target.CanonicalKey -ne $initial.Target.CanonicalKey -or
        $layout.Backup.CanonicalKey -ne $initial.Backup.CanonicalKey) {
        throw 'A restore path changed while waiting for the deployment lock.'
    }

    $barrier = Enter-AiriExecutableBarrier -ExecutablePath $layout.Executable.FullName -Operation 'restore'

    $backupDigest = Get-AiriFileDigest -Path $layout.Backup.FullName
    if ($backupDigest.Sha256 -ne $expectedBackup) {
        throw 'BackupPath SHA-256 does not match ExpectedBackupSha256.'
    }
    Assert-AiriAsar -Path $layout.Backup.FullName -Description 'BackupPath'

    $currentDigest = Get-AiriFileDigest -Path $layout.Target.FullName
    Assert-AiriAsar -Path $layout.Target.FullName -Description 'target app.asar'

    # A literal retry of a successful restore still carries the pre-restore
    # ExpectedCurrentSha256. The independently pinned backup digest is enough
    # to prove the requested end state before consulting that old precondition.
    if ($currentDigest.Sha256 -eq $backupDigest.Sha256 -and $currentDigest.Length -eq $backupDigest.Length) {
        [pscustomobject]@{
            Action = 'AlreadyRestored'
            TargetSha256 = $currentDigest.Sha256
            BackupSha256 = $backupDigest.Sha256
            BackupPath = $layout.Backup.FullName
        }
        return
    }
    if ($currentDigest.Sha256 -ne $expectedCurrent) {
        throw 'Current app.asar SHA-256 does not match ExpectedCurrentSha256.'
    }

    $stage = New-AiriVerifiedStage -Source $layout.Backup.FullName -TargetDirectory $layout.Resources.FullName `
        -Prefix '.app.asar.restore-stage-' -ExpectedLength $backupDigest.Length `
        -ExpectedSha256 $backupDigest.Sha256
    $stagePath = $stage.Path

    $targetRecheck = Get-AiriFileDigest -Path $layout.Target.FullName
    if ($targetRecheck.Sha256 -ne $currentDigest.Sha256 -or $targetRecheck.Length -ne $currentDigest.Length) {
        throw 'Target app.asar changed before restore replacement.'
    }
    Assert-AiriAsar -Path $layout.Target.FullName -Description 'target app.asar'

    $preRestoreBackupPath = Join-Path $layout.Resources.FullName (
        'app.asar.airi-pre-restore-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfffffff') + '-' +
        $currentDigest.Sha256.Substring(0, 16) + '-' + [guid]::NewGuid().ToString('N') + '.bak')

    try {
        [IO.File]::Replace($stagePath, $layout.Target.FullName, $preRestoreBackupPath, $true)
        $stagePath = $null

        $displaced = Get-AiriNormalPath -Path $preRestoreBackupPath -Description 'exact pre-restore archive'
        $displacedDigest = Get-AiriFileDigest -Path $displaced.FullName
        if ($displacedDigest.Sha256 -ne $currentDigest.Sha256 -or $displacedDigest.Length -ne $currentDigest.Length) {
            throw 'The exact pre-restore archive does not match the pinned current app.asar.'
        }
        Assert-AiriAsar -Path $displaced.FullName -Description 'exact pre-restore archive'

        $restoredDigest = Get-AiriFileDigest -Path $layout.Target.FullName
        Assert-AiriAsar -Path $layout.Target.FullName -Description 'restored app.asar'
        if ($restoredDigest.Sha256 -ne $backupDigest.Sha256 -or $restoredDigest.Length -ne $backupDigest.Length) {
            throw 'Restored app.asar does not match BackupPath.'
        }
        if ($TestOnlyFailAfterReplace) {
            throw 'Test-only post-replace failure requested.'
        }
    }
    catch {
        $restoreError = $_
        if (Test-Path -LiteralPath $preRestoreBackupPath) {
            $exactDisplacedDigest = Get-AiriFileDigest -Path $preRestoreBackupPath
            $targetNow = Get-AiriFileDigest -Path $layout.Target.FullName
            $failedCandidatePath = $null
            if ($targetNow.Sha256 -ne $exactDisplacedDigest.Sha256 -or $targetNow.Length -ne $exactDisplacedDigest.Length) {
                $rollback = Restore-AiriExactDisplacedFile -DisplacedPath $preRestoreBackupPath `
                    -TargetPath $layout.Target.FullName -TargetDirectory $layout.Resources.FullName `
                    -DisplacedDigest $exactDisplacedDigest
                $failedCandidatePath = $rollback.FailedCandidatePath
            }
            $rolledBack = Get-AiriFileDigest -Path $layout.Target.FullName
            if ($rolledBack.Sha256 -ne $exactDisplacedDigest.Sha256 -or $rolledBack.Length -ne $exactDisplacedDigest.Length) {
                throw "Restore failed and exact pre-restore rollback verification failed. $($restoreError.Exception.Message)"
            }
            throw "Restore failed; the exact pre-restore archive was restored and retained at '$preRestoreBackupPath'. Failed candidate: '$failedCandidatePath'. $($restoreError.Exception.Message)"
        }

        $targetAfterFailure = Get-AiriFileDigest -Path $layout.Target.FullName
        if ($null -eq $currentDigest -or $targetAfterFailure.Sha256 -ne $currentDigest.Sha256 -or
            $targetAfterFailure.Length -ne $currentDigest.Length) {
            throw "Restore failed without an exact pre-restore backup and target identity changed. $($restoreError.Exception.Message)"
        }
        throw "Restore failed before target replacement. $($restoreError.Exception.Message)"
    }

    [pscustomobject]@{
        Action = 'Restored'
        TargetSha256 = $backupDigest.Sha256
        BackupSha256 = $backupDigest.Sha256
        BackupPath = $layout.Backup.FullName
        PreRestoreBackupPath = $preRestoreBackupPath
        PreRestoreSha256 = $currentDigest.Sha256
    }
}
finally {
    if ($null -ne $stagePath -and (Test-Path -LiteralPath $stagePath)) {
        Remove-Item -LiteralPath $stagePath -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $barrier) { $barrier.Dispose() }
    Exit-AiriDeploymentMutex -MutexState $mutexState
}
