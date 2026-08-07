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

$backupPath = "$resolvedAsar.backup-before-playback-latency"
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $resolvedAsar -Destination $backupPath
}

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

$oldBlock = "source.start(0);`n`t`t`t`t`tif (item.intentId.startsWith(`"stream-`")) {`n`t`t`t`t`t`tconst model = resolveStreamingSessionModel();`n`t`t`t`t`t`tif (model) trackOfficialAutoTtsForTurn(model);`n`t`t`t`t`t}"
$newBlock = 'source.start(0);fetch("http://127.0.0.1:8892/api/event",{method:"POST",body:JSON.stringify({source:"playback",phase:"start",request_id:String(item.intentId)})}).catch(()=>{});'

$patched = [PlaybackLatencyBinaryPatcher]::Patch($resolvedAsar, $oldBlock, $newBlock)
if ($patched -eq 0) {
    Write-Output 'AIRI playback-start instrumentation was already patched.'
}
else {
    Write-Output 'Patched AIRI playback start to report source.start(0) to the latency dashboard.'
}
Write-Output 'The replaced block only contained official-provider usage analytics; the active OpenAI-compatible TTS path is unchanged.'
Write-Output "Backup: $backupPath"
