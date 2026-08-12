param(
    [string]$Model = 'midm-airi:2.0-mini',
    # Optional artifact pin. The same tag can be rebuilt locally from other
    # bytes, so a supplied digest turns preflight into a fail-closed gate.
    # Without one, preflight only records the digest it observed.
    [string]$ExpectedDigest = '',
    [switch]$PreflightOnly,
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'
if ($Recreate -and $PreflightOnly) {
    throw '-Recreate cannot be combined with -PreflightOnly.'
}

$normalizedExpectedDigest = ''
if (-not [string]::IsNullOrWhiteSpace($ExpectedDigest)) {
    $normalizedExpectedDigest = $ExpectedDigest.Trim().ToLowerInvariant()
    if ($normalizedExpectedDigest -notmatch '^[0-9a-f]{64}$') {
        throw 'ExpectedDigest must be a 64 character hex model digest.'
    }
}

$SourceModel = 'hf.co/DevQuasar/K-intelligence.Midm-2.0-Mini-Instruct-GGUF:Q4_K_M'
$DefaultModel = 'midm-airi:2.0-mini'
$Modelfile = Join-Path $PSScriptRoot 'Modelfile.midm-airi'

function Normalize-OllamaModelName {
    param([Parameter(Mandatory)][string]$Name)

    $value = $Name.Trim().ToLowerInvariant()
    if ($value -notmatch ':') { $value = "$value`:latest" }
    return $value
}

function Get-LocalOllamaModelDigests {
    try {
        $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 -ErrorAction Stop
    }
    catch {
        throw 'Local Ollama is not ready at http://127.0.0.1:11434. Start "ollama serve" and retry.'
    }
    $digests = @{}
    foreach ($entry in @($tags.models)) {
        if (-not $entry) { continue }
        $name = [string]$entry.name
        if ([string]::IsNullOrWhiteSpace($name)) { $name = [string]$entry.model }
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        $normalized = Normalize-OllamaModelName $name
        if (-not $digests.ContainsKey($normalized)) {
            $digests[$normalized] = ([string]$entry.digest).Trim().ToLowerInvariant()
        }
    }
    return $digests
}

$digests = Get-LocalOllamaModelDigests
$installed = @($digests.Keys)
$wanted = Normalize-OllamaModelName $Model
if ($installed -contains $wanted -and (-not $Recreate -or $PreflightOnly)) {
    $observedDigest = [string]$digests[$wanted]
    if ($observedDigest -notmatch '^[0-9a-f]{64}$') { $observedDigest = '' }
    if ($normalizedExpectedDigest) {
        if ($observedDigest -ne $normalizedExpectedDigest) {
            throw "Local chat model '$Model' does not match the expected artifact digest."
        }
        Write-Output "Local chat model is ready: $Model (digest $observedDigest, pinned)"
        return
    }
    # No pin was supplied, so record the artifact that startup actually used.
    # A tag rebuilt from other bytes then stays visible in the transcript.
    $reportedDigest = if ($observedDigest) { $observedDigest } else { 'unresolved' }
    Write-Output "Local chat model is ready: $Model (digest $reportedDigest)"
    return
}

if ($Model -ne $DefaultModel) {
    throw "Local chat model '$Model' is not installed. Create or install that explicit -ChatModel first."
}


if ($PreflightOnly) {
    throw "Local chat model '$DefaultModel' is not installed. Run .\ollama-proxy\setup-midm-airi-model.ps1 after confirming the Mi:dm source model is present; normal startup never pulls models."
}

if (-not (Test-Path -LiteralPath $Modelfile -PathType Leaf)) {
    throw "Mi:dm Modelfile is missing: $Modelfile"
}
if ($installed -notcontains (Normalize-OllamaModelName $SourceModel)) {
    throw "Required local Mi:dm source model '$SourceModel' is not installed. Install it separately, then rerun this setup script. No network download was attempted."
}

$ollama = Get-Command ollama -CommandType Application -ErrorAction Stop
& $ollama.Source create $DefaultModel -f $Modelfile
if ($LASTEXITCODE -ne 0) {
    throw "Ollama could not create '$DefaultModel'. The existing source model was left unchanged."
}

$digests = Get-LocalOllamaModelDigests
$installed = @($digests.Keys)
$createdName = Normalize-OllamaModelName $DefaultModel
if ($installed -notcontains $createdName) {
    throw "Ollama create completed but '$DefaultModel' is not listed locally; refusing to claim setup succeeded."
}
$createdDigest = [string]$digests[$createdName]
if ($createdDigest -notmatch '^[0-9a-f]{64}$') { $createdDigest = 'unresolved' }
# Print the digest so an operator can pin this exact artifact afterwards.
Write-Output "Created local AIRI Mi:dm runtime model: $DefaultModel (digest $createdDigest)"
