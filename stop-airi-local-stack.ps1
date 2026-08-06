$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'stt\stop-local-stt.ps1')
& (Join-Path $PSScriptRoot 'gpt-sovits\stop-local-stack.ps1')
& (Join-Path $PSScriptRoot 'ollama-proxy\stop-local-ollama-proxy.ps1')
& (Join-Path $PSScriptRoot 'latency-monitor\stop-latency-monitor.ps1')

Write-Output 'Stopped AIRI local STT, GPT-SoVITS TTS, Ollama proxy, and latency monitor services.'
Write-Output 'Ollama and the AIRI desktop app were left running.'
