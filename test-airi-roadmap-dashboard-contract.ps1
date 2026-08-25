#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$script:StrictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
$script:AllowedStates = @('x', '~', 'Q', ' ', 'P', 'B', 'D', 'F', 'S', 'N/A', '?')
$script:ChecklistPattern = '(?m)^- \[(?<state>[^\]\r\n]+)\][^\r\n]*'

function Read-Utf8File {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required roadmap-dashboard file is missing: $Path"
    }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        throw "Roadmap-dashboard file must be UTF-8 without BOM: $Path"
    }
    return [System.IO.File]::ReadAllText($Path, $script:StrictUtf8)
}

function Find-UniqueFile {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $matches = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Filter $Name)
    if ($matches.Count -ne 1) {
        throw "Expected one $Name below $Root; found $($matches.Count)."
    }
    return $matches[0].FullName
}

function ConvertFrom-Base64Utf8 {
    param([Parameter(Mandatory = $true)][string]$Value)

    return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Value))
}

function Assert-ContainsPattern {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if ($Text -notmatch $Pattern) {
        throw "Roadmap-dashboard contract missing: $Description"
    }
}

function Get-ChecklistMatches {
    param([Parameter(Mandatory = $true)][string]$Text)

    $matches = [regex]::Matches($Text, $script:ChecklistPattern)
    foreach ($match in $matches) {
        $state = $match.Groups['state'].Value
        if ($state -notin $script:AllowedStates) {
            throw "Roadmap-dashboard contract has unsupported checklist state [$state]."
        }
    }
    return $matches
}

function Get-StateCounts {
    param([Parameter(Mandatory = $true)]$Matches)

    $counts = @{}
    foreach ($state in $script:AllowedStates) {
        $counts[$state] = 0
    }
    foreach ($match in $Matches) {
        $counts[$match.Groups['state'].Value]++
    }
    return $counts
}

function Assert-DisplayedMetric {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][double]$Numerator,
        [Parameter(Mandatory = $true)][int]$Denominator
    )

    $pattern = '(?m)^- ' + [regex]::Escape($Label) +
        ':\s+\*\*(?<numerator>\d+(?:\.\d+)?)/(?<denominator>\d+)\s+\((?<percent>\d+(?:\.\d+)?)%\)\*\*'
    $match = [regex]::Match($Text, $pattern)
    if (-not $match.Success) {
        throw "Roadmap-dashboard metric is missing or malformed: $Label"
    }

    $culture = [System.Globalization.CultureInfo]::InvariantCulture
    $actualNumerator = [double]::Parse($match.Groups['numerator'].Value, $culture)
    $actualDenominator = [int]$match.Groups['denominator'].Value
    $actualPercent = [double]::Parse($match.Groups['percent'].Value, $culture)
    $expectedPercent = [Math]::Round(
        100.0 * $Numerator / $Denominator,
        1,
        [MidpointRounding]::AwayFromZero
    )
    if ([Math]::Abs($actualNumerator - $Numerator) -gt 0.001 -or
        $actualDenominator -ne $Denominator -or
        [Math]::Abs($actualPercent - $expectedPercent) -gt 0.001) {
        throw "Roadmap-dashboard metric differs from parsed checklist: $Label"
    }
}

$codexSkillPath = Join-Path $PSScriptRoot '.agents\skills\airi-roadmap-dashboard\SKILL.md'
$claudeSkillPath = Join-Path $PSScriptRoot '.claude\skills\airi-roadmap-dashboard\SKILL.md'
$openAiYamlPath = Join-Path $PSScriptRoot '.agents\skills\airi-roadmap-dashboard\agents\openai.yaml'
$docsRoot = Join-Path $PSScriptRoot 'airi_docs'
$contractPath = Find-UniqueFile -Root $docsRoot -Name 'AIRI-ROADMAP-DASHBOARD-CONTRACT.md'
$roadmapPath = Find-UniqueFile -Root $docsRoot -Name 'AIRI-ROADMAP-STATUS.md'

$codexSkill = Read-Utf8File -Path $codexSkillPath
$claudeSkill = Read-Utf8File -Path $claudeSkillPath
$openAiYaml = Read-Utf8File -Path $openAiYamlPath
$contract = Read-Utf8File -Path $contractPath
$roadmap = Read-Utf8File -Path $roadmapPath

if ((Get-FileHash -LiteralPath $codexSkillPath -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath $claudeSkillPath -Algorithm SHA256).Hash) {
    throw 'Codex and Claude roadmap-dashboard skill entry points must be byte-identical.'
}
foreach ($skill in @($codexSkill, $claudeSkill)) {
    Assert-ContainsPattern $skill '\A---\r?\n(?s:.*?)\r?\n---\r?\n' 'skill YAML frontmatter boundary'
    Assert-ContainsPattern $skill '(?m)^name:\s*airi-roadmap-dashboard\s*$' 'shared skill name'
    Assert-ContainsPattern $skill '(?m)^description:\s*.*AIRI.*heartbeat.*$' 'AIRI-scoped skill description'
    Assert-ContainsPattern $skill 'mutation,.*process.*commit.*push' 'permission boundary'
    if ($skill -match '(?m)^- `\[(?:x|~|Q| |P|B|D|F|S|N/A|\?)\]`') {
        throw 'Skill entry point duplicates the common status table.'
    }
}

$sharedRelativeReference = $null
foreach ($skillPath in @($codexSkillPath, $claudeSkillPath)) {
    $skillText = Read-Utf8File -Path $skillPath
    $contractLinks = @([regex]::Matches(
        $skillText,
        '\]\((?<target>\.\./[^)\r\n]*AIRI-ROADMAP-DASHBOARD-CONTRACT\.md)\)'
    ))
    if ($contractLinks.Count -ne 1) {
        throw "Skill must reference the shared dashboard contract exactly once: $skillPath"
    }
    $contractRelativePath = $contractLinks[0].Groups['target'].Value
    if ($null -eq $sharedRelativeReference) {
        $sharedRelativeReference = $contractRelativePath
    }
    elseif ($contractRelativePath -ne $sharedRelativeReference) {
        throw 'Codex and Claude skills reference different dashboard contract paths.'
    }
    $resolvedReference = [System.IO.Path]::GetFullPath(
        (Join-Path (Split-Path -Parent $skillPath) $contractRelativePath)
    )
    if ($resolvedReference -ne [System.IO.Path]::GetFullPath($contractPath)) {
        throw "Skill contract reference resolves to the wrong file: $skillPath"
    }
    foreach ($link in [regex]::Matches($skillText, '\]\((?<target>\.\./[^)\r\n]+)\)')) {
        $resolvedLink = [System.IO.Path]::GetFullPath(
            (Join-Path (Split-Path -Parent $skillPath) $link.Groups['target'].Value)
        )
        if (-not (Test-Path -LiteralPath $resolvedLink)) {
            throw "Skill has a broken relative link: $resolvedLink"
        }
    }
}

$displayName = ConvertFrom-Base64Utf8 'QUlSSSDroZzrk5zrp7Ug64yA7Iuc67O065Oc'
$shortDescription = ConvertFrom-Base64Utf8 '7Iuk7KCcIOyekeyXhSDsg4Htg5zsmYAg66Gc65Oc66e1IOyytO2BrOumrOyKpO2KuOulvCDrj5nquLDtmZTtlanri4jri6Q='
if (-not $openAiYaml.Contains('display_name: "' + $displayName + '"')) {
    throw 'Roadmap-dashboard contract missing: Codex display name'
}
if (-not $openAiYaml.Contains('short_description: "' + $shortDescription + '"')) {
    throw 'Roadmap-dashboard contract missing: Codex short description'
}
Assert-ContainsPattern $openAiYaml ([regex]::Escape('$airi-roadmap-dashboard')) 'Codex default prompt invocation'
Assert-ContainsPattern $openAiYaml '(?m)^\s*allow_implicit_invocation:\s*true\s*$' 'implicit invocation enabled'

foreach ($state in $script:AllowedStates) {
    $token = '`[' + $state + ']`'
    if (-not $contract.Contains($token)) {
        throw "Shared contract omits checklist state $token."
    }
}
Assert-ContainsPattern $contract '(?m)^- [^\r\n]+=\s*`\[x\] /' 'normal completion formula'
Assert-ContainsPattern $contract '(?m)^- [^\r\n]+=\s*`\(\[x\] \+ \[F\]\) /' 'terminal completion formula'
foreach ($artifactToken in @('report', 'health', 'run-contract', 'packet', 'duplicate', 'missing')) {
    Assert-ContainsPattern $contract ([regex]::Escape($artifactToken)) "heartbeat token $artifactToken"
}
Assert-ContainsPattern $contract '(?s)heartbeat.{0,600}14' 'dual-document heartbeat ceiling'

$dashboardHeading = ConvertFrom-Base64Utf8 'IyMg7IKs7Jqp7J6Q7JqpIO2YhOyerCDsp4Ttlokg64yA7Iuc67O065Oc'
$goalHeading = ConvertFrom-Base64Utf8 'IyMjIO2YhOyerCDso7zsmpQg7J6R7JeFIOuLqOqzhChNNCkg7LK07YGs66as7Iqk7Yq4'
$statusHeading = ConvertFrom-Base64Utf8 'IyMjIOyDge2DnCDtkZzspIDqs7wg6rOE7IKwIOq4sOykgA=='
$blockedCause = ConvertFrom-Base64Utf8 '7LCo64uoIOybkOyduDo='
$blockedResume = ConvertFrom-Base64Utf8 '7J6s6rCcIOyhsOqxtDo='
$dashboardIndex = $roadmap.IndexOf($dashboardHeading, [System.StringComparison]::Ordinal)
$firstSection = [regex]::Match($roadmap, '(?m)^## ').Index
if ($dashboardIndex -lt 0 -or $dashboardIndex -ne $firstSection) {
    throw 'User roadmap dashboard must be the first level-two section.'
}
$goalStart = $roadmap.IndexOf($goalHeading, [System.StringComparison]::Ordinal)
$goalEnd = $roadmap.IndexOf($statusHeading, [System.StringComparison]::Ordinal)
if ($goalStart -lt 0 -or $goalEnd -le $goalStart) {
    throw 'Current M4 checklist boundary is missing or malformed.'
}
$goalChecklist = $roadmap.Substring($goalStart, $goalEnd - $goalStart)
$goalMatches = Get-ChecklistMatches -Text $goalChecklist
$allMatches = Get-ChecklistMatches -Text $roadmap
if ($goalMatches.Count -eq 0 -or $allMatches.Count -eq 0) {
    throw 'Roadmap checklist parsing produced no items.'
}

$goalRunning = @($goalMatches | Where-Object { $_.Groups['state'].Value -eq '~' })
if ($goalRunning.Count -gt 1) {
    throw 'Current Goal has more than one [~] item.'
}
foreach ($running in $goalRunning) {
    if ($running.Value -notmatch '\d{4}-\d{2}-\d{2} \d{2}:\d{2}') {
        throw 'Current [~] item must include an observed date and time.'
    }
    if ($running.Value -match 'matrix|campaign' -and
        $running.Value -notmatch '\d+/\d+') {
        throw 'Long-running [~] heartbeat must include current/total progress.'
    }
}
if (@($allMatches | Where-Object { $_.Groups['state'].Value -eq '?' }).Count -ne 0) {
    throw 'Roadmap audit left an unresolved [?] item.'
}

for ($index = 0; $index -lt $allMatches.Count; $index++) {
    if ($allMatches[$index].Groups['state'].Value -ne 'B') {
        continue
    }
    $blockEnd = if ($index + 1 -lt $allMatches.Count) {
        $allMatches[$index + 1].Index
    }
    else {
        $roadmap.Length
    }
    $block = $roadmap.Substring($allMatches[$index].Index, $blockEnd - $allMatches[$index].Index)
    if (-not $block.Contains($blockedCause) -or -not $block.Contains($blockedResume)) {
        throw "Blocked roadmap item lacks cause or resume condition: $($allMatches[$index].Value)"
    }
}

$goalCounts = Get-StateCounts -Matches $goalMatches
$goalActive = $goalMatches.Count - $goalCounts['S'] - $goalCounts['N/A']
$goalTerminal = $goalCounts['x'] + $goalCounts['F']
$goalProgress = $goalTerminal + (0.5 * $goalCounts['P']) + (0.5 * $goalCounts['~'])
Assert-DisplayedMetric -Text $roadmap -Label (ConvertFrom-Base64Utf8 'TTQg7KCV7IOBIOyZhOujjOycqA==') -Numerator $goalCounts['x'] -Denominator $goalActive
Assert-DisplayedMetric -Text $roadmap -Label (ConvertFrom-Base64Utf8 'TTQg7LKY66asIOyiheujjOycqA==') -Numerator $goalTerminal -Denominator $goalActive
Assert-DisplayedMetric -Text $roadmap -Label (ConvertFrom-Base64Utf8 'TTQg7KeE7ZaJIOyngOyImA==') -Numerator $goalProgress -Denominator $goalActive

$allCounts = Get-StateCounts -Matches $allMatches
$allActive = $allMatches.Count - $allCounts['S'] - $allCounts['N/A']
$allTerminal = $allCounts['x'] + $allCounts['F']
$allProgress = $allTerminal + (0.5 * $allCounts['P']) + (0.5 * $allCounts['~'])
Assert-DisplayedMetric -Text $roadmap -Label (ConvertFrom-Base64Utf8 '7KCE7LK0IOuhnOuTnOuntSDsoJXsg4Eg7JmE66OM7Jyo') -Numerator $allCounts['x'] -Denominator $allActive
Assert-DisplayedMetric -Text $roadmap -Label (ConvertFrom-Base64Utf8 '7KCE7LK0IOuhnOuTnOuntSDsspjrpqwg7KKF66OM7Jyo') -Numerator $allTerminal -Denominator $allActive
Assert-DisplayedMetric -Text $roadmap -Label (ConvertFrom-Base64Utf8 '7KCE7LK0IOuhnOuTnOuntSDsp4Ttlokg7KeA7IiY') -Numerator $allProgress -Denominator $allActive

Write-Output 'AIRI roadmap dashboard contract: PASS'
