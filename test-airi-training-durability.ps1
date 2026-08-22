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
    'alive without its durable runner', 'baselineRevision')) {
    if (-not $launcher.Contains($token)) {
        throw "Durable launcher contract token is missing: $token"
    }
}
foreach ($token in @(
    'SAFE_TO_POWER_OFF', 'Test-ExactProcessRecord', 'pause.request.json',
    'pause.ack.json', 'checkpoint_manifest_sha256', 'pending_microbatches',
    'complete outputs receipt', 'Assert-ExactJsonProperties', 'MoveFileEx',
    'DriveType]::Fixed', 'cannot traverse a reparse point', 'run-state.prev.json')) {
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

try {
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
        pins = [ordered]@{ test = 'offline' }
        run_id = 'contract-run'
        schema_version = 1
    }
    $manifestPath = Join-Path $generationDir 'manifest.json'
    [IO.File]::WriteAllText(
        $manifestPath, (($manifest | ConvertTo-Json -Compress) + "`n"),
        [Text.UTF8Encoding]::new($false))
    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
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
        terminal = [ordered]@{ exit_code = 75; reason = 'safe-optimizer-boundary' }
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
        inputs = [ordered]@{}
        command = [ordered]@{}
        heartbeat = [ordered]@{}
        logs = [ordered]@{}
        outputs = [ordered]@{ adapter = $null; report = $null }
    }
    [IO.File]::WriteAllText(
        (Join-Path $controlDir 'pause.request.json'),
        (($request | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText(
        (Join-Path $controlDir 'pause.ack.json'),
        (($ack | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText(
        (Join-Path $runDir 'run-state.json'),
        (($state | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))

    $result = & $pausePath -RunDir $runDir
    if (-not ($result -contains 'SAFE_TO_POWER_OFF')) {
        throw 'Offline safe-pause verified receipt did not produce SAFE_TO_POWER_OFF'
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
        if ($_.Exception.Message -match 'property set is invalid') {
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
import json
import time
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--run-dir", type=Path, required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
args, _ = parser.parse_known_args()
time.sleep(2.0)
args.output.mkdir(parents=True)
(args.output / "adapter.bin").write_bytes(b"adapter")
args.report.write_text("{}\n", encoding="utf-8")
progress = {
    "schema_version": "airi.behavior-training-progress.v1",
    "run_id": args.run_id, "status": "completed", "epoch": 1,
    "next_batch_index": 0, "microsteps_completed": 2,
    "optimizer_steps": 1, "pending_microbatches": 0,
    "checkpoint": None,
    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
}
(args.run_dir / "progress.json").write_text(
    json.dumps(progress, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8")
'@
    [IO.File]::WriteAllText($fakeTrainer, $fakeSource, [Text.UTF8Encoding]::new($false))
    $launcherRun = Join-Path $launcherCase 'run with spaces'
    $launcherOutput = Join-Path $launcherCase 'adapter output'
    $launcherReport = Join-Path $launcherCase 'report output.json'
    $pinnedTestPython = 'D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe'
    $pythonPath = if (Test-Path -LiteralPath $pinnedTestPython -PathType Leaf) {
        $pinnedTestPython
    }
    else {
        (Get-Command python -ErrorAction Stop).Source
    }
    $launchReceipt = & $launcherPath `
        -RunDir $launcherRun `
        -RunId 'launcher-contract' `
        -PythonPath $pythonPath `
        -TrainerPath $fakeTrainer `
        -WorkingDirectory $launcherCase `
        -InputManifestSha256 ('c' * 64) `
        -CheckpointEveryOptimizerSteps 5 `
        -HeartbeatSeconds 1 `
        -TrainerArguments @(
            '--dataset-sha256', ('a' * 64), '--model-sha256', ('b' * 64),
            '--output', $launcherOutput, '--report', $launcherReport)
    if ([string]$launchReceipt.run_id -ne 'launcher-contract' -or
        [int]$launchReceipt.runner_pid -le 0) {
        throw 'Durable launcher did not return its PID/run-state receipt'
    }
    $launcherStatePath = Join-Path $launcherRun 'run-state.json'
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
    $completeSafe = & $pausePath -RunDir $launcherRun -TimeoutSeconds 30 -PollSeconds 1
    if (-not ($completeSafe -contains 'SAFE_TO_POWER_OFF')) {
        throw 'Durably completed run was not accepted as safe to power off'
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
    $orphanRejected = $false
    try {
        & $launcherPath `
            -RunDir $orphanCase `
            -RunId 'orphan-contract' `
            -PythonPath $pythonPath `
            -TrainerPath $fakeTrainer `
            -WorkingDirectory $launcherCase `
            -InputManifestSha256 ('d' * 64) `
            -TrainerArguments @(
                '--dataset-sha256', ('a' * 64), '--model-sha256', ('b' * 64),
                '--output', (Join-Path $orphanCase 'adapter'),
                '--report', (Join-Path $orphanCase 'report.json')) | Out-Null
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
    $junctionRejected = $false
    try {
        & $launcherPath `
            -RunDir $junctionRun `
            -RunId 'junction-contract' `
            -PythonPath $pythonPath `
            -TrainerPath $fakeTrainer `
            -WorkingDirectory $launcherCase `
            -TrainerArguments @(
                '--dataset-sha256', ('a' * 64), '--model-sha256', ('b' * 64),
                '--output', (Join-Path $junctionTarget 'adapter'),
                '--report', (Join-Path $junctionTarget 'report.json')) | Out-Null
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

parser = argparse.ArgumentParser()
parser.add_argument("--run-dir", type=Path, required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--dataset-sha256", required=True)
parser.add_argument("--model-sha256", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--report", type=Path, required=True)
parser.add_argument("--resume-from-checkpoint", type=Path)
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

request_path = args.run_dir / "control" / "pause.request.json"
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
}
manifest = {
    "schema_version": 1, "generation": generation, "run_id": args.run_id,
    "payload": {"name": "state.pt", "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()},
    "pins": pins,
}
manifest_bytes = canonical(manifest)
(checkpoint / "manifest.json").write_bytes(manifest_bytes)
reference = {"relative_path": generation,
             "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}
index = {"schema_version": "airi.behavior-checkpoint-index.v1",
         "latest": reference, "previous": None}
(args.run_dir / "checkpoints" / "checkpoint-index.json").write_bytes(canonical(index))
now = datetime.now(timezone.utc).isoformat()
progress = {
    "schema_version": "airi.behavior-training-progress.v1",
    "run_id": args.run_id, "status": "paused-safe", "epoch": 0,
    "next_batch_index": 2, "microsteps_completed": 2,
    "optimizer_steps": 1, "pending_microbatches": 0,
    "checkpoint": reference, "updated_at_utc": now,
}
(args.run_dir / "progress.json").write_bytes(canonical(progress))
ack = {
    "schema_version": "airi.behavior-pause-ack.v1", "run_id": args.run_id,
    "request_id": request["request_id"],
    "checkpoint_manifest_sha256": reference["manifest_sha256"],
    "checkpoint_relative_path": generation,
    "acknowledged_at_utc": now, "safe_to_power_off": True,
}
(args.run_dir / "control" / "pause.ack.json").write_bytes(canonical(ack))
raise SystemExit(75)
'@
    [IO.File]::WriteAllText(
        $pauseTrainer, $pauseTrainerSource, [Text.UTF8Encoding]::new($false))
    $pauseRun = Join-Path $pauseCase 'durable run'
    $pauseOutput = Join-Path $pauseCase 'adapter output'
    $pauseReport = Join-Path $pauseCase 'report.json'
    $pauseTrainerArguments = @(
        '--dataset-sha256', ('d' * 64), '--model-sha256', ('e' * 64),
        '--output', $pauseOutput, '--report', $pauseReport)
    $pauseLaunch = & $launcherPath `
        -RunDir $pauseRun `
        -RunId 'live-pause-contract' `
        -PythonPath $pythonPath `
        -TrainerPath $pauseTrainer `
        -WorkingDirectory $pauseCase `
        -InputManifestSha256 ('f' * 64) `
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
    $liveCurrentStatePath = Join-Path $pauseRun 'run-state.json'
    $livePreviousStatePath = Join-Path $pauseRun 'run-state.prev.json'
    [IO.File]::WriteAllBytes($livePreviousStatePath, [IO.File]::ReadAllBytes($liveCurrentStatePath))
    $parseableCorruptLiveState = Get-Content -LiteralPath $liveCurrentStatePath -Raw -Encoding utf8 | ConvertFrom-Json
    $parseableCorruptLiveState.runner = [pscustomobject]@{ pid = 12345 }
    [IO.File]::WriteAllText(
        $liveCurrentStatePath,
        (($parseableCorruptLiveState | ConvertTo-Json -Compress -Depth 10) + "`n"),
        [Text.UTF8Encoding]::new($false))
    $safePauseResult = & $pausePath -RunDir $pauseRun -TimeoutSeconds 30 -PollSeconds 1
    if (-not ($safePauseResult -contains 'SAFE_TO_POWER_OFF')) {
        throw 'Active trainer safe-pause did not produce SAFE_TO_POWER_OFF'
    }
    $pausedStatePath = Join-Path $pauseRun 'run-state.json'
    $pausedState = Get-Content -LiteralPath $pausedStatePath -Raw -Encoding utf8 | ConvertFrom-Json
    if ([string]$pausedState.status -ne 'paused-safe' -or
        [int]$pausedState.terminal.exit_code -ne 75) {
        throw 'Active trainer did not persist a paused-safe terminal receipt'
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
    [IO.File]::WriteAllBytes($previousStatePath, $pausedStateBytes)
    $structurallyCorruptState = [Text.UTF8Encoding]::new($false).GetString(
        $pausedStateBytes) | ConvertFrom-Json
    $structurallyCorruptState.runner = [pscustomobject]@{ pid = 12345 }
    [IO.File]::WriteAllText(
        $pausedStatePath,
        (($structurallyCorruptState | ConvertTo-Json -Compress -Depth 10) + "`n"),
        [Text.UTF8Encoding]::new($false))
    $resumeLaunch = & $launcherPath `
        -RunDir $pauseRun `
        -RunId 'live-pause-contract' `
        -PythonPath $pythonPath `
        -TrainerPath $pauseTrainer `
        -WorkingDirectory $pauseCase `
        -InputManifestSha256 ('f' * 64) `
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
    if (-not @(Get-ChildItem -LiteralPath (Join-Path $pauseRun 'quarantine') -File -ErrorAction SilentlyContinue |
            Where-Object Name -Like 'run-state.corrupt.*.json').Count) {
        throw 'Corrupt current run-state was not quarantined during previous-state recovery'
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
