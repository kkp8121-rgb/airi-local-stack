param(
    [string]$Model = 'small',
    [ValidateSet('cuda', 'cpu')]
    [string]$Device = 'cuda',
    [string]$ComputeType = 'float16',
    [ValidateRange(1, 32)]
    [int]$CpuThreads = 8,
    [switch]$EnableDebugAudio
)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$repoRoot = Split-Path -Parent $PSScriptRoot
$server = Join-Path $repo 'openai_stt_server.py'
$modelRoot = Join-Path $repo 'models'
$stdoutLog = Join-Path $repo 'stt-server.out.log'
$stderrLog = Join-Path $repo 'stt-server.err.log'

# CPU inference cannot use float16, so a caller who only asked for -Device cpu gets int8
# instead of a startup failure. An explicit -ComputeType always wins.
if ($Device -eq 'cpu' -and -not $PSBoundParameters.ContainsKey('ComputeType')) {
    $ComputeType = 'int8'
    Write-Output 'Device is cpu, so compute type defaults to int8.'
}

# Python candidates in priority order. The repo ships no virtual environment, so a fresh
# clone falls through to whatever python is on PATH instead of failing outright.
$pythonCandidates = @()
if ($env:AIRI_STT_PYTHON) {
    $pythonCandidates += $env:AIRI_STT_PYTHON
}
$pythonCandidates += (Join-Path $repo '.venv\Scripts\python.exe')
$pythonCandidates += (Join-Path $repoRoot 'chatterbox\.venv\Scripts\python.exe')

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    $pathPython = Get-Command python -ErrorAction SilentlyContinue
    if ($pathPython) {
        $python = $pathPython.Source
        Write-Warning "No project virtual environment found. Falling back to the python on PATH: $python"
    }
}
if (-not $python) {
    throw "Python environment not found. Checked: $($pythonCandidates -join ', '), and python on PATH. Set AIRI_STT_PYTHON to override."
}

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8890 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Output "A service is already listening on port 8890 (PID $($listener.OwningProcess))."
    exit 0
}

if ($Device -eq 'cuda') {
    # ctranslate2 loads cuBLAS 12 and cuDNN 9 from a torch install; both have to be present
    # in the same directory or CUDA startup fails after the process is already detached.
    $cudaCandidates = @()
    if ($env:AIRI_CUDA_TORCH_LIB) {
        $cudaCandidates += $env:AIRI_CUDA_TORCH_LIB
    }
    $pythonHome = Split-Path -Parent (Split-Path -Parent $python)
    $cudaCandidates += (Join-Path $pythonHome 'Lib\site-packages\torch\lib')
    $cudaCandidates += (Join-Path $repoRoot 'external\GPT-SoVITS\.venv\Lib\site-packages\torch\lib')
    $cudaCandidates += (Join-Path (Split-Path -Parent $repoRoot) 'external\GPT-SoVITS\.venv\Lib\site-packages\torch\lib')

    $cudaRuntime = $null
    foreach ($candidate in $cudaCandidates) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        $hasCublas = Test-Path -LiteralPath (Join-Path $candidate 'cublas64_12.dll')
        $hasCudnn = Test-Path -LiteralPath (Join-Path $candidate 'cudnn_ops64_9.dll')
        if (-not $hasCudnn) {
            $hasCudnn = @(Get-ChildItem -LiteralPath $candidate -Filter 'cudnn*64_9.dll' -ErrorAction SilentlyContinue).Count -gt 0
        }
        if ($hasCublas -and $hasCudnn) {
            $cudaRuntime = $candidate
            break
        }
    }

    if (-not $cudaRuntime) {
        $checked = $cudaCandidates -join "`n  "
        throw "CUDA is unavailable: no directory below contains both cublas64_12.dll and a cuDNN 9 DLL.`n  $checked`nSet AIRI_CUDA_TORCH_LIB to a torch\lib directory that has them, or run this script with -Device cpu -ComputeType int8."
    }

    Write-Output "Using CUDA runtime DLLs from: $cudaRuntime"
    $env:PATH = "$cudaRuntime;$env:PATH"
}

$serverArguments = @(
    $server,
    '--host', '127.0.0.1',
    '--port', '8890',
    '--model', $Model,
    '--model-root', $modelRoot,
    '--device', $Device,
    '--compute-type', $ComputeType,
    '--cpu-threads', $CpuThreads
)
if ($EnableDebugAudio) {
    $debugAudioRoot = Join-Path $repo 'debug-recordings'
    $serverArguments += @('--debug-audio-dir', $debugAudioRoot)
    Write-Warning 'Debug audio persistence is enabled. Uploaded microphone audio will be saved locally.'
}

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $serverArguments `
    -WorkingDirectory $repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Output "Started AIRI local STT server (PID $($process.Id))."

$ready = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8890/health' -TimeoutSec 2
        if ($health.status -eq 'ok') {
            $ready = $true
            Write-Output "AIRI local STT ready (model=$($health.model), device=$($health.device), threads=$($health.cpu_threads))."
            break
        }
    } catch {
        # The model may still be loading; keep polling until the bounded timeout.
    }
}
if (-not $ready) {
    throw 'AIRI local STT did not become ready within 60 seconds. Check stt-server.err.log.'
}
