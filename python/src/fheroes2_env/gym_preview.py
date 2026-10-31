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

"""Small, real Gymnasium adapter for the current adventure_basic engine profile.

This preview controls one hero. The observation is an omniscient RGB camera;
info['state'] contains the full structured world, including every AI player.
Reward is deliberately 0.0: this example does not define the future RL objective.
"""

from contextlib import suppress
from copy import deepcopy
from pathlib import Path

import gymnasium as gym
from gymnasium import spaces
import numpy as np

from .session import EngineError, HeroesSession

ENV_ID = "Fheroes2AdventurePreview-v0"
DIRECTIONS = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
ACTION_NAMES = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west", "end turn")


class AdventurePreviewEnv(gym.Env):
    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 4}

    def __init__(self, *, executable, save, render_mode=None, max_steps=12, hero_id=None, width=640, height=480, fps=4, timeout=60):
        if render_mode not in (None, "human", "rgb_array"):
            raise ValueError("render_mode must be None, human or rgb_array")
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        if any(type(value) is not int or not 32 <= value <= 1024 for value in (width, height)):
            raise ValueError("width and height must be between 32 and 1024")
        if type(fps) is not int or not 0 <= fps <= 60:
            raise ValueError("fps must be between 0 (no delay) and 60")
        self.executable = Path(executable).resolve(strict=True)
        self.save = Path(save).resolve(strict=True)
        self.render_mode = render_mode
        self.max_steps = max_steps
        self.requested_hero_id = hero_id
        self.width, self.height, self.fps, self.timeout = width, height, fps, timeout
        self.action_space = spaces.Discrete(9)
        self.observation_space = spaces.Box(0, 255, shape=(height, width, 3), dtype=np.uint8)
        self._session = None
        self._decision = self._state = self._frame = None
        self._hero_id = None
        self._center = None
        self._steps = 0
        self._needs_reset = True
        self._viewer = None
        self._action_name = "reset"
        self._accepted = True
        self._rejection = None
        self._events = []
        self.window_closed = False

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options:
            raise ValueError("This preview has no reset options; it reloads its configured save")
        if seed is not None:
            self.action_space.seed(seed)
        self._needs_reset = True
        try:
            if self._session is None:
                self._session = HeroesSession(self.executable, timeout=self.timeout)
            episode = self._session.reset(save=self.save, seed=seed)
            self._episode_seed = episode["seed"]
            self._state = self._session.get_state(include_serialized=False)
            humans = [p for p in self._state["players"] if p["is_human"]]
            if len(humans) != 1:
                raise ValueError("The preview needs one human player")
            own = [h for h in self._state["heroes"] if h["active"] and h["id"] in humans[0]["hero_ids"]]
            if self.requested_hero_id is not None:
                own = [h for h in own if h["id"] == self.requested_hero_id]
            if not own:
                raise ValueError("No active owned hero matches this preview")
            self._hero_id = own[0]["id"]
            self._decision = episode["decision"]
            self._steps = 0
            self._action_name, self._accepted, self._rejection, self._events = "reset", True, None, []
            self._capture()
            self._needs_reset = False
            if self.render_mode == "human":
                self.render()
            return self._frame.copy(), self._info()
        except BaseException:
            if self._session is not None:
                with suppress(Exception):
                    self._session.close()
                self._session = None
            raise

    def step(self, action):
        if self._needs_reset:
            raise gym.error.ResetNeeded("Call reset() before stepping or after an episode ends")
        if isinstance(action, (bool, np.bool_)) or not self.action_space.contains(action):
            raise ValueError("action must be an integer from 0 to 8")
        action = int(action)
        self._action_name = ACTION_NAMES[action]
        self._accepted, self._rejection, self._events = True, None, []
        try:
            if action == 8:
                result = self._session.end_turn(token=self._decision["token"])
            else:
                hero = next(h for h in self._state["heroes"] if h["id"] == self._hero_id)
                position = hero["position"]
                if not hero["active"] or position is None:
                    raise EngineError("illegal_action", "The selected hero is no longer active")
                dx, dy = DIRECTIONS[action]
                x, y = position["x"] + dx, position["y"] + dy
                if not 0 <= x < self._state["map"]["width"] or not 0 <= y < self._state["map"]["height"]:
                    raise EngineError("illegal_action", "The target is outside the map")
                result = self._session.move_hero(self._hero_id, x, y, token=self._decision["token"])
            self._decision, self._events = result["decision"], result["events"]
            if self._decision["phase"] == "choice":
                self._needs_reset = True
                raise EngineError("unsupported_choice", "The nine-action preview cannot answer choices; use HeroesSession or reset")
            if self._decision["phase"] == "battle":
                self._needs_reset = True
                raise EngineError("unsupported_battle", "The nine-action preview cannot control battles; use HeroesSession or reset")
        except EngineError as error:
            if error.code not in ("illegal_action", "unsupported_action"):
                # A battle boundary, engine failure or bad protocol is not an episode result/time limit.
                raise
            self._accepted = False
            self._rejection = {"code": error.code, "message": str(error)}
        self._steps += 1
        self._state = self._session.get_state(include_serialized=False)
        self._capture()
        terminated = self._state["phase"] == "terminal"
        truncated = self._steps >= self.max_steps and not terminated
        self._needs_reset = terminated or truncated
        if self.render_mode == "human":
            self.render()
        return self._frame.copy(), 0.0, terminated, truncated, self._info()

    def _capture(self):
        hero = next(h for h in self._state["heroes"] if h["id"] == self._hero_id)
        if hero["position"] is not None:
            self._center = (hero["position"]["x"], hero["position"]["y"])
        frame = self._session.render(width=self.width, height=self.height, center=self._center)
        self._frame = np.frombuffer(frame.pixels, dtype=np.uint8).reshape(frame.shape).copy()

    def _info(self):
        return {"state": deepcopy(self._state), "events": deepcopy(self._events), "hero_id": self._hero_id,
                "episode_step": self._steps, "action_name": self._action_name, "action_accepted": self._accepted,
                "rejection": deepcopy(self._rejection), "seed": self._episode_seed}

    def render(self):
        if self._frame is None:
            raise gym.error.ResetNeeded("Call reset() before rendering")
        if self.render_mode == "rgb_array":
            return self._frame.copy()
        if self.render_mode != "human":
            return None
        if self._viewer is None:
            import pygame

            pygame.display.init()
            pygame.font.init()
            try:
                window = pygame.display.set_mode((max(self.width, 640), self.height + 104))
                pygame.display.set_caption("fheroes2 - Python Gym preview")
                self._viewer = (pygame, window, pygame.font.Font(None, 23), pygame.time.Clock())
            except BaseException:
                pygame.display.quit()
                pygame.font.quit()
                raise
            self.window_closed = False
        pygame, window, font, clock = self._viewer
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                self.window_closed = True
        if self.window_closed:
            return None
        window.fill((22, 25, 31))
        image = pygame.image.frombuffer(self._frame.tobytes(), (self.width, self.height), "RGB")
        window.blit(image, ((window.get_width() - self.width) // 2, 0))
        hero = next(h for h in self._state["heroes"] if h["id"] == self._hero_id)
        player = next(p for p in self._state["players"] if p["id"] == self._decision["player_id"])
        date = self._state["date"]
        lines = (
            f"Day {date['total_days']} | step {self._steps}/{self.max_steps} | {hero['name']} | move points {hero['move_points']}",
            f"Python action: {self._action_name} | {'accepted' if self._accepted else 'rejected: ' + self._rejection['code']}",
            f"Gold {player['funds']['gold']} | wood {player['funds']['wood']} | events: {', '.join(e['type'] for e in self._events) or '-'}",
            "Preview: one hero, 8 directions + end turn | reward=0 | Esc / close window to exit",
        )
        for index, line in enumerate(lines):
            window.blit(font.render(line, True, (233, 237, 242)), (8, self.height + 5 + index * 24))
        pygame.display.flip()
        if self.fps:
            clock.tick(self.fps)
        return None

    def close(self):
        try:
            if self._session is not None:
                self._session.close()
        finally:
            self._session = None
            self._needs_reset = True
            self._frame = None
            if self._viewer is not None:
                pygame = self._viewer[0]
                pygame.display.quit()
                pygame.font.quit()
                self._viewer = None


if ENV_ID not in gym.registry:
    gym.register(ENV_ID, entry_point="fheroes2_env.gym_preview:AdventurePreviewEnv")


def make_preview(**kwargs):
    """Create the registered preview with Gymnasium's usual API/order checks.

    reset(seed=...) seeds both the sampler and the native continuation RNG.
    """
    return gym.make(ENV_ID, **kwargs)
