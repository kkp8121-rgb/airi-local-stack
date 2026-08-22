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

    [ValidatePattern('^$|^[0-9a-f]{64}$')]
    [string]$InputManifestSha256 = '',

    [ValidateRange(1, 1000000)]
    [int]$CheckpointEveryOptimizerSteps = 5,

    [ValidateRange(1, 15)]
    [int]$HeartbeatSeconds = 10,

    [switch]$ResumeInterrupted,

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
    if ($drive.DriveType -eq [IO.DriveType]::Network) {
        throw "$Label cannot use a mapped network drive"
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
        $candidate = Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json
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
    $current = Read-ValidRunStateCandidate $currentPath
    if ($null -ne $current) {
        return $current
    }
    $previous = Read-ValidRunStateCandidate $previousPath
    if ($null -ne $previous) {
        return $previous
    }
    if ((Test-Path -LiteralPath $currentPath) -or (Test-Path -LiteralPath $previousPath)) {
        throw 'No valid current or previous run-state receipt is available'
    }
    return $null
}

$resolvedRunDir = Resolve-RequiredLocalPath $RunDir 'RunDir' -AllowMissing
$resolvedPython = Resolve-RequiredLocalPath $PythonPath 'PythonPath'
$resolvedTrainer = Resolve-RequiredLocalPath $TrainerPath 'TrainerPath'
$resolvedWorking = Resolve-RequiredLocalPath $WorkingDirectory 'WorkingDirectory'
$runnerPath = Resolve-RequiredLocalPath (
    (Join-Path $PSScriptRoot 'ollama-proxy\training\durable_training_runner.py')) 'RunnerPath'

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

[IO.Directory]::CreateDirectory($resolvedRunDir) | Out-Null

$runnerArguments = @(
    $runnerPath,
    '--run-dir', $resolvedRunDir,
    '--run-id', $RunId,
    '--python', $resolvedPython,
    '--trainer', $resolvedTrainer,
    '--working-directory', $resolvedWorking,
    '--input-manifest-sha256', $InputManifestSha256,
    '--checkpoint-every-optimizer-steps', [string]$CheckpointEveryOptimizerSteps,
    '--heartbeat-seconds', [string]$HeartbeatSeconds
)
if ($ResumeInterrupted) {
    $runnerArguments += '--resume-interrupted'
}
$runnerArguments += '--'
$runnerArguments += $TrainerArguments
$argumentLine = (($runnerArguments | ForEach-Object {
    ConvertTo-WindowsCommandLineArgument ([string]$_)
}) -join ' ')

$logsDir = Join-Path $resolvedRunDir 'logs'
[IO.Directory]::CreateDirectory($logsDir) | Out-Null
$trainerStdout = Join-Path $logsDir 'trainer.stdout.log'
$trainerStderr = Join-Path $logsDir 'trainer.stderr.log'
$started = Start-Process `
    -FilePath $resolvedPython `
    -ArgumentList $argumentLine `
    -WorkingDirectory $resolvedWorking `
    -WindowStyle Hidden `
    -PassThru

$deadline = [DateTime]::UtcNow.AddSeconds(30)
$launchShimExited = $false
do {
    Start-Sleep -Milliseconds 200
    if (Test-Path -LiteralPath $statePath) {
        try {
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding utf8 | ConvertFrom-Json
            $terminalReceipt = ([string]$state.status -in @(
                'paused-safe', 'complete', 'failed', 'interrupted') -and
                $null -ne $state.terminal)
            if ([string]$state.run_id -eq $RunId -and
                [int]$state.revision -gt $baselineRevision -and
                ((Test-ExactProcessRecord $state.runner) -or $terminalReceipt)) {
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
throw "Durable runner did not publish a verified run-state within 30 seconds; launch_shim_exited=$launchShimExited"
