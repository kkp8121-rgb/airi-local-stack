param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 11436,
    [Parameter(Mandatory)]
    [string]$Model,
    [Parameter(Mandatory)]
    [string]$ExpectedDigest
)

$ErrorActionPreference = 'Stop'
$hostAddress = '127.0.0.1'
$baseUri = "http://${hostAddress}:$Port"

function Get-VerifiedOllamaModelDigest {
    param(
        [Parameter(Mandatory)]$Health,
        [Parameter(Mandatory)][string]$RequestedModel,
        [Parameter(Mandatory)][string]$Expected
    )
    function Normalize-OllamaModelName([string]$Name) {
        $value = $Name.Trim().ToLowerInvariant()
        $leaf = $value.Substring($value.LastIndexOf('/') + 1)
        if ($leaf -notmatch ':') { $value = "$value`:latest" }
        return $value
    }
    if ($Expected -notmatch '^[0-9a-fA-F]{64}$') { throw 'Expected memory extractor digest is invalid.' }
    $wanted = Normalize-OllamaModelName $RequestedModel
    $matches = @($Health.models | Where-Object {
        if (-not $_) {
            $false
        }
        else {
            $candidate = [string]$_.name
            if ([string]::IsNullOrWhiteSpace($candidate)) { $candidate = [string]$_.model }
            -not [string]::IsNullOrWhiteSpace($candidate) -and (Normalize-OllamaModelName $candidate) -eq $wanted
        }
    })
    if ($matches.Count -ne 1) { throw 'Memory extractor model lookup did not resolve exactly one model.' }
    $digest = [string]$matches[0].digest
    if ($digest -notmatch '^[0-9a-fA-F]{64}$') { throw 'Memory extractor model digest is invalid.' }
    if ($digest -ine $Expected) { throw 'Memory extractor model digest does not match the gate digest.' }
    return $digest
}

function Get-VerifiedOllamaServeProcess {
    param(
        [Parameter(Mandatory)][int]$ProcessId
    )
    try {
        $target = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
    }
    catch {
        throw 'Memory extractor ownership could not be verified.'
    }
    $name = [string]$target.Name
    $executablePath = [string]$target.ExecutablePath
    $commandLine = [string]$target.CommandLine
    if (-not $target -or
        $name -ine 'ollama.exe' -or
        [string]::IsNullOrWhiteSpace($executablePath) -or
        [IO.Path]::GetFileName($executablePath) -ine 'ollama.exe' -or
        [string]::IsNullOrWhiteSpace($commandLine) -or
        $commandLine -notmatch '(?i)\bserve\b') {
        throw 'Memory extractor ownership could not be verified.'
    }
    return $target
}

$listener = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listener) {
    if ($listener.Count -ne 1 -or @($listener | Where-Object LocalAddress -ne $hostAddress).Count -gt 0) {
        throw 'Existing memory extractor ownership could not be verified.'
    }
    $existingProcess = Get-VerifiedOllamaServeProcess -ProcessId ([int]$listener[0].OwningProcess)
    try {
        $health = Invoke-RestMethod -Uri "$baseUri/api/tags" -TimeoutSec 3 -ErrorAction Stop
        $null = Get-VerifiedOllamaModelDigest -Health $health -RequestedModel $Model -Expected $ExpectedDigest
    }
    catch {
        throw 'Existing memory extractor does not match the requested model digest.'
    }
    return [pscustomobject]@{
        Status = 'ok'
        Uri = $baseUri
        Pid = [int]$existingProcess.ProcessId
        ModelVerified = $true
        StartedByCaller = $false
    }
}

$ollama = Get-Command ollama -ErrorAction Stop
$environment = @{
    OLLAMA_HOST = "${hostAddress}:$Port"
    OLLAMA_NUM_PARALLEL = '1'
    OLLAMA_MAX_LOADED_MODELS = '1'
    OLLAMA_KEEP_ALIVE = '5m'
}
$previous = @{}
foreach ($name in $environment.Keys) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $environment[$name], 'Process')
}
try {
    $process = Start-Process `
        -FilePath $ollama.Source `
        -ArgumentList 'serve' `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $PSScriptRoot 'memory-extractor.out.log') `
        -RedirectStandardError (Join-Path $PSScriptRoot 'memory-extractor.err.log') `
        -PassThru
}
finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}

$deadline = (Get-Date).AddSeconds(30)
$health = $null
do {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri "$baseUri/api/tags" -TimeoutSec 2
    }
    catch {
        $health = $null
    }
} while (-not $health -and (Get-Date) -lt $deadline)

if (-not $health) {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    throw "Memory extractor Ollama did not become ready on $baseUri."
}

try {
    $null = Get-VerifiedOllamaModelDigest -Health $health -RequestedModel $Model -Expected $ExpectedDigest
}
catch {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw 'Started memory extractor does not match the requested model digest.'
}

try {
    $readyListener = Get-NetTCPConnection -LocalAddress $hostAddress -LocalPort $Port -State Listen -ErrorAction Stop
}
catch {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw 'Started memory extractor ownership could not be verified.'
}
if (@($readyListener).Count -ne 1 -or [int]$readyListener[0].OwningProcess -ne [int]$process.Id) {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw 'Started memory extractor ownership could not be verified.'
}
try {
    $null = Get-VerifiedOllamaServeProcess -ProcessId ([int]$process.Id)
}
catch {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw 'Started memory extractor ownership could not be verified.'
}
return [pscustomobject]@{
    Status = 'ok'
    Uri = $baseUri
    Pid = [int]$process.Id
    ModelVerified = $true
    StartedByCaller = $true
}
