#Requires -Version 5.1
<#
.SYNOPSIS
    Applies the full AIRI low-latency patch set to an installed app.asar, in the
    supported order, behind a single pristine backup.

.DESCRIPTION
    Order matters. Each patch is an equal-length or padded in-place byte edit of
    the installed archive, so a patch that has already consumed its stock marker
    cannot be replayed. This orchestrator:

      1. Verifies AIRI is not running.
      2. Scans app.asar once and reports the state of every patch site.
      3. Takes ONE app.asar.backup-pristine copy (~1.05 GiB) if the archive is
         still fully stock and no pristine backup exists. Every patch script
         honours the same contract, so this copy is never duplicated.
      4. Runs, in order:
           patch-airi-audio-constraints.ps1
           patch-airi-native-media-recorder.ps1
           patch-airi-voice-input-segmentation.ps1
           patch-airi-reaction-latency.ps1
           patch-airi-playback-latency.ps1
           patch-airi-session-header.ps1
         patch-airi-transcript-latency.ps1 is DEPRECATED (folded into
         patch-airi-reaction-latency.ps1) and is intentionally not run.
      5. Re-scans and prints a pass/fail table. Exits 1 if any site is wrong.

    Undo with .\restore-airi-original.ps1.

.PARAMETER InstallDir
    AIRI installation directory. Default: %LOCALAPPDATA%\Programs\airi

.PARAMETER Force
    Forwarded to each patch script: continue when app.asar is in an
    unrecognized state and no pristine backup exists.

.EXAMPLE
    .\apply-airi-patches.ps1
.EXAMPLE
    .\apply-airi-patches.ps1 -InstallDir 'D:\Apps\airi'
#>
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\airi",
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# --- 1. Resolve and validate the installation --------------------------------
if (-not (Test-Path -LiteralPath $InstallDir)) {
    throw "AIRI installation directory not found: $InstallDir"
}
$installItemBeforeResolve = Get-Item -LiteralPath $InstallDir -Force
if (-not $installItemBeforeResolve.PSIsContainer -or (($installItemBeforeResolve.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
    throw "AIRI installation path is not a regular non-reparse directory: $InstallDir"
}
$resolvedInstallDir = (Resolve-Path -LiteralPath $InstallDir).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedInstallDir 'airi.exe'))) {
    throw "'$resolvedInstallDir' does not look like an AIRI installation (airi.exe not found)."
}
$asarPath = Join-Path $resolvedInstallDir 'resources\app.asar'
if (-not (Test-Path -LiteralPath $asarPath)) {
    throw "app.asar not found: $asarPath"
}
$asarItemBeforeResolve = Get-Item -LiteralPath $asarPath -Force
if ($asarItemBeforeResolve.PSIsContainer -or (($asarItemBeforeResolve.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
    throw "app.asar is not a regular non-reparse file: $asarPath"
}
$resolvedAsar = (Resolve-Path -LiteralPath $asarPath).Path
$resolvedAsarItem = Get-Item -LiteralPath $resolvedAsar -Force
if ($resolvedAsarItem.PSIsContainer -or (($resolvedAsarItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
    throw "Resolved app.asar is not a regular non-reparse file: $resolvedAsar"
}

# --- 2. AIRI must not be running ---------------------------------------------
$airiProcesses = @(Get-Process -Name 'airi' -ErrorAction SilentlyContinue)
if ($airiProcesses.Count -gt 0) {
    $airiPids = ($airiProcesses | ForEach-Object { $_.Id }) -join ', '
    throw "AIRI is running (PID: $airiPids). Close AIRI completely and re-run; patching a loaded app.asar corrupts the install."
}

if (-not ('AiriPatchScanner' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;

public static class AiriPatchScanner
{
    // Single pass over the archive, counting every pattern at once.
    // Patterns shorter than the longest one would be re-counted inside the
    // carry-over overlap, so matches are de-duplicated by absolute offset.
    public static int[] CountAll(string path, string[] patterns)
    {
        byte[][] needles = new byte[patterns.Length][];
        long[] lastCounted = new long[patterns.Length];
        int[] counts = new int[patterns.Length];
        int maxLength = 1;

        for (int p = 0; p < patterns.Length; p++)
        {
            needles[p] = Encoding.UTF8.GetBytes(patterns[p]);
            lastCounted[p] = -1;
            if (needles[p].Length > maxLength)
                maxLength = needles[p].Length;
        }

        const int chunkSize = 8 * 1024 * 1024;
        byte[] buffer = new byte[chunkSize + maxLength - 1];
        int carry = 0;
        long bufferBase = 0;

        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
        {
            while (true)
            {
                int read = stream.Read(buffer, carry, chunkSize);
                int total = carry + read;
                if (total == 0)
                    break;

                for (int p = 0; p < needles.Length; p++)
                {
                    byte[] needle = needles[p];
                    int searchLimit = total - needle.Length;
                    byte first = needle[0];
                    for (int index = 0; index <= searchLimit; index++)
                    {
                        if (buffer[index] != first)
                            continue;
                        bool matches = true;
                        for (int offset = 1; offset < needle.Length; offset++)
                        {
                            if (buffer[index + offset] != needle[offset])
                            {
                                matches = false;
                                break;
                            }
                        }
                        if (!matches)
                            continue;

                        long absolute = bufferBase + index;
                        if (absolute > lastCounted[p])
                        {
                            lastCounted[p] = absolute;
                            counts[p]++;
                        }
                    }
                }

                if (read == 0)
                    break;

                carry = Math.Min(maxLength - 1, total);
                Buffer.BlockCopy(buffer, total - carry, buffer, 0, carry);
                bufferBase += total - carry;
            }
        }
        return counts;
    }
}
'@
}

# --- 3. Marker table ----------------------------------------------------------
# Offsets below were measured on the stock 0.11.3 install
# (app.asar, 1,130,829,614 bytes) with a read-only scan.
$knownPristineAsarSha256 = 'B3433A29D2E8357A84068DFFCAD80A2A23A4D4C0F5F803764C66839C84B788AF'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

$stockMarkers = @(
    @{ Patch = 'audio-constraints';        Text = "autoGainControl: true,`n`t`techoCancellation: true,`n`t`tnoiseSuppression: true"; Expected = 2 }
    @{ Patch = 'native-media-recorder';    Text = 'function useAudioRecorder(media) {';                                              Expected = 1 }
    @{ Patch = 'voice-input-segmentation'; Text = 'var DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS = 900;';                                Expected = 1 }
    @{ Patch = 'voice-input-segmentation'; Text = 'error.value = `No transcription result returned from provider (${result.mode === "generate" ? describeEmptyTranscriptionResponse(result) : "stream result returned empty text"})`;' ; Expected = 1 }
    @{ Patch = 'reaction-latency';         Text = 'var DEFAULT_VAD_MIN_SILENCE_DURATION_MS = 1200;';                                 Expected = 1 }
    @{ Patch = 'reaction-latency';         Text = 'var DEFAULT_VAD_SPEECH_PAD_MS = 360;';                                             Expected = 1 }
    @{ Patch = 'reaction-latency';         Text = "flushDelayMs: 1200,`n`t`t`tmaxBufferedTextLength: 90,";                           Expected = 1 }
    @{ Patch = 'playback-latency';         Text = "source.start(0);`n`t`t`t`t`tif (item.intentId.startsWith(`"stream-`")) {";        Expected = 1 }
    @{ Patch = 'session-header';           Text = "`t`tif (providerMode(activeProvider.value) === `"official`" && options?.requestCorrelation) {`n`t`t`theaders[AIRI_CHAT_SESSION_ID_HEADER] = options.requestCorrelation.conversationId;`n`t`t`theaders[AIRI_CHAT_ROUND_ID_HEADER] = options.requestCorrelation.roundId;`n`t`t`theaders[AIRI_CHAT_APP_SURFACE_HEADER] = getConversationAnalyticsSurface();`n`t`t}"; Expected = 1 }
)

$patchedMarkers = @(
    @{ Patch = 'audio-constraints';        Site = 'raw mic constraints';   Text = 'autoGainControl: !1  ,';                                            Expected = 2 }
    @{ Patch = 'native-media-recorder';    Site = 'native MediaRecorder';  Text = 'audioBitsPerSecond:128e3';                                          Expected = 1 }
    @{ Patch = 'voice-input-segmentation'; Site = 'volume fallback 2700';  Text = 'var DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS =2700;';                  Expected = 1 }
    @{ Patch = 'voice-input-segmentation'; Site = 'empty transcript toast'; Text = 'error.value = void 0; /* Valid empty transcription is silence. */'; Expected = 1 }
    @{ Patch = 'reaction-latency';         Site = 'VAD silence 450';       Text = 'var DEFAULT_VAD_MIN_SILENCE_DURATION_MS =  450;';                   Expected = 1 }
    @{ Patch = 'reaction-latency';         Site = 'speech pre-roll 600';   Text = 'var DEFAULT_VAD_SPEECH_PAD_MS = 600;';                       Expected = 1 }
    @{ Patch = 'reaction-latency';         Site = 'transcript flush 400';  Text = "flushDelayMs:  400,`n`t`t`tmaxBufferedTextLength: 90,";             Expected = 1 }
    @{ Patch = 'playback-latency';         Site = 'playback start event';  Text = 'request_id:String(item.intentId)';                                  Expected = 1 }
    @{ Patch = 'session-header';           Site = 'custom conversation id'; Text = 'if(options?.requestCorrelation)headers[AIRI_CHAT_SESSION_ID_HEADER]=options.requestCorrelation.conversationId;'; Expected = 1 }
)

# Superseded patch that deleted the volume-fallback safety net for VAD segments.
$legacyMarker = '/* VAD owns its own stop timer. */'

Write-Output "AIRI install : $resolvedInstallDir"
Write-Output "app.asar     : $resolvedAsar ($('{0:N0}' -f (Get-Item -LiteralPath $resolvedAsar).Length) bytes)"
Write-Output ''
Write-Output 'Scanning app.asar for patch sites...'

$preScanTexts = @()
$preScanTexts += ($stockMarkers   | ForEach-Object { $_.Text })
$preScanTexts += ($patchedMarkers | ForEach-Object { $_.Text })
$preScanTexts += $legacyMarker
$preCounts = [AiriPatchScanner]::CountAll($resolvedAsar, $preScanTexts)

$stockCount = $stockMarkers.Count
$isFullyStock = $true
for ($i = 0; $i -lt $stockCount; $i++) {
    if ($preCounts[$i] -ne $stockMarkers[$i].Expected) { $isFullyStock = $false }
}
$legacyCount = $preCounts[$preCounts.Length - 1]

if ($isFullyStock) {
    Write-Output 'State: app.asar is stock (all patch sites carry their original bytes).'
}
else {
    Write-Output 'State: app.asar is partially patched or otherwise modified.'
}
if ($legacyCount -gt 0) {
    Write-Warning 'app.asar carries the SUPERSEDED voice-input segmentation patch. patch-airi-voice-input-segmentation.ps1 will refuse to run; restore with .\restore-airi-original.ps1 (or reinstall AIRI) first.'
}
Write-Output ''

# --- 4. Pristine backup -------------------------------------------------------
$pristineBackupPath = "$resolvedAsar.backup-pristine"
if (Test-Path -LiteralPath $pristineBackupPath) {
    $pristineBackupHash = Get-Sha256 $pristineBackupPath
    if ($pristineBackupHash -ne $knownPristineAsarSha256) {
        throw "Pristine backup SHA-256 mismatch: got $pristineBackupHash, expected $knownPristineAsarSha256. Refusing to continue."
    }
    Write-Output "Pristine backup exists - skipping the backup copy: $pristineBackupPath"
}
elseif ($isFullyStock) {
    Write-Output "Creating pristine backup (this copies ~1.05 GiB): $pristineBackupPath"
    $sourceHashBeforeBackup = Get-Sha256 $resolvedAsar
    if ($sourceHashBeforeBackup -ne $knownPristineAsarSha256) {
        throw "Stock scan/hash race detected: app.asar SHA-256 is $sourceHashBeforeBackup, expected $knownPristineAsarSha256. Refusing to create a backup."
    }
    $temporaryBackupPath = Join-Path (Split-Path -Parent $pristineBackupPath) ('.app.asar.backup-{0}.tmp' -f ([guid]::NewGuid().ToString('N')))
    try {
        Copy-Item -LiteralPath $resolvedAsar -Destination $temporaryBackupPath -Force
        $temporaryBackupHash = Get-Sha256 $temporaryBackupPath
        if ($temporaryBackupHash -ne $knownPristineAsarSha256) {
            throw "Pristine backup staging SHA-256 mismatch: got $temporaryBackupHash, expected $knownPristineAsarSha256."
        }
        try {
            [System.IO.File]::Move($temporaryBackupPath, $pristineBackupPath)
        }
        catch [System.IO.IOException] {
            if (-not (Test-Path -LiteralPath $pristineBackupPath)) {
                throw
            }
            $racingBackupHash = Get-Sha256 $pristineBackupPath
            if ($racingBackupHash -ne $knownPristineAsarSha256) {
                throw "Concurrent pristine backup has an unexpected SHA-256: got $racingBackupHash, expected $knownPristineAsarSha256."
            }
            Write-Warning 'A concurrent run created the verified pristine backup; reusing it.'
        }
        Write-Output 'Pristine backup created or safely reused.'
    }
    finally {
        if (Test-Path -LiteralPath $temporaryBackupPath) {
            Remove-Item -LiteralPath $temporaryBackupPath -Force -ErrorAction SilentlyContinue
        }
    }
}
elseif ($Force) {
    Write-Warning 'No pristine backup exists and app.asar is not stock. Continuing without a backup because -Force was supplied.'
}
else {
    throw "No pristine backup exists and app.asar is not stock, so a backup taken now would not be pristine. Reinstall AIRI 0.11.3 and re-run, or pass -Force to patch without a backup."
}
Write-Output ''

# --- 5. Apply patches in order ------------------------------------------------
$patchScripts = @(
    'patch-airi-audio-constraints.ps1'
    'patch-airi-native-media-recorder.ps1'
    'patch-airi-voice-input-segmentation.ps1'
    'patch-airi-reaction-latency.ps1'
    'patch-airi-playback-latency.ps1'
    'patch-airi-session-header.ps1'
)

$failures = New-Object System.Collections.ArrayList
foreach ($scriptName in $patchScripts) {
    $scriptPath = Join-Path $PSScriptRoot $scriptName
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Patch script not found: $scriptPath"
    }

    Write-Output "--- $scriptName ---"
    try {
        if ($Force) {
            & $scriptPath -AsarPath $resolvedAsar -Force
        }
        else {
            & $scriptPath -AsarPath $resolvedAsar
        }
    }
    catch {
        Write-Warning "$scriptName FAILED: $($_.Exception.Message)"
        [void]$failures.Add($scriptName)
    }
    Write-Output ''
}

# --- 6. Final verification ----------------------------------------------------
Write-Output 'Verifying patched app.asar...'
$verifyTexts = @()
$verifyTexts += ($patchedMarkers | ForEach-Object { $_.Text })
$verifyTexts += $legacyMarker
$verifyCounts = [AiriPatchScanner]::CountAll($resolvedAsar, $verifyTexts)
$stockVerifyTexts = @($stockMarkers | ForEach-Object { $_.Text })
$stockVerifyCounts = [AiriPatchScanner]::CountAll($resolvedAsar, $stockVerifyTexts)

$report = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $patchedMarkers.Count; $i++) {
    $marker = $patchedMarkers[$i]
    $found = $verifyCounts[$i]
    $ok = ($found -eq $marker.Expected)
    [void]$report.Add([pscustomobject]@{
        Patch    = $marker.Patch
        Site     = $marker.Site
        Expected = $marker.Expected
        Found    = $found
        Result   = $(if ($ok) { 'PASS' } else { 'FAIL' })
    })
}
for ($i = 0; $i -lt $stockMarkers.Count; $i++) {
    $marker = $stockMarkers[$i]
    $found = $stockVerifyCounts[$i]
    [void]$report.Add([pscustomobject]@{
        Patch    = $marker.Patch
        Site     = 'stock marker absent'
        Expected = 0
        Found    = $found
        Result   = $(if ($found -eq 0) { 'PASS' } else { 'FAIL' })
    })
}
$legacyFound = $verifyCounts[$verifyCounts.Length - 1]
[void]$report.Add([pscustomobject]@{
    Patch    = 'voice-input-segmentation'
    Site     = 'superseded patch absent'
    Expected = 0
    Found    = $legacyFound
    Result   = $(if ($legacyFound -eq 0) { 'PASS' } else { 'FAIL' })
})

$report | Format-Table -AutoSize | Out-String | Write-Output

$failedChecks = @($report | Where-Object { $_.Result -eq 'FAIL' })
if ($failedChecks.Count -gt 0 -or $failures.Count -gt 0) {
    if ($failures.Count -gt 0) {
        Write-Warning "Patch scripts that threw: $($failures -join ', ')"
    }
    Write-Warning "$($failedChecks.Count) patch site(s) did not verify. Restore with .\restore-airi-original.ps1 and investigate before launching AIRI."
    exit 1
}

Write-Output 'All AIRI patches applied and verified.'
Write-Output 'Effective values: raw mic capture, native MediaRecorder (Opus/WebM), VAD silence 450 ms,'
Write-Output 'speech pre-roll 600 ms, volume-fallback safety net 2700 ms, transcript flush 400 ms,'
Write-Output 'playback start reported to 127.0.0.1:8892,'
Write-Output 'and stable x-airi-session-id on custom OpenAI-compatible chat requests.'
if (Test-Path -LiteralPath $pristineBackupPath) {
    Write-Output "Pristine backup: $pristineBackupPath"
}
else {
    Write-Warning "No pristine backup exists for this install; .\restore-airi-original.ps1 cannot undo these edits."
}
exit 0
