param(
    [string]$AsarPath = "$env:LOCALAPPDATA\Programs\airi\resources\app.asar"
)

$ErrorActionPreference = 'Stop'

$resolvedAsar = (Resolve-Path -LiteralPath $AsarPath).Path
$expectedRoot = [System.IO.Path]::GetFullPath("$env:LOCALAPPDATA\Programs\airi\resources\")
if (-not $resolvedAsar.StartsWith($expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to patch an archive outside the AIRI resources directory: $resolvedAsar"
}
if ([System.IO.Path]::GetFileName($resolvedAsar) -ne 'app.asar') {
    throw "Expected app.asar, got: $resolvedAsar"
}

$backupPath = "$resolvedAsar.backup-before-voice-input-segmentation"
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $resolvedAsar -Destination $backupPath
}

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

function Pad-Replacement([string]$Original, [string]$Replacement) {
    if ($Replacement.Length -gt $Original.Length) {
        throw "Replacement is longer than the original block ($($Replacement.Length) > $($Original.Length))."
    }
    return $Replacement + (' ' * ($Original.Length - $Replacement.Length))
}

$oldSegmentationBlock = 'activeRecordingTrigger.value === "volume" || activeRecordingTrigger.value === "vad"'
$newSegmentationCore = 'activeRecordingTrigger.value === "volume" /* VAD owns its own stop timer. */'
$newSegmentationBlock = Pad-Replacement $oldSegmentationBlock $newSegmentationCore

$oldEmptyResultBlock = 'error.value = `No transcription result returned from provider (${result.mode === "generate" ? describeEmptyTranscriptionResponse(result) : "stream result returned empty text"})`;'
$newEmptyResultCore = 'error.value = void 0; /* Valid empty transcription is silence. */'
$newEmptyResultBlock = Pad-Replacement $oldEmptyResultBlock $newEmptyResultCore

$segmentationCount = [VoiceInputBinaryPatcher]::PatchExactly(
    $resolvedAsar,
    $oldSegmentationBlock,
    $newSegmentationBlock,
    1
)
$emptyResultCount = [VoiceInputBinaryPatcher]::PatchExactly(
    $resolvedAsar,
    $oldEmptyResultBlock,
    $newEmptyResultBlock,
    1
)

if ($segmentationCount -eq 0 -and $emptyResultCount -eq 0) {
    Write-Output 'AIRI voice-input segmentation was already patched.'
}
else {
    Write-Output "Patched AIRI voice input: volume fallback=$segmentationCount empty-result handling=$emptyResultCount."
}
Write-Output "Backup: $backupPath"
