$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$gptRoot = Join-Path $projectRoot 'external\GPT-SoVITS'
$python = Join-Path $gptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "GPT-SoVITS environment not found: $python" }
New-Item -ItemType Directory -Force -Path (Join-Path $gptRoot 'GPT_SoVITS\pretrained_models\fast_langdetect') | Out-Null

function Test-Port([int]$Port) {
  return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

if (-not (Test-Port 11434)) {
  $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
  if (-not $ollama) { throw 'ollama.exe was not found in PATH' }
  Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
  Start-Sleep -Seconds 2
}

if (-not (Test-Port 9880)) {
  $env:PYTHONPATH = "$gptRoot;$gptRoot\GPT_SoVITS"
  $env:PYTHONIOENCODING = 'utf-8'
  $out = Join-Path $PSScriptRoot 'api-v2proplus.out.log'
  $err = Join-Path $PSScriptRoot 'api-v2proplus.err.log'
  Start-Process -FilePath $python -ArgumentList '-u','api_v2.py','-a','127.0.0.1','-p','9880','-c',(Join-Path $PSScriptRoot 'tts-infer-v2proplus.yaml') -WorkingDirectory $gptRoot -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
}

if (-not (Test-Port 8880)) {
  $out = Join-Path $PSScriptRoot 'proxy.out.log'
  $err = Join-Path $PSScriptRoot 'proxy.err.log'
  Start-Process -FilePath $python -ArgumentList '-u',(Join-Path $PSScriptRoot 'openai_compatible_proxy.py'),'--host','127.0.0.1','--port','8880' -WorkingDirectory $projectRoot -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
}

Start-Sleep -Seconds 2
$ports = 11434, 9880, 8880 | ForEach-Object { [pscustomobject]@{ Port = $_; Listening = Test-Port $_ } }
$ports | Format-Table -AutoSize
if (@($ports | Where-Object { -not $_.Listening }).Count -gt 0) {
  $missing = ($ports | Where-Object { -not $_.Listening } | ForEach-Object Port) -join ', '
  throw "Local stack failed to open port(s): $missing"
}
Write-Output 'AIRI OpenAI Compatible Speech Base URL: http://127.0.0.1:8880/v1'
