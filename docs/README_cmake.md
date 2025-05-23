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


## Windows / Visual Studio Code

Visual Studio Code can be used instead of the full Visual Studio IDE to build
the project on Windows 11. Install the **CMake Tools** extension and follow the
steps below:

1. Install the dependencies using [vcpkg](https://vcpkg.readthedocs.io/en/latest/)
   as described in the section above.
2. Open the `fheroes2` folder in Visual Studio Code.
3. Press `Ctrl+Shift+P` and run **CMake: Configure**. When prompted, provide
   `-DCMAKE_TOOLCHAIN_FILE=C:\vcpkg\scripts\buildsystems\vcpkg.cmake` and
   `-DVCPKG_TARGET_TRIPLET=x64-windows` as configure arguments.
4. After configuration run **CMake: Build** to compile the project.

The resulting executable will be placed in the selected build configuration
inside the `build` directory.

## Using Demo Data

CMake project allows to download and install original HoMM II Demo files which used by fheroes2 project.
To do this please add `-DGET_HOMM2_DEMO=ON` to configuration options. For example:

```shell
cmake -B build -DGET_HOMM2_DEMO=ON <some other options>
```
