[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunDir,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [string]$PythonPath,

    [string]$TrainerPath = (Join-Path $PSScriptRoot 'ollama-proxy\training\train_airi_behavior_lora.py'),

    [string]$WorkingDirectory = $PSScriptRoot,

    [Parameter(Mandatory = $true)]
    [string]$InputManifestPath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$InputManifestSha256,

    [ValidateRange(1, 1000000)]
    [int]$CheckpointEveryOptimizerSteps = 5,

    [ValidateRange(1, 15)]
    [int]$HeartbeatSeconds = 10,

    [switch]$ResumeInterrupted,

    [switch]$PauseAtFirstOptimizerBoundary,

    [Parameter(Mandatory = $true)]
    [string[]]$TrainerArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

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

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    # Hash the same immutable, no-follow snapshot that authorizes the launch.
    # Do not hash a second path-based read after validation has completed.
    $snapshot = Read-LauncherAuthoritySnapshot $Path 'SHA-256 authority input'
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($hash.ComputeHash($snapshot.Bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hash.Dispose()
    }
}

function Read-LauncherAuthoritySnapshot {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Label)

    if (-not ('AiriLauncherReadSnapshot' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public sealed class AiriLauncherSnapshotValue { public byte[] Bytes; public long Length; }
public static class AiriLauncherReadSnapshot {
 const uint R=0x80000000,S=1,O=3,RP=0x00200000,RE=0x400,D=0x10; static readonly IntPtr I=new IntPtr(-1);
 [StructLayout(LayoutKind.Sequential)] struct F { public uint A; public System.Runtime.InteropServices.ComTypes.FILETIME C,LA,LW; public uint V,SH,SL,N,IH,IL; }
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFileW(string p,uint a,uint s,IntPtr x,uint c,uint f,IntPtr t);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandle(IntPtr h,out F f);
 public static AiriLauncherSnapshotValue Read(string path) {
  IntPtr raw=CreateFileW(path,R,S,IntPtr.Zero,O,RP,IntPtr.Zero); if(raw==I) throw new IOException("CreateFileW failed: "+Marshal.GetLastWin32Error());
  using(var h=new SafeFileHandle(raw,true)) { F f; if(!GetFileInformationByHandle(h.DangerousGetHandle(),out f)) throw new IOException("GetFileInformationByHandle failed: "+Marshal.GetLastWin32Error()); if((f.A&(RE|D))!=0) throw new IOException("authority path is a reparse point or directory"); ulong n=((ulong)f.SH<<32)|f.SL; if(n>Int32.MaxValue) throw new IOException("authority file is too large"); byte[] b=new byte[(int)n]; using(var s=new FileStream(h,FileAccess.Read,4096,false)) { int o=0; while(o<b.Length){int k=s.Read(b,o,b.Length-o);if(k<=0)throw new EndOfStreamException();o+=k;} if(s.ReadByte()!=-1)throw new IOException("authority file length changed"); } return new AiriLauncherSnapshotValue{Bytes=b,Length=b.LongLength}; }
 }
}
'@
    }
    try { return [AiriLauncherReadSnapshot]::Read($Path) }
    catch { throw "$Label cannot be read through a no-follow authority handle: $($_.Exception.Message)" }
}

function Read-LauncherAuthorityJson {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Label)
    $snapshot = Read-LauncherAuthoritySnapshot $Path $Label
    try {
        return [pscustomobject]@{ value = ([Text.UTF8Encoding]::new($false,$true).GetString($snapshot.Bytes) | ConvertFrom-Json); bytes = $snapshot.Bytes }
    }
    catch { throw "$Label is not UTF-8 JSON: $($_.Exception.Message)" }
}

function Get-CanonicalStringArraySha256 {
    param([Parameter(Mandatory = $true)][string[]]$Values)

    # Python durable runner uses json.dumps(list, ensure_ascii=False,
    # sort_keys=True, separators=(',', ':')) plus one LF.  A string array has
    # no object keys, and Windows PowerShell's compressed JSON uses the same
    # escaping/separators for this closed scalar schema.
    $json = ConvertTo-Json -InputObject ([object[]]$Values) -Compress
    return Get-Utf8Sha256 ($json + "`n")
}

function Test-PathEntryExists {
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        [IO.File]::GetAttributes($Path) | Out-Null
        return $true
    }
    catch [IO.FileNotFoundException], [IO.DirectoryNotFoundException] {
        return $false
    }
    catch {
        throw "RunDir existence could not be verified: $Path"
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

function Test-RecordedProcessHasExited {
    param([AllowNull()]$Record)

    # A terminal receipt cannot be authoritative while its recorded PID is
    # still occupied.  Treat PID reuse conservatively too: a different live
    # process at that PID cannot prove that the recorded process exited.
    if ($null -eq $Record -or $null -eq $Record.pid -or [int64]$Record.pid -le 0) {
        return $false
    }
    return $null -eq (Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$Record.pid)" `
        -ErrorAction SilentlyContinue)
}

function Test-SameProcessRecord {
    param(
        [AllowNull()]$Expected,
        [AllowNull()]$Actual
    )

    if ($null -eq $Expected -or $null -eq $Actual) {
        return $false
    }
    foreach ($property in @(
            'pid', 'creation_time_utc', 'executable_path_sha256', 'command_line_sha256')) {
        if ([string]$Expected.$property -ne [string]$Actual.$property) {
            return $false
        }
    }
    return $true
}

function Test-StartedRunnerProvenance {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][int]$StartedProcessId,
        [Parameter(Mandatory = $true)][DateTime]$LaunchStartedUtc
    )

    if (-not (Test-ExactProcessRecord $Record)) {
        return $false
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$Record.pid)" -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.CreationDate.ToUniversalTime() -lt $LaunchStartedUtc) {
        return $false
    }
    $candidatePid = [int]$process.ProcessId
    for ($depth = 0; $depth -lt 16; $depth++) {
        if ($candidatePid -eq $StartedProcessId) {
            return $true
        }
        $parentPid = [int]$process.ParentProcessId
        if ($parentPid -le 0) {
            return $false
        }
        if ($parentPid -eq $StartedProcessId) {
            return $true
        }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $parentPid" -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            return $false
        }
        $candidatePid = [int]$process.ProcessId
    }
    return $false
}

function Test-ObservedTrainerProvenance {
    param(
        [Parameter(Mandatory = $true)]$TrainerRecord,
        [Parameter(Mandatory = $true)]$RunnerRecord
    )

    if (-not (Test-ExactProcessRecord $TrainerRecord)) {
        return $false
    }
    $trainer = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$TrainerRecord.pid)" -ErrorAction SilentlyContinue
    if ($null -eq $trainer -or [int]$trainer.ParentProcessId -ne [int]$RunnerRecord.pid) {
        return $false
    }
    return $trainer.CreationDate.ToUniversalTime() -ge [DateTime]::Parse(
        [string]$RunnerRecord.creation_time_utc).ToUniversalTime()
}

function Test-ArtifactReceipt {
    param(
        [AllowNull()]$Receipt,
        [switch]$Required
    )

    if ($null -eq $Receipt) {
        return -not $Required
    }
    if ([string]::IsNullOrWhiteSpace([string]$Receipt.path)) {
        return $false
    }
    try {
        $path = Resolve-RequiredLocalPath ([string]$Receipt.path) 'Terminal artifact receipt path'
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $snapshot = Read-LauncherAuthoritySnapshot $path 'terminal file artifact'
            $hash = [Security.Cryptography.SHA256]::Create()
            try {
                $sha256 = ([BitConverter]::ToString($hash.ComputeHash($snapshot.Bytes))).Replace('-', '').ToLowerInvariant()
            }
            finally { $hash.Dispose() }
            return (Test-ExactJsonProperties -Value $Receipt -Names @('path', 'kind', 'size', 'sha256')) -and
                [string]$Receipt.kind -eq 'file' -and
                [int64]$Receipt.size -eq [int64]$snapshot.Length -and
                [string]$Receipt.sha256 -eq $sha256
        }
        if (-not (Test-Path -LiteralPath $path -PathType Container) -or
            -not (Test-ExactJsonProperties -Value $Receipt -Names @('path', 'kind', 'files', 'manifest_sha256')) -or
            [string]$Receipt.kind -ne 'directory' -or $null -eq $Receipt.files) {
            return $false
        }
        foreach ($item in @(Get-ChildItem -LiteralPath $path -Directory -Recurse -Force)) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                return $false
            }
        }
        $actualFiles = @()
        foreach ($item in @(Get-ChildItem -LiteralPath $path -File -Recurse -Force | Sort-Object FullName)) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                return $false
            }
            $snapshot = Read-LauncherAuthoritySnapshot $item.FullName 'terminal directory artifact file'
            $hash = [Security.Cryptography.SHA256]::Create()
            try {
                $digest = ([BitConverter]::ToString($hash.ComputeHash($snapshot.Bytes))).Replace('-', '').ToLowerInvariant()
            }
            finally { $hash.Dispose() }
            $actualFiles += [ordered]@{
                path = $item.FullName.Substring($path.TrimEnd('\\').Length).TrimStart('\\').Replace('\\', '/')
                sha256 = $digest
                size = [int64]$snapshot.Length
            }
        }
        if ($Receipt.files.Count -ne $actualFiles.Count) {
            return $false
        }
        for ($index = 0; $index -lt $actualFiles.Count; $index++) {
            if (-not (Test-ExactJsonProperties -Value $Receipt.files[$index] -Names @('path', 'size', 'sha256')) -or
                [string]$Receipt.files[$index].path -ne [string]$actualFiles[$index].path -or
                [int64]$Receipt.files[$index].size -ne [int64]$actualFiles[$index].size -or
                [string]$Receipt.files[$index].sha256 -ne [string]$actualFiles[$index].sha256) {
                return $false
            }
        }
        $canonicalFiles = ConvertTo-Json -InputObject ([object[]]$actualFiles) -Compress
        return [string]$Receipt.manifest_sha256 -eq (Get-Utf8Sha256 ($canonicalFiles + "`n"))
    }
    catch {
        # Receipt paths are an authority boundary; any race or path failure is invalid.
        return $false
    }
}

function Test-VerifiedTerminalLaunchReceipt {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$RunDir,
        [AllowNull()]$ObservedRunner,
        [AllowNull()]$ObservedTrainer
    )

    # The launcher only trusts a terminal state that retains the exact runner
    # and trainer identities it observed while they were live.  An attacker
    # cannot replace those records with absent PIDs to manufacture an exit.
    if (-not (Test-SameProcessRecord $ObservedRunner $State.runner) -or
        -not (Test-SameProcessRecord $ObservedTrainer $State.trainer) -or
        -not (Test-RecordedProcessHasExited $State.runner) -or
        -not (Test-RecordedProcessHasExited $State.trainer)) {
        return $false
    }
    if ([string]$State.status -eq 'complete') {
        if (-not (Test-ExactJsonProperties -Value $State.terminal -Names @(
                    'exit_code', 'reason', 'at_utc', 'final_evidence_root')) -or
            [int]$State.terminal.exit_code -ne 0 -or
            [string]$State.terminal.reason -ne 'trainer-complete' -or
            -not (Test-ExactJsonProperties -Value $State.outputs -Names @('adapter', 'report')) -or
            -not (Test-ArtifactReceipt -Receipt $State.outputs.adapter -Required) -or
            -not (Test-ArtifactReceipt -Receipt $State.outputs.report -Required)) {
            return $false
        }
    }
    if ([string]$State.status -in @('complete', 'paused-safe')) {
        # The launcher owns launch/child provenance; the pause gateway owns
        # the deeper checkpoint/final-root snapshot verification.  Both are
        # required, so a terminal cannot be accepted by a structural shape.
        try {
            $pauseGateway = Join-Path $PSScriptRoot 'pause-airi-safely.ps1'
            $pauseReceipt = @(& $pauseGateway `
                -RunDir $RunDir `
                -TimeoutSeconds 5 `
                -PollSeconds 1)
            return $pauseReceipt -contains 'SAFE_TO_POWER_OFF'
        }
        catch {
            return $false
        }
    }
    return $false
}

function ConvertTo-WindowsCommandLineArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') {
        return $Value
    }
    $builder = [Text.StringBuilder]::new()
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') {
            $backslashes++
            continue
        }
        if ($character -eq '"') {
            [void]$builder.Append(('\' * (($backslashes * 2) + 1)))
            [void]$builder.Append('"')
            $backslashes = 0
            continue
        }
        if ($backslashes -gt 0) {
            [void]$builder.Append(('\' * $backslashes))
            $backslashes = 0
        }
        [void]$builder.Append($character)
    }
    if ($backslashes -gt 0) {
        [void]$builder.Append(('\' * ($backslashes * 2)))
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Resolve-RequiredLocalPath {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$AllowMissing
    )

    if ($Value.StartsWith('\\') -or $Value.StartsWith('//') -or $Value.Contains('://')) {
        throw "$Label must be a local filesystem path"
    }
    $full = [IO.Path]::GetFullPath($Value)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.TrimEnd('\') -eq $root.TrimEnd('\')) {
        throw "$Label cannot be a volume root"
    }
    if (-not $AllowMissing -and -not (Test-Path -LiteralPath $full)) {
        throw "$Label does not exist: $full"
    }
    $drive = [IO.DriveInfo]::new($root)
    if ($drive.DriveType -ne [IO.DriveType]::Fixed) {
        throw "$Label must use a local fixed drive"
    }
    $probe = $full
    while (-not (Test-Path -LiteralPath $probe)) {
        $parent = Split-Path -Parent $probe
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $probe) {
            break
        }
        $probe = $parent
    }
    while (Test-Path -LiteralPath $probe) {
        $item = Get-Item -LiteralPath $probe -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label cannot traverse a reparse point"
        }
        $parent = Split-Path -Parent $probe
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $probe) {
            break
        }
        $probe = $parent
    }
    return $full
}

function Test-ExactJsonProperties {
    param(
        [AllowNull()]$Value,
        [Parameter(Mandatory = $true)][string[]]$Names
    )

    if ($null -eq $Value) {
        return $false
    }
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $expected = @($Names | Sort-Object)
    if ($actual.Count -ne $expected.Count) {
        return $false
    }
    for ($index = 0; $index -lt $expected.Count; $index++) {
        if ([string]$actual[$index] -ne [string]$expected[$index]) {
            return $false
        }
    }
    return $true
}

function Read-ValidRunStateCandidate {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    try {
        $receipt = Read-LauncherAuthorityJson $Path 'run-state'
        $candidate = $receipt.value
        $required = @(
            'schema_version', 'revision', 'run_id', 'status', 'created_at_utc',
            'updated_at_utc', 'runner', 'trainer', 'inputs', 'command', 'progress',
            'heartbeat', 'checkpoint', 'logs', 'outputs', 'terminal')
        if (-not (Test-ExactJsonProperties -Value $candidate -Names $required) -or
            [string]$candidate.schema_version -ne 'airi.behavior-durable-run.v1' -or
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
            if (-not (Test-ExactJsonProperties -Value $record -Names $processProperties) -or
                [int64]$record.pid -le 0 -or
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
            if (-not (Test-ExactJsonProperties -Value $candidate.terminal -Names @(
                        'exit_code', 'reason', 'at_utc', 'checkpoint_verification')) -or
                [int]$candidate.terminal.exit_code -ne 75 -or
                [string]$candidate.terminal.reason -ne 'safe-optimizer-boundary' -or
                -not (Test-ExactJsonProperties -Value $candidate.terminal.checkpoint_verification -Names @(
                        'schema_version', 'checkpoint_relative_path',
                        'checkpoint_manifest_sha256', 'checkpoint_payload_sha256',
                        'checkpoint_payload_bytes', 'canonical_pins_sha256')) -or
                [string]$candidate.terminal.checkpoint_verification.schema_version -ne
                    'airi.behavior-checkpoint-verification.v1') {
                return $null
            }
        }
        elseif ([string]$candidate.status -eq 'complete' -and
            -not (Test-ExactJsonProperties -Value $candidate.terminal -Names @(
                    'exit_code', 'reason', 'at_utc', 'final_evidence_root'))) {
            return $null
        }
        elseif ($terminalStatus -and -not (Test-ExactJsonProperties -Value $candidate.terminal -Names @(
                    'exit_code', 'reason', 'at_utc'))) {
            return $null
        }
        $hash = [Security.Cryptography.SHA256]::Create()
        try {
            $candidate | Add-Member -NotePropertyName '__authority_sha256' -NotePropertyValue (
                ([BitConverter]::ToString($hash.ComputeHash($receipt.bytes))).Replace('-', '').ToLowerInvariant()) -Force
        }
        finally {
            $hash.Dispose()
        }
        $candidate | Add-Member -NotePropertyName '__authority_run_id' -NotePropertyValue ([string]$candidate.run_id) -Force
        $candidate | Add-Member -NotePropertyName '__authority_revision' -NotePropertyValue ([int64]$candidate.revision) -Force
        return $candidate
    }
    catch {
        return $null
    }
}

function Read-ExistingRunState {
    param([Parameter(Mandatory = $true)][string]$Directory)

    $currentPath = Join-Path $Directory 'run-state.json'
    $previousPath = Join-Path $Directory 'run-state.prev.json'
    if (-not (Test-Path -LiteralPath $currentPath) -and
        -not (Test-Path -LiteralPath $previousPath)) {
        return $null
    }
    $anchorReceipt = Read-LauncherAuthorityJson (Join-Path $Directory 'run-state.anchor.json') 'run-state anchor'
    $anchor = $anchorReceipt.value
    if (-not (Test-ExactJsonProperties -Value $anchor -Names @(
                'schema_version', 'run_id', 'current', 'previous')) -or
        [string]$anchor.schema_version -ne 'airi.behavior-durable-run-anchor.v1' -or
        [string]::IsNullOrWhiteSpace([string]$anchor.run_id) -or
        $null -eq $anchor.current) {
        throw 'run-state anchor schema is invalid'
    }
    foreach ($name in @('current', 'previous')) {
        $entry = $anchor.$name
        if ($null -eq $entry) { continue }
        if (-not (Test-ExactJsonProperties -Value $entry -Names @('sha256', 'revision')) -or
            [string]$entry.sha256 -notmatch '^[0-9a-f]{64}$' -or
            [int64]$entry.revision -lt 0) {
            throw "run-state anchor $name is invalid"
        }
    }
    $current = Read-ValidRunStateCandidate $currentPath
    if ($null -ne $current -and
        [string]$current.__authority_run_id -eq [string]$anchor.run_id -and
        [string]$current.__authority_sha256 -eq [string]$anchor.current.sha256 -and
        [int64]$current.__authority_revision -eq [int64]$anchor.current.revision) {
        return $current
    }
    if ($null -eq $current -and (Test-Path -LiteralPath $currentPath)) {
        throw 'Current run-state receipt is invalid; previous state cannot authorize resume'
    }
    $previous = Read-ValidRunStateCandidate $previousPath
    if ($null -ne $previous -and
        [string]$previous.status -notin @('paused-safe', 'complete', 'failed', 'interrupted') -and
        [string]$previous.__authority_run_id -eq [string]$anchor.run_id -and
        [string]$previous.__authority_sha256 -eq [string]$anchor.current.sha256 -and
        [int64]$previous.__authority_revision -eq [int64]$anchor.current.revision) {
        return $previous
    }
    throw 'No anchor-authorized current or previous run-state receipt is available'
}

$resolvedRunDir = Resolve-RequiredLocalPath $RunDir 'RunDir' -AllowMissing
$resolvedPython = Resolve-RequiredLocalPath $PythonPath 'PythonPath'
$resolvedTrainer = Resolve-RequiredLocalPath $TrainerPath 'TrainerPath'
$resolvedCheckpointHelper = Resolve-RequiredLocalPath (
    (Join-Path (Split-Path -Parent $resolvedTrainer) 'behavior_training_checkpoint.py')) 'CheckpointHelperPath'
$resolvedWorking = Resolve-RequiredLocalPath $WorkingDirectory 'WorkingDirectory'
$resolvedInputManifest = Resolve-RequiredLocalPath $InputManifestPath 'InputManifestPath'
$runnerPath = Resolve-RequiredLocalPath (
    (Join-Path $PSScriptRoot 'ollama-proxy\training\durable_training_runner.py')) 'RunnerPath'

if ($PauseAtFirstOptimizerBoundary -and (Test-PathEntryExists $resolvedRunDir)) {
    throw 'PauseAtFirstOptimizerBoundary requires an absent RunDir'
}

$inputManifestItem = Get-Item -LiteralPath $resolvedInputManifest -Force
if (-not ($inputManifestItem -is [IO.FileInfo])) {
    throw 'InputManifestPath must be a regular file'
}
if (($inputManifestItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'InputManifestPath cannot be a reparse point'
}
$actualInputManifestSha256 = Get-FileSha256 $resolvedInputManifest
if ($actualInputManifestSha256 -ne $InputManifestSha256) {
    throw 'InputManifestPath SHA-256 does not match InputManifestSha256'
}
$requestedTrainerSourceSha256 = Get-FileSha256 $resolvedTrainer
$requestedCheckpointHelperSourceSha256 = Get-FileSha256 $resolvedCheckpointHelper
$requestedRunnerSourceSha256 = Get-FileSha256 $runnerPath
$effectiveTrainerArguments = @($TrainerArguments)
foreach ($binding in @(
        [pscustomobject]@{ flag = '--run-dir'; value = $resolvedRunDir },
        [pscustomobject]@{ flag = '--run-id'; value = $RunId },
        [pscustomobject]@{
            flag = '--checkpoint-every-optimizer-steps'
            value = [string]$CheckpointEveryOptimizerSteps
        })) {
    $positions = @()
    for ($index = 0; $index -lt $effectiveTrainerArguments.Count; $index++) {
        if ([string]$effectiveTrainerArguments[$index] -eq [string]$binding.flag) {
            $positions += $index
        }
    }
    if ($positions.Count -gt 1 -or
        ($positions.Count -eq 1 -and $positions[0] + 1 -ge $effectiveTrainerArguments.Count)) {
        throw "Trainer argument is duplicated or missing its value: $($binding.flag)"
    }
    if ($positions.Count -eq 1) {
        if ([string]$effectiveTrainerArguments[$positions[0] + 1] -ne [string]$binding.value) {
            throw "Trainer argument conflicts with the durable runner: $($binding.flag)"
        }
    }
    else {
        $effectiveTrainerArguments += @([string]$binding.flag, [string]$binding.value)
    }
}
$requestedTrainerCommandSha256 = Get-CanonicalStringArraySha256 -Values (
    @($resolvedPython, $resolvedTrainer) + $effectiveTrainerArguments)

foreach ($argument in $TrainerArguments) {
    if ($argument -match '(?i)^--.*(?:password|passwd|secret|token|api[-_]?key)') {
        throw 'Secret-bearing trainer flags are forbidden'
    }
}

$statePath = Join-Path $resolvedRunDir 'run-state.json'
$baselineRevision = -1
$existing = Read-ExistingRunState $resolvedRunDir
if ($null -ne $existing) {
    if ([string]$existing.run_id -ne $RunId) {
        throw 'RunDir belongs to a different run ID'
    }
    $baselineRevision = [int]$existing.revision
    $runnerAlive = Test-ExactProcessRecord $existing.runner
    $trainerAlive = Test-ExactProcessRecord $existing.trainer
    if ($runnerAlive) {
        $requiredInputProperties = @(
            'dataset_sha256', 'model_weight_sha256', 'trainer_source_sha256',
            'input_manifest_path', 'input_manifest_sha256',
            'input_manifest_training_config_sha256', 'checkpoint_helper_source_sha256')
        # A v3 (adapter-weights-only) run-state carries the init mode and four
        # adapter provenance pins; treat that exact superset as the live shape.
        if (@($existing.inputs.PSObject.Properties.Name) -contains 'init_mode') {
            $requiredInputProperties += @(
                'init_mode', 'init_adapter_dir', 'init_adapter_model_sha256',
                'init_adapter_config_sha256', 'init_adapter_artifact_manifest_sha256')
        }
        $requiredCommandProperties = @(
            'canonical_sha256', 'base_canonical_sha256',
            'runner_source_sha256', 'trainer_source_sha256')
        if (-not (Test-ExactJsonProperties -Value $existing.inputs -Names $requiredInputProperties) -or
            -not (Test-ExactJsonProperties -Value $existing.command -Names $requiredCommandProperties) -or
            -not [string]::Equals(
                [string]$existing.inputs.input_manifest_path, $resolvedInputManifest,
                [StringComparison]::OrdinalIgnoreCase) -or
            [string]$existing.inputs.input_manifest_sha256 -ne $InputManifestSha256 -or
            [string]$existing.inputs.trainer_source_sha256 -ne $requestedTrainerSourceSha256 -or
            [string]$existing.inputs.checkpoint_helper_source_sha256 -ne $requestedCheckpointHelperSourceSha256 -or
            [string]$existing.command.base_canonical_sha256 -ne $requestedTrainerCommandSha256 -or
            [string]$existing.command.runner_source_sha256 -ne $requestedRunnerSourceSha256 -or
            [string]$existing.command.trainer_source_sha256 -ne $requestedTrainerSourceSha256) {
            throw 'Recorded live runner inputs or trainer command differ from the requested launch'
        }
        [pscustomobject]@{
            status = 'already-running'
            run_id = $RunId
            run_state = $statePath
            runner_pid = if ($null -ne $existing.runner) { $existing.runner.pid } else { $null }
            trainer_pid = if ($null -ne $existing.trainer) { $existing.trainer.pid } else { $null }
        }
        return
    }
    if ($trainerAlive) {
        throw 'Recorded trainer is alive without its durable runner; refusing duplicate launch'
    }
    if (-not $ResumeInterrupted) {
        throw 'Existing run-state requires -ResumeInterrupted after PID/command reconciliation'
    }
}

$runnerArguments = @(
    $runnerPath,
    '--run-dir', $resolvedRunDir,
    '--run-id', $RunId,
    '--python', $resolvedPython,
    '--trainer', $resolvedTrainer,
    '--working-directory', $resolvedWorking,
    '--input-manifest-path', $resolvedInputManifest,
    '--input-manifest-sha256', $InputManifestSha256,
    '--checkpoint-every-optimizer-steps', [string]$CheckpointEveryOptimizerSteps,
    '--heartbeat-seconds', [string]$HeartbeatSeconds
)
if ($ResumeInterrupted) {
    $runnerArguments += '--resume-interrupted'
}
if ($PauseAtFirstOptimizerBoundary) {
    if ($ResumeInterrupted) {
        throw 'PauseAtFirstOptimizerBoundary is fresh-run only and cannot be combined with ResumeInterrupted'
    }
    $runnerArguments += '--pause-at-first-optimizer-boundary'
}
$runnerArguments += '--'
$runnerArguments += $TrainerArguments
$argumentLine = (($runnerArguments | ForEach-Object {
    ConvertTo-WindowsCommandLineArgument ([string]$_)
}) -join ' ')

$trainerStdout = Join-Path (Join-Path $resolvedRunDir 'logs') 'trainer.stdout.log'
$trainerStderr = Join-Path (Join-Path $resolvedRunDir 'logs') 'trainer.stderr.log'
$launchStartedUtc = [DateTime]::UtcNow
$started = Start-Process `
    -FilePath $resolvedPython `
    -ArgumentList $argumentLine `
    -WorkingDirectory $resolvedWorking `
    -WindowStyle Hidden `
    -PassThru

$deadline = [DateTime]::UtcNow.AddSeconds(30)
$launchShimExited = $false
$observedRunner = $null
$observedTrainer = $null
do {
    Start-Sleep -Milliseconds 500
    if (Test-Path -LiteralPath $statePath) {
        try {
            $state = Read-ValidRunStateCandidate $statePath
            if ($null -eq $state) {
                continue
            }
            $pollAnchorReceipt = Read-LauncherAuthorityJson (
                (Join-Path $resolvedRunDir 'run-state.anchor.json')) 'run-state anchor'
            $pollAnchor = $pollAnchorReceipt.value
            if (-not (Test-ExactJsonProperties -Value $pollAnchor -Names @(
                        'schema_version', 'run_id', 'current', 'previous')) -or
                [string]$pollAnchor.schema_version -ne 'airi.behavior-durable-run-anchor.v1' -or
                [string]::IsNullOrWhiteSpace([string]$pollAnchor.run_id) -or
                $null -eq $pollAnchor.current -or
                -not (Test-ExactJsonProperties -Value $pollAnchor.current -Names @('sha256', 'revision')) -or
                [string]$pollAnchor.current.sha256 -notmatch '^[0-9a-f]{64}$' -or
                [int64]$pollAnchor.current.revision -lt 0 -or
                ($null -ne $pollAnchor.previous -and (
                    -not (Test-ExactJsonProperties -Value $pollAnchor.previous -Names @('sha256', 'revision')) -or
                    [string]$pollAnchor.previous.sha256 -notmatch '^[0-9a-f]{64}$' -or
                    [int64]$pollAnchor.previous.revision -lt 0)) -or
                [string]$state.__authority_run_id -ne [string]$pollAnchor.run_id -or
                [string]$state.__authority_sha256 -ne [string]$pollAnchor.current.sha256 -or
                [int64]$state.__authority_revision -ne [int64]$pollAnchor.current.revision) {
                continue
            }
            $requestedStateBinding = (
                [string]::Equals(
                    [string]$state.inputs.input_manifest_path, $resolvedInputManifest,
                    [StringComparison]::OrdinalIgnoreCase) -and
                [string]$state.inputs.input_manifest_sha256 -eq $InputManifestSha256 -and
                [string]$state.inputs.trainer_source_sha256 -eq $requestedTrainerSourceSha256 -and
                [string]$state.inputs.checkpoint_helper_source_sha256 -eq $requestedCheckpointHelperSourceSha256 -and
                [string]$state.command.base_canonical_sha256 -eq $requestedTrainerCommandSha256 -and
                [string]$state.command.runner_source_sha256 -eq $requestedRunnerSourceSha256 -and
                [string]$state.command.trainer_source_sha256 -eq $requestedTrainerSourceSha256)
            $terminalStatus = [string]$state.status -in @(
                'paused-safe', 'complete', 'failed', 'interrupted')
            $trustedLiveState = (-not $terminalStatus -and
                [string]$state.run_id -eq $RunId -and
                [int]$state.revision -gt $baselineRevision -and
                $requestedStateBinding -and
                (Test-StartedRunnerProvenance $state.runner $started.Id $launchStartedUtc))
            $trustedTrainerState = $false
            if ($trustedLiveState) {
                if ($null -eq $observedRunner) {
                    $observedRunner = $state.runner
                }
                elseif (-not (Test-SameProcessRecord $observedRunner $state.runner)) {
                    throw 'Observed durable runner identity changed during launch polling'
                }
                if ($null -ne $state.trainer -and
                    (Test-ObservedTrainerProvenance $state.trainer $observedRunner)) {
                    if ($null -eq $observedTrainer) {
                        $observedTrainer = $state.trainer
                    }
                    elseif (-not (Test-SameProcessRecord $observedTrainer $state.trainer)) {
                        throw 'Observed trainer identity changed during launch polling'
                    }
                    # A starting receipt is not authoritative until the trainer
                    # is exact-live and proven to be the observed runner's child.
                    $trustedTrainerState = $true
                }
            }
            $terminalReceipt = Test-VerifiedTerminalLaunchReceipt `
                -State $state `
                -RunDir $resolvedRunDir `
                -ObservedRunner $observedRunner `
                -ObservedTrainer $observedTrainer
            $acceptableState = if ($terminalStatus) {
                $terminalReceipt
            }
            else {
                $trustedTrainerState
            }
            if ([string]$state.run_id -eq $RunId -and
                [int]$state.revision -gt $baselineRevision -and
                $requestedStateBinding -and
                $acceptableState) {
                $launchReceipt = [pscustomobject]@{
                    status = [string]$state.status
                    run_id = $RunId
                    runner_pid = [int]$state.runner.pid
                    run_state = $statePath
                    stdout = $trainerStdout
                    stderr = $trainerStderr
                }
                $started.Dispose()
                $launchReceipt
                return
            }
        }
        catch {
            # Atomic replacement can race this read; retry until the deadline.
        }
    }
    $started.Refresh()
    if ($started.HasExited -and -not $launchShimExited) {
        $started.WaitForExit()
        $launchShimExited = $true
    }
} while ([DateTime]::UtcNow -lt $deadline)

$started.Dispose()
throw "Durable runner $RunId did not publish a verified run-state within 30 seconds; launch_shim_exited=$launchShimExited"
