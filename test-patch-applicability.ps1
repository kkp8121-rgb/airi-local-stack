#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$BaseCheckout
)

$ErrorActionPreference = 'Stop'
$PinnedCommit = 'dbf812488829a61cc2e95909e021b215704d066c'
$CanonicalPatch = Join-Path $PSScriptRoot 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch'
$SanitizerPatch = Join-Path $PSScriptRoot 'airi_docs/patches/AIRI-v0.11.3-context-correlation-sanitizer.patch'

if ([string]::IsNullOrWhiteSpace($BaseCheckout)) {
    Write-Output 'Patch applicability: SKIP (offline and inert; supply -BaseCheckout to opt in).'
    exit 0
}

function Invoke-Git {
    param([string]$WorkingDirectory, [string[]]$Arguments, [switch]$AllowFailure)
    # Git writes progress such as `Preparing worktree` to stderr even when the
    # command succeeds. Capture that stream without letting PowerShell's
    # Stop-on-error preference turn a successful command into an exception.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $result = @(& git -C $WorkingDirectory @Arguments 2>&1)
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $code = $LASTEXITCODE
    if (-not $AllowFailure -and $code -ne 0) {
        $detail = ($result | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        throw "git $($Arguments -join ' ') failed (exit $code): $detail"
    }
    return [pscustomobject]@{ ExitCode = $code; Output = $result }
}

function Assert-RegularDirectory {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "$Label is not a local directory: $Path" }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "$Label must be a regular non-reparse directory: $Path"
    }
}

Assert-RegularDirectory -Path $BaseCheckout -Label 'Base checkout'
$resolvedBase = (Resolve-Path -LiteralPath $BaseCheckout).Path
$inside = ((Invoke-Git $resolvedBase @('rev-parse', '--is-inside-work-tree')).Output | Select-Object -Last 1).ToString().Trim()
if ($inside -ne 'true') { throw 'Base checkout is not a non-bare work-tree.' }
$bare = ((Invoke-Git $resolvedBase @('rev-parse', '--is-bare-repository')).Output | Select-Object -Last 1).ToString().Trim()
if ($bare -ne 'false') { throw 'Base checkout must not be a bare repository.' }
$top = ((Invoke-Git $resolvedBase @('rev-parse', '--show-toplevel')).Output | Select-Object -Last 1).ToString().Trim()
if ((Resolve-Path -LiteralPath $top).Path -ne $resolvedBase) { throw 'BaseCheckout is not the checkout root.' }
$head = ((Invoke-Git $resolvedBase @('rev-parse', '--verify', 'HEAD')).Output | Select-Object -Last 1).ToString().Trim().ToLowerInvariant()
if ($head -ne $PinnedCommit) { throw "Base checkout HEAD must be $PinnedCommit (found $head)." }

foreach ($patch in @($CanonicalPatch, $SanitizerPatch)) {
    if (-not (Test-Path -LiteralPath $patch -PathType Leaf)) { throw "Missing patch artifact: $patch" }
}

$worktree = Join-Path ([IO.Path]::GetTempPath()) ('airi-patch-applicability-' + [guid]::NewGuid().ToString('N'))
$worktreeAdded = $false
try {
    Write-Output "Patch applicability: validating pinned checkout $PinnedCommit"
    Invoke-Git $resolvedBase @('worktree', 'add', '--detach', $worktree, $PinnedCommit) | Out-Null
    $worktreeAdded = $true
    Invoke-Git $worktree @('apply', '--check', '--whitespace=nowarn', $CanonicalPatch) | Out-Null
    Invoke-Git $worktree @('apply', '--whitespace=nowarn', $CanonicalPatch) | Out-Null
    Invoke-Git $worktree @('apply', '--check', '--whitespace=nowarn', $SanitizerPatch) | Out-Null
    Invoke-Git $worktree @('apply', '--whitespace=nowarn', $SanitizerPatch) | Out-Null
    Invoke-Git $worktree @('apply', '--reverse', '--check', '--whitespace=nowarn', $SanitizerPatch) | Out-Null
    Invoke-Git $worktree @('apply', '--reverse', '--whitespace=nowarn', $SanitizerPatch) | Out-Null
    Invoke-Git $worktree @('apply', '--reverse', '--check', '--whitespace=nowarn', $CanonicalPatch) | Out-Null
    Invoke-Git $worktree @('apply', '--reverse', '--whitespace=nowarn', $CanonicalPatch) | Out-Null
    $status = (Invoke-Git $worktree @('status', '--porcelain')).Output
    if ($status.Count -ne 0) { throw 'Temporary worktree was not clean after reverse application.' }
    Write-Output 'Patch applicability: PASS (canonical and sanitizer apply/reverse-check cleanly; AIRI untouched).'
}
finally {
    if ($worktreeAdded) {
        # Let Git remove its own worktree through its registered metadata. Do
        # not fall back to a path-based recursive delete: a same-user race
        # could replace the path between validation and Remove-Item.
        $removeResult = Invoke-Git $resolvedBase @('worktree', 'remove', '--force', $worktree) -AllowFailure
        if ($removeResult.ExitCode -ne 0) {
            Write-Warning 'Git could not remove the temporary worktree; leaving it untouched for manual cleanup.'
        }
    }
}
