param(
    # Speech-to-text is opt-in so the chat and text input path do not reserve
    # GPU memory for a service they do not use.
    [ValidateSet('on', 'off')]
    [string]$Stt = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_STT)) { 'off' } else { $env:AIRI_STT }),
    [string]$SttModel = 'mobiuslabsgmbh/faster-whisper-large-v3-turbo',
    [string]$SttComputeType = 'int8_float16',
    [ValidateRange(0, 999)]
    # Keep the local chat model on the GPU by default.  num_gpu=0 forces
    # CPU-only inference and makes first-token latency several seconds slower.
    [int]$OllamaNumGpu = 999,
    # Foreground context is explicit so all local chat hops share one window.
    # A null parameter permits a nonblank AIRI_NUM_CTX override to be resolved
    # below with the same strict validation as an explicit invocation.
    [object]$NumCtx = $null,
    # Keep the foreground Ollama runner loaded across normal chat gaps.
    [string]$OllamaKeepAlive = '30m',
    [bool]$EnableMemory = $true,
    [bool]$EnableKnowledge = $true,
    [string]$MemoryDbPath = '',
    [string]$KnowledgeDbPath = '',
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
    # The output gate remains opt-in. An explicit environment value is honored
    # when callers do not provide a switch; invalid values fail parameter binding.
    [ValidateSet('on', 'off')]
    [string]$OutputModeration = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_OUTPUT_MODERATION)) { 'off' } else { $env:AIRI_OUTPUT_MODERATION }),
    # Optional custom policy dictionary. Resolve it before the proxy child
    # changes its working directory so relative paths cannot drift at launch.
    [string]$OutputModerationTerms = $env:AIRI_OUTPUT_MODERATION_TERMS,
    [ValidateSet('on', 'off')]
    [string]$InputScreening = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_INPUT_SCREENING)) { 'off' } else { $env:AIRI_INPUT_SCREENING }),
    [string]$InputScreeningPolicy = $env:AIRI_INPUT_SCREENING_POLICY,
    [ValidateSet('on', 'off')]
    [string]$EpistemicConfidence = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_EPISTEMIC_CONFIDENCE)) { 'off' } else { $env:AIRI_EPISTEMIC_CONFIDENCE }),
    # Affect continuity stays opt-in; no launcher path may promote it.
    [ValidateSet('on', 'off')]
    [string]$AffectContinuity = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_AFFECT_CONTINUITY_ENABLED)) { 'off' } else { $env:AIRI_AFFECT_CONTINUITY_ENABLED }),
    # This enables the separately authenticated live broadcast control plane.
    # The launcher creates a fresh in-memory master token for the proxy child.
    [switch]$LiveBroadcast,
    # Test-only logical time is a second explicit opt-in. Production launches
    # must never gain the ability to manufacture long continuity gaps.
    [switch]$LiveBroadcastEvalClock,
    # A same-process evaluation wrapper may supply fresh capabilities so it
    # can start the proxy and immediately run the campaign without printing
    # or persisting either secret. Supplying only one always fails closed.
    [string]$LiveBroadcastMasterTokenOverride = '',
    [string]$LiveBroadcastObserverTokenOverride = '',
    [bool]$AllowExternalSearch = $false,
    [string]$TopicBoardPath = '',
    [bool]$EnableEvaluation = $false,
    [bool]$EnableCharacterEvaluator = $false,
    [ValidateRange(1, 1000000)]
    [int]$EvaluationMaxRecords = 10000
)

$ErrorActionPreference = 'Stop'
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
function Resolve-AiriNumCtx {
    param([object]$Value)
    $parsed = 0
    if (-not [int]::TryParse([string]$Value, [Globalization.NumberStyles]::Integer,
            [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed) -or
            $parsed -lt 512 -or $parsed -gt 32768) {
        throw 'NumCtx must be an integer from 512 through 32768. Check -NumCtx or AIRI_NUM_CTX.'
    }
    return $parsed
}
function New-AiriLiveBroadcastMasterToken {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
$NumCtx = Resolve-AiriNumCtx $(if ($null -ne $NumCtx) { $NumCtx } elseif (-not [string]::IsNullOrWhiteSpace($env:AIRI_NUM_CTX)) { $env:AIRI_NUM_CTX } else { 2048 })
$OutputModeration = $OutputModeration.ToLowerInvariant()
if ($OutputModeration -notin @('on', 'off')) {
    throw 'OutputModeration must be on or off. Check the parameter or AIRI_OUTPUT_MODERATION.'
}
$InputScreening = $InputScreening.ToLowerInvariant()
if ($InputScreening -notin @('on', 'off')) {
    throw 'InputScreening must be on or off. Check the parameter or AIRI_INPUT_SCREENING.'
}
if ($LiveBroadcast -and $InputScreening -ne 'on') {
    throw 'LiveBroadcast requires InputScreening on.'
}
if ($LiveBroadcastEvalClock -and -not $LiveBroadcast) {
    throw 'LiveBroadcastEvalClock requires LiveBroadcast.'
}
if (-not $LiveBroadcast -and (-not [string]::IsNullOrWhiteSpace($LiveBroadcastMasterTokenOverride) -or
        -not [string]::IsNullOrWhiteSpace($LiveBroadcastObserverTokenOverride))) {
    throw 'Live broadcast token overrides require LiveBroadcast.'
}
$EpistemicConfidence = $EpistemicConfidence.ToLowerInvariant()
if ($EpistemicConfidence -notin @('on', 'off')) {
    throw 'EpistemicConfidence must be on or off. Check the parameter or AIRI_EPISTEMIC_CONFIDENCE.'
}
$AffectContinuity = $AffectContinuity.ToLowerInvariant()
if ($AffectContinuity -notin @('on', 'off')) {
    throw 'AffectContinuity must be on or off. Check the parameter or AIRI_AFFECT_CONTINUITY_ENABLED.'
}
if ($Stt -notin @('on', 'off')) {
    throw 'Stt must be on or off. Check the -Stt parameter or AIRI_STT environment variable.'
}
$Stt = $Stt.ToLowerInvariant()
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
    if ($policyItem.PSIsContainer -or $policyItem -isnot [IO.FileInfo] -or ($policyItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'InputScreeningPolicy must be a regular file.' }
    $resolvedInputScreeningPolicy = [IO.Path]::GetFullPath($policyItem.FullName)
}
$effectiveInputScreeningPolicy = if ($InputScreening -eq 'on') {
    if ($resolvedInputScreeningPolicy) { $resolvedInputScreeningPolicy }
    else { Join-Path $PSScriptRoot 'ollama-proxy\input_screening_policy_ko.json' }
} else { '' }
$expectedInputScreeningPolicySha256 = if ($effectiveInputScreeningPolicy) {
    $policyDigestItem = Get-Item -LiteralPath $effectiveInputScreeningPolicy -ErrorAction Stop
    if ($policyDigestItem.PSIsContainer -or $policyDigestItem -isnot [IO.FileInfo] -or
            ($policyDigestItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Effective input screening policy must be a regular file.'
    }
    (Get-FileHash -LiteralPath $policyDigestItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
} else { '' }
$effectiveChatModel = if ($ChatProvider -eq 'local' -and [string]::IsNullOrWhiteSpace($ChatModel)) {
    'midm-airi:2.0-mini'
} else {
    $ChatModel
}
# The dev-PC verified Mi:dm artifact is the normal local runtime default.
# Respect an explicit parameter or environment pin, and leave rollback tags
# and external providers unpinned unless the caller supplied a digest.
if ($ChatProvider -eq 'local' -and $effectiveChatModel -ceq 'midm-airi:2.0-mini' `
        -and [string]::IsNullOrWhiteSpace($ChatModelDigest)) {
    $ChatModelDigest = '92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f'
}
$effectiveEvaluatorModel = if ($ChatProvider -eq 'local') {
    $effectiveChatModel
} else {
    'midm-airi:2.0-mini'
}
$hasMasterTokenOverride = -not [string]::IsNullOrWhiteSpace($LiveBroadcastMasterTokenOverride)
$hasObserverTokenOverride = -not [string]::IsNullOrWhiteSpace($LiveBroadcastObserverTokenOverride)
if ($LiveBroadcast -and $hasMasterTokenOverride -ne $hasObserverTokenOverride) {
    throw 'Live broadcast token overrides must be supplied together.'
}
$liveBroadcastMasterToken = if ($hasMasterTokenOverride) {
    $LiveBroadcastMasterTokenOverride
} elseif ($LiveBroadcast) {
    New-AiriLiveBroadcastMasterToken
} else { '' }
$liveBroadcastObserverToken = if ($hasObserverTokenOverride) {
    $LiveBroadcastObserverTokenOverride
} elseif ($LiveBroadcast) {
    New-AiriLiveBroadcastMasterToken
} else { '' }
if ($LiveBroadcast -and ($liveBroadcastMasterToken -notmatch '^[A-Za-z0-9_-]{32,128}$' -or
        $liveBroadcastObserverToken -notmatch '^[A-Za-z0-9_-]{32,128}$' -or
        $liveBroadcastMasterToken -ceq $liveBroadcastObserverToken)) {
    throw 'Live broadcast token generation failed or produced duplicate tokens.'
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

# Only an extractor process this launcher actually created may be stopped by
# the companion stop script.  Keep the record under the repository runtime
# directory and write it via a same-directory rename so an interrupted launch
# never leaves a partially written ownership claim.
$extractorRuntimeDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'ollama-proxy\runtime'))
$extractorOwnerPath = [IO.Path]::GetFullPath((Join-Path $extractorRuntimeDir 'memory-extractor-owner.json'))
if (-not $extractorOwnerPath.StartsWith($extractorRuntimeDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Memory extractor owner record path must stay under the repository runtime directory.'
}
function Write-MemoryExtractorOwnerRecord {
    param([int]$Port, [int]$Pid)
    if ($Pid -le 0) { throw 'Memory extractor owner PID must be positive.' }
    New-Item -ItemType Directory -Path $extractorRuntimeDir -Force | Out-Null
    $temporary = Join-Path $extractorRuntimeDir ('.memory-extractor-owner-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        @{ port = $Port; pid = $Pid } | ConvertTo-Json -Compress | Set-Content -LiteralPath $temporary -Encoding utf8 -NoNewline
        Move-Item -LiteralPath $temporary -Destination $extractorOwnerPath -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    }
}
function Remove-MemoryExtractorOwnerRecord {
    if (Test-Path -LiteralPath $extractorOwnerPath -PathType Leaf) {
        Remove-Item -LiteralPath $extractorOwnerPath -Force -ErrorAction Stop
    }
}

if ($Stt -eq 'off') {
    # Reclaim STT resources before starting or preflighting GPU-backed services.
    # The stop helper requires the Python executable and this repository's
    # exact STT server/host/port command signature. Never kill by port alone.
    & (Join-Path $PSScriptRoot 'stt\stop-local-stt.ps1')
    $remainingSttListener = Get-NetTCPConnection -LocalPort 8890 -State Listen -ErrorAction SilentlyContinue
    if ($remainingSttListener) {
        throw 'STT is disabled, but a listener remains on local port 8890. Refusing to continue.'
    }
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
                    -NumCtx $NumCtx `
                    -MemoryExtractionProvider $MemoryExtractionProvider `
                    -MemoryExtractionModel $autoModel `
                    -MemoryExtractionGateReport $autoGateReport `
                    -MemoryExtractionGateProfile $MemoryExtractionGateProfile `
                    -AffectContinuity $AffectContinuity `
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
        -NumCtx $NumCtx `
        -NumGpu $OllamaNumGpu `
        -OllamaKeepAlive $OllamaKeepAlive `
        -EnableMemory $EnableMemory `
        -EnableKnowledge $EnableKnowledge `
        -MemoryDbPath $MemoryDbPath `
        -KnowledgeDbPath $KnowledgeDbPath `
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
        -OutputModeration $OutputModeration `
        -OutputModerationTerms $resolvedOutputModerationTerms `
        -InputScreening $InputScreening `
        -InputScreeningPolicy $resolvedInputScreeningPolicy `
        -EpistemicConfidence $EpistemicConfidence `
        -AffectContinuity $AffectContinuity `
        -LiveBroadcast:$LiveBroadcast `
        -LiveBroadcastEvalClock:$LiveBroadcastEvalClock `
        -LiveBroadcastMasterToken $liveBroadcastMasterToken `
        -LiveBroadcastObserverToken $liveBroadcastObserverToken `
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
        -NumCtx $NumCtx `
        -NumGpu $OllamaNumGpu -MemoryExtractionProvider $MemoryExtractionProvider `
        -OllamaKeepAlive $OllamaKeepAlive `
        -EnableMemory $EnableMemory `
        -EnableKnowledge $EnableKnowledge `
        -AllowExternalMemoryExtraction $AllowExternalMemoryExtraction -MemoryExtractionModel $MemoryExtractionModel `
        -MemoryExtractionGateReport $MemoryExtractionGateReport -MemoryExtractionUpstream "http://127.0.0.1:$MemoryExtractionPort" `
        -MemoryExtractionGateProfile $MemoryExtractionGateProfile `
        -ChatProvider $ChatProvider -AllowExternalChat $AllowExternalChat -ChatModel $effectiveChatModel -ChatModelPreflighted `
        -OutputModeration $OutputModeration -OutputModerationTerms $resolvedOutputModerationTerms `
        -InputScreening $InputScreening -InputScreeningPolicy $resolvedInputScreeningPolicy `
        -EpistemicConfidence $EpistemicConfidence `
        -AffectContinuity $AffectContinuity `
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
        if ($extractorResult.StartedByCaller -eq $true) {
            Write-MemoryExtractorOwnerRecord -Port $MemoryExtractionPort -Pid ([int]$extractorResult.Pid)
        }
        $null = Wait-LocalHealth -Uri "http://127.0.0.1:$MemoryExtractionPort/api/tags" -TimeoutSeconds 30
        & (Join-Path $PSScriptRoot 'ollama-proxy\start-local-ollama-proxy.ps1') `
            -NumCtx $NumCtx `
            -NumGpu $OllamaNumGpu -MemoryExtractionProvider $MemoryExtractionProvider `
            -OllamaKeepAlive $OllamaKeepAlive `
            -EnableMemory $EnableMemory `
            -EnableKnowledge $EnableKnowledge `
            -MemoryDbPath $MemoryDbPath `
            -KnowledgeDbPath $KnowledgeDbPath `
            -AllowExternalMemoryExtraction $AllowExternalMemoryExtraction -MemoryExtractionModel $MemoryExtractionModel `
            -MemoryExtractionGateReport $MemoryExtractionGateReport -MemoryExtractionUpstream "http://127.0.0.1:$MemoryExtractionPort" `
            -MemoryExtractionGateProfile $MemoryExtractionGateProfile `
            -ChatProvider $ChatProvider -AllowExternalChat $AllowExternalChat -ChatModel $effectiveChatModel -ChatModelPreflighted `
            -ChatModelDigest $ChatModelDigest `
            -OutputModeration $OutputModeration -OutputModerationTerms $resolvedOutputModerationTerms `
            -InputScreening $InputScreening -InputScreeningPolicy $resolvedInputScreeningPolicy `
            -EpistemicConfidence $EpistemicConfidence `
            -AffectContinuity $AffectContinuity `
            -LiveBroadcast:$LiveBroadcast `
            -LiveBroadcastEvalClock:$LiveBroadcastEvalClock `
            -LiveBroadcastMasterToken $liveBroadcastMasterToken `
            -LiveBroadcastObserverToken $liveBroadcastObserverToken `
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
            # This launch failed; never leave an ownership claim behind even
            # when the extractor has already exited or been replaced.
            Remove-MemoryExtractorOwnerRecord
        }
        throw
    }
}
else {
    throw 'Memory extraction gate requires the local ollama provider.'
}
$proxy = Wait-LocalHealth -Uri 'http://127.0.0.1:11435/health'
$liveMemoryEnabled = Get-AiriHealthBoolean $proxy.memory 'enabled' 'Live proxy memory enabled'
$liveMemoryReady = Get-AiriHealthBoolean $proxy.memory 'ready' 'Live proxy memory ready'
$liveKnowledgeEnabled = Get-AiriHealthBoolean $proxy.knowledge 'enabled' 'Live proxy knowledge enabled'
$liveKnowledgeReady = Get-AiriHealthBoolean $proxy.knowledge 'ready' 'Live proxy knowledge ready'
if ($liveMemoryEnabled -ne $EnableMemory -or ($EnableMemory -and -not $liveMemoryReady)) {
    throw 'Live proxy memory state is missing, unready, or differs from the requested configuration.'
}
if ($liveKnowledgeEnabled -ne $EnableKnowledge -or ($EnableKnowledge -and -not $liveKnowledgeReady)) {
    throw 'Live proxy knowledge state is missing, unready, or differs from the requested configuration.'
}
if ($EnableKnowledge -and $proxy.knowledge.documents -eq 0) {
    Write-Warning 'Live proxy knowledge is ready but has no indexed documents.'
}
$requestedInputScreening = $InputScreening -eq 'on'
$requestedEpistemicConfidence = $EpistemicConfidence -eq 'on'
$requestedAffectContinuity = $AffectContinuity -eq 'on'
if ($null -eq $proxy.input_screening) {
    throw 'Live proxy input screening state is missing, unready, or differs from the requested configuration.'
}
$liveInputScreeningEnabled = Get-AiriHealthBoolean `
    $proxy.input_screening 'enabled' 'Live proxy input screening enabled'
$liveInputScreeningReady = Get-AiriHealthBoolean `
    $proxy.input_screening 'ready' 'Live proxy input screening ready'
if ($liveInputScreeningEnabled -ne $requestedInputScreening -or
        ($requestedInputScreening -and -not $liveInputScreeningReady)) {
    throw 'Live proxy input screening state is missing, unready, or differs from the requested configuration.'
}
$livePolicyProperty = $proxy.input_screening.PSObject.Properties['policy_sha256']
if ($requestedInputScreening -and ($null -eq $livePolicyProperty -or
        $livePolicyProperty.Value -isnot [string] -or
        $livePolicyProperty.Value -notmatch '^[0-9a-f]{64}$' -or
        $livePolicyProperty.Value -cne $expectedInputScreeningPolicySha256)) {
    throw 'Live proxy input screening policy digest differs from the requested policy.'
}

$liveEpistemicConfidenceEnabled = Get-AiriHealthBoolean `
    $proxy.epistemic_confidence 'enabled' 'Live proxy epistemic confidence enabled'
if ($liveEpistemicConfidenceEnabled -ne $requestedEpistemicConfidence) {
    throw 'Live proxy epistemic confidence state is missing or differs from the requested configuration.'
}
if ($null -eq $proxy.affect_continuity) {
    throw 'Live proxy affect continuity state is missing or differs from the requested configuration.'
}
Assert-AiriAffectContinuityContract $proxy.affect_continuity 'Live proxy affect continuity'
$liveAffectContinuityEnabled = Get-AiriHealthBoolean `
    $proxy.affect_continuity 'enabled' 'Live proxy affect continuity enabled'
$liveAffectContinuityReady = Get-AiriHealthBoolean `
    $proxy.affect_continuity 'ready' 'Live proxy affect continuity ready'
if ($liveAffectContinuityEnabled -ne $requestedAffectContinuity -or
        ($requestedAffectContinuity -and -not $liveAffectContinuityReady)) {
    throw 'Live proxy affect continuity state is missing or differs from the requested configuration.'
}
if ($null -eq $proxy.show_arc -or $null -eq $proxy.broadcast_affect) {
    throw 'Live proxy broadcast state is missing or differs from the requested configuration.'
}
$liveShowArcEnabled = Get-AiriHealthBoolean $proxy.show_arc 'enabled' 'Live proxy show arc enabled'
$liveShowArcReady = Get-AiriHealthBoolean $proxy.show_arc 'ready' 'Live proxy show arc ready'
$liveBroadcastAffectEnabled = Get-AiriHealthBoolean $proxy.broadcast_affect 'enabled' 'Live proxy broadcast affect enabled'
$liveBroadcastAffectReady = Get-AiriHealthBoolean $proxy.broadcast_affect 'ready' 'Live proxy broadcast affect ready'
$liveBroadcastEvalClock = Get-AiriHealthBoolean $proxy.show_arc 'evaluation_clock' 'Live proxy broadcast evaluation clock'
if ($liveShowArcEnabled -ne [bool]$LiveBroadcast -or
        $liveBroadcastAffectEnabled -ne [bool]$LiveBroadcast -or
        $liveBroadcastEvalClock -ne [bool]$LiveBroadcastEvalClock -or
        ($LiveBroadcast -and (-not $liveShowArcReady -or -not $liveBroadcastAffectReady))) {
    throw 'Live proxy broadcast state is missing, unready, or differs from the requested configuration.'
}
$liveNumCtx = 0
$liveNumCtxText = [Convert]::ToString(
    $proxy.num_ctx, [Globalization.CultureInfo]::InvariantCulture)
if (-not [int]::TryParse(
        $liveNumCtxText, [Globalization.NumberStyles]::None,
        [Globalization.CultureInfo]::InvariantCulture, [ref]$liveNumCtx) -or
        $liveNumCtx -ne $NumCtx) {
    throw 'Live proxy num_ctx differs from the requested NumCtx; refusing to start dependent services.'
}
& (Join-Path $PSScriptRoot 'gpt-sovits\start-local-stack.ps1')
if ($Stt -eq 'on') {
    & (Join-Path $PSScriptRoot 'stt\start-local-stt.ps1') `
        -Model $SttModel `
        -ComputeType $SttComputeType
}

$tts = Wait-LocalHealth -Uri 'http://127.0.0.1:8880/health'
$sttHealth = if ($Stt -eq 'on') {
    Wait-LocalHealth -Uri 'http://127.0.0.1:8890/health'
} else {
    $null
}
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
            num_ctx = $NumCtx
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
    OutputModerationEnabled = $proxy.output_moderation.enabled
    OutputModerationReady = $proxy.output_moderation.ready
    InputScreeningEnabled = $proxy.input_screening.enabled
    InputScreeningReady = $proxy.input_screening.ready
    EpistemicConfidenceEnabled = $proxy.epistemic_confidence.enabled
    AffectContinuityEnabled = $proxy.affect_continuity.enabled
    AffectContinuityReady = $proxy.affect_continuity.ready
    LiveBroadcastEnabled = $proxy.show_arc.enabled
    LiveBroadcastReady = $proxy.show_arc.ready
    LiveBroadcastEvaluationClock = $proxy.show_arc.evaluation_clock
    LLMWarmup = if ($warmup) { $warmup.StatusCode } else { $null }
    ChatProvider = $ChatProvider
    ChatModel = $effectiveChatModel
    ChatModelEnforced = $proxy.chat_model.enforced
    ChatModelDigest = $proxy.chat_model.digest.digest
    ChatModelDigestStatus = $proxy.chat_model.digest.status
    CharacterEvaluatorModel = if ($EnableCharacterEvaluator) { $effectiveEvaluatorModel } else { '' }
    NumCtx = $NumCtx
    NumGpu = $proxy.num_gpu
    TTS = $tts.status
    TTSEngine = $tts.engine
    VoiceReferenceFound = $tts.reference_audio_found
    STTMode = $Stt
    STT = if ($Stt -eq 'on') { $sttHealth.status } else { 'disabled' }
    STTModel = if ($Stt -eq 'on') { $sttHealth.model } else { '' }
    STTDevice = if ($Stt -eq 'on') { $sttHealth.device } else { '' }
}
