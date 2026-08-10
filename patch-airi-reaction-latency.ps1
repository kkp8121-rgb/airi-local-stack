#Requires -Version 5.1
<#
.SYNOPSIS
    Tunes AIRI's VAD timing and assistant transcript flush delay.

.DESCRIPTION
    Three equal-length, in-place edits of the installed app.asar (no repack):

      1. DEFAULT_VAD_MIN_SILENCE_DURATION_MS  1200 ms -> 450 ms
         The dominant end-of-turn delay. Silero VAD must observe this much
         silence before it closes a segment, and every user turn pays it.

      2. transcript flushDelayMs              1200 ms -> 400 ms
         How long the assistant transcript buffer waits for more STT text
         before flushing a sentence downstream.

      3. DEFAULT_VAD_SPEECH_PAD_MS             360 ms -> 600 ms
         Retains more audio before speech onset so a sentence-leading proper
         noun is not clipped. This is pre-roll audio; it does not increase the
         end-of-turn silence window.

    WHY flushDelayMs = 400 AND NOT 100 OR 700+
    ------------------------------------------
    The buffer exists to merge consecutive STT fragments into one turn. On this
    stack the next fragment cannot arrive sooner than roughly 750 ms (VAD 450 ms
    silence + recorder stop + STT round trip), so:

      * 100 ms  -> the buffer always flushes before the next fragment can land.
                   Sentence merging is effectively disabled and a mid-sentence
                   pause splits one utterance into two turns.
      * 700 ms+ -> merging works, but every single turn pays the full delay.
      * 400 ms  -> keeps the buffer meaningful for back-to-back fragments while
                   only adding 0.4 s to a turn. Chosen balance point.

    WHY speechPadMs = 600
    ---------------------
    A physical microphone test clipped the first proper noun once in two turns;
    that chunk was also about 240 ms shorter than the exact-recognition chunk.
    Increasing pre-roll by the same 240 ms protects the leading word without
    changing the 450 ms silence endpoint.

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

if (-not ('ReactionLatencyBinaryPatcher' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public static class ReactionLatencyBinaryPatcher
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

    public static int PatchOneOf(string path, string[] oldTexts, string newText)
    {
        byte[] newBytes = Encoding.UTF8.GetBytes(newText);
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            if (FindAll(stream, newBytes).Count == 1)
                return 0;

            foreach (string oldText in oldTexts)
            {
                byte[] oldBytes = Encoding.UTF8.GetBytes(oldText);
                if (oldBytes.Length != newBytes.Length)
                    throw new InvalidOperationException("Replacement must have exactly the same byte length.");

                List<long> positions = FindAll(stream, oldBytes);
                if (positions.Count == 0)
                    continue;
                if (positions.Count != 1)
                    throw new InvalidOperationException(string.Format(
                        "Expected one latency block, found {0}.", positions.Count
                    ));

                stream.Position = positions[0];
                stream.Write(newBytes, 0, newBytes.Length);
                stream.Flush(true);
                if (FindAll(stream, newBytes).Count != 1)
                    throw new InvalidOperationException("Post-patch verification failed.");
                return 1;
            }
        }
        throw new InvalidOperationException("No supported stock or previously patched latency block was found.");
    }

    public static int PatchAllOneOf(
        string path, string[] oldTexts, string newText, int expectedCount)
    {
        byte[] newBytes = Encoding.UTF8.GetBytes(newText);
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            int existingNewCount = FindAll(stream, newBytes).Count;
            if (existingNewCount == expectedCount)
                return 0;

            var positions = new List<long>();
            foreach (string oldText in oldTexts)
            {
                byte[] oldBytes = Encoding.UTF8.GetBytes(oldText);
                if (oldBytes.Length != newBytes.Length)
                    throw new InvalidOperationException("Replacement must have exactly the same byte length.");
                positions.AddRange(FindAll(stream, oldBytes));
            }

            if (existingNewCount + positions.Count != expectedCount)
                throw new InvalidOperationException(string.Format(
                    "Expected {0} total latency blocks, found {1}.",
                    expectedCount, existingNewCount + positions.Count
                ));

            foreach (long position in positions)
            {
                stream.Position = position;
                stream.Write(newBytes, 0, newBytes.Length);
            }
            stream.Flush(true);
            if (FindAll(stream, newBytes).Count != expectedCount)
                throw new InvalidOperationException("Post-patch verification failed.");
            return positions.Count;
        }
    }
}
'@
}

function Get-MarkerCount([string]$Text) {
    return [ReactionLatencyBinaryPatcher]::CountOccurrences($resolvedAsar, $Text)
}

function Test-MarkersPresent([string[]]$Markers) {
    foreach ($marker in $Markers) {
        if ((Get-MarkerCount $marker) -lt 1) { return $false }
    }
    return $true
}

# --- 3. Patch targets --------------------------------------------------------
# Verified against the stock 0.11.3 install (app.asar, 1,130,829,614 bytes):
#   "var DEFAULT_VAD_MIN_SILENCE_DURATION_MS = 1200;" -> 1 hit @   870,085,942
#   "var DEFAULT_VAD_SPEECH_PAD_MS = 360;"            -> 1 hit
#   "flushDelayMs: 1200,<LF><TAB><TAB><TAB>maxBufferedTextLength: 90," -> 1 hit @ 1,105,472,073
$stockVadSilence = 'var DEFAULT_VAD_MIN_SILENCE_DURATION_MS = 1200;'
$stockVadSpeechPad = 'var DEFAULT_VAD_SPEECH_PAD_MS = 360;'
$stockFlushDelay = "flushDelayMs: 1200,`n`t`t`tmaxBufferedTextLength: 90,"

$stockMarkers = @($stockVadSilence, $stockVadSpeechPad, $stockFlushDelay)

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

# --- 4. Patch ----------------------------------------------------------------
$vadSilence = [ReactionLatencyBinaryPatcher]::PatchOneOf(
    $resolvedAsar,
    @($stockVadSilence),
    'var DEFAULT_VAD_MIN_SILENCE_DURATION_MS =  450;'
)

# Accepted old states for the transcript buffer, all the same byte length:
#   1200 = stock, 400 = current target (handled by PatchOneOf's leading
#   idempotency check), 100 = superseded over-aggressive patch.
$transcriptFlush = [ReactionLatencyBinaryPatcher]::PatchOneOf(
    $resolvedAsar,
    @(
        $stockFlushDelay,
        "flushDelayMs:  400,`n`t`t`tmaxBufferedTextLength: 90,",
        "flushDelayMs:  100,`n`t`t`tmaxBufferedTextLength: 90,"
    ),
    "flushDelayMs:  400,`n`t`t`tmaxBufferedTextLength: 90,"
)

$vadSpeechPad = [ReactionLatencyBinaryPatcher]::PatchAllOneOf(
    $resolvedAsar,
    @(
        $stockVadSpeechPad,
        'var DEFAULT_VAD_SPEECH_PAD_MS = 120;'
    ),
    'var DEFAULT_VAD_SPEECH_PAD_MS = 600;',
    1
)

Write-Output "AIRI reaction latency patch: VAD silence=$vadSilence transcript flush=$transcriptFlush speech pre-roll=$vadSpeechPad."
Write-Output 'Effective values: VAD silence 450 ms, transcript flush 400 ms, speech pre-roll 600 ms.'
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup: $pristineBackupPath"
}
else {
    Write-Warning "No pristine backup exists for this install; .\restore-airi-original.ps1 cannot undo these edits."
}
