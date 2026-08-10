#Requires -Version 5.1
<#
.SYNOPSIS
    Restores the installed AIRI app.asar from app.asar.backup-pristine.

.DESCRIPTION
    Undo for the patch-airi-*.ps1 set and apply-airi-patches.ps1. The pristine
    backup is taken once, by whichever patch runs first while app.asar is still
    stock, so restoring it returns the install to its as-shipped state.

    Safety:
      * refuses to run while AIRI is running
      * refuses to run when no pristine backup exists
      * skips the copy when app.asar already matches the backup byte for byte
      * verifies size and SHA-256 after copying

.PARAMETER InstallDir
    AIRI installation directory. Default: %LOCALAPPDATA%\Programs\airi

.PARAMETER BackupPath
    Override the backup file. Default: <InstallDir>\resources\app.asar.backup-pristine

.EXAMPLE
    .\restore-airi-original.ps1
#>
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\airi",
    [string]$BackupPath
)

$ErrorActionPreference = 'Stop'
$knownPristineAsarSha256 = 'B3433A29D2E8357A84068DFFCAD80A2A23A4D4C0F5F803764C66839C84B788AF'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Assert-AiriNotRunning {
    $processes = @(Get-Process -Name 'airi' -ErrorAction SilentlyContinue)
    if ($processes.Count -gt 0) {
        $pids = ($processes | ForEach-Object { $_.Id }) -join ', '
        throw "AIRI is running (PID: $pids). Close AIRI completely before replacing app.asar."
    }
}

# --- 1. Resolve and validate the installation --------------------------------
if (-not (Test-Path -LiteralPath $InstallDir)) {
    throw "AIRI installation directory not found: $InstallDir"
}
$resolvedInstallDir = (Resolve-Path -LiteralPath $InstallDir).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedInstallDir 'airi.exe'))) {
    throw "'$resolvedInstallDir' does not look like an AIRI installation (airi.exe not found)."
}
$asarPath = Join-Path $resolvedInstallDir 'resources\app.asar'
if (-not (Test-Path -LiteralPath $asarPath)) {
    throw "app.asar not found: $asarPath"
}
$resolvedAsar = (Resolve-Path -LiteralPath $asarPath).Path

# --- 2. AIRI must not be running ---------------------------------------------
# Checked before the backup lookup so the guard message is the same regardless
# of whether a backup happens to exist.
Assert-AiriNotRunning

# --- 3. Locate the pristine backup -------------------------------------------
if ([string]::IsNullOrWhiteSpace($BackupPath)) {
    $BackupPath = "$resolvedAsar.backup-pristine"
}
if (-not (Test-Path -LiteralPath $BackupPath)) {
    throw "No pristine backup found at '$BackupPath'. Nothing to restore - reinstall AIRI 0.11.3 to get a clean app.asar."
}
$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
$backupItem = Get-Item -LiteralPath $resolvedBackup
if ($backupItem.PSIsContainer -or (($backupItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
    throw "Pristine backup is not a regular non-reparse file: $resolvedBackup"
}
$backupHash = Get-Sha256 $resolvedBackup
if ($backupHash -ne $knownPristineAsarSha256) {
    throw "Pristine backup SHA-256 mismatch: got $backupHash, expected $knownPristineAsarSha256. Refusing to restore."
}

# --- 4. Compare current archive with the backup ------------------------------
$currentItem = Get-Item -LiteralPath $resolvedAsar
Write-Output "app.asar : $resolvedAsar ($('{0:N0}' -f $currentItem.Length) bytes)"
Write-Output "backup   : $resolvedBackup ($('{0:N0}' -f $backupItem.Length) bytes)"

if ($currentItem.Length -eq $backupItem.Length) {
    Write-Output 'Sizes match - comparing SHA-256...'
    $currentHash = Get-Sha256 $resolvedAsar
    if ($currentHash -eq $backupHash) {
        Write-Output "app.asar already matches the pristine backup (SHA-256 $currentHash). Nothing to restore."
        exit 0
    }
    Write-Output "Hashes differ (current $currentHash / backup $backupHash) - restoring."
}
else {
    Write-Output 'Sizes differ - restoring.'
}

# --- 5. Restore atomically ----------------------------------------------------
$temporaryRestorePath = Join-Path (Split-Path -Parent $resolvedAsar) ('.app.asar.restore-{0}.tmp' -f ([guid]::NewGuid().ToString('N')))
try {
    Copy-Item -LiteralPath $resolvedBackup -Destination $temporaryRestorePath -Force
    $temporaryHash = Get-Sha256 $temporaryRestorePath
    if ($temporaryHash -ne $backupHash) {
        throw "Restore staging SHA-256 mismatch: staged $temporaryHash, backup $backupHash."
    }
    Assert-AiriNotRunning
    [System.IO.File]::Replace($temporaryRestorePath, $resolvedAsar, $null, $true)
}
finally {
    if (Test-Path -LiteralPath $temporaryRestorePath) {
        Remove-Item -LiteralPath $temporaryRestorePath -Force -ErrorAction SilentlyContinue
    }
}

# --- 6. Verify ----------------------------------------------------------------
$restoredItem = Get-Item -LiteralPath $resolvedAsar
if ($restoredItem.Length -ne $backupItem.Length) {
    throw "Restore verification failed: app.asar is $($restoredItem.Length) bytes, backup is $($backupItem.Length) bytes."
}
$restoredHash = Get-Sha256 $resolvedAsar
if ($restoredHash -ne $backupHash) {
    throw "Restore verification failed: SHA-256 mismatch (app.asar $restoredHash / backup $backupHash)."
}

Write-Output "Restored app.asar from the pristine backup (SHA-256 $restoredHash)."
Write-Output 'Re-apply the patch set with .\apply-airi-patches.ps1 when needed.'
exit 0
