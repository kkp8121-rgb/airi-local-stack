#Requires -Version 5.1
<#
.SYNOPSIS
    Widens AIRI's volume-fallback stop timer so VAD, not the fallback, ends a
    voice segment.

.DESCRIPTION
    Stock AIRI runs two independent segment terminators on the same recording:

      1. Silero VAD (packages/stage-ui/src/stores/ai/models/vad.ts)
      2. A volume-RMS fallback timer inside useVoiceInputSession
         (DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS = 900 ms)

    The fallback branch fires for BOTH triggers ('volume' and 'vad'), so with
    the VAD silence window reduced to 450 ms by patch-airi-reaction-latency.ps1
    the 900 ms fallback would sometimes cut a VAD-owned segment mid-sentence.

    WHY A TIMER CHANGE INSTEAD OF REMOVING THE 'vad' BRANCH
    -------------------------------------------------------
    An earlier revision of this script neutered the branch itself:

        activeRecordingTrigger.value === "volume" || ... === "vad"
      -> activeRecordingTrigger.value === "volume" /* VAD owns ... */

    That removed AIRI's only self-recovery path. If the VAD worklet crashes or
    stops delivering frames (device switch, audio graph teardown, worklet
    exception), nothing else can call stopSegment() -- the recorder stays open
    forever and voice input is permanently locked until the app restarts.

    Widening the timer keeps the safety net and still removes the premature cut:

      * VAD healthy  -> VAD stops at ~450 ms, well before the 2700 ms fallback,
                        so the fallback never pre-empts a VAD-owned segment.
      * VAD dead     -> the 2700 ms fallback still finalizes the segment, so the
                        session recovers instead of hanging.

    The patch is an equal-length, in-place byte replacement (" = 900" -> " =2700",
    5 bytes each); the asar is never repacked.

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

if (-not ('VoiceInputBinaryPatcher' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public static class VoiceInputBinaryPatcher
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
                    "Expected {0} matching voice-input blocks, found {1}.",
                    expectedCount,
                    oldPositions.Count
                ));

            foreach (long position in oldPositions)
            {
                stream.Position = position;
                stream.Write(newBytes, 0, newBytes.Length);
            }
            stream.Flush(true);

            if (FindAll(stream, oldBytes).Count != 0 || FindAll(stream, newBytes).Count != expectedCount)
                throw new InvalidOperationException("Post-patch verification failed.");
            return oldPositions.Count;
        }
    }
}
'@
}

function Pad-Replacement([string]$Original, [string]$Replacement) {
    if ($Replacement.Length -gt $Original.Length) {
        throw "Replacement is longer than the original block ($($Replacement.Length) > $($Original.Length))."
    }
    return $Replacement + (' ' * ($Original.Length - $Replacement.Length))
}

function Get-MarkerCount([string]$Text) {
    return [VoiceInputBinaryPatcher]::CountOccurrences($resolvedAsar, $Text)
}

function Test-MarkersPresent([string[]]$Markers) {
    foreach ($marker in $Markers) {
        if ((Get-MarkerCount $marker) -lt 1) { return $false }
    }
    return $true
}

# --- 3. Patch targets --------------------------------------------------------
# Verified against the stock 0.11.3 install (app.asar, 1,130,829,614 bytes):
#   "var DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS = 900;" -> 1 hit @ 870,122,206
#   empty-transcription toast block                    -> 1 hit @ 870,119,686
# Both live in the built renderer bundle. A second, non-executed copy of the
# TypeScript source ships in the same asar but uses `const` and single quotes,
# so the `var ...;` form below is unambiguous.
$oldStopDelayBlock = 'var DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS = 900;'
$newStopDelayBlock = 'var DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS =2700;'

$oldEmptyResultBlock = 'error.value = `No transcription result returned from provider (${result.mode === "generate" ? describeEmptyTranscriptionResponse(result) : "stream result returned empty text"})`;'
$newEmptyResultCore = 'error.value = void 0; /* Valid empty transcription is silence. */'
$newEmptyResultBlock = Pad-Replacement $oldEmptyResultBlock $newEmptyResultCore

$stockMarkers = @($oldStopDelayBlock, $oldEmptyResultBlock)

# --- 4. Reject the superseded "remove the 'vad' branch" patch -----------------
$legacyMarker = '/* VAD owns its own stop timer. */'
if ((Get-MarkerCount $legacyMarker) -gt 0) {
    $legacyMessage = @(
        'This app.asar carries the SUPERSEDED voice-input segmentation patch, which deleted the'
        "volume-fallback branch for VAD-owned segments. That build has no recovery path when the VAD"
        'worklet stops delivering frames, so voice input can lock up permanently.'
        ''
        'Restore a clean archive before applying the current patch:'
        '  1) .\restore-airi-original.ps1      (uses app.asar.backup-pristine)'
        '     or reinstall AIRI 0.11.3 if no pristine backup exists.'
        '  2) .\apply-airi-patches.ps1'
    ) -join [Environment]::NewLine

    if ($Force) {
        Write-Warning $legacyMessage
        Write-Warning 'Continuing anyway because -Force was supplied.'
    }
    else {
        throw $legacyMessage
    }
}

# --- 5. Pristine backup contract (shared by every patch-airi-*.ps1) -----------
# One 1.05 GiB copy for the whole patch set, taken only while app.asar is stock.
$pristineBackupPath = "$resolvedAsar.backup-pristine"
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup exists - skipping the backup copy: $pristineBackupPath"
}
elseif (Test-MarkersPresent $stockMarkers) {
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
$stopDelayCount = [VoiceInputBinaryPatcher]::PatchExactly(
    $resolvedAsar,
    $oldStopDelayBlock,
    $newStopDelayBlock,
    1
)
$emptyResultCount = [VoiceInputBinaryPatcher]::PatchExactly(
    $resolvedAsar,
    $oldEmptyResultBlock,
    $newEmptyResultBlock,
    1
)

if ($stopDelayCount -eq 0 -and $emptyResultCount -eq 0) {
    Write-Output 'AIRI voice-input segmentation was already patched.'
}
else {
    Write-Output "Patched AIRI voice input: volume fallback delay=$stopDelayCount empty-result handling=$emptyResultCount."
}
Write-Output 'Effective values: volume-fallback stop delay 2700 ms (safety net only), empty transcription no longer raises an error toast.'
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup: $pristineBackupPath"
}
else {
    Write-Warning "No pristine backup exists for this install; .\restore-airi-original.ps1 cannot undo these edits."
}
