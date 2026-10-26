# fheroes2 Python connection

This is implementation step 2: a process connection and lifecycle API. It does not load a map, expose game state, simulate turns,
render the game, or implement Gymnasium yet. The handshake explicitly reports those capabilities as unavailable.

## Platform separation

* Python support is opt-in: CMake's `ENABLE_PYTHON_ENV` defaults to `OFF`.
* Only the project-local `windows-local` and inherited `windows-debug` presets enable it automatically.
* Standard game builds do not require Python, uv, a virtual environment or the JSON library. The JSON header is compiled only
  into the enabled transport implementation. Game rules use the same existing C++ code.
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
    process_id = game.pid

assert game.closed
assert game.returncode == 0
```

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
{"api_version":1,"id":2,"error":{"code":"unknown_method","message":"This bootstrap supports hello, capabilities and close."}}
```

* `id`: unsigned 32-bit integer; replies echo it. Invalid/unreadable IDs produce `null` in the error response.
* `api_version`: integer 1. Unsupported versions are rejected rather than interpreted as another protocol.
* Methods: `hello`, `capabilities`, `close`. `params` is optional but must be an empty object when present in this version.
* Request limit: 65,536 bytes before the terminating LF. CRLF is accepted as JSON trailing whitespace plus LF.
* Nesting is limited to a shallow request envelope. Malformed/deep/oversized records return an error; the next record can run.
* Error codes: `invalid_request`, `unsupported_version`, `unknown_method`, `request_too_large`.
* `close` returns `{"closed":true}`, flushes stdout and exits with code 0. EOF also ends the bootstrap cleanly.
* A final nonempty record without LF is rejected. Oversized records are drained with bounded retained memory.

Future world/session operations will reuse this transport and keep game rules in the engine. This bootstrap does not claim
that a real game can already run headlessly.

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
