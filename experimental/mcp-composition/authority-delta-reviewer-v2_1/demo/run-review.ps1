[CmdletBinding()]
param(
    [Alias('McpSourceRoot')]
    [string]$McpSource = ''
)

$ErrorActionPreference = 'Stop'
$reviewRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($McpSource)) {
    $McpSource = Join-Path $reviewRoot 'upstream\sep3004-head-1143d96f82ce9316e4e1675a3f6786902b9fe1ce.md'
}
$McpSource = [System.IO.Path]::GetFullPath($McpSource)
if (-not (Test-Path -LiteralPath $McpSource)) {
    throw "Pinned SEP-3004 source is missing: $McpSource"
}
$resultsDir = Join-Path $reviewRoot 'results'
if (-not (Test-Path -LiteralPath $resultsDir)) {
    New-Item -ItemType Directory -Path $resultsDir | Out-Null
}

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE"
    }
}

$watch = [System.Diagnostics.Stopwatch]::StartNew()
Push-Location $reviewRoot
try {
    Invoke-Checked node @('.\vectors\generate-corpus.mjs')
    Invoke-Checked node @(
        '.\oracles\node\oracle.mjs',
        '--vectors', '.\vectors\corpus.json',
        '--parser', '.\vectors\parser-hostile.jsonl',
        '--kats', '.\vectors\canonicalization-kats.json',
        '--output', '.\results\node.json'
    )
    Invoke-Checked python @(
        '.\oracles\python\oracle.py',
        '--vectors', '.\vectors\corpus.json',
        '--parser', '.\vectors\parser-hostile.jsonl',
        '--kats', '.\vectors\canonicalization-kats.json',
        '--output', '.\results\python.json'
    )
    Invoke-Checked node @(
        '.\oracles\verify-parity-and-collision.mjs',
        '.\results\node.json',
        '.\results\python.json',
        '.\vectors\corpus.json',
        '.\results\PARITY_AND_COMMITMENT.json'
    )
    Invoke-Checked node @(
        '.\oracles\sep3004-current-head-projection.mjs',
        $McpSource,
        '.\vectors\corpus.json',
        '.\results\SEP3004_CURRENT_HEAD_PROJECTION.json'
    )
    Invoke-Checked node @(
        '.\oracles\verify-independence.mjs',
        $reviewRoot,
        '.\results\PACKAGE_INDEPENDENCE.json'
    )
}
finally {
    Pop-Location
    $watch.Stop()
}

if ($watch.Elapsed.TotalMinutes -gt 5) {
    throw "Reviewer command exceeded five minutes: $($watch.Elapsed.TotalSeconds) seconds"
}

$manifest = Get-Content -Raw -LiteralPath (Join-Path $reviewRoot 'vectors\EXACT_SET_MANIFEST.json') | ConvertFrom-Json
$nodeResult = Get-Content -Raw -LiteralPath (Join-Path $reviewRoot 'results\node.json') | ConvertFrom-Json
$pythonResult = Get-Content -Raw -LiteralPath (Join-Path $reviewRoot 'results\python.json') | ConvertFrom-Json
$parityResult = Get-Content -Raw -LiteralPath (Join-Path $reviewRoot 'results\PARITY_AND_COMMITMENT.json') | ConvertFrom-Json
$projectionResult = Get-Content -Raw -LiteralPath (Join-Path $reviewRoot 'results\SEP3004_CURRENT_HEAD_PROJECTION.json') | ConvertFrom-Json
$independenceResult = Get-Content -Raw -LiteralPath (Join-Path $reviewRoot 'results\PACKAGE_INDEPENDENCE.json') | ConvertFrom-Json

$pass = $nodeResult.pass -and $pythonResult.pass -and $parityResult.pass -and $projectionResult.pass -and $independenceResult.pass
if (-not $pass) {
    throw 'One or more Reviewer V2.1 Core gates failed.'
}
if ($manifest.vectorCount -lt 48 -or $manifest.kindCount -lt 16 -or
    $manifest.parserFixtureCount -lt 24 -or $manifest.canonicalizationKatCount -lt 3) {
    throw 'Reviewer V2.1 exact-set minimums are not satisfied.'
}
if ($nodeResult.mutations.count -ne 4096 -or $nodeResult.mutations.unique -ne 4096 -or
    $nodeResult.mutations.operatorCount -lt 16 -or $nodeResult.mutations.unexpectedAcceptance -ne 0 -or
    $pythonResult.mutations.count -ne 4096 -or $pythonResult.mutations.unique -ne 4096 -or
    $pythonResult.mutations.operatorCount -lt 16 -or $pythonResult.mutations.unexpectedAcceptance -ne 0) {
    throw 'Reviewer V2.1 mutation breadth gate failed.'
}

[pscustomobject]@{
    verdict = 'PASS'
    profile = 'auec-authority-delta-decision-v2_1'
    elapsedSeconds = [math]::Round($watch.Elapsed.TotalSeconds, 3)
    vectorCount = $manifest.vectorCount
    kindCount = $manifest.kindCount
    parserHostileCount = $manifest.parserFixtureCount
    canonicalizationKatCount = $manifest.canonicalizationKatCount
    mutationInstancesPerOracle = $nodeResult.mutations.count
    mutationOperatorsPerOracle = $nodeResult.mutations.operatorCount
    unexpectedAcceptance = $nodeResult.mutations.unexpectedAcceptance + $pythonResult.mutations.unexpectedAcceptance
    currentHeadClassification = $projectionResult.classification
    remoteWrites = 0
} | ConvertTo-Json -Compress
