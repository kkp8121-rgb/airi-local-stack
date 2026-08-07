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
$airiProcesses = @(Get-Process -Name 'airi' -ErrorAction SilentlyContinue)
if ($airiProcesses.Count -gt 0) {
    $airiPids = ($airiProcesses | ForEach-Object { $_.Id }) -join ', '
    throw "AIRI is running (PID: $airiPids). Close AIRI completely and re-run; overwriting a loaded app.asar corrupts the install."
}

# --- 3. Locate the pristine backup -------------------------------------------
if ([string]::IsNullOrWhiteSpace($BackupPath)) {
    $BackupPath = "$resolvedAsar.backup-pristine"
}
if (-not (Test-Path -LiteralPath $BackupPath)) {
    throw "No pristine backup found at '$BackupPath'. Nothing to restore - reinstall AIRI 0.11.3 to get a clean app.asar."
}
$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path

# --- 4. Compare current archive with the backup ------------------------------
$currentItem = Get-Item -LiteralPath $resolvedAsar
$backupItem = Get-Item -LiteralPath $resolvedBackup

Write-Output "app.asar : $resolvedAsar ($('{0:N0}' -f $currentItem.Length) bytes)"
Write-Output "backup   : $resolvedBackup ($('{0:N0}' -f $backupItem.Length) bytes)"

if ($currentItem.Length -eq $backupItem.Length) {
    Write-Output 'Sizes match - comparing SHA-256...'
    $currentHash = (Get-FileHash -LiteralPath $resolvedAsar -Algorithm SHA256).Hash
    $backupHash = (Get-FileHash -LiteralPath $resolvedBackup -Algorithm SHA256).Hash
    if ($currentHash -eq $backupHash) {
        Write-Output "app.asar already matches the pristine backup (SHA-256 $currentHash). Nothing to restore."
        exit 0
    }
    Write-Output "Hashes differ (current $currentHash / backup $backupHash) - restoring."
}
else {
    Write-Output 'Sizes differ - restoring.'
}

# --- 5. Restore ---------------------------------------------------------------
Copy-Item -LiteralPath $resolvedBackup -Destination $resolvedAsar -Force

# --- 6. Verify ----------------------------------------------------------------
$restoredItem = Get-Item -LiteralPath $resolvedAsar
if ($restoredItem.Length -ne $backupItem.Length) {
    throw "Restore verification failed: app.asar is $($restoredItem.Length) bytes, backup is $($backupItem.Length) bytes."
}
$restoredHash = (Get-FileHash -LiteralPath $resolvedAsar -Algorithm SHA256).Hash
$backupHash = (Get-FileHash -LiteralPath $resolvedBackup -Algorithm SHA256).Hash
if ($restoredHash -ne $backupHash) {
    throw "Restore verification failed: SHA-256 mismatch (app.asar $restoredHash / backup $backupHash)."
}

Write-Output "Restored app.asar from the pristine backup (SHA-256 $restoredHash)."
Write-Output 'Re-apply the patch set with .\apply-airi-patches.ps1 when needed.'
exit 0
