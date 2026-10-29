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

"""Exercise the actual executable and process failure modes, without game assets."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fheroes2_env import EngineError, EngineProcessError, EngineTimeoutError, HeroesSession, ProtocolError
from fheroes2_env import session as session_module

ROOT = Path(__file__).resolve().parents[2]
EXECUTABLE = Path(os.environ.get("FHEROES2_TEST_EXE", ROOT / "fheroes2.exe"))
if os.name != "nt" and "FHEROES2_TEST_EXE" not in os.environ:
    EXECUTABLE = ROOT / "fheroes2"
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def record(method, request_id=1, **fields):
    return (json.dumps({"api_version": 1, "id": request_id, "method": method, **fields}) + "\n").encode()


class EngineIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXECUTABLE.is_file():
            raise RuntimeError(f"Build the engine first or set FHEROES2_TEST_EXE: {EXECUTABLE}")

    def run_raw(self, payload):
        result = subprocess.run(
            [str(EXECUTABLE), "--python-env"],
            input=payload,
            capture_output=True,
            timeout=10,
            creationflags=CREATE_FLAGS,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_bootstrap_needs_no_assets_video_audio_or_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ)
            env.pop("HOME", None)
            env.update(
                APPDATA=str(Path(directory) / "unused-profile"),
                FHEROES2_DATA=str(Path(directory) / "missing-assets"),
                SDL_VIDEODRIVER="nonexistent-driver",
                SDL_AUDIODRIVER="nonexistent-driver",
            )
            result = subprocess.run(
                [str(EXECUTABLE), "--python-env"],
                input=record("hello") + record("capabilities", 2) + record("close", 3),
                cwd=directory,
                env=env,
                capture_output=True,
                timeout=10,
                creationflags=CREATE_FLAGS,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b"")
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([reply["id"] for reply in replies], [1, 2, 3])
            self.assertEqual(replies[0]["result"]["engine"], "fheroes2")
            self.assertEqual(replies[0]["result"]["mode"], "bootstrap")
            self.assertFalse(replies[1]["result"]["game_initialized"])
            self.assertTrue(replies[1]["result"]["headless_gameplay"])
            self.assertEqual(replies[2]["result"], {"closed": True})
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_multiple_sessions_and_repeated_close(self):
        with HeroesSession(EXECUTABLE) as first, HeroesSession(EXECUTABLE) as second:
            self.assertNotEqual(first.pid, second.pid)
            self.assertEqual(first.capabilities()["commands"], ["hello", "capabilities", "load_save", "get_state", "start_session", "get_decision", "step", "runtime_info", "render", "close", "get_castle_options", "get_army_options"])
            first.close()
            first.close()
            self.assertTrue(first.closed)
            self.assertEqual(first.returncode, 0)
            self.assertFalse(second.closed)
            self.assertEqual(second.hello()["engine"], "fheroes2")
            with self.assertRaises(EngineProcessError):
                first.capabilities()
        self.assertEqual(second.returncode, 0)

    def test_engine_rejection_keeps_connection_alive(self):
        with HeroesSession(EXECUTABLE) as game:
            with self.assertRaises(EngineError) as rejected:
                game.request("not_a_method")
            self.assertEqual(rejected.exception.code, "unknown_method")
            with self.assertRaises(EngineError) as rejected:
                game.request("hello", {"unexpected": True})
            self.assertEqual(rejected.exception.code, "invalid_request")
            with self.assertRaises(ValueError):
                game.request("hello", {"oversized": "x" * 65536})
            self.assertEqual(game.hello()["mode"], "bootstrap")

    def test_malformed_messages_are_rejected_and_next_message_is_processed(self):
        malformed = [
            (b"{\n", "invalid_request"),
            (b"[]\n", "invalid_request"),
            (record("hello", True), "invalid_request"),
            (record("hello", -1), "invalid_request"),
            (record("hello", 4294967296), "invalid_request"),
            (record("hello", 1.0), "invalid_request"),
            (record("hello", api_version=True), "unsupported_version"),
            (record("hello", api_version=2), "unsupported_version"),
            (record(123), "invalid_request"),
            (record("hello", params=[]), "invalid_request"),
            (record("hello", params={"unsupported": 1}), "invalid_request"),
            (b'{"id":1,"api_version":1,"method":"\xff"}\n', "invalid_request"),
            (b"[" * 1000 + b"]" * 1000 + b"\n", "invalid_request"),
            (b"x" * 65537 + b"\n", "request_too_large"),
        ]
        replies = self.run_raw(b"".join(line for line, _ in malformed) + record("hello", 20) + record("close", 21))
        self.assertEqual([reply["error"]["code"] for reply in replies[:-2]], [code for _, code in malformed])
        self.assertEqual(replies[-2]["result"]["engine"], "fheroes2")
        self.assertEqual(replies[-1]["result"], {"closed": True})

    def test_eof_and_incomplete_record(self):
        self.assertEqual(self.run_raw(b""), [])
        replies = self.run_raw(record("hello").rstrip(b"\n"))
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["error"]["code"], "invalid_request")
        replies = self.run_raw(b"x" * 65537)
        self.assertEqual(replies[0]["error"]["code"], "request_too_large")

    def test_extra_bootstrap_arguments_do_not_start_the_game(self):
        result = subprocess.run(
            [str(EXECUTABLE), "--python-env", "unexpected"],
            capture_output=True,
            timeout=10,
            creationflags=CREATE_FLAGS,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"Usage:", result.stderr)

    def test_body_exception_is_preserved_and_process_is_closed(self):
        game = HeroesSession(EXECUTABLE)
        with self.assertRaisesRegex(ValueError, "caller failure"):
            with game:
                raise ValueError("caller failure")
        self.assertTrue(game.closed)
        self.assertEqual(game.returncode, 0)


HELLO_STUB = """
import json, sys, time
request = json.loads(sys.stdin.readline())
hello = {'engine': 'fheroes2', 'engine_version': 'stub', 'mode': 'bootstrap', 'capabilities': {}}
print(json.dumps({'api_version': 1, 'id': request['id'], 'result': hello}), flush=True)
"""


class ProcessFailureTests(unittest.TestCase):
    @contextmanager
    def peer(self, script):
        real_popen = subprocess.Popen
        processes = []

        def launch(_args, **kwargs):
            process = real_popen([sys.executable, "-u", "-c", script], **kwargs)
            processes.append(process)
            return process

        try:
            with patch.object(session_module.subprocess, "Popen", side_effect=launch):
                yield processes
        finally:
            for process in processes:
                alive = process.poll() is None
                if alive:
                    process.kill()
                    process.wait(timeout=5)
                self.assertFalse(alive, "Client left a peer process running")

    def test_startup_timeout_kills_process(self):
        with self.peer("import time; time.sleep(60)"):
            with self.assertRaises(EngineTimeoutError):
                HeroesSession(sys.executable, timeout=0.5)

    def test_stdout_closed_during_startup(self):
        with self.peer("import sys; sys.exit(7)"):
            with self.assertRaises(EngineProcessError):
                HeroesSession(sys.executable)

    def test_invalid_json_kills_process(self):
        with self.peer("import time; print('not json', flush=True); time.sleep(60)"):
            with self.assertRaises(ProtocolError):
                HeroesSession(sys.executable)

    def test_mismatched_response_id_kills_process(self):
        script = HELLO_STUB + "\nrequest=json.loads(sys.stdin.readline())\nprint(json.dumps({'api_version':1,'id':999,'result':{}}),flush=True)\ntime.sleep(60)"
        with self.peer(script):
            game = HeroesSession(sys.executable)
            with self.assertRaises(ProtocolError):
                game.capabilities()
            self.assertTrue(game.closed)

    def test_request_timeout_also_covers_blocked_writes(self):
        with self.peer(HELLO_STUB + "\ntime.sleep(60)"):
            game = HeroesSession(sys.executable, timeout=0.5)
            with self.assertRaises(EngineTimeoutError):
                game.request("hello", {"payload": "x" * 60000})
            self.assertTrue(game.closed)

    def test_acknowledged_close_without_exit_is_killed(self):
        script = HELLO_STUB + "\nrequest=json.loads(sys.stdin.readline())\nprint(json.dumps({'api_version':1,'id':request['id'],'result':{'closed':True}}),flush=True)\ntime.sleep(60)"
        with self.peer(script):
            game = HeroesSession(sys.executable, timeout=0.5)
            with self.assertRaises(EngineTimeoutError):
                game.close()
            self.assertTrue(game.closed)

    def test_large_stderr_does_not_deadlock(self):
        script = HELLO_STUB + "\nsys.stderr.write('diagnostic'*100000);sys.stderr.flush()\nrequest=json.loads(sys.stdin.readline())\nprint(json.dumps({'api_version':1,'id':request['id'],'result':{'closed':True}}),flush=True)"
        with self.peer(script):
            with HeroesSession(sys.executable) as game:
                self.assertFalse(game.closed)
            self.assertEqual(game.returncode, 0)


if __name__ == "__main__":
    unittest.main()
