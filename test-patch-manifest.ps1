#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
# Every tracked patch is pinned, not just the three the current procedure
# applies. An unpinned artifact can be rewritten with nothing detecting it,
# and two of the historical ones reached this state already: their Korean was
# replaced by '?' at some point and cannot be recovered from the bytes here.
# Usable = whether `git apply` accepts the file against the pinned v0.11.3
# base. That was measured, not assumed; the three false entries carry the
# defect that makes them unusable.
$artifacts = @(
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-round-cancel.patch'
        Length = 84743
        Sha256 = '8BD061184BB98B48FCA1946DCAF1C8AE6707FB404541640F744A6A0B5AA9B26C'
        Usable = $true
        Defect = ''
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch'
        Length = 414208
        Sha256 = '2077D440481D64BD08B9A890C318D3CDFABADFE0E1398C28CAF3A3AB8B76CD86'
        Usable = $true
        Defect = ''
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-context-correlation-sanitizer.patch'
        Length = 2541
        Sha256 = 'BA38C5F13670DECEEDAB3F0BFE9473AE7FB3BE1DE1A652A26E80E046F572B59E'
        Usable = $true
        Defect = ''
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-session-header.patch'
        Length = 801
        Sha256 = 'FD6711F3716DFE926DBAF053F66C04E44CA3E6B4FEB28151193D49965DD4D273'
        Usable = $true
        Defect = ''
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-broadcast-meta-filter-20260809.patch'
        Length = 1888
        Sha256 = 'F1BA41639A814C9B92162CF2ADD4C8633660D6131BB7257B3B9DBFA230E6331A'
        Usable = $false
        Defect = 'BareHunkHeader'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source-retry.patch'
        Length = 198939
        Sha256 = 'B6F24532FA7821B623B74F8EAA9DBABAF2774E8A91FFB0E1C1D55AF67B7B0038'
        Usable = $false
        Defect = 'LostKorean'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source-retry-normalized.patch'
        Length = 200223
        Sha256 = '63D231990D44124E6D3641E1A3B68660FD25BF05461395C26E5A2A7DF2D96FB6'
        Usable = $false
        Defect = 'LostKorean'
    }
)

foreach ($artifact in $artifacts) {
    $path = Join-Path $root $artifact.Path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing patch artifact: $($artifact.Path)"
    }

    $file = Get-Item -LiteralPath $path
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Patch artifact is a reparse point: $($artifact.Path)"
    }
    if ([int64]$file.Length -ne [int64]$artifact.Length) {
        throw "Patch size mismatch: $($artifact.Path)"
    }

    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($hash -ne $artifact.Sha256) {
        throw "Patch hash mismatch: $($artifact.Path)"
    }

    # Both defects are visible in the bytes, so the usable/unusable split is
    # checked here rather than only by the opt-in base-checkout verifier that
    # CI never runs. A hunk header without line numbers makes git reject the
    # whole file, and a run of question marks is what is left where Korean
    # source lines used to be.
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $bareHunk = [regex]::IsMatch($text, '(?m)^@@\s*$')
    $lostKorean = [regex]::IsMatch($text, '\?{3,}')

    switch ($artifact.Defect) {
        'BareHunkHeader' {
            if (-not $bareHunk) {
                throw "Recorded bare hunk header is gone; re-verify and update the manifest: $($artifact.Path)"
            }
        }
        'LostKorean' {
            if (-not $lostKorean) {
                throw "Recorded lost Korean is gone; re-verify and update the manifest: $($artifact.Path)"
            }
        }
        default {
            if ($bareHunk) {
                throw "Hunk header without line numbers: $($artifact.Path)"
            }
            if ($lostKorean) {
                throw "Korean replaced by question marks: $($artifact.Path)"
            }
        }
    }
}

$workflowPath = Join-Path $root '.github/workflows/remediation-checkpoint.yml'
if (-not (Test-Path -LiteralPath $workflowPath -PathType Leaf)) {
    throw 'Missing checkpoint workflow.'
}
$workflow = Get-Content -LiteralPath $workflowPath -Raw
if ($workflow -notmatch 'actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09' -or
    $workflow -notmatch 'actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444' -or
    $workflow -match 'actions/(checkout|setup-node)@v[0-9]' -or
    $workflow -notmatch 'git diff --check' -or
    $workflow -notmatch 'git diff-tree --check --no-commit-id -r \$env:CHECK_HEAD' -or
    $workflow -notmatch 'CHECK_BEFORE' -or
    $workflow -notmatch 'CHECK_BASE' -or
    $workflow -notmatch 'fetch-depth: 0' -or
    $workflow -notmatch [regex]::Escape(':(exclude)airi_docs/patches/*.patch')) {
    throw 'Checkpoint workflow contract failed.'
}

Write-Output 'Patch manifest contract: PASS (offline, no archive access).'
