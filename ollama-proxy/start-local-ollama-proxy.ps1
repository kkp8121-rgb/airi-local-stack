param(
    [object]$NumCtx = 4096,
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
    [string]$KnowledgeDbPath = '',
    [string]$MemoryEmbedModel = 'nlpai-lab/KURE-v1',
    [ValidateSet('auto', 'cpu', 'cuda')]
    [string]$MemoryEmbedDevice = 'cuda',
    [string]$MemorySession = '',
    # Evaluation campaigns may use a dedicated SQLite file so thousands of
    # synthetic turns exercise the real memory path without contaminating the
    # normal broadcast database.
    [string]$MemoryDbPath = '',
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
    [ValidateSet('on', 'off')]
    [string]$OutputModeration = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_OUTPUT_MODERATION)) { 'off' } else { $env:AIRI_OUTPUT_MODERATION }),
    [string]$OutputModerationTerms = $env:AIRI_OUTPUT_MODERATION_TERMS,
    [ValidateSet('on', 'off')]
    [string]$InputScreening = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_INPUT_SCREENING)) { 'off' } else { $env:AIRI_INPUT_SCREENING }),
    [string]$InputScreeningPolicy = $env:AIRI_INPUT_SCREENING_POLICY,
    [ValidateSet('on', 'off')]
    [string]$EpistemicConfidence = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_EPISTEMIC_CONFIDENCE)) { 'off' } else { $env:AIRI_EPISTEMIC_CONFIDENCE }),
    # Continuity across turns is an explicit opt-in. Leave it disabled unless
    # the caller supplies the exact supported mode.
    [ValidateSet('on', 'off')]
    [string]$AffectContinuity = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_AFFECT_CONTINUITY_ENABLED)) { 'off' } else { $env:AIRI_AFFECT_CONTINUITY_ENABLED }),
    # Live broadcast control is a separate explicit opt-in. The root launcher
    # creates its tokens; they are passed to Python through child-only env.
    [switch]$LiveBroadcast,
    [string]$LiveBroadcastMasterToken = '',
    [string]$LiveBroadcastObserverToken = '',
    # Evaluation-only logical time. Production launchers leave this off; the
    # campaign harness uses server-attested advances instead of claiming that
    # a fast run spent literal wall-clock hours on air.
    [switch]$LiveBroadcastEvalClock,
    # 선반응 ACK 모드 — 2026-08-19 사용자 결정(C안): 운영 기본은 표정 마커만
    # 남기는 marker다. audible은 구 동작 롤백용, off는 완전 무반응.
    [ValidateSet('audible', 'marker', 'off')]
    [string]$ImmediateAck = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_IMMEDIATE_ACK)) { 'marker' } else { $env:AIRI_IMMEDIATE_ACK }),
    # 침묵 폴백 문구 풀 — 문구 6종·운영 채택 모두 사용자 승인(2026-08-19).
    # env 계약이 1/true/yes/on을 받으므로 ValidateSet 대신 본문에서 정규화한다.
    [string]$SilenceFallbackPool = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_SILENCE_FALLBACK_POOL)) { 'on' } else { $env:AIRI_SILENCE_FALLBACK_POOL }),
    # 방송 발화 계약 v3 — 파라미터 9행 원안 승인과 함께 운영 ON(2026-08-19).
    [string]$BroadcastContract = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_BROADCAST_CONTRACT)) { 'on' } else { $env:AIRI_BROADCAST_CONTRACT }),
    # 근거 없는 기억 단정 가드 — 도입 승인(2026-08-19).
    [string]$MemoryClaimGuard = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_MEMORY_CLAIM_GUARD)) { 'on' } else { $env:AIRI_MEMORY_CLAIM_GUARD }),
    [bool]$AllowExternalSearch = $false,
    [string]$TopicBoardPath = '',
    [bool]$EnableEvaluation = $false,
    [bool]$EnableCharacterEvaluator = $false,
    [ValidateRange(1, 1000000)]
    [int]$EvaluationMaxRecords = 10000
)

$ErrorActionPreference = 'Stop'
$resolvedMemoryDbPath = if ([string]::IsNullOrWhiteSpace($MemoryDbPath)) {
    Join-Path $PSScriptRoot 'runtime\airi-memory.sqlite3'
} else {
    [IO.Path]::GetFullPath($MemoryDbPath)
}
if ([IO.Path]::GetExtension($resolvedMemoryDbPath) -cne '.sqlite3') {
    throw 'MemoryDbPath must use the .sqlite3 extension.'
}
$memoryDbParent = Split-Path -Parent $resolvedMemoryDbPath
if (-not (Test-Path -LiteralPath $memoryDbParent -PathType Container)) {
    throw 'MemoryDbPath parent directory must already exist.'
}
$resolvedKnowledgeDbPath = if ([string]::IsNullOrWhiteSpace($KnowledgeDbPath)) {
    Join-Path $PSScriptRoot 'runtime\airi-knowledge.sqlite3'
} else {
    [IO.Path]::GetFullPath($KnowledgeDbPath)
}
if ([IO.Path]::GetExtension($resolvedKnowledgeDbPath) -cne '.sqlite3') {
    throw 'KnowledgeDbPath must use the .sqlite3 extension.'
}
$knowledgeDbParent = Split-Path -Parent $resolvedKnowledgeDbPath
if (-not (Test-Path -LiteralPath $knowledgeDbParent -PathType Container)) {
    throw 'KnowledgeDbPath parent directory must already exist.'
}
function Get-AiriHealthBoolean {
    param([object]$Container, [string]$Name, [string]$Description)
    $property = if ($null -ne $Container) { $Container.PSObject.Properties[$Name] } else { $null }
    if ($null -eq $property -or $property.Value -isnot [bool]) {
        throw "$Description must be a JSON Boolean."
    }
    return $property.Value
}
function Assert-AiriAffectContinuityContract {
    param([object]$Container, [string]$Description)
    $mode = if ($null -ne $Container) { $Container.PSObject.Properties['mode'] } else { $null }
    $schema = if ($null -ne $Container) { $Container.PSObject.Properties['schema_version'] } else { $null }
    $cap = if ($null -ne $Container) { $Container.PSObject.Properties['prompt_cap_bytes'] } else { $null }
    if ($null -eq $mode -or $mode.Value -isnot [string] -or $mode.Value -cne 'typed-snapshot-v1' -or
            $null -eq $schema -or $schema.Value -isnot [string] -or $schema.Value -cne 'airi.affect-state.v1' -or
            $null -eq $cap -or $cap.Value -isnot [int] -or $cap.Value -ne 384) {
        throw "$Description contract is missing or unsupported."
    }
}
$OutputModeration = $OutputModeration.ToLowerInvariant()
if ($OutputModeration -notin @('on', 'off')) {
    throw 'OutputModeration must be on or off. Check the parameter or AIRI_OUTPUT_MODERATION.'
}
$onValues = @('on', '1', 'true', 'yes')
$SilenceFallbackPool = if ($SilenceFallbackPool.Trim().ToLowerInvariant() -in $onValues) { 'on' } else { 'off' }
$BroadcastContract = if ($BroadcastContract.Trim().ToLowerInvariant() -in $onValues) { 'on' } else { 'off' }
$MemoryClaimGuard = if ($MemoryClaimGuard.Trim().ToLowerInvariant() -in $onValues) { 'on' } else { 'off' }
$InputScreening = $InputScreening.ToLowerInvariant()
if ($InputScreening -notin @('on', 'off')) {
    throw 'InputScreening must be on or off. Check the parameter or AIRI_INPUT_SCREENING.'
}
$EpistemicConfidence = $EpistemicConfidence.ToLowerInvariant()
if ($EpistemicConfidence -notin @('on', 'off')) {
    throw 'EpistemicConfidence must be on or off. Check the parameter or AIRI_EPISTEMIC_CONFIDENCE.'
}
$AffectContinuity = $AffectContinuity.ToLowerInvariant()
if ($AffectContinuity -notin @('on', 'off')) {
    throw 'AffectContinuity must be on or off. Check the parameter or AIRI_AFFECT_CONTINUITY_ENABLED.'
}
if ($LiveBroadcast -and $InputScreening -ne 'on') {
    throw 'LiveBroadcast requires InputScreening on.'
}
if ($LiveBroadcastEvalClock -and -not $LiveBroadcast) {
    throw 'LiveBroadcastEvalClock requires LiveBroadcast.'
}
if ($LiveBroadcast -and ($LiveBroadcastMasterToken -notmatch '^[A-Za-z0-9_-]{32,128}$' -or
        $LiveBroadcastObserverToken -notmatch '^[A-Za-z0-9_-]{32,128}$' -or
        $LiveBroadcastMasterToken -ceq $LiveBroadcastObserverToken)) {
    throw 'Live broadcast tokens must be distinct and each contain 32 through 128 URL-safe characters when LiveBroadcast is enabled.'
}
$parsedNumCtx = 0
if (-not [int]::TryParse(
        [string]$NumCtx, [Globalization.NumberStyles]::Integer,
        [Globalization.CultureInfo]::InvariantCulture, [ref]$parsedNumCtx) -or
        $parsedNumCtx -lt 512 -or $parsedNumCtx -gt 32768) {
    throw 'NumCtx must be an integer from 512 through 32768.'
}
$NumCtx = $parsedNumCtx
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
$resolvedOutputModerationTerms = ''
if (-not [string]::IsNullOrWhiteSpace($OutputModerationTerms)) {
    $termsItem = Get-Item -LiteralPath $OutputModerationTerms -ErrorAction Stop
    if ($termsItem.PSIsContainer -or $termsItem -isnot [IO.FileInfo] -or
            ($termsItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'OutputModerationTerms must be a regular file.'
    }
    $resolvedOutputModerationTerms = [IO.Path]::GetFullPath($termsItem.FullName)
}
$resolvedInputScreeningPolicy = ''
if (-not [string]::IsNullOrWhiteSpace($InputScreeningPolicy)) {
    $policyItem = Get-Item -LiteralPath $InputScreeningPolicy -ErrorAction Stop
    if ($policyItem.PSIsContainer -or $policyItem -isnot [IO.FileInfo] -or
            ($policyItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'InputScreeningPolicy must be a regular file.'
    }
    $resolvedInputScreeningPolicy = [IO.Path]::GetFullPath($policyItem.FullName)
}
$effectiveInputScreeningPolicy = if ($InputScreening -eq 'on') {
    if ($resolvedInputScreeningPolicy) { $resolvedInputScreeningPolicy }
    else { Join-Path $repo 'input_screening_policy_ko.json' }
} else { '' }
$expectedInputScreeningPolicySha256 = if ($effectiveInputScreeningPolicy) {
    $policyDigestItem = Get-Item -LiteralPath $effectiveInputScreeningPolicy -ErrorAction Stop
    if ($policyDigestItem.PSIsContainer -or $policyDigestItem -isnot [IO.FileInfo] -or
            ($policyDigestItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Effective input screening policy must be a regular file.'
    }
    (Get-FileHash -LiteralPath $policyDigestItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
} else { '' }

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
    if ($LiveBroadcast) {
        # Live capabilities are bound to the two in-memory secrets supplied at
        # process creation. Health must not expose token identity, so a new
        # launcher invocation can only hand off safely by restarting.
        throw 'Existing proxy cannot be reused with LiveBroadcast; stop it and restart so fresh control tokens take effect.'
    }
    if (-not [string]::IsNullOrWhiteSpace($MemoryExtractionModel)) {
        throw 'Existing proxy cannot be reused for memory extraction.'
    }
    if (-not [string]::IsNullOrWhiteSpace($resolvedTopicBoardPath)) {
        throw 'Existing proxy cannot be reused with TopicBoardPath; stop it and restart so the approved board is loaded.'
    }
    if (-not [string]::IsNullOrWhiteSpace($resolvedOutputModerationTerms)) {
        throw 'Existing proxy cannot be reused with OutputModerationTerms; stop it and restart so the policy identity is known.'
    }
    try {
        $existingHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/health' -TimeoutSec 3 -ErrorAction Stop
        if ($null -eq $existingHealth.output_moderation -or
                $null -eq $existingHealth.output_moderation.PSObject.Properties['enabled']) {
            throw 'Existing proxy health does not report output moderation state.'
        }
        $existingModerationEnabled = [bool]$existingHealth.output_moderation.enabled
        if ($null -eq $existingHealth.input_screening) {
            throw 'Existing proxy health does not report input screening state.'
        }
        $existingInputScreeningEnabled = Get-AiriHealthBoolean `
            $existingHealth.input_screening 'enabled' 'Existing proxy input screening enabled'
        $existingInputScreeningReady = Get-AiriHealthBoolean `
            $existingHealth.input_screening 'ready' 'Existing proxy input screening ready'
        $policyProperty = $existingHealth.input_screening.PSObject.Properties['policy_sha256']
        if ($InputScreening -eq 'on' -and ($null -eq $policyProperty -or
                $policyProperty.Value -isnot [string] -or
                $policyProperty.Value -notmatch '^[0-9a-f]{64}$')) {
            throw 'Existing proxy input screening policy digest is malformed.'
        }
        $existingInputScreeningPolicySha256 = if ($null -ne $policyProperty) { $policyProperty.Value } else { '' }
        if ($null -eq $existingHealth.epistemic_confidence) {
            throw 'Existing proxy health does not report epistemic confidence state.'
        }
        $existingEpistemicConfidenceEnabled = Get-AiriHealthBoolean `
            $existingHealth.epistemic_confidence 'enabled' 'Existing proxy epistemic confidence enabled'
        if ($null -eq $existingHealth.affect_continuity) {
            throw 'Existing proxy health does not report affect continuity state.'
        }
        Assert-AiriAffectContinuityContract `
            $existingHealth.affect_continuity 'Existing proxy affect continuity'
        $existingAffectContinuityEnabled = Get-AiriHealthBoolean `
            $existingHealth.affect_continuity 'enabled' 'Existing proxy affect continuity enabled'
        $existingAffectContinuityReady = Get-AiriHealthBoolean `
            $existingHealth.affect_continuity 'ready' 'Existing proxy affect continuity ready'
        if ($null -eq $existingHealth.show_arc -or $null -eq $existingHealth.broadcast_affect) {
            throw 'Existing proxy health does not report live broadcast state.'
        }
        $existingShowArcEnabled = Get-AiriHealthBoolean `
            $existingHealth.show_arc 'enabled' 'Existing proxy show arc enabled'
        $existingShowArcReady = Get-AiriHealthBoolean `
            $existingHealth.show_arc 'ready' 'Existing proxy show arc ready'
        $existingBroadcastAffectEnabled = Get-AiriHealthBoolean `
            $existingHealth.broadcast_affect 'enabled' 'Existing proxy broadcast affect enabled'
        $existingBroadcastAffectReady = Get-AiriHealthBoolean `
            $existingHealth.broadcast_affect 'ready' 'Existing proxy broadcast affect ready'
        if ($null -eq $existingHealth.chat_model) {
            throw 'Existing proxy health does not report chat model state.'
        }
        $existingChatProvider = $existingHealth.chat_model.provider
        $existingChatModel = $existingHealth.chat_model.model
        if ($existingChatProvider -isnot [string] -or $existingChatModel -isnot [string]) {
            throw 'Existing proxy chat model state is malformed.'
        }
        $existingDigest = $existingHealth.chat_model.digest
        if (-not [string]::IsNullOrWhiteSpace($ChatModelDigest) -and
                ($null -eq $existingDigest -or $existingDigest.digest -isnot [string])) {
            throw 'Existing proxy health does not report chat model digest state.'
        }
        $existingMemoryEnabled = Get-AiriHealthBoolean $existingHealth.memory 'enabled' 'Existing proxy memory enabled'
        $existingMemoryReady = Get-AiriHealthBoolean $existingHealth.memory 'ready' 'Existing proxy memory ready'
        $existingKnowledgeEnabled = Get-AiriHealthBoolean $existingHealth.knowledge 'enabled' 'Existing proxy knowledge enabled'
        $existingKnowledgeReady = Get-AiriHealthBoolean $existingHealth.knowledge 'ready' 'Existing proxy knowledge ready'
        $existingExternalSearch = Get-AiriHealthBoolean $existingHealth 'cloud_search_external_approved' 'Existing proxy external search approval'
        $existingBroadcastContract = Get-AiriHealthBoolean $existingHealth 'broadcast_contract' 'Existing proxy broadcast contract'
        $existingMemoryClaimGuard = Get-AiriHealthBoolean $existingHealth 'memory_claim_guard' 'Existing proxy memory claim guard'
        if ($existingHealth.immediate_ack -isnot [string]) {
            throw 'Existing proxy immediate acknowledgement state is malformed.'
        }
        $existingImmediateAck = $existingHealth.immediate_ack
    }
    catch {
        throw 'Existing proxy safety state could not be verified; stop it and restart.'
    }
    $existingNumCtx = 0
    $existingNumCtxText = [Convert]::ToString(
        $existingHealth.num_ctx, [Globalization.CultureInfo]::InvariantCulture)
    if (-not [int]::TryParse(
            $existingNumCtxText, [Globalization.NumberStyles]::None,
            [Globalization.CultureInfo]::InvariantCulture, [ref]$existingNumCtx) -or
            $existingNumCtx -ne $NumCtx) {
        throw 'Existing proxy num_ctx differs from the requested configuration; stop it and restart.'
    }
    $requestedModerationEnabled = $OutputModeration -eq 'on'
    if ($existingModerationEnabled -ne $requestedModerationEnabled) {
        throw 'Existing proxy output moderation state differs from the requested configuration; stop it and restart.'
    }
    if ($existingInputScreeningEnabled -ne ($InputScreening -eq 'on')) {
        throw 'Existing proxy input screening state differs from the requested configuration; stop it and restart.'
    }
    if ($InputScreening -eq 'on' -and -not $existingInputScreeningReady) {
        throw 'Existing proxy input screening is enabled but not ready; stop it and restart.'
    }
    if ($InputScreening -eq 'on' -and
            $existingInputScreeningPolicySha256 -cne $expectedInputScreeningPolicySha256) {
        throw 'Existing proxy input screening policy digest differs from the requested policy; stop it and restart.'
    }
    if ($existingEpistemicConfidenceEnabled -ne ($EpistemicConfidence -eq 'on')) {
        throw 'Existing proxy epistemic confidence state differs from the requested configuration; stop it and restart.'
    }
    if ($existingAffectContinuityEnabled -ne ($AffectContinuity -eq 'on')) {
        throw 'Existing proxy affect continuity state differs from the requested configuration; stop it and restart.'
    }
    if ($AffectContinuity -eq 'on' -and -not $existingAffectContinuityReady) {
        throw 'Existing proxy affect continuity is enabled but not ready; stop it and restart.'
    }
    if ($existingShowArcEnabled -ne [bool]$LiveBroadcast -or
            $existingBroadcastAffectEnabled -ne [bool]$LiveBroadcast -or
            ($LiveBroadcast -and (-not $existingShowArcReady -or -not $existingBroadcastAffectReady))) {
        throw 'Existing proxy live broadcast state differs from the requested configuration or is not ready; stop it and restart.'
    }
    if ($existingChatProvider -cne $ChatProvider -or $existingChatModel -cne $effectiveChatModel) {
        throw 'Existing proxy chat provider or model differs from the requested configuration; stop it and restart.'
    }
    if (-not [string]::IsNullOrWhiteSpace($ChatModelDigest) -and $existingDigest.digest -cne $ChatModelDigest) {
        throw 'Existing proxy chat model digest differs from the requested configuration; stop it and restart.'
    }
    if ($existingMemoryEnabled -ne $EnableMemory -or ($EnableMemory -and -not $existingMemoryReady)) {
        throw 'Existing proxy memory state differs from the requested configuration; stop it and restart.'
    }
    if ($existingKnowledgeEnabled -ne $EnableKnowledge -or ($EnableKnowledge -and -not $existingKnowledgeReady)) {
        throw 'Existing proxy knowledge state differs from the requested configuration; stop it and restart.'
    }
    if ($EnableKnowledge -and $existingHealth.knowledge.documents -eq 0) {
        Write-Warning 'Existing proxy knowledge is ready but has no indexed documents.'
    }
    if ($existingExternalSearch -ne $AllowExternalSearch -or $existingImmediateAck -cne $ImmediateAck -or
            $existingBroadcastContract -ne ($BroadcastContract -eq 'on') -or
            $existingMemoryClaimGuard -ne ($MemoryClaimGuard -eq 'on')) {
        throw 'Existing proxy safety configuration differs from the requested configuration; stop it and restart.'
    }
    $existingNumGpu = 0
    if (-not [int]::TryParse([Convert]::ToString($existingHealth.num_gpu, [Globalization.CultureInfo]::InvariantCulture),
            [Globalization.NumberStyles]::None, [Globalization.CultureInfo]::InvariantCulture, [ref]$existingNumGpu) -or
            $existingNumGpu -ne $NumGpu) {
        throw 'Existing proxy num_gpu differs from the requested configuration; stop it and restart.'
    }
    Write-Output 'A service is already listening on port 11435; it was not reconfigured.'
    return
}

$memoryEnvironment = @{
    AIRI_MEMORY_ENABLED = if ($EnableMemory) { '1' } else { '0' }
    AIRI_KNOWLEDGE_ENABLED = if ($EnableKnowledge) { '1' } else { '0' }
    # KURE query embeddings share the foreground GPU with Ollama. A timed-out
    # Python worker cannot cancel an in-flight CUDA encode, so approved public
    # knowledge uses deterministic title/alias/FTS retrieval by default.
    AIRI_KNOWLEDGE_ALLOW_SEMANTIC = '0'
    AIRI_KNOWLEDGE_DB = $resolvedKnowledgeDbPath
    AIRI_KNOWLEDGE_RUNTIME_DIR = $knowledgeDbParent
    AIRI_MEMORY_DB = $resolvedMemoryDbPath
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
    AIRI_OUTPUT_MODERATION = $OutputModeration
    AIRI_OUTPUT_MODERATION_TERMS = $resolvedOutputModerationTerms
    AIRI_INPUT_SCREENING = $InputScreening
    AIRI_INPUT_SCREENING_POLICY = $resolvedInputScreeningPolicy
    AIRI_EPISTEMIC_CONFIDENCE = $EpistemicConfidence
    AIRI_EPISTEMIC_CONFIDENCE_MODE = 'enforce'
    AIRI_AFFECT_CONTINUITY_ENABLED = $AffectContinuity
    AIRI_LIVE_BROADCAST_ENABLED = if ($LiveBroadcast) { 'on' } else { 'off' }
    AIRI_LIVE_BROADCAST_MASTER_TOKEN = if ($LiveBroadcast) { $LiveBroadcastMasterToken } else { '' }
    AIRI_LIVE_BROADCAST_OBSERVER_TOKEN = if ($LiveBroadcast) { $LiveBroadcastObserverToken } else { '' }
    AIRI_LIVE_BROADCAST_EVAL_CLOCK = if ($LiveBroadcastEvalClock) { 'on' } else { 'off' }
    AIRI_IMMEDIATE_ACK = $ImmediateAck
    AIRI_SILENCE_FALLBACK_POOL = $SilenceFallbackPool
    AIRI_BROADCAST_CONTRACT = $BroadcastContract
    AIRI_MEMORY_CLAIM_GUARD = $MemoryClaimGuard
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

Write-Output "Started AIRI Ollama compatibility proxy (PID $($process.Id), memory=$EnableMemory, extraction=$MemoryExtractionProvider/$([bool]$MemoryExtractionModel), chat=$ChatProvider/$effectiveChatModel, liveBroadcast=$([bool]$LiveBroadcast), externalSearch=$AllowExternalSearch, evaluation=$EnableEvaluation, characterEvaluator=$EnableCharacterEvaluator/$effectiveEvaluatorModel)."
