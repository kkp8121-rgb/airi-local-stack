[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$artifacts = @(
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-round-cancel.patch'
        Length = 84743
        Sha256 = '8BD061184BB98B48FCA1946DCAF1C8AE6707FB404541640F744A6A0B5AA9B26C'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch'
        Length = 414208
        Sha256 = '2077D440481D64BD08B9A890C318D3CDFABADFE0E1398C28CAF3A3AB8B76CD86'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-context-correlation-sanitizer.patch'
        Length = 2541
        Sha256 = 'BA38C5F13670DECEEDAB3F0BFE9473AE7FB3BE1DE1A652A26E80E046F572B59E'
    }
)

foreach ($artifact in $artifacts) {
    $path = Join-Path $root $artifact.Path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing patch artifact: $($artifact.Path)"
    }

    $file = Get-Item -LiteralPath $path
    if ([int64]$file.Length -ne [int64]$artifact.Length) {
        throw "Patch size mismatch: $($artifact.Path)"
    }

    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($hash -ne $artifact.Sha256) {
        throw "Patch hash mismatch: $($artifact.Path)"
    }
}

Write-Output 'Patch manifest contract: PASS (offline, no archive access).'
