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

"""Small standalone-battle Gym profile; world snapshots remain explicitly available."""

from gymnasium import spaces

from .gym_env import HeroesEnv, _json_copy
from .gym_candidates import candidates, ProfileLimitError
from .gym_observation import encode

BATTLE_KEYS = ('battle', 'battle_units', 'battle_unit_mask', 'battle_effects', 'battle_board', 'battle_commanders', 'actions', 'action_mask')


class BattleEnv(HeroesEnv):
    """Same native battle actions/rewards, eight numeric fields and small info.

    No world-state RPC during live decisions. Full omniscient world state is
    available on demand through world_snapshot(). Process reuse is opt-in here too.
    """
    def __init__(self, *, executable, battle_config, max_steps=160, max_battle_units=12, max_actions=512,
                 reuse_process=False, render_mode=None, width=640, height=480, timeout=60, cwd=None, env=None):
        super().__init__(executable=executable, battle_config=battle_config, max_steps=max_steps,
                         max_map_size=2, max_heroes=1, max_castles=1, max_battle_units=max_battle_units,
                         max_actions=max_actions, max_text_bytes=1, max_answer_bytes=1, reuse_process=reuse_process,
                         render_mode=render_mode, render_view='battle', width=width, height=height, timeout=timeout, cwd=cwd, env=env)
        self._encoding_space = self.observation_space
        self.observation_space = spaces.Dict({key: self._encoding_space[key] for key in BATTLE_KEYS})

    def _refresh(self):
        if self._decision['phase'] not in ('battle', 'terminal'):
            raise ProfileLimitError('BattleEnv supports standalone battle decisions only')
        terminal = self._decision['phase'] == 'terminal'
        world = self._session.get_state(include_serialized=False) if terminal else None
        # Private encoder scaffold, never exposed as a world snapshot.
        self._state = {'map': {'width': 2, 'height': 2, 'seed': 0, 'tiles': []},
                       'date': {'total_days': 1, 'total_weeks': 1, 'month': 1},
                       'current_player': self._decision['player_id'], 'players': [], 'heroes': [], 'castles': [],
                       'game_result': world['game_result'] if terminal else 0,
                       'standalone_battle': {'result': world['standalone_battle']['result'] if terminal else None}}
        self._commands = candidates(self._session, self._state, self._decision, self.max_actions)
        if not terminal and not self._commands:
            raise ProfileLimitError('A live battle has no native legal commands')
        self._observation = self._encode_current()

    def _encode_current(self):
        encoded = encode(self._encoding_space, self._state, self._decision, self._commands, self._steps, self.max_steps)
        return {key: encoded[key] for key in BATTLE_KEYS}

    def _info(self, events):
        return {'profile': 'battle', 'phase': self._decision['phase'], 'player_id': self._decision['player_id'],
                'seed': self._episode_seed, 'episode_step': self._steps, 'action_accepted': True, 'rejection': None,
                'events': _json_copy(events), 'battle_result': _json_copy(self._state['standalone_battle']['result'])}

    def world_snapshot(self):
        """Fetch full native world/AI state explicitly; never return the encoder scaffold."""
        if self._session is None:
            raise RuntimeError('Call reset before requesting a world snapshot')
        return self._session.get_state(include_serialized=False)
