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

"""Save native adventure, hero, castle and battle views as PNG files, without a window."""

import argparse
import os
from pathlib import Path
import struct
import zlib

from fheroes2_env import HeroesSession


def save_png(frame, path):
    """Encode the RGB frame with Python's standard library."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    stride = frame.width * 3
    rows = b"".join(b"\0" + frame.pixels[y * stride:(y + 1) * stride] for y in range(frame.height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", frame.width, frame.height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=root / "build/python-env-views")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with HeroesSession(root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"), timeout=60) as game:
        game.load_save(root / "build/python-env-baseline/fixtures/battles-heroes-day1.sav")
        decision = game.start_session(1)
        for view, params in (("adventure", {"center": (32, 24)}), ("hero", {"hero_id": 52}), ("castle", {"castle_id": 896})):
            before = game.get_state()
            frame = game.render(view=view, **params)
            assert game.get_state() == before
            assert game.get_decision() == decision
            path = args.output_dir / f"{view}.png"
            save_png(frame, path)
            print(view, frame.width, frame.height, path.resolve(), flush=True)
        decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
        assert decision["phase"] == "battle"
        before = game.get_state()
        frame = game.render(view="battle")
        assert game.get_state() == before
        assert game.get_decision() == decision
        path = args.output_dir / "battle.png"
        save_png(frame, path)
        print("battle", frame.width, frame.height, path.resolve(), flush=True)
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
