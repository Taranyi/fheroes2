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

"""Check the real compiler database for opt-in adapter isolation."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--enabled', choices=('ON', 'OFF'), required=True)
    args = parser.parse_args()
    commands = json.loads(args.database.read_text())
    # The excluded fixture executable deliberately defines the macro for its whole
    # target; inspect the shipped game target, not fixture compilation commands.
    game = [c for c in commands if '/src/fheroes2/' in c['file'].replace('\\', '/')
            and 'fheroes2.dir/' in c.get('command', ' '.join(c.get('arguments', []))).replace('\\', '/')]
    if not game:
        raise RuntimeError('No actual game compilation commands found')
    found = set()
    for entry in game:
        path = Path(entry['file'])
        command = entry.get('command', ' '.join(entry.get('arguments', [])))
        defined = 'FHEROES2_ENABLE_PYTHON_ENV' in command
        expected = args.enabled == 'ON' and (path.name == 'fheroes2.cpp' or path.name.startswith('python_env'))
        if defined != expected:
            raise RuntimeError(f'Unexpected Python adapter definition: {path}')
        if defined:
            found.add(path.name)
    if args.enabled == 'ON' and not {'fheroes2.cpp', 'python_env.cpp', 'python_env_standalone.cpp'} <= found:
        raise RuntimeError('Missing required opt-in adapter sources')
    print(f'Validated {len(game)} real game compiler commands: Python={args.enabled}, opted-in sources={len(found)}')


if __name__ == '__main__':
    main()
