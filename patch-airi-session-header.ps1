#Requires -Version 5.1
<#
.SYNOPSIS
    Sends AIRI's stable conversation ID to custom OpenAI-compatible providers.

.DESCRIPTION
    AIRI 0.11.3 only adds x-airi-session-id for an "official" provider even
    though requestCorrelation.conversationId is available for every provider.
    This equal-length in-place patch sends only the session header for custom
    providers; round/app-surface analytics remain official-provider-only.

    AIRI must be closed. Restore with .\restore-airi-original.ps1.

    This script is bound to AIRI ProductVersion 0.11.3.0 and the SHA-256 of
    its pristine and known supported patched app.asar hashes. -Force only
    permits a no-backup run for an otherwise known supported current archive;
    it never bypasses the version or archive-hash checks.
#>
param(
    [string]$AsarPath = "$env:LOCALAPPDATA\Programs\airi\resources\app.asar",
    [switch]$Force,
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$resolvedAsar = (Resolve-Path -LiteralPath $AsarPath).Path
if ([IO.Path]::GetFileName($resolvedAsar) -ne 'app.asar') {
    throw "Expected app.asar, got: $resolvedAsar"
}
$resourcesDir = Split-Path -Parent $resolvedAsar
$installDir = Split-Path -Parent $resourcesDir
if ((Split-Path -Leaf $resourcesDir) -ne 'resources' -or
    -not (Test-Path -LiteralPath (Join-Path $installDir 'airi.exe'))) {
    throw "Refusing to patch an archive outside an AIRI installation: $resolvedAsar"
}
$expectedProductVersion = '0.11.3.0'
$knownPristineAsarSha256 = 'B3433A29D2E8357A84068DFFCAD80A2A23A4D4C0F5F803764C66839C84B788AF'
$knownPreSessionAsarSha256 = '93DFF73B984A74C71D0BB05F4DC710B8B2DDEDB2724F18D389613995AACD4891'
$knownPostSessionPristineAsarSha256 = '0E1E4B03D132283F06F6AED743B3AC57C15BEC9C94C942097B00EA236239135C'
$knownPostSessionPreSessionAsarSha256 = 'CB672061D4A92F36D9450E8A30FE08134D0C66BBC388E1B3C444AD4A328634C8'
$airiExe = Join-Path $installDir 'airi.exe'
$productVersion = (Get-Item -LiteralPath $airiExe).VersionInfo.ProductVersion
if ($productVersion -ne $expectedProductVersion) {
    throw "Refusing to patch unsupported AIRI ProductVersion '$productVersion'; expected '$expectedProductVersion'. -Force does not override this binding."
}
if ($Force) {
    Write-Warning '-Force was supplied. It only permits a no-backup run for a known supported archive; it does not override AIRI version or archive-hash checks.'
}
function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}
$airiProcesses = @(Get-Process -Name 'airi' -ErrorAction SilentlyContinue)
if (-not $VerifyOnly -and $airiProcesses.Count) {
    throw "AIRI is running (PID: $(($airiProcesses.Id) -join ', ')). Close AIRI completely before patching."
}

if (-not ('AiriSessionHeaderPatcher' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;

public static class AiriSessionHeaderPatcher
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
            if (total == 0) break;
            int limit = total - pattern.Length;
            for (int index = 0; index <= limit; index++)
            {
                bool matches = true;
                for (int offset = 0; offset < pattern.Length; offset++)
                {
                    if (buffer[index + offset] != pattern[offset]) { matches = false; break; }
                }
                if (matches) positions.Add(bufferBase + index);
            }
            if (read == 0) break;
            carry = Math.Min(pattern.Length - 1, total);
            Buffer.BlockCopy(buffer, total - carry, buffer, 0, carry);
            bufferBase += total - carry;
        }
        return positions;
    }

    public static int Count(string path, string text)
    {
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            return FindAll(stream, Encoding.UTF8.GetBytes(text)).Count;
    }

    private static string GetSha256(FileStream stream)
    {
        stream.Position = 0;
        using (var sha256 = SHA256.Create())
            return BitConverter.ToString(sha256.ComputeHash(stream)).Replace("-", "");
    }

    // forcePostWriteVerificationFailure is a test-only hook. Production calls
    // the four-argument overload below and cannot select this behavior.
    public static int Patch(string path, string oldText, string newText, string expectedPostSha256, bool forcePostWriteVerificationFailure)
    {
        byte[] oldBytes = Encoding.UTF8.GetBytes(oldText);
        byte[] newBytes = Encoding.UTF8.GetBytes(newText);
        if (oldBytes.Length != newBytes.Length)
            throw new InvalidOperationException("Session-header replacement must be byte-for-byte equal length.");
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            List<long> positions = FindAll(stream, oldBytes);
            int newCount = FindAll(stream, newBytes).Count;
            if (positions.Count == 0 && newCount == 1) return 0;
            if (positions.Count != 1 || newCount != 0)
                throw new InvalidOperationException(string.Format("Expected exactly one stock session-header block and no patched blocks; found stock={0}, patched={1}.", positions.Count, newCount));
            stream.Position = positions[0];
            try
            {
                stream.Write(newBytes, 0, newBytes.Length);
                stream.Flush(true);
                if (forcePostWriteVerificationFailure || FindAll(stream, newBytes).Count != 1)
                    throw new InvalidOperationException("Session-header patch verification failed.");
                if (!String.IsNullOrEmpty(expectedPostSha256) &&
                    !String.Equals(GetSha256(stream), expectedPostSha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Session-header archive hash verification failed.");
                return 1;
            }
            catch (Exception patchFailure)
            {
                try
                {
                    stream.Position = positions[0];
                    stream.Write(oldBytes, 0, oldBytes.Length);
                    stream.Flush(true);
                    if (FindAll(stream, oldBytes).Count != 1 || FindAll(stream, newBytes).Count != 0)
                        throw new InvalidOperationException("Stock marker verification failed after rollback.");
                }
                catch (Exception rollbackFailure)
                {
                    throw new InvalidOperationException(
                        "Session-header patch failed and rollback could not be verified; archive safety is unknown.",
                        new AggregateException(patchFailure, rollbackFailure));
                }
                throw;
            }
        }
    }

    public static int Patch(string path, string oldText, string newText)
    {
        return Patch(path, oldText, newText, null, false);
    }

    public static int Patch(string path, string oldText, string newText, bool forcePostWriteVerificationFailure)
    {
        return Patch(path, oldText, newText, null, forcePostWriteVerificationFailure);
    }

    public static int Patch(string path, string oldText, string newText, string expectedPostSha256)
    {
        return Patch(path, oldText, newText, expectedPostSha256, false);
    }
}
'@
}

$oldBlock = "`t`tif (providerMode(activeProvider.value) === `"official`" && options?.requestCorrelation) {`n`t`t`theaders[AIRI_CHAT_SESSION_ID_HEADER] = options.requestCorrelation.conversationId;`n`t`t`theaders[AIRI_CHAT_ROUND_ID_HEADER] = options.requestCorrelation.roundId;`n`t`t`theaders[AIRI_CHAT_APP_SURFACE_HEADER] = getConversationAnalyticsSurface();`n`t`t}"
$newBlock = 'if(options?.requestCorrelation)headers[AIRI_CHAT_SESSION_ID_HEADER]=options.requestCorrelation.conversationId;if(providerMode(activeProvider.value)=="official"&&options?.requestCorrelation){headers[AIRI_CHAT_ROUND_ID_HEADER]=options.requestCorrelation.roundId;headers[AIRI_CHAT_APP_SURFACE_HEADER]=getConversationAnalyticsSurface()}'

$oldLength = [Text.Encoding]::UTF8.GetByteCount($oldBlock)
$newLength = [Text.Encoding]::UTF8.GetByteCount($newBlock)
if ($oldLength -ne 332 -or $newLength -ne $oldLength) {
    throw "Internal patch length mismatch: old=$oldLength new=$newLength"
}

$oldCount = [AiriSessionHeaderPatcher]::Count($resolvedAsar, $oldBlock)
$newCount = [AiriSessionHeaderPatcher]::Count($resolvedAsar, $newBlock)
$currentHash = Get-Sha256 $resolvedAsar
$backup = "$resolvedAsar.backup-pristine"
if (Test-Path -LiteralPath $backup) {
    $backupHash = Get-Sha256 $backup
    if ($backupHash -ne $knownPristineAsarSha256) {
        throw "Pristine backup SHA-256 mismatch: got $backupHash, expected $knownPristineAsarSha256. Refusing to patch."
    }
}
$state = if ($oldCount -eq 1 -and $newCount -eq 0 -and
              ($currentHash -eq $knownPristineAsarSha256 -or $currentHash -eq $knownPreSessionAsarSha256)) { 'stock' }
         elseif ($oldCount -eq 0 -and $newCount -eq 1 -and
                 ($currentHash -eq $knownPostSessionPristineAsarSha256 -or $currentHash -eq $knownPostSessionPreSessionAsarSha256)) { 'patched' }
         else { 'unrecognized' }
if ($VerifyOnly) {
    [pscustomobject]@{
        Patch = 'session-header'
        State = $state
        StockMatches = $oldCount
        PatchedMatches = $newCount
        ArchiveSha256 = $currentHash
        EqualLengthBytes = $oldLength
    } | Format-List
    if ($state -ne 'unrecognized') { exit 0 }
    exit 1
}

if ($state -eq 'unrecognized') {
    throw "Unrecognized app.asar marker/hash state (stock=$oldCount, patched=$newCount, SHA-256=$currentHash). Refusing to patch; -Force does not override archive-hash checks."
}
if ($state -eq 'patched') {
    Write-Output 'AIRI session-header patch is already applied.'
    Write-Output 'Only the session ID is shared with custom providers; round/app-surface analytics remain official-only.'
    exit 0
}
$expectedPostHash = if ($currentHash -eq $knownPristineAsarSha256) {
    $knownPostSessionPristineAsarSha256
}
elseif ($currentHash -eq $knownPreSessionAsarSha256) {
    $knownPostSessionPreSessionAsarSha256
}
else {
    throw "No expected post-session hash mapping exists for SHA-256=$currentHash. Refusing to patch."
}

if (Test-Path -LiteralPath $backup) {
    Write-Output "Pristine backup exists: $backup"
}
else {
    if ($currentHash -eq $knownPristineAsarSha256) {
        Copy-Item -LiteralPath $resolvedAsar -Destination $backup
        Write-Output "Created pristine backup: $backup"
    }
    elseif (-not $Force) {
        throw 'No pristine backup exists for the known pre-session archive. Refusing to patch without -Force.'
    }
    else {
        Write-Warning 'Continuing without a pristine backup because -Force was supplied for a known pre-session archive.'
    }
}

$patched = [AiriSessionHeaderPatcher]::Patch($resolvedAsar, $oldBlock, $newBlock, $expectedPostHash)
if ($patched) {
    Write-Output 'Patched AIRI custom-provider requests to send x-airi-session-id.'
}
else {
    Write-Output 'AIRI session-header patch is already applied.'
}
Write-Output 'Only the session ID is shared with custom providers; round/app-surface analytics remain official-only.'
