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

"""An RGB frame independent of NumPy, SDL and the engine's temporary output file."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RGBFrame:
    width: int
    height: int
    pixels: bytes = field(repr=False)
    center: tuple[int, int]
    state_version: int

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.height, self.width, 3

    def to_numpy(self):
        """Return a read-only uint8 HWC array; requires NumPy installed by the caller."""
        import numpy as np

        return np.frombuffer(self.pixels, dtype=np.uint8).reshape(self.shape)

    def save_ppm(self, path: str | Path) -> None:
        """Write a binary PPM image using only the Python standard library."""
        Path(path).write_bytes(f"P6\n{self.width} {self.height}\n255\n".encode("ascii") + self.pixels)
