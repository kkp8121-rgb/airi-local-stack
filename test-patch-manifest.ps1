#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
# Every tracked patch is pinned, not just the runtime artifacts the current
# procedure supports. The tracked-file comparison below makes additions and
# removals fail closed; an unpinned artifact cannot silently appear. `Usable`
# records historical `git apply` applicability against the pinned v0.11.3 base,
# while `Support` records the deliberately narrower runtime procedure.
$artifacts = @(
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-round-cancel.patch'
        Length = 84743
        Sha256 = '8BD061184BB98B48FCA1946DCAF1C8AE6707FB404541640F744A6A0B5AA9B26C'
        Usable = $true
        Defect = ''
        Support = 'Historical'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch'
        Length = 414208
        Sha256 = '2077D440481D64BD08B9A890C318D3CDFABADFE0E1398C28CAF3A3AB8B76CD86'
        Usable = $true
        Defect = ''
        Support = 'Runtime'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-context-correlation-sanitizer.patch'
        Length = 2541
        Sha256 = 'BA38C5F13670DECEEDAB3F0BFE9473AE7FB3BE1DE1A652A26E80E046F572B59E'
        Usable = $true
        Defect = ''
        Support = 'Runtime'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-upgrade-scout-runtime-20260811.patch'
        Length = 130974
        Sha256 = 'CC172A16281E56DC03E6A6F261B5531367711C0393D57E171C932EA8544C5E3E'
        Usable = $true
        Defect = ''
        Support = 'Runtime'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-session-header.patch'
        Length = 801
        Sha256 = 'FD6711F3716DFE926DBAF053F66C04E44CA3E6B4FEB28151193D49965DD4D273'
        Usable = $true
        Defect = ''
        Support = 'Historical'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-broadcast-meta-filter-20260809.patch'
        Length = 1888
        Sha256 = 'F1BA41639A814C9B92162CF2ADD4C8633660D6131BB7257B3B9DBFA230E6331A'
        Usable = $false
        Defect = 'BareHunkHeader'
        Support = 'Historical'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source-retry.patch'
        Length = 198939
        Sha256 = 'B6F24532FA7821B623B74F8EAA9DBABAF2774E8A91FFB0E1C1D55AF67B7B0038'
        Usable = $false
        Defect = 'LostKorean'
        Support = 'Historical'
    }
    [pscustomobject]@{
        Path = 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source-retry-normalized.patch'
        Length = 200223
        Sha256 = '63D231990D44124E6D3641E1A3B68660FD25BF05461395C26E5A2A7DF2D96FB6'
        Usable = $false
        Defect = 'LostKorean'
        Support = 'Historical'
    }
)

$trackedArtifacts = @(git -C $root ls-files -- 'airi_docs/patches/*.patch')
if ($LASTEXITCODE -ne 0) {
    throw 'Could not list tracked patch artifacts.'
}
$trackedArtifacts = @($trackedArtifacts | ForEach-Object { $_.Replace('\', '/') } | Sort-Object -Unique)
$manifestArtifacts = @($artifacts.Path | Sort-Object -Unique)
if ($manifestArtifacts.Count -ne $artifacts.Count) {
    throw 'Patch manifest contains duplicate artifact paths.'
}
$missingFromManifest = @($trackedArtifacts | Where-Object { $_ -notin $manifestArtifacts })
$notTracked = @($manifestArtifacts | Where-Object { $_ -notin $trackedArtifacts })
if ($missingFromManifest.Count -or $notTracked.Count) {
    throw "Tracked patch set and manifest differ. Missing: $($missingFromManifest -join ', '); untracked manifest entries: $($notTracked -join ', ')"
}

# Runtime support is intentionally not synonymous with historical applicability:
# the documented procedure is the combined runtime patch, the generic context
# sanitizer, and then the Upgrade Scout runtime layer. All three must remain
# usable and defect-free.
$supportedArtifacts = @($artifacts | Where-Object { $_.Support -eq 'Runtime' })
$expectedSupportedPaths = @(
    'airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch'
    'airi_docs/patches/AIRI-v0.11.3-context-correlation-sanitizer.patch'
    'airi_docs/patches/AIRI-v0.11.3-upgrade-scout-runtime-20260811.patch'
)
$actualSupportedSet = (@($supportedArtifacts.Path | Sort-Object) -join "`n")
$expectedSupportedSet = (@($expectedSupportedPaths | Sort-Object) -join "`n")
if ($actualSupportedSet -ne $expectedSupportedSet) {
    throw 'Runtime support set must be exactly the combined patch, context sanitizer, and Upgrade Scout layer.'
}

foreach ($artifact in $artifacts) {
    $path = Join-Path $root $artifact.Path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing patch artifact: $($artifact.Path)"
    }

    $file = Get-Item -LiteralPath $path
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Patch artifact is a reparse point: $($artifact.Path)"
    }
    if ([int64]$file.Length -ne [int64]$artifact.Length) {
        throw "Patch size mismatch: $($artifact.Path)"
    }

    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($hash -ne $artifact.Sha256) {
        throw "Patch hash mismatch: $($artifact.Path)"
    }

    # Both defects are visible in the bytes, so the usable/unusable split is
    # checked here rather than only by the opt-in base-checkout verifier that
    # CI never runs. A hunk header without line numbers makes git reject the
    # whole file, and a run of question marks is what is left where Korean
    # source lines used to be.
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    $bareHunk = [regex]::IsMatch($text, '(?m)^@@\s*$')
    $lostKorean = [regex]::IsMatch($text, '\?{3,}')

    if ($artifact.Usable -and $artifact.Defect) {
        throw "Usable artifact has a recorded defect: $($artifact.Path)"
    }
    if (-not $artifact.Usable -and -not $artifact.Defect) {
        throw "Unusable artifact has no recorded defect: $($artifact.Path)"
    }
    if ($artifact.Support -notin @('Runtime', 'Historical')) {
        throw "Unknown support classification: $($artifact.Path)"
    }
    if ($artifact.Support -eq 'Runtime' -and (-not $artifact.Usable -or $artifact.Defect)) {
        throw "Supported runtime artifact is not usable and defect-free: $($artifact.Path)"
    }

    switch ($artifact.Defect) {
        'BareHunkHeader' {
            if (-not $bareHunk) {
                throw "Recorded bare hunk header is gone; re-verify and update the manifest: $($artifact.Path)"
            }
        }
        'LostKorean' {
            if (-not $lostKorean) {
                throw "Recorded lost Korean is gone; re-verify and update the manifest: $($artifact.Path)"
            }
        }
        default {
            if ($bareHunk) {
                throw "Hunk header without line numbers: $($artifact.Path)"
            }
            if ($lostKorean) {
                throw "Korean replaced by question marks: $($artifact.Path)"
            }
        }
    }
}

$workflowPath = Join-Path $root '.github/workflows/remediation-checkpoint.yml'
if (-not (Test-Path -LiteralPath $workflowPath -PathType Leaf)) {
    throw 'Missing checkpoint workflow.'
}
$workflow = Get-Content -LiteralPath $workflowPath -Raw
if ($workflow -notmatch 'actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09' -or
    $workflow -notmatch 'actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444' -or
    $workflow -match 'actions/(checkout|setup-node)@v[0-9]' -or
    $workflow -notmatch 'git diff --check' -or
    $workflow -notmatch 'git diff-tree --check --no-commit-id -r \$env:CHECK_HEAD' -or
    $workflow -notmatch 'CHECK_BEFORE' -or
    $workflow -notmatch 'CHECK_BASE' -or
    $workflow -notmatch 'fetch-depth: 0' -or
    $workflow -notmatch [regex]::Escape(':(exclude)airi_docs/patches/*.patch')) {
    throw 'Checkpoint workflow contract failed.'
}

# An apply/reverse check alone cannot detect a regenerated layer being replaced
# by a smaller, unrelated delta. Keep representative markers from every
# Upgrade Scout capability in the pinned artifact, including B3 moderation.
$upgradeScoutPatch = Join-Path $root 'airi_docs/patches/AIRI-v0.11.3-upgrade-scout-runtime-20260811.patch'
$upgradeScoutText = [IO.File]::ReadAllText($upgradeScoutPatch, [Text.Encoding]::UTF8)
$requiredUpgradeScoutMarkers = @(
    'packages/stage-ui/src/libs/speech/pcm-worklet.ts',
    'packages/stage-ui/src/libs/speech/incremental-wav.ts',
    'packages/stage-ui/src/libs/speech/pcm-resampler.ts',
    'packages/stage-ui/src/composables/audio/voice-input-vad-experiment.ts',
    'packages/stage-ui/src/stores/providers/local-stt/stream-transcription.ts',
    'packages/stage-ui/src/libs/speech/text-self-echo.ts',
    'type: ''airi-moderation''',
    'airiModerationNotice'
)
foreach ($marker in $requiredUpgradeScoutMarkers) {
    if (-not $upgradeScoutText.Contains($marker)) {
        throw "Upgrade Scout semantic marker missing: $marker"
    }
}

# B4 방송 생성은 raw Ollama나 임의 원격 provider를 통과하면 proxy의
# fail-closed 스타일 게이트를 잃는다. Byte/hash pin에 더해 사람이 읽을 수
# 있는 의미 계약으로 exact 11435/v1 허용과 대표 거부 케이스를 고정한다.
$runtimeSourcePatch = Join-Path $root 'airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch'
$runtimeSourceText = [IO.File]::ReadAllText($runtimeSourcePatch, [Text.Encoding]::UTF8)
$requiredBroadcastProxyMarkers = @(
    'export function isExactLocalLoopbackProvider',
    "target.port === '11435'",
    '^\/v1(?:\/|$)',
    "provider('http://127.0.0.1:11434/v1')",
    "provider('http://127.0.0.1:11435/api')",
    "provider('https://example.test:11435/v1')",
    "headers: { 'x-airi-turn-origin': 'local-proactive' }"
)
foreach ($marker in $requiredBroadcastProxyMarkers) {
    if (-not $runtimeSourceText.Contains($marker)) {
        throw "Broadcast proxy routing marker missing: $marker"
    }
}

$pythonJob = [regex]::Match($workflow, '(?ms)^  python-core-tests:\r?\n(?<body>.*?)(?=^  [^\s]|\z)')
if (-not $pythonJob.Success) {
    throw 'Missing python-core-tests workflow job.'
}
$pythonJobBody = $pythonJob.Groups['body'].Value
$requiredTestRoots = @(
    'ollama-proxy/'
    'test_latency_trace.py'
    'test_start_airi_background.py'
    'test_midm_model_configuration.py'
    'latency-monitor'
    'stt'
)
if ($pythonJobBody -notmatch '(?m)^    timeout-minutes: 10\s*$' -or
    $pythonJobBody -notmatch '(?m)^    strategy:' -or
    $pythonJobBody -notmatch '(?m)^      fail-fast: false\s*$' -or
    $pythonJobBody -notmatch '(?m)^      matrix:' -or
    $pythonJobBody -match '(?m)^    timeout-minutes: (?!10\s*$)' -or
    @($requiredTestRoots | Where-Object { $pythonJobBody -notlike "*$_*" }).Count -ne 0) {
    throw 'Python CI sharding and ten-minute timeout contract failed.'
}

# Directory roots keep latency-monitor and STT future-proof. Ollama-proxy is
# split by file for predictable shard duration, so fail closed when a tracked
# test file is added or removed without updating the matrix.
$trackedProxyTests = @(
    git -C $root ls-files -- `
        'ollama-proxy/test_*.py' `
        ':(glob)ollama-proxy/eval/**/test_*.py' `
        'ollama-proxy/training/tests/test_*.py'
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not list tracked ollama-proxy Python tests.'
}
$trackedProxyTests = @(
    $trackedProxyTests |
        ForEach-Object { $_.Replace('\', '/') } |
        Sort-Object -Unique
)
$matrixProxyTests = @(
    [regex]::Matches(
        $pythonJobBody,
        'ollama-proxy/[A-Za-z0-9_./-]*test_[A-Za-z0-9_.-]+\.py'
    ) |
        ForEach-Object { $_.Value } |
        Sort-Object -Unique
)
$missingProxyTests = @($trackedProxyTests | Where-Object { $_ -notin $matrixProxyTests })
$staleProxyTests = @($matrixProxyTests | Where-Object { $_ -notin $trackedProxyTests })
if ($missingProxyTests.Count -or $staleProxyTests.Count) {
    throw "Python CI matrix differs from tracked ollama-proxy tests. Missing: $($missingProxyTests -join ', '); stale: $($staleProxyTests -join ', ')"
}

$checkpointPath = Join-Path $root 'test-current-checkpoint.ps1'
$checkpoint = Get-Content -LiteralPath $checkpointPath -Raw
if ($checkpoint -notmatch [regex]::Escape('gpt-sovits\test_start_local_stack_contract.ps1')) {
    throw 'Offline checkpoint must enforce the GPT-SoVITS cache-ready launcher contract.'
}

Write-Output 'Patch manifest contract: PASS (offline, no archive access).'
