param(
    [string]$Python = (Join-Path $PSScriptRoot '..\external\GPT-SoVITS\.venv\Scripts\python.exe')
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$gptRoot = Join-Path $repoRoot 'external\GPT-SoVITS'
$sitePackages = & $Python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "GPT-SoVITS Python not found: $Python"
}

& $Python -m pip install --only-binary=:all: --no-deps python-mecab-ko==1.2.9 python-mecab-ko-dic
if ($LASTEXITCODE -ne 0) { throw 'Failed to install Windows MeCab wheels.' }
& $Python -m pip install --only-binary=:all: --no-deps regex defusedxml joblib
if ($LASTEXITCODE -ne 0) { throw 'Failed to install Korean G2P support dependencies.' }

$compatDir = Join-Path $sitePackages 'eunjeon'
New-Item -ItemType Directory -Force -Path $compatDir | Out-Null
$compat = @'
"""GPT-SoVITS Windows adapter: eunjeon.Mecab -> mecab.MeCab."""
from mecab import MeCab as Mecab

__all__ = ["Mecab"]
'@
Set-Content -LiteralPath (Join-Path $compatDir '__init__.py') -Value $compat -Encoding utf8

$env:PYTHONPATH = "$gptRoot;$($gptRoot)\GPT_SoVITS;$($env:PYTHONPATH)"
& $Python -c "from text import korean; print(korean.g2p('안녕하세요. 아이리입니다.'))"
if ($LASTEXITCODE -ne 0) { throw 'Korean G2P verification failed.' }

Write-Output "Windows Korean G2P adapter is ready: $compatDir"
