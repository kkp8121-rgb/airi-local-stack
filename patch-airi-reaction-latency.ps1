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

$backupPath = "$resolvedAsar.backup-before-reaction-latency"
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $resolvedAsar -Destination $backupPath
}

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
}
'@

$vadSilence = [ReactionLatencyBinaryPatcher]::PatchOneOf(
    $resolvedAsar,
    @('var DEFAULT_VAD_MIN_SILENCE_DURATION_MS = 1200;'),
    'var DEFAULT_VAD_MIN_SILENCE_DURATION_MS =  450;'
)
$vadPadding = [ReactionLatencyBinaryPatcher]::PatchOneOf(
    $resolvedAsar,
    @('var DEFAULT_VAD_SPEECH_PAD_MS = 360;'),
    'var DEFAULT_VAD_SPEECH_PAD_MS = 120;'
)
$transcriptFlush = [ReactionLatencyBinaryPatcher]::PatchOneOf(
    $resolvedAsar,
    @(
        "flushDelayMs: 1200,`n`t`t`tmaxBufferedTextLength: 90,",
        "flushDelayMs:  400,`n`t`t`tmaxBufferedTextLength: 90,"
    ),
    "flushDelayMs:  100,`n`t`t`tmaxBufferedTextLength: 90,"
)

Write-Output "AIRI reaction latency patch: VAD silence=$vadSilence padding=$vadPadding transcript flush=$transcriptFlush."
Write-Output "Effective values: VAD silence 450 ms, speech padding 120 ms, transcript flush 100 ms."
Write-Output "Backup: $backupPath"
