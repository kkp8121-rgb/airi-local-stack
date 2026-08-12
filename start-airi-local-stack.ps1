param(
    [string]$SttModel = 'mobiuslabsgmbh/faster-whisper-large-v3-turbo',
    [string]$SttComputeType = 'int8_float16',
    [ValidateRange(0, 999)]
    # Keep the local chat model on the GPU by default.  num_gpu=0 forces
    # CPU-only inference and makes first-token latency several seconds slower.
    [int]$OllamaNumGpu = 999,
    # Keep the foreground Ollama runner loaded across normal chat gaps.
    [string]$OllamaKeepAlive = '30m',
    [bool]$EnableKnowledge = $true,
    [ValidateSet('ollama', 'openai', 'anthropic')]
    [string]$MemoryExtractionProvider = 'ollama',
    [bool]$AllowExternalMemoryExtraction = $false,
    # Operational default: promote conversation to memory whenever an approved
    # gate report exists. Pass $false to keep the extractor off entirely.
    [bool]$EnableMemoryExtraction = $true,
    [string]$MemoryExtractionModel = '',
    [string]$MemoryExtractionGateReport = '',
    # Gate thresholds used by verify_extraction_gate.py. 'balanced' keeps every
    # structural metric at 1.0 and relaxes only the model-judgement metrics.
    [ValidateSet('strict', 'balanced')]
    [string]$MemoryExtractionGateProfile = 'balanced',
    [ValidateRange(1024, 65535)]
    [int]$MemoryExtractionPort = 11436,
    [ValidateSet('local', 'openai', 'anthropic')]
    [string]$ChatProvider = 'local',
    [bool]$AllowExternalChat = $false,
    # For the local provider, an omitted value resolves to the stable runtime
    # tag. Pass -ChatModel exaone-airi:2.4b to roll back without changing files.
    [string]$ChatModel = '',
    # Optional approved artifact digest for the selected chat model. Supplying
    # it (directly or through AIRI_CHAT_MODEL_DIGEST) makes startup fail closed
    # when the tag was rebuilt from other bytes.
    [string]$ChatModelDigest = $env:AIRI_CHAT_MODEL_DIGEST,
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

function Wait-LocalHealth {
    param(
        [Parameter(Mandatory)]
        [string]$Uri,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            return Invoke-RestMethod -Uri $Uri -TimeoutSec 3
        }
        catch {
            Start-Sleep -Seconds 1
        }
    } while ((Get-Date) -lt $deadline)

    throw "Local service did not become ready within $TimeoutSeconds seconds: $Uri"
}

$ollamaListener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if (-not $ollamaListener) {
    $ollama = Get-Command ollama -ErrorAction Stop
    Start-Process `
        -FilePath $ollama.Source `
        -ArgumentList 'serve' `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $PSScriptRoot 'ollama-proxy\ollama-serve.out.log') `
        -RedirectStandardError (Join-Path $PSScriptRoot 'ollama-proxy\ollama-serve.err.log')
}

# Do not let a missing model turn into a late first-chat failure after the
# other local services have started.  This only reads Ollama's local tag list;
# it never pulls a model or contacts Hugging Face.
$requiredLocalModels = @()
if ($ChatProvider -eq 'local') {
    $requiredLocalModels += $effectiveChatModel
}
if ($EnableCharacterEvaluator) {
    $requiredLocalModels += $effectiveEvaluatorModel
}
if ($requiredLocalModels.Count -gt 0) {
    $null = Wait-LocalHealth -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSeconds 30
    foreach ($model in @($requiredLocalModels | Sort-Object -Unique)) {
        # The digest pin describes the chat model artifact only; an evaluator
        # on a different tag keeps the plain name check.
        $expectedDigest = if ($model -ceq $effectiveChatModel) { $ChatModelDigest } else { '' }
        & (Join-Path $PSScriptRoot 'ollama-proxy\setup-midm-airi-model.ps1') `
            -Model $model -PreflightOnly -ExpectedDigest $expectedDigest
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
    catch { throw 'Local model digest lookup failed.' }
    if ($matches.Count -ne 1) { throw 'Local model digest lookup did not resolve exactly one model.' }
    $digest = [string]$matches[0].digest
    if ($digest -notmatch '^[0-9a-fA-F]{64}$') { throw 'Local model digest is invalid.' }
    return $digest.ToLowerInvariant()
}

if (-not [string]::IsNullOrWhiteSpace($MemoryExtractionModel)) {
    $existingProxyListener = Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue
    if ($existingProxyListener) {
        throw 'Existing proxy must be restarted before enabling memory extraction.'
    }
}

# Operational default for the conversation-to-memory promotion loop. The gate
# report is the single source of truth for which model passed, so an approved
# report at the conventional path activates extraction without any flag. This
# resolution stays fail-open: a missing, unreadable or failing report leaves the
# established OFF path untouched instead of blocking the whole stack. An
# explicit -MemoryExtractionModel keeps the original fail-closed contract above.
$memoryExtractionAutoEnabled = $false
if ($EnableMemoryExtraction -and [string]::IsNullOrWhiteSpace($MemoryExtractionModel) `
        -and $MemoryExtractionProvider -eq 'ollama') {
    $autoGateReport = if ([string]::IsNullOrWhiteSpace($MemoryExtractionGateReport)) {
        Join-Path $PSScriptRoot 'ollama-proxy\runtime\extraction-gate-report.json'
    }
    else {
        $MemoryExtractionGateReport
    }
    $autoModel = ''
    if (-not (Test-Path -LiteralPath $autoGateReport -PathType Leaf)) {
        Write-Warning ("Memory extraction stays off: no extraction gate report at $autoGateReport. " +
            "Produce one with benchmark_memory_track.py --mode extraction --model <tag> --model-digest <sha256> --report <path>.")
    }
    elseif (Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue) {
        Write-Warning 'Memory extraction stays off: a proxy already listens on 11435. Stop it and rerun to enable extraction.'
    }
    else {
        try {
            $autoReport = Get-Content -LiteralPath $autoGateReport -Raw -Encoding utf8 | ConvertFrom-Json -ErrorAction Stop
            $autoModel = [string]$autoReport.config.model
        }
        catch {
            $autoModel = ''
        }
        if ([string]::IsNullOrWhiteSpace($autoModel)) {
            Write-Warning 'Memory extraction stays off: the extraction gate report does not name a model.'
        }
        else {
            # Read-only preflight of the same verifier the activation path runs.
            # Doing it here means a failing report degrades to OFF rather than
            # aborting startup for every other service.
            try {
                & (Join-Path $PSScriptRoot 'ollama-proxy\start-local-ollama-proxy.ps1') `
                    -MemoryExtractionProvider $MemoryExtractionProvider `
                    -MemoryExtractionModel $autoModel `
                    -MemoryExtractionGateReport $autoGateReport `
                    -MemoryExtractionGateProfile $MemoryExtractionGateProfile `
                    -VerifyExtractionGateOnly | Out-Null
                $MemoryExtractionModel = $autoModel
                $MemoryExtractionGateReport = $autoGateReport
                $memoryExtractionAutoEnabled = $true
            }
            catch {
                Write-Warning 'Memory extraction stays off: the extraction gate report did not verify.'
            }
        }
    }
}

& (Join-Path $PSScriptRoot 'latency-monitor\start-latency-monitor.ps1')
$latencyMonitor = Wait-LocalHealth -Uri 'http://127.0.0.1:8892/health' -TimeoutSeconds 15

if ([string]::IsNullOrWhiteSpace($MemoryExtractionModel)) {
    # The established OFF path does not perform an extraction gate check.
    & (Join-Path $PSScriptRoot 'ollama-proxy\start-local-ollama-proxy.ps1') `
        -NumGpu $OllamaNumGpu `
        -OllamaKeepAlive $OllamaKeepAlive `
        -EnableKnowledge $EnableKnowledge `
        -MemoryExtractionProvider $MemoryExtractionProvider `
        -AllowExternalMemoryExtraction $AllowExternalMemoryExtraction `
        -MemoryExtractionModel $MemoryExtractionModel `
        -MemoryExtractionGateReport $MemoryExtractionGateReport `
        -MemoryExtractionGateProfile $MemoryExtractionGateProfile `
        -MemoryExtractionUpstream "http://127.0.0.1:$MemoryExtractionPort" `
        -ChatProvider $ChatProvider `
        -AllowExternalChat $AllowExternalChat `
        -ChatModel $effectiveChatModel `
        -ChatModelDigest $ChatModelDigest `
        -ChatModelPreflighted `
        -AllowExternalSearch $AllowExternalSearch `
        -TopicBoardPath $TopicBoardPath `
        -EnableEvaluation $EnableEvaluation `
        -EnableCharacterEvaluator $EnableCharacterEvaluator `
        -EvaluationMaxRecords $EvaluationMaxRecords
}
elseif ($MemoryExtractionProvider -eq 'ollama') {
    # Verify first without listening on 11435. A pending proxy request can
    # therefore never reach an unverified or mismatched isolated extractor.
    & (Join-Path $PSScriptRoot 'ollama-proxy\start-local-ollama-proxy.ps1') `
        -NumGpu $OllamaNumGpu -MemoryExtractionProvider $MemoryExtractionProvider `
        -OllamaKeepAlive $OllamaKeepAlive `
        -EnableKnowledge $EnableKnowledge `
        -AllowExternalMemoryExtraction $AllowExternalMemoryExtraction -MemoryExtractionModel $MemoryExtractionModel `
        -MemoryExtractionGateReport $MemoryExtractionGateReport -MemoryExtractionUpstream "http://127.0.0.1:$MemoryExtractionPort" `
        -MemoryExtractionGateProfile $MemoryExtractionGateProfile `
        -ChatProvider $ChatProvider -AllowExternalChat $AllowExternalChat -ChatModel $effectiveChatModel -ChatModelPreflighted `
        -AllowExternalSearch $AllowExternalSearch -TopicBoardPath $TopicBoardPath -EnableEvaluation $EnableEvaluation `
        -EnableCharacterEvaluator $EnableCharacterEvaluator -EvaluationMaxRecords $EvaluationMaxRecords `
        -VerifyExtractionGateOnly

    try {
        $gateReport = Get-Content -LiteralPath $MemoryExtractionGateReport -Raw -Encoding utf8 | ConvertFrom-Json -ErrorAction Stop
        $gateModel = [string]$gateReport.config.model
        $expectedDigest = [string]$gateReport.config.model_digest
    }
    catch { throw 'Memory extraction gate report could not be revalidated.' }
    if ($gateModel -cne $MemoryExtractionModel -or $expectedDigest -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'Memory extraction gate report binding is invalid.'
    }
    $liveDigest = Resolve-LocalOllamaModelDigest -Model $MemoryExtractionModel
    if ($liveDigest -ine $expectedDigest) { throw 'Local model digest changed after gate verification.' }
    $extractorResult = $null
    try {
        $extractorResult = & (Join-Path $PSScriptRoot 'ollama-proxy\start-memory-extractor.ps1') `
            -Port $MemoryExtractionPort -Model $MemoryExtractionModel -ExpectedDigest $liveDigest
        if ($extractorResult.ModelVerified -ne $true -or $extractorResult.StartedByCaller -isnot [bool] `
                -or [int]$extractorResult.Pid -le 0) {
            throw 'Memory extractor ownership verification failed.'
        }
        $null = Wait-LocalHealth -Uri "http://127.0.0.1:$MemoryExtractionPort/api/tags" -TimeoutSeconds 30
        & (Join-Path $PSScriptRoot 'ollama-proxy\start-local-ollama-proxy.ps1') `
            -NumGpu $OllamaNumGpu -MemoryExtractionProvider $MemoryExtractionProvider `
            -OllamaKeepAlive $OllamaKeepAlive `
            -EnableKnowledge $EnableKnowledge `
            -AllowExternalMemoryExtraction $AllowExternalMemoryExtraction -MemoryExtractionModel $MemoryExtractionModel `
            -MemoryExtractionGateReport $MemoryExtractionGateReport -MemoryExtractionUpstream "http://127.0.0.1:$MemoryExtractionPort" `
            -MemoryExtractionGateProfile $MemoryExtractionGateProfile `
            -ChatProvider $ChatProvider -AllowExternalChat $AllowExternalChat -ChatModel $effectiveChatModel -ChatModelPreflighted `
            -ChatModelDigest $ChatModelDigest `
            -AllowExternalSearch $AllowExternalSearch -TopicBoardPath $TopicBoardPath -EnableEvaluation $EnableEvaluation `
            -EnableCharacterEvaluator $EnableCharacterEvaluator -EvaluationMaxRecords $EvaluationMaxRecords
        $proxy = Wait-LocalHealth -Uri 'http://127.0.0.1:11435/health'
        if ($proxy.memory.extraction_enabled -ne $true -or $proxy.memory.extraction_configured -ne $true) {
            throw 'Memory extraction proxy configuration was not activated.'
        }
    }
    catch {
        if ($extractorResult -and $extractorResult.StartedByCaller -eq $true) {
            try {
                & (Join-Path $PSScriptRoot 'ollama-proxy\stop-memory-extractor.ps1') `
                    -Port $MemoryExtractionPort -ExpectedPid ([int]$extractorResult.Pid)
            }
            catch {
                # Preserve the proxy-start failure; the stop script refuses
                # PID replacement rather than affecting another process.
            }
        }
        throw
    }
}
else {
    throw 'Memory extraction gate requires the local ollama provider.'
}
$proxy = Wait-LocalHealth -Uri 'http://127.0.0.1:11435/health'
& (Join-Path $PSScriptRoot 'gpt-sovits\start-local-stack.ps1')
& (Join-Path $PSScriptRoot 'stt\start-local-stt.ps1') `
    -Model $SttModel `
    -ComputeType $SttComputeType

$tts = Wait-LocalHealth -Uri 'http://127.0.0.1:8880/health'
$stt = Wait-LocalHealth -Uri 'http://127.0.0.1:8890/health'
if (-not [string]::IsNullOrWhiteSpace($TopicBoardPath) -and -not [bool]$proxy.topic_board.configured) {
    throw 'TopicBoardPath was requested but the live 11435 proxy did not confirm a configured local topic board.'
}

# Load the local foreground model before its first user turn.  External chat
# providers must never have their model name sent to the local Ollama endpoint.
$warmup = $null
if ($ChatProvider -eq 'local') {
    $warmupJson = @{
        model = $effectiveChatModel
        stream = $false
        keep_alive = $OllamaKeepAlive
        messages = @(@{ role = 'user'; content = '준비.' })
        options = @{
            num_ctx = 2048
            num_gpu = $OllamaNumGpu
            num_predict = 1
            temperature = 0
            seed = 42
        }
    } | ConvertTo-Json -Depth 6 -Compress
    $warmupBytes = [Text.Encoding]::UTF8.GetBytes($warmupJson)
    $previousProgressPreference = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try {
        $warmup = Invoke-WebRequest `
            -Uri 'http://127.0.0.1:11434/api/chat' `
            -Method Post `
            -ContentType 'application/json; charset=utf-8' `
            -Body $warmupBytes `
            -UseBasicParsing `
            -TimeoutSec 120
    }
    finally {
        $ProgressPreference = $previousProgressPreference
    }
}

[pscustomobject]@{
    LatencyMonitor = $latencyMonitor.status
    LatencyDashboard = 'http://127.0.0.1:8892/'
    OllamaProxy = $proxy.status
    MemoryEnabled = $proxy.memory.enabled
    MemoryReady = $proxy.memory.ready
    MemoryEmbedder = $proxy.memory.embedder
    MemoryExtractionAutoEnabled = $memoryExtractionAutoEnabled
    MemoryExtractionGateProfile = $MemoryExtractionGateProfile
    MemoryExtractionEnabled = $proxy.memory.extraction_enabled
    MemoryExtractionIsolated = $proxy.memory.extraction_isolated
    MemoryExtractionReady = $proxy.memory.extraction_ready
    EvaluationEnabled = $proxy.evaluation.enabled
    CharacterEvaluatorEnabled = $proxy.character_state_evaluator.enabled
    CharacterEvaluatorReady = $proxy.character_state_evaluator.ready
    LLMWarmup = if ($warmup) { $warmup.StatusCode } else { $null }
    ChatProvider = $ChatProvider
    ChatModel = $effectiveChatModel
    ChatModelEnforced = $proxy.chat_model.enforced
    ChatModelDigest = $proxy.chat_model.digest.digest
    ChatModelDigestStatus = $proxy.chat_model.digest.status
    CharacterEvaluatorModel = if ($EnableCharacterEvaluator) { $effectiveEvaluatorModel } else { '' }
    NumCtx = $proxy.num_ctx
    NumGpu = $proxy.num_gpu
    TTS = $tts.status
    TTSEngine = $tts.engine
    VoiceReferenceFound = $tts.reference_audio_found
    STT = $stt.status
    STTModel = $stt.model
    STTDevice = $stt.device
}
