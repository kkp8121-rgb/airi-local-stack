param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('sample','sample2')]
    [string]$Prefix,
    [Parameter(Mandatory=$true)]
    [ValidateRange(0.0, 1.0)]
    [double]$CfgWeight
)

$ErrorActionPreference = 'Stop'
$sampleDir = Join-Path $PSScriptRoot 'voice-samples'
New-Item -ItemType Directory -Path $sampleDir -Force | Out-Null
$encodedText = '7JWI64WV7ZWY7IS47JqULiDsmKTripjsnYAg7IOI66Gc7Jq0IOydtOyVvOq4sOulvCDsspzsspztnogg65Ok66Ck65Oc66a06rKM7JqULiDrsJzsnYzsnbQg7J6Q7Jew7Iqk65+96rKMIOuTpOumrOuKlOyngCDtmZXsnbjtlbQg7KO87IS47JqULg=='
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedText))
$variants = @(
    @{ Name='neutral'; Exaggeration=0.50; Temperature=0.65 },
    @{ Name='stable'; Exaggeration=0.40; Temperature=0.55 }
)

foreach ($variant in $variants) {
    $body = @{
        model = 'tts-1-ko'
        input = $text
        voice = 'airi-vtuber'
        response_format = 'wav'
        exaggeration = $variant.Exaggeration
        cfg_weight = $CfgWeight
        temperature = $variant.Temperature
        seed = 20260804
    } | ConvertTo-Json -Compress
    $output = Join-Path $sampleDir "$Prefix-$($variant.Name).wav"
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
        Voice = $Prefix
        Variant = $variant.Name
        Seconds = [math]::Round($timer.Elapsed.TotalSeconds, 2)
        File = $output
    }
}
