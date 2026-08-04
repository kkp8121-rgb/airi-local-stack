param(
    [string]$OutputPrefix = 'pacing',
    [string]$Page = 'pacing-index.html'
)

$ErrorActionPreference = 'Stop'
$sampleDir = Join-Path $PSScriptRoot 'voice-samples'
New-Item -ItemType Directory -Path $sampleDir -Force | Out-Null
$encodedText = '7JWI64WVISDsnbTsoJwg67Cd6rOgIOyekOyXsOyKpOufrOyatCDtlZzqta3slrQg67KE7LaU7Ja8IOy6kOumre2EsCDrqqnshozrpqzroZwg66eQ7ZWg6rKMLg=='
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedText))
$variants = @(
    @{ Name='current'; Cfg=0.00; Exaggeration=0.65; Temperature=0.80 },
    @{ Name='balanced'; Cfg=0.15; Exaggeration=0.65; Temperature=0.65 },
    @{ Name='tight'; Cfg=0.30; Exaggeration=0.60; Temperature=0.60 }
)

foreach ($variant in $variants) {
    $body = @{
        model = 'tts-1-ko'
        input = $text
        voice = 'airi-vtuber'
        response_format = 'wav'
        exaggeration = $variant.Exaggeration
        cfg_weight = $variant.Cfg
        temperature = $variant.Temperature
        seed = 20260804
    } | ConvertTo-Json -Compress
    $output = Join-Path $sampleDir "$OutputPrefix-$($variant.Name).wav"
    $timer = [Diagnostics.Stopwatch]::StartNew()
    Invoke-WebRequest `
        -Uri 'http://127.0.0.1:8880/v1/audio/speech' `
        -Method Post `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
        -OutFile $output `
        -UseBasicParsing
    $timer.Stop()
    [pscustomobject]@{
        Variant = $variant.Name
        Seconds = [math]::Round($timer.Elapsed.TotalSeconds, 2)
        File = $output
    }
}

if ($Page) {
    Start-Process (Join-Path $sampleDir $Page)
}
