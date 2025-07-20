#!/usr/bin/env python3
"""Minimal example showing how to launch fheroes2 from Python."""

import fheroes2

print("fheroes2 version:", fheroes2.get_version())

# Start the game with no command line arguments.
# You can pass parameters as you would on the command line,
# for example: fheroes2.run_game("--map", "test.mp2")
fheroes2.run_game()
