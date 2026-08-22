#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$script:StrictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)

function Read-Utf8File {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required work-continuity file is missing: $Path"
    }
    return [System.IO.File]::ReadAllText($Path, $script:StrictUtf8)
}

function Assert-ContainsPattern {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if ($Text -notmatch $Pattern) {
        throw "Work-continuity contract missing: $Description"
    }
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

function Get-FrontMatterValue {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $pattern = '(?m)^' + [System.Text.RegularExpressions.Regex]::Escape($Name) + ':\s*"([^"\r\n]+)"\s*$'
    $match = [System.Text.RegularExpressions.Regex]::Match($Text, $pattern)
    if (-not $match.Success) {
        throw "Work-continuity contract missing: frontmatter $Name"
    }
    return $match.Groups[1].Value
}

function Get-FrontMatter {
    param([Parameter(Mandatory = $true)][string]$Text)

    $match = [System.Text.RegularExpressions.Regex]::Match(
        $Text,
        '\A---\r?\n(?<front>.*?)\r?\n---(?:\r?\n|$)',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
    if (-not $match.Success) {
        throw 'Work-continuity contract missing: exact YAML frontmatter boundary.'
    }
    return $match.Groups['front'].Value
}

function Get-TailFromToken {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Token
    )

    $index = $Text.IndexOf($Token, [System.StringComparison]::Ordinal)
    if ($index -lt 0) {
        throw "Work-continuity contract missing: section token $Token"
    }
    return $Text.Substring($index)
}

function Assert-TokenOrder {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$First,
        [Parameter(Mandatory = $true)][string]$Second,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $firstIndex = $Text.IndexOf($First, [System.StringComparison]::OrdinalIgnoreCase)
    $secondIndex = $Text.IndexOf($Second, [System.StringComparison]::OrdinalIgnoreCase)
    if ($firstIndex -lt 0 -or $secondIndex -lt 0 -or $firstIndex -ge $secondIndex) {
        throw "Work-continuity contract ordering failed: $Description"
    }
}

$docsRoot = Join-Path $PSScriptRoot 'airi_docs'
$liveStatePath = Find-UniqueFile -Root $docsRoot -Name 'AIRI-WORKING-STATE.md'
$agentsPath = Join-Path $PSScriptRoot 'AGENTS.md'
$nextSessionPath = Join-Path $PSScriptRoot 'NEXT-SESSION.md'
$handoffPath = Find-UniqueFile -Root $docsRoot -Name 'AIRI-CODEX-HANDOFF-2026-08-21.md'
$roadmapPath = Find-UniqueFile -Root $docsRoot -Name 'AIRI-ROADMAP-STATUS.md'

$liveState = Read-Utf8File -Path $liveStatePath
$agents = Read-Utf8File -Path $agentsPath
$nextSession = Read-Utf8File -Path $nextSessionPath
$handoff = Read-Utf8File -Path $handoffPath
$roadmap = Read-Utf8File -Path $roadmapPath
$frontMatter = Get-FrontMatter -Text $liveState

Assert-ContainsPattern $frontMatter '(?m)^schema_version:\s*1\s*$' 'live-state schema version'
Assert-ContainsPattern $frontMatter '(?m)^updated_at_kst:\s*"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2}"\s*$' 'parseable live-state update time'
Assert-ContainsPattern $frontMatter '(?m)^checkpoint_id:\s*"[^"\r\n]+"\s*$' 'durable checkpoint id'
Assert-ContainsPattern $frontMatter '(?m)^goal_status:\s*"(?:active|paused|complete|blocked)"\s*$' 'recognized goal status'
Assert-ContainsPattern $frontMatter '(?m)^authorization:\s*"[^"\r\n]+"\s*$' 'authorization fence'
Assert-ContainsPattern $frontMatter '(?m)^active_phase:\s*"[^"\r\n]+"\s*$' 'active phase'
Assert-ContainsPattern $frontMatter '(?m)^git_head:\s*"[0-9a-f]{40}"\s*$' 'exact git HEAD'
Assert-ContainsPattern $frontMatter '(?m)^worktree_state:\s*"[^"\r\n]+"\s*$' 'worktree state'
Assert-ContainsPattern $frontMatter '(?m)^active_trainer_count:\s*\d+\s*$' 'active trainer count'
Assert-ContainsPattern $liveState 'heartbeat' 'heartbeat and event triggers'
Assert-ContainsPattern $liveState 'resume' 'resume recovery procedure'
Assert-ContainsPattern $liveState 'compact' 'post-compact read/reconcile procedure'
Assert-ContainsPattern $liveState 'intent checkpoint' 'pre-command intent checkpoint'
Assert-ContainsPattern $liveState 'receipt checkpoint' 'post-command receipt checkpoint'

Assert-ContainsPattern $agents 'AIRI-WORKING-STATE\.md' 'AGENTS live-state read rule'
Assert-ContainsPattern $agents '(?s)active goal.*60.*heartbeat' 'AGENTS heartbeat ceiling'
Assert-ContainsPattern $agents '(?s)GPU.*15' 'AGENTS active-compute heartbeat ceiling'
Assert-ContainsPattern $agents 'intent checkpoint' 'AGENTS pre-command checkpoint rule'
Assert-ContainsPattern $agents 'compact' 'AGENTS post-compact distrust rule'
Assert-ContainsPattern $agents 'interrupted-awaiting-quota-reset' 'quota exhaustion recovery state'

$goalStatus = Get-FrontMatterValue -Text $frontMatter -Name 'goal_status'
$authorization = Get-FrontMatterValue -Text $frontMatter -Name 'authorization'
$activePhase = Get-FrontMatterValue -Text $frontMatter -Name 'active_phase'
$gitHead = Get-FrontMatterValue -Text $frontMatter -Name 'git_head'
if ($goalStatus -eq 'active') {
    if ($authorization -match 'read-only|documentation-only' -or $activePhase -match 'paused') {
        throw 'Work-continuity contract mismatch: active goal has paused authorization or phase.'
    }
    Assert-ContainsPattern $liveState 'operational-adoption-forbidden' 'active goal adoption fence'
}

& git -C $PSScriptRoot merge-base --is-ancestor $gitHead HEAD
if ($LASTEXITCODE -ne 0) {
    throw 'Work-continuity contract mismatch: recorded git_head is not an ancestor of HEAD.'
}

$executionOrder = 'execution_order=P0_A>P0_B>E2_LAUNCH>E2_PROVENANCE>PACKAGE>T3_36>CAMPAIGN_3X500>USER_DECISION'
foreach ($document in @($nextSession, $handoff, $roadmap)) {
    Assert-ContainsPattern $document ([System.Text.RegularExpressions.Regex]::Escape("goal_status=$goalStatus")) 'goal status must agree across current documents'
    Assert-ContainsPattern $document 'adoption_authorized=false' 'operational adoption must stay forbidden'
    Assert-ContainsPattern $document ([System.Text.RegularExpressions.Regex]::Escape($executionOrder)) 'exact execution order must agree across current documents'
}

$liveStateEntry = $nextSession.IndexOf('AIRI-WORKING-STATE.md', [System.StringComparison]::Ordinal)
$handoffEntry = $nextSession.IndexOf('AIRI-CODEX-HANDOFF-2026-08-21.md', [System.StringComparison]::Ordinal)
if ($liveStateEntry -lt 0 -or $handoffEntry -lt 0 -or $liveStateEntry -ge $handoffEntry) {
    throw 'Work-continuity contract missing: live state must precede the handoff entry.'
}
Assert-ContainsPattern $handoff 'AIRI-WORKING-STATE\.md' 'handoff points to live state'
Assert-ContainsPattern $roadmap 'AIRI-WORKING-STATE\.md' 'roadmap points to live state'
$handoffExecution = Get-TailFromToken -Text $handoff -Token '## 8.'
$roadmapExecution = Get-TailFromToken -Text $roadmap -Token '### v4 active'
Assert-ContainsPattern $handoff 'PRE-P0 PARAMETER REFERENCE.*DO NOT RUN' 'direct trainer block must be non-authoritative'
Assert-ContainsPattern $handoffExecution '--resume-from-checkpoint' 'exact checkpoint resume gate'
Assert-ContainsPattern $handoffExecution 'run-state\.json' 'durable runner state contract'
Assert-ContainsPattern $handoffExecution 'SAFE_TO_POWER_OFF' 'safe power-off marker'
Assert-ContainsPattern $handoffExecution 'authoritative durable runner' 'E2 must use the durable runner'
Assert-TokenOrder $handoffExecution 'P0-A' 'P0-B' 'handoff P0-A must precede P0-B'
Assert-TokenOrder $handoffExecution 'P0-B' 'E2-LAUNCH' 'handoff P0-B must precede E2 launch'
Assert-TokenOrder $roadmapExecution 'P0-A' 'P0-B' 'roadmap P0-A must precede P0-B'
Assert-TokenOrder $roadmapExecution 'P0-B' 'E2-LAUNCH' 'roadmap P0-B must precede E2 launch'
$e2LaunchTail = Get-TailFromToken -Text $handoffExecution -Token 'E2-LAUNCH'
if ($e2LaunchTail -match 'train_airi_behavior_lora\.py') {
    throw 'Work-continuity contract mismatch: E2 launch checklist bypasses the durable runner.'
}

Write-Output 'AIRI work-continuity contract: PASS'
