param([string]$Text)

$ErrorActionPreference = 'Stop'
$sampleDir = Join-Path $PSScriptRoot 'voice-samples'
New-Item -ItemType Directory -Path $sampleDir -Force | Out-Null

# Keep this script ASCII-only for Windows PowerShell 5.1. Decode the Korean
# default explicitly as UTF-8 so it cannot be interpreted through an ANSI page.
if (-not $PSBoundParameters.ContainsKey('Text')) {
    $encodedText = '7JWI64WVISDrp4zrgpjshJwg67CY6rCA7JuMLiDsmKTripjsnYAg7Ja065akIOyerOuvuOyeiOuKlCDsnbTslbzquLDrpbwg7ZW0IOuzvOq5jD8='
    $Text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedText))
}

foreach ($value in 0.65, 0.70, 0.75, 0.80) {
    $suffix = '{0:000}' -f [int]($value * 100)
    $body = @{
        model = 'tts-1-ko'
        input = $Text
        voice = "airi-$suffix"
        response_format = 'wav'
        exaggeration = $value
        cfg_weight = 0.30
    } | ConvertTo-Json -Compress
    $bodyBytes = [Text.Encoding]::UTF8.GetBytes($body)
    $output = Join-Path $sampleDir "airi-exaggeration-$suffix.wav"
    $timer = [Diagnostics.Stopwatch]::StartNew()
    Invoke-WebRequest `
        -Uri 'http://127.0.0.1:8880/v1/audio/speech' `
        -Method Post `
        -ContentType 'application/json; charset=utf-8' `
        -Body $bodyBytes `
        -OutFile $output `
        -UseBasicParsing
    $timer.Stop()
    [pscustomobject]@{
        Exaggeration = $value
        Seconds = [math]::Round($timer.Elapsed.TotalSeconds, 2)
        File = $output
    }
}

Start-Process (Join-Path $sampleDir 'index.html')
