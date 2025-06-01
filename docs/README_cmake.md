# Building with CMake

## Linux and macOS

[**fheroes2**](README.md) can be built with the CMake build system. First, you need to install dependencies.
For Linux and macOS follow the instructions as described above.

Next, you can configure the project with the following command:

```shell
cmake -B build
```

After configuration let's build the project:

```shell
cmake --build build
```

After building, the executable can be found in the `build` directory.

## Windows / Visual Studio

For Windows you'll need Visual Studio 2019 with C++ support and
[vcpkg package manager](https://vcpkg.readthedocs.io/en/latest/) for dependency management.
Here is a quick and short instruction for deployment:

```shell
# Clone vcpkg repository. For convenience, let's place it in C:\vcpkg directory, but it can be anywhere.
git clone https://github.com/microsoft/vcpkg.git
# Now initialize manager
.\vcpkg\bootstrap-vcpkg.bat
```

Your vcpkg is ready to install external libraries. Assuming you use an x64 system, let's install all needed dependencies:

```shell
.\vcpkg\vcpkg --triplet x64-windows install sdl2 sdl2-image sdl2-mixer zlib
```

If you plan to develop fheroes2 with Visual Studio, you may want to integrate vcpkg with it (requires elevated admin privileges).
After running the following command Visual Studio will automatically find all required dependencies:

```shell
.\vcpkg\vcpkg integrate install
```

Now you are ready to configure the project. Change to the fheroes2 directory and run the `cmake` command (note the `-DCMAKE_TOOLCHAIN_FILE` and
`-DVCPKG_TARGET_TRIPLET` options):

```shell
cmake -B build -DCMAKE_TOOLCHAIN_FILE="C:\vcpkg\scripts\buildsystems\vcpkg.cmake" -DVCPKG_TARGET_TRIPLET=x64-windows
```

After configuration let's build the project:

```shell
cmake --build build --config Release
```

After building, the executable can be found in the `build\Release` directory.

## Using Demo Data

The CMake project allows you to download and install the original HoMM II Demo files which are used by the fheroes2 project.
To do this, please add `-DGET_HOMM2_DEMO=ON` to the configuration options. For example:

```shell
cmake -B build -DGET_HOMM2_DEMO=ON <some other options>
```
