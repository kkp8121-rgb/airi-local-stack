#Requires -Version 5.1
<#
.SYNOPSIS
    Replaces AIRI's WAV-encoding recorder with a native MediaRecorder that emits
    Opus/WebM.

.DESCRIPTION
    Overwrites the useAudioRecorder region of the installed app.asar with the
    minified replacement in airi-native-media-recorder.min.js, padding the rest
    of the region with spaces so the asar is never repacked.

    Idempotency: the region's start marker is consumed by the first run, so a
    second run would fail on "found 0 starts". The script therefore checks for a
    marker unique to the replacement (audioBitsPerSecond:128e3, absent from
    stock) and exits 0 when the patch is already in place.

    Backup: this script participates in the shared pristine backup contract -
    a single app.asar.backup-pristine copy is taken by whichever patch runs
    first while app.asar is still stock, instead of one 1.05 GiB copy per
    script. Restore with .\restore-airi-original.ps1.

.PARAMETER AsarPath
    Path to the installed AIRI app.asar.

.PARAMETER ReplacementPath
    Minified recorder implementation written into the region.

.PARAMETER Force
    Continue when app.asar is in an unrecognized state (no pristine backup and
    no stock markers). No backup is created in that case.
#>
param(
    [string]$AsarPath = "$env:LOCALAPPDATA\Programs\airi\resources\app.asar",
    [string]$ReplacementPath = "$PSScriptRoot\airi-native-media-recorder.min.js",
    [switch]$Force,
    [switch]$InternalOrchestrator
)

$ErrorActionPreference = 'Stop'
if (-not $InternalOrchestrator) {
    throw 'This patch step is internal; run .\apply-airi-patches.ps1.'
}

# --- 1. Resolve and validate the target archive ------------------------------
$resolvedAsar = (Resolve-Path -LiteralPath $AsarPath).Path
$resolvedReplacement = (Resolve-Path -LiteralPath $ReplacementPath).Path
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

if (-not ('AsarRegionPatcher' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public static class AsarRegionPatcher
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

    public static long PatchRegion(string path, string startMarker, string endMarker, string replacement)
    {
        byte[] startBytes = Encoding.UTF8.GetBytes(startMarker);
        byte[] endBytes = Encoding.UTF8.GetBytes(endMarker);
        byte[] replacementBytes = Encoding.UTF8.GetBytes(replacement);

        using (var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            List<long> starts = FindAll(stream, startBytes);
            List<long> ends = FindAll(stream, endBytes);
            if (starts.Count != 1 || ends.Count != 1 || ends[0] <= starts[0])
                throw new InvalidOperationException(string.Format(
                    "Expected one recorder region, found {0} starts and {1} ends.",
                    starts.Count,
                    ends.Count
                ));

            long regionLengthLong = ends[0] - starts[0];
            if (regionLengthLong > int.MaxValue)
                throw new InvalidOperationException("Recorder region is unexpectedly large.");
            int regionLength = (int)regionLengthLong;
            if (replacementBytes.Length > regionLength)
                throw new InvalidOperationException(string.Format(
                    "Replacement is {0} bytes but only {1} bytes are available.",
                    replacementBytes.Length,
                    regionLength
                ));

            byte[] padded = new byte[regionLength];
            for (int index = 0; index < padded.Length; index++)
                padded[index] = 0x20;
            Buffer.BlockCopy(replacementBytes, 0, padded, 0, replacementBytes.Length);

            stream.Position = starts[0];
            stream.Write(padded, 0, padded.Length);
            stream.Flush(true);

            byte[] verification = new byte[replacementBytes.Length];
            stream.Position = starts[0];
            int verified = stream.Read(verification, 0, verification.Length);
            if (verified != verification.Length)
                throw new InvalidOperationException("Could not read the patched recorder for verification.");
            for (int index = 0; index < verification.Length; index++)
                if (verification[index] != replacementBytes[index])
                    throw new InvalidOperationException("Native recorder post-patch verification failed.");

            return regionLength;
        }
    }
}
'@
}

function Get-MarkerCount([string]$Text) {
    return [AsarRegionPatcher]::CountOccurrences($resolvedAsar, $Text)
}

function Test-MarkersPresent([string[]]$Markers) {
    foreach ($marker in $Markers) {
        if ((Get-MarkerCount $marker) -lt 1) { return $false }
    }
    return $true
}

$replacement = Get-Content -LiteralPath $resolvedReplacement -Raw -Encoding UTF8

# --- 3. Patch targets --------------------------------------------------------
# Verified against the stock 0.11.3 install (app.asar, 1,130,829,614 bytes):
#   "function useAudioRecorder(media) {"      -> 1 hit @ 868,203,257
#   "<LF>//#endregion<LF>//#region .../vad.ts" -> 1 hit @ 868,205,384
#   region length 2,127 bytes; replacement 2,075 bytes -> fits with padding
#   "audioBitsPerSecond:128e3"                -> 0 hits (unique to the patch)
$startMarker = 'function useAudioRecorder(media) {'
$endMarker = "`n//#endregion`n//#region ../../packages/stage-ui/src/libs/audio/vad.ts"
$patchedMarker = 'audioBitsPerSecond:128e3'

# --- 4. Idempotency: the start marker is consumed by the first run ------------
# This check must run BEFORE the backup block: an already-patched archive is not
# pristine, so taking a backup here would capture a patched copy.
if ((Get-MarkerCount $patchedMarker) -gt 0) {
    Write-Output 'AIRI native MediaRecorder replacement is already applied - nothing to do.'
    # Return from the child script so an orchestrator invoking this file can
    # continue with the remaining patch sites. `exit` would terminate the
    # hosting PowerShell process instead of returning to apply-airi-patches.ps1.
    return
}

# --- 5. Pristine backup contract (shared by every patch-airi-*.ps1) ----------
$pristineBackupPath = "$resolvedAsar.backup-pristine"
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup exists - skipping the backup copy: $pristineBackupPath"
}
elseif (Test-MarkersPresent @($startMarker, $endMarker)) {
    Copy-Item -LiteralPath $resolvedAsar -Destination $pristineBackupPath
    Write-Output "Created pristine backup: $pristineBackupPath"
}
elseif ($Force) {
    Write-Warning 'No pristine backup exists and app.asar no longer carries this patch''s stock markers. Continuing without a backup because -Force was supplied.'
}
else {
    throw "No pristine backup exists and app.asar no longer carries this patch's stock markers, so a backup taken now would not be pristine. Run .\restore-airi-original.ps1 (or reinstall AIRI) and retry, or pass -Force to patch without a backup."
}

# --- 6. Patch ----------------------------------------------------------------
$regionLength = [AsarRegionPatcher]::PatchRegion(
    $resolvedAsar,
    $startMarker,
    $endMarker,
    $replacement
)

Write-Output "Replaced the AIRI recorder region ($regionLength bytes) with native MediaRecorder."
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup: $pristineBackupPath"
}
else {
    Write-Warning "No pristine backup exists for this install; .\restore-airi-original.ps1 cannot undo these edits."
}
