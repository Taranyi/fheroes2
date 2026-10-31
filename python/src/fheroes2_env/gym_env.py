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

"""Gymnasium environment for the bounded, native fheroes2 command profile."""

from contextlib import suppress
from copy import deepcopy
from pathlib import Path

import gymnasium as gym
from gymnasium import spaces
import numpy as np

from .session import HeroesSession
from .gym_candidates import candidates, ProfileLimitError
from .gym_observation import encode, observation_space

ENV_ID = "Fheroes2-v0"


class HeroesEnv(gym.Env):
    """One external participant; omniscient structured observations and native actions.

    Action slots are indices into observation['actions']; sample with action_mask.
    Hero movement uses adjacent tiles. All integer quantities of the remaining
    supported command categories are enumerated, without truncating candidates.
    """

    metadata = {"render_modes": ["rgb_array"], "render_fps": 4}

    def __init__(self, *, executable, save=None, map_path=None, player_id=None, difficulty=1, timeout=60,
                 max_steps=1000, max_map_size=144, max_heroes=128, max_castles=128, max_battle_units=32,
                 max_actions=8192, render_mode=None, render_view="auto", width=640, height=480,
                 hero_id=None, castle_id=None, cwd=None, env=None, sphinx_answers=(), max_text_bytes=4096, max_answer_bytes=256):
        if (save is None) == (map_path is None):
            raise ValueError("Specify exactly one save or map_path")
        if render_mode not in (None, "rgb_array") or render_view not in ("auto", "adventure", "battle", "hero", "castle", "world", "oracle"):
            raise ValueError("Unsupported render_mode or render_view")
        for key, value, upper in (("max_steps", max_steps, 1000000000), ("max_map_size", max_map_size, 144),
                                  ("max_heroes", max_heroes, 256), ("max_castles", max_castles, 512),
                                  ("max_battle_units", max_battle_units, 256), ("max_actions", max_actions, 65536)):
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError(f"{key} must be an integer from 1 to {upper}")
        if any(type(v) is not int or not 32 <= v <= 1024 for v in (width, height)):
            raise ValueError("width and height must be integers from 32 to 1024")
        if type(max_text_bytes) is not int or not 1 <= max_text_bytes <= 65536 or type(max_answer_bytes) is not int or not 1 <= max_answer_bytes <= 4096:
            raise ValueError("Invalid text/answer byte capacities")
        if max_actions * max_answer_bytes > 16777216:
            raise ValueError("Action text buffer exceeds the 16 MiB Gym profile limit")
        if isinstance(sphinx_answers, (str, bytes)):
            raise ValueError("sphinx_answers must be a sequence of answer strings")
        try:
            text_answers = tuple(sphinx_answers)
        except TypeError:
            raise ValueError("sphinx_answers must be a sequence of strings") from None
        for answer in text_answers:
            if not isinstance(answer, str) or any(c in answer for c in ("\0", "\r", "\n")) or len(answer.encode("utf-8")) > max_answer_bytes:
                raise ValueError("Sphinx vocabulary contains an invalid or overlong answer")
        self._sphinx_answers = tuple(dict.fromkeys(("", *text_answers)))
        self.executable = Path(executable).resolve(strict=True)
        self._setup = {"save": save} if save is not None else {"map_path": map_path}
        self._setup.update(player_id=player_id, difficulty=difficulty)
        self._process_options = dict(timeout=timeout, cwd=cwd, env=env)
        self.max_steps, self.max_actions = max_steps, max_actions
        self.render_mode, self.render_view = render_mode, render_view
        self.width, self.height, self.hero_id, self.castle_id = width, height, hero_id, castle_id
        self.action_space = spaces.Discrete(max_actions)
        self.observation_space = observation_space(max_map_size, max_heroes, max_castles, max_battle_units, max_actions, max_text_bytes, max_answer_bytes)
        self._session = None
        self._needs_reset = True
        self._state = self._decision = self._observation = None
        self._commands = []
        self._steps = 0

    def reset(self, *, seed=None, options=None):
        if seed is not None:
            HeroesSession._validate_seed(seed)
        if options is not None and (not isinstance(options, dict) or set(options) - {"save", "map_path", "player_id", "difficulty"}):
            raise ValueError("Reset options accept only save, map_path, player_id and difficulty")
        super().reset(seed=seed)
        if seed is not None:
            self.action_space.seed(seed)
        self._needs_reset = True
        setup = dict(self._setup)
        if options:
            if "save" in options:
                setup.pop("map_path", None)
            if "map_path" in options:
                setup.pop("save", None)
            setup.update(options)
        try:
            if self._session is None:
                self._session = HeroesSession(self.executable, **self._process_options)
            episode = self._session.reset(**setup, seed=seed)
            self._episode_seed, self._decision = episode["seed"], episode["decision"]
            self._steps = 0
            self._refresh()
            self._setup = setup
            self._needs_reset = False
            return self._copy_observation(), self._info([])
        except BaseException:
            self.close()
            raise

    def _refresh(self):
        self._state = self._session.get_state(include_serialized=False)
        # Check entity/map limits before any potentially expensive candidate enumeration.
        encode(self.observation_space, self._state, self._decision, [], self._steps, self.max_steps)
        self._commands = candidates(self._session, self._state, self._decision, self.max_actions, text_answers=self._sphinx_answers)
        if self._decision["phase"] != "terminal" and not self._commands:
            raise ProfileLimitError("A live decision has no supported legal commands")
        self._observation = encode(self.observation_space, self._state, self._decision, self._commands, self._steps, self.max_steps)

    def step(self, action):
        if self._needs_reset:
            raise gym.error.ResetNeeded("Call reset before stepping or after an episode/error")
        if isinstance(action, (bool, np.bool_)) or not self.action_space.contains(action):
            raise ValueError("Action must be an integer slot in action_space")
        index = int(action)
        if index >= len(self._commands):
            # Gym permits unmasked action_space.sample(). Padding is an explicit rejected
            # attempt, never silently translated into a native gameplay command.
            self._steps += 1
            self._observation = encode(self.observation_space, self._state, self._decision, self._commands, self._steps, self.max_steps)
            truncated = self._steps >= self.max_steps
            self._needs_reset = truncated
            info = self._info([])
            info.update(action_accepted=False, rejection={"code": "masked_action", "message": "Select a slot with action_mask=1"})
            return self._copy_observation(), 0.0, False, truncated, info
        cmd = self._commands[index]
        try:
            result = self._session.step(cmd["action"], token=self._decision["token"], params=cmd["params"])
            self._decision = result["decision"]
            self._steps += 1
            self._refresh()
            terminated = self._decision["phase"] == "terminal"
            truncated = self._steps >= self.max_steps and not terminated
            reward = 0.0
            if terminated:
                outcome = self._state["game_result"]
                win, loss = bool(outcome & 0x3F), bool(outcome & 0x70F00)
                if win == loss:
                    raise ProfileLimitError(f"Unrecognized terminal result bits: {outcome}")
                reward = 1.0 if win else -1.0
            self._needs_reset = terminated or truncated
            return self._copy_observation(), reward, terminated, truncated, self._info(result["events"])
        except BaseException:
            self._needs_reset = True
            raise

    def _copy_observation(self):
        return {key: value.copy() for key, value in self._observation.items()}

    def _info(self, events):
        return {"state": deepcopy(self._state), "actions": deepcopy(self._commands), "events": deepcopy(events),
                "phase": self._decision["phase"], "player_id": self._decision["player_id"],
                "seed": self._episode_seed, "episode_step": self._steps, "action_accepted": True, "rejection": None}

    def action_masks(self):
        """Boolean mask for mask-aware RL wrappers; returned storage is independent."""
        if self._needs_reset:
            raise gym.error.ResetNeeded("Call reset before requesting an action mask")
        return self._observation["action_mask"].astype(bool)

    def render(self):
        if self.render_mode is None:
            return None
        if self._session is None or self._state is None:
            raise gym.error.ResetNeeded("Call reset before rendering")
        view = self.render_view
        if view == "auto":
            view = "battle" if self._decision["phase"] == "battle" else "adventure"
        params = {"view": view, "width": self.width, "height": self.height}
        if view in ("hero", "castle"):
            key, items = ("hero_id", self._state["heroes"]) if view == "hero" else ("castle_id", self._state["castles"])
            selected = self.hero_id if view == "hero" else self.castle_id
            if selected is None:
                own = [item for item in items if item["owner"] == self._decision["player_id"] and item.get("active", True)]
                if not own:
                    raise ProfileLimitError(f"No owned entity available for {view} rendering")
                selected = own[0]["id"]
            params[key] = selected
        frame = self._session.render(**params)
        return np.frombuffer(frame.pixels, dtype=np.uint8).reshape(frame.shape).copy()

    def close(self):
        try:
            if self._session is not None:
                with suppress(Exception):
                    self._session.close()
        finally:
            self._session = None
            self._needs_reset = True
            self._state = self._decision = self._observation = None
            self._commands = []


if ENV_ID not in gym.registry:
    gym.register(ENV_ID, entry_point="fheroes2_env.gym_env:HeroesEnv")


def make_env(**kwargs):
    return gym.make(ENV_ID, **kwargs)
