param(
    [ValidateSet('check', 'run')]
    [string]$Action = 'check'
)

$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$taskExpected = Get-Content -LiteralPath (Join-Path $taskRoot 'docs\python_env\baseline.expected.json') -Raw | ConvertFrom-Json
$taskWorkRoot = Join-Path $taskRoot 'build\python-env-baseline'
$taskExecutable = Join-Path $taskRoot 'fheroes2.exe'

# Check immutable inputs before copying anything into the disposable runtime profile.
foreach ($taskInput in @($taskExpected.assets) + @($taskExpected.fixtures)) {
    $taskInputPath = Join-Path $taskRoot $taskInput.path
    if (!(Test-Path -LiteralPath $taskInputPath -PathType Leaf)) {
        throw "Missing local input: $taskInputPath. See docs/PYTHON_ENV_BASELINE.md."
    }
    if ((Get-FileHash -LiteralPath $taskInputPath -Algorithm SHA256).Hash -ne $taskInput.sha256) {
        throw "Baseline input changed: $taskInputPath. Preserve the fixture and review the expected manifest."
    }
}
foreach ($taskFixture in $taskExpected.fixtures) {
    $taskMapPath = Join-Path $taskRoot $taskFixture.map
    if (!(Test-Path -LiteralPath $taskMapPath -PathType Leaf)) {
        throw "Missing map: $taskMapPath"
    }
    if ((Get-FileHash -LiteralPath $taskMapPath -Algorithm SHA256).Hash -ne $taskFixture.map_sha256) {
        throw "Baseline map changed: $taskMapPath"
    }
}
if (!(Test-Path -LiteralPath $taskExecutable -PathType Leaf)) {
    throw 'Build the game first with script/windows/local.ps1.'
}
$taskBuiltExecutable = Join-Path $taskRoot 'build\windows-local\fheroes2.exe'
if (!(Test-Path -LiteralPath $taskBuiltExecutable -PathType Leaf)) {
    throw 'The windows-local build is missing. Run script/windows/local.ps1.'
}
$taskExecutableHash = (Get-FileHash -LiteralPath $taskExecutable -Algorithm SHA256).Hash
if ((Get-FileHash -LiteralPath $taskBuiltExecutable -Algorithm SHA256).Hash -ne $taskExecutableHash) {
    throw 'The root executable does not match the windows-local build. Run script/windows/local.ps1.'
}

New-Item -ItemType Directory -Path $taskWorkRoot -Force | Out-Null
$taskGitRevision = & git -C $taskRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine the source revision.' }
$taskManifest = [ordered]@{
    schema_version = 1
    source_commit = $taskGitRevision
    executable_sha256 = $taskExecutableHash
    expected_manifest = 'docs/python_env/baseline.expected.json'
    input_hashes_verified = $true
    note = 'File identity checks only; gameplay values are UI observations until the state API exists.'
}
$taskManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskWorkRoot 'verified-inputs.json') -Encoding UTF8
Write-Host 'Verified: 2 save snapshots, 2 maps, 2 AGG files, matching executables.'

if ($Action -eq 'check') { return }

# Windows GetHomeDirectory() prefers HOME over APPDATA. Do not silently use a real user profile.
if ($env:HOME) {
    throw 'HOME is set and would override the isolated APPDATA profile. Use a PowerShell session without HOME for this Windows-only baseline runner.'
}
$taskAppData = Join-Path $taskWorkRoot 'appdata'
$taskProfile = Join-Path $taskAppData 'fheroes2'
$taskSaveDirectory = Join-Path $taskProfile 'files\save'
New-Item -ItemType Directory -Path $taskSaveDirectory -Force | Out-Null
foreach ($taskFixture in $taskExpected.fixtures) {
    Copy-Item -LiteralPath (Join-Path $taskRoot $taskFixture.path) -Destination (Join-Path $taskSaveDirectory ($taskFixture.id + '.sav')) -Force
}
$taskConfig = Join-Path $taskProfile 'fheroes2.cfg'
if (!(Test-Path -LiteralPath $taskConfig)) {
    @('videomode = 800x600:800x600', 'fullscreen = off', 'sound volume = 0', 'music volume = 0') |
        Set-Content -LiteralPath $taskConfig -Encoding ASCII
}

$taskPreviousAppData = $env:APPDATA
$taskPreviousData = $env:FHEROES2_DATA
Push-Location $taskRoot
try {
    $env:APPDATA = $taskAppData
    $env:FHEROES2_DATA = $taskRoot
    Write-Host 'Load Standard Game -> other-side-day1 (or forsaken-day2).'
    Write-Host 'This runner is windowed; it is not the future headless/Python API.'
    & $taskExecutable
    if ($LASTEXITCODE -ne 0) { throw "Game exited with code $LASTEXITCODE." }
}
finally {
    $env:APPDATA = $taskPreviousAppData
    $env:FHEROES2_DATA = $taskPreviousData
    Pop-Location
}
