#Requires -Version 5.1
<#
.SYNOPSIS
    DEPRECATED - no longer patches anything.

.DESCRIPTION
    This script used to set the assistant transcript buffer's flushDelayMs from
    1200 ms to 400 ms. patch-airi-reaction-latency.ps1 now owns that same byte
    range, so running both was redundant and order-dependent: whichever script
    ran second found a value it did not list as a stock target and failed hard.

    The file is kept as a no-op stub so existing automation that still calls it
    stays harmless. It accepts the old parameters, prints a notice and exits 0.

    Use instead:
        .\patch-airi-reaction-latency.ps1     (VAD silence + transcript flush)
        .\apply-airi-patches.ps1              (full patch set, correct order)
#>
param(
    [string]$AsarPath = "$env:LOCALAPPDATA\Programs\airi\resources\app.asar",
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

Write-Output 'patch-airi-transcript-latency.ps1 is DEPRECATED and does nothing.'
Write-Output 'The transcript flush delay (1200 ms -> 400 ms) is now applied by patch-airi-reaction-latency.ps1.'
Write-Output 'Run .\apply-airi-patches.ps1 to apply the full patch set in the supported order.'

exit 0
