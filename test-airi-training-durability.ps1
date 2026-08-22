[CmdletBinding()]
param([switch]$KeepFailedArtifacts)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$launcherPath = Join-Path $root 'run-airi-behavior-training-durable.ps1'
$pausePath = Join-Path $root 'pause-airi-safely.ps1'
$runnerPath = Join-Path $root 'ollama-proxy\training\durable_training_runner.py'

foreach ($path in @($launcherPath, $pausePath, $runnerPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required durability file is missing: $path"
    }
}

foreach ($path in @($launcherPath, $pausePath)) {
    $tokens = $null
    $errors = $null
    [Management.Automation.Language.Parser]::ParseFile(
        $path, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count -ne 0) {
        throw "PowerShell parse failed for $path : $($errors[0].Message)"
    }
}

$launcher = [IO.File]::ReadAllText($launcherPath, [Text.UTF8Encoding]::new($false, $true))
$pause = [IO.File]::ReadAllText($pausePath, [Text.UTF8Encoding]::new($false, $true))
foreach ($token in @(
    'Start-Process', '-WindowStyle Hidden', 'Test-ExactProcessRecord',
    '--checkpoint-every-optimizer-steps', '--resume-interrupted', 'run-state.json',
    'run-state.prev.json', 'cannot traverse a reparse point',
    'DriveType]::Fixed', 'alive without its durable runner', 'baselineRevision',
    '$state = Read-ValidRunStateCandidate $statePath', '$requestedStateBinding',
    'Test-VerifiedTerminalLaunchReceipt', 'final_evidence_root',
    'Read-LauncherAuthoritySnapshot', 'Test-ArtifactReceipt -Receipt $State.outputs.report -Required',
    '__authority_sha256', 'No anchor-authorized current or previous run-state receipt is available',
    '$pollAnchorReceipt = Read-LauncherAuthorityJson',
    'Test-StartedRunnerProvenance', 'Test-ObservedTrainerProvenance $state.trainer $observedRunner',
    '$trustedTrainerState', '$acceptableState',
    'checkpoint_helper_source_sha256', '$requestedCheckpointHelperSourceSha256',
    'CheckpointHelperPath')) {
    if (-not $launcher.Contains($token)) {
        throw "Durable launcher contract token is missing: $token"
    }
}
foreach ($token in @(
    'SAFE_TO_POWER_OFF', 'Test-ExactProcessRecord', 'pause.request.json',
    'pause.ack.json', 'checkpoint_manifest_sha256', 'pending_microbatches',
    'complete outputs receipt', 'Assert-ExactJsonProperties', 'MoveFileEx',
    'DriveType]::Fixed', 'cannot traverse a reparse point', 'run-state.prev.json',
    'Find-ActiveDurableRunDirectory', 'durable_training_runner',
    'no active durable AIRI training run', 'more than one active durable AIRI training run',
    'An unanchored or terminal previous run-state cannot authorize power-off',
    'checkpoint canonical pins SHA differs', 'Read-AuthoritativeFileSnapshot',
    'airi.behavior-checkpoint-index.v2', 'airi.behavior-final-evidence-root.v1',
    'checkpoint_helper_source_sha256', 'run-state checkpoint helper source SHA is invalid')) {
    if (-not $pause.Contains($token)) {
        throw "Safe-pause contract token is missing: $token"
    }
}

$temporaryRoot = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) (
    'airi-durability-contract-' + [Guid]::NewGuid().ToString('N'))))
$expectedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
if (-not $temporaryRoot.StartsWith($expectedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Temporary test directory escaped the system temp root'
}
$contractSucceeded = $false

function Get-ContractUtf8Sha256 {
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

function Get-ContractProcessRecord {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
    return [ordered]@{
        pid = $ProcessId
        creation_time_utc = $process.CreationDate.ToUniversalTime().ToString('o')
        executable_path_sha256 = Get-ContractUtf8Sha256 (
            ([string]$process.ExecutablePath).ToLowerInvariant())
        command_line_sha256 = Get-ContractUtf8Sha256 ([string]$process.CommandLine)
    }
}

function Invoke-OmittedRunDirPause {
    param([int]$TimeoutSeconds = 10)

    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& powershell -NoProfile -ExecutionPolicy Bypass -File $pausePath `
            -TimeoutSeconds $TimeoutSeconds -PollSeconds 1 2>&1)
        return [pscustomobject]@{ exit_code = $LASTEXITCODE; output = ($output -join "`n") }
    }
    finally {
        $ErrorActionPreference = $savedPreference
    }
}

function Invoke-ManualRunDirPause {
    param(
        [Parameter(Mandatory = $true)][string]$RunDir,
        [int]$TimeoutSeconds = 10,
        [int]$PollSeconds = 1,
        [int]$TestOnlyFinalGateDelayMilliseconds = 0
    )

    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $arguments = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $pausePath,
            '-RunDir', $RunDir, '-TimeoutSeconds', $TimeoutSeconds,
            '-PollSeconds', $PollSeconds)
        if ($TestOnlyFinalGateDelayMilliseconds -gt 0) {
            $arguments += @(
                '-TestOnlyFinalGateDelayMilliseconds', $TestOnlyFinalGateDelayMilliseconds)
        }
        $output = @(& powershell @arguments 2>&1)
        return [pscustomobject]@{ exit_code = $LASTEXITCODE; output = ($output -join "`n") }
    }
    finally {
        $ErrorActionPreference = $savedPreference
    }
}

function Test-ContainsSafePowerOffMarker {
    param([AllowNull()][string]$Output)

    if ($null -eq $Output) {
        return $false
    }
    return [Regex]::IsMatch($Output, '(?m)^SAFE_TO_POWER_OFF\r?$')
}

if (Test-ContainsSafePowerOffMarker 'Safe-pause deadline expired before SAFE_TO_POWER_OFF emission') {
    throw 'Subprocess SAFE_TO_POWER_OFF marker parser accepted an error substring'
}
if (-not (Test-ContainsSafePowerOffMarker ("prefix`r`nSAFE_TO_POWER_OFF`nsuffix"))) {
    throw 'Subprocess SAFE_TO_POWER_OFF marker parser rejected an exact multiline marker line'
}

function New-ContractInputManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$TrainerPath,
        [Parameter(Mandatory = $true)][string]$DatasetPath,
        [Parameter(Mandatory = $true)][string]$ModelDir,
        [Parameter(Mandatory = $true)][int]$CheckpointEveryOptimizerSteps
    )

    $config = [ordered]@{
        batch_size = 1
        checkpoint_every_optimizer_steps = $CheckpointEveryOptimizerSteps
        deterministic_validation = $true
        gradient_accumulation = 1
        learning_rate = 0.0002
        lora_alpha = 16
        lora_dropout = 0.05
        lora_r = 8
        max_seq_len = 64
        max_steps = 2
        mode = 'cpu-smoke'
        seed = 123
    }
    $configJson = ($config | ConvertTo-Json -Compress) + "`n"
    $helperPath = Join-Path (Split-Path -Parent $TrainerPath) 'behavior_training_checkpoint.py'
    $modelWeightPath = Join-Path $ModelDir 'model.safetensors'
    if (-not (Test-Path -LiteralPath $DatasetPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $helperPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $modelWeightPath -PathType Leaf)) {
        throw 'v2 fixture manifest requires a dataset, sibling checkpoint helper, and model.safetensors'
    }
    $modelInventory = @(
        Get-ChildItem -LiteralPath $ModelDir -File -Recurse -Force |
        Sort-Object { $_.FullName } |
        ForEach-Object {
            if (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'v2 fixture model inventory cannot contain a reparse point'
            }
            [ordered]@{
                bytes = [int64]$_.Length
                path = $_.FullName.Substring($ModelDir.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        })
    if ($modelInventory.Count -eq 0) {
        throw 'v2 fixture model inventory is empty'
    }
    $manifest = [ordered]@{
        checkpoint_helper_source_sha256 = (Get-FileHash -LiteralPath $helperPath -Algorithm SHA256).Hash.ToLowerInvariant()
        dataset_sha256 = (Get-FileHash -LiteralPath $DatasetPath -Algorithm SHA256).Hash.ToLowerInvariant()
        model_inventory = $modelInventory
        model_weight_sha256 = (Get-FileHash -LiteralPath $modelWeightPath -Algorithm SHA256).Hash.ToLowerInvariant()
        schema_version = 'airi.behavior-input-manifest.v2'
        trainer_source_sha256 = (Get-FileHash -LiteralPath $TrainerPath -Algorithm SHA256).Hash.ToLowerInvariant()
        training_config = $config
        training_config_sha256 = Get-ContractUtf8Sha256 $configJson
    }
    [IO.File]::WriteAllText($Path, ($manifest | ConvertTo-Json -Compress) + "`n", [Text.UTF8Encoding]::new($false))
    $parsed = Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json
    if ([string]$parsed.schema_version -ne 'airi.behavior-input-manifest.v2' -or
        [string]$parsed.checkpoint_helper_source_sha256 -ne [string]$manifest.checkpoint_helper_source_sha256 -or
        [string]$parsed.dataset_sha256 -ne [string]$manifest.dataset_sha256 -or
        [string]$parsed.model_weight_sha256 -ne [string]$manifest.model_weight_sha256 -or
        [string]$parsed.trainer_source_sha256 -ne [string]$manifest.trainer_source_sha256 -or
        [string]$parsed.training_config_sha256 -ne [string]$manifest.training_config_sha256 -or
        @($parsed.model_inventory).Count -ne $modelInventory.Count) {
        throw 'v2 fixture input manifest did not retain its helper/model inventory pins'
    }
    for ($index = 0; $index -lt $modelInventory.Count; $index++) {
        $actual = $parsed.model_inventory[$index]
        $expected = $modelInventory[$index]
        if ((@($actual.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'bytes,path,sha256' -or
            [int64]$actual.bytes -ne [int64]$expected.bytes -or
            [string]$actual.path -ne [string]$expected.path -or
            [string]$actual.sha256 -ne [string]$expected.sha256) {
            throw 'v2 fixture model inventory is not the exact closed regular-file set'
        }
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Start-ContractSleeper {
    param([Parameter(Mandatory = $true)][int]$Seconds)

    [IO.Directory]::CreateDirectory($temporaryRoot) | Out-Null
    $scriptPath = Join-Path $temporaryRoot ('runner-sleeper-' + [Guid]::NewGuid().ToString('N') + '.py')
    [IO.File]::WriteAllText(
        $scriptPath, "import time`ntime.sleep($Seconds)`n", [Text.UTF8Encoding]::new($false))
    Start-Process -FilePath $pythonPath -ArgumentList @($scriptPath) -WindowStyle Hidden | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    do {
        $process = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                [string]$_.CommandLine -like "*$scriptPath*"
            } | Select-Object -First 1)
        if ($process.Count -eq 1 -and $null -ne $process[0].CreationDate) {
            return [pscustomobject]@{ Id = [int]$process[0].ProcessId }
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Actual contract sleeper process did not become observable through Win32_Process'
}

function Wait-ContractProcessExit {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        if ($null -eq (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue)) {
            return
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Actual contract sleeper did not exit before the test deadline'
}

function Write-ContractTerminalPredecessor {
    param(
        [Parameter(Mandatory = $true)]$TerminalState,
        [Parameter(Mandatory = $true)][string]$StatePath
    )

    $predecessor = (($TerminalState | ConvertTo-Json -Compress -Depth 20) | ConvertFrom-Json)
    $predecessor.revision = [int]$TerminalState.revision - 1
    $predecessor.status = 'running'
    $predecessor.terminal = $null
    [IO.File]::WriteAllText(
        (Join-Path (Split-Path -Parent $StatePath) 'run-state.prev.json'),
        (($predecessor | ConvertTo-Json -Compress -Depth 20) + "`n"),
        [Text.UTF8Encoding]::new($false))
    Write-ContractRunStateAnchor -StatePath $StatePath
}

function Write-ContractRunStateAnchor {
    param([Parameter(Mandatory = $true)][string]$StatePath)

    $runDirectory = Split-Path -Parent $StatePath
    $current = Get-Content -LiteralPath $StatePath -Raw -Encoding utf8 | ConvertFrom-Json
    $previousPath = Join-Path $runDirectory 'run-state.prev.json'
    $previous = if (Test-Path -LiteralPath $previousPath -PathType Leaf) {
        Get-Content -LiteralPath $previousPath -Raw -Encoding utf8 | ConvertFrom-Json
    }
    else {
        $null
    }
    $anchor = [ordered]@{
        current = [ordered]@{
            revision = [int64]$current.revision
            sha256 = (Get-FileHash -LiteralPath $StatePath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        previous = if ($null -eq $previous) {
            $null
        }
        else {
            [ordered]@{
                revision = [int64]$previous.revision
                sha256 = (Get-FileHash -LiteralPath $previousPath -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
        run_id = [string]$current.run_id
        schema_version = 'airi.behavior-durable-run-anchor.v1'
    }
    $expectedAnchorBytes = (($anchor | ConvertTo-Json -Compress -Depth 10) + "`n")
    if ($expectedAnchorBytes -cne (
            '{"current":{"revision":' + [int64]$current.revision +
            ',"sha256":"' + (Get-FileHash -LiteralPath $StatePath -Algorithm SHA256).Hash.ToLowerInvariant() +
            '"},"previous":' + $(if ($null -eq $previous) { 'null' } else {
                    '{"revision":' + [int64]$previous.revision +
                    ',"sha256":"' + (Get-FileHash -LiteralPath $previousPath -Algorithm SHA256).Hash.ToLowerInvariant() + '"}'
                }) + ',"run_id":' + ([string]$current.run_id | ConvertTo-Json -Compress) +
            ',"schema_version":"airi.behavior-durable-run-anchor.v1"}' + "`n")) {
        throw 'Synthetic run-state anchor fixture is not canonical JSON'
    }
    [IO.File]::WriteAllText(
        (Join-Path $runDirectory 'run-state.anchor.json'),
        $expectedAnchorBytes,
        [Text.UTF8Encoding]::new($false))
}

function Write-InitialLaunchFailureReceipt {
    param([Parameter(Mandatory = $true)]$ErrorRecord)

    # Keep a failure receipt in the preserved synthetic root without retaining
    # command lines, artifact paths, logs, or any potentially sensitive values.
    $message = [string]$ErrorRecord.Exception.Message
    $message = [Regex]::Replace(
        $message, '(?i)(?:[a-z]:\\|\\\\)[^\s''"]+', '<redacted-path>')
    $receipt = [ordered]@{
        schema_version = 'airi.durability-contract-failure-receipt.v1'
        stage = 'initial-launch'
        at_utc = [DateTime]::UtcNow.ToString('o')
        exception_type = [string]$ErrorRecord.Exception.GetType().FullName
        exception_message = $message
    }
    $target = Join-Path $temporaryRoot 'contract-failure-receipt.json'
    $temporary = Join-Path $temporaryRoot ('.contract-failure-receipt.' +
        [Guid]::NewGuid().ToString('N') + '.tmp')
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(
        (($receipt | ConvertTo-Json -Compress) + "`n"))
    try {
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
        [IO.File]::Move($temporary, $target)
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

$pinnedTestPython = 'D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe'
$pythonPath = if (Test-Path -LiteralPath $pinnedTestPython -PathType Leaf) {
    $pinnedTestPython
}
else {
    (Get-Command python -ErrorAction Stop).Source
}
$contractTrainingArguments = @(
    '--mode', 'cpu-smoke', '--seed', '123', '--lora-r', '8', '--lora-alpha', '16',
    '--lora-dropout', '0.05', '--learning-rate', '0.0002', '--max-steps', '2',
    '--batch-size', '1', '--gradient-accumulation', '1', '--max-seq-len', '64',
    '--deterministic-validation')

try {
    # This contract suite must begin without a durable runner.  Omitted RunDir must
    # refuse rather than selecting a directory by recency or prompting for input.
    $ambientDurableRunners = @(Get-CimInstance Win32_Process | Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_.CommandLine) -and
            [string]$_.CommandLine -like '*durable_training_runner.py*'
        })
    if ($ambientDurableRunners.Count -ne 0) {
        throw ('Durability contract refuses to invoke auto-pause while an ambient durable runner is active: ' +
            (@($ambientDurableRunners | ForEach-Object { [string]$_.ProcessId }) -join ','))
    }
    $noActiveResult = Invoke-OmittedRunDirPause
    if ($noActiveResult.exit_code -eq 0 -or
        $noActiveResult.output -notmatch 'no active durable AIRI training run') {
        throw 'Omitted RunDir accepted an absent active durable runner'
    }

    $runDir = Join-Path $temporaryRoot 'run'
    $generation = 'checkpoint-00000001'
    $generationDir = Join-Path $runDir "checkpoints\$generation"
    $controlDir = Join-Path $runDir 'control'
    [IO.Directory]::CreateDirectory($generationDir) | Out-Null
    [IO.Directory]::CreateDirectory($controlDir) | Out-Null
    $payloadPath = Join-Path $generationDir 'state.pt'
    [IO.File]::WriteAllBytes($payloadPath, [Text.Encoding]::ASCII.GetBytes('verified-state'))
    $payloadHash = (Get-FileHash -LiteralPath $payloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest = [ordered]@{
        generation = $generation
        payload = [ordered]@{ bytes = 14; name = 'state.pt'; sha256 = $payloadHash }
        pins = [ordered]@{
            dataset_sha256 = 'd' * 64
            model_weight_sha256 = 'e' * 64
            trainer_source_sha256 = 'f' * 64
        }
        run_id = 'contract-run'
        schema_version = 1
    }
    $manifestPath = Join-Path $generationDir 'manifest.json'
    [IO.File]::WriteAllText(
        $manifestPath, (($manifest | ConvertTo-Json -Compress) + "`n"),
        [Text.UTF8Encoding]::new($false))
    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $pinsHash = Get-ContractUtf8Sha256 (
        (($manifest.pins | ConvertTo-Json -Compress) + "`n"))
    $request = [ordered]@{
        schema_version = 'airi.behavior-pause-request.v1'
        run_id = 'contract-run'
        request_id = 'pause-contract'
    }
    $ack = [ordered]@{
        schema_version = 'airi.behavior-pause-ack.v1'
        run_id = 'contract-run'
        request_id = 'pause-contract'
        checkpoint_manifest_sha256 = $manifestHash
        checkpoint_relative_path = $generation
        acknowledged_at_utc = '2026-08-22T00:00:00Z'
        safe_to_power_off = $true
    }
    $state = [ordered]@{
        schema_version = 'airi.behavior-durable-run.v1'
        revision = 1
        run_id = 'contract-run'
        status = 'paused-safe'
        created_at_utc = '2026-08-22T00:00:00Z'
        updated_at_utc = '2026-08-22T00:00:00Z'
        runner = [ordered]@{
            pid = 1
            creation_time_utc = '2026-08-22T00:00:00Z'
            executable_path_sha256 = 'a' * 64
            command_line_sha256 = 'b' * 64
        }
        terminal = [ordered]@{
            exit_code = 75
            reason = 'safe-optimizer-boundary'
            at_utc = '2026-08-22T00:00:00Z'
            checkpoint_verification = [ordered]@{
                schema_version = 'airi.behavior-checkpoint-verification.v1'
                checkpoint_relative_path = $generation
                checkpoint_manifest_sha256 = $manifestHash
                checkpoint_payload_sha256 = $payloadHash
                checkpoint_payload_bytes = 14
                canonical_pins_sha256 = $pinsHash
            }
        }
        checkpoint = [ordered]@{
            relative_path = $generation
            manifest_sha256 = $manifestHash
        }
        progress = [ordered]@{
            optimizer_steps = 1
            microsteps_completed = 16
            pending_microbatches = 0
        }
        trainer = $null
        inputs = [ordered]@{
            dataset_sha256 = 'd' * 64
            model_weight_sha256 = 'e' * 64
            input_manifest_path = 'C:\\offline-input-manifest.json'
            input_manifest_sha256 = '1' * 64
            input_manifest_training_config_sha256 = '2' * 64
            trainer_source_sha256 = 'f' * 64
            checkpoint_helper_source_sha256 = '3' * 64
        }
        command = [ordered]@{}
        heartbeat = [ordered]@{}
        logs = [ordered]@{}
        outputs = [ordered]@{ adapter = $null; report = $null }
    }
    if ([string]$state.inputs.checkpoint_helper_source_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'Manual paused-safe fixture omitted a valid checkpoint helper source pin'
    }
    $terminalTrainer = Start-ContractSleeper -Seconds 2
    Start-Sleep -Milliseconds 200
    $terminalTrainerRecord = Get-ContractProcessRecord $terminalTrainer.Id
    $state.trainer = $terminalTrainerRecord
    [IO.File]::WriteAllText(
        (Join-Path $controlDir 'pause.request.json'),
        (($request | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText(
        (Join-Path $controlDir 'pause.ack.json'),
        (($ack | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText(
        (Join-Path $runDir 'run-state.json'),
        (($state | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))

    $liveRunner = Start-ContractSleeper -Seconds 30
    try {
        Start-Sleep -Milliseconds 200
        $state.runner = Get-ContractProcessRecord $liveRunner.Id
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
        $timeoutResult = Invoke-ManualRunDirPause -RunDir $runDir -TimeoutSeconds 2
        if ($timeoutResult.exit_code -eq 0 -or (Test-ContainsSafePowerOffMarker $timeoutResult.output)) {
            throw 'Already-paused-safe receipt emitted SAFE_TO_POWER_OFF while its exact runner remained live'
        }
    }
    finally {
        if (Get-Process -Id $liveRunner.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $liveRunner.Id -Force }
    }

    $timeoutRunner = Start-ContractSleeper -Seconds 30
    try {
        Start-Sleep -Milliseconds 200
        $state.runner = Get-ContractProcessRecord $timeoutRunner.Id
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
        $stopwatch = [Diagnostics.Stopwatch]::StartNew()
        $overrunResult = Invoke-ManualRunDirPause -RunDir $runDir -TimeoutSeconds 1 -PollSeconds 15
        $stopwatch.Stop()
        if ($overrunResult.exit_code -eq 0 -or (Test-ContainsSafePowerOffMarker $overrunResult.output) -or
            $stopwatch.Elapsed.TotalSeconds -gt 5) {
            throw 'Safe-pause timeout exceeded its global deadline when PollSeconds exceeded TimeoutSeconds'
        }
    }
    finally {
        if (Get-Process -Id $timeoutRunner.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $timeoutRunner.Id -Force }
    }

    $exitingRunner = Start-ContractSleeper -Seconds 2
    try {
        Start-Sleep -Milliseconds 200
        $state.runner = Get-ContractProcessRecord $exitingRunner.Id
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
        Wait-ContractProcessExit $exitingRunner.Id
        $result = Invoke-ManualRunDirPause -RunDir $runDir
        if ($result.exit_code -eq 0 -or (Test-ContainsSafePowerOffMarker $result.output) -or
            $result.output -notmatch 'Already-paused terminal cannot authorize') {
            throw "Already-paused-safe synthetic receipt bypassed live-observation authority: $($result.output)"
        }
        $originalPinsReceipt = $state.terminal.checkpoint_verification.canonical_pins_sha256
        $state.terminal.checkpoint_verification.canonical_pins_sha256 = '0' * 64
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
        $tamperedPinsReceipt = Invoke-ManualRunDirPause -RunDir $runDir
        if ($tamperedPinsReceipt.exit_code -eq 0 -or
            (Test-ContainsSafePowerOffMarker $tamperedPinsReceipt.output) -or
            $tamperedPinsReceipt.output -notmatch 'Already-paused terminal cannot authorize') {
            throw 'A mutated canonical pins receipt bypassed already-paused provenance denial'
        }
        $state.terminal.checkpoint_verification.canonical_pins_sha256 = $originalPinsReceipt
        $originalPayloadReceipt = $state.terminal.checkpoint_verification.checkpoint_payload_sha256
        $state.terminal.checkpoint_verification.checkpoint_payload_sha256 = '0' * 64
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
        $tamperedReceipt = Invoke-ManualRunDirPause -RunDir $runDir
        if ($tamperedReceipt.exit_code -eq 0 -or
            (Test-ContainsSafePowerOffMarker $tamperedReceipt.output) -or
            $tamperedReceipt.output -notmatch 'Already-paused terminal cannot authorize') {
            throw 'A mutated authoritative checkpoint receipt bypassed already-paused provenance denial'
        }
        $state.terminal.checkpoint_verification.checkpoint_payload_sha256 = $originalPayloadReceipt
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.prev.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'), '{"torn":' + "`n",
            [Text.UTF8Encoding]::new($false))
        $stalePrevious = Invoke-ManualRunDirPause -RunDir $runDir
        if ($stalePrevious.exit_code -eq 0 -or
            (Test-ContainsSafePowerOffMarker $stalePrevious.output) -or
            $stalePrevious.output -notmatch 'An unanchored or terminal previous run-state cannot authorize power-off') {
            throw 'An unanchored terminal predecessor authorized power-off while current was invalid'
        }
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        Remove-Item -LiteralPath (Join-Path $runDir 'run-state.prev.json') -Force
    }
    finally {
        if (Get-Process -Id $exitingRunner.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $exitingRunner.Id -Force }
    }

    $exitedRunner = Start-ContractSleeper -Seconds 2
    $replacedTrainer = Start-ContractSleeper -Seconds 30
    try {
        Start-Sleep -Milliseconds 200
        $state.runner = Get-ContractProcessRecord $exitedRunner.Id
        $state.trainer = Get-ContractProcessRecord $replacedTrainer.Id
        $state.trainer.command_line_sha256 = '0' * 64
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
        Wait-ContractProcessExit $exitedRunner.Id
        $replacedTrainerResult = Invoke-ManualRunDirPause -RunDir $runDir
        if ($replacedTrainerResult.exit_code -eq 0 -or
            (Test-ContainsSafePowerOffMarker $replacedTrainerResult.output) -or
            $replacedTrainerResult.output -notmatch 'Already-paused terminal cannot authorize') {
            throw 'A replaced trainer identity bypassed the paused-safe provenance gate after exact runner exit'
        }
    }
    finally {
        if (Get-Process -Id $exitedRunner.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $exitedRunner.Id -Force }
        if (Get-Process -Id $replacedTrainer.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $replacedTrainer.Id -Force }
        $state.trainer = $terminalTrainerRecord
    }

    $spoofedRunner = Start-ContractSleeper -Seconds 12
    try {
        Start-Sleep -Milliseconds 200
        $state.runner = Get-ContractProcessRecord $spoofedRunner.Id
        $state.runner.command_line_sha256 = '0' * 64
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 10) + "`n"), [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
        $spoofedResult = Invoke-ManualRunDirPause -RunDir $runDir
        if ($spoofedResult.exit_code -eq 0 -or (Test-ContainsSafePowerOffMarker $spoofedResult.output) -or
            $spoofedResult.output -notmatch 'Already-paused terminal cannot authorize') {
            throw 'A live PID with a spoofed/reused runner identity bypassed the paused-safe provenance gate'
        }
    }
    finally {
        if (Get-Process -Id $spoofedRunner.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $spoofedRunner.Id -Force }
    }

    $forgedPausedRunner = Start-ContractSleeper -Seconds 15
    $forgedPausedTrainer = Start-ContractSleeper -Seconds 15
    try {
        Start-Sleep -Milliseconds 200
        $predecessorState = (($state | ConvertTo-Json -Compress -Depth 20) | ConvertFrom-Json)
        $predecessorState.revision = [int]$state.revision - 1
        $predecessorState.status = 'running'
        $predecessorState.terminal = $null
        $predecessorState.runner = Get-ContractProcessRecord $forgedPausedRunner.Id
        $predecessorState.trainer = Get-ContractProcessRecord $forgedPausedTrainer.Id
        $forgedPausedState = (($state | ConvertTo-Json -Compress -Depth 20) | ConvertFrom-Json)
        $forgedPausedState.runner = Get-ContractProcessRecord $forgedPausedRunner.Id
        $forgedPausedState.trainer = Get-ContractProcessRecord $forgedPausedTrainer.Id
        $forgedPausedState.runner.pid = 2147483646
        $forgedPausedState.trainer.pid = 2147483645
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.prev.json'),
            (($predecessorState | ConvertTo-Json -Compress -Depth 20) + "`n"),
            [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText(
        (Join-Path $runDir 'run-state.json'),
        (($forgedPausedState | ConvertTo-Json -Compress -Depth 20) + "`n"),
            [Text.UTF8Encoding]::new($false))
        Write-ContractRunStateAnchor -StatePath (Join-Path $runDir 'run-state.json')
        $forgedPausedResult = Invoke-ManualRunDirPause -RunDir $runDir -TimeoutSeconds 2
        if ($forgedPausedResult.exit_code -eq 0 -or
            (Test-ContainsSafePowerOffMarker $forgedPausedResult.output) -or
            $forgedPausedResult.output -notmatch 'Already-paused terminal cannot authorize') {
            throw 'Full forged paused-safe receipt with absent PIDs bypassed live-observation authority'
        }
    }
    finally {
        if (Get-Process -Id $forgedPausedRunner.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $forgedPausedRunner.Id -Force }
        if (Get-Process -Id $forgedPausedTrainer.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $forgedPausedTrainer.Id -Force }
    }
    [IO.File]::WriteAllText(
        (Join-Path $runDir 'run-state.json'),
        (($state | ConvertTo-Json -Compress -Depth 20) + "`n"),
        [Text.UTF8Encoding]::new($false))
    Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')

    $cutpointRunner = Start-ContractSleeper -Seconds 8
    $cutpointTrainer = Start-ContractSleeper -Seconds 8
    $cutpointJob = $null
    try {
        Start-Sleep -Milliseconds 200
        $state.runner = Get-ContractProcessRecord $cutpointRunner.Id
        $state.trainer = Get-ContractProcessRecord $cutpointTrainer.Id
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 20) + "`n"),
            [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
        $cutpointJob = Start-Job -ScriptBlock {
            param($PausePath, $RunDir)
            $savedPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = 'Continue'
                $output = @(& powershell -NoProfile -ExecutionPolicy Bypass -File $PausePath `
                    -RunDir $RunDir -TimeoutSeconds 3 -PollSeconds 1 2>&1)
                [pscustomobject]@{ exit_code = $LASTEXITCODE; output = ($output -join "`n") }
            }
            finally {
                $ErrorActionPreference = $savedPreference
            }
        } -ArgumentList $pausePath, $runDir
        $cutpointJobDeadline = [DateTime]::UtcNow.AddSeconds(5)
        do {
            Start-Sleep -Milliseconds 50
        } while ($cutpointJob.State -eq 'NotStarted' -and [DateTime]::UtcNow -lt $cutpointJobDeadline)
        if ($cutpointJob.State -ne 'Running') {
            throw 'Higher-revision competitor pause job did not remain running before mutation'
        }
        $cutpointCurrentPath = Join-Path $runDir 'run-state.json'
        $cutpointCompetitor = Get-Content -LiteralPath $cutpointCurrentPath -Raw -Encoding utf8 | ConvertFrom-Json
        $cutpointCompetitor.revision = [int]$cutpointCompetitor.revision + 1
        $cutpointCompetitor.runner.command_line_sha256 = '0' * 64
        [IO.File]::WriteAllText(
            $cutpointCurrentPath, (($cutpointCompetitor | ConvertTo-Json -Compress -Depth 20) + "`n"),
            [Text.UTF8Encoding]::new($false))
        $cutpointResult = Receive-Job -Job $cutpointJob -Wait -AutoRemoveJob
        $cutpointJob = $null
        if ($cutpointResult.exit_code -eq 0 -or
            (Test-ContainsSafePowerOffMarker $cutpointResult.output) -or
            $cutpointResult.output -notmatch 'An unanchored or terminal previous run-state cannot authorize power-off') {
            throw 'A live higher-revision competitor bypassed anchor authority'
        }
    }
    finally {
        if ($null -ne $cutpointJob) {
            Wait-Job -Job $cutpointJob -Timeout 5 | Out-Null
            Remove-Job -Job $cutpointJob -Force -ErrorAction SilentlyContinue
        }
        if (Get-Process -Id $cutpointRunner.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $cutpointRunner.Id -Force }
        if (Get-Process -Id $cutpointTrainer.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $cutpointTrainer.Id -Force }
        $state.runner = [ordered]@{
            pid = 2147483647
            creation_time_utc = '2026-08-22T00:00:00Z'
            executable_path_sha256 = 'a' * 64
            command_line_sha256 = 'b' * 64
        }
        $state.trainer = $terminalTrainerRecord
        [IO.File]::WriteAllText(
            (Join-Path $runDir 'run-state.json'),
            (($state | ConvertTo-Json -Compress -Depth 20) + "`n"),
            [Text.UTF8Encoding]::new($false))
        Write-ContractTerminalPredecessor $state (Join-Path $runDir 'run-state.json')
    }

    $priorTestHooks = [Environment]::GetEnvironmentVariable('AIRI_DURABILITY_TEST_HOOKS', 'Process')
    try {
        $env:AIRI_DURABILITY_TEST_HOOKS = '1'
        $expiredPausedGate = Invoke-ManualRunDirPause `
            -RunDir $runDir -TimeoutSeconds 1 -PollSeconds 1 `
            -TestOnlyFinalGateDelayMilliseconds 1500
        if ($expiredPausedGate.exit_code -eq 0 -or
            (Test-ContainsSafePowerOffMarker $expiredPausedGate.output) -or
            $expiredPausedGate.output -notmatch 'Already-paused terminal cannot authorize') {
            throw 'Already-paused terminal bypassed provenance during delayed final gate'
        }
    }
    finally {
        if ($null -eq $priorTestHooks) { Remove-Item Env:AIRI_DURABILITY_TEST_HOOKS -ErrorAction SilentlyContinue }
        else { $env:AIRI_DURABILITY_TEST_HOOKS = $priorTestHooks }
    }

    $malformedAck = [ordered]@{}
    foreach ($property in $ack.GetEnumerator()) {
        $malformedAck[$property.Key] = $property.Value
    }
    $malformedAck['unexpected'] = 'must-fail'
    [IO.File]::WriteAllText(
        (Join-Path $controlDir 'pause.ack.json'),
        (($malformedAck | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))
    $malformedAckRejected = $false
    try {
        & $pausePath -RunDir $runDir | Out-Null
    }
    catch {
        if ($_.Exception.Message -match 'Already-paused terminal cannot authorize') {
            $malformedAckRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $malformedAckRejected) {
        throw 'Malformed already-paused ack schema was accepted'
    }
    [IO.File]::WriteAllText(
        (Join-Path $controlDir 'pause.ack.json'),
        (($ack | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))

    $launcherCase = Join-Path $temporaryRoot 'launcher-case'
    [IO.Directory]::CreateDirectory($launcherCase) | Out-Null
    $fakeTrainer = Join-Path $launcherCase 'fake trainer.py'
    $fakeSource = @'
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument("--run-dir", type=Path, required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--dataset-sha256", required=True)
parser.add_argument("--model-sha256", required=True)
parser.add_argument("--inject-terminal", action="store_true")
parser.add_argument("--prime-process-records", type=Path)
args, _ = parser.parse_known_args()
def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
def artifact_receipt(path):
    if path.is_file():
        raw = path.read_bytes()
        return {"path": str(path.resolve()), "kind": "file", "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}
    rows = [{"path": item.relative_to(path).as_posix(), "size": item.stat().st_size,
             "sha256": hashlib.sha256(item.read_bytes()).hexdigest()}
            for item in sorted(path.rglob("*")) if item.is_file()]
    return {"path": str(path.resolve()), "kind": "directory", "files": rows,
            "manifest_sha256": hashlib.sha256(canonical(rows)).hexdigest()}
def publish_adapter_artifact():
    args.output.mkdir(parents=True, exist_ok=True)
    adapter_path = args.output / "adapter.bin"
    adapter_path.write_bytes(b"adapter")
    adapter_raw = adapter_path.read_bytes()
    pins = {"dataset_sha256": args.dataset_sha256,
            "model_weight_sha256": args.model_sha256,
            "trainer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    manifest = {
        "schema_version": "airi.behavior-adapter-artifact.v1",
        "run_id": args.run_id,
        "pins": pins,
        "files": [{"path": "adapter.bin", "bytes": len(adapter_raw),
                   "sha256": hashlib.sha256(adapter_raw).hexdigest()}],
    }
    manifest_path = args.output / "artifact-manifest.json"
    manifest_path.write_bytes(canonical(manifest))
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()
if args.inject_terminal:
    # Create the synthetic terminal artifacts before the long fault window.
    # Windows venv launch shims can outlive or underlive their child; the
    # runner must never mistake shim timing for missing final test artifacts.
    publish_adapter_artifact()
    args.report.write_text("{}\n", encoding="utf-8")
    injection_deadline = time.monotonic() + 8.0
    state_path = args.run_dir / "run-state.json"
    anchor_path = args.run_dir / "run-state.anchor.json"
    forged_gate = args.run_dir / "forged-complete-live.gate"
    forged_gate.write_text("live\n", encoding="utf-8")
    prime_records = (json.loads(args.prime_process_records.read_text(encoding="utf-8"))
                     if args.prime_process_records else None)
    prime_deadline = None
    actual_live_state_bytes = None
    while time.monotonic() < injection_deadline:
        try:
            state_raw = state_path.read_bytes()
            state = json.loads(state_raw.decode("utf-8"))
            if not isinstance(state.get("runner"), dict) or not isinstance(state.get("trainer"), dict):
                time.sleep(0.02)
                continue
            if actual_live_state_bytes is None:
                anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
                if (int(state.get("revision", -1)) < 2
                        or int(anchor["current"]["revision"]) != int(state["revision"])
                        or anchor["current"]["sha256"] != hashlib.sha256(state_raw).hexdigest()):
                    time.sleep(0.02)
                    continue
                actual_live_state_bytes = state_raw
                prime_deadline = time.monotonic() + 0.8
                injection_deadline = time.monotonic() + 2.0
            if prime_records and time.monotonic() < prime_deadline:
                state["revision"] = int(state.get("revision", 0)) + 1
                state["status"] = "running"
                state["runner"] = prime_records["runner"]
                state["trainer"] = prime_records["trainer"]
                state["terminal"] = None
                temporary = state_path.with_name(".primed-live.tmp")
                temporary.write_text(
                    json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8")
                temporary.replace(state_path)
                (args.run_dir / "unrelated-live-prime-observed.txt").write_text(
                    "live\n", encoding="utf-8")
                time.sleep(0.02)
                continue
            state["revision"] = int(state.get("revision", 0)) + 100
            state["status"] = "complete"
            if prime_records:
                state["runner"] = prime_records["runner"]
                state["trainer"] = prime_records["trainer"]
            state["runner"]["pid"] = 2147483646
            state["trainer"]["pid"] = 2147483645
            state["outputs"] = {
                "adapter": artifact_receipt(args.output),
                "report": artifact_receipt(args.report),
            }
            # This is schema-valid and carries the requested bindings already
            # published by the runner, but substitutes absent identities while
            # the real runner and trainer remain live.
            forged_at = datetime.now(timezone.utc).isoformat()
            state["terminal"] = {
                "exit_code": 0,
                "reason": "trainer-complete",
                "at_utc": forged_at,
                "final_evidence_root": {
                    "relative_path": "final-evidence-root.json",
                    "sha256": "f" * 64,
                    "state_projection_sha256": "e" * 64,
                },
            }
            temporary = state_path.with_name(".injected-terminal.tmp")
            temporary.write_text(
                json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8")
            temporary.replace(state_path)
            (args.run_dir / "forged-complete-observed.txt").write_text(
                forged_at, encoding="utf-8")
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(0.02)
    forged_gate.unlink(missing_ok=True)
    if prime_records and actual_live_state_bytes:
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
        if (anchor["current"]["sha256"] != hashlib.sha256(actual_live_state_bytes).hexdigest()
                or int(anchor["current"]["revision"])
                != int(json.loads(actual_live_state_bytes.decode("utf-8"))["revision"])):
            raise RuntimeError("captured live state is no longer anchor-authorized")
        temporary = state_path.with_name(".actual-live-after-forgery.tmp")
        temporary.write_bytes(actual_live_state_bytes)
        temporary.replace(state_path)
        (args.run_dir / "anchor-authorized-live-restore-observed.txt").write_text(
            hashlib.sha256(actual_live_state_bytes).hexdigest(), encoding="utf-8")
        # Give launcher polling an actual, provenance-bound state before this
        # trainer exits and the runner publishes the real terminal receipt.
        time.sleep(0.8)
else:
    # Keep the synthetic trainer live across several 500 ms launcher polls so
    # exact runner/trainer provenance is observed before terminal publication.
    time.sleep(2.0)
adapter_artifact_manifest_sha256 = publish_adapter_artifact()
args.report.write_text("{}\n", encoding="utf-8")
generation = "checkpoint-00000001"
checkpoint_dir = args.run_dir / "checkpoints" / generation
checkpoint_dir.mkdir(parents=True, exist_ok=True)
payload = b"complete-transactional-checkpoint"
(checkpoint_dir / "state.pt").write_bytes(payload)
pins = {"dataset_sha256": args.dataset_sha256,
        "model_weight_sha256": args.model_sha256,
        "trainer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
manifest = {"schema_version": 1, "generation": generation, "run_id": args.run_id,
            "payload": {"name": "state.pt", "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()}, "pins": pins}
manifest_bytes = canonical(manifest)
(checkpoint_dir / "manifest.json").write_bytes(manifest_bytes)
reference = {"relative_path": generation,
             "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
             "event_relative_path": "checkpoint-events/" + generation + ".json"}
now = datetime.now(timezone.utc).isoformat()
event = {"schema_version": "airi.behavior-checkpoint-event.v2", "run_id": args.run_id,
         "generation": generation, "reason": "epoch-complete", "microsteps_completed": 2,
         "optimizer_steps": 1, "pending_microbatches": 0, "training_elapsed_ns": 1,
         "checkpoint_payload_progress": {"microsteps_completed": 2, "optimizer_steps": 1,
                                         "pending_microbatches": 0},
         "checkpoint_manifest_sha256": reference["manifest_sha256"],
         "checkpoint_payload_sha256": hashlib.sha256(payload).hexdigest(),
         "pins_sha256": hashlib.sha256(canonical(pins)).hexdigest(),
         "previous_event_sha256": None, "previous_index_sha256": None,
         "publish_started_at_utc": now, "checkpoint_durable_at_utc": now,
         "publish_elapsed_ns": 0}
event_bytes = canonical(event)
event_path = args.run_dir / reference["event_relative_path"]
event_path.parent.mkdir(parents=True, exist_ok=True)
event_path.write_bytes(event_bytes)
reference["event_sha256"] = hashlib.sha256(event_bytes).hexdigest()
index = {"schema_version": "airi.behavior-checkpoint-index.v2", "run_id": args.run_id,
         "latest": reference, "previous": None, "previous_index_sha256": None}
index_bytes = canonical(index)
(args.run_dir / "checkpoints" / "checkpoint-index.json").write_bytes(index_bytes)
progress = {
    "schema_version": "airi.behavior-training-progress.v2",
    "run_id": args.run_id, "status": "completed", "epoch": 1,
    "next_batch_index": 0, "microsteps_completed": 2,
    "optimizer_steps": 1, "pending_microbatches": 0,
    "checkpoint": {"relative_path": generation, "manifest_sha256": reference["manifest_sha256"]},
    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    "training_elapsed_ns": 1,
}
progress_bytes = canonical(progress)
(args.run_dir / "progress.json").write_bytes(progress_bytes)
producer = {"schema_version": "airi.behavior-producer-evidence-root.v1", "run_id": args.run_id,
            "checkpoint_index_sha256": hashlib.sha256(index_bytes).hexdigest(),
            "latest_checkpoint": reference,
            "adapter_artifact_manifest_sha256": adapter_artifact_manifest_sha256,
            "report_sha256": artifact_receipt(args.report)["sha256"],
            "progress": {"microsteps_completed": 2, "optimizer_steps": 1,
                         "pending_microbatches": 0, "training_elapsed_ns": 1}}
(args.run_dir / "producer-evidence-root.json").write_bytes(canonical(producer))
'@
    [IO.File]::WriteAllText($fakeTrainer, $fakeSource, [Text.UTF8Encoding]::new($false))
    Copy-Item -LiteralPath (Join-Path $root 'ollama-proxy\training\behavior_training_checkpoint.py') `
        -Destination (Join-Path $launcherCase 'behavior_training_checkpoint.py') -Force
    $launcherDataset = Join-Path $launcherCase 'dataset.jsonl'
    $launcherModel = Join-Path $launcherCase 'model'
    [IO.File]::WriteAllText(
        $launcherDataset, "{}$([Environment]::NewLine)",
        [Text.UTF8Encoding]::new($false))
    [IO.Directory]::CreateDirectory($launcherModel) | Out-Null
    [IO.File]::WriteAllText(
        (Join-Path $launcherModel 'config.json'), "{}$([Environment]::NewLine)",
        [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllBytes(
        (Join-Path $launcherModel 'model.safetensors'), [Text.Encoding]::ASCII.GetBytes('fixture-model-weight'))
    $launcherRun = Join-Path $launcherCase 'run with spaces'
    $launcherOutput = Join-Path $launcherCase 'adapter output'
    $launcherReport = Join-Path $launcherCase 'report output.json'
    $launcherInputManifest = Join-Path $launcherCase 'input-manifest.json'
    $launcherDatasetSha256 = (Get-FileHash -LiteralPath $launcherDataset -Algorithm SHA256).Hash.ToLowerInvariant()
    $launcherModelSha256 = (Get-FileHash -LiteralPath (Join-Path $launcherModel 'model.safetensors') -Algorithm SHA256).Hash.ToLowerInvariant()
    $launcherInputManifestSha256 = New-ContractInputManifest `
        $launcherInputManifest $fakeTrainer $launcherDataset $launcherModel 5
    $spoofSourceDir = Join-Path $temporaryRoot 'spoof-source'
    $spoofRunDir = Join-Path $temporaryRoot 'spoof-run'
    [IO.Directory]::CreateDirectory($spoofSourceDir) | Out-Null
    [IO.Directory]::CreateDirectory($spoofRunDir) | Out-Null
    $spoofRunnerPath = Join-Path $spoofSourceDir 'durable_training_runner.py'
    [IO.File]::WriteAllText(
        $spoofRunnerPath, "import time`ntime.sleep(20)`n", [Text.UTF8Encoding]::new($false))
    $spoofProcess = Start-Process -FilePath $pythonPath -ArgumentList @(
        $spoofRunnerPath, '--run-dir', $spoofRunDir, '--run-id', 'spoof-run') `
        -WindowStyle Hidden -PassThru
    try {
        Start-Sleep -Milliseconds 200
        $spoofRunnerRecord = Get-ContractProcessRecord $spoofProcess.Id
        # Everything except the persisted process identity is plausible.  Discovery
        # must reject this live same-name/source-bound process rather than trusting argv.
        $spoofRunnerRecord.command_line_sha256 = '0' * 64
        $spoofState = [ordered]@{
            schema_version = 'airi.behavior-durable-run.v1'
            revision = 0
            run_id = 'spoof-run'
            status = 'running'
            created_at_utc = '2026-08-22T00:00:00Z'
            updated_at_utc = '2026-08-22T00:00:00Z'
            runner = $spoofRunnerRecord
            trainer = $null
            inputs = [ordered]@{}
            command = [ordered]@{
                canonical_sha256 = '1' * 64
                runner_source_sha256 = (
                    Get-FileHash -LiteralPath $spoofRunnerPath -Algorithm SHA256
                ).Hash.ToLowerInvariant()
                trainer_source_sha256 = '2' * 64
            }
            progress = [ordered]@{}
            heartbeat = [ordered]@{}
            checkpoint = $null
            logs = [ordered]@{}
            outputs = [ordered]@{}
            terminal = $null
        }
        [IO.File]::WriteAllText(
            (Join-Path $spoofRunDir 'run-state.json'),
            (($spoofState | ConvertTo-Json -Compress -Depth 10) + "`n"),
            [Text.UTF8Encoding]::new($false))
        $spoofResult = Invoke-OmittedRunDirPause
        if ($spoofResult.exit_code -eq 0 -or
            (Test-ContainsSafePowerOffMarker $spoofResult.output)) {
            throw 'Omitted RunDir accepted a runner whose persisted process identity was spoofed'
        }
    }
    finally {
        if (-not $spoofProcess.HasExited) { Stop-Process -Id $spoofProcess.Id -Force }
    }
    $launcherTrainerArguments = @(
        '--dataset', $launcherDataset, '--dataset-sha256', $launcherDatasetSha256,
        '--model-dir', $launcherModel, '--model-sha256', $launcherModelSha256,
        '--output', $launcherOutput, '--report', $launcherReport) + $contractTrainingArguments
    try {
        $launchReceipt = & $launcherPath `
            -RunDir $launcherRun `
            -RunId 'launcher-contract' `
            -PythonPath $pythonPath `
            -TrainerPath $fakeTrainer `
            -WorkingDirectory $launcherCase `
            -InputManifestPath $launcherInputManifest `
            -InputManifestSha256 $launcherInputManifestSha256 `
            -CheckpointEveryOptimizerSteps 5 `
            -HeartbeatSeconds 15 `
            -TrainerArguments $launcherTrainerArguments
    }
    catch {
        Write-InitialLaunchFailureReceipt $_
        throw
    }
    if ([string]$launchReceipt.run_id -ne 'launcher-contract' -or
        [int]$launchReceipt.runner_pid -le 0) {
        throw 'Durable launcher did not return its PID/run-state receipt'
    }
    # An already-running receipt is only reusable for the exact requested
    # manifest and trainer command; a byte-identical manifest at another path
    # must not be silently rebound.
    $alternateManifest = Join-Path $launcherCase 'alternate-input-manifest.json'
    [IO.File]::WriteAllBytes($alternateManifest, [IO.File]::ReadAllBytes($launcherInputManifest))
    $alternateManifestSha256 = (Get-FileHash -LiteralPath $alternateManifest -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifestBindingRejected = $false
    try {
        & $launcherPath `
            -RunDir $launcherRun `
            -RunId 'launcher-contract' `
            -PythonPath $pythonPath `
            -TrainerPath $fakeTrainer `
            -WorkingDirectory $launcherCase `
            -InputManifestPath $alternateManifest `
            -InputManifestSha256 $alternateManifestSha256 `
            -CheckpointEveryOptimizerSteps 5 `
            -HeartbeatSeconds 1 `
            -TrainerArguments $launcherTrainerArguments | Out-Null
    }
    catch {
        if ($_.Exception.Message -match 'Recorded live runner inputs or trainer command differ') {
            $manifestBindingRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $manifestBindingRejected) {
        throw 'Already-running launcher accepted a mismatched requested manifest binding'
    }
    $launcherStatePath = Join-Path $launcherRun 'run-state.json'
    $unanchoredCompetitor = Get-Content -LiteralPath $launcherStatePath -Raw -Encoding utf8 | ConvertFrom-Json
    $unanchoredCompetitor.revision = [int]$unanchoredCompetitor.revision + 1000
    $unanchoredCompetitor.updated_at_utc = [DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText(
        $launcherStatePath,
        (($unanchoredCompetitor | ConvertTo-Json -Compress -Depth 20) + "`n"),
        [Text.UTF8Encoding]::new($false))
    $unanchoredExistingRejected = $false
    try {
        & $launcherPath `
            -RunDir $launcherRun `
            -RunId 'launcher-contract' `
            -PythonPath $pythonPath `
            -TrainerPath $fakeTrainer `
            -WorkingDirectory $launcherCase `
            -InputManifestPath $launcherInputManifest `
            -InputManifestSha256 $launcherInputManifestSha256 `
            -CheckpointEveryOptimizerSteps 5 `
            -HeartbeatSeconds 1 `
            -TrainerArguments $launcherTrainerArguments | Out-Null
    }
    catch {
        if ($_.Exception.Message -match 'No anchor-authorized current or previous run-state receipt is available') {
            $unanchoredExistingRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $unanchoredExistingRejected) {
        throw 'Unanchored higher-revision competitor returned an already-running receipt'
    }
    $launcherDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        $launcherState = Get-Content -LiteralPath $launcherStatePath -Raw -Encoding utf8 | ConvertFrom-Json
        if ([string]$launcherState.status -eq 'complete') {
            break
        }
        if ([string]$launcherState.status -in @('failed', 'interrupted')) {
            throw "Durable launcher integration ended as $($launcherState.status)"
        }
    } while ([DateTime]::UtcNow -lt $launcherDeadline)
    if ([string]$launcherState.status -ne 'complete' -or
        [int]$launcherState.terminal.exit_code -ne 0 -or
        -not (Test-Path -LiteralPath $launcherOutput -PathType Container) -or
        -not (Test-Path -LiteralPath $launcherReport -PathType Leaf)) {
        throw 'Durable launcher did not persist a complete terminal artifact receipt'
    }
    $completeControl = Join-Path $launcherRun 'control'
    [IO.Directory]::CreateDirectory($completeControl) | Out-Null
    $latePauseRequest = [ordered]@{
        schema_version = 'airi.behavior-pause-request.v1'
        run_id = 'launcher-contract'
        request_id = 'arrived-after-final-checkpoint'
    }
    [IO.File]::WriteAllText(
        (Join-Path $completeControl 'pause.request.json'),
        (($latePauseRequest | ConvertTo-Json -Compress) + "`n"),
        [Text.UTF8Encoding]::new($false))
    $priorTestHooks = [Environment]::GetEnvironmentVariable('AIRI_DURABILITY_TEST_HOOKS', 'Process')
    try {
        $env:AIRI_DURABILITY_TEST_HOOKS = '1'
        $expiredCompleteGate = Invoke-ManualRunDirPause `
            -RunDir $launcherRun -TimeoutSeconds 1 -PollSeconds 1 `
            -TestOnlyFinalGateDelayMilliseconds 1500
        $deadlineExitSucceeded = $expiredCompleteGate.exit_code -eq 0
        $deadlineMarkerObserved = Test-ContainsSafePowerOffMarker $expiredCompleteGate.output
        $deadlineTextObserved = $expiredCompleteGate.output -match 'deadline expired'
        if ($deadlineExitSucceeded -or $deadlineMarkerObserved -or -not $deadlineTextObserved) {
            throw ('Final completion deadline gate failed: exit_success=' + $deadlineExitSucceeded +
                '; exact_marker=' + $deadlineMarkerObserved +
                '; deadline_text=' + $deadlineTextObserved)
        }
    }
    finally {
        if ($null -eq $priorTestHooks) { Remove-Item Env:AIRI_DURABILITY_TEST_HOOKS -ErrorAction SilentlyContinue }
        else { $env:AIRI_DURABILITY_TEST_HOOKS = $priorTestHooks }
    }
    # This parent-scope decoy must not affect the child PowerShell verifier;
    # Assert-VerifiedArtifactReceipt now derives its directory root directly
    # from the exact receipt before either artifact branch uses it.
    $path = Join-Path $temporaryRoot 'caller-scope-directory-decoy'
    $completeSafe = & $pausePath -RunDir $launcherRun -TimeoutSeconds 30 -PollSeconds 1
    if (-not ($completeSafe -contains 'SAFE_TO_POWER_OFF')) {
        throw 'Durably completed run was not accepted as safe to power off'
    }
    Remove-Item -LiteralPath $launcherReport -Force
    $missingFinalReport = Invoke-ManualRunDirPause -RunDir $launcherRun -TimeoutSeconds 5
    $missingReportExitSucceeded = $missingFinalReport.exit_code -eq 0
    $missingReportMarkerObserved = Test-ContainsSafePowerOffMarker $missingFinalReport.output
    $missingReportArtifactError = $missingFinalReport.output -match 'completed file artifact'
    if ($missingReportExitSucceeded -or $missingReportMarkerObserved -or -not $missingReportArtifactError) {
        throw ('Disappeared report gate failed: exit_success=' + $missingReportExitSucceeded +
            '; exact_marker=' + $missingReportMarkerObserved +
            '; completed_file_artifact_error=' + $missingReportArtifactError)
    }

    $injectedRun = Join-Path $launcherCase 'terminal-injection-run'
    $injectedOutput = Join-Path $launcherCase 'terminal-injection-adapter'
    $injectedReport = Join-Path $launcherCase 'terminal-injection-report.json'
    $unrelatedRunner = Start-ContractSleeper -Seconds 15
    $unrelatedTrainer = Start-ContractSleeper -Seconds 15
    $primeRecordsPath = Join-Path $launcherCase 'unrelated-live-prime.json'
    Start-Sleep -Milliseconds 200
    [IO.File]::WriteAllText(
        $primeRecordsPath,
        (([ordered]@{
                    runner = Get-ContractProcessRecord $unrelatedRunner.Id
                    trainer = Get-ContractProcessRecord $unrelatedTrainer.Id
                } | ConvertTo-Json -Compress -Depth 10) + "`n"),
        [Text.UTF8Encoding]::new($false))
    $injectedArguments = @(
        '--dataset', $launcherDataset, '--dataset-sha256', $launcherDatasetSha256,
        '--model-dir', $launcherModel, '--model-sha256', $launcherModelSha256,
        '--output', $injectedOutput, '--report', $injectedReport,
        '--inject-terminal', '--prime-process-records', $primeRecordsPath) + $contractTrainingArguments
    $injectedArgumentsJson = ConvertTo-Json -InputObject ([object[]]$injectedArguments) -Compress
    # Keep the supervisor from publishing a legitimate heartbeat over the
    # forged terminal during the two-second fault window.  Launch in a job so
    # the fault is observed while the launcher invocation is still live.
    $injectedLaunchJob = $null
    $injectedLaunchReceipt = $null
    try {
        $injectedLaunchJob = Start-Job -ScriptBlock {
            param(
                $LauncherPath,
                $RunDir,
                $PythonPath,
                $TrainerPath,
                $WorkingDirectory,
                $InputManifestPath,
                $InputManifestSha256,
                [string]$TrainerArgumentsJson
            )
            [string[]]$jobTrainerArguments = @(
                (ConvertFrom-Json -InputObject $TrainerArgumentsJson) |
                    ForEach-Object { [string]$_ }
            )
            & $LauncherPath `
                -RunDir $RunDir `
                -RunId 'terminal-injection-contract' `
                -PythonPath $PythonPath `
                -TrainerPath $TrainerPath `
                -WorkingDirectory $WorkingDirectory `
                -InputManifestPath $InputManifestPath `
                -InputManifestSha256 $InputManifestSha256 `
                -CheckpointEveryOptimizerSteps 5 `
                -HeartbeatSeconds 15 `
                -TrainerArguments $jobTrainerArguments
        } -ArgumentList $launcherPath, $injectedRun, $pythonPath, $fakeTrainer, $launcherCase, `
            $launcherInputManifest, $launcherInputManifestSha256, $injectedArgumentsJson
        $forgedGate = Join-Path $injectedRun 'forged-complete-live.gate'
        $forgedGateDeadline = [DateTime]::UtcNow.AddSeconds(10)
        do {
            Start-Sleep -Milliseconds 50
            if ($injectedLaunchJob.State -ne 'Running') {
                throw 'Launcher returned before its provenance-bound trainer reached the forged-terminal gate'
            }
        } while (-not (Test-Path -LiteralPath $forgedGate -PathType Leaf) -and
                 [DateTime]::UtcNow -lt $forgedGateDeadline)
        if (-not (Test-Path -LiteralPath $forgedGate -PathType Leaf) -or
            $injectedLaunchJob.State -ne 'Running') {
            throw 'Launcher did not remain live through the forged-terminal readiness gate'
        }
        $forgedMarker = Join-Path $injectedRun 'forged-complete-observed.txt'
        $forgedDeadline = [DateTime]::UtcNow.AddSeconds(10)
        do {
            Start-Sleep -Milliseconds 50
            if ($injectedLaunchJob.State -ne 'Running') {
                throw 'Launcher returned before the forged complete terminal was observed'
            }
        } while (-not (Test-Path -LiteralPath $forgedMarker -PathType Leaf) -and
                 [DateTime]::UtcNow -lt $forgedDeadline)
        if (-not (Test-Path -LiteralPath $forgedMarker -PathType Leaf) -or
            $injectedLaunchJob.State -ne 'Running') {
            throw 'Actual-process forged complete terminal was not observed while launcher invocation remained live'
        }
        $injectedLaunchReceipt = Receive-Job -Job $injectedLaunchJob -Wait -AutoRemoveJob
        $injectedLaunchJob = $null
    }
    finally {
        if ($null -ne $injectedLaunchJob) {
            Stop-Job -Job $injectedLaunchJob -ErrorAction SilentlyContinue
            Remove-Job -Job $injectedLaunchJob -Force -ErrorAction SilentlyContinue
        }
        if (Get-Process -Id $unrelatedRunner.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $unrelatedRunner.Id -Force }
        if (Get-Process -Id $unrelatedTrainer.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $unrelatedTrainer.Id -Force }
    }
    if ([string]$injectedLaunchReceipt.run_id -ne 'terminal-injection-contract') {
        throw 'Actual-process terminal-injection launch did not publish a live receipt'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $injectedRun 'unrelated-live-prime-observed.txt') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $injectedRun 'anchor-authorized-live-restore-observed.txt') -PathType Leaf) -or
        [string]$injectedLaunchReceipt.status -eq 'complete') {
        throw 'Launcher did not reject the forged terminal and return through an anchor-authorized live receipt'
    }
    $injectedDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 200
        try {
            $injectedState = Get-Content -LiteralPath (Join-Path $injectedRun 'run-state.json') `
                -Raw -Encoding utf8 | ConvertFrom-Json
        }
        catch { continue }
        $verifiedInjectedComplete = $false
        if ([string]$injectedState.status -eq 'complete' -and $null -ne $injectedState.terminal) {
            $terminalProperties = @($injectedState.terminal.PSObject.Properties.Name)
            $adapterReceipt = $injectedState.outputs.adapter
            $reportReceipt = $injectedState.outputs.report
            $adapterProperties = if ($null -eq $adapterReceipt) {
                @()
            }
            else {
                @($adapterReceipt.PSObject.Properties.Name)
            }
            $reportProperties = if ($null -eq $reportReceipt) {
                @()
            }
            else {
                @($reportReceipt.PSObject.Properties.Name)
            }
            if ($terminalProperties -contains 'exit_code' -and
                $terminalProperties -contains 'reason') {
                $verifiedInjectedComplete = (
                    [int]$injectedState.terminal.exit_code -eq 0 -and
                    [string]$injectedState.terminal.reason -eq 'trainer-complete' -and
                    $adapterProperties -contains 'manifest_sha256' -and
                    $reportProperties -contains 'sha256' -and
                    (Test-Path -LiteralPath $injectedOutput -PathType Container) -and
                    (Test-Path -LiteralPath $injectedReport -PathType Leaf))
            }
        }
        if ($verifiedInjectedComplete -or
            [string]$injectedState.status -in @('failed', 'interrupted')) { break }
    } while ([DateTime]::UtcNow -lt $injectedDeadline)
    if (-not $verifiedInjectedComplete) {
        throw 'Strict launcher terminal-injection contract did not recover to a valid completion'
    }
    $adapterReceiptProperties = @($injectedState.outputs.adapter.PSObject.Properties.Name)
    $reportReceiptProperties = @($injectedState.outputs.report.PSObject.Properties.Name)
    if (-not ($adapterReceiptProperties -contains 'manifest_sha256') -or
        -not ($reportReceiptProperties -contains 'sha256') -or
        -not (Test-Path -LiteralPath $injectedOutput -PathType Container) -or
        -not (Test-Path -LiteralPath $injectedReport -PathType Leaf)) {
        throw 'Launcher accepted the forged complete terminal instead of waiting for terminal semantics and artifacts'
    }

    $orphanCase = Join-Path $temporaryRoot 'orphan-case'
    [IO.Directory]::CreateDirectory($orphanCase) | Out-Null
    $now = [DateTime]::UtcNow.ToString('o')
    $orphanState = [ordered]@{
        schema_version = 'airi.behavior-durable-run.v1'
        revision = 1
        run_id = 'orphan-contract'
        status = 'interrupted'
        created_at_utc = $now
        updated_at_utc = $now
        runner = [ordered]@{
            pid = 2147483647
            creation_time_utc = $now
            executable_path_sha256 = 'a' * 64
            command_line_sha256 = 'b' * 64
        }
        trainer = Get-ContractProcessRecord $PID
        inputs = [ordered]@{}
        command = [ordered]@{}
        progress = [ordered]@{
            epoch = 0; next_batch_index = 0; microsteps_completed = 0
            optimizer_steps = 0; pending_microbatches = 0
        }
        heartbeat = [ordered]@{ sequence = 1; at_utc = $now; phase = 'interrupted' }
        checkpoint = $null
        logs = [ordered]@{}
        outputs = [ordered]@{ adapter = $null; report = $null }
        terminal = [ordered]@{ exit_code = $null; reason = 'process-missing'; at_utc = $now }
    }
    [IO.File]::WriteAllText(
        (Join-Path $orphanCase 'run-state.json'),
        (($orphanState | ConvertTo-Json -Compress -Depth 10) + "`n"),
        [Text.UTF8Encoding]::new($false))
    Write-ContractRunStateAnchor -StatePath (Join-Path $orphanCase 'run-state.json')
    $orphanTrainerArguments = @(
        '--dataset', $launcherDataset, '--dataset-sha256', $launcherDatasetSha256,
        '--model-dir', $launcherModel, '--model-sha256', $launcherModelSha256,
        '--output', (Join-Path $orphanCase 'adapter'),
        '--report', (Join-Path $orphanCase 'report.json')) + $contractTrainingArguments
    $orphanRejected = $false
    try {
        & $launcherPath `
            -RunDir $orphanCase `
            -RunId 'orphan-contract' `
            -PythonPath $pythonPath `
            -TrainerPath $fakeTrainer `
            -WorkingDirectory $launcherCase `
            -InputManifestPath $launcherInputManifest `
            -InputManifestSha256 $launcherInputManifestSha256 `
            -TrainerArguments $orphanTrainerArguments | Out-Null
    }
    catch {
        if ($_.Exception.Message -match 'alive without its durable runner') {
            $orphanRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $orphanRejected -or (Test-Path -LiteralPath (Join-Path $orphanCase 'logs'))) {
        throw 'Actual trainer-only orphan was not rejected before launcher side effects'
    }

    $junctionTarget = Join-Path $temporaryRoot 'junction-target'
    $junctionRoot = Join-Path $temporaryRoot 'junction-root'
    [IO.Directory]::CreateDirectory($junctionTarget) | Out-Null
    New-Item -ItemType Junction -Path $junctionRoot -Target $junctionTarget | Out-Null
    $junctionRun = Join-Path $junctionRoot 'must-not-exist'
    $junctionTrainerArguments = @(
        '--dataset', $launcherDataset, '--dataset-sha256', $launcherDatasetSha256,
        '--model-dir', $launcherModel, '--model-sha256', $launcherModelSha256,
        '--output', (Join-Path $junctionTarget 'adapter'),
        '--report', (Join-Path $junctionTarget 'report.json')) + $contractTrainingArguments
    $junctionRejected = $false
    try {
        & $launcherPath `
            -RunDir $junctionRun `
            -RunId 'junction-contract' `
            -PythonPath $pythonPath `
            -TrainerPath $fakeTrainer `
            -WorkingDirectory $launcherCase `
            -InputManifestPath $launcherInputManifest `
            -InputManifestSha256 $launcherInputManifestSha256 `
            -TrainerArguments $junctionTrainerArguments | Out-Null
    }
    catch {
        if ($_.Exception.Message -match 'reparse point') {
            $junctionRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $junctionRejected -or (Test-Path -LiteralPath $junctionRun)) {
        throw 'Reparse RunDir was not rejected before filesystem creation'
    }
    Remove-Item -LiteralPath $junctionRoot -Force

    $pauseJunctionTarget = Join-Path $temporaryRoot 'pause-junction-target'
    $pauseJunctionRoot = Join-Path $temporaryRoot 'pause-junction-root'
    [IO.Directory]::CreateDirectory($pauseJunctionTarget) | Out-Null
    New-Item -ItemType Junction -Path $pauseJunctionRoot -Target $pauseJunctionTarget | Out-Null
    $pauseJunctionRun = Join-Path $pauseJunctionRoot 'must-not-exist'
    $pauseJunctionRejected = $false
    try {
        & $pausePath -RunDir $pauseJunctionRun | Out-Null
    }
    catch {
        if ($_.Exception.Message -match 'reparse point') {
            $pauseJunctionRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $pauseJunctionRejected -or
        (Test-Path -LiteralPath $pauseJunctionRun) -or
        (Test-Path -LiteralPath (Join-Path $pauseJunctionTarget 'control'))) {
        throw 'Safe-pause accepted a junction RunDir or created control side effects'
    }
    Remove-Item -LiteralPath $pauseJunctionRoot -Force

    $pauseCase = Join-Path $temporaryRoot 'live-pause-case'
    [IO.Directory]::CreateDirectory($pauseCase) | Out-Null
    $pauseTrainer = Join-Path $pauseCase 'pause trainer.py'
    $pauseTrainerSource = @'
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument("--run-dir", type=Path, required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--dataset-sha256", required=True)
parser.add_argument("--model-sha256", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--resume-from-checkpoint", type=Path)
parser.add_argument("--require-prearm", action="store_true")
args, _ = parser.parse_known_args()

if args.resume_from_checkpoint is not None:
    if not args.resume_from_checkpoint.is_dir():
        raise SystemExit(9)
    request = json.loads((args.run_dir / "control" / "pause.request.json").read_text())
    ack = json.loads((args.run_dir / "control" / "pause.ack.json").read_text())
    accepted = {
        "schema_version": "airi.behavior-resume-accepted.v1",
        "run_id": args.run_id, "request_id": request["request_id"],
        "checkpoint_relative_path": ack["checkpoint_relative_path"],
        "checkpoint_manifest_sha256": ack["checkpoint_manifest_sha256"],
    }
    (args.run_dir / "control" / "resume.accepted.json").write_bytes(canonical(accepted))
    time.sleep(1.5)
    args.output.mkdir(parents=True)
    (args.output / "adapter.bin").write_bytes(b"resumed-adapter")
    args.report.write_text("{}\n", encoding="utf-8")
    progress_path = args.run_dir / "progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    progress.update({"status": "completed", "epoch": 1,
                     "next_batch_index": 0, "microsteps_completed": 4,
                     "optimizer_steps": 2,
                     "updated_at_utc": datetime.now(timezone.utc).isoformat()})
    progress_path.write_bytes(canonical(progress))
    raise SystemExit(0)

# The durable launcher must pre-arm before Popen: observe the request at the
# trainer's first instruction, not after a polling window has hidden a race.
request_path = args.run_dir / "control" / "pause.request.json"
if args.require_prearm and not request_path.is_file():
    raise SystemExit(8)
if args.require_prearm:
    # The observation above is the trainer's first instruction.  Stay alive
    # briefly afterwards so the supervisor can capture the exact child PID;
    # an immediate exit would test snapshot scheduling instead of pre-Popen arm.
    time.sleep(1.5)
if not args.require_prearm:
    deadline = time.monotonic() + 20
    while not request_path.is_file() and time.monotonic() < deadline:
        time.sleep(0.1)
    if not request_path.is_file():
        raise SystemExit(8)
request = json.loads(request_path.read_text(encoding="utf-8"))
generation = "checkpoint-00000001"
checkpoint = args.run_dir / "checkpoints" / generation
checkpoint.mkdir(parents=True)
payload = b"live-safe-checkpoint"
(checkpoint / "state.pt").write_bytes(payload)
pins = {
    "dataset_sha256": args.dataset_sha256,
    "model_weight_sha256": args.model_sha256,
    "trainer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "config": {"learning_rate": 2e-5, "lora_dropout": 0.05},
}
manifest = {
    "schema_version": 1, "generation": generation, "run_id": args.run_id,
    "payload": {"name": "state.pt", "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()},
    "pins": pins,
}
manifest_bytes = canonical(manifest)
(checkpoint / "manifest.json").write_bytes(manifest_bytes)
progress_reference = {"relative_path": generation,
                      "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}
reference = {**progress_reference,
             "event_relative_path": "checkpoint-events/" + generation + ".json"}
now = datetime.now(timezone.utc).isoformat()
event = {
    "schema_version": "airi.behavior-checkpoint-event.v2", "run_id": args.run_id,
    "generation": generation, "reason": "safe-pause", "microsteps_completed": 2,
    "optimizer_steps": 1, "pending_microbatches": 0, "training_elapsed_ns": 1,
    "checkpoint_payload_progress": {"microsteps_completed": 2, "optimizer_steps": 1,
                                    "pending_microbatches": 0},
    "checkpoint_manifest_sha256": reference["manifest_sha256"],
    "checkpoint_payload_sha256": hashlib.sha256(payload).hexdigest(),
    "pins_sha256": hashlib.sha256(canonical(pins)).hexdigest(),
    "previous_event_sha256": None, "previous_index_sha256": None,
    "publish_started_at_utc": now, "checkpoint_durable_at_utc": now,
    "publish_elapsed_ns": 0,
}
event_bytes = canonical(event)
event_path = args.run_dir / reference["event_relative_path"]
event_path.parent.mkdir(parents=True, exist_ok=True)
event_path.write_bytes(event_bytes)
reference["event_sha256"] = hashlib.sha256(event_bytes).hexdigest()
index = {"schema_version": "airi.behavior-checkpoint-index.v2", "run_id": args.run_id,
         "latest": reference, "previous": None, "previous_index_sha256": None}
(args.run_dir / "checkpoints" / "checkpoint-index.json").write_bytes(canonical(index))
progress = {
    "schema_version": "airi.behavior-training-progress.v2",
    "run_id": args.run_id, "status": "paused-safe", "epoch": 0,
    "next_batch_index": 2, "microsteps_completed": 2,
    "optimizer_steps": 1, "pending_microbatches": 0,
    "checkpoint": progress_reference, "updated_at_utc": now, "training_elapsed_ns": 1,
}
(args.run_dir / "progress.json").write_bytes(canonical(progress))
ack = {
    "schema_version": "airi.behavior-pause-ack.v1", "run_id": args.run_id,
    "request_id": request["request_id"],
    "checkpoint_manifest_sha256": progress_reference["manifest_sha256"],
    "checkpoint_relative_path": generation,
    "acknowledged_at_utc": now, "safe_to_power_off": True,
}
(args.run_dir / "control" / "pause.ack.json").write_bytes(canonical(ack))
raise SystemExit(75)
'@
    [IO.File]::WriteAllText(
        $pauseTrainer, $pauseTrainerSource, [Text.UTF8Encoding]::new($false))
    Copy-Item -LiteralPath (Join-Path $root 'ollama-proxy\training\behavior_training_checkpoint.py') `
        -Destination (Join-Path $pauseCase 'behavior_training_checkpoint.py') -Force
    $pauseDataset = Join-Path $pauseCase 'dataset.jsonl'
    $pauseModel = Join-Path $pauseCase 'model'
    [IO.File]::WriteAllText(
        $pauseDataset, "{}$([Environment]::NewLine)",
        [Text.UTF8Encoding]::new($false))
    [IO.Directory]::CreateDirectory($pauseModel) | Out-Null
    [IO.File]::WriteAllText(
        (Join-Path $pauseModel 'config.json'), "{}$([Environment]::NewLine)",
        [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllBytes(
        (Join-Path $pauseModel 'model.safetensors'), [Text.Encoding]::ASCII.GetBytes('fixture-pause-model-weight'))
    $pauseRun = Join-Path $pauseCase 'durable run'
    $pauseOutput = Join-Path $pauseCase 'adapter output'
    $pauseReport = Join-Path $pauseCase 'report.json'
    $pauseInputManifest = Join-Path $pauseCase 'input-manifest.json'
    $pauseDatasetSha256 = (Get-FileHash -LiteralPath $pauseDataset -Algorithm SHA256).Hash.ToLowerInvariant()
    $pauseModelSha256 = (Get-FileHash -LiteralPath (Join-Path $pauseModel 'model.safetensors') -Algorithm SHA256).Hash.ToLowerInvariant()
    $pauseInputManifestSha256 = New-ContractInputManifest `
        $pauseInputManifest $pauseTrainer $pauseDataset $pauseModel 5
    $pauseTrainerArguments = @(
        '--dataset', $pauseDataset, '--dataset-sha256', $pauseDatasetSha256,
        '--model-dir', $pauseModel, '--model-sha256', $pauseModelSha256,
        '--output', $pauseOutput, '--report', $pauseReport,
        '--decoy-runner-path', $runnerPath) + $contractTrainingArguments
    $pauseLaunch = & $launcherPath `
        -RunDir $pauseRun `
        -RunId 'live-pause-contract' `
        -PythonPath $pythonPath `
        -TrainerPath $pauseTrainer `
        -WorkingDirectory $pauseCase `
        -InputManifestPath $pauseInputManifest `
        -InputManifestSha256 $pauseInputManifestSha256 `
        -CheckpointEveryOptimizerSteps 5 `
        -HeartbeatSeconds 1 `
        -TrainerArguments $pauseTrainerArguments
    if ([string]$pauseLaunch.run_id -ne 'live-pause-contract') {
        throw 'Live pause runner did not publish a launch receipt'
    }
    $liveStateDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 100
        $liveState = Get-Content -LiteralPath (Join-Path $pauseRun 'run-state.json') -Raw -Encoding utf8 | ConvertFrom-Json
        if ([string]$liveState.status -in @('running', 'pause-requested', 'checkpointing') -and
            $null -ne $liveState.runner -and $null -ne $liveState.trainer) {
            break
        }
    } while ([DateTime]::UtcNow -lt $liveStateDeadline)
    if ($null -eq $liveState.runner -or $null -eq $liveState.trainer) {
        throw 'Live pause runner did not publish exact runner and trainer identities'
    }
    if ([string]$liveState.command.runner_source_sha256 -ne
        (Get-FileHash -LiteralPath $runnerPath -Algorithm SHA256).Hash.ToLowerInvariant()) {
        throw 'Live pause runner did not bind its runner source hash'
    }
    $emptyManualRunDirRejected = $false
    try {
        & $pausePath -RunDir '' -TimeoutSeconds 10 -PollSeconds 1 | Out-Null
    }
    catch {
        if ($_.Exception.Message -match 'RunDir cannot be empty') {
            $emptyManualRunDirRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $emptyManualRunDirRejected) {
        throw 'Explicit empty RunDir unexpectedly entered automatic discovery'
    }
    $secondPauseRun = Join-Path $pauseCase 'second durable run'
    $secondPauseOutput = Join-Path $pauseCase 'second adapter output'
    $secondPauseReport = Join-Path $pauseCase 'second report.json'
    $secondPauseArguments = @(
        '--dataset', $pauseDataset, '--dataset-sha256', $pauseDatasetSha256,
        '--model-dir', $pauseModel, '--model-sha256', $pauseModelSha256,
        '--output', $secondPauseOutput, '--report', $secondPauseReport) + $contractTrainingArguments
    & $launcherPath `
        -RunDir $secondPauseRun `
        -RunId 'second-live-pause-contract' `
        -PythonPath $pythonPath `
        -TrainerPath $pauseTrainer `
        -WorkingDirectory $pauseCase `
        -InputManifestPath $pauseInputManifest `
        -InputManifestSha256 $pauseInputManifestSha256 `
        -CheckpointEveryOptimizerSteps 5 `
        -HeartbeatSeconds 1 `
        -TrainerArguments $secondPauseArguments | Out-Null
    $secondStatePath = Join-Path $secondPauseRun 'run-state.json'
    $secondLiveDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 100
        $secondLiveState = Get-Content -LiteralPath $secondStatePath -Raw -Encoding utf8 | ConvertFrom-Json
    } while (($null -eq $secondLiveState.runner -or $null -eq $secondLiveState.trainer) -and
        [DateTime]::UtcNow -lt $secondLiveDeadline)
    if ($null -eq $secondLiveState.runner -or $null -eq $secondLiveState.trainer) {
        throw 'Second live pause runner did not publish exact identities'
    }
    $multipleActiveResult = Invoke-OmittedRunDirPause
    $normalizedMultipleActiveOutput = $multipleActiveResult.output -replace '\s+', ' '
    if ($multipleActiveResult.exit_code -eq 0 -or
        $normalizedMultipleActiveOutput -notmatch 'more than one active durable AIRI training run' -or
        $normalizedMultipleActiveOutput -notmatch 'run_id=live-pause-contract' -or
        $normalizedMultipleActiveOutput -notmatch 'run_id=second-live-pause-contract') {
        throw "Omitted RunDir did not refuse multiple active durable runners: $($multipleActiveResult.output)"
    }
    $secondSafePause = & $pausePath -RunDir $secondPauseRun -TimeoutSeconds 30 -PollSeconds 1
    if (-not ($secondSafePause -contains 'SAFE_TO_POWER_OFF')) {
        throw 'Second active trainer did not stop after automatic-discovery ambiguity test'
    }
    $liveCurrentStatePath = Join-Path $pauseRun 'run-state.json'
    $livePreviousStatePath = Join-Path $pauseRun 'run-state.prev.json'
    [IO.File]::WriteAllBytes($livePreviousStatePath, [IO.File]::ReadAllBytes($liveCurrentStatePath))
    $parseableCorruptLiveState = Get-Content -LiteralPath $liveCurrentStatePath -Raw -Encoding utf8 | ConvertFrom-Json
    $parseableCorruptLiveState.runner = [pscustomobject]@{ pid = 12345 }
    [IO.File]::WriteAllText(
        $liveCurrentStatePath,
        (($parseableCorruptLiveState | ConvertTo-Json -Compress -Depth 10) + "`n"),
        [Text.UTF8Encoding]::new($false))
    # Omitted RunDir must select this sole live runner using its exact command line
    # and the valid previous receipt after the current receipt is corrupted.
    $safePauseResult = & $pausePath -TimeoutSeconds 30 -PollSeconds 1
    if (-not ($safePauseResult -contains 'SAFE_TO_POWER_OFF')) {
        throw 'Active trainer safe-pause did not produce SAFE_TO_POWER_OFF'
    }
    $pausedStatePath = Join-Path $pauseRun 'run-state.json'
    $pausedState = Get-Content -LiteralPath $pausedStatePath -Raw -Encoding utf8 | ConvertFrom-Json
    if ([string]$pausedState.status -ne 'paused-safe' -or
        [int]$pausedState.terminal.exit_code -ne 75) {
        throw 'Active trainer did not persist a paused-safe terminal receipt'
    }
    $pausedCheckpointManifest = Get-Content -LiteralPath (
        Join-Path $pauseRun 'checkpoints\checkpoint-00000001\manifest.json'
    ) -Raw -Encoding utf8 | ConvertFrom-Json
    if ([string]$pausedCheckpointManifest.pins.model_weight_sha256 -ne $pauseModelSha256) {
        throw 'Synthetic safe-pause checkpoint lost its exact model weight pin'
    }
    $runnerExitDeadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $liveRunner = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$pausedState.runner.pid)" -ErrorAction SilentlyContinue
        if ($null -eq $liveRunner) {
            break
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $runnerExitDeadline)
    if ($null -ne $liveRunner) {
        throw 'Paused durable runner did not exit before explicit resume'
    }
    $previousStatePath = Join-Path $pauseRun 'run-state.prev.json'
    $pausedStateBytes = [IO.File]::ReadAllBytes($pausedStatePath)
    $originalPreviousStateBytes = [IO.File]::ReadAllBytes($previousStatePath)
    $quarantineDir = Join-Path $pauseRun 'quarantine'
    $quarantineBeforeLauncher = @(
        Get-ChildItem -LiteralPath $quarantineDir -File -Filter 'run-state.corrupt.*.json' `
            -ErrorAction SilentlyContinue |
            Sort-Object Name |
            ForEach-Object {
                "$($_.Name):$($_.Length):$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
            }
    )
    [IO.File]::WriteAllBytes($previousStatePath, $pausedStateBytes)
    $structurallyCorruptState = [Text.UTF8Encoding]::new($false).GetString(
        $pausedStateBytes) | ConvertFrom-Json
    $structurallyCorruptState.runner = [pscustomobject]@{ pid = 12345 }
    $structurallyCorruptBytes = [Text.UTF8Encoding]::new($false).GetBytes(
        (($structurallyCorruptState | ConvertTo-Json -Compress -Depth 10) + "`n"))
    [IO.File]::WriteAllBytes($pausedStatePath, $structurallyCorruptBytes)
    $corruptCurrentRejected = $false
    try {
        & $launcherPath `
            -RunDir $pauseRun `
            -RunId 'live-pause-contract' `
            -PythonPath $pythonPath `
            -TrainerPath $pauseTrainer `
            -WorkingDirectory $pauseCase `
            -InputManifestPath $pauseInputManifest `
            -InputManifestSha256 $pauseInputManifestSha256 `
            -CheckpointEveryOptimizerSteps 5 `
            -HeartbeatSeconds 1 `
            -ResumeInterrupted `
            -TrainerArguments $pauseTrainerArguments | Out-Null
    }
    catch {
        if ($_.Exception.Message -match 'previous state cannot authorize resume') {
            $corruptCurrentRejected = $true
        }
        else {
            throw
        }
    }
    if (-not $corruptCurrentRejected) {
        throw 'Corrupt current run-state authorized stale terminal previous resume'
    }
    $quarantineAfterRejection = @(
        Get-ChildItem -LiteralPath $quarantineDir -File -Filter 'run-state.corrupt.*.json' `
            -ErrorAction SilentlyContinue |
            Sort-Object Name |
            ForEach-Object {
                "$($_.Name):$($_.Length):$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
            }
    )
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($pausedStatePath)) -ne
            [Convert]::ToBase64String($structurallyCorruptBytes) -or
        ($quarantineAfterRejection -join "`n") -ne ($quarantineBeforeLauncher -join "`n")) {
        throw 'Launcher rejection mutated the corrupt current run-state before explicit restoration'
    }
    [IO.File]::WriteAllBytes($pausedStatePath, $pausedStateBytes)
    [IO.File]::WriteAllBytes($previousStatePath, $originalPreviousStateBytes)
    $resumeLaunch = & $launcherPath `
        -RunDir $pauseRun `
        -RunId 'live-pause-contract' `
        -PythonPath $pythonPath `
        -TrainerPath $pauseTrainer `
        -WorkingDirectory $pauseCase `
        -InputManifestPath $pauseInputManifest `
        -InputManifestSha256 $pauseInputManifestSha256 `
        -CheckpointEveryOptimizerSteps 5 `
        -HeartbeatSeconds 1 `
        -ResumeInterrupted `
        -TrainerArguments $pauseTrainerArguments
    if ([string]$resumeLaunch.run_id -ne 'live-pause-contract') {
        throw 'Explicit PowerShell resume did not publish a launch receipt'
    }
    if ([string]$resumeLaunch.status -eq 'paused-safe') {
        throw 'Resume launcher returned the stale paused-safe terminal receipt'
    }
    $postLaunchState = Get-Content -LiteralPath $pausedStatePath -Raw -Encoding utf8 | ConvertFrom-Json
    if ([int]$postLaunchState.revision -le [int]$pausedState.revision) {
        throw 'Resume launcher did not require a new run-state revision'
    }
    $resumeDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        $resumedState = Get-Content -LiteralPath $pausedStatePath -Raw -Encoding utf8 | ConvertFrom-Json
        if ([string]$resumedState.status -eq 'complete') {
            break
        }
        if ([string]$resumedState.status -in @('failed', 'interrupted')) {
            throw "Explicit PowerShell resume ended as $($resumedState.status)"
        }
    } while ([DateTime]::UtcNow -lt $resumeDeadline)
    $resumeAcceptedHistory = @(Get-ChildItem -LiteralPath (
            Join-Path $pauseRun 'control\history') -File -Filter '*.resume-accepted.json' -ErrorAction SilentlyContinue)
    if ([string]$resumedState.status -ne 'complete' -or
        [int]$resumedState.terminal.exit_code -ne 0 -or
        -not (Test-Path -LiteralPath $pauseOutput -PathType Container) -or
        -not (Test-Path -LiteralPath $pauseReport -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $pauseRun 'control\history') -PathType Container) -or
        $resumeAcceptedHistory.Count -ne 1) {
        throw 'Explicit PowerShell resume did not complete with archived pause controls'
    }
    $quarantineAfterResume = @(
        Get-ChildItem -LiteralPath $quarantineDir -File -Filter 'run-state.corrupt.*.json' `
            -ErrorAction SilentlyContinue |
            Sort-Object Name |
            ForEach-Object {
                "$($_.Name):$($_.Length):$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
            }
    )
    if (($quarantineAfterResume -join "`n") -ne ($quarantineBeforeLauncher -join "`n")) {
        throw 'Explicit restore/resume changed the pre-existing corrupt-state quarantine inventory'
    }
    $resumeRunnerExitDeadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $resumedRunnerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$resumedState.runner.pid)" -ErrorAction SilentlyContinue
        if ($null -eq $resumedRunnerProcess) {
            break
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $resumeRunnerExitDeadline)
    if ($null -ne $resumedRunnerProcess) {
        throw 'Resumed durable runner did not release its log handles after terminal receipt'
    }
    $prearmRun = Join-Path $pauseCase 'prearm-first-boundary'
    $prearmOutput = Join-Path $pauseCase 'prearm adapter'
    $prearmReport = Join-Path $pauseCase 'prearm report.json'
    $prearmArguments = @(
        '--dataset', $pauseDataset, '--dataset-sha256', $pauseDatasetSha256,
        '--model-dir', $pauseModel, '--model-sha256', $pauseModelSha256,
        '--output', $prearmOutput, '--report', $prearmReport,
        '--require-prearm') + $contractTrainingArguments
    $prearmLaunch = & $launcherPath `
        -RunDir $prearmRun `
        -RunId 'prearm-first-boundary-contract' `
        -PythonPath $pythonPath `
        -TrainerPath $pauseTrainer `
        -WorkingDirectory $pauseCase `
        -InputManifestPath $pauseInputManifest `
        -InputManifestSha256 $pauseInputManifestSha256 `
        -CheckpointEveryOptimizerSteps 5 `
        -HeartbeatSeconds 1 `
        -PauseAtFirstOptimizerBoundary `
        -TrainerArguments $prearmArguments
    if ([string]$prearmLaunch.run_id -ne 'prearm-first-boundary-contract' -or
        [string]::IsNullOrWhiteSpace([string]$prearmLaunch.status)) {
        throw 'Prearmed first-boundary launcher did not publish a verified launch receipt'
    }
    $prearmDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 100
        $prearmState = Get-Content -LiteralPath (Join-Path $prearmRun 'run-state.json') -Raw -Encoding utf8 | ConvertFrom-Json
        if ([string]$prearmState.status -in @('paused-safe', 'failed', 'interrupted')) { break }
    } while ([DateTime]::UtcNow -lt $prearmDeadline)
    if ([string]$prearmState.status -ne 'paused-safe' -or
        [int]$prearmState.terminal.exit_code -ne 75 -or
        $null -eq $prearmState.terminal.checkpoint_verification) {
        throw 'Fresh prearm request was not visible to the trainer at process spawn'
    }
    $prearmPostHocPause = Invoke-ManualRunDirPause -RunDir $prearmRun -TimeoutSeconds 5
    if ($prearmPostHocPause.exit_code -eq 0 -or
        (Test-ContainsSafePowerOffMarker $prearmPostHocPause.output) -or
        $prearmPostHocPause.output -notmatch 'Already-paused terminal cannot authorize power-off') {
        throw 'Post-hoc pause accepted a prearmed terminal without live identity observation'
    }
    $relatedExitDeadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $relatedProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $null -ne $_.CommandLine -and
                ([string]$_.CommandLine).Contains($temporaryRoot) })
        if ($relatedProcesses.Count -eq 0) {
            break
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $relatedExitDeadline)
    if ($relatedProcesses.Count -ne 0) {
        throw "Durability contract left related process IDs alive: $($relatedProcesses.ProcessId -join ',')"
    }
    $contractSucceeded = $true
}
finally {
    if ($KeepFailedArtifacts -and -not $contractSucceeded) {
        Write-Warning "Preserved failed durability artifacts at $temporaryRoot"
    }
    elseif (Test-Path -LiteralPath $temporaryRoot) {
        $resolved = [IO.Path]::GetFullPath($temporaryRoot)
        if ($resolved.StartsWith($expectedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and
            $resolved -ne $expectedTempRoot) {
            $cleanupError = $null
            for ($attempt = 0; $attempt -lt 50 -and (Test-Path -LiteralPath $resolved); $attempt++) {
                try {
                    Remove-Item -LiteralPath $resolved -Recurse -Force
                    $cleanupError = $null
                }
                catch {
                    $cleanupError = $_
                    Start-Sleep -Milliseconds 200
                }
            }
            if (Test-Path -LiteralPath $resolved) {
                Write-Warning "Deferred locked temp cleanup until the calling PowerShell session exits: $resolved"
            }
        }
    }
}

Write-Output 'AIRI training durability contract: PASS'
