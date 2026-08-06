$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'stt\stop-local-stt.ps1')
& (Join-Path $PSScriptRoot 'gpt-sovits\stop-local-stack.ps1')
& (Join-Path $PSScriptRoot 'ollama-proxy\stop-local-ollama-proxy.ps1')

Write-Output 'Stopped AIRI local STT, GPT-SoVITS TTS, and Ollama compatibility proxy services.'
Write-Output 'Ollama and the AIRI desktop app were left running.'
