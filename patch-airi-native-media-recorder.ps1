param(
    [string]$AsarPath = "$env:LOCALAPPDATA\Programs\airi\resources\app.asar",
    [string]$ReplacementPath = "$PSScriptRoot\airi-native-media-recorder.min.js"
)

$ErrorActionPreference = 'Stop'

$resolvedAsar = (Resolve-Path -LiteralPath $AsarPath).Path
$resolvedReplacement = (Resolve-Path -LiteralPath $ReplacementPath).Path
$expectedRoot = [System.IO.Path]::GetFullPath("$env:LOCALAPPDATA\Programs\airi\resources\")
if (-not $resolvedAsar.StartsWith($expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to patch an archive outside the AIRI resources directory: $resolvedAsar"
}
if ([System.IO.Path]::GetFileName($resolvedAsar) -ne 'app.asar') {
    throw "Expected app.asar, got: $resolvedAsar"
}

$backupPath = "$resolvedAsar.backup-before-native-mediarecorder"
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $resolvedAsar -Destination $backupPath
}

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

$replacement = Get-Content -LiteralPath $resolvedReplacement -Raw -Encoding UTF8
$startMarker = 'function useAudioRecorder(media) {'
$endMarker = "`n//#endregion`n//#region ../../packages/stage-ui/src/libs/audio/vad.ts"
$regionLength = [AsarRegionPatcher]::PatchRegion(
    $resolvedAsar,
    $startMarker,
    $endMarker,
    $replacement
)

Write-Output "Replaced the AIRI recorder region ($regionLength bytes) with native MediaRecorder."
Write-Output "Backup: $backupPath"
