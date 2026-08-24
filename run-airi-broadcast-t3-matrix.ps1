<#
Run the deliberately small, isolated T3 matrix.  This is an evidence launcher,
not an adoption command: it never prints capability material or DB locations.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$OutputDir,
    [Parameter(Mandatory)] [string]$ModelManifest,
    [string]$FixtureManifest = (Join-Path $PSScriptRoot 'ollama-proxy\eval\broadcast_sim\t3_fixture_manifest_v2.json'),
    # 't3' is the pinned baseline/e1/e2 matrix.  'e2c1' runs the frozen E2-C1
    # blind evaluation: baseline/e2/e2-c1 over the sealed external blind root.
    # 'e2c2' runs the frozen E2-C2 blind evaluation (baseline/e2/e2-c2) over its
    # own sealed root, with the proxy handle-grounding guard pinned ON and
    # attested per run through /health.
    [ValidateSet('t3','e2c1','e2c2')] [string]$MatrixProfile = 't3',
    [string]$BlindRoot = '',
    # Offline contract-test seam; production always performs the localhost lookup.
    [string]$OllamaTagsFile = '',
    [switch]$PreflightOnly,
    [string]$HealthFixtureFile = '',
    [string]$ReportFixtureFile = '',
    [string]$ReportPlanFixtureFile = '',
    [string]$FixtureArmName = 'baseline',
    [int]$ReportFixtureIndex = 1,
    [int]$ReportFixtureSeed = 11,
    [ValidateRange(512, 32768)] [int]$NumCtx = 2048
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$out = [IO.Path]::GetFullPath($OutputDir)
$python = (Get-Command python -ErrorAction Stop).Source
$ports = @(11435, 11436, 8880, 9880, 8892, 8890)
$isBlindProfile = ($MatrixProfile -ceq 'e2c1' -or $MatrixProfile -ceq 'e2c2')
# The e2c2 matrix is measured with the handle-grounding guard ON; /health must
# prove it on every run because the report schema has no field for it.
$requireGuardHealth = ($MatrixProfile -ceq 'e2c2')

function New-Capability {
    $b = New-Object byte[] 48; $r = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $r.GetBytes($b) } finally { $r.Dispose() }
    [Convert]::ToBase64String($b).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
function Restore-Env([string]$Name, [object]$Value) {
    [Environment]::SetEnvironmentVariable($Name, $(if ($null -eq $Value) { $null } else { [string]$Value }), 'Process')
}
function Get-BytesSha256([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { -join @($sha.ComputeHash($Bytes) | ForEach-Object { $_.ToString('x2') }) }
    finally { $sha.Dispose() }
}
function Get-CanonicalJsonSha256([string]$Path) {
    $code = "import hashlib,json,sys; p=json.load(open(sys.argv[1],encoding='utf-8')); b=json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'); print(hashlib.sha256(b).hexdigest())"
    $value = @(& $python -c $code $Path)
    if ($LASTEXITCODE -ne 0 -or $value.Count -ne 1 -or $value[0] -notmatch '^[0-9a-f]{64}$') { throw 'Canonical JSON SHA-256 calculation failed.' }
    [string]$value[0]
}
function Write-JsonNoOverwrite([string]$Path, [object]$Value) {
    if (Test-Path -LiteralPath $Path) { throw "Evidence already exists: $Path" }
    $parent = Split-Path -Parent $Path; [IO.Directory]::CreateDirectory($parent) | Out-Null
    $temp = Join-Path $parent ('.tmp-' + [guid]::NewGuid().ToString('N'))
    try {
        [IO.File]::WriteAllText($temp, ($Value | ConvertTo-Json -Depth 32 -Compress) + "`n", [Text.UTF8Encoding]::new($false))
        [IO.File]::Move($temp, $Path)
    } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force } }
}
function Copy-NoOverwrite([string]$Source, [string]$Destination) {
    if (Test-Path -LiteralPath $Destination) { throw "Evidence already exists: $Destination" }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Destination)) | Out-Null
    $tmp = "$Destination.tmp-$([guid]::NewGuid().ToString('N'))"
    try { Copy-Item -LiteralPath $Source -Destination $tmp -ErrorAction Stop; [IO.File]::Move($tmp, $Destination) }
    finally { if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force } }
}
function Get-Listeners { param([int[]]$ForPorts) @($ForPorts | ForEach-Object { Get-NetTCPConnection -State Listen -LocalPort $_ -ErrorAction SilentlyContinue } | Where-Object { $_ }) }
function Get-OwnedPortKey([string]$CommandLine) {
    if ($CommandLine.IndexOf((Join-Path $root 'ollama-proxy\ollama_proxy.py'), [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $CommandLine -match '(?:^|\s)--port\s+11435(?:\s|$)') { return '11435' }
    if ($CommandLine.IndexOf((Join-Path $root 'gpt-sovits\openai_compatible_proxy.py'), [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $CommandLine -match '(?:^|\s)--port\s+8880(?:\s|$)') { return '8880' }
    if ($CommandLine.IndexOf((Join-Path $root 'gpt-sovits\run_v2proplus_with_sv_cache.py'), [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $CommandLine -match '(?:^|\s)-p\s+9880(?:\s|$)') { return '9880' }
    if ($CommandLine.IndexOf((Join-Path $root 'latency-monitor\monitor_server.py'), [StringComparison]::OrdinalIgnoreCase) -ge 0) { return '8892' }
    $null
}
function Stop-Owned([hashtable]$Owners) {
    $failures = @()
    foreach ($port in @($Owners.Keys)) {
        $ownerProcessId = [int]$Owners[$port]
        $identity = @(Get-CimInstance Win32_Process -Filter "ProcessId = $ownerProcessId" -ErrorAction SilentlyContinue)
        if ($identity.Count -eq 1 -and
            (Get-OwnedPortKey ([string]$identity[0].CommandLine)) -ceq [string]$port) {
            try {
                $stoppedProcess = Stop-Process -Id $ownerProcessId -Force -PassThru -ErrorAction Stop
                if (-not $stoppedProcess.WaitForExit(10000)) { throw 'Owned process did not exit within ten seconds.' }
            }
            catch { $failures += [string]$port }
        }
    }
    @($failures)
}
function Assert-OwnedListeners([hashtable]$Owners) {
    foreach ($requiredPort in @(11435, 8880, 9880, 8892)) {
        $portKey = [string]$requiredPort
        if (-not $Owners.ContainsKey($portKey)) { throw "T3-owned listener identity missing for port $requiredPort." }
        $ownerProcessId = [int]$Owners[$portKey]
        $matches = @(Get-NetTCPConnection -State Listen -LocalPort $requiredPort -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $ownerProcessId })
        if ($matches.Count -eq 0) { throw "T3-owned process does not own port $requiredPort." }
    }
}
function Get-RecentOwned([datetime]$Since) {
    # Resolve ownership from the actual listening socket first.  Start-Process
    # may insert a launcher process, so command-line enumeration alone can
    # produce multiple identities for one port.
    $found = @{}
    foreach ($listener in @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)) {
        $portKey = Get-OwnedPortKey ([string](Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue).CommandLine)
        if ($null -eq $portKey -or $found.ContainsKey($portKey)) { continue }
        $identity = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($identity -and $identity.CreationDate -and ([datetime]$identity.CreationDate).ToUniversalTime() -ge $Since) {
            $found[$portKey] = [int]$listener.OwningProcess
        }
    }
    $found
}
function Test-ExactBoolean([object]$Value, [bool]$Expected) {
    $null -ne $Value -and $Value.GetType() -eq [bool] -and [bool]$Value -eq $Expected
}
function Test-ExactInteger([object]$Value, [long]$Expected) {
    $null -ne $Value -and ($Value.GetType() -eq [int] -or $Value.GetType() -eq [long]) -and [long]$Value -eq $Expected
}
function Assert-Health([object]$H, [object]$Arm) {
    if ($H.status -cne 'ok' -or $H.chat_model.provider -cne 'local' -or
        -not (Test-ExactBoolean $H.chat_provider.external_approved $false) -or
        -not (Test-ExactBoolean $H.chat_provider.configured $true) -or
        -not (Test-ExactBoolean $H.chat_provider.ready $false) -or
        $H.chat_model.model -cne $Arm.tag -or -not (Test-ExactBoolean $H.chat_model.enforced $true) -or
        $H.chat_model.digest.status -cne 'pinned' -or -not (Test-ExactBoolean $H.chat_model.digest.verified $true) -or
        $H.chat_model.digest.digest -cne $Arm.digest -or -not (Test-ExactInteger $H.num_ctx $NumCtx) -or
        $H.immediate_ack -cne 'marker' -or -not (Test-ExactBoolean $H.broadcast_contract $true) -or
        -not (Test-ExactBoolean $H.memory.enabled $true) -or -not (Test-ExactBoolean $H.memory.ready $true) -or
        -not (Test-ExactBoolean $H.knowledge.enabled $true) -or -not (Test-ExactBoolean $H.knowledge.ready $true) -or
        -not (Test-ExactInteger $H.knowledge.documents 0) -or -not (Test-ExactInteger $H.knowledge.chunks 0) -or
        -not (Test-ExactInteger $H.knowledge.accepted_chunks 0) -or
        -not (Test-ExactBoolean $H.input_screening.enabled $true) -or -not (Test-ExactBoolean $H.input_screening.ready $true) -or
        -not (Test-ExactBoolean $H.output_moderation.enabled $true) -or -not (Test-ExactBoolean $H.output_moderation.ready $true) -or
        -not (Test-ExactBoolean $H.epistemic_confidence.enabled $true) -or $H.epistemic_confidence.mode -cne 'enforce' -or
        -not (Test-ExactBoolean $H.affect_continuity.enabled $true) -or -not (Test-ExactBoolean $H.affect_continuity.ready $true) -or
        -not (Test-ExactBoolean $H.show_arc.enabled $true) -or -not (Test-ExactBoolean $H.show_arc.ready $true) -or
        -not (Test-ExactBoolean $H.show_arc.evaluation_clock $true) -or
        -not (Test-ExactBoolean $H.broadcast_affect.enabled $true) -or -not (Test-ExactBoolean $H.broadcast_affect.ready $true) -or
        -not (Test-ExactBoolean $H.broadcast_affect.evaluation_clock $true)) { throw 'T3 health attestation differs from the pinned isolated contract.' }
    if ($requireGuardHealth) {
        $guardProperty = $H.PSObject.Properties['handle_grounding_guard']
        if ($null -eq $guardProperty -or -not (Test-ExactBoolean $guardProperty.Value $true)) {
            throw 'E2-C2 health attestation does not prove the handle grounding guard is ON.'
        }
    }
}
function Assert-TtsHealth([object]$H) {
    if ($H.status -cne 'ok' -or $H.engine -cne 'gpt-sovits-v2ProPlus' -or
        -not (Test-ExactBoolean $H.reference_audio_found $true) -or
        -not (Test-ExactInteger $H.streaming_contract.mode 2) -or
        -not (Test-ExactInteger $H.streaming_contract.min_chunk_length 16) -or
        $H.streaming_contract.media_type -cne 'wav' -or
        -not (Test-ExactBoolean $H.streaming_contract.parallel_infer $false)) {
        throw 'T3 TTS health differs from the pinned streaming contract.'
    }
}
function Assert-Report([string]$Path, [object]$Arm, [object]$Fixture, [int]$Seed, [string]$PlanPath) {
    $r = Get-Content -Raw -LiteralPath $Path -Encoding utf8 | ConvertFrom-Json
    $plan = Get-Content -Raw -LiteralPath $PlanPath -Encoding utf8 | ConvertFrom-Json
    if (@($plan.picks | Where-Object { -not (Test-ExactInteger $_.turn_index ([long]$_.turn_index)) }).Count -ne 0 -or
        @($r.rows | Where-Object { -not (Test-ExactInteger $_.turn_index ([long]$_.turn_index)) }).Count -ne 0) {
        throw 'Runner report or plan turn_index is not an exact JSON integer.'
    }
    $expectedTurns = @($plan.picks | ForEach-Object { [long]$_.turn_index } | Sort-Object)
    $actualTurns = @($r.rows | ForEach-Object { [long]$_.turn_index } | Sort-Object)
    $turnSetsMatch = $expectedTurns.Count -eq $actualTurns.Count -and
        @($expectedTurns | Sort-Object -Unique).Count -eq $expectedTurns.Count -and
        @($actualTurns | Sort-Object -Unique).Count -eq $actualTurns.Count
    if ($turnSetsMatch) {
        for ($index=0; $index -lt $expectedTurns.Count; $index++) {
            if ($expectedTurns[$index] -ne $actualTurns[$index]) { $turnSetsMatch = $false; break }
        }
    }
    if ($r.schema_version -cne 'airi.broadcast-sim-report.v1' -or
        $plan.schema_version -cne 'airi.broadcast-sim-report.v1' -or $plan.mode -cne 'stream_only' -or
        -not (Test-ExactInteger $plan.seed $Seed) -or $plan.fixture_sha256 -cne $Fixture.canonical_sha256 -or -not $turnSetsMatch -or
        $r.model -cne $Arm.tag -or $r.memory_arm -cne 'seeded' -or $r.contract -cne 'on' -or $r.protocol -cne 'operational' -or
        $r.author_format -cne 'runtime' -or -not (Test-ExactInteger $r.history_turns 8) -or
        $r.briefing -cne 'on' -or $r.briefing_evidence -cne 'on' -or $r.acts -cne 'on' -or $r.live_broadcast_context -cne 'on' -or
        -not (Test-ExactBoolean $r.live_contract_verified $true) -or -not (Test-ExactInteger $r.seed $Seed) -or $r.fixture_sha256 -cne $Fixture.canonical_sha256 -or
        -not (Test-ExactInteger $r.summary.transport_failures 0) -or -not @($r.rows).Count -or
        -not (Test-ExactInteger $r.summary.turns @($r.rows).Count) -or
        @($r.rows.live_action_id | Sort-Object -Unique).Count -ne @($r.rows).Count -or
        @($r.rows.live_trace_id | Sort-Object -Unique).Count -ne @($r.rows).Count -or
        @($r.rows | Where-Object {
            -not (Test-ExactBoolean $_.live_broadcast_context $true) -or
            -not (Test-ExactBoolean $_.live_receipt_bound $true) -or
            $_.live_action_id -notmatch '.+' -or $_.live_trace_id -notmatch '.+' -or $_.failure
        }).Count -ne 0) { throw 'Runner report does not prove the complete T3 live/durable receipt contract.' }
}

# Everything below this line is preflight-only until the manifest and all fixtures validate.
if (Test-Path -LiteralPath $out) { throw 'OutputDir must not exist: evidence is no-overwrite.' }
if ($isBlindProfile -and -not $BlindRoot) { throw "The $MatrixProfile profile requires -BlindRoot." }
if (-not $isBlindProfile -and $BlindRoot) { throw '-BlindRoot is only valid for the e2c1 and e2c2 profiles.' }
if (($OllamaTagsFile -or $HealthFixtureFile -or $ReportFixtureFile -or $ReportPlanFixtureFile) -and -not $PreflightOnly) { throw 'Offline fixture seams are PreflightOnly and forbidden for production runs.' }
$strictUtf8 = [Text.UTF8Encoding]::new($false, $true)
$modelManifestBytes = [IO.File]::ReadAllBytes((Get-Item -LiteralPath $ModelManifest -ErrorAction Stop).FullName)
$modelManifestSha256 = Get-BytesSha256 $modelManifestBytes
$armsDoc = $strictUtf8.GetString($modelManifestBytes) | ConvertFrom-Json
$armProperties = @($armsDoc.PSObject.Properties.Name | Sort-Object)
if ($armsDoc.schema_version -cne 'airi.broadcast-sim-t3-model-manifest.v2' -or $armProperties.Count -ne 2 -or $armProperties[0] -cne 'arms' -or $armProperties[1] -cne 'schema_version') { throw 'Model manifest schema or key set is invalid.' }
$arms = @($armsDoc.arms)
$armNames = @($arms.name | Sort-Object)
$expectedArmNames = if ($MatrixProfile -ceq 'e2c1') { @('baseline','e2','e2-c1') } elseif ($MatrixProfile -ceq 'e2c2') { @('baseline','e2','e2-c2') } else { @('baseline','e1','e2') }
$armNamesMatch = $arms.Count -eq 3 -and @($arms.name | Sort-Object -Unique).Count -eq 3 -and $armNames.Count -eq 3
if ($armNamesMatch) { for ($i=0; $i -lt 3; $i++) { if ($armNames[$i] -cne $expectedArmNames[$i]) { $armNamesMatch = $false; break } } }
if (-not $armNamesMatch) { throw "Model manifest must contain exactly $($expectedArmNames -join ', ')." }
foreach ($arm in $arms) {
    $keys = @($arm.PSObject.Properties.Name | Sort-Object)
    if ($keys.Count -ne 3 -or $keys[0] -cne 'digest' -or $keys[1] -cne 'name' -or $keys[2] -cne 'tag' -or
        $arm.tag -notmatch '^[^\s]+$' -or $arm.digest -notmatch '^[0-9a-f]{64}$') {
        throw 'Each model arm needs only name, tag, and lowercase 64-hex digest.'
    }
}
if (@($arms.tag | Sort-Object -Unique).Count -ne 3 -or @($arms.digest | Sort-Object -Unique).Count -ne 3) { throw 'T3 model tags and digests must each be distinct.' }
$arms = @(
    @($arms | Where-Object { $_.name -ceq $expectedArmNames[0] }) +
    @($arms | Where-Object { $_.name -ceq $expectedArmNames[1] }) +
    @($arms | Where-Object { $_.name -ceq $expectedArmNames[2] })
)
if ($isBlindProfile) {
    # The blind bodies stay outside the repository; only their size and hashes
    # are read here, and only against the frozen in-repo commitment.
    if ($MatrixProfile -ceq 'e2c1') {
        $blindCommitmentFile = 'airi_e2_c1_blind_commitment.json'
        $blindPolicyFile = 'airi_e2_c1_metric_policy.json'
        $blindCommitmentSchema = 'airi.e2-c1-blind-commitment.v1'
        $blindRootId = 'airi-e2-c1-blind-freeze-20260824-v2'
        $expectedSealedSha256 = 'ce81bbb59edd473210b0c5b6637a5728827fef3e56e077786f213b52f989c9d4'
    } else {
        $blindCommitmentFile = 'airi_e2_c2_blind_commitment.json'
        $blindPolicyFile = 'airi_e2_c2_metric_policy.json'
        $blindCommitmentSchema = 'airi.e2-c2-blind-commitment.v1'
        $blindRootId = 'airi-e2-c2-blind-freeze-20260824-v3'
        $expectedSealedSha256 = 'f878fe2e01713ccf4024771e66d44ee83ee626509cadf7252878d8df37484931'
    }
    $commitmentPath = Join-Path $root ('ollama-proxy\eval\broadcast_sim\fixtures\commitments\' + $blindCommitmentFile)
    $commitmentBytes = [IO.File]::ReadAllBytes((Get-Item -LiteralPath $commitmentPath -ErrorAction Stop).FullName)
    $commitmentSha256 = Get-BytesSha256 $commitmentBytes
    $commitment = $strictUtf8.GetString($commitmentBytes) | ConvertFrom-Json
    if ($commitment.schema_version -cne $blindCommitmentSchema -or
        $commitment.root_id -cne $blindRootId -or
        [int]$commitment.expected_matrix_reports -ne 36) { throw 'Blind commitment schema or root is invalid.' }
    $blindRootPath = [IO.Path]::GetFullPath((Get-Item -LiteralPath $BlindRoot -ErrorAction Stop).FullName)
    $fixtures = @($commitment.fixtures)
    if ($fixtures.Count -ne 3 -or @($fixtures.logical_role | Sort-Object -Unique).Count -ne 3) { throw 'Blind commitment must pin exactly three distinct blind fixtures.' }
    $fixtureKeys = @($fixtures.logical_role)
    $expectedCanon = @($fixtures.canonical_sha256)
    $expectedRaw = @($fixtures.raw_sha256)
    $commitmentSeeds = @($commitment.seeds)
    if ($commitmentSeeds.Count -ne 4) { throw 'Blind commitment must pin exactly four seeds.' }
    $seedSets = @($commitmentSeeds, $commitmentSeeds, $commitmentSeeds)
    for ($i=0; $i -lt 3; $i++) {
        $f = $fixtures[$i]; $file = Join-Path $blindRootPath $f.filename
        $item = Get-Item -LiteralPath $file -ErrorAction Stop
        if ($item.PSIsContainer -or [long]$item.Length -ne [long]$f.size_bytes -or
            (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedRaw[$i] -or
            (Get-CanonicalJsonSha256 $file) -cne $expectedCanon[$i]) { throw 'Blind fixture size or hash binding is invalid.' }
    }
    $sealedManifestPath = Join-Path $blindRootPath 'sealed_manifest.json'
    if ((Get-FileHash -LiteralPath $sealedManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedSealedSha256) { throw 'Sealed blind manifest raw SHA-256 is invalid.' }
} else {
    $fixtureManifestBytes = [IO.File]::ReadAllBytes((Get-Item -LiteralPath $FixtureManifest -ErrorAction Stop).FullName)
    $fixtureManifestSha256 = Get-BytesSha256 $fixtureManifestBytes
    $fixturesDoc = $strictUtf8.GetString($fixtureManifestBytes) | ConvertFrom-Json
    $fixtures = @($fixturesDoc.fixtures | Sort-Object creation_order)
    if ($fixtures.Count -ne 3 -or [int]$fixtures[0].creation_order -ne 1 -or [int]$fixtures[1].creation_order -ne 2 -or [int]$fixtures[2].creation_order -ne 3) { throw 'Fixture manifest must contain first/second/third in exact creation order.' }
    $expectedManifestHash='d150bf0d928da565ab1d29885b2eb494e52f806b04d384ed9bbf124609953bd8'; if ($fixtureManifestSha256 -cne $expectedManifestHash) { throw 'Fixture manifest raw SHA-256 differs from the approved T3 manifest.' }
    $expectedCanon = @('0d558c0ce3e019569673ed96f4f171e3464e1e044028e7de6b7ede9d5b8085d6','c2ae8a2db00f8f0ed8bd4ee4d909bde965bcbf18dd359b8dbaf340f4c65a57b1','ddb43f03f88dacff70ebd8a6221274e51348e01e9fe542153139c0330bd52b61')
    $expectedRaw = @('d6cdd694e76ac4017ca1cdebb60ba09c337efa6a1813ce9c00c91b03d4ffcc9c','22692a9d24f25cbb6877c297ffc23c93e7d0a74028ddff5072b899e648583760','4e0f018729857b8f4648496298abf2f358a1ad19098f2927d6ec1356809a9897')
    $fixtureKeys = @('1','2','3')
    $seedSets = @(@(11,22,33,20260818),@(11,22,33,20260818),@(44,55,66,20260822))
    for ($i=0; $i -lt 3; $i++) { $f=$fixtures[$i]; $file=Join-Path (Split-Path $FixtureManifest) $f.filename; if ($f.canonical_sha256 -cne $expectedCanon[$i] -or $f.raw_sha256 -cne $expectedRaw[$i] -or -not (Test-Path -LiteralPath $file) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedRaw[$i]) { throw 'Fixture manifest hash binding is invalid.' } }
}
$plannedKeys = @()
foreach ($arm in $arms) {
    for ($i=0; $i -lt 3; $i++) {
        foreach ($seed in $seedSets[$i]) {
            $plannedKeys += "$($arm.name)-$($fixtureKeys[$i])-$seed"
        }
    }
}
if ($plannedKeys.Count -ne 36 -or @($plannedKeys | Sort-Object -Unique).Count -ne 36) { throw 'T3 plan must contain exactly 36 unique run keys.' }
if (@(Get-Listeners $ports).Count -ne 0) { throw 'T3 requires no pre-existing owned service listeners.' }
# This is the final preflight before any output directory or service is created.
try {
    $tagResponse = if ($OllamaTagsFile) { Get-Content -Raw -LiteralPath $OllamaTagsFile -Encoding utf8 | ConvertFrom-Json } else { Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 }
    $localTags = @($tagResponse.models)
} catch { throw 'Local Ollama tag preflight failed (including required E2).' }
foreach ($arm in $arms) {
    $found = @($localTags | Where-Object {
        $tagName = if ($_.PSObject.Properties['name']) { [string]$_.PSObject.Properties['name'].Value } elseif ($_.PSObject.Properties['model']) { [string]$_.PSObject.Properties['model'].Value } else { '' }
        $tagDigest = if ($_.PSObject.Properties['digest']) { [string]$_.PSObject.Properties['digest'].Value } else { '' }
        $tagName -ceq $arm.tag -and $tagDigest.ToLowerInvariant() -ceq $arm.digest
    })
    if ($found.Count -ne 1) { throw "Required pinned arm is absent or ambiguous: $($arm.name)." }
}
if ($PreflightOnly) {
    if ($HealthFixtureFile) {
        $fixtureArm = @($arms | Where-Object { $_.name -ceq $FixtureArmName })
        if ($fixtureArm.Count -ne 1) { throw 'Health fixture arm is not unique.' }
        Assert-Health (Get-Content -Raw -LiteralPath $HealthFixtureFile -Encoding utf8 | ConvertFrom-Json) $fixtureArm[0]
    }
    if ($ReportFixtureFile) {
        if (-not $ReportPlanFixtureFile) { throw 'Report fixture validation requires a stream plan fixture.' }
        if ($ReportFixtureIndex -lt 1 -or $ReportFixtureIndex -gt 3) { throw 'Report fixture index must be 1..3.' }
        Assert-Report $ReportFixtureFile @($arms | Where-Object { $_.name -ceq $FixtureArmName })[0] $fixtures[$ReportFixtureIndex - 1] $ReportFixtureSeed $ReportPlanFixtureFile
    }
    $plannedComparisons = if ($MatrixProfile -ceq 'e2c1') { @('e2c1-blind') } elseif ($MatrixProfile -ceq 'e2c2') { @('e2c2-blind') } else { @('baseline-vs-e1','baseline-vs-e2') }
    [pscustomobject]@{ runs = 36; run_keys = $plannedKeys; arms = @($arms.name); seed_sets = $seedSets; comparisons = $plannedComparisons; common = @{ memory_arm='seeded'; max_tokens=220; timeout_seconds=180; num_ctx=$NumCtx; live_context='on' } } | ConvertTo-Json -Depth 8 -Compress
    exit 0
}

$previousAck = [Environment]::GetEnvironmentVariable('AIRI_IMMEDIATE_ACK','Process')
$previousGuard = [Environment]::GetEnvironmentVariable('AIRI_HANDLE_GROUNDING_GUARD','Process')
$previousMaster = [Environment]::GetEnvironmentVariable('AIRI_LIVE_BROADCAST_MASTER_TOKEN','Process')
$previousObserver = [Environment]::GetEnvironmentVariable('AIRI_LIVE_BROADCAST_OBSERVER_TOKEN','Process')
$previousCache = [Environment]::GetEnvironmentVariable('AIRI_GPT_SOVITS_SV_CACHE','Process')
$previousStreamingMode = [Environment]::GetEnvironmentVariable('GPT_SOVITS_STREAMING_MODE','Process')
$previousMinChunkLength = [Environment]::GetEnvironmentVariable('GPT_SOVITS_MIN_CHUNK_LENGTH','Process')
$previousReferenceAudio = [Environment]::GetEnvironmentVariable('GPT_SOVITS_REFERENCE_AUDIO','Process')
$previousNltkData = [Environment]::GetEnvironmentVariable('NLTK_DATA','Process')
$previousPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH','Process')
$previousPythonIoEncoding = [Environment]::GetEnvironmentVariable('PYTHONIOENCODING','Process')
$previousStackPython = [Environment]::GetEnvironmentVariable('AIRI_STACK_PYTHON','Process')
$created = $false
try {
    # Pin the only supported production TTS identity.  Besides guaranteeing the
    # embedding-cache wrapper on 9880, this makes listener ownership and cleanup
    # use the same exact command identity on every run.
    $env:AIRI_GPT_SOVITS_SV_CACHE = 'on'
    if ($MatrixProfile -ceq 'e2c2') {
        # Pin the handle-grounding guard ON for every proxy this matrix starts;
        # /health attestation and the environment attestation both prove it.
        $env:AIRI_HANDLE_GROUNDING_GUARD = 'on'
    }
    # The training venv is intentionally used for deterministic simulation,
    # but it does not carry the local service web dependencies.  Bind the
    # stack launcher to an existing service venv so the proxy cannot silently
    # die during the ownership/readiness gate.
    $servicePythonCandidates = @(
        (Join-Path $root 'stt\.venv\Scripts\python.exe'),
        (Join-Path $root 'external\GPT-SoVITS\.venv\Scripts\python.exe')
    )
    $servicePython = @($servicePythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1)
    if ($servicePython.Count -ne 1) { throw 'T3 service Python with local web dependencies is unavailable.' }
    $env:AIRI_STACK_PYTHON = [string]$servicePython[0]
    # The simulator also imports httpx; use the same verified interpreter so
    # service and evaluation dependencies cannot drift within one matrix.
    $python = [string]$servicePython[0]
    $env:GPT_SOVITS_STREAMING_MODE = '2'
    $env:GPT_SOVITS_MIN_CHUNK_LENGTH = '16'
    [IO.Directory]::CreateDirectory($out) | Out-Null; $created = $true
    foreach ($d in @('evidence','evidence\plans','reports','packets','comparisons','runtime')) { [IO.Directory]::CreateDirectory((Join-Path $out $d)) | Out-Null }
    foreach ($armDirectory in $expectedArmNames) {
        [IO.Directory]::CreateDirectory((Join-Path $out ('reports\\' + $armDirectory))) | Out-Null
        [IO.Directory]::CreateDirectory((Join-Path $out ('packets\\' + $armDirectory))) | Out-Null
    }
    $evidenceModelManifest = Join-Path $out 'evidence\model-manifest.json'
    Copy-NoOverwrite $ModelManifest $evidenceModelManifest
    if ($isBlindProfile) {
        # The sealed blind bodies are copied only into this external OutputDir;
        # nothing under the repository ever holds them.
        $evidenceCommitment = Join-Path $out 'evidence\blind-commitment.json'
        $evidencePolicy = Join-Path $out 'evidence\blind-metric-policy.json'
        Copy-NoOverwrite $commitmentPath $evidenceCommitment
        Copy-NoOverwrite (Join-Path $root ('ollama-proxy\eval\broadcast_sim\fixtures\commitments\' + $blindPolicyFile)) $evidencePolicy
        Copy-NoOverwrite $sealedManifestPath (Join-Path $out 'evidence\sealed_manifest.json')
        foreach ($f in $fixtures) { Copy-NoOverwrite (Join-Path $blindRootPath $f.filename) (Join-Path $out ('evidence\' + $f.filename)) }
        if ((Get-FileHash -LiteralPath $evidenceCommitment -Algorithm SHA256).Hash.ToLowerInvariant() -cne $commitmentSha256 -or
            (Get-FileHash -LiteralPath (Join-Path $out 'evidence\sealed_manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedSealedSha256) {
            throw 'Retained blind commitment or sealed manifest differs from the preflight bytes.'
        }
    } else {
        $evidenceFixtureManifest = Join-Path $out 'evidence\fixture-manifest.json'
        Copy-NoOverwrite $FixtureManifest $evidenceFixtureManifest
        foreach ($f in $fixtures) {
            # Keep fixtures beside their unchanged approved manifest so the evidence
            # package is directly replayable and source drift cannot affect a later run.
            Copy-NoOverwrite (Join-Path (Split-Path $FixtureManifest) $f.filename) (Join-Path $out ('evidence\' + $f.filename))
        }
        if ((Get-FileHash -LiteralPath $evidenceFixtureManifest -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedManifestHash) {
            throw 'Retained manifest differs from the preflight bytes.'
        }
    }
    $retainedModelManifestHash = (Get-FileHash -LiteralPath $evidenceModelManifest -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($retainedModelManifestHash -cne $modelManifestSha256) { throw 'Retained manifest differs from the preflight bytes.' }
    for ($i=0; $i -lt 3; $i++) {
        $retainedFixture = Join-Path $out ('evidence\' + $fixtures[$i].filename)
        $rawBefore = (Get-FileHash -LiteralPath $retainedFixture -Algorithm SHA256).Hash.ToLowerInvariant()
        $canonical = Get-CanonicalJsonSha256 $retainedFixture
        $rawAfter = (Get-FileHash -LiteralPath $retainedFixture -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($rawBefore -cne $expectedRaw[$i] -or $rawAfter -cne $expectedRaw[$i] -or $canonical -cne $expectedCanon[$i]) {
            throw 'Retained fixture failed raw/canonical replay verification.'
        }
    }
    $plansByKey = @{}
    $planEvidence = @()
    for ($i=0; $i -lt 3; $i++) {
        $fixture = $fixtures[$i]
        foreach ($seed in $seedSets[$i]) {
            $planKey = "$($fixtureKeys[$i])-$seed"
            $planPath = Join-Path $out ('evidence\plans\' + $planKey + '.json')
            $null = & $python (Join-Path $root 'ollama-proxy\eval\broadcast_sim\run_broadcast_sim.py') --fixture (Join-Path $out ('evidence\' + $fixture.filename)) --seed $seed --stream-only --report $planPath
            if ($LASTEXITCODE -ne 0) { throw 'T3 deterministic stream plan generation failed.' }
            $plan = Get-Content -Raw -LiteralPath $planPath -Encoding utf8 | ConvertFrom-Json
            if ($plan.schema_version -cne 'airi.broadcast-sim-report.v1' -or $plan.mode -cne 'stream_only' -or
                -not (Test-ExactInteger $plan.seed $seed) -or $plan.fixture_sha256 -cne $fixture.canonical_sha256 -or
                -not @($plan.picks).Count) { throw 'T3 deterministic stream plan is incomplete.' }
            $plansByKey[$planKey] = $planPath
            $planEvidence += @{plan_key=$planKey;sha256=(Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
    }
    if ($plansByKey.Count -ne 12 -or $planEvidence.Count -ne 12) { throw 'T3 requires exactly twelve immutable stream plans.' }
    $baseline = @($arms | Where-Object name -ceq 'baseline')[0]
    $comparisonStatuses = @{}
    $successfulKeys = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $healthEvidence = @()
    $reportEvidence = @()
    $packetEvidence = @()
    $contractEvidence = @()
    $comparisonEvidence = @()
    foreach ($arm in $arms) {
        for ($i=0; $i -lt 3; $i++) { $fixture = $fixtures[$i]; foreach ($seed in $seedSets[$i]) {
            $key = "$($arm.name)-$($fixtureKeys[$i])-$seed"; $run = Join-Path $out ('runtime\' + $key)
            [IO.Directory]::CreateDirectory($run) | Out-Null
            $master=New-Capability; $observer=New-Capability; if ($master -ceq $observer) { throw 'Capability collision.' }
            $owners=@{}; $started=[DateTime]::UtcNow
            try {
                if (@(Get-Listeners $ports).Count -ne 0) { throw 'A service listener appeared between isolated T3 runs.' }
                $env:AIRI_IMMEDIATE_ACK='marker'; $env:AIRI_LIVE_BROADCAST_MASTER_TOKEN=$master; $env:AIRI_LIVE_BROADCAST_OBSERVER_TOKEN=$observer
                & (Join-Path $root 'start-airi-local-stack.ps1') -Stt off -OllamaNumGpu 999 -NumCtx $NumCtx -EnableMemory $true -EnableKnowledge $true -MemoryDbPath (Join-Path $run 'memory.sqlite3') -KnowledgeDbPath (Join-Path $run 'knowledge.sqlite3') -EnableMemoryExtraction $false -AllowExternalMemoryExtraction $false -ChatProvider local -AllowExternalChat $false -ChatModel $arm.tag -ChatModelDigest $arm.digest -OutputModeration on -OutputModerationTerms '' -InputScreening on -InputScreeningPolicy '' -EpistemicConfidence on -AffectContinuity on -AllowExternalSearch $false -LiveBroadcast -LiveBroadcastEvalClock -LiveBroadcastMasterTokenOverride $master -LiveBroadcastObserverTokenOverride $observer
                $owners = Get-RecentOwned $started
                Assert-OwnedListeners $owners
                if (@(Get-Listeners @(11436, 8890)).Count -ne 0) { throw 'T3 forbids memory extraction and STT listeners.' }
                $healthBefore=Invoke-RestMethod 'http://127.0.0.1:11435/health' -TimeoutSec 5; Assert-Health $healthBefore $arm
                $ttsHealthBefore=Invoke-RestMethod 'http://127.0.0.1:8880/health' -TimeoutSec 5; Assert-TtsHealth $ttsHealthBefore
                $report=Join-Path $out ('reports\' + $arm.name + '\' + $key + '.json'); $packet=Join-Path $out ('packets\' + $arm.name + '\' + $key + '.md')
                & $python (Join-Path $root 'ollama-proxy\eval\broadcast_sim\run_broadcast_sim.py') --base-url http://127.0.0.1:11435/v1 --model $arm.tag --memory-arm seeded --contract on --protocol operational --author-format runtime --fixture (Join-Path $out ('evidence\' + $fixture.filename)) --seed $seed --history-turns 8 --max-tokens 220 --timeout 180 --briefing on --briefing-evidence on --acts on --live-broadcast-context on --report $report --packet $packet
                if ($LASTEXITCODE -ne 0) { throw 'T3 runner failed.' }
                Assert-Report $report $arm $fixture $seed $plansByKey["$($fixtureKeys[$i])-$seed"]
                $healthAfter=Invoke-RestMethod 'http://127.0.0.1:11435/health' -TimeoutSec 5; Assert-Health $healthAfter $arm
                $ttsHealthAfter=Invoke-RestMethod 'http://127.0.0.1:8880/health' -TimeoutSec 5; Assert-TtsHealth $ttsHealthAfter
                $healthPath = Join-Path $out ('evidence\health-' + $key + '.json')
                Write-JsonNoOverwrite $healthPath @{ run_key=$key; model=$arm.tag; digest=$arm.digest; num_ctx=$NumCtx; knowledge=@{documents=0;chunks=0;accepted_chunks=0}; before=$healthBefore; after=$healthAfter; tts_before=$ttsHealthBefore; tts_after=$ttsHealthAfter }
                $healthEvidence += @{run_key=$key;sha256=(Get-FileHash -LiteralPath $healthPath -Algorithm SHA256).Hash.ToLowerInvariant()}
                # The runner's public report schema intentionally has no model digest,
                # timeout, num_ctx, or invocation argument fields.  Preserve a separate
                # content-free, no-overwrite outer attestation for precisely those gaps.
                $contractPath = Join-Path $out ('evidence\run-contract-' + $key + '.json')
                Write-JsonNoOverwrite $contractPath @{ run_key=$key; model=$arm.tag; digest=$arm.digest; memory_arm='seeded'; max_tokens=220; timeout_seconds=180; num_ctx=$NumCtx; receipt_bound=$true }
                $reportEvidence += @{run_key=$key;sha256=(Get-FileHash -LiteralPath $report -Algorithm SHA256).Hash.ToLowerInvariant()}
                $packetEvidence += @{run_key=$key;sha256=(Get-FileHash -LiteralPath $packet -Algorithm SHA256).Hash.ToLowerInvariant()}
                $contractEvidence += @{run_key=$key;sha256=(Get-FileHash -LiteralPath $contractPath -Algorithm SHA256).Hash.ToLowerInvariant()}
                if (-not $successfulKeys.Add($key)) { throw 'Duplicate T3 run key.' }
            } finally {
                $cleanupOwners = @{}
                foreach ($ownedPort in @($owners.Keys)) { $cleanupOwners[$ownedPort] = [int]$owners[$ownedPort] }
                $recentOwners = Get-RecentOwned $started
                foreach ($ownedPort in @($recentOwners.Keys)) {
                    if (-not $cleanupOwners.ContainsKey($ownedPort)) {
                        $cleanupOwners[$ownedPort] = [int]$recentOwners[$ownedPort]
                    }
                }
                $cleanupFailures = @(Stop-Owned $cleanupOwners)
                Remove-Item Env:AIRI_LIVE_BROADCAST_MASTER_TOKEN -ErrorAction SilentlyContinue
                Remove-Item Env:AIRI_LIVE_BROADCAST_OBSERVER_TOKEN -ErrorAction SilentlyContinue
                if ($cleanupFailures.Count -gt 0) { throw 'One or more T3-owned services could not be stopped.' }
            }
        } }
    }
    if ($successfulKeys.Count -ne 36 -or $healthEvidence.Count -ne 36 -or
        $reportEvidence.Count -ne 36 -or $packetEvidence.Count -ne 36 -or
        $contractEvidence.Count -ne 36 -or $planEvidence.Count -ne 12) {
        throw 'T3 matrix evidence is not exactly 36 complete runs.'
    }
    $comparisonFailures = @()
    if ($isBlindProfile) {
        # privacy, localhost_exposure and external_provider_without_opt_in have no
        # field in the runner's report schema.  Attest exactly what this launcher
        # verified so the comparator can gate them instead of assuming them.
        if ($MatrixProfile -ceq 'e2c1') {
            $candidateArm = 'e2-c1'
            $attestationSchema = 'airi.e2-c1-environment-attestation.v1'
            $comparatorScript = 'compare_e2c1_blind.py'
            $comparisonSchema = 'airi.e2-c1-blind-comparison.v1'
            $comparisonFile = 'e2c1-blind.json'
        } else {
            $candidateArm = 'e2-c2'
            $attestationSchema = 'airi.e2-c2-environment-attestation.v1'
            $comparatorScript = 'compare_e2c2_blind.py'
            $comparisonSchema = 'airi.e2-c2-blind-comparison.v1'
            $comparisonFile = 'e2c2-blind.json'
        }
        $attestationPath = Join-Path $out 'evidence\environment-attestation.json'
        $attestationDocument = @{
            schema_version=$attestationSchema
            root_id=[string]$commitment.root_id
            run_count=36
            zero_violations=@{privacy=0;localhost_exposure=0;external_provider_without_opt_in=0}
            verified_by='run-airi-broadcast-t3-matrix.ps1'
            evidence=@{chat_provider_local_only=$true;chat_provider_external_approved=$false;external_chat_allowed=$false;external_search_allowed=$false;external_memory_extraction_allowed=$false;loopback_only_endpoints=$true;memory_extraction_listener_absent=$true;stt_listener_absent=$true;per_run_isolated_databases=$true}
        }
        if ($MatrixProfile -ceq 'e2c2') {
            # Every run's before/after /health proved handle_grounding_guard=true
            # (Assert-Health throws otherwise), so this is observed, not assumed.
            $attestationDocument['handle_grounding_guard'] = 'on'
            $attestationDocument.evidence['handle_grounding_guard_health_attested'] = $true
        }
        Write-JsonNoOverwrite $attestationPath $attestationDocument
        $comparison = Join-Path $out ('comparisons\' + $comparisonFile)
        & $python (Join-Path $root ('ollama-proxy\eval\broadcast_sim\' + $comparatorScript)) --reports-dir (Join-Path $out 'reports') --policy $evidencePolicy --commitment $evidenceCommitment --output $comparison --environment-attestation $attestationPath --expected-model-manifest-sha256 $retainedModelManifestHash
        $comparisonExit = $LASTEXITCODE
        if (Test-Path -LiteralPath $comparison) {
            $comparisonEvidence += @{candidate=$candidateArm;sha256=(Get-FileHash -LiteralPath $comparison -Algorithm SHA256).Hash.ToLowerInvariant()}
            try {
                $verdict = Get-Content -Raw -LiteralPath $comparison -Encoding utf8 | ConvertFrom-Json
                # A published `no_winner` verdict is a terminal success of the
                # matrix, not a launcher failure: the human decides what follows.
                if ($comparisonExit -eq 0 -and $verdict.schema_version -ceq $comparisonSchema -and
                    $verdict.status -ceq 'pass' -and (Test-ExactInteger $verdict.report_count 36) -and
                    (Test-ExactBoolean $verdict.adoption_authorized $false) -and
                    ($null -eq $verdict.winner -or ($verdict.winner -is [string] -and $verdict.winner))) {
                    $comparisonStatuses[$candidateArm] = if ($null -eq $verdict.winner) { 'pass-no-winner' } else { 'pass-' + [string]$verdict.winner }
                } else { $comparisonFailures += $candidateArm }
            } catch { $comparisonFailures += $candidateArm }
        } else { $comparisonFailures += $candidateArm }
        if ($comparisonFailures.Count -ne 0) { throw 'The blind comparator did not publish a valid verdict.' }
        if ($comparisonEvidence.Count -ne 1 -or $comparisonStatuses.Count -ne 1) { throw 'Blind evidence is not exactly one published verdict.' }
    } else {
    # Run both comparisons after all 36 reports exist.  A failed E1 comparison
    # must not prevent the independent E2 comparison from producing evidence.
    foreach ($candidateName in @('e1','e2')) {
        $comparison=Join-Path $out ('comparisons\baseline-vs-' + $candidateName + '.json')
        & $python (Join-Path $root 'ollama-proxy\eval\broadcast_sim\compare_broadcast_t3.py') --base-reports (Join-Path $out 'reports\baseline') --candidate-reports (Join-Path $out ('reports\' + $candidateName)) --fixture-manifest $evidenceFixtureManifest --output $comparison
        $comparisonExit = $LASTEXITCODE
        if (Test-Path -LiteralPath $comparison) {
            $comparisonEvidence += @{candidate=$candidateName;sha256=(Get-FileHash -LiteralPath $comparison -Algorithm SHA256).Hash.ToLowerInvariant()}
            try {
                $comparisonResult = Get-Content -Raw -LiteralPath $comparison -Encoding utf8 | ConvertFrom-Json
                if ($comparisonExit -eq 0 -and $comparisonResult.status -ceq 'pass' -and
                    (Test-ExactInteger $comparisonResult.paired_reports 12)) {
                    $comparisonStatuses[$candidateName] = 'pass'
                } else { $comparisonFailures += $candidateName }
            } catch { $comparisonFailures += $candidateName }
        } else { $comparisonFailures += $candidateName }
    }
    if ($comparisonFailures.Count -ne 0) { throw 'Both T3 comparisons ran, but one or more did not attest twelve passing pairs.' }
    if ($successfulKeys.Count -ne 36 -or $healthEvidence.Count -ne 36 -or
        $reportEvidence.Count -ne 36 -or $packetEvidence.Count -ne 36 -or
        $contractEvidence.Count -ne 36 -or $comparisonEvidence.Count -ne 2 -or
        $comparisonStatuses.Count -ne 2 -or $planEvidence.Count -ne 12) {
        throw 'T3 matrix evidence is not exactly 36 runs plus two comparisons.'
    }
    }
    foreach ($key in $plannedKeys) {
        foreach ($dbName in @('memory.sqlite3','knowledge.sqlite3')) {
            $dbPath = Join-Path $out ('runtime\' + $key + '\' + $dbName)
            $dbItem = Get-Item -LiteralPath $dbPath -ErrorAction Stop
            if ($dbItem.PSIsContainer -or $dbItem.Length -le 0) { throw "Required per-run database is missing or empty: $key/$dbName" }
        }
    }
    $outputPrefix = $out.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $runtimeEvidence = @(
        Get-ChildItem -LiteralPath (Join-Path $out 'runtime') -File -Recurse -ErrorAction Stop |
            Sort-Object FullName | ForEach-Object {
                if (-not $_.FullName.StartsWith($outputPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime artifact escaped OutputDir.' }
                @{path=$_.FullName.Substring($outputPrefix.Length).Replace('\','/');size=[long]$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
            }
    )
    if ($isBlindProfile) {
        Write-JsonNoOverwrite (Join-Path $out 'summary.json') @{ schema_version='airi.t3-matrix-launcher.v2'; matrix_profile=$MatrixProfile; status='pass'; adoption_authorized=$false; run_count=36; model_manifest_sha256=$retainedModelManifestHash; blind_commitment_sha256=$commitmentSha256; sealed_manifest_sha256=$expectedSealedSha256; blind_root_id=[string]$commitment.root_id; common_settings=@{memory_arm='seeded';max_tokens=220;timeout_seconds=180;num_ctx=$NumCtx;num_gpu=999;live_context='on';tts_reference_embedding_cache=$true;tts_streaming_mode=2;tts_min_chunk_length=16}; models=@($arms | ForEach-Object { @{name=$_.name;tag=$_.tag;digest=$_.digest} }); fixtures=@(0..2 | ForEach-Object { @{logical_role=$fixtureKeys[$_];canonical_sha256=$expectedCanon[$_];raw_sha256=$expectedRaw[$_];seeds=$seedSets[$_]} }); plan_evidence=$planEvidence; health_evidence=$healthEvidence; report_evidence=$reportEvidence; packet_evidence=$packetEvidence; run_contract_evidence=$contractEvidence; comparison_evidence=$comparisonEvidence; runtime_evidence=$runtimeEvidence; comparisons=$comparisonStatuses }
        return
    }
    Write-JsonNoOverwrite (Join-Path $out 'summary.json') @{ schema_version='airi.t3-matrix-launcher.v2'; status='pass'; adoption_authorized=$false; run_count=36; model_manifest_sha256=$retainedModelManifestHash; fixture_manifest_sha256=$expectedManifestHash; common_settings=@{memory_arm='seeded';max_tokens=220;timeout_seconds=180;num_ctx=$NumCtx;num_gpu=999;live_context='on';tts_reference_embedding_cache=$true;tts_streaming_mode=2;tts_min_chunk_length=16}; models=@($arms | ForEach-Object { @{name=$_.name;tag=$_.tag;digest=$_.digest} }); fixtures=@($fixtures | ForEach-Object { @{creation_order=$_.creation_order;canonical_sha256=$_.canonical_sha256;seeds=$seedSets[[int]$_.creation_order-1]} }); plan_evidence=$planEvidence; health_evidence=$healthEvidence; report_evidence=$reportEvidence; packet_evidence=$packetEvidence; run_contract_evidence=$contractEvidence; comparison_evidence=$comparisonEvidence; runtime_evidence=$runtimeEvidence; comparisons=$comparisonStatuses }
} finally {
    Restore-Env AIRI_IMMEDIATE_ACK $previousAck
    Restore-Env AIRI_HANDLE_GROUNDING_GUARD $previousGuard
    Restore-Env AIRI_LIVE_BROADCAST_MASTER_TOKEN $previousMaster
    Restore-Env AIRI_LIVE_BROADCAST_OBSERVER_TOKEN $previousObserver
    Restore-Env AIRI_GPT_SOVITS_SV_CACHE $previousCache
    Restore-Env GPT_SOVITS_STREAMING_MODE $previousStreamingMode
    Restore-Env GPT_SOVITS_MIN_CHUNK_LENGTH $previousMinChunkLength
    Restore-Env GPT_SOVITS_REFERENCE_AUDIO $previousReferenceAudio
    Restore-Env NLTK_DATA $previousNltkData
    Restore-Env PYTHONPATH $previousPythonPath
    Restore-Env PYTHONIOENCODING $previousPythonIoEncoding
    Restore-Env AIRI_STACK_PYTHON $previousStackPython
}
