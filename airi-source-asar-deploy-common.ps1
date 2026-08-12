#Requires -Version 5.1

Set-StrictMode -Version Latest

$script:AiriMinimumAsarBytes = 1MB
$script:AiriMaximumHeaderBytes = 16MB

if (-not ('AiriSourceAsarNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static class AiriSourceAsarNative
{
    [StructLayout(LayoutKind.Sequential)]
    private struct BY_HANDLE_FILE_INFORMATION
    {
        public uint FileAttributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetFileInformationByHandle(
        SafeFileHandle handle,
        out BY_HANDLE_FILE_INFORMATION information);

    public static string GetFileIdentity(SafeFileHandle handle)
    {
        BY_HANDLE_FILE_INFORMATION information;
        if (!GetFileInformationByHandle(handle, out information))
            throw new Win32Exception(Marshal.GetLastWin32Error());

        return String.Format(
            "{0:X8}:{1:X8}:{2:X8}",
            information.VolumeSerialNumber,
            information.FileIndexHigh,
            information.FileIndexLow);
    }
}
'@
}

function Assert-AiriNoReparseAncestors {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Description
    )

    $fullPath = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($fullPath)
    if ($root -notmatch '^[A-Za-z]:\\$') {
        throw "$Description must be on a local drive: $Path"
    }

    $current = $root
    $rootItem = Get-Item -LiteralPath $current -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Description has a reparse-point drive root: $root"
    }

    $relative = $fullPath.Substring($root.Length)
    foreach ($component in $relative.Split([char[]]@('\', '/'), [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $component
        if (-not (Test-Path -LiteralPath $current)) {
            throw "$Description does not exist: $Path"
        }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Description contains a reparse-point component: $current"
        }
    }
}

function Get-AiriNormalPath {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Description,
        [switch]$Directory
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Description must not be empty."
    }
    Assert-AiriNoReparseAncestors -Path $Path -Description $Description
    $item = Get-Item -LiteralPath $Path -Force
    if ($Directory -and -not $item.PSIsContainer) {
        throw "$Description must be a directory: $Path"
    }
    if (-not $Directory -and $item.PSIsContainer) {
        throw "$Description must be a regular file: $Path"
    }

    $fullName = [IO.Path]::GetFullPath($item.FullName)
    [pscustomobject]@{
        Item = $item
        FullName = $fullName
        CanonicalKey = $fullName.ToLowerInvariant()
    }
}

function Get-AiriFileIdentity {
    param([Parameter(Mandatory)][string]$Path)

    $share = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
    try {
        [AiriSourceAsarNative]::GetFileIdentity($stream.SafeFileHandle)
    }
    finally {
        $stream.Dispose()
    }
}

function Test-AiriSameFile {
    param(
        [Parameter(Mandatory)][string]$First,
        [Parameter(Mandatory)][string]$Second
    )

    (Get-AiriFileIdentity -Path $First) -eq (Get-AiriFileIdentity -Path $Second)
}

function Get-AiriFileDigest {
    param([Parameter(Mandatory)][string]$Path)

    $item = Get-Item -LiteralPath $Path -Force
    $hash = Get-FileHash -LiteralPath $Path -Algorithm SHA256
    [pscustomobject]@{
        Length = [Int64]$item.Length
        Sha256 = $hash.Hash.ToLowerInvariant()
    }
}

function Read-AiriExactly {
    param(
        [Parameter(Mandatory)][IO.Stream]$Stream,
        [Parameter(Mandatory)][byte[]]$Buffer,
        [int]$Offset = 0,
        [int]$Count = $Buffer.Length
    )

    $readTotal = 0
    while ($readTotal -lt $Count) {
        $read = $Stream.Read($Buffer, $Offset + $readTotal, $Count - $readTotal)
        if ($read -le 0) {
            throw 'Unexpected end of file while reading ASAR data.'
        }
        $readTotal += $read
    }
}

function Get-AiriJsonProperty {
    param(
        [Parameter(Mandatory)]$Object,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Description
    )

    if ($null -eq $Object -or $null -eq $Object.PSObject) {
        throw "$Description is not an object."
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        throw "$Description is missing '$Name'."
    }
    $property.Value
}

function Get-AiriAsarEntry {
    param(
        [Parameter(Mandatory)]$Header,
        [Parameter(Mandatory)][string[]]$Segments,
        [Parameter(Mandatory)][Int64]$ContentStart,
        [Parameter(Mandatory)][Int64]$ArchiveLength
    )

    $node = Get-AiriJsonProperty -Object $Header -Name 'files' -Description 'ASAR header'
    for ($index = 0; $index -lt $Segments.Count; $index++) {
        $segment = $Segments[$index]
        $node = Get-AiriJsonProperty -Object $node -Name $segment -Description "ASAR entry $($Segments[0..$index] -join '/')"
        if ($index -lt $Segments.Count - 1) {
            $node = Get-AiriJsonProperty -Object $node -Name 'files' -Description "ASAR directory $($Segments[0..$index] -join '/')"
        }
    }

    $sizeValue = Get-AiriJsonProperty -Object $node -Name 'size' -Description "ASAR file $($Segments -join '/')"
    $integerTypes = @(
        [TypeCode]::Byte, [TypeCode]::SByte, [TypeCode]::Int16, [TypeCode]::UInt16,
        [TypeCode]::Int32, [TypeCode]::UInt32, [TypeCode]::Int64, [TypeCode]::UInt64
    )
    if ($null -eq $sizeValue -or $integerTypes -notcontains [Type]::GetTypeCode($sizeValue.GetType())) {
        throw "ASAR file $($Segments -join '/') has a non-integer size."
    }
    try { $size = [Convert]::ToInt64($sizeValue) }
    catch { throw "ASAR file $($Segments -join '/') has an out-of-range size." }
    if ($size -lt 0) {
        throw "ASAR file $($Segments -join '/') has a negative size."
    }

    $offsetValue = Get-AiriJsonProperty -Object $node -Name 'offset' -Description "ASAR file $($Segments -join '/')"
    if ($offsetValue -isnot [string] -or $offsetValue -notmatch '^(0|[1-9][0-9]*)$') {
        throw "ASAR file $($Segments -join '/') has an invalid decimal offset."
    }
    $offset = 0L
    if (-not [Int64]::TryParse($offsetValue, [Globalization.NumberStyles]::None, [Globalization.CultureInfo]::InvariantCulture, [ref]$offset)) {
        throw "ASAR file $($Segments -join '/') has an out-of-range offset."
    }

    $absoluteEnd = [decimal]$ContentStart + [decimal]$offset + [decimal]$size
    if ($absoluteEnd -gt [decimal]$ArchiveLength) {
        throw "ASAR file $($Segments -join '/') extends beyond the archive."
    }

    [pscustomobject]@{
        Node = $node
        Offset = $offset
        Size = $size
        AbsoluteOffset = $ContentStart + $offset
    }
}

function Assert-AiriAsar {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Description
    )

    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        if ($stream.Length -lt $script:AiriMinimumAsarBytes) {
            throw "$Description is implausibly small ($($stream.Length) bytes)."
        }

        $lead = New-Object byte[] 16
        Read-AiriExactly -Stream $stream -Buffer $lead
        $outerSize = [BitConverter]::ToUInt32($lead, 0)
        $headerSize = [Int64][BitConverter]::ToUInt32($lead, 4)
        $innerSize = [Int64][BitConverter]::ToUInt32($lead, 8)
        $jsonSize = [Int64][BitConverter]::ToUInt32($lead, 12)
        if ($outerSize -ne 4 -or $headerSize -lt 8 -or $headerSize -gt $script:AiriMaximumHeaderBytes -or
            ($headerSize % 4) -ne 0 -or $innerSize -ne ($headerSize - 4) -or (8L + $headerSize) -gt $stream.Length) {
            throw "$Description has inconsistent ASAR pickle sizes."
        }
        $paddingSize = $innerSize - 4 - $jsonSize
        if ($jsonSize -lt 2 -or $paddingSize -lt 0 -or $paddingSize -gt 3) {
            throw "$Description has an invalid ASAR JSON payload size."
        }

        $jsonBytes = New-Object byte[] ([int]$jsonSize)
        Read-AiriExactly -Stream $stream -Buffer $jsonBytes
        $padding = New-Object byte[] ([int]$paddingSize)
        if ($padding.Length -gt 0) {
            Read-AiriExactly -Stream $stream -Buffer $padding
            if (@($padding | Where-Object { $_ -ne 0 }).Count -ne 0) {
                throw "$Description has non-zero ASAR pickle padding."
            }
        }

        $strictUtf8 = New-Object Text.UTF8Encoding($false, $true)
        try { $headerJson = $strictUtf8.GetString($jsonBytes) }
        catch { throw "$Description ASAR header is not strict UTF-8." }
        try { $header = $headerJson | ConvertFrom-Json }
        catch { throw "$Description ASAR header is not valid JSON." }
        if ($header -isnot [pscustomobject]) {
            throw "$Description ASAR header must be a JSON object."
        }

        $contentStart = 8L + $headerSize
        $packageEntry = Get-AiriAsarEntry -Header $header -Segments @('package.json') -ContentStart $contentStart -ArchiveLength $stream.Length
        if ($packageEntry.Size -le 0 -or $packageEntry.Size -gt 1MB) {
            throw "$Description package.json has an invalid size."
        }
        foreach ($criticalPath in @(
            @('out', 'main', 'index.js'),
            @('out', 'preload', 'index.mjs'),
            @('out', 'renderer', 'index.html')
        )) {
            $entry = Get-AiriAsarEntry -Header $header -Segments $criticalPath -ContentStart $contentStart -ArchiveLength $stream.Length
            if ($entry.Size -le 0) {
                throw "$Description critical entry $($criticalPath -join '/') is empty."
            }
        }

        $stream.Position = $packageEntry.AbsoluteOffset
        $packageBytes = New-Object byte[] ([int]$packageEntry.Size)
        Read-AiriExactly -Stream $stream -Buffer $packageBytes
        try { $packageJson = $strictUtf8.GetString($packageBytes) }
        catch { throw "$Description package.json is not strict UTF-8." }
        try { $package = $packageJson | ConvertFrom-Json }
        catch { throw "$Description package.json is not valid JSON." }
        if ($package.name -ne 'ai.moeru.airi' -or $package.version -ne '0.11.3') {
            throw "$Description is not AIRI ai.moeru.airi version 0.11.3."
        }

        $integrityProperty = $packageEntry.Node.PSObject.Properties['integrity']
        if ($null -ne $integrityProperty) {
            $integrity = $integrityProperty.Value
            $algorithm = Get-AiriJsonProperty -Object $integrity -Name 'algorithm' -Description 'package.json integrity'
            $expectedHash = Get-AiriJsonProperty -Object $integrity -Name 'hash' -Description 'package.json integrity'
            if ($algorithm -ne 'SHA256' -or $expectedHash -notmatch '^[A-Fa-f0-9]{64}$') {
                throw "$Description package.json has invalid integrity metadata."
            }
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $actualHash = ([BitConverter]::ToString($sha.ComputeHash($packageBytes))).Replace('-', '').ToLowerInvariant() }
            finally { $sha.Dispose() }
            if ($actualHash -ne $expectedHash.ToLowerInvariant()) {
                throw "$Description package.json integrity hash does not match its payload."
            }
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Copy-AiriFileNew {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Destination
    )

    $inputStream = [IO.File]::Open($Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        $outputStream = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $inputStream.CopyTo($outputStream)
            $outputStream.Flush($true)
        }
        finally { $outputStream.Dispose() }
    }
    finally { $inputStream.Dispose() }
}

function New-AiriVerifiedStage {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$TargetDirectory,
        [Parameter(Mandatory)][string]$Prefix,
        [Parameter(Mandatory)][Int64]$ExpectedLength,
        [Parameter(Mandatory)][string]$ExpectedSha256,
        [switch]$SkipAsarValidation
    )

    $stagePath = Join-Path $TargetDirectory ($Prefix + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        Copy-AiriFileNew -Source $Source -Destination $stagePath
        $digest = Get-AiriFileDigest -Path $stagePath
        if ($digest.Length -ne $ExpectedLength -or $digest.Sha256 -ne $ExpectedSha256.ToLowerInvariant()) {
            throw 'Staged archive digest does not match its pinned source.'
        }
        if (-not $SkipAsarValidation) {
            Assert-AiriAsar -Path $stagePath -Description 'staged app.asar'
        }
        [pscustomobject]@{ Path = $stagePath; Digest = $digest }
    }
    catch {
        if (Test-Path -LiteralPath $stagePath) {
            Remove-Item -LiteralPath $stagePath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Assert-AiriStopped {
    param(
        [Parameter(Mandatory)][string]$ExecutablePath,
        [Parameter(Mandatory)][string]$Operation
    )

    foreach ($process in @(Get-Process -Name 'airi' -ErrorAction SilentlyContinue)) {
        try { $actualPath = $process.Path }
        catch { throw "Could not inspect an AIRI process path; refusing $Operation." }
        if ([string]::IsNullOrWhiteSpace($actualPath)) {
            throw "Could not inspect an AIRI process path; refusing $Operation."
        }
        if ([IO.Path]::GetFullPath($actualPath).Equals($ExecutablePath, [StringComparison]::OrdinalIgnoreCase)) {
            throw "AIRI is running from the requested InstallDir; refusing $Operation."
        }
    }
}

function Enter-AiriExecutableBarrier {
    param(
        [Parameter(Mandatory)][string]$ExecutablePath,
        [Parameter(Mandatory)][string]$Operation
    )

    Assert-AiriStopped -ExecutablePath $ExecutablePath -Operation $Operation
    try {
        $barrier = [IO.File]::Open($ExecutablePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    }
    catch {
        throw "Could not acquire the exclusive AIRI executable launch barrier; refusing $Operation. $($_.Exception.Message)"
    }
    try {
        Assert-AiriStopped -ExecutablePath $ExecutablePath -Operation $Operation
        $barrier
    }
    catch {
        $barrier.Dispose()
        throw
    }
}

function Get-AiriDeploymentMutexName {
    param([Parameter(Mandatory)][string]$CanonicalTargetPath)

    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($CanonicalTargetPath.ToLowerInvariant())
        $digest = $sha.ComputeHash($bytes)
    }
    finally { $sha.Dispose() }
    'Global\AiriSourceAsarDeploy_' + ([BitConverter]::ToString($digest)).Replace('-', '').Substring(0, 32)
}

function Enter-AiriDeploymentMutex {
    param([Parameter(Mandatory)][string]$CanonicalTargetPath)

    try { $mutex = [Threading.Mutex]::new($false, (Get-AiriDeploymentMutexName -CanonicalTargetPath $CanonicalTargetPath)) }
    catch { throw "Could not create the cross-session ASAR deployment mutex. $($_.Exception.Message)" }
    try {
        try { $held = $mutex.WaitOne([TimeSpan]::FromSeconds(30)) }
        catch [Threading.AbandonedMutexException] { $held = $true }
        if (-not $held) {
            throw 'Timed out waiting for another ASAR deployment operation.'
        }
        [pscustomobject]@{ Mutex = $mutex; Held = $true }
    }
    catch {
        $mutex.Dispose()
        throw
    }
}

function Exit-AiriDeploymentMutex {
    param($MutexState)
    if ($null -ne $MutexState) {
        if ($MutexState.Held) { $MutexState.Mutex.ReleaseMutex() }
        $MutexState.Mutex.Dispose()
    }
}

function Restore-AiriExactDisplacedFile {
    param(
        [Parameter(Mandatory)][string]$DisplacedPath,
        [Parameter(Mandatory)][string]$TargetPath,
        [Parameter(Mandatory)][string]$TargetDirectory,
        [Parameter(Mandatory)]$DisplacedDigest
    )

    $stage = New-AiriVerifiedStage -Source $DisplacedPath -TargetDirectory $TargetDirectory `
        -Prefix '.app.asar.rollback-stage-' -ExpectedLength $DisplacedDigest.Length `
        -ExpectedSha256 $DisplacedDigest.Sha256 -SkipAsarValidation
    $failedCandidatePath = Join-Path $TargetDirectory ('app.asar.airi-failed-candidate-' + [guid]::NewGuid().ToString('N') + '.bak')
    try {
        [IO.File]::Replace($stage.Path, $TargetPath, $failedCandidatePath, $true)
        $restored = Get-AiriFileDigest -Path $TargetPath
        if ($restored.Length -ne $DisplacedDigest.Length -or $restored.Sha256 -ne $DisplacedDigest.Sha256) {
            throw 'Exact displaced-file rollback verification failed.'
        }
        [pscustomobject]@{ RestoredDigest = $restored; FailedCandidatePath = $failedCandidatePath }
    }
    finally {
        if (Test-Path -LiteralPath $stage.Path) {
            Remove-Item -LiteralPath $stage.Path -Force -ErrorAction SilentlyContinue
        }
    }
}
