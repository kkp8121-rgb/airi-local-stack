param(
    [ValidateRange(512, 32768)]
    [int]$NumCtx = 2048,
    [ValidateRange(0, 999)]
    # Ollama interprets num_gpu=0 as CPU-only. AIRI's local model is small
    # enough to fully offload on the supported local GPU; callers can still
    # override this explicitly when diagnosing a CPU-only environment.
    [int]$NumGpu = 999,
    # Keep the foreground model resident between normal chat turns. This must
    # also be used by warmup and the post-turn evaluator.
    [string]$OllamaKeepAlive = '30m',
    [ValidateRange(0.0, 2.0)]
    [double]$OllamaTemperature = 0.45,
    [ValidateRange(0.0, 1.0)]
    [double]$OllamaTopP = 0.9,
    [ValidateRange(0.0, 2.0)]
    [double]$OllamaRepeatPenalty = 1.05,
    [bool]$EnableMemory = $true,
    [bool]$EnableKnowledge = $true,
    [string]$MemoryEmbedModel = 'nlpai-lab/KURE-v1',
    [ValidateSet('auto', 'cpu', 'cuda')]
    [string]$MemoryEmbedDevice = 'cuda',
    [string]$MemorySession = '',
    [ValidateSet('ollama', 'openai', 'anthropic')]
    [string]$MemoryExtractionProvider = 'ollama',
    [bool]$AllowExternalMemoryExtraction = $false,
    [string]$MemoryExtractionModel = '',
    [string]$MemoryExtractionGateReport = '',
    # Gate threshold profile. 'balanced' keeps every structural metric at 1.0
    # and only relaxes the model-judgement metrics; 'strict' restores the
    # original all-1.0 contract.
    [ValidateSet('strict', 'balanced')]
    [string]$MemoryExtractionGateProfile = 'balanced',
    [switch]$VerifyExtractionGateOnly,
    [uri]$MemoryExtractionUpstream = 'http://127.0.0.1:11436',
    [string]$MemoryExtractionKeepAlive = '5m',
    [ValidateSet('local', 'openai', 'anthropic')]
    [string]$ChatProvider = 'local',
    [bool]$AllowExternalChat = $false,
    # For the local provider, an omitted value resolves to the stable runtime
    # tag. Specify -ChatModel exaone-airi:2.4b for a reversible rollback.
    [string]$ChatModel = '',
    # Optional approved artifact digest for the selected chat model. Supplying
    # it (directly or through AIRI_CHAT_MODEL_DIGEST) makes both this preflight
    # and the proxy's own startup check fail closed on a rebuilt tag.
    [string]$ChatModelDigest = $env:AIRI_CHAT_MODEL_DIGEST,
    # The root stack launcher runs the same local-tag preflight before it
    # starts any downstream service, then supplies this switch to avoid doing
    # the identical checks a second time.
    [switch]$ChatModelPreflighted,
    [bool]$AllowExternalSearch = $false,
    [string]$TopicBoardPath = '',
    [bool]$EnableEvaluation = $false,
    [bool]$EnableCharacterEvaluator = $false,
    [ValidateRange(1, 1000000)]
    [int]$EvaluationMaxRecords = 10000
)

$ErrorActionPreference = 'Stop'
$effectiveChatModel = if ($ChatProvider -eq 'local' -and [string]::IsNullOrWhiteSpace($ChatModel)) {
    'midm-airi:2.0-mini'
} else {
    $ChatModel
}
$effectiveEvaluatorModel = if ($ChatProvider -eq 'local') {
    $effectiveChatModel
} else {
    'midm-airi:2.0-mini'
}
$repo = $PSScriptRoot
$stackRoot = Split-Path -Parent $repo
$server = Join-Path $repo 'ollama_proxy.py'
$stdoutLog = Join-Path $repo 'ollama-proxy.out.log'
$stderrLog = Join-Path $repo 'ollama-proxy.err.log'

$requiredLocalModels = @()
if (-not $VerifyExtractionGateOnly) {
    if ($ChatProvider -eq 'local') {
        $requiredLocalModels += $effectiveChatModel
    }
    if ($EnableCharacterEvaluator) {
        $requiredLocalModels += $effectiveEvaluatorModel
    }
}
if (-not $ChatModelPreflighted) {
    foreach ($model in @($requiredLocalModels | Sort-Object -Unique)) {
        # The digest pin describes the chat model artifact only; an evaluator
        # on a different tag keeps the plain name check.
        $expectedDigest = if ($model -ceq $effectiveChatModel) { $ChatModelDigest } else { '' }
        & (Join-Path $repo 'setup-midm-airi-model.ps1') -Model $model -PreflightOnly -ExpectedDigest $expectedDigest
    }
}
$resolvedTopicBoardPath = ''
if (-not [string]::IsNullOrWhiteSpace($TopicBoardPath)) {
    $topicItem = Get-Item -LiteralPath $TopicBoardPath -ErrorAction Stop
    if ($topicItem.PSIsContainer) {
        throw 'Topic board must be a regular JSON file.'
    }
    $runtimeRoot = [IO.Path]::GetFullPath((Join-Path $repo 'runtime')).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $topicFullPath = [IO.Path]::GetFullPath($topicItem.FullName)
    $runtimePrefix = $runtimeRoot + [IO.Path]::DirectorySeparatorChar
    if (-not $topicFullPath.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Topic board must be inside ollama-proxy\runtime.'
    }
    $resolvedTopicBoardPath = $topicFullPath
}

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

# A supplied board is an explicit startup opt-in. Validate it with the same
# interpreter before any existing proxy can be reused or a new one is started.
if (-not [string]::IsNullOrWhiteSpace($resolvedTopicBoardPath)) {
    $topicBoardValidator = Join-Path $repo 'validate_approved_topics.py'
    if (-not (Test-Path -LiteralPath $topicBoardValidator -PathType Leaf)) {
        throw 'Topic board startup validator is missing.'
    }
    & $python $topicBoardValidator --board $resolvedTopicBoardPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Topic board startup validation failed.'
    }
}

function Resolve-LocalOllamaModelDigest {
    param([Parameter(Mandatory)][string]$Model)

    function Normalize-OllamaModelName([string]$Name) {
        $value = $Name.Trim().ToLowerInvariant()
        $leaf = $value.Substring($value.LastIndexOf('/') + 1)
        if ($leaf -notmatch ':') { $value = "$value`:latest" }
        return $value
    }

    try {
        $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 -ErrorAction Stop
        $wanted = Normalize-OllamaModelName $Model
        $matches = @($tags.models | Where-Object {
            if (-not $_) { $false }
            else {
                $candidate = [string]$_.name
                if ([string]::IsNullOrWhiteSpace($candidate)) { $candidate = [string]$_.model }
                -not [string]::IsNullOrWhiteSpace($candidate) -and (Normalize-OllamaModelName $candidate) -eq $wanted
            }
        })
    }
    catch {
        throw 'Local model digest lookup failed.'
    }
    if ($matches.Count -ne 1) { throw 'Local model digest lookup did not resolve exactly one model.' }
    $digest = [string]$matches[0].digest
    if ($digest -notmatch '^[0-9a-fA-F]{64}$') { throw 'Local model digest is invalid.' }
    return $digest.ToLowerInvariant()
}

if ($VerifyExtractionGateOnly -and [string]::IsNullOrWhiteSpace($MemoryExtractionModel)) {
    throw 'VerifyExtractionGateOnly requires MemoryExtractionModel.'
}

if (-not [string]::IsNullOrWhiteSpace($MemoryExtractionModel)) {
    if ($MemoryExtractionProvider -ne 'ollama') {
        throw 'Memory extraction gate requires the local ollama provider.'
    }
    if ([string]::IsNullOrWhiteSpace($MemoryExtractionGateReport)) {
        throw 'MemoryExtractionGateReport is required when MemoryExtractionModel is set.'
    }
    if (-not (Test-Path -LiteralPath $MemoryExtractionGateReport -PathType Leaf)) {
        throw 'MemoryExtractionGateReport does not exist.'
    }
    $extractionGateVerifier = Join-Path $repo 'verify_extraction_gate.py'
    $extractionFixtures = Join-Path $repo 'memory_benchmark_fixtures.json'
    if (-not (Test-Path -LiteralPath $extractionGateVerifier -PathType Leaf)) {
        throw 'Memory extraction gate verifier is missing.'
    }
    if (-not (Test-Path -LiteralPath $extractionFixtures -PathType Leaf)) {
        throw 'Memory extraction benchmark fixtures are missing.'
    }
    $memoryExtractionModelDigest = Resolve-LocalOllamaModelDigest -Model $MemoryExtractionModel
    & $python $extractionGateVerifier --report $MemoryExtractionGateReport --fixtures $extractionFixtures --model $MemoryExtractionModel --model-digest $memoryExtractionModelDigest --profile $MemoryExtractionGateProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Memory extraction operational gate verification failed.'
    }
}

if ($VerifyExtractionGateOnly) {
    Write-Output 'Memory extraction operational gate verified.'
    return
}

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    if (-not [string]::IsNullOrWhiteSpace($MemoryExtractionModel)) {
        throw 'Existing proxy cannot be reused for memory extraction.'
    }
    if (-not [string]::IsNullOrWhiteSpace($resolvedTopicBoardPath)) {
        throw 'Existing proxy cannot be reused with TopicBoardPath; stop it and restart so the approved board is loaded.'
    }
    Write-Output 'A service is already listening on port 11435; it was not reconfigured.'
    exit 0
}

$memoryEnvironment = @{
    AIRI_MEMORY_ENABLED = if ($EnableMemory) { '1' } else { '0' }
    AIRI_KNOWLEDGE_ENABLED = if ($EnableKnowledge) { '1' } else { '0' }
    # KURE query embeddings share the foreground GPU with Ollama. A timed-out
    # Python worker cannot cancel an in-flight CUDA encode, so approved public
    # knowledge uses deterministic title/alias/FTS retrieval by default.
    AIRI_KNOWLEDGE_ALLOW_SEMANTIC = '0'
    AIRI_KNOWLEDGE_DB = Join-Path $repo 'runtime\airi-knowledge.sqlite3'
    AIRI_MEMORY_DB = Join-Path $repo 'runtime\airi-memory.sqlite3'
    # Keep the base scope stable across proxy restarts. MemoryRuntime rotates a
    # genuinely different no-header history to a UUID child and can recover a
    # unique 2+ turn tail; a fresh GUID here would orphan every prior scope and
    # create another canon snapshot on each launch.
    AIRI_MEMORY_SESSION = if ($MemorySession) { $MemorySession } else { 'broadcast-default' }
    AIRI_MEMORY_EMBED_MODEL = if ($EnableMemory) { $MemoryEmbedModel } else { '' }
    AIRI_MEMORY_EMBED_DEVICE = $MemoryEmbedDevice
    AIRI_MEMORY_CACHE = '1'
    AIRI_MEMORY_CANON_BUNDLE = Join-Path $repo 'airi-canon.json'
    AIRI_MEMORY_EXTRACTION_PROVIDER = $MemoryExtractionProvider
    AIRI_MEMORY_ALLOW_EXTERNAL_EXTRACTION = if ($AllowExternalMemoryExtraction) { '1' } else { '0' }
    AIRI_MEMORY_EXTRACTION_MODEL = $MemoryExtractionModel
    AIRI_MEMORY_EXTRACTION_UPSTREAM = $MemoryExtractionUpstream.AbsoluteUri.TrimEnd('/')
    AIRI_MEMORY_EXTRACTION_KEEP_ALIVE = $MemoryExtractionKeepAlive
    AIRI_MEMORY_EXTRACTION_NUM_CTX = '8192'
    AIRI_MEMORY_EXTRACTION_NUM_GPU = '0'
    AIRI_MEMORY_EXTRACTION_SEED = '42'
    AIRI_MEMORY_EXTRACTION_MAX_TOKENS = '2048'
    AIRI_MEMORY_EXTRACTION_BATCH_MESSAGES = '60'
    AIRI_MEMORY_EXTRACTION_BATCH_CHARS = '24000'
    AIRI_CHAT_PROVIDER = $ChatProvider
    AIRI_ALLOW_EXTERNAL_CHAT = if ($AllowExternalChat) { '1' } else { '0' }
    AIRI_CHAT_MODEL = $effectiveChatModel
    # Empty means "no pin": the proxy then records the digest it observed
    # instead of refusing to start.
    AIRI_CHAT_MODEL_DIGEST = $ChatModelDigest
    AIRI_OLLAMA_KEEP_ALIVE = $OllamaKeepAlive
    AIRI_OLLAMA_TEMPERATURE = $OllamaTemperature.ToString([Globalization.CultureInfo]::InvariantCulture)
    AIRI_OLLAMA_TOP_P = $OllamaTopP.ToString([Globalization.CultureInfo]::InvariantCulture)
    AIRI_OLLAMA_REPEAT_PENALTY = $OllamaRepeatPenalty.ToString([Globalization.CultureInfo]::InvariantCulture)
    AIRI_ALLOW_EXTERNAL_SEARCH = if ($AllowExternalSearch) { '1' } else { '0' }
    AIRI_TOPIC_BOARD_PATH = $resolvedTopicBoardPath
    # Evaluation retention is a separate explicit opt-in. Chat never writes
    # to this DB automatically; each record also requires consent=true.
    AIRI_EVAL_ENABLED = if ($EnableEvaluation) { 'true' } else { 'false' }
    # Provenance must name the model that actually answered, including after a
    # -ChatModel rollback or an approved external provider.
    AIRI_EVAL_MODEL = $effectiveChatModel
    AIRI_EVAL_DB = Join-Path $repo 'runtime\airi-evaluations.sqlite3'
    AIRI_EVAL_MAX_RECORDS = $EvaluationMaxRecords.ToString([Globalization.CultureInfo]::InvariantCulture)
    AIRI_CHARACTER_EVALUATOR_ENABLED = if ($EnableCharacterEvaluator) { '1' } else { '0' }
    AIRI_CHARACTER_EVALUATOR_PROVIDER = 'ollama'
    # For local chat, keep the evaluator on the same selected model so a
    # -ChatModel rollback applies consistently to the entire local path.
    AIRI_CHARACTER_EVALUATOR_MODEL = $effectiveEvaluatorModel
    AIRI_CHARACTER_EVALUATOR_UPSTREAM = 'http://127.0.0.1:11434'
    AIRI_CHARACTER_EVALUATOR_NUM_CTX = '2048'
    AIRI_CHARACTER_EVALUATOR_NUM_GPU = $NumGpu.ToString([Globalization.CultureInfo]::InvariantCulture)
    AIRI_CHARACTER_EVALUATOR_KEEP_ALIVE = $OllamaKeepAlive
    AIRI_CHARACTER_EVALUATOR_TIMEOUT_SECONDS = '15'
    AIRI_CHARACTER_EVALUATOR_MAX_TOKENS = '320'
    # Post-turn state observation is deliberately idle-only so it does not
    # take Ollama's sole runner from the next foreground chat request.
    AIRI_CHARACTER_EVALUATOR_IDLE_DELAY_SECONDS = '6'
    AIRI_USAGE_LEDGER_PATH = Join-Path $repo 'runtime\provider-usage.sqlite3'
    HF_HUB_OFFLINE = '1'
    HF_HUB_DISABLE_PROGRESS_BARS = '1'
    TRANSFORMERS_OFFLINE = '1'
    TRANSFORMERS_VERBOSITY = 'error'
}
$previousEnvironment = @{}
foreach ($name in $memoryEnvironment.Keys) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $memoryEnvironment[$name], 'Process')
}
try {
    $process = Start-Process `
        -FilePath $python `
        -ArgumentList $server, '--host', '127.0.0.1', '--port', '11435', '--upstream', 'http://127.0.0.1:11434', '--num-ctx', $NumCtx, '--num-gpu', $NumGpu `
        -WorkingDirectory $repo `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru
}
finally {
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
}

Write-Output "Started AIRI Ollama compatibility proxy (PID $($process.Id), memory=$EnableMemory, extraction=$MemoryExtractionProvider/$([bool]$MemoryExtractionModel), chat=$ChatProvider/$effectiveChatModel, externalSearch=$AllowExternalSearch, evaluation=$EnableEvaluation, characterEvaluator=$EnableCharacterEvaluator/$effectiveEvaluatorModel)."
