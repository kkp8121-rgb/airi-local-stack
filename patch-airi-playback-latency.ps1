#Requires -Version 5.1
<#
.SYNOPSIS
    Reports AIRI's audio playback start to the local latency dashboard.

.DESCRIPTION
    Replaces the official-provider usage-analytics block that follows
    source.start(0) with a fire-and-forget POST to the latency monitor on
    127.0.0.1:8892. The replacement is shorter than the region and is padded
    with spaces, so the asar is never repacked. The active OpenAI-compatible
    TTS path is unchanged.

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

if (-not ('PlaybackLatencyBinaryPatcher' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public static class PlaybackLatencyBinaryPatcher
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

    public static int Patch(string path, string oldText, string newText)
    {
        byte[] oldBytes = Encoding.UTF8.GetBytes(oldText);
        byte[] newBytes = Encoding.UTF8.GetBytes(newText);
        if (newBytes.Length > oldBytes.Length)
            throw new InvalidOperationException("Playback instrumentation is larger than its patch region.");

        using (var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            if (FindAll(stream, newBytes).Count == 1)
                return 0;

            List<long> positions = FindAll(stream, oldBytes);
            if (positions.Count != 1)
                throw new InvalidOperationException(string.Format(
                    "Expected one playback start block, found {0}.", positions.Count
                ));

            byte[] padded = new byte[oldBytes.Length];
            for (int index = 0; index < padded.Length; index++)
                padded[index] = 0x20;
            Buffer.BlockCopy(newBytes, 0, padded, 0, newBytes.Length);
            stream.Position = positions[0];
            stream.Write(padded, 0, padded.Length);
            stream.Flush(true);

            if (FindAll(stream, newBytes).Count != 1)
                throw new InvalidOperationException("Playback instrumentation verification failed.");
            return 1;
        }
    }
}
'@
}

function Get-MarkerCount([string]$Text) {
    return [PlaybackLatencyBinaryPatcher]::CountOccurrences($resolvedAsar, $Text)
}

function Test-MarkersPresent([string[]]$Markers) {
    foreach ($marker in $Markers) {
        if ((Get-MarkerCount $marker) -lt 1) { return $false }
    }
    return $true
}

# --- 3. Patch targets --------------------------------------------------------
# Verified against the stock 0.11.3 install (app.asar, 1,130,829,614 bytes):
#   source.start(0) analytics block -> 1 hit @ 1,105,392,928
$oldBlock = "source.start(0);`n`t`t`t`t`tif (item.intentId.startsWith(`"stream-`")) {`n`t`t`t`t`t`tconst model = resolveStreamingSessionModel();`n`t`t`t`t`t`tif (model) trackOfficialAutoTtsForTurn(model);`n`t`t`t`t`t}"
$newBlock = 'source.start(0);fetch("http://127.0.0.1:8892/api/event",{method:"POST",body:JSON.stringify({source:"playback",phase:"start",request_id:String(item.intentId)})}).catch(()=>{});'

# --- 4. Pristine backup contract (shared by every patch-airi-*.ps1) ----------
$pristineBackupPath = "$resolvedAsar.backup-pristine"
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup exists - skipping the backup copy: $pristineBackupPath"
}
elseif (Test-MarkersPresent @($oldBlock)) {
    Copy-Item -LiteralPath $resolvedAsar -Destination $pristineBackupPath
    Write-Output "Created pristine backup: $pristineBackupPath"
}
elseif ($Force) {
    Write-Warning 'No pristine backup exists and app.asar no longer carries this patch''s stock markers. Continuing without a backup because -Force was supplied.'
}
else {
    throw "No pristine backup exists and app.asar no longer carries this patch's stock markers, so a backup taken now would not be pristine. Run .\restore-airi-original.ps1 (or reinstall AIRI) and retry, or pass -Force to patch without a backup."
}

# --- 5. Patch ----------------------------------------------------------------
$patched = [PlaybackLatencyBinaryPatcher]::Patch($resolvedAsar, $oldBlock, $newBlock)
if ($patched -eq 0) {
    Write-Output 'AIRI playback-start instrumentation was already patched.'
}
else {
    Write-Output 'Patched AIRI playback start to report source.start(0) to the latency dashboard.'
}
Write-Output 'The replaced block only contained official-provider usage analytics; the active OpenAI-compatible TTS path is unchanged.'
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup: $pristineBackupPath"
}
else {
    Write-Warning "No pristine backup exists for this install; .\restore-airi-original.ps1 cannot undo these edits."
}
