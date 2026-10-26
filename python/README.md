# fheroes2 Python connection

Implementation steps 2–3 provide a process connection, real save loading and a read-only world API. Loading and inspection
work without video or audio initialization. Actions, turn simulation, rendering and Gymnasium are still unavailable.

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

The state schema is version 1. `state_version` increases on each attempted load; inspection leaves it unchanged. The saved
current player is metadata, not yet an external-controller decision handshake. Saves do not restore an open castle/hero UI.
A future `observe(player_id)` will apply visibility rules separately; it is not implemented and omniscient state must not
be mistaken for a fair player observation.

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
* Methods: `hello`, `capabilities`, `load_save`, `get_state`, `close`. `params` is optional and must be an object.
  `load_save` requires exactly `{"path":"absolute save path"}`; `get_state` accepts only `{"include_serialized":true}`
  (optional, default true). Other methods require empty parameters.
* Request limit: 65,536 bytes before the terminating LF. CRLF is accepted as JSON trailing whitespace plus LF.
* Response limit: 64 MiB including the terminating LF. A larger state returns `response_too_large`; retry without the payload.
* Nesting is limited to a shallow request envelope. Malformed/deep/oversized records return an error; the next record can run.
* Error codes include `invalid_request`, `unsupported_version`, `unknown_method`, `request_too_large`, `no_game_loaded`,
  `invalid_path`, `assets_unavailable`, `load_failed`, `state_export_failed`, `response_too_large` and `engine_error`.
* `close` returns `{"closed":true}`, flushes stdout and exits with code 0. EOF also ends the bootstrap cleanly.
* A final nonempty record without LF is rejected. Oversized records are drained with bounded retained memory.

The handshake's historical `mode: "bootstrap"` label is retained. Capabilities report `state_queries` and `omniscient_state`
as true, and `game_initialized` reflects whether a save is loaded. Full headless gameplay remains false until actions work.

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
