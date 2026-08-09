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
    [string]$MemoryExtractionModel = '',
    [string]$MemoryExtractionGateReport = '',
    [ValidateRange(1024, 65535)]
    [int]$MemoryExtractionPort = 11436,
    [ValidateSet('local', 'openai', 'anthropic')]
    [string]$ChatProvider = 'local',
    [bool]$AllowExternalChat = $false,
    [string]$ChatModel = '',
    [bool]$AllowExternalSearch = $false,
    [string]$TopicBoardPath = '',
    [bool]$EnableEvaluation = $false,
    [bool]$EnableCharacterEvaluator = $true,
    [ValidateRange(1, 1000000)]
    [int]$EvaluationMaxRecords = 10000
)

$ErrorActionPreference = 'Stop'

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
        -MemoryExtractionUpstream "http://127.0.0.1:$MemoryExtractionPort" `
        -ChatProvider $ChatProvider `
        -AllowExternalChat $AllowExternalChat `
        -ChatModel $ChatModel `
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
        -ChatProvider $ChatProvider -AllowExternalChat $AllowExternalChat -ChatModel $ChatModel `
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
            -ChatProvider $ChatProvider -AllowExternalChat $AllowExternalChat -ChatModel $ChatModel `
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
& (Join-Path $PSScriptRoot 'gpt-sovits\start-local-stack.ps1')
& (Join-Path $PSScriptRoot 'stt\start-local-stt.ps1') `
    -Model $SttModel `
    -ComputeType $SttComputeType

$proxy = Wait-LocalHealth -Uri 'http://127.0.0.1:11435/health'
$tts = Wait-LocalHealth -Uri 'http://127.0.0.1:8880/health'
$stt = Wait-LocalHealth -Uri 'http://127.0.0.1:8890/health'
if (-not [string]::IsNullOrWhiteSpace($TopicBoardPath) -and -not [bool]$proxy.topic_board.configured) {
    throw 'TopicBoardPath was requested but the live 11435 proxy did not confirm a configured local topic board.'
}

# Load Ollama's model before the first user turn. Warm the native loopback
# endpoint directly so this synthetic probe can never enter AIRI's memory,
# character-state, evaluation, or cloud-routing paths.
$warmupJson = @{
    model = 'exaone-airi:2.4b'
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

[pscustomobject]@{
    LatencyMonitor = $latencyMonitor.status
    LatencyDashboard = 'http://127.0.0.1:8892/'
    OllamaProxy = $proxy.status
    MemoryEnabled = $proxy.memory.enabled
    MemoryReady = $proxy.memory.ready
    MemoryEmbedder = $proxy.memory.embedder
    MemoryExtractionEnabled = $proxy.memory.extraction_enabled
    MemoryExtractionIsolated = $proxy.memory.extraction_isolated
    MemoryExtractionReady = $proxy.memory.extraction_ready
    EvaluationEnabled = $proxy.evaluation.enabled
    CharacterEvaluatorEnabled = $proxy.character_state_evaluator.enabled
    CharacterEvaluatorReady = $proxy.character_state_evaluator.ready
    LLMWarmup = $warmup.StatusCode
    NumCtx = $proxy.num_ctx
    NumGpu = $proxy.num_gpu
    TTS = $tts.status
    TTSEngine = $tts.engine
    VoiceReferenceFound = $tts.reference_audio_found
    STT = $stt.status
    STTModel = $stt.model
    STTDevice = $stt.device
}
