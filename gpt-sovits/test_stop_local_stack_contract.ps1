$ErrorActionPreference = 'Stop'

# Static contract test: it never enumerates or stops processes.
$scriptPath = Join-Path $PSScriptRoot 'stop-local-stack.ps1'
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

$source = Get-Content -LiteralPath $scriptPath -Raw
foreach ($requiredFragment in @(
    "Join-Path `$PSScriptRoot 'run_v2proplus_with_sv_cache.py'",
    "Join-Path `$PSScriptRoot '..\external\GPT-SoVITS'",
    '[regex]::Escape($wrapper)',
    '[regex]::Escape($externalRoot)',
    '[regex]::Escape($config)',
    "`$_.CommandLine -match `$wrapperPattern",
    "`$_.CommandLine -match `$configPattern",
    "`$_.CommandLine -match `$externalRootArgumentPattern",
    "(?<!\S)--external-root\s+`"?' + [regex]::Escape(`$externalRoot)",
    "--\s+-a\s+127\.0\.0\.1",
    "-p\s+9880"
)) {
    if ($source -notmatch [regex]::Escape($requiredFragment)) {
        throw "Cached-wrapper stopper contract is missing: $requiredFragment"
    }
}

if ($source -notmatch [regex]::Escape("`$_.CommandLine.IndexOf('api_v2.py', [StringComparison]::OrdinalIgnoreCase) -ge 0")) {
    throw 'Stopper must retain legacy api_v2.py backend recognition.'
}

Write-Output 'stop_local_stack_wrapper_ownership_contract=passed'
