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

"""One isolated engine process and a bounded, synchronous JSON-lines connection."""

from __future__ import annotations

import contextlib
import json
import math
import os
from pathlib import Path
import queue
import secrets
import subprocess
import tempfile
import threading
from typing import Any, Mapping

from .frame import RGBFrame

API_VERSION = 1
MAX_REQUEST_BYTES = 65536
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


class EngineError(RuntimeError):
    """The engine rejected a request, but the connection remains usable."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class ProtocolError(RuntimeError):
    """The peer did not follow the protocol; its process has been stopped."""


class EngineProcessError(RuntimeError):
    """The engine stopped or its pipes failed unexpectedly."""


class EngineTimeoutError(TimeoutError):
    """The engine missed a deadline and its process has been stopped."""


def _exchange_worker(process, outgoing, incoming):
    # This thread owns both pipes. Even a blocked write is covered by the caller's deadline.
    while True:
        payload = outgoing.get()
        if payload is None:
            return
        try:
            process.stdin.write(payload)
            process.stdin.flush()
            line = process.stdout.readline(MAX_RESPONSE_BYTES + 1)
            if not line:
                raise EngineProcessError("Engine closed stdout before replying.")
            if len(line) > MAX_RESPONSE_BYTES or not line.endswith(b"\n"):
                raise ProtocolError("Engine response is oversized or lacks a newline.")
            incoming.put(line)
        except (OSError, ValueError, RuntimeError) as error:
            incoming.put(error)
            return


class HeroesSession:
    """Start ``fheroes2 --python-env`` and complete its protocol handshake.

    Use as a context manager, or call close(). Saves can be loaded and inspected,
    including all AI players, plus the limited native adventure action profile.
    """

    def __init__(
        self,
        executable: str | os.PathLike[str],
        *,
        timeout: float = 5.0,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
    ):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        executable_path = Path(executable).resolve(strict=True)
        if not executable_path.is_file():
            raise ValueError("executable must name a file")
        self._timeout = timeout
        self._lock = threading.RLock()
        self._executable = executable_path
        self._cwd = cwd
        self._env = dict(env) if env is not None else None
        self._reset_source = None
        self._launch()

    def _launch(self):
        executable_path, cwd, env = self._executable, self._cwd, self._env
        self._closed = False
        self._next_id = 1
        self._outgoing = queue.Queue()
        self._incoming = queue.Queue()
        # A file avoids stderr pipe deadlocks, including during startup failures.
        self._diagnostics = tempfile.TemporaryFile()
        try:
            self._process = subprocess.Popen(
                [str(executable_path), "--python-env"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._diagnostics,
                cwd=cwd if cwd is not None else executable_path.parent,
                env=dict(env) if env is not None else None,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except BaseException:
            self._diagnostics.close()
            raise
        self._worker = threading.Thread(
            target=_exchange_worker,
            args=(self._process, self._outgoing, self._incoming),
            name=f"fheroes2-transport-{self._process.pid}",
            daemon=True,
        )
        try:
            self._worker.start()
            self.info = self.hello()
            if (
                self.info.get("engine") != "fheroes2"
                or self.info.get("mode") != "bootstrap"
                or not isinstance(self.info.get("engine_version"), str)
                or not isinstance(self.info.get("capabilities"), dict)
            ):
                raise ProtocolError("Unexpected engine handshake.")
        except BaseException:
            self._dispose()
            raise

    @property
    def pid(self) -> int:
        return self._process.pid

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def returncode(self) -> int | None:
        return self._process.poll()

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Exchange one request. Engine rejections do not close the session."""
        with self._lock:
            if self._closed:
                raise EngineProcessError("Session is closed.")
            if not isinstance(method, str) or (params is not None and not isinstance(params, dict)):
                raise TypeError("method must be a string and params must be a dictionary")
            if self._next_id > 0xFFFFFFFF:
                raise ProtocolError("Request id limit reached; start a new session.")
            request_id = self._next_id
            payload = json.dumps(
                {"api_version": API_VERSION, "id": request_id, "method": method, "params": params if params is not None else {}},
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(payload) > MAX_REQUEST_BYTES:
                raise ValueError("Request exceeds 65536 bytes.")
            self._next_id += 1
            self._outgoing.put(payload + b"\n")
            try:
                reply = self._incoming.get(timeout=self._timeout)
            except queue.Empty:
                self._dispose()
                raise EngineTimeoutError(f"Engine did not reply within {self._timeout:g} seconds.") from None
            if isinstance(reply, BaseException):
                self._dispose()
                if isinstance(reply, (ProtocolError, EngineProcessError)):
                    raise reply
                raise EngineProcessError("Engine communication failed.") from reply
            try:
                response = json.loads(reply)
                if (
                    not isinstance(response, dict)
                    or type(response.get("api_version")) is not int
                    or response["api_version"] != API_VERSION
                    or type(response.get("id")) is not int
                    or response["id"] != request_id
                    or ("result" in response) == ("error" in response)
                ):
                    raise ProtocolError("Invalid response envelope or mismatched request id/version.")
                if "error" in response:
                    error = response["error"]
                    if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
                        raise ProtocolError("Invalid engine error response.")
                    raise EngineError(error["code"], error["message"])
                if not isinstance(response["result"], dict):
                    raise ProtocolError("Expected an object result.")
                return response["result"]
            except EngineError:
                raise
            except (ValueError, UnicodeError, RecursionError, ProtocolError) as error:
                self._dispose()
                if isinstance(error, ProtocolError):
                    raise
                raise ProtocolError("Engine returned invalid JSON.") from error

    def hello(self) -> dict[str, Any]:
        return self.request("hello")

    def capabilities(self) -> dict[str, Any]:
        return self.request("capabilities")

    def load_save(self, path: str | os.PathLike[str], *, seed: int | None = None) -> dict[str, Any]:
        """Load a trusted standard-game save without advancing turns.

        The save is read-only. A failed load clears the current loaded world;
        another valid save can then be loaded in the same session.
        An optional seed controls future main-thread draws, preserving the saved
        map seed. Use reset for isolation and replay from a fresh engine process.
        """
        params = {"path": str(Path(path).resolve())}
        if seed is not None:
            self._validate_seed(seed)
            params["seed"] = seed
        return self.request("load_save", params)

    @staticmethod
    def _validate_seed(seed):
        if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
            raise ValueError("seed must be an unsigned 32-bit integer")

    def new_game(self, path: str | os.PathLike[str], *, seed: int, player_id: int = 1, difficulty: int = 1) -> dict[str, Any]:
        """Initialize a standard MP2/MX2/FH2M map using native seeded setup rules."""
        self._validate_seed(seed)
        if type(player_id) is not int or player_id not in (1, 2, 4, 8, 16, 32):
            raise ValueError("player_id must be one player color bit")
        if type(difficulty) is not int or not 0 <= difficulty <= 4:
            raise ValueError("difficulty must be an integer from 0 to 4")
        return self.request("new_game", {"path": str(Path(path).resolve()), "seed": seed, "player_id": player_id, "difficulty": difficulty})

    def reset(self, *, save=None, map_path=None, seed: int | None = None, player_id: int | None = None, difficulty: int | None = None) -> dict[str, Any]:
        """Restart the engine, initialize an episode and return its decision and effective seed.

        Specify exactly one source on first use; subsequent calls reuse that source
        and player/difficulty configuration. A missing seed generates a fresh uint32.
        Reset also recovers closed, crashed and timed-out sessions.
        """
        if save is not None and map_path is not None:
            raise ValueError("Specify save or map_path, not both")
        if seed is not None:
            self._validate_seed(seed)
        if player_id is not None and (type(player_id) is not int or player_id not in (1, 2, 4, 8, 16, 32)):
            raise ValueError("player_id must be one player color bit")
        if difficulty is not None and (type(difficulty) is not int or not 0 <= difficulty <= 4):
            raise ValueError("difficulty must be an integer from 0 to 4")
        with self._lock:
            if save is None and map_path is None:
                if self._reset_source is None:
                    raise ValueError("First reset requires save or map_path")
                kind, path, configured_player, configured_difficulty = self._reset_source
                if player_id is None:
                    player_id = configured_player
                if difficulty is None:
                    difficulty = configured_difficulty
            else:
                kind = "save" if save is not None else "map"
                path = str(Path(save if save is not None else map_path).resolve())
            if difficulty is None:
                difficulty = 1
            effective_seed = secrets.randbits(32) if seed is None else seed
            self._dispose()
            try:
                self._launch()
                if kind == "save":
                    loaded = self.load_save(path, seed=effective_seed)
                    if player_id is None:
                        humans = [p["id"] for p in self.get_state(include_serialized=False)["players"] if p["is_human"] and p["in_play"]]
                        if len(humans) != 1:
                            raise ValueError("The saved-game profile requires exactly one live human-rule player")
                        player_id = humans[0]
                else:
                    if player_id is None:
                        player_id = 1
                    loaded = self.new_game(path, seed=effective_seed, player_id=player_id, difficulty=difficulty)
                decision = self.start_session(player_id)
                self._reset_source = (kind, path, player_id, difficulty)
                return {"seed": effective_seed, "source": kind, "loaded": loaded, "decision": decision}
            except BaseException:
                self._dispose()
                raise

    def get_state(self, *, include_serialized: bool = True) -> dict[str, Any]:
        """Return the omniscient world, including AI and fog-hidden objects.

        The optional hex payload preserves save fields not projected into JSON.
        This is not a visibility-filtered observation for a learning agent.
        """
        if type(include_serialized) is not bool:
            raise TypeError("include_serialized must be a boolean")
        return self.request("get_state", {"include_serialized": include_serialized})

    def start_session(self, player_id: int) -> dict[str, Any]:
        """Wait at the loaded human player's adventure decision, without advancing time."""
        if type(player_id) is not int or player_id not in (1, 2, 4, 8, 16, 32):
            raise ValueError("player_id must be one player color bit")
        return self.request("start_session", {"player_id": player_id})

    def get_decision(self) -> dict[str, Any]:
        """Inspect the pending decision and its explicit action token."""
        return self.request("get_decision")

    def check_actions(self, actions, *, token: Mapping[str, Any]) -> list[bool]:
        """Validate up to 128 adventure command candidates without executing them."""
        actions = list(actions)
        result = self.request("check_actions", {"actions": actions, "token": dict(token)})
        valid = result.get("valid")
        if not isinstance(valid, list) or len(valid) != len(actions) or any(type(value) is not bool for value in valid):
            self._dispose()
            raise ProtocolError("Invalid native action validation result")
        return valid

    def runtime_info(self) -> dict[str, Any]:
        """Report the actual presentation subsystem state of this process."""
        return self.request("runtime_info")

    def render(self, *, view: str = "adventure", width: int = 640, height: int = 480, center: tuple[int, int] | None = None,
               hero_id: int | None = None, castle_id: int | None = None) -> RGBFrame:
        """Render an omniscient adventure, active battle, hero or castle image.

        Hero/castle views require their entity ID. No game time passes.
        Pixels use HWC order, three uint8 channels, with no row padding.
        """
        if type(width) is not int or type(height) is not int or not 32 <= width <= 1024 or not 32 <= height <= 1024:
            raise ValueError("width and height must be integers between 32 and 1024")
        if not isinstance(view, str):
            raise TypeError("view must be a string")
        params = {"view": view, "width": width, "height": height}
        for name, value in (("hero_id", hero_id), ("castle_id", castle_id)):
            if value is not None:
                if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                    raise ValueError(f"{name} must be an unsigned 32-bit integer")
                params[name] = value
        if center is not None:
            if not isinstance(center, (tuple, list)) or len(center) != 2 or any(type(value) is not int or value < 0 for value in center):
                raise ValueError("center must be a pair of nonnegative tile coordinates")
            params.update(center_x=center[0], center_y=center[1])
        with self._lock, tempfile.TemporaryDirectory(prefix="fheroes2-frame-") as directory:
            path = Path(directory) / "frame.rgb"
            params["output_path"] = str(path)
            result = self.request("render", params)
            try:
                if (
                    result.get("view") != view or result.get("format") != "rgb8" or result.get("perspective") != "omniscient"
                    or type(result.get("width")) is not int or result["width"] != width
                    or type(result.get("height")) is not int or result["height"] != height
                    or type(result.get("channels")) is not int or result["channels"] != 3
                    or type(result.get("byte_count")) is not int or result["byte_count"] != width * height * 3
                    or result.get("output_path") != str(path)
                    or type(result.get("state_version")) is not int
                    or not isinstance(result.get("center"), dict)
                    or any(type(result["center"].get(key)) is not int for key in ("x", "y"))
                    or path.stat().st_size != width * height * 3
                ):
                    raise ProtocolError("Invalid RGB frame metadata or size")
                with path.open("rb") as source:
                    pixels = source.read(width * height * 3 + 1)
                if len(pixels) != width * height * 3:
                    raise ProtocolError("RGB frame size changed while reading")
                return RGBFrame(width, height, pixels, (result["center"]["x"], result["center"]["y"]), result["state_version"])
            except (OSError, ProtocolError) as error:
                self._dispose()
                raise ProtocolError("Engine returned an invalid RGB frame") from error

    def step(self, action: str, *, token: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Submit a token-checked gameplay command or session.stop.

        Pass the token returned by start_session/get_decision explicitly; the
        client must never silently replace a stale token with the latest one.
        """
        if not isinstance(action, str) or not isinstance(token, Mapping) or (params is not None and not isinstance(params, Mapping)):
            raise TypeError("Expected an action string, token mapping and optional params mapping")
        return self.request("step", {"action": action, "token": dict(token), "params": dict(params) if params is not None else {}})

    def move_hero(self, hero_id: int, x: int, y: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Follow an affordable land route using the engine's native movement/pickup rules."""
        return self.step("hero.move", token=token, params={"hero_id": hero_id, "x": x, "y": y})

    def end_turn(self, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Run the remaining built-in AI turns and return at the next human decision."""
        return self.step("turn.end", token=token)

    def get_castle_options(self, castle_id: int) -> dict[str, Any]:
        """Read native building/recruitment conditions without modifying the world."""
        return self.request("get_castle_options", {"castle_id": castle_id})

    def build_castle(self, castle_id: int, building_id: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Buy one building using native prerequisites, prices and the daily limit."""
        return self.step("castle.build", token=token, params={"castle_id": castle_id, "building_id": building_id})

    def recruit_castle(self, castle_id: int, dwelling_id: int, count: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Recruit exactly count creatures of the base dwelling's current native tier."""
        return self.step("castle.recruit", token=token, params={"castle_id": castle_id, "dwelling_id": dwelling_id, "count": count})

    def refresh_hero_offers(self, castle_id: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Explicitly run the native lazy hero-offer refresh; this can change world/RNG state."""
        return self.step("castle.refresh_heroes", token=token, params={"castle_id": castle_id})

    def hire_hero(self, castle_id: int, hero_id: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Buy one currently offered hero through the native castle recruitment path."""
        return self.step("castle.hire", token=token, params={"castle_id": castle_id, "hero_id": hero_id})

    def trade_resources(self, castle_id: int, resource_from: int, resource_to: int, lots: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Trade an exact number of native lots at the owner's kingdom marketplace rate."""
        return self.step("market.trade", token=token, params={"castle_id": castle_id, "resource_from": resource_from, "resource_to": resource_to, "lots": lots})

    def meet_heroes(self, hero_id: int, other_hero_id: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Establish a land meeting via native adjacent movement, including its movement cost."""
        return self.step("hero.meet", token=token, params={"hero_id": hero_id, "other_hero_id": other_hero_id})

    def transfer_troops(self, source: Mapping[str, Any], target: Mapping[str, Any], count: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Move/split/merge exactly count units between {kind, id, slot} endpoints."""
        return self.step("army.transfer", token=token, params={"source": dict(source), "target": dict(target), "count": count})

    def swap_troops(self, source: Mapping[str, Any], target: Mapping[str, Any], *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Swap two accessible army slots without emptying a hero's army."""
        return self.step("army.swap", token=token, params={"source": dict(source), "target": dict(target)})

    def transfer_artifact(self, source: Mapping[str, Any], target: Mapping[str, Any], *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Move a non-book artifact to an empty {hero_id, slot} endpoint."""
        return self.step("artifact.transfer", token=token, params={"source": dict(source), "target": dict(target)})

    def swap_artifacts(self, source: Mapping[str, Any], target: Mapping[str, Any], *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Exchange artifact slots using native book protection, set assembly and scouting effects."""
        return self.step("artifact.swap", token=token, params={"source": dict(source), "target": dict(target)})

    def end_meeting(self, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Finish the encounter and apply native net-gain scouting effects once."""
        return self.step("hero.end_meeting", token=token)

    def get_army_options(self, kind: str, entity_id: int) -> dict[str, Any]:
        """Read native upgrade costs/conditions and stack-dismissal availability for any side."""
        return self.request("get_army_options", {"kind": kind, "id": entity_id})

    def upgrade_troop(self, source: Mapping[str, Any], *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Upgrade the entire specified stack at its native castle facility and price."""
        return self.step("army.upgrade", token=token, params={"source": dict(source)})

    def answer_choice(self, choice_id: int, value: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Resume the suspended native action with an exact offered value."""
        return self.step("choice.answer", token=token, params={"choice_id": choice_id, "value": value})

    def cast_spell(self, hero_id: int, spell_id: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Cast an adventure spell supported by the current capability profile."""
        return self.step("hero.cast", token=token, params={"hero_id": hero_id, "spell_id": spell_id})

    def battle_action(self, action_id: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Execute a candidate from the current battle decision's actions list."""
        return self.step("battle.act", token=token, params={"action_id": action_id})

    def dismiss_troop(self, source: Mapping[str, Any], *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Dismiss an entire stack, preserving the hero's last required stack."""
        return self.step("army.dismiss", token=token, params={"source": dict(source)})

    def dismiss_hero(self, hero_id: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Voluntarily dismiss an owned hero outside castles, subject to scenario restrictions."""
        return self.step("hero.dismiss", token=token, params={"hero_id": hero_id})

    def buy_spell_book(self, hero_id: int, *, token: Mapping[str, Any]) -> dict[str, Any]:
        """Buy a book and learn native mage-guild spells at the hero's owned castle."""
        return self.step("hero.buy_spell_book", token=token, params={"hero_id": hero_id})

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                result = self.request("close")
                if result.get("closed") is not True:
                    raise ProtocolError("Engine did not acknowledge close.")
                try:
                    exit_code = self._process.wait(timeout=self._timeout)
                except subprocess.TimeoutExpired:
                    raise EngineTimeoutError("Engine acknowledged close but did not exit.") from None
                if exit_code != 0:
                    raise EngineProcessError(f"Engine exited with code {exit_code}.")
            finally:
                self._dispose()

    def _dispose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._process.poll() is None:
            self._process.kill()
        self._process.wait(timeout=5)
        self._outgoing.put(None)
        if self._worker.ident is not None:
            self._worker.join(timeout=5)
        for pipe in (self._process.stdin, self._process.stdout):
            with contextlib.suppress(OSError):
                pipe.close()
        self._diagnostics.close()

    def __enter__(self) -> HeroesSession:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.close()
        else:
            with contextlib.suppress(Exception):
                self.close()
