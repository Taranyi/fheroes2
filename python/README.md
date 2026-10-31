# fheroes2 Python connection

Start with the [usage guide, support matrix and measured acceptance results](../docs/PYTHON_ENV_GUIDE.md).
The current single-external-side profile is verified; per-side controllers, multi-agent and AI-only execution remain task 4/A.

Implementation steps 2–6 provide real save loading/state inspection, external decisions, offscreen adventure rendering,
native land movement/resource pickup and turn progression through the built-in AI. These work without video/audio
initialization. Selected native choices, two adventure spells and native battles work through the session API.
Step 11 adds offscreen hero, castle and live battle snapshots, including AI-owned heroes and castles.
Step 13 provides the structured `Fheroes2-v0` Gym adapter below, including native choices and battles.
Further engine actions remain outside the documented profile; the older visual preview is also retained.

Participant-control requirement (2026-10-29): the final session must support a built-in AI or Python controller per side,
including AI-only simulation and multiple external agents with no manual player. Currently the state is already omniscient
for every side, but external control is limited to one side marked human in the save. That side can already be driven entirely
by a Python policy; the human marker is an engine limitation, not a requirement for keyboard input.
See the [implementation plan's participant requirements](../docs/PYTHON_ENV_IMPLEMENTATION_PLAN.md), task 4/A,
for the required broader control model. It remains unimplemented after the profile acceptance and measurements in step 14.

Castle inspection, building and exact-count recruitment are also available through the native engine:

```powershell
uv run --project python python python/examples/castle.py
```

Use `game.get_castle_options(castle_id)`, `game.build_castle(castle_id, building_id, token=...)` and
`game.recruit_castle(castle_id, dwelling_id, count, token=...)`. Both actions return a fresh decision token.
The read-only options include prices, prerequisites/statuses, available creatures, affordable quantities and army destinations.
Queries include opponents' castles; actions require ownership by the waiting player. Recruitment is exact, with no silent clamping.
Hero hiring and marketplace trading also work, with a [runnable walkthrough](examples/economy.py):

```powershell
uv run --project python python python/examples/economy.py
```

`get_castle_options` includes cached `hero_hiring` offers/conditions and `market` rates/limits for all sides.
Use `refresh_hero_offers(castle_id, token=...)` for the native lazy offer update, then
`hire_hero(castle_id, hero_id, token=...)` for a currently offered hero in an empty, owned castle visitor slot.
Refreshing is an explicit action because it can change native RNG/state; read-only queries never generate offers.
Use `trade_resources(castle_id, resource_from, resource_to, lots, token=...)` for exact quoted marketplace lots;
rates use all marketplaces owned by that castle's kingdom. The UI and Python share checked quote/execution functions.
See [the castle/economy API and limits](../docs/PYTHON_ENV_CASTLE.md). Ship purchases are still pending;
the nine-action Gym preview remains unchanged.

## Army management

Army management is also available through `HeroesSession`:

```powershell
uv run --project python python python/examples/army.py
```

Use `transfer_troops(source, target, count, token=...)` for exact move/split/merge and
`swap_troops(source, target, token=...)` for slot swaps. Endpoints are `{kind: "hero" | "castle", id, slot}` with slots `0..4`.
Between two heroes, first establish a native adjacent encounter with `meet_heroes(hero_id, other_hero_id, token=...)`;
this charges the real movement cost once. Hero/garrison transfers require the actual castle visitor.
Ownership, last-hero-unit protection and count limits are enforced in C++; no remote transfers are allowed.
See [the army contract and limits](../docs/PYTHON_ENV_ARMY.md).

Artifact operations also work: `transfer_artifact(source, target, token=...)` moves to an empty slot;
`swap_artifacts(source, target, token=...)` swaps occupied or empty slots. Endpoints are `{hero_id, slot}` with slots `0..13`.
Books cannot be moved/traded. Between heroes the same paid `meet_heroes` encounter is required; local reordering needs no meeting.
Scroll spell data and native set assembly are preserved. `end_meeting(token=...)` applies net scouting gains on close,
matching the native meeting window; other successful gameplay actions and `session.stop` close an open encounter automatically.
The full state now includes artifact `spell_id` (0 for no granted spell) and each hero's `scouting_distance`, for AI sides too.

The original local saves have no movable artifact on the controlled side. Prepare separate native test saves for the walkthrough:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python python python/examples/artifacts.py
```

The builder is an explicit optional test target, absent from disabled/default game builds and the production protocol.
See [the artifact API, fixture preparation and limits](../docs/PYTHON_ENV_ARTIFACTS.md).

Native upgrades, dismissals and spell-book purchases are available too:

```powershell
uv run --project python python python/examples/hero_operations.py
```

`get_army_options(kind, entity_id)` reads five slots, whole-stack upgrade prices and current upgrade/dismiss conditions,
including AI armies. `upgrade_troop(source, token=...)` and `dismiss_troop(source, token=...)` act on an owned army endpoint.
`dismiss_hero(hero_id, token=...)` respects castle/scenario restrictions; `buy_spell_book(hero_id, token=...)` requires an owned
castle visitor, mage guild, funds and free artifact space. The full state includes book/purchase/dismissal flags for every hero.
See [the API, native side effects and limits](../docs/PYTHON_ENV_HERO_OPERATIONS.md). The Gym preview still exposes nine actions.

## Native choices and adventure spells

Prepare the native local fixtures and run the treasure/level-up walkthrough:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python python python/examples/choices.py
```

An action can return `decision["phase"] == "choice"`. Read `pending_choice`, then call
`answer_choice(choice_id, value, token=decision["token"])` with an exact offered integer or a quantity inside its bounds.
The original C++ action continues and can return another choice before completing. State, AI data and rendering remain readable.
`session.stop` during a choice rolls back the whole suspended action; close/reset can also unwind it.
The supported profile includes treasure gold/experience, secondary skills, neutral joining/pursuit, and lamp/Wagon Camp recruitment.
`cast_spell(hero_id, spell_id, token=...)` supports Identify Hero and Visions with native costs/conditions.
All heroes expose `adventure_spell_options`; player state exposes `identify_hero` and `vision_monster_indices`.
See [choice protocol, partial state, rollback and spell limits](../docs/PYTHON_ENV_CHOICES.md).
The nine-action Gym preview reports `unsupported_choice` and requires reset at a choice boundary; it never chooses on the agent's behalf.

## Native adventure battles

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python python python/examples/battle.py
uv run --project python python python/examples/battle.py --spells
```

Movement, a refused monster offer or an AI attack during `turn.end` can return `phase="battle"`.
Read `decision["battle"]`: both forces, the 99-cell board, current unit/round, commander mana and supported legal `actions`.
Select a candidate and call `battle_action(action["action_id"], token=decision["token"])` until the next battle/choice/adventure/terminal decision.
The same native arena handles movement, melee directions, shooting, a basic targeted spell profile, retreat and surrender.
Native casualties, experience, necromancy and castle capture persist back to the adventure world; level-up choices remain external.
During combat, `battle.units` is the live force; world hero armies are synchronized by the engine when battle ends.
The nine-action Gym preview raises `unsupported_battle` at an external combat decision and requires reset.
See [the battle contract, fixtures, spell coverage and limits](../docs/PYTHON_ENV_BATTLE.md).

## Runnable Gymnasium preview

From the repository root, after building the enabled engine and preparing the local reference saves:

```powershell
uv run --project python --extra viewer python python/examples/gym_loop.py
```

This opens a Python viewer of the real engine's adventure image. Roxana walks out and back on the recorded
The Other Side day-1 save; end-turn runs the native AI, then the 12-action episode limit triggers a reset.
The default demonstration runs 120 actions. Esc or closing the window exits. No mouse/keyboard control of the
original game is involved. The C++ engine remains headless; only the optional Python viewer opens a window.

For the random action loop, including completely windowless operation:

```powershell
uv run --project python --extra viewer python python/examples/gym_loop.py --policy random
uv run --project python --extra gym python python/examples/gym_loop.py --headless --policy random --steps 10000
```

The adapter and example are [gym_preview.py](src/fheroes2_env/gym_preview.py) and
[gym_loop.py](examples/gym_loop.py). The essential calling pattern is:

```python
from fheroes2_env.gym_preview import make_preview

with make_preview(executable="fheroes2.exe",
                  save="build/python-env-baseline/fixtures/other-side-day1.sav",
                  render_mode=None, max_steps=12) as env:
    obs, info = env.reset(seed=123)
    for _ in range(10000):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            obs, info = env.reset()
```

* `obs`: omniscient adventure RGB image, NumPy `uint8`, shape `(480, 640, 3)` by default. Camera follows one owned hero.
  `width` and `height` configure it at construction. This image is requested even with `render_mode=None`.
* `info["state"]`: the full structured omniscient world, including opponents, heroes, castles, resources and hidden tiles.
  `info["events"]` exposes native action/AI events. This is currently **not** an observation restricted to player visibility.
* `Discrete(9)` actions: `0` north, `1` north-east, `2` east, `3` south-east, `4` south, `5` south-west,
  `6` west, `7` north-west, `8` end turn. Movement requests the adjacent destination using native route validation;
  obstacles can cause a rejection or a longer route, so an accepted request is not a promise of a single tile cost.
* Rejected illegal/unsupported actions leave the world unchanged and return `action_accepted=False` plus `rejection` in `info`.
  Sampling can select them: this preview has no legal-action mask. Attempts still count toward the episode limit.
* Reward is always `0.0`; a learning objective and final reward rules have not been implemented.
* `terminated` means an actual native terminal state; `truncated` means the configured action limit (12 by default).
  `reset()` closes the previous engine process and reloads the original save in a fresh process. It does not overwrite it.
* A human battle/choice boundary, engine failure or transport error raises an exception. It is never disguised as game over
  or a time limit. The current engine rolls back unsupported gameplay interactions. Longer random runs can encounter these
  limits; this is not yet an adapter for complete arbitrary games.
* `reset(seed=...)` seeds both the Python action sampler and the native continuation RNG. The saved world/map seed is
  preserved. `info["seed"]` reports the effective engine seed; registration now allows the checker's determinism checks.
* `render_mode="rgb_array"` returns a copy of the observation via `render()`; `"human"` needs the `viewer` extra.
  Use one human viewer per Python process. The CLI also checks `env.unwrapped.window_closed`; window closing is not a game result.

The `gym` and `viewer` extras install only into the separate Python environment. Importing the base `fheroes2_env` package
still requires only the Python standard library. No C++ or mobile build changes were needed for this preview.
On Linux/macOS, supply your enabled desktop executable with `--executable`; current runtime verification was on Windows.
Assets and local reference saves are required, as described in [the baseline instructions](../docs/PYTHON_ENV_BASELINE.md).
This early example does not complete implementation-plan step 13 (full observation/action coverage and RL contract).

The calling convention follows the [official Gymnasium basic loop](https://gymnasium.farama.org/main/content/basic_usage/).
To run the optional checks together with the existing suite:

```powershell
uv run --project python --extra viewer python -m unittest discover -s python/tests -v
```

## Platform separation

* Python support is opt-in: CMake's `ENABLE_PYTHON_ENV` defaults to `OFF`.
* Only the project-local `windows-local` and inherited `windows-debug` presets enable it automatically.
* Standard game builds do not require Python, uv, a virtual environment or the JSON library. The JSON header is compiled only
  into the enabled environment implementation. Game rules use the same existing C++ code.
* Enabling the option is supported for desktop Windows, Linux and macOS. CMake rejects it for other target systems. Android,
  iOS, console and WebAssembly builds retain the disabled default. The legacy Makefiles and Visual Studio project also leave
  the feature disabled unless its C++ definition is explicitly supplied.
* `python/.venv` is a local, ignored development environment, not a game dependency or a distributed game asset.
* Runtime verification for this step was performed on Windows. This does not claim that other platform SDK builds were run.

## Build and run

From the repository root, on the configured Windows development machine:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/local.ps1
uv sync --project python
uv run --project python python python/examples/hello.py
```

The example starts `fheroes2.exe --python-env`, prints the handshake and capabilities, then verifies a successful process exit.
The protocol bootstrap initializes no video, audio, game data or player configuration. Required executable libraries, such as
SDL's DLLs on Windows, must still be available beside the executable or on the library search path.

For a separate desktop CMake build with the normal engine dependencies installed:

```sh
cmake -S . -B build/python-env -DENABLE_PYTHON_ENV=ON
cmake --build build/python-env --parallel
uv sync --project python
uv run --project python python python/examples/hello.py --executable build/python-env/fheroes2
```

Adjust the executable path for Windows (`.exe`) or a multi-configuration generator. A build with the feature disabled rejects
`--python-env` immediately with a stderr explanation. Running the game without that argument retains the normal startup path.

The package needs Python 3.11 or newer and has no third-party runtime dependencies. The local uv interpreter selection is 3.14.
Only setuptools is needed to install the package; neither setuptools nor uv participates in the C++ build.

## Python use

```python
from fheroes2_env import HeroesSession

with HeroesSession("fheroes2.exe", timeout=5.0) as game:
    print(game.info["engine_version"])
    print(game.capabilities())
    game.load_save("build/python-env-baseline/fixtures/other-side-day1.sav")
    state = game.get_state()
    print(state["date"], state["players"])
    process_id = game.pid

assert game.closed
assert game.returncode == 0
```

For a runnable example with a short report:

```powershell
uv run --project python python python/examples/read_state.py build/python-env-baseline/fixtures/other-side-day1.sav
```

`load_save(path)` resolves the path and invokes the original C++ save loader. It currently accepts standard single-player
adventure saves, up to 64 MiB. Campaign/hotseat saves are rejected. Original `DATA/HEROES2.AGG` assets are required at this
point; set the child environment's `FHEROES2_DATA` to the game data root if necessary. No Python save parser is involved.
Only load trusted local saves: the existing engine deserializer is not a security boundary for hostile files.

A successful load does not run a turn or start the human input loop. A failed load clears the previous world; `get_state()`
then returns `no_game_loaded` until a valid save is loaded. Invalid request parameters are rejected before changing the world.
Input saves are opened read-only. The session does not initialize or write the normal player profile.

`get_state()` is explicitly **omniscient**: it exports every player's funds, hero/castle ownership, all heroes (including the
inactive/recruitable pool), armies, positions, primary/secondary skills, artifacts, spell IDs, castles, buildings, dwelling
stocks, and every tile, including objects behind fog. Tile metadata, object parts, fog colors and passability are included.
The `date`, `current_player`, map seed/conditions and game result describe the loaded save. Coordinates are zero-based;
tile index is `y * width + x`; player/owner IDs are the engine's color bits; neutral ownership is zero. Castle IDs are entrance
tile indices. Enum IDs follow the engine source. Empty army/artifact slots and unavailable positions are `null`.

The JSON fields are an initial projection of the world, not every internal C++ member. By default, `serialized_state` also
contains the engine's complete `world + settings + game result` save payload as hex, with its save format version. This
preserves events, visit flags and other persistent fields not yet projected into named JSON properties. It is an opaque,
version-dependent payload, not a standalone `.sav`, restore API or snapshot of a running battle/input stack. Use
`get_state(include_serialized=False)` for the named fields alone. Repeated queries do not advance the game or consume RNG.

The state schema is version 1. `state_version` increases on each attempted load and successful gameplay action; inspection
leaves it unchanged. The saved
current player is metadata, not yet an external-controller decision handshake. Saves do not restore an open castle/hero UI.
A future `observe(player_id)` will apply visibility rules separately; it is not implemented and omniscient state must not
be mistaken for a fair player observation.

After loading, `start_session(player_id)` enters the engine's saved human-turn checkpoint and returns its pending decision.
`get_decision()` repeats it. `step("session.stop", token=decision["token"])` exits that wait without ending a game turn.
State inspection and `close()` remain available while waiting. Tokens identify the process, episode, state, decision and
player; stale or wrong-player commands are rejected without changing the world. Loading another save requires stopping
the wait first. Only the single human player of a live standard save can be attached at present. No control flags change.
See the [controller contract and source audit](../docs/PYTHON_ENV_CONTROLLER.md) and runnable `examples/decision.py`.

## Adventure actions

After attaching the human player, use the explicit current decision token:

```python
result = game.move_hero(hero_id=52, x=32, y=25, token=decision["token"])
decision = result["decision"]
result = game.end_turn(token=decision["token"])
decision = result["decision"]
print(result["events"])
```

These wrap `step("hero.move", token=..., params={"hero_id":52,"x":32,"y":25})` and `step("turn.end", token=...)`.
The first profile supports affordable complete land routes through ordinary tiles and plain resource piles. It preserves
native path costs, fog, pickup/removal and daily/weekly rules. `turn.end` runs the real remaining AI players and returns
at the next human decision. Events report movement, funds collected, AI turns, dates and daily events; player state exposes
`daily_income` and `lost_town_days`. Each successful gameplay action invalidates the old token; reads/render do not.

Ships and actions outside the declared choice/adventure/battle profile are not supported yet. A blocked interaction
during an AI turn rejects and restores the entire command's world/settings/result, RNG, UID and decision checkpoint.
The pending token remains valid. It does not silently resolve a human battle or skip the AI's intended action.
Gameplay requires matching H2D resources as well as AGG data. See the [action contract and limits](../docs/PYTHON_ENV_ADVENTURE.md).

```powershell
uv run --project python python python/examples/adventure.py
```

## Seeded episodes and reset

```python
episode = game.reset(save="checkpoint.sav", seed=123)
decision = episode["decision"]  # already waiting for the external agent
episode = game.reset(seed=123)  # same source, new process, repeatable continuation
episode = game.reset(map_path="maps/THEOTHER.MP2", seed=123, player_id=1, difficulty=1)
```

`HeroesSession.reset` restarts the process, including from live choices/battles, terminal states, crashes and timeouts.
It returns `seed`, `source`, `loaded` and `decision`. Omit `seed` for a fresh uint32 seed and retain the returned value for replay.
The source is required on first use; later resets can reuse the last successful source/player/difficulty configuration.
New games use existing standard MP2/MX2/FH2M maps and native setup rules. The current single-external-side profile still applies.
For saves, the seed controls future main-thread random draws, preserving the entire saved world and its own map seed.
The native save format does not restore the original unsaved main-thread RNG continuation. Lower-level `load_save(path, seed=...)`
and `new_game(path, seed=..., player_id=1, difficulty=1)` are also available; they require a separate `start_session` afterward.
See [the reset contract, lifecycle, RNG audit and example](../docs/PYTHON_ENV_RESET.md).

```powershell
uv run --project python python python/examples/reset.py
uv run --project python python python/examples/reset.py --map maps/THEOTHER.MP2 --seed 123
```

## Structured Gymnasium environment

```python
from fheroes2_env.gym_env import make_env

with make_env(executable="fheroes2.exe", save="checkpoint.sav", max_steps=1000) as env:
    obs, info = env.reset(seed=123)
    for _ in range(10000):
        action = env.action_space.sample(mask=obs["action_mask"])
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            obs, info = env.reset()
```

`Fheroes2-v0` uses a fixed numeric `Dict` observation and `Discrete(8192)` action slots with descriptors and a native-validated
mask. Every own active hero can move to adjacent tiles; supported castle, army, artifact and spell commands are included.
Choices and every native battle candidate stay inside the episode. Exact integer quantity ranges are enumerated; configured
entity/action limits raise `ProfileLimitError` instead of dropping legal candidates. The full omniscient state and events,
including AI sides, remain in `info`. The current one-external-side engine profile still applies.

Reward is 0 between decisions, +1 for native victory, -1 for native defeat. Only native results terminate; the agent-attempt
limit truncates. Unsupported engine situations and failures raise exceptions and require reset. An in-range masked slot
is an explicit rejected attempt with zero reward and unchanged native state; it counts toward the agent limit.
`render_mode=None` makes no image requests. With `"rgb_array"`, explicit `render()` returns the configured native view;
the default `render_view="auto"` selects the live battle or adventure view. This adapter does not open a human viewer.

```powershell
uv run --project python --extra gym python python/examples/train_loop.py
uv run --project python --extra gym python python/examples/train_loop.py --battle-demo --max-steps 100
```

See the [full Gym schema, command codes, bounds and verification](../docs/PYTHON_ENV_GYM.md).
Import the Gym module explicitly; importing the base package remains free of NumPy/Gym dependencies.
The old `Fheroes2AdventurePreview-v0` remains available with its narrower nine-action interface.

## Headless rendering

```python
with HeroesSession("fheroes2.exe", timeout=20) as game:
    game.load_save("build/python-env-baseline/fixtures/other-side-day1.sav")
    frame = game.render(width=640, height=480, center=(32, 24))
    print(frame.shape)  # (480, 640, 3)
    frame.save_ppm("build/frame.ppm")
    # Optional, if NumPy is installed: rgb_array = frame.to_numpy()
    print(game.runtime_info())  # video/audio/controller initialization all false
```

`render()` returns an immutable `RGBFrame` with RGB uint8 bytes in HWC order, a camera tile coordinate and state version.
Dimensions must be integers from 32 to 1024; the optional center is a valid zero-based tile pair (default: map center).
The default view is `adventure`, explicitly omniscient, with terrain, objects and heroes. It uses the real engine's
`GameArea::Redraw` into an independent `Image`, without constructing a window, radar or interactive interface.
Step 11 also provides native hero, castle and battle snapshots:

```python
hero_frame = game.render(view="hero", hero_id=52)
castle_frame = game.render(view="castle", castle_id=896)
# While waiting for an external battle action:
battle_frame = game.render(view="battle")
```

Select actual hero/castle IDs from `get_state()`. Both own and AI entities can be rendered. The three new views
use a native 640×480 canvas resized to the requested dimensions. Battle rendering requires a live battle decision;
otherwise it returns `no_active_battle`. These are read-only snapshots, not interactive windows.

Rendering requires the original AGG data and matching `files/data/resurrection.h2d`; missing graphics resources return
`assets_unavailable`. Pure state loading still needs only the original AGG files. The client owns a short-lived output
directory, reads a bounded RGB file and cleans it on success/error. Pixels do not travel as JSON number arrays.
The low-level `render` request uses `view`, `width`, `height`, `output_path`, optional adventure-only `center_x`/`center_y`,
hero-only `hero_id` or castle-only `castle_id`; output must
be a new file in an existing directory. Always prefer the Python method, which manages those files automatically.

Frame requests work while waiting for a decision and do not advance the day, consume a decision, change player flags,
update animation frames or write the player profile. `runtime_info()` reports the actual SDL subsystem state.
The headless execution policy rejects display access, modal dialogs and interactive event loops with
`unsupported_interaction`. Animation delay checks do not wait. This is infrastructure for future gameplay operations;
unsupported actions still fail explicitly and the guard does not substitute answers for game choices.

Runnable example:

```powershell
uv run --project python python python/examples/render.py build/python-env-baseline/fixtures/other-side-day1.sav
```

See [headless implementation and verification](../docs/PYTHON_ENV_HEADLESS.md).
The [four-view example and implementation notes](../docs/PYTHON_ENV_VIEWS.md) cover all four snapshots:

```powershell
uv run --project python python python/examples/views.py
```

The example writes PNG files under `build/python-env-views` and checks that rendering preserves the full state and decision.

`hello()` repeats the handshake. `request(method, params)` exposes the underlying connection; unknown commands raise
`EngineError` without breaking the session. A timeout, invalid reply or unexpected process exit stops the process and raises
`EngineTimeoutError`, `ProtocolError` or `EngineProcessError`. The request deadline covers both writing and reading.
`close()` is idempotent. Always use a context manager or call `close()` explicitly.

Each session owns one child process. The client serializes requests, keeps stderr separate from protocol output, and uses a
temporary diagnostics file to avoid a full stderr pipe blocking the engine. `cwd` and a complete child `env` mapping can be
provided explicitly. The client does not modify the parent's environment or global Python installation.

## Protocol version 1

Transport: UTF-8 JSON objects, one per line, on the child's stdin/stdout. The client launches without a shell and with hidden
console creation on Windows. Stdout contains only replies. No unsolicited startup banner is sent.

Request:

```json
{"api_version":1,"id":1,"method":"hello","params":{}}
```

Success:

```json
{"api_version":1,"id":1,"result":{"engine":"fheroes2","engine_version":"1.1.17","mode":"bootstrap","capabilities":{}}}
```

The actual handshake includes all capability fields; the example above abbreviates that object.

Error:

```json
{"api_version":1,"id":2,"error":{"code":"unknown_method","message":"Unknown environment method. Use capabilities to list supported methods."}}
```

* `id`: unsigned 32-bit integer; replies echo it. Invalid/unreadable IDs produce `null` in the error response.
* `api_version`: integer 1. Unsupported versions are rejected rather than interpreted as another protocol.
* Methods: `hello`, `capabilities`, `load_save`, `new_game`, `get_state`, `get_castle_options`, `get_army_options`, `check_actions`, `start_session`, `get_decision`, `step`, `runtime_info`, `render`, `close`.
  `params` is optional and must be an object.
  `load_save` requires `{"path":"absolute save path"}` with an optional uint32 `seed`;
  `new_game` requires `path`, uint32 `seed`, `player_id` and `difficulty` (0..4). `get_state` accepts only `{"include_serialized":true}`
  (optional, default true). `start_session` requires `{"player_id":1}` (one color bit); `step` requires `action`, `token`
  and `params`, as described in the controller contract. `render` uses the frame parameters described above.
  `get_castle_options` requires `{castle_id}`; `get_army_options` requires `{kind,id}`.
  `check_actions` requires `{token,actions}` with at most 128 adventure `{action,params}` commands; its `valid` array
  reports native precondition checks without executing commands. Other methods require empty parameters.
* Request limit: 65,536 bytes before the terminating LF. CRLF is accepted as JSON trailing whitespace plus LF.
* Response limit: 64 MiB including the terminating LF. A larger state returns `response_too_large`; retry without the payload.
* Nesting is limited to a shallow request envelope. Malformed/deep/oversized records return an error; the next record can run.
* Error codes include `invalid_request`, `unsupported_version`, `unknown_method`, `request_too_large`, `no_game_loaded`,
  `invalid_path`, `assets_unavailable`, `load_failed`, `state_export_failed`, `response_too_large` and `engine_error`.
* `close` returns `{"closed":true}`, flushes stdout and exits with code 0. EOF also ends the bootstrap cleanly.
* A final nonempty record without LF is rejected. Oversized records are drained with bounded retained memory.

The handshake's historical `mode: "bootstrap"` label is retained. Capabilities report `state_queries` and `omniscient_state`
as true, and `game_initialized` reflects whether a save is loaded. `simulation`, `headless_gameplay` and `gameplay_actions`
are true for the limited `gameplay_profile: "adventure_basic"` described above, not for every game interaction.
`external_controller` is true; `controller_active` reflects the decision wait. `choices` is true for the enumerated `choice_types`;
`adventure_spells` lists the two currently supported spells. This does not mean all map interactions or spells are covered.
`render` is true, `render_views` lists `adventure`, `battle`, `hero`, `castle`, and `render_backend` is `memory_image`.

## Verification

```powershell
uv run --project python python -m unittest discover -s python/tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-baseline.ps1
```

The tests use the compiled executable (default: repository-root `fheroes2.exe` on Windows, `fheroes2` elsewhere). Override with
`FHEROES2_TEST_EXE` if needed. They cover real pipe round trips, unavailable assets/video/audio, profile isolation, malformed
records, version/ID validation, EOF, multiple sessions, timeouts including blocked writes, process crashes, bad replies and
process cleanup. Failure-mode peers use temporary Python child processes, not a second implementation of game logic.

The engine uses the vendored, unmodified [JSON for Modern C++ 3.12.0](../src/thirdparty/nlohmann/README.md) header for parsing.
Its upstream release checksum was verified on download. The normal disabled build does not include it.

On 2026-10-26, the Windows opt-in build passed all 14 tests and the example. The feature-disabled build was also compiled:
its compile commands contained no transport definition, and the transport object had no JSON-header dependency. A fresh
CMake configuration defaulted to `OFF`, and a non-desktop target rejected explicit opt-in. The original baseline save and
asset checks still passed. Normal windowed startup reached the main menu and exited cleanly using the isolated test profile.
These are Windows build/runtime and configuration checks, not Android/iOS/Linux/macOS SDK tests.

Step 3 added seven world-state tests (21 total): both recorded saves match the original UI values; AI and fog-hidden data are
present; repeated exports and small/large/small reloads preserve the world; invalid loads recover; loaded processes are
independent. These tests deliberately use invalid SDL video/audio drivers and an empty isolated profile. Local reference
saves remain ignored; world tests skip with an explanation when the fixtures are absent.

Step 4 adds seven decision tests (28 total), covering repeated state reads while the real C++ decision callback waits,
unchanged player control flags and serialized world, rejection of wrong/stale/cross-process tokens, unsupported actions,
reload/reentry protection, close and EOF unwinding, and malformed requests inside the decision wait.

Step 5 adds seven render tests (35 total), including deterministic repeated frames, full serialized world/decision equality,
invalid SDL drivers, empty profile, two independent processes, bounds/camera validation, temporary-file cleanup, file-error
recovery and missing H2D graphics resources. Separate C++ policy checks reject display/input initialization before SDL starts.
Dummy/software probes verify both explicit video-only initialization and the unchanged normal video+audio defaults.

Step 6 adds eight adventure tests (43 total), covering native movement/pickup, rejected routes/ownership, AI progression on
both fixtures, exact daily income, weekly dwelling growth, stop/reattach, and atomic rejection at a real human-battle boundary.

Step 10 replaces the old unsupported-battle expectation with live external battle decisions and full-action cancellation.
On 2026-10-29, all 111 integration tests passed, including 12 new battle tests, AI-initiated defense, offensive siege/capture,
combat spell costs, surrender payment, loss, battle-to-level-up continuation, read-only snapshots and Gym battle boundaries.
Both the enabled and feature-disabled normal Windows builds compiled. Other platform SDK builds and manual GUI battle checks were not run.
