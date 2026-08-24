[CmdletBinding()]
param(
    [string]$RunDir,

    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 600,

    [ValidateRange(1, 15)]
    [int]$PollSeconds = 2,

    [ValidateRange(0, 60000)]
    [int]$TestOnlyFinalGateDelayMilliseconds = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
if ($TestOnlyFinalGateDelayMilliseconds -gt 0 -and $env:AIRI_DURABILITY_TEST_HOOKS -ne '1') {
    throw 'TestOnlyFinalGateDelayMilliseconds requires AIRI_DURABILITY_TEST_HOOKS=1'
}

function Resolve-RequiredLocalRunDirectory {
    param([Parameter(Mandatory = $true)][string]$Value)

    if ($Value.StartsWith('\\') -or $Value.StartsWith('//') -or $Value.Contains('://')) {
        throw 'RunDir must be a local filesystem path'
    }
    $full = [IO.Path]::GetFullPath($Value)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.TrimEnd('\') -eq $root.TrimEnd('\')) {
        throw 'RunDir cannot be a volume root'
    }
    $drive = [IO.DriveInfo]::new($root)
    if ($drive.DriveType -ne [IO.DriveType]::Fixed) {
        throw 'RunDir must be on a local fixed volume; mapped and removable drives are forbidden'
    }
    $probe = $full
    while (-not (Test-Path -LiteralPath $probe)) {
        $parent = Split-Path -Parent $probe
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $probe) {
            throw 'RunDir has no verifiable existing local ancestor'
        }
        $probe = $parent
    }
    while (Test-Path -LiteralPath $probe) {
        $item = Get-Item -LiteralPath $probe -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'RunDir cannot traverse a reparse point'
        }
        $parent = Split-Path -Parent $probe
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $probe) {
            break
        }
        $probe = $parent
    }
    return $full
}

function Get-Utf8Sha256 {
    param([Parameter(Mandatory = $true)][string]$Value)

    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Value)
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($hash.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hash.Dispose()
    }
}

function Get-BytesSha256 {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($hash.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hash.Dispose()
    }
}

function Read-AuthoritativeFileSnapshot {
    <#
    Read an authority file through one Windows handle.  Opening the final
    component with OPEN_REPARSE_POINT lets us reject links rather than following
    them; FILE_SHARE_READ denies delete/write replacement until the bytes and
    file identity have both been observed.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not ('AiriPauseReadSnapshot' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public sealed class AiriPauseSnapshotValue {
    public byte[] Bytes;
    public long Length;
    public uint VolumeSerialNumber;
    public uint FileIndexHigh;
    public uint FileIndexLow;
}

public static class AiriPauseReadSnapshot {
    const uint GENERIC_READ = 0x80000000;
    const uint FILE_SHARE_READ = 0x00000001;
    const uint OPEN_EXISTING = 3;
    const uint FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000;
    const uint FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400;
    const uint FILE_ATTRIBUTE_DIRECTORY = 0x00000010;
    static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential)]
    struct BY_HANDLE_FILE_INFORMATION {
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

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CreateFileW(string name, uint access, uint share,
        IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetFileInformationByHandle(IntPtr handle,
        out BY_HANDLE_FILE_INFORMATION information);

    public static AiriPauseSnapshotValue Read(string path) {
        IntPtr raw = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ,
            IntPtr.Zero, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, IntPtr.Zero);
        if (raw == INVALID_HANDLE_VALUE) {
            throw new IOException("CreateFileW failed: " + Marshal.GetLastWin32Error());
        }
        using (var handle = new SafeFileHandle(raw, true)) {
            BY_HANDLE_FILE_INFORMATION info;
            if (!GetFileInformationByHandle(handle.DangerousGetHandle(), out info)) {
                throw new IOException("GetFileInformationByHandle failed: " + Marshal.GetLastWin32Error());
            }
            if ((info.FileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY)) != 0) {
                throw new IOException("authority path is a reparse point or directory");
            }
            ulong size = ((ulong)info.FileSizeHigh << 32) | info.FileSizeLow;
            if (size > Int32.MaxValue) {
                throw new IOException("authority file is too large for an atomic snapshot");
            }
            byte[] bytes = new byte[(int)size];
            using (var stream = new FileStream(handle, FileAccess.Read, 4096, false)) {
                int offset = 0;
                while (offset < bytes.Length) {
                    int count = stream.Read(bytes, offset, bytes.Length - offset);
                    if (count <= 0) throw new EndOfStreamException("authority file changed while being read");
                    offset += count;
                }
                if (stream.ReadByte() != -1) throw new IOException("authority file length changed while being read");
            }
            return new AiriPauseSnapshotValue {
                Bytes = bytes, Length = bytes.LongLength,
                VolumeSerialNumber = info.VolumeSerialNumber,
                FileIndexHigh = info.FileIndexHigh, FileIndexLow = info.FileIndexLow
            };
        }
    }
}
'@
    }
    try {
        return [AiriPauseReadSnapshot]::Read($Path)
    }
    catch {
        throw "$Label cannot be read through a no-follow authority handle: $($_.Exception.Message)"
    }
}

function Get-CanonicalJsonValue {
    param([AllowNull()]$Value)

    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) { return $(if ($Value) { 'true' } else { 'false' }) }
    if ($Value -is [string]) { return ($Value | ConvertTo-Json -Compress) }
    if ($Value -is [byte] -or $Value -is [sbyte] -or $Value -is [int16] -or
        $Value -is [uint16] -or $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64]) {
        return [Convert]::ToString($Value, [Globalization.CultureInfo]::InvariantCulture)
    }
    if ($Value -is [double] -or $Value -is [single] -or $Value -is [decimal]) {
        # JSON authority files used here deliberately contain only integral
        # counters outside the manifest pins object.  Refuse a representation
        # PowerShell cannot prove byte-for-byte equivalent to Python JSON.
        throw 'non-integral value is not permitted in a PowerShell authority JSON canonicalization'
    }
    if ($Value -is [Collections.IDictionary]) {
        $names = @($Value.Keys | ForEach-Object { [string]$_ } | Sort-Object)
        return '{' + (($names | ForEach-Object {
                    (($_ | ConvertTo-Json -Compress) + ':' + (Get-CanonicalJsonValue $Value[$_]))
                }) -join ',') + '}'
    }
    if ($Value -is [Collections.IEnumerable]) {
        return '[' + ((@($Value) | ForEach-Object { Get-CanonicalJsonValue $_ }) -join ',') + ']'
    }
    $names = @($Value.PSObject.Properties.Name | Sort-Object)
    return '{' + (($names | ForEach-Object {
                (($_ | ConvertTo-Json -Compress) + ':' + (Get-CanonicalJsonValue $Value.$_))
            }) -join ',') + '}'
}

function Read-CanonicalAuthorityJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $snapshot = Read-AuthoritativeFileSnapshot $Path $Label
    try {
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($snapshot.Bytes)
        $value = $text | ConvertFrom-Json
        if ($text -cne ((Get-CanonicalJsonValue $value) + "`n")) {
            throw "$Label is not canonical JSON"
        }
        return [pscustomobject]@{ value = $value; bytes = $snapshot.Bytes; snapshot = $snapshot }
    }
    catch {
        throw "$Label is not canonical UTF-8 authority JSON: $($_.Exception.Message)"
    }
}

function Read-AuthorityJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $snapshot = Read-AuthoritativeFileSnapshot $Path $Label
    try {
        return [pscustomobject]@{
            value = ([Text.UTF8Encoding]::new($false, $true).GetString($snapshot.Bytes) | ConvertFrom-Json)
            bytes = $snapshot.Bytes
            snapshot = $snapshot
        }
    }
    catch {
        throw "$Label is not UTF-8 JSON: $($_.Exception.Message)"
    }
}

function Test-ExactProcessRecord {
    param([AllowNull()]$Record)

    if ($null -eq $Record -or $null -eq $Record.pid) {
        return $false
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$Record.pid)" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $false
    }
    $created = $process.CreationDate.ToUniversalTime().ToString('o')
    $executableHash = Get-Utf8Sha256 (([string]$process.ExecutablePath).ToLowerInvariant())
    $commandHash = Get-Utf8Sha256 ([string]$process.CommandLine)
    return ($created -eq [string]$Record.creation_time_utc -and
        $executableHash -eq [string]$Record.executable_path_sha256 -and
        $commandHash -eq [string]$Record.command_line_sha256)
}

function Get-RecordedProcessExitStatus {
    param([Parameter(Mandatory = $true)]$Record)

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$Record.pid)" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return 'exited'
    }
    if (Test-ExactProcessRecord $Record) {
        return 'live'
    }
    # A live process with this PID is not evidence that the recorded runner exited:
    # it can be a reused PID or a replaced process.  Fail closed in that case.
    return 'replaced'
}

function Start-RemainingDeadlineSleep {
    param(
        [Parameter(Mandatory = $true)][DateTime]$Deadline,
        [Parameter(Mandatory = $true)][double]$MaximumSeconds
    )

    $remainingMilliseconds = ($Deadline - [DateTime]::UtcNow).TotalMilliseconds
    if ($remainingMilliseconds -le 0) {
        return $false
    }
    $sleepMilliseconds = [Math]::Max(1, [Math]::Ceiling([Math]::Min(
            $remainingMilliseconds, $MaximumSeconds * 1000)))
    Start-Sleep -Milliseconds ([int]$sleepMilliseconds)
    return $true
}

function Assert-SameProcessRecord {
    param(
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)][string]$Label
    )

    foreach ($property in @(
            'pid', 'creation_time_utc', 'executable_path_sha256', 'command_line_sha256')) {
        if ([string]$Expected.$property -ne [string]$Actual.$property) {
            throw "$Label process identity changed while waiting for safe power-off"
        }
    }
}

function Assert-TerminalStateUnchanged {
    param(
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)]$Actual
    )

    if ([string]$Expected.run_id -ne [string]$Actual.run_id -or
        [int64]$Expected.revision -ne [int64]$Actual.revision -or
        [string]$Expected.status -ne [string]$Actual.status) {
        throw 'Terminal run-state changed before SAFE_TO_POWER_OFF emission'
    }
    Assert-SameProcessRecord $Expected.runner $Actual.runner 'Runner'
    Assert-SameProcessRecord $Expected.trainer $Actual.trainer 'Trainer'
}

function Assert-ExactJsonProperties {
    param(
        [AllowNull()]$Value,
        [Parameter(Mandatory = $true)][string[]]$Names,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($null -eq $Value) {
        throw "$Label is missing"
    }
    $actual = if ($Value -is [Collections.IDictionary]) {
        @($Value.Keys | ForEach-Object { [string]$_ } | Sort-Object)
    }
    else {
        @($Value.PSObject.Properties.Name | Sort-Object)
    }
    $expected = @($Names | Sort-Object)
    if ($actual.Count -ne $expected.Count) {
        throw "$Label property set is invalid"
    }
    for ($index = 0; $index -lt $expected.Count; $index++) {
        if ([string]$actual[$index] -ne [string]$expected[$index]) {
            throw "$Label property set is invalid"
        }
    }
}

function Read-ValidRunStateCandidate {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    try {
        $receipt = Read-AuthorityJson $Path 'run-state'
        $candidate = $receipt.value
        Assert-ExactJsonProperties -Value $candidate -Names @(
            'schema_version', 'revision', 'run_id', 'status', 'created_at_utc',
            'updated_at_utc', 'runner', 'trainer', 'inputs', 'command', 'progress',
            'heartbeat', 'checkpoint', 'logs', 'outputs', 'terminal') -Label 'run-state'
        if ([string]$candidate.schema_version -ne 'airi.behavior-durable-run.v1' -or
            [string]::IsNullOrWhiteSpace([string]$candidate.run_id) -or
            [int64]$candidate.revision -lt 0 -or
            [string]$candidate.status -notin @(
                'starting', 'running', 'pause-requested', 'checkpointing', 'paused-safe',
                'resuming', 'complete', 'failed', 'interrupted')) {
            return $null
        }
        $processProperties = @(
            'pid', 'creation_time_utc', 'executable_path_sha256', 'command_line_sha256')
        foreach ($label in @('runner', 'trainer')) {
            $record = $candidate.$label
            if ($null -eq $record) {
                if ($label -eq 'runner') {
                    return $null
                }
                continue
            }
            try {
                Assert-ExactJsonProperties -Value $record -Names $processProperties -Label "$label process record"
            }
            catch {
                return $null
            }
            if ([int64]$record.pid -le 0 -or
                [string]::IsNullOrWhiteSpace([string]$record.creation_time_utc) -or
                [string]$record.executable_path_sha256 -notmatch '^[0-9a-f]{64}$' -or
                [string]$record.command_line_sha256 -notmatch '^[0-9a-f]{64}$') {
                return $null
            }
        }
        $terminalStatus = [string]$candidate.status -in @(
            'paused-safe', 'complete', 'failed', 'interrupted')
        if (($terminalStatus -and $null -eq $candidate.terminal) -or
            (-not $terminalStatus -and $null -ne $candidate.terminal)) {
            return $null
        }
        if ([string]$candidate.status -eq 'paused-safe') {
            try {
                Assert-ExactJsonProperties -Value $candidate.terminal -Names @(
                    'exit_code', 'reason', 'at_utc', 'checkpoint_verification') `
                    -Label 'paused-safe terminal receipt'
                Assert-ExactJsonProperties -Value $candidate.terminal.checkpoint_verification -Names @(
                    'schema_version', 'checkpoint_relative_path',
                    'checkpoint_manifest_sha256', 'checkpoint_payload_sha256',
                    'checkpoint_payload_bytes', 'canonical_pins_sha256') `
                    -Label 'paused-safe checkpoint verification receipt'
            }
            catch {
                return $null
            }
            if ([int]$candidate.terminal.exit_code -ne 75 -or
                [string]$candidate.terminal.reason -ne 'safe-optimizer-boundary' -or
                [string]$candidate.terminal.checkpoint_verification.schema_version -ne
                    'airi.behavior-checkpoint-verification.v1') {
                return $null
            }
        }
        # A terminal receipt is only useful for power-off when it freezes both
        # process identities.  A null trainer would otherwise turn a replaced
        # child into an unobservable success path.
        if ($terminalStatus -and $null -eq $candidate.trainer) {
            return $null
        }
        $candidate | Add-Member -NotePropertyName '__authority_sha256' -NotePropertyValue (Get-BytesSha256 $receipt.bytes) -Force
        $candidate | Add-Member -NotePropertyName '__authority_run_id' -NotePropertyValue ([string]$candidate.run_id) -Force
        $candidate | Add-Member -NotePropertyName '__authority_revision' -NotePropertyValue ([int64]$candidate.revision) -Force
        return $candidate
    }
    catch {
        return $null
    }
}

function Read-RunStateAnchor {
    param([Parameter(Mandatory = $true)][string]$RunDirectory)
    $receipt = Read-CanonicalAuthorityJson (Join-Path $RunDirectory 'run-state.anchor.json') 'run-state anchor'
    $anchor = $receipt.value
    Assert-ExactJsonProperties -Value $anchor -Names @('schema_version', 'run_id', 'current', 'previous') -Label 'run-state anchor'
    if ([string]$anchor.schema_version -ne 'airi.behavior-durable-run-anchor.v1' -or
            [string]::IsNullOrWhiteSpace([string]$anchor.run_id) -or $null -eq $anchor.current) {
        throw 'run-state anchor schema is invalid'
    }
    foreach ($name in @('current', 'previous')) {
        $entry = $anchor.$name
        if ($null -eq $entry) { continue }
        Assert-ExactJsonProperties -Value $entry -Names @('sha256', 'revision') -Label "run-state anchor $name"
        if ([string]$entry.sha256 -notmatch '^[0-9a-f]{64}$' -or [int64]$entry.revision -lt 0) {
            throw "run-state anchor $name is invalid"
        }
    }
    return $anchor
}

function Test-AnchorAuthorizedRunState {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$Anchor,
        [Parameter(Mandatory = $true)][string]$ReceiptName
    )
    $entry = $Anchor.$ReceiptName
    return ($null -ne $entry -and [string]$State.__authority_run_id -eq [string]$Anchor.run_id -and
        [string]$State.__authority_sha256 -eq [string]$entry.sha256 -and
        [int64]$State.__authority_revision -eq [int64]$entry.revision)
}

function Read-RunState {
    param(
        [Parameter(Mandatory = $true)][string]$CurrentPath,
        [Parameter(Mandatory = $true)][string]$PreviousPath
    )
    $runDirectory = Split-Path -Parent $CurrentPath
    $anchor = Read-RunStateAnchor $runDirectory
    $current = Read-ValidRunStateCandidate $CurrentPath
    if ($null -ne $current -and (Test-AnchorAuthorizedRunState $current $anchor 'current')) {
        return $current
    }
    # Preserve a torn or malformed current receipt.  The durable runner owns its
    # quarantine/write-through protocol; pause only consumes a strict previous receipt.
    $previous = Read-ValidRunStateCandidate $PreviousPath
    if ($null -ne $previous) {
        # A current absence/unanchored receipt is an interrupted publication:
        # only the exact nonterminal predecessor committed as anchor.current
        # may bridge it.  A terminal previous is never rollback authority here.
        if ([string]$previous.status -in @('paused-safe', 'complete', 'failed', 'interrupted') -or
                -not (Test-AnchorAuthorizedRunState $previous $anchor 'current')) {
            throw 'An unanchored or terminal previous run-state cannot authorize power-off'
        }
        return $previous
    }
    throw 'No valid current or previous run-state receipt is available'
}

function ConvertFrom-WindowsCommandLine {
    param([Parameter(Mandatory = $true)][string]$CommandLine)

    if (-not ('AiriPauseCommandLine' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AiriPauseCommandLine {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr CommandLineToArgvW(string commandLine, out int argc);
    [DllImport("kernel32.dll")]
    public static extern IntPtr LocalFree(IntPtr hMem);
}
'@
    }
    $count = 0
    $pointer = [AiriPauseCommandLine]::CommandLineToArgvW($CommandLine, [ref]$count)
    if ($pointer -eq [IntPtr]::Zero -or $count -lt 1) {
        throw 'runner command line cannot be parsed'
    }
    try {
        $arguments = [Collections.Generic.List[string]]::new()
        for ($index = 0; $index -lt $count; $index++) {
            $itemAddress = [IntPtr]($pointer.ToInt64() + ($index * [IntPtr]::Size))
            $item = [Runtime.InteropServices.Marshal]::ReadIntPtr($itemAddress)
            $arguments.Add([Runtime.InteropServices.Marshal]::PtrToStringUni($item))
        }
        return $arguments.ToArray()
    }
    finally {
        [void][AiriPauseCommandLine]::LocalFree($pointer)
    }
}

function Get-RunnerCommandBinding {
    param([Parameter(Mandatory = $true)][string]$CommandLine)

    try { $arguments = @(ConvertFrom-WindowsCommandLine $CommandLine) }
    catch { return $null }
    $separatorIndex = [Array]::IndexOf($arguments, '--')
    $runnerArgumentCount = if ($separatorIndex -ge 0) { $separatorIndex } else { $arguments.Count }
    $scriptIndexes = @()
    for ($index = 0; $index -lt $runnerArgumentCount; $index++) {
        if ([string]$arguments[$index] -match '(?i)(^|[\\/])durable_training_runner\.py$') {
            $scriptIndexes += $index
        }
    }
    if ($scriptIndexes.Count -ne 1) { return $null }
    $scriptIndex = [int]$scriptIndexes[0]
    $runDirValues = @()
    $runIdValues = @()
    for ($index = $scriptIndex + 1; $index -lt $runnerArgumentCount; $index++) {
        if ($arguments[$index] -in @('--run-dir', '--run-id')) {
            if ($index + 1 -ge $arguments.Count -or $arguments[$index + 1].StartsWith('--')) { return $null }
            if ($arguments[$index] -eq '--run-dir') { $runDirValues += $arguments[$index + 1] }
            else { $runIdValues += $arguments[$index + 1] }
            $index++
        }
    }
    if ($runDirValues.Count -ne 1 -or $runIdValues.Count -ne 1) { return $null }
    return [pscustomobject]@{
        script_path = [string]$arguments[$scriptIndex]
        run_dir = [string]$runDirValues[0]
        run_id = [string]$runIdValues[0]
    }
}

function Find-ActiveDurableRunDirectory {
    $candidates = [Collections.Generic.List[object]]::new()
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        if ([string]::IsNullOrWhiteSpace([string]$process.CommandLine)) { continue }
        $binding = Get-RunnerCommandBinding ([string]$process.CommandLine)
        if ($null -eq $binding) { continue }
        try { $candidateDir = Resolve-RequiredLocalRunDirectory $binding.run_dir }
        catch { continue }
        $currentPath = Join-Path $candidateDir 'run-state.json'
        $previousPath = Join-Path $candidateDir 'run-state.prev.json'
        try { $state = Read-RunState $currentPath $previousPath }
        catch { continue }
        try {
            Assert-ExactJsonProperties -Value $state.command -Names @(
                'canonical_sha256', 'base_canonical_sha256',
                'runner_source_sha256', 'trainer_source_sha256') -Label 'run-state command'
            if ([string]$state.command.runner_source_sha256 -notmatch '^[0-9a-f]{64}$') { continue }
            $runnerScript = Resolve-RequiredLocalRunDirectory (Split-Path -Parent $binding.script_path)
            $runnerSourcePath = Join-Path $runnerScript (Split-Path -Leaf $binding.script_path)
            if ((Split-Path -Leaf $runnerSourcePath) -ne 'durable_training_runner.py' -or
                -not (Test-Path -LiteralPath $runnerSourcePath -PathType Leaf) -or
                ((Get-FileHash -LiteralPath $runnerSourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
                    [string]$state.command.runner_source_sha256)) { continue }
        }
        catch { continue }
        if ([string]$state.status -notin @('starting', 'running', 'pause-requested', 'checkpointing') -or
            [string]$state.run_id -ne $binding.run_id -or
            [int]$state.runner.pid -ne [int]$process.ProcessId -or
            -not (Test-ExactProcessRecord $state.runner)) { continue }
        $candidates.Add([pscustomobject]@{ run_dir = $candidateDir; run_id = [string]$state.run_id })
    }
    $unique = @($candidates | Group-Object run_dir | ForEach-Object { $_.Group[0] })
    if ($unique.Count -eq 0) {
        throw 'no active durable AIRI training run was found; specify -RunDir explicitly'
    }
    if ($unique.Count -ne 1) {
        $identifiers = @($unique | ForEach-Object { "run_id=$($_.run_id); RunDir=$($_.run_dir)" }) -join [Environment]::NewLine
        throw "more than one active durable AIRI training run was found; refusing automatic selection:$([Environment]::NewLine)$identifiers"
    }
    return [string]$unique[0].run_dir
}

if (-not $PSBoundParameters.ContainsKey('RunDir')) {
    $RunDir = Find-ActiveDurableRunDirectory
}
elseif ([string]::IsNullOrWhiteSpace($RunDir)) {
    throw 'RunDir cannot be empty when specified explicitly'
}
$resolvedRunDir = Resolve-RequiredLocalRunDirectory $RunDir
$statePath = Join-Path $resolvedRunDir 'run-state.json'
$previousStatePath = Join-Path $resolvedRunDir 'run-state.prev.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf) -and
    -not (Test-Path -LiteralPath $previousStatePath -PathType Leaf)) {
    throw 'run-state current and previous receipts are missing; no training run can be reconciled'
}

function Write-AtomicUtf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $directory = Split-Path -Parent $Path
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' +
        [Guid]::NewGuid().ToString('N') + '.tmp')
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Text)
    $stream = [IO.FileStream]::new(
        $temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write,
        [IO.FileShare]::None, 4096, [IO.FileOptions]::WriteThrough)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    }
    finally {
        $stream.Dispose()
    }
    try {
        if (-not ('AiriPauseNativeFile' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AiriPauseNativeFile {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool MoveFileEx(string source, string target, int flags);
}
'@
        }
        if (-not [AiriPauseNativeFile]::MoveFileEx($temporary, $Path, 0x8)) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "Write-through atomic pause request publication failed: Windows error $errorCode"
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Assert-DeadlineNotExpired {
    param(
        [Parameter(Mandatory = $true)][DateTime]$Deadline,
        [Parameter(Mandatory = $true)][string]$Phase
    )

    if ([DateTime]::UtcNow -ge $Deadline) {
        throw "Safe-pause deadline expired before $Phase"
    }
}

function Invoke-TestOnlyFinalGateDelay {
    if ($TestOnlyFinalGateDelayMilliseconds -gt 0) {
        Start-Sleep -Milliseconds $TestOnlyFinalGateDelayMilliseconds
    }
}

function Assert-VerifiedCheckpoint {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$Ack
    )

    Assert-DeadlineNotExpired $deadline 'checkpoint verification'
    $verification = $State.terminal.checkpoint_verification
    Assert-ExactJsonProperties -Value $verification -Names @(
        'schema_version', 'checkpoint_relative_path', 'checkpoint_manifest_sha256',
        'checkpoint_payload_sha256', 'checkpoint_payload_bytes',
        'canonical_pins_sha256') -Label 'authoritative checkpoint verification receipt'
    if ([string]$verification.schema_version -ne 'airi.behavior-checkpoint-verification.v1' -or
        [string]$verification.checkpoint_relative_path -notmatch '^checkpoint-[0-9]{8}$' -or
        [string]$verification.checkpoint_manifest_sha256 -notmatch '^[0-9a-f]{64}$' -or
        [string]$verification.checkpoint_payload_sha256 -notmatch '^[0-9a-f]{64}$' -or
        [string]$verification.canonical_pins_sha256 -notmatch '^[0-9a-f]{64}$' -or
        [int64]$verification.checkpoint_payload_bytes -lt 1) {
        throw 'authoritative checkpoint verification receipt is invalid'
    }
    if ($null -eq $State.checkpoint -or
        [string]$State.checkpoint.relative_path -ne [string]$Ack.checkpoint_relative_path -or
        [string]$State.checkpoint.manifest_sha256 -ne [string]$Ack.checkpoint_manifest_sha256 -or
        [string]$verification.checkpoint_relative_path -ne [string]$Ack.checkpoint_relative_path -or
        [string]$verification.checkpoint_manifest_sha256 -ne [string]$Ack.checkpoint_manifest_sha256) {
        throw 'run-state and pause ack checkpoint references differ'
    }
    $generation = [string]$Ack.checkpoint_relative_path
    if ($generation -notmatch '^checkpoint-[0-9]{8}$') {
        throw 'pause ack checkpoint generation is invalid'
    }
    $checkpointRoot = [IO.Path]::GetFullPath((Join-Path $resolvedRunDir 'checkpoints'))
    $generationDir = [IO.Path]::GetFullPath((Join-Path $checkpointRoot $generation))
    if ((Split-Path -Parent $generationDir) -ne $checkpointRoot) {
        throw 'checkpoint path escapes the run directory'
    }
    $manifestPath = Join-Path $generationDir 'manifest.json'
    if (-not (Test-Path -LiteralPath $generationDir -PathType Container) -or
        ((Get-Item -LiteralPath $generationDir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'checkpoint generation must be a regular non-reparse directory'
    }
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
        ((Get-Item -LiteralPath $manifestPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'checkpoint manifest is missing'
    }
    $manifestSnapshot = Read-AuthoritativeFileSnapshot $manifestPath 'checkpoint manifest'
    $manifestBytes = [byte[]]$manifestSnapshot.Bytes
    $manifestHash = Get-BytesSha256 $manifestBytes
    if ($manifestHash -ne [string]$Ack.checkpoint_manifest_sha256 -or
        $manifestHash -ne [string]$verification.checkpoint_manifest_sha256) {
        throw 'checkpoint manifest SHA does not match the pause ack'
    }
    $manifestText = [Text.UTF8Encoding]::new($false, $true).GetString($manifestBytes)
    $manifest = $manifestText | ConvertFrom-Json
    Assert-ExactJsonProperties -Value $manifest -Names @(
        'schema_version', 'generation', 'run_id', 'payload', 'pins') -Label 'checkpoint manifest'
    Assert-ExactJsonProperties -Value $manifest.payload -Names @(
        'name', 'bytes', 'sha256') -Label 'checkpoint payload'
    if ([int]$manifest.schema_version -ne 1 -or
        [string]$manifest.generation -ne $generation -or
        [string]$manifest.run_id -ne [string]$State.run_id -or
        [string]$manifest.payload.name -ne 'state.pt' -or
        $manifest.pins -isnot [Collections.IDictionary] -and $manifest.pins -isnot [pscustomobject] -or
        [int64]$manifest.payload.bytes -lt 1 -or
        [string]$manifest.payload.sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'checkpoint manifest identity is invalid'
    }
    # v2 inputs are the seven launch pins; v3 (adapter-weights-only initialization)
    # adds the init mode and the four E2 adapter provenance pins. Either exact set
    # is acceptable, never a mixture and never extra keys.
    $inputsV2 = @(
        'dataset_sha256', 'model_weight_sha256', 'input_manifest_path',
        'input_manifest_sha256', 'input_manifest_training_config_sha256',
        'trainer_source_sha256', 'checkpoint_helper_source_sha256')
    $inputsV3 = $inputsV2 + @(
        'init_mode', 'init_adapter_dir', 'init_adapter_model_sha256',
        'init_adapter_config_sha256', 'init_adapter_artifact_manifest_sha256')
    $inputNames = @($State.inputs.PSObject.Properties.Name)
    if ($inputNames -contains 'init_mode') {
        Assert-ExactJsonProperties -Value $State.inputs -Names $inputsV3 -Label 'run-state inputs'
        if ([string]$State.inputs.init_mode -notin @('fresh-lora', 'adapter-weights-only')) {
            throw 'run-state init mode is invalid'
        }
        if ([string]$State.inputs.init_mode -eq 'adapter-weights-only') {
            if ([string]::IsNullOrWhiteSpace([string]$State.inputs.init_adapter_dir)) {
                throw 'run-state init adapter directory is invalid'
            }
            foreach ($key in @('init_adapter_model_sha256', 'init_adapter_config_sha256',
                    'init_adapter_artifact_manifest_sha256')) {
                if ([string]$State.inputs.$key -notmatch '^[0-9a-f]{64}$') {
                    throw "run-state init adapter pin is invalid: $key"
                }
            }
        }
    }
    else {
        Assert-ExactJsonProperties -Value $State.inputs -Names $inputsV2 -Label 'run-state inputs'
    }
    if ([string]$State.inputs.checkpoint_helper_source_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'run-state checkpoint helper source SHA is invalid'
    }
    foreach ($key in @('dataset_sha256', 'model_weight_sha256', 'trainer_source_sha256')) {
        if ([string]$State.inputs.$key -notmatch '^[0-9a-f]{64}$' -or
            [string]$manifest.pins.$key -ne [string]$State.inputs.$key) {
            throw "checkpoint pin differs from run-state input: $key"
        }
    }
    # The exact runner has already proved Python canonical JSON.  Bind its pins
    # receipt without reserializing floats in PowerShell: canonical top-level
    # ordering gives us the exact raw pins value bytes from the manifest itself.
    $manifestPrefix = '{"generation":"' + $generation +
        '","payload":{"bytes":' + ([string][int64]$manifest.payload.bytes) +
        ',"name":"state.pt","sha256":"' + [string]$manifest.payload.sha256 +
        '"},"pins":'
    $manifestSuffix = ',"run_id":"' + [string]$State.run_id +
        '","schema_version":1}' + "`n"
    if (-not $manifestText.StartsWith($manifestPrefix, [StringComparison]::Ordinal) -or
        -not $manifestText.EndsWith($manifestSuffix, [StringComparison]::Ordinal) -or
        $manifestText.Length -le ($manifestPrefix.Length + $manifestSuffix.Length)) {
        throw 'checkpoint manifest does not match the authoritative canonical layout'
    }
    $pinsText = $manifestText.Substring(
        $manifestPrefix.Length,
        $manifestText.Length - $manifestPrefix.Length - $manifestSuffix.Length)
    if (-not $pinsText.StartsWith('{', [StringComparison]::Ordinal) -or
        -not $pinsText.EndsWith('}', [StringComparison]::Ordinal)) {
        throw 'checkpoint canonical pins value is invalid'
    }
    $pinsBytes = [Text.UTF8Encoding]::new($false).GetBytes($pinsText + "`n")
    if ((Get-BytesSha256 $pinsBytes) -ne [string]$verification.canonical_pins_sha256) {
        throw 'checkpoint canonical pins SHA differs from the authoritative receipt'
    }
    $payloadPath = Join-Path $generationDir 'state.pt'
    if (-not (Test-Path -LiteralPath $payloadPath -PathType Leaf) -or
        ((Get-Item -LiteralPath $payloadPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'checkpoint payload is missing'
    }
    $payloadSnapshot = Read-AuthoritativeFileSnapshot $payloadPath 'checkpoint payload'
    $payloadBytes = [byte[]]$payloadSnapshot.Bytes
    $payloadHash = Get-BytesSha256 $payloadBytes
    if ([int64]$manifest.payload.bytes -ne $payloadBytes.LongLength -or
        [int64]$verification.checkpoint_payload_bytes -ne $payloadBytes.LongLength -or
        [string]$manifest.payload.sha256 -ne $payloadHash -or
        [string]$verification.checkpoint_payload_sha256 -ne $payloadHash) {
        throw 'checkpoint payload integrity verification failed'
    }
    if ([int]$State.progress.pending_microbatches -ne 0) {
        throw 'checkpoint is not at a safe optimizer boundary'
    }
    Assert-VerifiedCheckpointTransaction -State $State -Generation $generation `
        -ManifestHash $manifestHash -PayloadHash $payloadHash -PinsHash (Get-BytesSha256 $pinsBytes)
}

function Assert-VerifiedCheckpointTransaction {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$Generation,
        [Parameter(Mandatory = $true)][string]$ManifestHash,
        [Parameter(Mandatory = $true)][string]$PayloadHash,
        [Parameter(Mandatory = $true)][string]$PinsHash
    )

    $checkpointRoot = Join-Path $resolvedRunDir 'checkpoints'
    $indexPath = Join-Path $checkpointRoot 'checkpoint-index.json'
    $indexReceipt = Read-CanonicalAuthorityJson $indexPath 'current checkpoint index'
    $index = $indexReceipt.value
    Assert-ExactJsonProperties -Value $index -Names @(
        'schema_version', 'run_id', 'latest', 'previous', 'previous_index_sha256') `
        -Label 'checkpoint transaction index'
    if ([string]$index.schema_version -ne 'airi.behavior-checkpoint-index.v2' -or
        [string]$index.run_id -ne [string]$State.run_id -or $null -eq $index.latest -or
        ([string]$index.previous_index_sha256 -ne '' -and
            [string]$index.previous_index_sha256 -notmatch '^[0-9a-f]{64}$')) {
        throw 'checkpoint transaction index schema/identity is invalid'
    }
    $referenceProperties = @('relative_path', 'manifest_sha256', 'event_relative_path', 'event_sha256')
    foreach ($referenceLabel in @('latest', 'previous')) {
        $reference = $index.$referenceLabel
        if ($null -eq $reference) { continue }
        Assert-ExactJsonProperties -Value $reference -Names $referenceProperties `
            -Label "checkpoint transaction $referenceLabel reference"
        if ([string]$reference.relative_path -notmatch '^checkpoint-[0-9]{8}$' -or
            [string]$reference.event_relative_path -ne "checkpoint-events/$($reference.relative_path).json" -or
            [string]$reference.manifest_sha256 -notmatch '^[0-9a-f]{64}$' -or
            [string]$reference.event_sha256 -notmatch '^[0-9a-f]{64}$') {
            throw 'checkpoint transaction reference is invalid'
        }
    }
    if ([string]$index.latest.relative_path -ne $Generation -or
        [string]$index.latest.manifest_sha256 -ne $ManifestHash) {
        throw 'checkpoint transaction latest reference differs from the pause checkpoint'
    }

    $eventPath = Join-Path $resolvedRunDir ([string]$index.latest.event_relative_path).Replace('/', '\')
    $eventReceipt = Read-CanonicalAuthorityJson $eventPath 'latest checkpoint event'
    if ((Get-BytesSha256 $eventReceipt.bytes) -ne [string]$index.latest.event_sha256) {
        throw 'latest checkpoint event SHA differs from the transaction index'
    }
    $event = $eventReceipt.value
    Assert-ExactJsonProperties -Value $event -Names @(
        'schema_version', 'run_id', 'generation', 'reason', 'microsteps_completed',
        'optimizer_steps', 'pending_microbatches', 'training_elapsed_ns',
        'checkpoint_payload_progress', 'checkpoint_manifest_sha256',
        'checkpoint_payload_sha256', 'pins_sha256', 'previous_event_sha256',
        'previous_index_sha256', 'publish_started_at_utc', 'checkpoint_durable_at_utc',
        'publish_elapsed_ns') -Label 'latest checkpoint event'
    Assert-ExactJsonProperties -Value $event.checkpoint_payload_progress -Names @(
        'microsteps_completed', 'optimizer_steps', 'pending_microbatches') `
        -Label 'latest checkpoint event payload progress'
    foreach ($counter in @('microsteps_completed', 'optimizer_steps', 'training_elapsed_ns', 'publish_elapsed_ns')) {
        if ($event.$counter -isnot [ValueType] -or [int64]$event.$counter -lt 0) {
            throw "latest checkpoint event counter is invalid: $counter"
        }
    }
    if ([string]$event.schema_version -ne 'airi.behavior-checkpoint-event.v2' -or
        [string]$event.run_id -ne [string]$State.run_id -or
        [string]$event.generation -ne $Generation -or
        [string]$event.reason -notin @('interval', 'safe-pause', 'epoch-tail', 'epoch-complete') -or
        [int64]$event.pending_microbatches -ne 0 -or
        [int64]$event.optimizer_steps -gt [int64]$event.microsteps_completed -or
        [string]$event.checkpoint_manifest_sha256 -ne $ManifestHash -or
        [string]$event.checkpoint_payload_sha256 -ne $PayloadHash -or
        [string]$event.pins_sha256 -ne $PinsHash -or
        [string]$event.previous_index_sha256 -ne [string]$index.previous_index_sha256 -or
        [string]::IsNullOrWhiteSpace([string]$event.publish_started_at_utc) -or
        [string]::IsNullOrWhiteSpace([string]$event.checkpoint_durable_at_utc) -or
        [int64]$event.checkpoint_payload_progress.microsteps_completed -ne [int64]$event.microsteps_completed -or
        [int64]$event.checkpoint_payload_progress.optimizer_steps -ne [int64]$event.optimizer_steps -or
        [int64]$event.checkpoint_payload_progress.pending_microbatches -ne 0 -or
        [int64]$State.progress.microsteps_completed -ne [int64]$event.microsteps_completed -or
        [int64]$State.progress.optimizer_steps -ne [int64]$event.optimizer_steps) {
        throw 'latest checkpoint event does not bind the authoritative pause checkpoint/progress'
    }
    foreach ($predecessor in @('previous_event_sha256', 'previous_index_sha256')) {
        if ($null -ne $event.$predecessor -and [string]$event.$predecessor -notmatch '^[0-9a-f]{64}$') {
            throw "latest checkpoint event predecessor is invalid: $predecessor"
        }
    }
    $previousIndexPath = Join-Path $checkpointRoot 'checkpoint-index.prev.json'
    if ($null -eq $index.previous_index_sha256) {
        if ($null -ne $index.previous -or $null -ne $event.previous_event_sha256 -or
            (Test-Path -LiteralPath $previousIndexPath)) {
            throw 'initial checkpoint transaction has an unexpected predecessor'
        }
    }
    else {
        if ($null -eq $index.previous -or $null -eq $event.previous_event_sha256 -or
            -not (Test-Path -LiteralPath $previousIndexPath -PathType Leaf)) {
            throw 'checkpoint transaction predecessor evidence is incomplete'
        }
        $previousIndexReceipt = Read-CanonicalAuthorityJson $previousIndexPath 'previous checkpoint index'
        if ((Get-BytesSha256 $previousIndexReceipt.bytes) -ne [string]$index.previous_index_sha256) {
            throw 'checkpoint predecessor index SHA differs from the current index'
        }
        $previousIndex = $previousIndexReceipt.value
        Assert-ExactJsonProperties -Value $previousIndex -Names @(
            'schema_version', 'run_id', 'latest', 'previous', 'previous_index_sha256') `
            -Label 'previous checkpoint transaction index'
        if ([string]$previousIndex.schema_version -ne 'airi.behavior-checkpoint-index.v2' -or
            [string]$previousIndex.run_id -ne [string]$State.run_id -or
            (Get-CanonicalJsonValue $previousIndex.latest) -ne (Get-CanonicalJsonValue $index.previous) -or
            [string]$event.previous_event_sha256 -ne [string]$index.previous.event_sha256) {
            throw 'checkpoint transaction predecessor chain is broken'
        }
    }
}

function Assert-PauseReceiptIdentity {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$Request,
        [Parameter(Mandatory = $true)]$Ack
    )

    Assert-ExactJsonProperties -Value $Request -Names @(
        'schema_version', 'run_id', 'request_id') -Label 'pause request'
    Assert-ExactJsonProperties -Value $Ack -Names @(
        'schema_version', 'run_id', 'request_id', 'checkpoint_manifest_sha256',
        'checkpoint_relative_path', 'acknowledged_at_utc', 'safe_to_power_off') -Label 'pause ack'
    if ([string]$Request.schema_version -ne 'airi.behavior-pause-request.v1' -or
        [string]$Ack.schema_version -ne 'airi.behavior-pause-ack.v1' -or
        [string]$Request.run_id -ne [string]$State.run_id -or
        [string]$Ack.run_id -ne [string]$State.run_id -or
        [string]::IsNullOrWhiteSpace([string]$Request.request_id) -or
        [string]$Ack.request_id -ne [string]$Request.request_id -or
        [string]$Ack.checkpoint_manifest_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $Ack.safe_to_power_off -ne $true) {
        throw 'safe-pause request and ack identity is invalid'
    }
}

function Get-SafeArtifactFiles {
    param([Parameter(Mandatory = $true)][string]$Root)

    $stack = [Collections.Generic.Stack[string]]::new()
    $stack.Push($Root)
    while ($stack.Count -gt 0) {
        $directory = $stack.Pop()
        foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'completed artifact cannot contain a reparse point'
            }
            if ($item.PSIsContainer) {
                $stack.Push($item.FullName)
            }
            else {
                Write-Output $item
            }
        }
    }
}

function Assert-VerifiedArtifactReceipt {
    param(
        [AllowNull()]$Receipt,
        [Parameter(Mandatory = $true)][bool]$Required
    )

    if ($null -eq $Receipt) {
        if ($Required) {
            throw 'required completed artifact receipt is missing'
        }
        return
    }
    if ([string]$Receipt.kind -eq 'file') {
        Assert-ExactJsonProperties -Value $Receipt -Names @(
            'path', 'kind', 'size', 'sha256') -Label 'file artifact receipt'
    }
    elseif ([string]$Receipt.kind -eq 'directory') {
        Assert-ExactJsonProperties -Value $Receipt -Names @(
            'path', 'kind', 'files', 'manifest_sha256') -Label 'directory artifact receipt'
    }
    else {
        throw 'completed artifact receipt kind is invalid'
    }
    $path = [IO.Path]::GetFullPath([string]$Receipt.path)
    if ([string]$Receipt.kind -eq 'file') {
        $snapshot = Read-AuthoritativeFileSnapshot $path 'completed file artifact'
        if ([int64]$Receipt.size -ne [int64]$snapshot.Length -or
            [string]$Receipt.sha256 -ne (Get-BytesSha256 $snapshot.Bytes)) {
            throw 'completed file artifact receipt no longer matches disk'
        }
        return
    }
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw 'completed directory artifact is missing'
    }
    $rootItem = Get-Item -LiteralPath $path -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'completed directory artifact cannot be a reparse point'
    }
    $expected = @{}
    $canonicalRows = @()
    foreach ($row in @($Receipt.files)) {
        Assert-ExactJsonProperties -Value $row -Names @(
            'path', 'size', 'sha256') -Label 'directory artifact row'
        $relative = [string]$row.path
        if ([string]::IsNullOrWhiteSpace($relative) -or
            [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or
            $expected.ContainsKey($relative) -or [string]$row.sha256 -notmatch '^[0-9a-f]{64}$') {
            throw 'directory artifact row is invalid'
        }
        $expected[$relative] = $row
        $canonicalRows += [ordered]@{
            path = $relative
            sha256 = [string]$row.sha256
            size = [int64]$row.size
        }
    }
    $actualFiles = @(Get-SafeArtifactFiles $path)
    if ($actualFiles.Count -ne $expected.Count) {
        throw 'completed directory artifact inventory changed'
    }
    foreach ($item in $actualFiles) {
        $relative = $item.FullName.Substring($path.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
        if (-not $expected.ContainsKey($relative)) {
            throw 'completed directory artifact contains an unexpected file'
        }
        $row = $expected[$relative]
        $snapshot = Read-AuthoritativeFileSnapshot $item.FullName 'completed directory artifact file'
        if ([int64]$row.size -ne [int64]$snapshot.Length -or
            [string]$row.sha256 -ne (Get-BytesSha256 $snapshot.Bytes)) {
            throw 'completed directory artifact file receipt no longer matches disk'
        }
    }
    $sortedRows = @($canonicalRows | Sort-Object { [string]$_.path })
    $canonicalJson = ConvertTo-Json -InputObject $sortedRows -Compress -Depth 5
    if ((Get-Utf8Sha256 ($canonicalJson + "`n")) -ne [string]$Receipt.manifest_sha256) {
        throw 'completed directory artifact manifest receipt is invalid'
    }
}

function Assert-VerifiedFinalEvidenceRoot {
    param([Parameter(Mandatory = $true)]$State)

    $receipt = $State.terminal.final_evidence_root
    Assert-ExactJsonProperties -Value $receipt -Names @(
        'relative_path', 'sha256', 'state_projection_sha256') -Label 'final evidence root receipt'
    if ([string]$receipt.relative_path -ne 'final-evidence-root.json' -or
        [string]$receipt.sha256 -notmatch '^[0-9a-f]{64}$' -or
        [string]$receipt.state_projection_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'final evidence root receipt is invalid'
    }
    $rootPath = Join-Path $resolvedRunDir ([string]$receipt.relative_path)
    $finalReceipt = Read-CanonicalAuthorityJson $rootPath 'final evidence root'
    if ((Get-BytesSha256 $finalReceipt.bytes) -ne [string]$receipt.sha256) {
        throw 'final evidence root SHA differs from terminal receipt'
    }
    $finalRoot = $finalReceipt.value
    Assert-ExactJsonProperties -Value $finalRoot -Names @(
        'schema_version', 'run_id', 'producer_evidence_root_sha256',
        'checkpoint_index_sha256', 'latest_event_sha256',
        'completed_progress_sha256', 'state_projection', 'state_projection_sha256') `
        -Label 'final evidence root'
    if ([string]$finalRoot.schema_version -ne 'airi.behavior-final-evidence-root.v1' -or
        [string]$finalRoot.run_id -ne [string]$State.run_id -or
        [string]$finalRoot.state_projection_sha256 -ne [string]$receipt.state_projection_sha256) {
        throw 'final evidence root identity differs from complete terminal'
    }
    $projection = $finalRoot.state_projection
    Assert-ExactJsonProperties -Value $projection -Names @(
        'run_id', 'revision', 'status', 'inputs', 'outputs', 'progress_sha256',
        'producer_evidence_root_sha256') -Label 'final evidence state projection'
    if ([string]$projection.run_id -ne [string]$State.run_id -or
        [int64]$projection.revision -ne [int64]$State.revision -or
        [string]$projection.status -ne 'complete' -or
        (Get-Utf8Sha256 ((Get-CanonicalJsonValue $projection) + "`n")) -ne
            [string]$finalRoot.state_projection_sha256 -or
        (Get-CanonicalJsonValue $projection.inputs) -ne (Get-CanonicalJsonValue $State.inputs) -or
        (Get-CanonicalJsonValue $projection.outputs) -ne (Get-CanonicalJsonValue $State.outputs)) {
        throw 'final evidence root state projection differs from terminal state'
    }
    $producerReceipt = Read-CanonicalAuthorityJson (Join-Path $resolvedRunDir 'producer-evidence-root.json') `
        'producer evidence root'
    $producer = $producerReceipt.value
    Assert-ExactJsonProperties -Value $producer -Names @(
        'schema_version', 'run_id', 'checkpoint_index_sha256', 'latest_checkpoint',
        'adapter_artifact_manifest_sha256', 'report_sha256', 'progress') `
        -Label 'producer evidence root'
    if ([string]$producer.schema_version -ne 'airi.behavior-producer-evidence-root.v1' -or
        [string]$producer.run_id -ne [string]$State.run_id -or
        (Get-BytesSha256 $producerReceipt.bytes) -ne [string]$finalRoot.producer_evidence_root_sha256 -or
        [string]$projection.producer_evidence_root_sha256 -ne [string]$finalRoot.producer_evidence_root_sha256) {
        throw 'producer evidence root differs from the final evidence cut'
    }
    $indexReceipt = Read-CanonicalAuthorityJson (Join-Path $resolvedRunDir 'checkpoints\checkpoint-index.json') `
        'completion checkpoint index'
    $index = $indexReceipt.value
    Assert-ExactJsonProperties -Value $index -Names @(
        'schema_version', 'run_id', 'latest', 'previous', 'previous_index_sha256') `
        -Label 'completion checkpoint index'
    if ([string]$index.schema_version -ne 'airi.behavior-checkpoint-index.v2' -or
        [string]$index.run_id -ne [string]$State.run_id -or $null -eq $index.latest -or
        (Get-BytesSha256 $indexReceipt.bytes) -ne [string]$finalRoot.checkpoint_index_sha256 -or
        (Get-CanonicalJsonValue $producer.latest_checkpoint) -ne (Get-CanonicalJsonValue $index.latest)) {
        throw 'final/producer evidence root checkpoint index binding is invalid'
    }
    Assert-ExactJsonProperties -Value $index.latest -Names @(
        'relative_path', 'manifest_sha256', 'event_relative_path', 'event_sha256') `
        -Label 'completion latest checkpoint reference'
    $eventReceipt = Read-CanonicalAuthorityJson (Join-Path $resolvedRunDir (
            [string]$index.latest.event_relative_path).Replace('/', '\')) 'completion latest checkpoint event'
    if ((Get-BytesSha256 $eventReceipt.bytes) -ne [string]$index.latest.event_sha256 -or
        [string]$finalRoot.latest_event_sha256 -ne [string]$index.latest.event_sha256) {
        throw 'final evidence root latest event binding is invalid'
    }
    $progressReceipt = Read-CanonicalAuthorityJson (Join-Path $resolvedRunDir 'progress.json') 'completed progress'
    $progress = $progressReceipt.value
    Assert-ExactJsonProperties -Value $progress -Names @(
        'schema_version', 'run_id', 'status', 'epoch', 'next_batch_index',
        'microsteps_completed', 'optimizer_steps', 'pending_microbatches',
        'checkpoint', 'updated_at_utc', 'training_elapsed_ns') -Label 'completed progress'
    Assert-ExactJsonProperties -Value $producer.progress -Names @(
        'microsteps_completed', 'optimizer_steps', 'pending_microbatches', 'training_elapsed_ns') `
        -Label 'producer evidence progress'
    $adapterArtifactManifests = @($State.outputs.adapter.files | Where-Object {
            [string]$_.path -eq 'artifact-manifest.json'
        })
    if ([string]$progress.schema_version -ne 'airi.behavior-training-progress.v2' -or
        [string]$progress.run_id -ne [string]$State.run_id -or [string]$progress.status -ne 'completed' -or
        [int64]$progress.pending_microbatches -ne 0 -or
        (Get-BytesSha256 $progressReceipt.bytes) -ne [string]$finalRoot.completed_progress_sha256 -or
        [string]$projection.progress_sha256 -ne [string]$finalRoot.completed_progress_sha256 -or
        (Get-CanonicalJsonValue $producer.progress) -ne (Get-CanonicalJsonValue ([ordered]@{
                    microsteps_completed = $progress.microsteps_completed
                    optimizer_steps = $progress.optimizer_steps
                    pending_microbatches = $progress.pending_microbatches
                    training_elapsed_ns = $progress.training_elapsed_ns
                })) -or
        $adapterArtifactManifests.Count -ne 1 -or
        [string]$producer.adapter_artifact_manifest_sha256 -ne
            [string]$adapterArtifactManifests[0].sha256 -or
        [string]$producer.report_sha256 -ne [string]$State.outputs.report.sha256) {
        throw 'completion progress/artifact receipts do not match the final evidence root'
    }
}

function Assert-VerifiedCompletion {
    param([Parameter(Mandatory = $true)]$State)

    if ([string]$State.status -ne 'complete') {
        throw 'run is not complete'
    }
    Assert-ExactJsonProperties -Value $State.terminal -Names @(
        'exit_code', 'reason', 'at_utc', 'final_evidence_root') -Label 'complete terminal receipt'
    Assert-ExactJsonProperties -Value $State.outputs -Names @(
        'adapter', 'report') -Label 'complete outputs receipt'
    if ([int]$State.terminal.exit_code -ne 0 -or
        [string]$State.terminal.reason -ne 'trainer-complete') {
        throw 'complete terminal receipt is invalid'
    }
    Assert-VerifiedArtifactReceipt $State.outputs.adapter $true
    Assert-VerifiedArtifactReceipt $State.outputs.report $true
    Assert-VerifiedFinalEvidenceRoot $State
}

function Get-TerminalPredecessor {
    param([Parameter(Mandatory = $true)]$TerminalState)

    $previous = Read-ValidRunStateCandidate $previousStatePath
    $anchor = Read-RunStateAnchor $resolvedRunDir
    if ($null -eq $previous -or
        -not (Test-AnchorAuthorizedRunState $previous $anchor 'previous') -or
        [string]$previous.run_id -ne [string]$TerminalState.run_id -or
        [int64]$previous.revision -ge [int64]$TerminalState.revision) {
        throw 'Terminal run-state has no earlier authoritative identity receipt'
    }
    Assert-SameProcessRecord $previous.runner $TerminalState.runner 'Runner'
    Assert-SameProcessRecord $previous.trainer $TerminalState.trainer 'Trainer'
    return $previous
}

function Wait-RecordedRunnerExit {
    param(
        [Parameter(Mandatory = $true)]$ExpectedState,
        [Parameter(Mandatory = $true)][DateTime]$Deadline
    )

    do {
        Assert-DeadlineNotExpired $Deadline 'recorded runner exit'
        $state = Read-RunState $statePath $previousStatePath
        if ([string]$state.run_id -ne [string]$ExpectedState.run_id) {
            throw 'Run identity changed while waiting for recorded runner exit'
        }
        Assert-SameProcessRecord $ExpectedState.runner $state.runner 'Runner'
        Assert-SameProcessRecord $ExpectedState.trainer $state.trainer 'Trainer'
        $runnerExitStatus = Get-RecordedProcessExitStatus -Record ($ExpectedState.runner)
        switch ($runnerExitStatus) {
            'exited' { return $state }
            'replaced' { throw 'Recorded durable runner PID is live with a different process identity' }
        }
        if (-not (Start-RemainingDeadlineSleep $Deadline $PollSeconds)) { break }
    } while ($true)
    throw 'Recorded durable runner did not exit before the safe power-off deadline'
}

function Wait-RecordedTrainerExit {
    param(
        [AllowNull()]$Record,
        [Parameter(Mandatory = $true)][DateTime]$Deadline
    )

    if ($null -eq $Record) {
        throw 'Recorded trainer identity is missing'
    }
    do {
        Assert-DeadlineNotExpired $Deadline 'recorded trainer exit'
        switch (Get-RecordedProcessExitStatus -Record $Record) {
            'exited' { return }
            'replaced' { throw 'Recorded trainer PID is live with a different process identity' }
        }
        if (-not (Start-RemainingDeadlineSleep $Deadline $PollSeconds)) { break }
    } while ($true)
    throw 'Recorded trainer did not exit before the safe power-off deadline'
}

function Assert-VerifiedSafePause {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$Request,
        [Parameter(Mandatory = $true)]$Ack
    )

    if ([string]$State.status -ne 'paused-safe' -or $null -eq $State.terminal -or
        [int]$State.terminal.exit_code -ne 75 -or
        [string]$State.terminal.reason -ne 'safe-optimizer-boundary') {
        throw 'paused-safe state has an invalid terminal receipt'
    }
    Assert-ExactJsonProperties -Value $State.terminal -Names @(
        'exit_code', 'reason', 'at_utc', 'checkpoint_verification') -Label 'paused-safe terminal receipt'
    if ($null -eq $State.trainer) {
        throw 'paused-safe state is missing its recorded trainer identity'
    }
    Assert-PauseReceiptIdentity $State $Request $Ack
    Assert-VerifiedCheckpoint $State $Ack
}

function Wait-VerifiedCompletionPowerOff {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][DateTime]$Deadline
    )

    do {
        Assert-DeadlineNotExpired $Deadline 'completed artifact verification'
        Assert-VerifiedCompletion $State
        $state = Wait-RecordedRunnerExit $State $Deadline
        Assert-DeadlineNotExpired $Deadline 'completed artifact verification'
        Assert-VerifiedCompletion $state
        if ([string]$state.status -ne 'complete') {
            throw "Training changed to '$($state.status)' while waiting for completion power-off"
        }
        Wait-RecordedTrainerExit $State.trainer $Deadline
        Assert-DeadlineNotExpired $Deadline 'SAFE_TO_POWER_OFF emission'
        $finalState = Read-RunState $statePath $previousStatePath
        Assert-TerminalStateUnchanged $State $finalState
        Assert-VerifiedCompletion $finalState
        if ((Get-RecordedProcessExitStatus -Record ($State.runner)) -eq 'exited' -and
            (Get-RecordedProcessExitStatus -Record ($State.trainer)) -eq 'exited') {
            [pscustomobject]@{
                status = 'complete'
                run_id = [string]$state.run_id
                optimizer_steps = [int]$state.progress.optimizer_steps
                microsteps_completed = [int]$state.progress.microsteps_completed
            }
            Invoke-TestOnlyFinalGateDelay
            $postDelayState = Read-RunState $statePath $previousStatePath
            Assert-TerminalStateUnchanged $State $postDelayState
            Assert-VerifiedCompletion $postDelayState
            if ((Get-RecordedProcessExitStatus -Record ($State.runner)) -ne 'exited' -or
                (Get-RecordedProcessExitStatus -Record ($State.trainer)) -ne 'exited') {
                throw 'Recorded processes changed during final completion gate delay'
            }
            Assert-DeadlineNotExpired $Deadline 'SAFE_TO_POWER_OFF emission'
            Write-Output 'SAFE_TO_POWER_OFF'
            return
        }
        $State = Read-RunState $statePath $previousStatePath
    } while ([string]$State.status -eq 'complete')
    throw 'Completed artifacts are verified but trainer/runner did not exit in time'
}

Assert-DeadlineNotExpired $deadline 'run discovery'
$initial = Read-RunState $statePath $previousStatePath
if ([string]$initial.status -eq 'complete') {
    [void](Get-TerminalPredecessor $initial)
    Wait-VerifiedCompletionPowerOff $initial $deadline
    return
}
if ([string]$initial.status -eq 'paused-safe' -and
    [int]$initial.terminal.exit_code -eq 75 -and
    [string]$initial.terminal.reason -eq 'safe-optimizer-boundary') {
    throw 'Already-paused terminal cannot authorize power-off without runner and trainer identities observed live by this invocation'
}

if ([string]$initial.status -notin @('starting', 'running', 'pause-requested', 'checkpointing')) {
    throw "Run status '$($initial.status)' is not actively trainable"
}
$expectedRunner = $initial.runner
$identityDeadline = [DateTime]::UtcNow.AddSeconds([Math]::Min(30, $TimeoutSeconds))
while (-not (Test-ExactProcessRecord $initial.trainer)) {
    Assert-SameProcessRecord $expectedRunner $initial.runner 'Runner'
    if ([string]$initial.status -notin @('starting', 'running', 'pause-requested', 'checkpointing')) {
        throw "Training became '$($initial.status)' before trainer identity was ready"
    }
    $identityDeadline = if ($identityDeadline -lt $deadline) { $identityDeadline } else { $deadline }
    if ([DateTime]::UtcNow -ge $identityDeadline) {
        throw 'Recorded trainer PID/creation/executable/command identity did not become live; refusing blind pause'
    }
    [void](Start-RemainingDeadlineSleep $identityDeadline 0.2)
    $initial = Read-RunState $statePath $previousStatePath
}
Assert-SameProcessRecord $expectedRunner $initial.runner 'Runner'

$controlDir = Join-Path $resolvedRunDir 'control'
[IO.Directory]::CreateDirectory($controlDir) | Out-Null
$requestPath = Join-Path $controlDir 'pause.request.json'
if (Test-Path -LiteralPath $requestPath) {
    $request = Get-Content -LiteralPath $requestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ([string]$request.run_id -ne [string]$initial.run_id -or
        [string]$request.schema_version -ne 'airi.behavior-pause-request.v1' -or
        [string]::IsNullOrWhiteSpace([string]$request.request_id)) {
        throw 'Existing pause request does not match this run'
    }
}
else {
    $request = [ordered]@{
        schema_version = 'airi.behavior-pause-request.v1'
        run_id = [string]$initial.run_id
        request_id = [Guid]::NewGuid().ToString('N')
    }
    $requestJson = ($request | ConvertTo-Json -Compress) + "`n"
    Write-AtomicUtf8NoBom $requestPath $requestJson
}

do {
    if (-not (Start-RemainingDeadlineSleep $deadline $PollSeconds)) { break }
    try {
        $state = Read-RunState $statePath $previousStatePath
    }
    catch {
        continue
    }
    if ([string]$state.run_id -ne [string]$initial.run_id) {
        throw 'Run identity changed while waiting for safe pause'
    }
    Assert-SameProcessRecord $expectedRunner $state.runner 'Runner'
    if ([string]$state.status -eq 'paused-safe' -and $null -ne $state.terminal) {
        if ([int]$state.terminal.exit_code -ne 75 -or
            [string]$state.terminal.reason -ne 'safe-optimizer-boundary') {
            throw 'paused-safe state has an invalid terminal receipt'
        }
        $ackPath = Join-Path $controlDir 'pause.ack.json'
        if (-not (Test-Path -LiteralPath $ackPath -PathType Leaf)) {
            throw 'Runner reported paused-safe without pause.ack.json'
        }
        $ack = Get-Content -LiteralPath $ackPath -Raw -Encoding utf8 | ConvertFrom-Json
        Assert-VerifiedSafePause $state $request $ack
        Assert-SameProcessRecord $initial.trainer $state.trainer 'Trainer'
        if (Test-ExactProcessRecord $initial.trainer) {
            continue
        }
        $pausedState = Wait-RecordedRunnerExit $initial $deadline
        $ack = Get-Content -LiteralPath $ackPath -Raw -Encoding utf8 | ConvertFrom-Json
        Assert-VerifiedSafePause $pausedState $request $ack
        Wait-RecordedTrainerExit $initial.trainer $deadline
        Assert-DeadlineNotExpired $deadline 'SAFE_TO_POWER_OFF emission'
        $finalPausedState = Read-RunState $statePath $previousStatePath
        Assert-TerminalStateUnchanged $pausedState $finalPausedState
        Assert-VerifiedSafePause $finalPausedState $request $ack
        if ((Get-RecordedProcessExitStatus -Record ($initial.runner)) -ne 'exited' -or
            (Get-RecordedProcessExitStatus -Record ($initial.trainer)) -ne 'exited') {
            throw 'Recorded processes are not both exited at SAFE_TO_POWER_OFF emission'
        }
        [pscustomobject]@{
            status = 'paused-safe'
            run_id = [string]$pausedState.run_id
            optimizer_steps = [int]$pausedState.progress.optimizer_steps
            microsteps_completed = [int]$pausedState.progress.microsteps_completed
            checkpoint = [string]$pausedState.checkpoint.relative_path
            checkpoint_manifest_sha256 = [string]$pausedState.checkpoint.manifest_sha256
        }
        Invoke-TestOnlyFinalGateDelay
        $postDelayState = Read-RunState $statePath $previousStatePath
        Assert-TerminalStateUnchanged $pausedState $postDelayState
        Assert-VerifiedSafePause $postDelayState $request $ack
        if ((Get-RecordedProcessExitStatus -Record ($initial.runner)) -ne 'exited' -or
            (Get-RecordedProcessExitStatus -Record ($initial.trainer)) -ne 'exited') {
            throw 'Recorded processes changed during final paused-safe gate delay'
        }
        Assert-DeadlineNotExpired $deadline 'SAFE_TO_POWER_OFF emission'
        Write-Output 'SAFE_TO_POWER_OFF'
        return
    }
    if ([string]$state.status -eq 'complete') {
        Assert-SameProcessRecord $expectedRunner $state.runner 'Runner'
        Assert-SameProcessRecord $initial.trainer $state.trainer 'Trainer'
        Wait-VerifiedCompletionPowerOff $state $deadline
        return
    }
    if ([string]$state.status -in @('failed', 'interrupted')) {
        throw "Training became '$($state.status)' before a verified safe-pause receipt"
    }
} while ([DateTime]::UtcNow -lt $deadline)

throw 'Timed out before SAFE_TO_POWER_OFF; pause request remains durable for the trainer'
