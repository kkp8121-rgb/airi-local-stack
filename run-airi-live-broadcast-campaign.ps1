param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDir,
    [Parameter(Mandatory = $true)]
    [string]$ChatModel,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$ChatModelDigest,
    [string]$Show = 'airi-synthetic-broadcast-eval',
    [string]$Seeds = '101,202,303',
    [ValidateRange(500, 100000)]
    [int]$Turns = 500,
    [ValidateRange(512, 32768)]
    [int]$NumCtx = 4096,
    # R2 F7: a campaign is only ever run for the arm a blind comparator named
    # as its unique passing winner.  Both files are the launcher's own retained
    # evidence (comparisons\<profile>-blind.json, evidence\model-manifest.json);
    # the gate refuses anything else before a single service starts.
    [Parameter(Mandatory = $true)]
    [string]$ComparatorVerdict,
    [Parameter(Mandatory = $true)]
    [string]$ModelManifest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$outputRoot = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $outputRoot) {
    throw 'OutputDir must not already exist; campaign evidence is append-inert and never overwritten.'
}
if ($Show -notmatch '^[A-Za-z0-9_-]{3,64}$') {
    throw 'Show must contain only 3-64 ASCII letters, digits, underscore, or hyphen.'
}

function Test-AiriCampaignWinnerGate {
    param(
        [string]$VerdictPath,
        [string]$ManifestPath,
        [string]$ExpectedTag,
        [string]$ExpectedDigest
    )
    foreach ($path in @($VerdictPath, $ManifestPath)) {
        $item = Get-Item -LiteralPath $path -ErrorAction Stop
        if ($item.PSIsContainer -or $item -isnot [IO.FileInfo]) {
            throw "Campaign gate input must be a regular file: $path"
        }
    }
    $verdict = Get-Content -LiteralPath $VerdictPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($name in @('schema_version', 'status', 'winner', 'adoption_authorized', 'arms')) {
        if (-not $verdict.PSObject.Properties[$name]) {
            throw "Comparator verdict lacks '$name'; refusing to run a campaign on it."
        }
    }
    if ([string]$verdict.schema_version -notmatch '^airi\.[a-z0-9-]+-blind-comparison\.v[0-9]+$') {
        throw 'Comparator verdict schema is not a blind comparison verdict.'
    }
    if ([string]$verdict.status -cne 'pass') {
        throw 'Comparator verdict status is not pass; campaign refused.'
    }
    if ($verdict.adoption_authorized -ne $false) {
        throw 'Comparator verdict must carry adoption_authorized=false; a campaign is not adoption.'
    }
    $winner = $verdict.winner
    if ($null -eq $winner -or [string]::IsNullOrWhiteSpace([string]$winner)) {
        throw 'Comparator verdict names no winner (no_winner); campaign refused.'
    }
    $winner = [string]$winner
    if (@($verdict.arms | Where-Object { [string]$_ -ceq $winner }).Count -ne 1) {
        throw 'Comparator winner is not one of the verdict arms.'
    }
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $manifest.PSObject.Properties['arms']) { throw 'Model manifest lacks arms.' }
    $arm = @($manifest.arms | Where-Object { [string]$_.name -ceq $winner })
    if ($arm.Count -ne 1) { throw "Model manifest does not pin exactly one arm named '$winner'." }
    if ([string]$arm[0].tag -cne $ExpectedTag -or [string]$arm[0].digest -cne $ExpectedDigest) {
        throw 'ChatModel/ChatModelDigest do not match the comparator winner arm; campaign refused.'
    }
    return $winner
}

$campaignWinner = Test-AiriCampaignWinnerGate `
    -VerdictPath $ComparatorVerdict -ManifestPath $ModelManifest `
    -ExpectedTag $ChatModel -ExpectedDigest $ChatModelDigest
Write-Output "Campaign winner gate passed for arm '$campaignWinner'."

$ownedPorts = @(11435, 11436, 8880, 9880, 8892, 8890)
$occupied = @(
    foreach ($port in $ownedPorts) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if ($listener) { $port }
    }
)
if ($occupied.Count -gt 0) {
    throw "Campaign requires fresh owned services; occupied port(s): $($occupied -join ', ')."
}

function New-AiriCampaignCapability {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) }
    finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Restore-AiriEnvironmentValue {
    param([string]$Name, [object]$Previous)
    if ($null -eq $Previous) {
        [Environment]::SetEnvironmentVariable($Name, $null, 'Process')
    }
    else {
        [Environment]::SetEnvironmentVariable($Name, [string]$Previous, 'Process')
    }
}

function Get-AiriCampaignOwnedServicePids {
    param([int[]]$Ports)
    $owners = @{}
    foreach ($port in $Ports) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        $pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
        if ($pids.Count -ne 1 -or [int]$pids[0] -le 0) {
            throw "Campaign service on port $port must have exactly one owning PID."
        }
        $owners[[string]$port] = [int]$pids[0]
    }
    return $owners
}

function Stop-AiriCampaignOwnedServices {
    param(
        [hashtable]$Owners,
        [hashtable]$IdentityVerifiedOwners
    )
    foreach ($portKey in @($Owners.Keys | Sort-Object -Descending)) {
        $port = [int]$portKey
        $expectedPid = [int]$Owners[$portKey]
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        $stillOwned = @($listeners | Where-Object { [int]$_.OwningProcess -eq $expectedPid })
        $verifiedWithoutListener =
            $IdentityVerifiedOwners.ContainsKey($portKey) -and
            [int]$IdentityVerifiedOwners[$portKey] -eq $expectedPid
        if ($stillOwned.Count -eq 0 -and -not $verifiedWithoutListener) {
            Write-Warning "Campaign-owned service PID $expectedPid no longer owns port $port; it was not stopped."
            continue
        }
        $process = Get-Process -Id $expectedPid -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        Stop-Process -Id $expectedPid -Force -ErrorAction Stop
        Write-Output "Stopped campaign-owned service on port $port (PID $expectedPid)."
    }
}

function Get-AiriCampaignPartialServicePids {
    param(
        [int[]]$Ports,
        [DateTime]$StartedAfterUtc
    )
    $owners = @{}
    $recentProcesses = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ProcessId -gt 0 -and $_.CommandLine -and $_.CreationDate -and
            ([DateTime]$_.CreationDate).ToUniversalTime() -ge $StartedAfterUtc
        }
    )
    foreach ($port in $Ports) {
        $matches = @($recentProcesses | Where-Object {
            $command = [string]$_.CommandLine
            switch ($port) {
                11435 {
                    $command.IndexOf((Join-Path $projectRoot 'ollama-proxy\ollama_proxy.py'), [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
                    $command -match '(?:^|\s)--port\s+11435(?:\s|$)'
                }
                8880 {
                    $command.IndexOf((Join-Path $projectRoot 'gpt-sovits\openai_compatible_proxy.py'), [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
                    $command -match '(?:^|\s)--port\s+8880(?:\s|$)'
                }
                9880 {
                    $command.IndexOf((Join-Path $projectRoot 'gpt-sovits\run_v2proplus_with_sv_cache.py'), [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
                    $command -match '(?:^|\s)-p\s+9880(?:\s|$)'
                }
                8892 {
                    $command.IndexOf((Join-Path $projectRoot 'latency-monitor\monitor_server.py'), [StringComparison]::OrdinalIgnoreCase) -ge 0
                }
                default { $false }
            }
        })
        if ($matches.Count -eq 1) {
            $owners[[string]$port] = [int]$matches[0].ProcessId
        }
        elseif ($matches.Count -gt 1) {
            Write-Warning "Multiple campaign process identities matched port $port; none were stopped."
        }
    }
    return $owners
}

function Wait-AiriCampaignKnowledgeReady {
    param([int]$Attempts = 120)
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/health' -Method Get -TimeoutSec 3
            $knowledge = $health.knowledge
            if (
                $health.status -eq 'ok' -and
                $knowledge.enabled -eq $true -and
                $knowledge.ready -eq $true -and
                ([int]$knowledge.documents) -gt 0 -and
                ([int]$knowledge.chunks) -gt 0
            ) {
                return
            }
        }
        catch {
            # The fresh proxy may still be starting or completing its local index setup.
        }
        Start-Sleep -Milliseconds 250
    }
    throw 'Campaign knowledge service did not become ready before attestation.'
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$runtimeRoot = Join-Path $outputRoot 'runtime'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$memoryDb = Join-Path $runtimeRoot 'memory.sqlite3'
$knowledgeDb = Join-Path $runtimeRoot 'knowledge.sqlite3'
$sourceFixture = Join-Path $projectRoot 'ollama-proxy\eval\airi_live_campaign_knowledge_fixture.json'
$runtimeFixture = Join-Path $runtimeRoot 'approved-knowledge-fixture.json'
$knowledgeAttestation = Join-Path $outputRoot 'approved-knowledge-attestation.json'
Copy-Item -LiteralPath $sourceFixture -Destination $runtimeFixture -ErrorAction Stop

$python = (Get-Command python -ErrorAction Stop).Source
& $python (Join-Path $projectRoot 'ollama-proxy\knowledge_ingest.py') `
    --runtime-dir $runtimeRoot `
    --input $runtimeFixture `
    --db $knowledgeDb `
    --apply
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $knowledgeDb -PathType Leaf)) {
    throw 'Failed to prepare the isolated approved-knowledge database.'
}

$master = New-AiriCampaignCapability
$observer = New-AiriCampaignCapability
if ($master -ceq $observer) { throw 'Campaign capabilities must be distinct.' }
$previousMaster = [Environment]::GetEnvironmentVariable('AIRI_LIVE_BROADCAST_MASTER_TOKEN', 'Process')
$previousObserver = [Environment]::GetEnvironmentVariable('AIRI_LIVE_BROADCAST_OBSERVER_TOKEN', 'Process')
$previousAck = [Environment]::GetEnvironmentVariable('AIRI_IMMEDIATE_ACK', 'Process')
$previousCache = [Environment]::GetEnvironmentVariable('AIRI_GPT_SOVITS_SV_CACHE', 'Process')
$previousStreamingMode = [Environment]::GetEnvironmentVariable('GPT_SOVITS_STREAMING_MODE', 'Process')
$previousMinChunkLength = [Environment]::GetEnvironmentVariable('GPT_SOVITS_MIN_CHUNK_LENGTH', 'Process')
$stackAttempted = $false
$stackStartUtc = [DateTime]::MinValue
$ownedServicePids = @{}
$campaignSucceeded = $false
try {
    $env:AIRI_IMMEDIATE_ACK = 'marker'
    $env:AIRI_GPT_SOVITS_SV_CACHE = 'on'
    $env:GPT_SOVITS_STREAMING_MODE = '2'
    $env:GPT_SOVITS_MIN_CHUNK_LENGTH = '16'
    $stackAttempted = $true
    $stackStartUtc = [DateTime]::UtcNow
    & (Join-Path $projectRoot 'start-airi-local-stack.ps1') `
        -Stt off `
        -OllamaNumGpu 999 `
        -NumCtx $NumCtx `
        -EnableMemory $true `
        -EnableKnowledge $true `
        -MemoryDbPath $memoryDb `
        -KnowledgeDbPath $knowledgeDb `
        -EnableMemoryExtraction $false `
        -AllowExternalMemoryExtraction $false `
        -ChatProvider local `
        -AllowExternalChat $false `
        -ChatModel $ChatModel `
        -ChatModelDigest $ChatModelDigest `
        -OutputModeration on `
        -InputScreening on `
        -EpistemicConfidence on `
        -AffectContinuity on `
        -LiveBroadcast `
        -LiveBroadcastEvalClock `
        -LiveBroadcastMasterTokenOverride $master `
        -LiveBroadcastObserverTokenOverride $observer `
        -AllowExternalSearch $false

    # Record only the fresh listeners started for this campaign. Cleanup must
    # never use repository-wide process-name matching because another local
    # stack may be running the same scripts on unrelated ports.
    $ownedServicePids = Get-AiriCampaignOwnedServicePids -Ports @(11435, 8880, 9880, 8892)
    Wait-AiriCampaignKnowledgeReady
    & $python (Join-Path $projectRoot 'ollama-proxy\eval\live_broadcast_campaign\live_campaign.py') `
        --write-approved-knowledge-manifest `
        --fixture $runtimeFixture `
        --knowledge-db $knowledgeDb `
        --output $knowledgeAttestation
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $knowledgeAttestation -PathType Leaf)) {
        throw 'Failed to create the content-free approved knowledge attestation manifest.'
    }

    $env:AIRI_LIVE_BROADCAST_MASTER_TOKEN = $master
    $env:AIRI_LIVE_BROADCAST_OBSERVER_TOKEN = $observer
    & $python (Join-Path $projectRoot 'ollama-proxy\eval\live_broadcast_campaign\live_campaign.py') `
        --show $Show `
        --seeds $Seeds `
        --turns $Turns `
        --output-dir $outputRoot `
        --approved-knowledge-manifest $knowledgeAttestation `
        --model $ChatModel `
        --timeout 300
    if ($LASTEXITCODE -ne 0) { throw 'Live broadcast campaign failed.' }

    & $python (Join-Path $projectRoot 'ollama-proxy\eval\live_broadcast_campaign\verify_campaign.py') $outputRoot `
        --approved-knowledge-manifest $knowledgeAttestation
    if ($LASTEXITCODE -ne 0) { throw 'Live broadcast campaign verifier rejected the evidence.' }
    $campaignSucceeded = $true
}
finally {
    Restore-AiriEnvironmentValue 'AIRI_LIVE_BROADCAST_MASTER_TOKEN' $previousMaster
    Restore-AiriEnvironmentValue 'AIRI_LIVE_BROADCAST_OBSERVER_TOKEN' $previousObserver
    Restore-AiriEnvironmentValue 'AIRI_IMMEDIATE_ACK' $previousAck
    Restore-AiriEnvironmentValue 'AIRI_GPT_SOVITS_SV_CACHE' $previousCache
    Restore-AiriEnvironmentValue 'GPT_SOVITS_STREAMING_MODE' $previousStreamingMode
    Restore-AiriEnvironmentValue 'GPT_SOVITS_MIN_CHUNK_LENGTH' $previousMinChunkLength
    $master = $null
    $observer = $null
    if ($stackAttempted) {
        # A launcher can fail after starting only a subset of services. Recover
        # those listeners only when their process was created by this attempt
        # and its exact script/port identity matches the campaign contract.
        $partialOwners = Get-AiriCampaignPartialServicePids `
            -Ports @(11435, 8880, 9880, 8892) `
            -StartedAfterUtc $stackStartUtc
        foreach ($portKey in $partialOwners.Keys) {
            if (-not $ownedServicePids.ContainsKey($portKey)) {
                $ownedServicePids[$portKey] = $partialOwners[$portKey]
            }
        }
        if ($ownedServicePids.Count -gt 0) {
            Stop-AiriCampaignOwnedServices `
                -Owners $ownedServicePids `
                -IdentityVerifiedOwners $partialOwners
        }
    }
}

if (-not $campaignSucceeded) { throw 'Campaign did not complete.' }
[pscustomobject]@{
    Status = 'complete'
    OutputDir = $outputRoot
    Model = $ChatModel
    Turns = $Turns
    Seeds = $Seeds
    ExternalChat = $false
    ExternalSearch = $false
    MemoryExtraction = $false
    Stt = 'off'
}
