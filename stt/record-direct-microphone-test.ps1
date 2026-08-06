$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName PresentationFramework

$device = 'audio=@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\wave_{DB4B1FBC-D9A0-4F14-87B0-1631EAE72B20}'
$outputPath = Join-Path $PSScriptRoot 'debug-recordings\direct-microphone-test.wav'

[System.Windows.MessageBox]::Show(
    'Click OK, then say the same Korean phrase. Recording lasts 5 seconds.',
    'AIRI direct microphone test',
    [System.Windows.MessageBoxButton]::OK,
    [System.Windows.MessageBoxImage]::Information
) | Out-Null

& ffmpeg `
    -hide_banner `
    -loglevel error `
    -y `
    -f dshow `
    -i $device `
    -t 5 `
    -ac 1 `
    -ar 48000 `
    -c:a pcm_s16le `
    $outputPath

if ($LASTEXITCODE -ne 0) {
    throw "FFmpeg microphone recording failed with exit code $LASTEXITCODE."
}

Start-Process -FilePath $outputPath
