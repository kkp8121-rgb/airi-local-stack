#Requires -Version 5.1
<#
.SYNOPSIS
    Disables Chromium's microphone DSP (AGC / echo cancellation / noise
    suppression) so the STT provider receives raw capture.

.DESCRIPTION
    Equal-length, in-place edit of the installed app.asar (no repack). The two
    constraint blocks are rewritten from `true` to `!1` plus padding.

    Backup: this script participates in the shared pristine backup contract -
    a single app.asar.backup-pristine copy is taken by whichever patch runs
    first while app.asar is still stock, instead of one 1.05 GiB copy per
    script. Restore with .\restore-airi-original.ps1.

.PARAMETER AsarPath
    Path to the installed AIRI app.asar.

.PARAMETER Force
    Continue when app.asar is in an unrecognized state (no pristine backup and
    no stock markers). No backup is created in that case.
#>
param(
    [string]$AsarPath = "$env:LOCALAPPDATA\Programs\airi\resources\app.asar",
    [switch]$Force,
    [switch]$InternalOrchestrator
)

$ErrorActionPreference = 'Stop'
if (-not $InternalOrchestrator) {
    throw 'This patch step is internal; run .\apply-airi-patches.ps1.'
}

# --- 1. Resolve and validate the target archive ------------------------------
$resolvedAsar = (Resolve-Path -LiteralPath $AsarPath).Path
if ([System.IO.Path]::GetFileName($resolvedAsar) -ne 'app.asar') {
    throw "Expected app.asar, got: $resolvedAsar"
}
$resourcesDir = Split-Path -Parent $resolvedAsar
if ((Split-Path -Leaf $resourcesDir) -ne 'resources') {
    throw "Refusing to patch an archive outside an AIRI 'resources' directory: $resolvedAsar"
}
$installDir = Split-Path -Parent $resourcesDir
if (-not (Test-Path -LiteralPath (Join-Path $installDir 'airi.exe'))) {
    throw "Refusing to patch: '$installDir' does not look like an AIRI installation (airi.exe not found)."
}

# --- 2. AIRI must not be running ---------------------------------------------
$airiProcesses = @(Get-Process -Name 'airi' -ErrorAction SilentlyContinue)
if ($airiProcesses.Count -gt 0) {
    $airiPids = ($airiProcesses | ForEach-Object { $_.Id }) -join ', '
    throw "AIRI is running (PID: $airiPids). Close AIRI completely and re-run; patching a loaded app.asar corrupts the install."
}

if (-not ('EqualLengthBinaryPatcher' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public static class EqualLengthBinaryPatcher
{
    private static List<long> FindAll(FileStream stream, byte[] pattern)
    {
        const int chunkSize = 4 * 1024 * 1024;
        byte[] buffer = new byte[chunkSize + pattern.Length - 1];
        var positions = new List<long>();
        int carry = 0;
        long bufferBase = 0;

        stream.Position = 0;
        while (true)
        {
            int read = stream.Read(buffer, carry, chunkSize);
            int total = carry + read;
            if (total == 0)
                break;

            int searchLimit = total - pattern.Length;
            for (int index = 0; index <= searchLimit; index++)
            {
                bool matches = true;
                for (int offset = 0; offset < pattern.Length; offset++)
                {
                    if (buffer[index + offset] != pattern[offset])
                    {
                        matches = false;
                        break;
                    }
                }
                if (matches)
                    positions.Add(bufferBase + index);
            }

            if (read == 0)
                break;

            carry = Math.Min(pattern.Length - 1, total);
            Buffer.BlockCopy(buffer, total - carry, buffer, 0, carry);
            bufferBase += total - carry;
        }

        return positions;
    }

    public static int CountOccurrences(string path, string text)
    {
        byte[] pattern = Encoding.UTF8.GetBytes(text);
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            return FindAll(stream, pattern).Count;
    }

    public static int PatchExactly(string path, string oldText, string newText, int expectedCount)
    {
        byte[] oldBytes = Encoding.UTF8.GetBytes(oldText);
        byte[] newBytes = Encoding.UTF8.GetBytes(newText);
        if (oldBytes.Length != newBytes.Length)
            throw new InvalidOperationException("Replacement must have exactly the same byte length.");

        using (var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            List<long> oldPositions = FindAll(stream, oldBytes);
            if (oldPositions.Count == 0)
            {
                List<long> newPositions = FindAll(stream, newBytes);
                if (newPositions.Count == expectedCount)
                    return 0;
            }
            if (oldPositions.Count != expectedCount)
                throw new InvalidOperationException(string.Format(
                    "Expected {0} matching audio constraint blocks, found {1}.",
                    expectedCount,
                    oldPositions.Count
                ));

            foreach (long position in oldPositions)
            {
                stream.Position = position;
                stream.Write(newBytes, 0, newBytes.Length);
            }
            stream.Flush(true);

            List<long> remainingOld = FindAll(stream, oldBytes);
            List<long> writtenNew = FindAll(stream, newBytes);
            if (remainingOld.Count != 0 || writtenNew.Count != expectedCount)
                throw new InvalidOperationException("Post-patch verification failed.");

            return oldPositions.Count;
        }
    }
}
'@
}

function Get-MarkerCount([string]$Text) {
    return [EqualLengthBinaryPatcher]::CountOccurrences($resolvedAsar, $Text)
}

function Test-MarkersPresent([string[]]$Markers) {
    foreach ($marker in $Markers) {
        if ((Get-MarkerCount $marker) -lt 1) { return $false }
    }
    return $true
}

# The bundle uses LF line endings. These patterns MUST NOT be built from a
# here-string: PowerShell keeps a here-string's literal newlines, so in a
# CRLF-saved .ps1 the pattern becomes "...,\r\n\t\techoCancellation..." and
# never matches the LF bundle. Measured on the stock 0.11.3 app.asar:
#   CRLF form -> 0 hits, LF form -> 2 hits.
# Explicit `n escapes keep the pattern correct regardless of how this file is
# checked out or saved.
$enabledBlock = "autoGainControl: true,`n`t`techoCancellation: true,`n`t`tnoiseSuppression: true"
$disabledBlock = "autoGainControl: !1  ,`n`t`techoCancellation: !1  ,`n`t`tnoiseSuppression: !1  "

# --- 3. Pristine backup contract (shared by every patch-airi-*.ps1) ----------
# Verified against the stock 0.11.3 install (app.asar, 1,130,829,614 bytes):
#   enabled constraint block -> 2 hits @ 868,084,859 and 868,084,942
$pristineBackupPath = "$resolvedAsar.backup-pristine"
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup exists - skipping the backup copy: $pristineBackupPath"
}
elseif (Test-MarkersPresent @($enabledBlock)) {
    Copy-Item -LiteralPath $resolvedAsar -Destination $pristineBackupPath
    Write-Output "Created pristine backup: $pristineBackupPath"
}
elseif ($Force) {
    Write-Warning 'No pristine backup exists and app.asar no longer carries this patch''s stock markers. Continuing without a backup because -Force was supplied.'
}
else {
    throw "No pristine backup exists and app.asar no longer carries this patch's stock markers, so a backup taken now would not be pristine. Run .\restore-airi-original.ps1 (or reinstall AIRI) and retry, or pass -Force to patch without a backup."
}

# --- 4. Patch ----------------------------------------------------------------
$patchedCount = [EqualLengthBinaryPatcher]::PatchExactly(
    $resolvedAsar,
    $enabledBlock,
    $disabledBlock,
    2
)

if ($patchedCount -eq 0) {
    Write-Output "AIRI raw microphone constraints were already patched."
}
else {
    Write-Output "Patched $patchedCount AIRI microphone constraint blocks."
}
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup: $pristineBackupPath"
}
else {
    Write-Warning "No pristine backup exists for this install; .\restore-airi-original.ps1 cannot undo these edits."
}
