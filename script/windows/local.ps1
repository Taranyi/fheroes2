param(
    [ValidateSet('configure', 'build', 'run', 'translations')]
    [string]$Action = 'build',
    [ValidateSet('windows-local', 'windows-debug')]
    [string]$Preset = 'windows-local',
    [ValidateRange(1, 256)]
    [int]$Jobs = [Math]::Max(1, [Math]::Min(8, [Environment]::ProcessorCount))
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$toolRoot = Join-Path $projectRoot '.tools\msys64'
$toolBin = Join-Path $toolRoot 'ucrt64\bin'
$cmake = Join-Path $toolBin 'cmake.exe'
if (!(Test-Path $cmake)) {
    throw 'Local tools are missing. Run script\windows\setup-local.ps1 first.'
}

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)." }
}

function Build-Translations {
    # Use the project's Makefile, including its legacy character encodings.
    Invoke-Checked (Join-Path $toolRoot 'usr\bin\bash.exe') @(
        '--noprofile', '--norc', '-c', 'export PATH=/usr/bin:$PATH; command -v make msgfmt iconv sed >/dev/null || exit 1; make -C files/lang'
    )
    foreach ($source in Get-ChildItem (Join-Path $projectRoot 'files\lang') -Filter '*.po') {
        $compiled = [IO.Path]::ChangeExtension($source.FullName, '.mo')
        if (!(Test-Path $compiled) -or (Get-Item $compiled).Length -lt 28) {
            throw "Translation was not generated: $compiled"
        }
    }
}

function Copy-RuntimeLibraries {
    param([string]$Executable)
    $queue = New-Object 'System.Collections.Generic.Queue[string]'
    $seen = @{}
    $queue.Enqueue($Executable)
    while ($queue.Count -gt 0) {
        $binary = $queue.Dequeue()
        $imports = & (Join-Path $toolBin 'objdump.exe') -p $binary
        if ($LASTEXITCODE -ne 0) { throw "Cannot inspect runtime dependencies: $binary" }
        foreach ($line in $imports) {
            if ($line -match 'DLL Name:\s*(\S+)') {
                $name = $Matches[1]
                if ($seen.ContainsKey($name)) { continue }
                $seen[$name] = $true
                $library = Join-Path $toolBin $name
                if (Test-Path $library) {
                    Copy-Item -LiteralPath $library -Destination $projectRoot -Force
                    Copy-Item -LiteralPath $library -Destination (Split-Path $Executable) -Force
                    $queue.Enqueue($library)
                }
            }
        }
    }
}

$previousPath = $env:PATH
$previousData = $env:FHEROES2_DATA
Push-Location $projectRoot
try {
    $env:PATH = "$toolBin;$previousPath"
    $env:FHEROES2_DATA = $projectRoot
    if ($Action -eq 'translations') { Build-Translations; return }
    Invoke-Checked $cmake @('--preset', $Preset)
    if ($Action -eq 'configure') { return }
    Invoke-Checked $cmake @('--build', '--preset', $Preset, '--parallel', "$Jobs")
    Build-Translations
    $executable = Join-Path $projectRoot "build\$Preset\fheroes2.exe"
    Copy-RuntimeLibraries $executable
    Write-Host "Ready: $executable"
    if ($Action -eq 'run') {
        if (!(Test-Path (Join-Path $projectRoot 'DATA\HEROES2.AGG'))) {
            Write-Warning 'Game data is missing. Copy the original DATA and MAPS folders into the project root. See docs/README_windows_local.md.'
        }
        Invoke-Checked $executable @()
    }
}
finally {
    $env:PATH = $previousPath
    $env:FHEROES2_DATA = $previousData
    Pop-Location
}
