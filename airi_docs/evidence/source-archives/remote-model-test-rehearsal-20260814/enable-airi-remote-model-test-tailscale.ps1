#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$TokenFile
)

$ErrorActionPreference = 'Stop'

$gatewayTarget = 'http://127.0.0.1:11439'
$servePort = '11439'

function Invoke-Tailscale {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = @(& $script:tailscalePath @Arguments 2>&1 | ForEach-Object { $_.ToString() })
    if ($LASTEXITCODE -ne 0) {
        throw 'Tailscale command failed. No Serve configuration was reported as enabled.'
    }
    return $output
}

function Get-TailscaleJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $text = (Invoke-Tailscale -Arguments $Arguments) -join "`n"
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw 'Tailscale returned no JSON status.'
    }
    try {
        return $text | ConvertFrom-Json
    } catch {
        throw 'Tailscale returned invalid JSON status.'
    }
}

function Get-TailscaleExecutable {
    $installedPath = Join-Path ${env:ProgramFiles} 'Tailscale\tailscale.exe'
    if (Test-Path -LiteralPath $installedPath -PathType Leaf) {
        return $installedPath
    }
    return (Get-Command tailscale -CommandType Application -ErrorAction Stop).Source
}

function Get-ServeWithoutRemotePort {
    param([Parameter(Mandatory = $true)]$Status)

    # Clone before removing our one listener, so the original status remains an
    # evidence snapshot for the preservation comparison.
    $copy = (($Status | ConvertTo-Json -Depth 100 -Compress) | ConvertFrom-Json)
    $tcp = $copy.PSObject.Properties['TCP'].Value
    if ($null -ne $tcp) { $tcp.PSObject.Properties.Remove($script:servePort) }
    $web = $copy.PSObject.Properties['Web'].Value
    if ($null -ne $web) {
        foreach ($property in @($web.PSObject.Properties)) {
            if ($property.Name -like "*:$script:servePort") {
                $web.PSObject.Properties.Remove($property.Name)
            }
        }
    }
    return $copy
}

function Test-RemotePortAbsent {
    param([Parameter(Mandatory = $true)]$Status)

    $tcp = $Status.PSObject.Properties['TCP'].Value
    if ($null -ne $tcp -and $null -ne $tcp.PSObject.Properties[$script:servePort].Value) { return $false }
    $web = $Status.PSObject.Properties['Web'].Value
    if ($null -eq $web) { return $true }
    return $null -eq ($web.PSObject.Properties | Where-Object { $_.Name -like "*:$script:servePort" } | Select-Object -First 1)
}

function Test-NoFunnelOrPublicServe {
    param([Parameter(Mandatory = $true)]$Status)

    function Test-Value {
        param($Value)

        if ($null -eq $Value -or $Value -is [string] -or $Value -is [ValueType]) { return $true }
        foreach ($property in $Value.PSObject.Properties) {
            if ($property.Name -match '^(?i:Funnel|AllowFunnel|Public)$' -and $property.Value -ne $false -and $null -ne $property.Value) {
                return $false
            }
            if (-not (Test-Value -Value $property.Value)) { return $false }
        }
        return $true
    }

    # Current status JSON may explicitly carry "Funnel": false. That is still
    # private Serve; any enabled/non-boolean public marker fails closed.
    return Test-Value -Value $Status
}

function ConvertTo-CanonicalJson {
    param($Value)

    if ($null -eq $Value -or $Value -is [string] -or $Value -is [ValueType]) {
        return ($Value | ConvertTo-Json -Compress)
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        return '[' + ((@($Value | ForEach-Object { ConvertTo-CanonicalJson -Value $_ }) -join ',')) + ']'
    }
    $entries = foreach ($property in @($Value.PSObject.Properties | Sort-Object Name)) {
        $encodedName = $property.Name | ConvertTo-Json -Compress
        $encodedValue = ConvertTo-CanonicalJson -Value $property.Value
        "$encodedName`:$encodedValue"
    }
    return '{' + ($entries -join ',') + '}'
}

function Test-StructuralEqual {
    param($Left, $Right)

    return (ConvertTo-CanonicalJson -Value $Left) -ceq (ConvertTo-CanonicalJson -Value $Right)
}

function Test-ExpectedRemoteServeStatus {
    param(
        [Parameter(Mandatory = $true)]$Status,
        [Parameter(Mandatory = $true)][string]$DnsName
    )

    # Other local listeners are allowed. Only this dedicated 11439 listener is
    # constrained, and any Funnel/public marker fails closed.
    if (-not (Test-NoFunnelOrPublicServe -Status $Status)) { return $false }
    $tcp = $Status.PSObject.Properties['TCP'].Value
    $web = $Status.PSObject.Properties['Web'].Value
    if ($null -eq $tcp -or $null -eq $web) { return $false }
    $listener = $tcp.PSObject.Properties[$script:servePort].Value
    if ($null -eq $listener -or $listener.HTTPS -ne $true) { return $false }
    $serveHostName = "$DnsName`:$script:servePort"
    $site = $web.PSObject.Properties[$serveHostName].Value
    if ($null -eq $site -or $site.PSObject.Properties['Handlers'].Value -eq $null) { return $false }
    $handlers = $site.Handlers
    $handler = $handlers.PSObject.Properties['/'].Value
    return $null -ne $handler -and $handler.Proxy -ceq $gatewayTarget
}

try {
    $resolvedTokenFile = (Resolve-Path -LiteralPath $TokenFile -ErrorAction Stop).Path
    $token = (Get-Content -LiteralPath $resolvedTokenFile -Raw -Encoding UTF8 -ErrorAction Stop).Trim()
    if ([string]::IsNullOrWhiteSpace($token)) { throw 'The token file is empty.' }

    # Do not print a gateway response: it could include request metadata.
    $null = Invoke-WebRequest -Uri "$gatewayTarget/v1/models" -Headers @{ Authorization = "Bearer $token" } -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop

    $script:tailscalePath = Get-TailscaleExecutable
    $version = (Invoke-Tailscale -Arguments @('version')) -join "`n"
    if ([string]::IsNullOrWhiteSpace($version)) { throw 'Tailscale version check returned no version.' }

    $node = Get-TailscaleJson -Arguments @('status', '--json')
    if ($node.BackendState -cne 'Running') { throw 'Tailscale is not logged in and running.' }
    if ([string]::IsNullOrWhiteSpace([string]$node.Self.DNSName)) { throw 'Tailscale has no tailnet DNS name.' }
    $dnsName = ([string]$node.Self.DNSName).TrimEnd('.')

    $before = Get-TailscaleJson -Arguments @('serve', 'status', '--json')
    if (-not (Test-RemotePortAbsent -Status $before)) {
        if (Test-ExpectedRemoteServeStatus -Status $before -DnsName $dnsName) {
            # An exact pre-existing mapping is an idempotent success. It was
            # not altered, so all unrelated Serve rules remain preserved.
            Write-Output ("https://{0}:{1}" -f $dnsName, $servePort)
            Write-Output $resolvedTokenFile
            exit 0
        }
        throw 'Tailscale HTTPS 11439 is already configured; refusing to replace it.'
    }
    $beforeOtherRules = Get-ServeWithoutRemotePort -Status $before

    $null = Invoke-Tailscale -Arguments @('serve', '--bg', '--https=11439', $gatewayTarget)
    $after = Get-TailscaleJson -Arguments @('serve', 'status', '--json')
    if (-not (Test-ExpectedRemoteServeStatus -Status $after -DnsName $dnsName)) {
        throw 'Tailscale Serve verification failed; expected HTTPS 11439 to the loopback gateway with no Funnel.'
    }
    if (-not (Test-StructuralEqual -Left $beforeOtherRules -Right (Get-ServeWithoutRemotePort -Status $after))) {
        throw 'Existing Tailscale Serve rules changed; refusing to report success.'
    }

    Write-Output ("https://{0}:{1}" -f $dnsName, $servePort)
    Write-Output $resolvedTokenFile
} catch {
    # Never include a bearer token, Tailscale command output, or HTTP response in errors.
    Write-Error 'AIRI remote model test Tailscale Serve was not enabled. Check the local gateway, token-file path, and Tailscale status.'
    exit 1
}
