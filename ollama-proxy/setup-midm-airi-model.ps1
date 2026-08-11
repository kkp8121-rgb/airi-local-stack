param(
    [string]$Model = 'midm-airi:2.0-mini',
    [switch]$PreflightOnly,
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'
if ($Recreate -and $PreflightOnly) {
    throw '-Recreate cannot be combined with -PreflightOnly.'
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

function Get-LocalOllamaModelNames {
    try {
        $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 -ErrorAction Stop
    }
    catch {
        throw 'Local Ollama is not ready at http://127.0.0.1:11434. Start "ollama serve" and retry.'
    }
    return @($tags.models | ForEach-Object {
        $name = [string]$_.name
        if ([string]::IsNullOrWhiteSpace($name)) { $name = [string]$_.model }
        if (-not [string]::IsNullOrWhiteSpace($name)) { Normalize-OllamaModelName $name }
    })
}

$installed = Get-LocalOllamaModelNames
$wanted = Normalize-OllamaModelName $Model
if ($installed -contains $wanted -and (-not $Recreate -or $PreflightOnly)) {
    Write-Output "Local chat model is ready: $Model"
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

$installed = Get-LocalOllamaModelNames
if ($installed -notcontains (Normalize-OllamaModelName $DefaultModel)) {
    throw "Ollama create completed but '$DefaultModel' is not listed locally; refusing to claim setup succeeded."
}
Write-Output "Created local AIRI Mi:dm runtime model: $DefaultModel"
