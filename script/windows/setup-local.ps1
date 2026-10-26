param([string]$Msys2Source = 'C:\dev\msys64')

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$destination = Join-Path $projectRoot '.tools\msys64'
if (!(Test-Path (Join-Path $destination 'usr\bin\pacman.exe'))) {
    if (!(Test-Path (Join-Path $Msys2Source 'usr\bin\pacman.exe'))) {
        throw 'Supply an existing MSYS2 installation with -Msys2Source <folder>.'
    }
    New-Item -ItemType Directory -Force $destination | Out-Null
    foreach ($part in @('usr', 'ucrt64', 'etc', 'var\lib\pacman')) {
        & robocopy (Join-Path $Msys2Source $part) (Join-Path $destination $part) /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1
        if ($LASTEXITCODE -ge 8) { throw "Failed to copy MSYS2 component: $part" }
    }
    Copy-Item (Join-Path $Msys2Source 'msys2_shell.cmd') $destination
}
foreach ($part in @('tmp', 'home', 'dev', 'var\cache\pacman\pkg')) {
    New-Item -ItemType Directory -Force (Join-Path $destination $part) | Out-Null
}

# Only the project-local copy is updated. The source installation is untouched.
$bash = Join-Path $destination 'usr\bin\bash.exe'
& $bash --noprofile --norc -c 'export PATH=/usr/bin:$PATH; pacman -Syu --noconfirm'
if ($LASTEXITCODE -ne 0) { throw 'MSYS2 update failed. Retry setup after checking the output.' }
# A second pass also handles updates that require a new MSYS2 process.
& $bash --noprofile --norc -c 'export PATH=/usr/bin:$PATH; pacman -Syu --needed --noconfirm mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-gdb mingw-w64-ucrt-x86_64-SDL2 mingw-w64-ucrt-x86_64-SDL2_mixer mingw-w64-ucrt-x86_64-SDL2_image mingw-w64-ucrt-x86_64-zlib make gettext iconv'
if ($LASTEXITCODE -ne 0) { throw 'Local dependency installation failed.' }
Write-Host 'Local tools are ready. Run script\windows\local.ps1 to build.'
