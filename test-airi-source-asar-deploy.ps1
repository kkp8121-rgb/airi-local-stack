#Requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSCommandPath
$installScript = Join-Path $repo 'install-airi-source-asar.ps1'
$restoreScript = Join-Path $repo 'restore-airi-source-asar.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('airi-source-asar-test-' + [guid]::NewGuid().ToString('N'))

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "Assertion failed: $Message" }
}

function Get-TestSha256 {
    param([string]$Path)
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-MustThrow {
    param(
        [scriptblock]$Action,
        [string]$ExpectedSubstring,
        [string]$Description
    )
    try { & $Action }
    catch {
        if ($_.Exception.Message -notlike "*$ExpectedSubstring*") {
            throw "Wrong failure for '$Description': $($_.Exception.Message)"
        }
        return
    }
    throw "Expected failure did not occur: $Description"
}

function Get-ByteSha256 {
    param([byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function New-TestAsar {
    param(
        [string]$Path,
        [string]$Tag,
        [ValidateSet('None', 'MissingMainOffset', 'RendererOutOfBounds', 'WrongPackageName')]
        [string]$Mutation = 'None'
    )

    $packageName = if ($Mutation -eq 'WrongPackageName') { 'not.airi' } else { 'ai.moeru.airi' }
    $packageBytes = [Text.Encoding]::UTF8.GetBytes('{"name":"' + $packageName + '","version":"0.11.3","tag":"' + $Tag + '"}')
    $mainBytes = [Text.Encoding]::UTF8.GetBytes('console.log("main-' + $Tag + '")')
    $preloadBytes = [Text.Encoding]::UTF8.GetBytes('export const preload = "' + $Tag + '"')
    $rendererBytes = [Text.Encoding]::UTF8.GetBytes('<html><body>' + $Tag + '</body></html>')
    $fillerBytes = New-Object byte[] (1MB)
    $fillerBytes[0] = [byte]($Tag.Length % 255)

    $packageOffset = 0L
    $mainOffset = $packageOffset + $packageBytes.Length
    $preloadOffset = $mainOffset + $mainBytes.Length
    $rendererOffset = $preloadOffset + $preloadBytes.Length
    $fillerOffset = $rendererOffset + $rendererBytes.Length

    $mainEntry = [ordered]@{ size = $mainBytes.Length; offset = $mainOffset.ToString([Globalization.CultureInfo]::InvariantCulture) }
    if ($Mutation -eq 'MissingMainOffset') { [void]$mainEntry.Remove('offset') }
    $rendererDeclaredOffset = if ($Mutation -eq 'RendererOutOfBounds') { 999999999L } else { $rendererOffset }

    $header = [ordered]@{
        files = [ordered]@{
            'package.json' = [ordered]@{
                size = $packageBytes.Length
                offset = '0'
                integrity = [ordered]@{ algorithm = 'SHA256'; hash = (Get-ByteSha256 -Bytes $packageBytes) }
            }
            out = [ordered]@{
                files = [ordered]@{
                    main = [ordered]@{ files = [ordered]@{ 'index.js' = $mainEntry } }
                    preload = [ordered]@{ files = [ordered]@{ 'index.mjs' = [ordered]@{ size = $preloadBytes.Length; offset = $preloadOffset.ToString([Globalization.CultureInfo]::InvariantCulture) } } }
                    renderer = [ordered]@{ files = [ordered]@{ 'index.html' = [ordered]@{ size = $rendererBytes.Length; offset = $rendererDeclaredOffset.ToString([Globalization.CultureInfo]::InvariantCulture) } } }
                }
            }
            'filler.bin' = [ordered]@{ size = $fillerBytes.Length; offset = $fillerOffset.ToString([Globalization.CultureInfo]::InvariantCulture) }
        }
    }
    $headerBytes = [Text.Encoding]::UTF8.GetBytes(($header | ConvertTo-Json -Compress -Depth 20))
    $innerSize = 4 + $headerBytes.Length
    $innerSize += (4 - ($innerSize % 4)) % 4
    $headerSize = $innerSize + 4

    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $writer = New-Object IO.BinaryWriter($stream, [Text.Encoding]::UTF8, $true)
    try {
        $writer.Write([UInt32]4)
        $writer.Write([UInt32]$headerSize)
        $writer.Write([UInt32]$innerSize)
        $writer.Write([UInt32]$headerBytes.Length)
        $writer.Write($headerBytes)
        for ($index = 0; $index -lt ($innerSize - 4 - $headerBytes.Length); $index++) { $writer.Write([byte]0) }
        $writer.Write($packageBytes)
        $writer.Write($mainBytes)
        $writer.Write($preloadBytes)
        $writer.Write($rendererBytes)
        $writer.Write($fillerBytes)
        $writer.Flush()
        $stream.Flush($true)
    }
    finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

$runningProcess = $null
try {
    $installDir = Join-Path $testRoot 'install'
    $resourcesDir = Join-Path $installDir 'resources'
    New-Item -ItemType Directory -Path $resourcesDir -Force | Out-Null
    $executable = Join-Path $installDir 'airi.exe'
    Copy-Item -LiteralPath (Join-Path $env:SystemRoot 'System32\cmd.exe') -Destination $executable

    $target = Join-Path $resourcesDir 'app.asar'
    $artifact = Join-Path $testRoot 'artifact.asar'
    New-TestAsar -Path $target -Tag 'old'
    New-TestAsar -Path $artifact -Tag 'new'
    $oldHash = Get-TestSha256 -Path $target
    $artifactHash = Get-TestSha256 -Path $artifact

    $backupCountBefore = @(Get-ChildItem -LiteralPath $resourcesDir -Filter '*.bak').Count
    Invoke-MustThrow {
        & $installScript -ArtifactPath $artifact -InstallDir $installDir `
            -ExpectedArtifactSha256 $artifactHash -ExpectedCurrentSha256 ('0' * 64)
    } 'Current app.asar SHA-256 does not match' 'wrong current digest'
    Assert-True ((Get-TestSha256 -Path $target) -eq $oldHash) 'wrong current digest must not mutate target'
    Assert-True (@(Get-ChildItem -LiteralPath $resourcesDir -Filter '*.bak').Count -eq $backupCountBefore) 'wrong current digest must not create a backup'

    $installed = & $installScript -ArtifactPath $artifact -InstallDir $installDir `
        -ExpectedArtifactSha256 $artifactHash -ExpectedCurrentSha256 $oldHash
    Assert-True ($installed.Action -eq 'Installed') 'valid source ASAR should install'
    Assert-True ((Get-TestSha256 -Path $target) -eq $artifactHash) 'installed target must equal artifact'
    Assert-True ((Get-TestSha256 -Path $installed.BackupPath) -eq $oldHash) 'File.Replace backup must be the exact displaced target'

    $idempotentInstall = & $installScript -ArtifactPath $artifact -InstallDir $installDir `
        -ExpectedArtifactSha256 $artifactHash -ExpectedCurrentSha256 $oldHash
    Assert-True ($idempotentInstall.Action -eq 'AlreadyInstalled') 'install must be idempotent'

    foreach ($invalidCase in @(
        @{ Mutation = 'MissingMainOffset'; Expected = 'missing'; Description = 'missing critical offset' },
        @{ Mutation = 'RendererOutOfBounds'; Expected = 'extends beyond the archive'; Description = 'truncated critical payload' },
        @{ Mutation = 'WrongPackageName'; Expected = 'is not AIRI'; Description = 'wrong package identity' }
    )) {
        $invalidPath = Join-Path $testRoot ($invalidCase.Mutation + '.asar')
        New-TestAsar -Path $invalidPath -Tag 'invalid' -Mutation $invalidCase.Mutation
        $invalidHash = Get-TestSha256 -Path $invalidPath
        Invoke-MustThrow {
            & $installScript -ArtifactPath $invalidPath -InstallDir $installDir `
                -ExpectedArtifactSha256 $invalidHash -ExpectedCurrentSha256 $artifactHash
        } $invalidCase.Expected $invalidCase.Description
        Assert-True ((Get-TestSha256 -Path $target) -eq $artifactHash) "$($invalidCase.Description) must not mutate target"
    }

    Invoke-MustThrow {
        & $installScript -ArtifactPath $artifact -InstallDir $installDir `
            -ExpectedArtifactSha256 ('0' * 64) -ExpectedCurrentSha256 $artifactHash
    } 'does not match ExpectedArtifactSha256' 'wrong artifact digest'
    Invoke-MustThrow {
        & $installScript -ArtifactPath $artifact -InstallDir $installDir `
            -ExpectedArtifactSha256 $artifactHash -ExpectedCurrentSha256 $artifactHash `
            -TestOnlyFailAfterReplace
    } 'requires EnableTestHooks' 'unguarded installer test hook'

    $rollbackArtifact = Join-Path $testRoot 'rollback-candidate.asar'
    New-TestAsar -Path $rollbackArtifact -Tag 'rollback-candidate'
    $rollbackArtifactHash = Get-TestSha256 -Path $rollbackArtifact
    Invoke-MustThrow {
        & $installScript -ArtifactPath $rollbackArtifact -InstallDir $installDir `
            -ExpectedArtifactSha256 $rollbackArtifactHash -ExpectedCurrentSha256 $artifactHash `
            -EnableTestHooks -TestOnlyFailAfterReplace
    } 'exact displaced archive was restored' 'installer forced post-replace rollback'
    Assert-True ((Get-TestSha256 -Path $target) -eq $artifactHash) 'failed install must restore exact prior target'

    # The executable barrier is the race-closing primitive: Windows must refuse
    # a new image section while an exclusive no-share handle is held.
    $exclusiveBarrier = [IO.File]::Open($executable, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    try {
        $launchFailed = $false
        try {
            $unexpectedProcess = Start-Process -FilePath $executable -ArgumentList '/c', 'exit 0' -PassThru -ErrorAction Stop
            if ($null -ne $unexpectedProcess) { $unexpectedProcess.WaitForExit(); $unexpectedProcess.Dispose() }
        }
        catch { $launchFailed = $true }
        Assert-True $launchFailed 'exclusive executable handle must prevent a launch race'
    }
    finally { $exclusiveBarrier.Dispose() }

    $runningProcess = Start-Process -FilePath $executable -ArgumentList '/c', 'ping 127.0.0.1 -n 8 > nul' -PassThru
    Start-Sleep -Milliseconds 250
    Invoke-MustThrow {
        & $installScript -ArtifactPath $artifact -InstallDir $installDir `
            -ExpectedArtifactSha256 $artifactHash -ExpectedCurrentSha256 $artifactHash
    } 'AIRI is running' 'running exact-path AIRI process'
    if (-not $runningProcess.HasExited) { $runningProcess.Kill(); $runningProcess.WaitForExit() }
    $runningProcess.Dispose()
    $runningProcess = $null

    Invoke-MustThrow {
        & $restoreScript -InstallDir $installDir -BackupPath $installed.BackupPath `
            -ExpectedBackupSha256 $oldHash -ExpectedCurrentSha256 $artifactHash `
            -EnableTestHooks -TestOnlyFailAfterReplace
    } 'exact pre-restore archive was restored' 'restore forced post-replace rollback'
    Assert-True ((Get-TestSha256 -Path $target) -eq $artifactHash) 'failed restore must restore exact pre-restore target'

    $restored = & $restoreScript -InstallDir $installDir -BackupPath $installed.BackupPath `
        -ExpectedBackupSha256 $oldHash -ExpectedCurrentSha256 $artifactHash
    Assert-True ($restored.Action -eq 'Restored') 'explicit restore should complete'
    Assert-True ((Get-TestSha256 -Path $target) -eq $oldHash) 'restore target must equal requested backup'
    Assert-True ((Get-TestSha256 -Path $restored.PreRestoreBackupPath) -eq $artifactHash) 'pre-restore backup must be the exact displaced installed archive'

    $idempotentRestore = & $restoreScript -InstallDir $installDir -BackupPath $installed.BackupPath `
        -ExpectedBackupSha256 $oldHash -ExpectedCurrentSha256 $artifactHash
    Assert-True ($idempotentRestore.Action -eq 'AlreadyRestored') 'literal restore retry must be idempotent under the deployment lock'

    Invoke-MustThrow {
        & $restoreScript -InstallDir $installDir -BackupPath $installed.BackupPath `
            -ExpectedBackupSha256 ('0' * 64) -ExpectedCurrentSha256 $oldHash
    } 'does not match ExpectedBackupSha256' 'wrong backup digest'
    Invoke-MustThrow {
        & $restoreScript -InstallDir $installDir -BackupPath $target `
            -ExpectedBackupSha256 $oldHash -ExpectedCurrentSha256 $oldHash
    } 'must not be the target app.asar' 'target used as backup'

    $hardLink = Join-Path $testRoot 'target-hardlink.asar'
    New-Item -ItemType HardLink -Path $hardLink -Target $target | Out-Null
    Invoke-MustThrow {
        & $restoreScript -InstallDir $installDir -BackupPath $hardLink `
            -ExpectedBackupSha256 $oldHash -ExpectedCurrentSha256 $oldHash
    } 'hard-link alias' 'hard-link alias used as backup'

    $junction = Join-Path $testRoot 'install-junction'
    New-Item -ItemType Junction -Path $junction -Target $installDir | Out-Null
    Invoke-MustThrow {
        & $installScript -ArtifactPath $artifact -InstallDir $junction `
            -ExpectedArtifactSha256 $artifactHash -ExpectedCurrentSha256 $oldHash
    } 'reparse-point component' 'junction install alias'

    'PASS: AIRI source ASAR deployment safety tests'
}
finally {
    if ($null -ne $runningProcess) {
        if (-not $runningProcess.HasExited) { $runningProcess.Kill(); $runningProcess.WaitForExit() }
        $runningProcess.Dispose()
    }
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
