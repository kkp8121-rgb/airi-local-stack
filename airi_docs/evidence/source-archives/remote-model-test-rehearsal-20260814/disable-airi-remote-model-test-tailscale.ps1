#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$gatewayTarget = 'http://127.0.0.1:11439'
$servePort = '11439'

function Invoke-Tailscale {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = @(& $script:tailscalePath @Arguments 2>&1 | ForEach-Object { $_.ToString() })
    if ($LASTEXITCODE -ne 0) {
        throw 'Tailscale command failed. Serve configuration was not reported as disabled.'
    }
    return $output
}

function Get-TailscaleJson {
    $text = (Invoke-Tailscale -Arguments @('serve', 'status', '--json')) -join "`n"
    if ([string]::IsNullOrWhiteSpace($text)) { throw 'Tailscale returned no JSON Serve status.' }
    try { return $text | ConvertFrom-Json } catch { throw 'Tailscale returned invalid JSON Serve status.' }
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

function Test-RemoteGatewayServeAbsent {
    param([Parameter(Mandatory = $true)]$Status)

    $tcp = $Status.PSObject.Properties['TCP'].Value
    if ($null -ne $tcp -and $null -ne $tcp.PSObject.Properties[$script:servePort].Value) { return $false }
    $web = $Status.PSObject.Properties['Web'].Value
    if ($null -eq $web) { return $true }
    foreach ($siteProperty in $web.PSObject.Properties) {
        if ($siteProperty.Name -like "*:$script:servePort") { return $false }
        $handlers = $siteProperty.Value.PSObject.Properties['Handlers'].Value
        if ($null -ne $handlers) {
            foreach ($handlerProperty in $handlers.PSObject.Properties) {
                if ($handlerProperty.Value.Proxy -ceq $script:gatewayTarget) { return $false }
            }
        }
    }
    return $true
}

function Test-ExpectedRemoteGatewayServe {
    param([Parameter(Mandatory = $true)]$Status, [Parameter(Mandatory = $true)][string]$DnsName)

    $tcp = $Status.PSObject.Properties['TCP'].Value
    $web = $Status.PSObject.Properties['Web'].Value
    if ($null -eq $tcp -or $null -eq $web) { return $false }
    $listener = $tcp.PSObject.Properties[$script:servePort].Value
    $site = $web.PSObject.Properties["$DnsName`:$script:servePort"].Value
    if ($null -eq $listener -or $listener.HTTPS -ne $true -or $null -eq $site) { return $false }
    $handler = $site.Handlers.PSObject.Properties['/'].Value
    return $null -ne $handler -and $handler.Proxy -ceq $script:gatewayTarget
}

try {
    $script:tailscalePath = Get-TailscaleExecutable
    $version = (Invoke-Tailscale -Arguments @('version')) -join "`n"
    if ([string]::IsNullOrWhiteSpace($version)) { throw 'Tailscale version check returned no version.' }
    $nodeText = (Invoke-Tailscale -Arguments @('status', '--json')) -join "`n"
    $node = $nodeText | ConvertFrom-Json
    if ($node.BackendState -cne 'Running' -or [string]::IsNullOrWhiteSpace([string]$node.Self.DNSName)) {
        throw 'Tailscale is not logged in and running.'
    }
    $dnsName = ([string]$node.Self.DNSName).TrimEnd('.')

    $before = Get-TailscaleJson
    if (Test-RemoteGatewayServeAbsent -Status $before) {
        Write-Output 'AIRI remote model test Tailscale Serve listener is already absent.'
        exit 0
    }
    if (-not (Test-ExpectedRemoteGatewayServe -Status $before -DnsName $dnsName)) {
        throw 'Tailscale HTTPS 11439 is not the AIRI loopback gateway; refusing to remove it.'
    }
    $beforeOtherRules = Get-ServeWithoutRemotePort -Status $before

    # This is intentionally scoped to the HTTPS listener created by the enable wrapper.
    $null = Invoke-Tailscale -Arguments @('serve', '--https=11439', 'off')
    $after = Get-TailscaleJson
    if (-not (Test-RemoteGatewayServeAbsent -Status $after)) {
        throw 'The AIRI remote model test Serve listener is still present.'
    }
    if (-not (Test-StructuralEqual -Left $beforeOtherRules -Right (Get-ServeWithoutRemotePort -Status $after))) {
        throw 'Existing Tailscale Serve rules changed; refusing to report success.'
    }
    Write-Output 'AIRI remote model test Tailscale Serve listener disabled.'
} catch {
    Write-Error 'AIRI remote model test Tailscale Serve was not disabled. Check Tailscale status and the local Serve configuration.'
    exit 1
}
