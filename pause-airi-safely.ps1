[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunDir,

    [ValidateRange(10, 3600)]
    [int]$TimeoutSeconds = 600,

    [ValidateRange(1, 15)]
    [int]$PollSeconds = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

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

$resolvedRunDir = Resolve-RequiredLocalRunDirectory $RunDir
$statePath = Join-Path $resolvedRunDir 'run-state.json'
$previousStatePath = Join-Path $resolvedRunDir 'run-state.prev.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf) -and
    -not (Test-Path -LiteralPath $previousStatePath -PathType Leaf)) {
    throw 'run-state current and previous receipts are missing; no training run can be reconciled'
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
        $candidate = Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json
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
        return $candidate
    }
    catch {
        return $null
    }
}

function Read-RunState {
    $current = Read-ValidRunStateCandidate $statePath
    if ($null -ne $current) {
        return $current
    }
    # Preserve a torn or malformed current receipt.  The durable runner owns its
    # quarantine/write-through protocol; pause only consumes a strict previous receipt.
    $previous = Read-ValidRunStateCandidate $previousStatePath
    if ($null -ne $previous) {
        return $previous
    }
    throw 'No valid current or previous run-state receipt is available'
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

function Assert-VerifiedCheckpoint {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$Ack
    )

    if ($null -eq $State.checkpoint -or
        [string]$State.checkpoint.relative_path -ne [string]$Ack.checkpoint_relative_path -or
        [string]$State.checkpoint.manifest_sha256 -ne [string]$Ack.checkpoint_manifest_sha256) {
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
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'checkpoint manifest is missing'
    }
    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($manifestHash -ne [string]$Ack.checkpoint_manifest_sha256) {
        throw 'checkpoint manifest SHA does not match the pause ack'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ([int]$manifest.schema_version -ne 1 -or
        [string]$manifest.generation -ne $generation -or
        [string]$manifest.run_id -ne [string]$State.run_id -or
        [string]$manifest.payload.name -ne 'state.pt') {
        throw 'checkpoint manifest identity is invalid'
    }
    $payloadPath = Join-Path $generationDir 'state.pt'
    if (-not (Test-Path -LiteralPath $payloadPath -PathType Leaf)) {
        throw 'checkpoint payload is missing'
    }
    $payload = Get-Item -LiteralPath $payloadPath
    $payloadHash = (Get-FileHash -LiteralPath $payloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ([int64]$manifest.payload.bytes -ne $payload.Length -or
        [string]$manifest.payload.sha256 -ne $payloadHash) {
        throw 'checkpoint payload integrity verification failed'
    }
    if ([int]$State.progress.pending_microbatches -ne 0) {
        throw 'checkpoint is not at a safe optimizer boundary'
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
    $path = [IO.Path]::GetFullPath([string]$Receipt.path)
    if ([string]$Receipt.kind -eq 'file') {
        Assert-ExactJsonProperties -Value $Receipt -Names @(
            'path', 'kind', 'size', 'sha256') -Label 'file artifact receipt'
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'completed file artifact is missing'
        }
        $item = Get-Item -LiteralPath $path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            [int64]$Receipt.size -ne $item.Length -or
            [string]$Receipt.sha256 -ne
                (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw 'completed file artifact receipt no longer matches disk'
        }
        return
    }
    if ([string]$Receipt.kind -ne 'directory') {
        throw 'completed artifact receipt kind is invalid'
    }
    Assert-ExactJsonProperties -Value $Receipt -Names @(
        'path', 'kind', 'files', 'manifest_sha256') -Label 'directory artifact receipt'
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
        if ([int64]$row.size -ne $item.Length -or
            [string]$row.sha256 -ne
                (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw 'completed directory artifact file receipt no longer matches disk'
        }
    }
    $sortedRows = @($canonicalRows | Sort-Object { [string]$_.path })
    $canonicalJson = ConvertTo-Json -InputObject $sortedRows -Compress -Depth 5
    if ((Get-Utf8Sha256 ($canonicalJson + "`n")) -ne [string]$Receipt.manifest_sha256) {
        throw 'completed directory artifact manifest receipt is invalid'
    }
}

function Assert-VerifiedCompletion {
    param([Parameter(Mandatory = $true)]$State)

    if ([string]$State.status -ne 'complete') {
        throw 'run is not complete'
    }
    Assert-ExactJsonProperties -Value $State.terminal -Names @(
        'exit_code', 'reason', 'at_utc') -Label 'complete terminal receipt'
    Assert-ExactJsonProperties -Value $State.outputs -Names @(
        'adapter', 'report') -Label 'complete outputs receipt'
    if ([int]$State.terminal.exit_code -ne 0 -or
        [string]$State.terminal.reason -ne 'trainer-complete') {
        throw 'complete terminal receipt is invalid'
    }
    Assert-VerifiedArtifactReceipt $State.outputs.adapter $true
    Assert-VerifiedArtifactReceipt $State.outputs.report $false
}

function Wait-VerifiedCompletionPowerOff {
    param([Parameter(Mandatory = $true)]$State)

    $deadline = [DateTime]::UtcNow.AddSeconds([Math]::Min(30, $TimeoutSeconds))
    do {
        Assert-VerifiedCompletion $State
        if (-not (Test-ExactProcessRecord $State.trainer) -and
            -not (Test-ExactProcessRecord $State.runner)) {
            [pscustomobject]@{
                status = 'complete'
                run_id = [string]$State.run_id
                optimizer_steps = [int]$State.progress.optimizer_steps
                microsteps_completed = [int]$State.progress.microsteps_completed
            }
            Write-Output 'SAFE_TO_POWER_OFF'
            return
        }
        Start-Sleep -Milliseconds 200
        $State = Read-RunState
    } while ([DateTime]::UtcNow -lt $deadline -and [string]$State.status -eq 'complete')
    throw 'Completed artifacts are verified but trainer/runner did not exit in time'
}

$initial = Read-RunState
if ([string]$initial.status -eq 'complete') {
    Wait-VerifiedCompletionPowerOff $initial
    return
}
if ([string]$initial.status -eq 'paused-safe' -and
    [int]$initial.terminal.exit_code -eq 75 -and
    [string]$initial.terminal.reason -eq 'safe-optimizer-boundary') {
    $requestPath = Join-Path $resolvedRunDir 'control\pause.request.json'
    $ackPath = Join-Path $resolvedRunDir 'control\pause.ack.json'
    if ((Test-Path -LiteralPath $requestPath) -and (Test-Path -LiteralPath $ackPath)) {
        $request = Get-Content -LiteralPath $requestPath -Raw -Encoding utf8 | ConvertFrom-Json
        $ack = Get-Content -LiteralPath $ackPath -Raw -Encoding utf8 | ConvertFrom-Json
        Assert-PauseReceiptIdentity $initial $request $ack
        Assert-VerifiedCheckpoint $initial $ack
        Write-Output 'SAFE_TO_POWER_OFF'
        return
    }
}

if ([string]$initial.status -notin @('starting', 'running', 'pause-requested', 'checkpointing')) {
    throw "Run status '$($initial.status)' is not actively trainable"
}
$identityDeadline = [DateTime]::UtcNow.AddSeconds([Math]::Min(30, $TimeoutSeconds))
while (-not (Test-ExactProcessRecord $initial.trainer)) {
    if ([string]$initial.status -notin @('starting', 'running', 'pause-requested', 'checkpointing')) {
        throw "Training became '$($initial.status)' before trainer identity was ready"
    }
    if ([DateTime]::UtcNow -ge $identityDeadline) {
        throw 'Recorded trainer PID/creation/executable/command identity did not become live; refusing blind pause'
    }
    Start-Sleep -Milliseconds 200
    $initial = Read-RunState
}

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

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds $PollSeconds
    try {
        $state = Read-RunState
    }
    catch {
        continue
    }
    if ([string]$state.run_id -ne [string]$initial.run_id) {
        throw 'Run identity changed while waiting for safe pause'
    }
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
        Assert-PauseReceiptIdentity $state $request $ack
        Assert-VerifiedCheckpoint $state $ack
        if (Test-ExactProcessRecord $state.trainer) {
            continue
        }
        [pscustomobject]@{
            status = 'paused-safe'
            run_id = [string]$state.run_id
            optimizer_steps = [int]$state.progress.optimizer_steps
            microsteps_completed = [int]$state.progress.microsteps_completed
            checkpoint = [string]$state.checkpoint.relative_path
            checkpoint_manifest_sha256 = [string]$state.checkpoint.manifest_sha256
        }
        Write-Output 'SAFE_TO_POWER_OFF'
        return
    }
    if ([string]$state.status -eq 'complete') {
        Wait-VerifiedCompletionPowerOff $state
        return
    }
    if ([string]$state.status -in @('failed', 'interrupted')) {
        throw "Training became '$($state.status)' before a verified safe-pause receipt"
    }
} while ([DateTime]::UtcNow -lt $deadline)

throw 'Timed out before SAFE_TO_POWER_OFF; pause request remains durable for the trainer'
