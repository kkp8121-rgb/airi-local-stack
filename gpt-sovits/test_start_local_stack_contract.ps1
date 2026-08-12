$ErrorActionPreference = 'Stop'

# Static contract test: it never invokes the launcher, Python, or a TTS model.
$scriptPath = Join-Path $PSScriptRoot 'start-local-stack.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
  $scriptPath,
  [ref]$tokens,
  [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
  throw "PowerShell parse failure: $($parseErrors[0].Message)"
}

$waitFunction = @($ast.FindAll({ param($node)
  $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
  $node.Name -eq 'Wait-ImmediateResponseCache'
}, $true))
if ($waitFunction.Count -ne 1) {
  throw 'Expected exactly one Wait-ImmediateResponseCache function.'
}

$functionText = $waitFunction[0].Extent.Text
foreach ($requiredFragment in @(
  'Invoke-RestMethod',
  'immediate_response_cache',
  '$total -gt 0',
  '$ready -eq $total',
  'Start-Sleep',
  'TimeoutSeconds'
)) {
  if ($functionText -notmatch [regex]::Escape($requiredFragment)) {
    throw "Readiness function is missing required contract fragment: $requiredFragment"
  }
}

$source = Get-Content -LiteralPath $scriptPath -Raw
if ($source -match '(?m)^\s*Wait-Port\s+8880\b') {
  throw 'Port 8880 must not be the speech proxy readiness gate.'
}
if ($source -notmatch '(?m)^\s*\$speechHealth\s*=\s*Wait-ImmediateResponseCache\b') {
  throw 'Launcher must wait for the acknowledgement cache before reporting ready.'
}
if ($source -notmatch '\$env:GPT_SOVITS_REFERENCE_AUDIO' -or
    $source -notmatch '\[System\.IO\.Path\]::GetFullPath') {
  throw 'Launcher must honor an explicit reference-audio path for clean worktrees.'
}

$verifierPath = Join-Path $PSScriptRoot 'verify-local-stack.ps1'
$verifierSource = Get-Content -LiteralPath $verifierPath -Raw
foreach ($requiredFragment in @(
  '$cache.total -le 0',
  '$cache.ready -ne $cache.total'
)) {
  if ($verifierSource -notmatch [regex]::Escape($requiredFragment)) {
    throw "Verifier must require every configured cached phrase to be ready: $requiredFragment"
  }
}
if ($verifierSource -match '\$cache\.ready\s*-lt\s*2') {
  throw 'Verifier must not accept only two ready cached phrases.'
}

Write-Output 'start_local_stack_cache_readiness_contract=passed'
