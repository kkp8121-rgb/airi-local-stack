#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'test-airi-work-continuity.ps1')
& (Join-Path $PSScriptRoot 'test-patch-manifest.ps1')
& (Join-Path $PSScriptRoot 'test-source-archive-manifest.ps1')
& (Join-Path $PSScriptRoot 'test-patch-entrypoints.ps1')
& (Join-Path $PSScriptRoot 'test-patch-applicability.ps1')
& (Join-Path $PSScriptRoot 'gpt-sovits\test_start_local_stack_contract.ps1')
& (Join-Path $PSScriptRoot 'test-airi-source-asar-deploy.ps1')
& (Join-Path $PSScriptRoot 'test-airi-source-asar-preflight-contract.ps1')

$senderTest = Join-Path $PSScriptRoot 'test-send-airi-local-text.mjs'
& node --test $senderTest
if ($LASTEXITCODE -ne 0) { throw 'Sender contract tests failed.' }

$runtimeFenceTest = Join-Path $PSScriptRoot 'test-affect-evaluator-runtime-fence.mjs'
$runtimeFenceMinimumTests = 11
$runtimeFenceOutput = @(& node --test $runtimeFenceTest 2>&1 | ForEach-Object { $_.ToString() })
$runtimeFenceExit = $LASTEXITCODE
$runtimeFenceOutput | Write-Output
if ($runtimeFenceExit -ne 0) { throw 'Affect evaluator runtime fence tests failed.' }
$runtimeFenceCountMatch = [regex]::Match(($runtimeFenceOutput -join "`n"), '(?m)^.{0,4}tests\s+(?<count>\d+)\s*$')
if (-not $runtimeFenceCountMatch.Success) {
    throw 'Could not read the affect evaluator runtime fence test count.'
}
$runtimeFenceCount = [int]$runtimeFenceCountMatch.Groups['count'].Value
if ($runtimeFenceCount -lt $runtimeFenceMinimumTests) {
    throw "Affect evaluator runtime fence suite reported $runtimeFenceCount tests; expected at least $runtimeFenceMinimumTests."
}

$inputSafetyTest = Join-Path $PSScriptRoot 'ollama-proxy\eval\input_safety\test_airi_ko_input_safety_eval.py'
$inputSafetyMinimumTests = 16
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $inputSafetyOutput = @(& python -m unittest -v $inputSafetyTest 2>&1 | ForEach-Object { $_.ToString() })
    $inputSafetyExit = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
$inputSafetyOutput | Write-Output
if ($inputSafetyExit -ne 0) { throw 'B3-d input safety regression tests failed.' }
$inputSafetyCountMatch = [regex]::Match(
    ($inputSafetyOutput -join "`n"),
    'Ran\s+(?<count>\d+)\s+tests?'
)
if (-not $inputSafetyCountMatch.Success) {
    throw 'Could not read the B3-d input safety regression test count.'
}
$inputSafetyCount = [int]$inputSafetyCountMatch.Groups['count'].Value
if ($inputSafetyCount -lt $inputSafetyMinimumTests) {
    throw "B3-d input safety suite reported $inputSafetyCount tests; expected at least $inputSafetyMinimumTests."
}

$broadcastRehearsalTest = Join-Path $PSScriptRoot 'ollama-proxy\eval\broadcast_chat\test_run_broadcast_rehearsal.py'
$broadcastRehearsalMinimumTests = 37
$previousBroadcastErrorActionPreference = $ErrorActionPreference
$previousPythonIoEncoding = $env:PYTHONIOENCODING
$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'
try {
    $broadcastRehearsalOutput = @(& python -m unittest -v $broadcastRehearsalTest 2>&1 | ForEach-Object { $_.ToString() })
    $broadcastRehearsalExit = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousBroadcastErrorActionPreference
    if ($null -eq $previousPythonIoEncoding) {
        Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONIOENCODING = $previousPythonIoEncoding
    }
}
$broadcastRehearsalOutput | Write-Output
if ($broadcastRehearsalExit -ne 0) { throw 'B4c broadcast rehearsal regression tests failed.' }
$broadcastRehearsalCountMatch = [regex]::Match(
    ($broadcastRehearsalOutput -join "`n"),
    'Ran\s+(?<count>\d+)\s+tests?'
)
if (-not $broadcastRehearsalCountMatch.Success) {
    throw 'Could not read the B4c broadcast rehearsal test count.'
}
$broadcastRehearsalCount = [int]$broadcastRehearsalCountMatch.Groups['count'].Value
if ($broadcastRehearsalCount -lt $broadcastRehearsalMinimumTests) {
    throw "B4c broadcast rehearsal suite reported $broadcastRehearsalCount tests; expected at least $broadcastRehearsalMinimumTests."
}

# `node --test` exits zero when its glob matches no file, so a green run alone
# does not prove the suite ran. Read the reported pass count and hold it to a
# floor; raise the floor whenever chat-ingress tests are added.
$chatIngressMinimumTests = 47
$chatIngressOutput = @(& node --test (Join-Path $PSScriptRoot 'chat-ingress\test-*.mjs') 2>&1 | ForEach-Object { $_.ToString() })
$chatIngressExit = $LASTEXITCODE
$chatIngressOutput | Write-Output
if ($chatIngressExit -ne 0) { throw 'Chat ingress contract tests failed.' }
$chatIngressPass = [regex]::Match(($chatIngressOutput -join "`n"), '(?m)^.{0,4}pass\s+(?<count>\d+)\s*$')
if (-not $chatIngressPass.Success) {
    throw 'Could not read the chat ingress passing test count.'
}
$chatIngressCount = [int]$chatIngressPass.Groups['count'].Value
if ($chatIngressCount -lt $chatIngressMinimumTests) {
    throw "Chat ingress suite reported $chatIngressCount passing tests; expected at least $chatIngressMinimumTests."
}

& node --test (Join-Path $PSScriptRoot 'broadcast-director\test-*.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Broadcast director contract tests failed.' }

& node --test (Join-Path $PSScriptRoot 'latency-monitor\test-dashboard-metrics.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Latency dashboard metrics tests failed.' }

Write-Output 'Current checkpoint contract: PASS (offline synthetic ASAR only; no installed archive/service/model access).'
