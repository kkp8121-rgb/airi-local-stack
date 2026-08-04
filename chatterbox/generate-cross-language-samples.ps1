param(
    [ValidatePattern('^[a-z0-9-]+$')]
    [string]$Prefix = 'airi'
)

$ErrorActionPreference = 'Stop'
$sampleDir = Join-Path $PSScriptRoot 'voice-samples'
New-Item -ItemType Directory -Path $sampleDir -Force | Out-Null

# ASCII-only source for Windows PowerShell 5.1; decoded value is Korean UTF-8.
$encodedText = '7JWI64WV7ZWY7IS47JqULiDsmKTripjsnYAg7IOI66Gc7Jq0IOydtOyVvOq4sOulvCDsspzsspztnogg65Ok66Ck65Oc66a06rKM7JqULiDrsJzsnYzsnbQg7J6Q7Jew7Iqk65+96rKMIOuTpOumrOuKlOyngCDtmZXsnbjtlbQg7KO87IS47JqULg=='
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedText))

foreach ($cfgWeight in 0.00, 0.15, 0.30) {
    $suffix = '{0:000}' -f [int]($cfgWeight * 100)
    $body = @{
        model = 'tts-1-ko'
        input = $text
        voice = 'airi-vtuber'
        response_format = 'wav'
        exaggeration = 0.65
        cfg_weight = $cfgWeight
    } | ConvertTo-Json -Compress
    $output = Join-Path $sampleDir "$Prefix-cfg-$suffix.wav"
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
        CfgWeight = $cfgWeight
        Seconds = [math]::Round($timer.Elapsed.TotalSeconds, 2)
        File = $output
    }
}

Start-Process (Join-Path $sampleDir 'cfg-index.html')
