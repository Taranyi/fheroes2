# Python bindings for fheroes2

This directory contains a minimal Python extension module exposing the `fheroes2` engine.

## Building

Use CMake to configure and build the project. The module is produced alongside the C++ binaries:

```bash
cmake -B build
cmake --build build
```

After compilation the shared library `fheroes2$(python3-config --extension-suffix)` will be located in the `build/python` directory.
You can either copy this file next to your scripts or adjust `PYTHONPATH`.

## Example usage

````python
import fheroes2

print("Version:", fheroes2.get_version())

# Run the game with default arguments
fheroes2.run_game()
````
