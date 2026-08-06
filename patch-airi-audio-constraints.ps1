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

$backupPath = "$resolvedAsar.backup-audio-constraints-v0113"
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $resolvedAsar -Destination $backupPath
}

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

$enabledBlock = @"
autoGainControl: true,
		echoCancellation: true,
		noiseSuppression: true
"@
$disabledBlock = @"
autoGainControl: !1  ,
		echoCancellation: !1  ,
		noiseSuppression: !1  
"@

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
Write-Output "Backup: $backupPath"
