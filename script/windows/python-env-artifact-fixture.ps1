###########################################################################
#   fheroes2: https://github.com/ihhub/fheroes2                           #
#   Copyright (C) 2026                                                    #
#                                                                         #
#   This program is free software; you can redistribute it and/or modify  #
#   it under the terms of the GNU General Public License as published by  #
#   the Free Software Foundation; either version 2 of the License, or     #
#   (at your option) any later version.                                   #
#                                                                         #
#   This program is distributed in the hope that it will be useful,       #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         #
#   GNU General Public License for more details.                          #
#                                                                         #
#   You should have received a copy of the GNU General Public License     #
#   along with this program; if not, write to the                         #
#   Free Software Foundation, Inc.,                                       #
#   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             #
###########################################################################

param(
    [ValidateRange(1, 256)]
    [int]$Jobs = 8,
    [switch]$ExpansionOnly
)

$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$taskToolBin = Join-Path $taskRoot '.tools/msys64/ucrt64/bin'
$taskBase = Join-Path $taskRoot 'build/python-env-baseline/fixtures/other-side-day1.sav'
$taskOutput = Join-Path $taskRoot 'build/python-env-baseline/fixtures'
if (!(Test-Path -LiteralPath $taskBase)) { throw 'Prepare the original baseline save first; see docs/PYTHON_ENV_BASELINE.md.' }
$taskOldPath = $env:PATH
$taskOldData = $env:FHEROES2_DATA
$taskOldAppData = $env:APPDATA
Push-Location $taskRoot
try {
    $env:PATH = "$taskToolBin;$taskOldPath"
    $env:FHEROES2_DATA = $taskRoot
    $env:APPDATA = Join-Path $taskRoot 'build/python-env-artifact-fixture-profile'
    & (Join-Path $taskToolBin 'cmake.exe') --preset windows-local
    if ($LASTEXITCODE -ne 0) { throw 'Could not configure the optional native test builder.' }
    & (Join-Path $taskToolBin 'cmake.exe') --build build/windows-local --target fheroes2_artifact_fixture --parallel $Jobs
    if ($LASTEXITCODE -ne 0) { throw 'Could not build the native test builder.' }
    if (!$ExpansionOnly) {
        & (Join-Path $taskRoot 'build/windows-local/fheroes2_artifact_fixture.exe') $taskBase $taskOutput
        if ($LASTEXITCODE -ne 0) { throw 'Native fixture generation failed.' }
    }
    & (Join-Path $taskRoot 'build/windows-local/fheroes2_artifact_fixture.exe') $taskBase $taskOutput --expansion-only
    if ($LASTEXITCODE -ne 0) { throw 'Native object/spell expansion fixture generation failed.' }
    & (Join-Path $taskRoot 'build/windows-local/fheroes2_artifact_fixture.exe') $taskBase $taskOutput --special-only
    if ($LASTEXITCODE -ne 0) { throw 'Native special fixture generation failed.' }
}
finally {
    $env:PATH = $taskOldPath
    $env:FHEROES2_DATA = $taskOldData
    $env:APPDATA = $taskOldAppData
    Pop-Location
}
