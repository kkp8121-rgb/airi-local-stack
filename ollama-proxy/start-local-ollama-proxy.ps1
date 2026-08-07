# Environment variables read by ollama_proxy.py. Start-Process inherits this
# shell's environment, so set them in the same session before running this
# script - no argument plumbing is needed.
#
#   $env:AIRI_LLM_MODE = 'local'
#       local (default)  local EXAONE, unchanged path
#       cloud            codex CLI subscription - needs a logged-in codex, no key
#       hybrid           cloud + a local reflex reaction raced against it
#       cloud_anthropic  Anthropic API - needs ANTHROPIC_API_KEY
#       open             OpenAI-compatible endpoint - needs OPENROUTER_API_KEY
#
#   $env:ANTHROPIC_API_KEY  = '<your-anthropic-key>'   # cloud_anthropic
#   $env:OPENROUTER_API_KEY = '<your-openrouter-key>'  # open
#   $env:AIRI_CODEX_EXECUTABLE = '<path-to-codex>'     # optional override
#   $env:KRW_PER_USD = '1400'       # bench-llm-modes.py cost conversion
#
# Never commit real keys, and never hardcode them in this file. Per-mode model,
# reasoning effort, pricing and timeout settings live in llm_modes.json.
#
# An external mode refuses to start when its prerequisite is missing - an API
# key for key-based providers, an installed codex CLI for codex-cli (privacy
# opt-in) - and on success the proxy logs one line naming the destination that
# will receive the conversation text.

param(
    [ValidateRange(512, 32768)]
    [int]$NumCtx = 2048
)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$stackRoot = Split-Path -Parent $repo
$server = Join-Path $repo 'ollama_proxy.py'
$stdoutLog = Join-Path $repo 'ollama-proxy.out.log'
$stderrLog = Join-Path $repo 'ollama-proxy.err.log'

# Interpreter candidates in priority order: explicit override, this project's
# own venv, the shared chatterbox venv, then whatever is on PATH.
$candidates = @()
if ($env:AIRI_STACK_PYTHON) { $candidates += $env:AIRI_STACK_PYTHON }
$candidates += Join-Path $repo '.venv\Scripts\python.exe'
$candidates += Join-Path $stackRoot 'chatterbox\.venv\Scripts\python.exe'

$python = $null
foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath) {
        Write-Warning "No project virtual environment found; falling back to '$($onPath.Source)' from PATH. Install fastapi, uvicorn and httpx there if startup fails."
        $python = $onPath.Source
    }
}

if (-not $python) {
    throw "Python interpreter not found. Set AIRI_STACK_PYTHON, or create a virtual environment at '$(Join-Path $repo '.venv')' or '$(Join-Path $stackRoot 'chatterbox\.venv')'."
}

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output "A service is already listening on port 11435 (PID $($listener.OwningProcess))."
    exit 0
}

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $server, '--host', '127.0.0.1', '--port', '11435', '--upstream', 'http://127.0.0.1:11434', '--num-ctx', $NumCtx `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output "Started AIRI Ollama compatibility proxy (PID $($process.Id))."
