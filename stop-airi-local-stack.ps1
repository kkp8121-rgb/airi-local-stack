$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'stt\stop-local-stt.ps1')
& (Join-Path $PSScriptRoot 'chatterbox\stop-local-tts.ps1')
& (Join-Path $PSScriptRoot 'ollama-proxy\stop-local-ollama-proxy.ps1')

Write-Output 'Stopped AIRI local STT, TTS, and Ollama compatibility proxy services.'
Write-Output 'Ollama and the AIRI desktop app were left running.'
