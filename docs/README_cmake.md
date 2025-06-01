# Building with CMake

## Linux and macOS

[**fheroes2**](README.md) can be built with CMake buildsystem. First, you need to install dependencies.
For Linux and macOS follow to instructions as described above.

Next, you can configure the project with following commands:

```shell
cmake -B build
```

After configuration let's build the project:

```shell
cmake --build build
```

After building, executable can be found in `build` directory.

## Windows / Visual Studio

For Windows you'll need Visual Studio 2019 with C++ support and
[vcpkg package manager](https://vcpkg.readthedocs.io/en/latest/) for dependency management.
Here quick and short instruction for deployment:

```shell
# Clone vcpkg repository. For convenient, let's place it in C:\vcpkg directory, but it can be anywhere.
git clone https://github.com/microsoft/vcpkg.git
# Now initialize manager
.\vcpkg\bootstrap-vcpkg.bat
```

Your vcpkg is ready to install external libraries. The repository contains a
`vcpkg.json` manifest file so dependencies can be installed automatically when
configuring the project in manifest mode. If you still prefer to install them
manually you can run:

```shell
.\vcpkg\vcpkg --triplet x64-windows install sdl2 sdl2-image sdl2-mixer zlib
```

If you plan to develop **fheroes2** with Visual Studio, you may want to integrate
vcpkg with it (requires elevated admin privileges). After the following command
Visual Studio automatically will find all required dependencies:

```shell
.\vcpkg\vcpkg integrate install
```

Now you are ready to configure the project. cd to fheroes2 directory and run `cmake` command (note for `-DCMAKE_TOOLCHAIN_FILE` and
`-DVCPKG_TARGET_TRIPLET` options):

```shell
cmake -B build -DCMAKE_TOOLCHAIN_FILE="C:\vcpkg\scripts\buildsystems\vcpkg.cmake" \
      -DVCPKG_TARGET_TRIPLET=x64-windows -DVCPKG_FEATURE_FLAGS=manifests
```

If you configure the project with `-DENABLE_IMAGE=ON`, vcpkg will automatically
install additional libraries required for that feature from the manifest.

After configuration let's build the project:

```shell
cmake --build build --config Release
```

After building, executable can be found in `build\Release` directory.

## Windows / Visual Studio Code and MinGW64

If you prefer a workflow without Visual Studio, you can build **fheroes2** using
the MinGW‑w64 toolchain and Visual Studio Code. Install a recent MinGW‑w64
distribution (for example via [MSYS2](https://www.msys2.org/)) so that `gcc`,
`g++`, `ar` and `make` are available in your `PATH`. Then clone the vcpkg
repository as described above and bootstrap it with `bootstrap-vcpkg.bat`.

To make CMake automatically locate vcpkg, set the `VCPKG_ROOT` environment
variable to the directory where vcpkg is installed:

```cmd
set VCPKG_ROOT=C:\vcpkg
```

Now configure the project using the MinGW generator and the vcpkg toolchain
file:

```shell
cmake -B build -G "MinGW Makefiles" ^
      -DCMAKE_TOOLCHAIN_FILE=%VCPKG_ROOT%\scripts\buildsystems\vcpkg.cmake ^
      -DVCPKG_TARGET_TRIPLET=x64-mingw-static ^
      -DVCPKG_FEATURE_FLAGS=manifests
```

If you configure with `-DENABLE_IMAGE=ON`, vcpkg will automatically install the
additional image libraries listed in the manifest. After configuration build the
project with:

```shell
cmake --build build
```

The resulting executable will appear in the `build` directory. When using Visual
Studio Code, the **CMake Tools** extension can invoke these commands to provide
an IDE-like experience on Windows 11 without requiring Visual Studio.

## Using Demo Data

CMake project allows to download and install original HoMM II Demo files which used by fheroes2 project.
To do this please add `-DGET_HOMM2_DEMO=ON` to configuration options. For example:

```shell
cmake -B build -DGET_HOMM2_DEMO=ON <some other options>
```
