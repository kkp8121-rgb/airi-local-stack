#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'test-patch-manifest.ps1')
& (Join-Path $PSScriptRoot 'test-patch-entrypoints.ps1')
& (Join-Path $PSScriptRoot 'test-patch-applicability.ps1')
& (Join-Path $PSScriptRoot 'gpt-sovits\test_start_local_stack_contract.ps1')

$senderTest = Join-Path $PSScriptRoot 'test-send-airi-local-text.mjs'
& node --test $senderTest
if ($LASTEXITCODE -ne 0) { throw 'Sender contract tests failed.' }

& node --test (Join-Path $PSScriptRoot 'chat-ingress\test-*.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Chat ingress contract tests failed.' }

& node --test (Join-Path $PSScriptRoot 'broadcast-director\test-*.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Broadcast director contract tests failed.' }

Write-Output 'Current checkpoint contract: PASS (offline, no archive/service/model access).'
