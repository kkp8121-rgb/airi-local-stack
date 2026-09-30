"""Default-off proxy supervisor (proxy_supervisor.py, start-local-ollama-proxy.ps1 -SuperviseProxy).

A proxy that exits is started again with AIRI_LIVE_RESTORE_SHOW_STATE=on so it replays the saved
live shows; the first launch never restores, and a crash loop gives up instead of spinning forever.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import proxy_supervisor


PROXY_DIR = Path(__file__).resolve().parent
SUPERVISOR = PROXY_DIR / "proxy_supervisor.py"
RESTORE = "AIRI_LIVE_RESTORE_SHOW_STATE"
TOKEN = "t" * 40
# Appends one JSON line per launch; exits 0 on the first launch and with the launch number after.
CHILD = """
import json, os, sys
record = sys.argv[1]
with open(record, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "restore": os.environ.get("AIRI_LIVE_RESTORE_SHOW_STATE"),
        "token": os.environ.get("AIRI_LIVE_BROADCAST_MASTER_TOKEN"),
        "args": sys.argv[2:],
    }) + "\\n")
with open(record, encoding="utf-8") as handle:
    launches = sum(1 for _ in handle)
sys.exit(0 if launches == 1 else launches)
"""
STAMP = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"
# A stand-in proxy with the real runtime: the fresh launch starts a show, sets its context and
# crashes; the restarted launch records what the runtime restored.
CRASHING_PROXY = """
import json, os, sys
sys.path.insert(0, sys.argv[2])
from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER, LiveBroadcastRuntime
runtime = LiveBroadcastRuntime.from_env()
if os.environ.get("AIRI_LIVE_RESTORE_SHOW_STATE") != "on":
    context = {"schema_version": 1, "topic_title": "t", "segment_label": "s", "situation": "x",
               "briefing": BROADCAST_BRIEFING_HEADER, "donation_continuation": False}
    runtime.master_control({"action": "start", "show_id": "show-crash"})
    runtime.master_control({"action": "set_tag_context", "show_id": "show-crash", "broadcast_context": context})
    os._exit(1)
turn = runtime.tag_turn(screening_ready=True)
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump({"shows": runtime.health()["active_shows"], "context_show": turn and turn.show_id}, handle)
"""


class ProxySupervisorTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.child = Path(folder.name) / "fake_proxy.py"
        self.child.write_text(CHILD, encoding="utf-8")
        self.record = Path(folder.name) / "launches.jsonl"

    def supervise(self, *options: str) -> subprocess.CompletedProcess:
        env = {**os.environ, RESTORE: "on", "AIRI_LIVE_BROADCAST_MASTER_TOKEN": TOKEN}
        return subprocess.run(
            [sys.executable, str(SUPERVISOR), *options, "--", str(self.child), str(self.record), "--port", "11435"],
            capture_output=True, text=True, timeout=60, env=env,
        )

    def launches(self) -> list[dict]:
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text(encoding="utf-8").splitlines()]

    def test_the_first_launch_never_restores_and_every_restart_does(self):
        completed = self.supervise("--restart-delay", "0", "--max-restarts", "2", "--window", "600")
        launches = self.launches()
        # An inherited restore flag is dropped: a fresh start must reset the saved shows.
        self.assertEqual([launch["restore"] for launch in launches], [None, "on", "on"])
        # The token reaches every launch through the environment, never through a command line.
        self.assertEqual([launch["token"] for launch in launches], [TOKEN] * 3)
        self.assertEqual([launch["args"] for launch in launches], [["--port", "11435"]] * 3)
        self.assertNotIn(TOKEN, completed.stdout + completed.stderr)

    def test_a_crashed_proxy_comes_back_with_its_live_show(self):
        folder = self.child.parent
        child = folder / "crashing_proxy.py"
        child.write_text(CRASHING_PROXY, encoding="utf-8")
        state = folder / "live-show-state.json"
        # State left by an earlier run must not survive the fresh first launch.
        state.write_text(json.dumps({"schema_version": 1, "shows": {"show-stale": {"tag_context": None}}}),
                         encoding="utf-8")
        env = {**os.environ, "AIRI_LIVE_BROADCAST_ENABLED": "on", "AIRI_LIVE_BROADCAST_MASTER_TOKEN": "m" * 32,
               "AIRI_LIVE_BROADCAST_OBSERVER_TOKEN": "o" * 32, "AIRI_LIVE_TAG_CONTEXT": "on",
               "AIRI_LIVE_SHOW_CARRYOVER": "", "AIRI_LIVE_SHOW_STATE_FILE": str(state)}
        env.pop(RESTORE, None)
        completed = subprocess.run(
            [sys.executable, str(SUPERVISOR), "--restart-delay", "0", "--max-restarts", "1", "--",
             str(child), str(self.record), str(PROXY_DIR), "--port", "11435"],
            capture_output=True, text=True, timeout=60, env=env,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(json.loads(self.record.read_text(encoding="utf-8")), {"shows": 1, "context_show": "show-crash"})
        self.assertIn("proxy exited with code 1; restart 1", completed.stderr)
        self.assertIn("[live show state] restored 1 show(s)", completed.stderr)
        self.assertNotIn("m" * 32, completed.stderr + state.read_text(encoding="utf-8"))

    def test_any_exit_is_logged_and_restarted_until_the_limit(self):
        completed = self.supervise("--restart-delay", "0", "--max-restarts", "2", "--window", "600")
        self.assertEqual(len(self.launches()), 3)
        self.assertEqual(completed.returncode, 1)
        lines = completed.stderr.splitlines()
        self.assertEqual(len(lines), 3, completed.stderr)
        # A clean exit (code 0) is restarted like a crash.
        self.assertRegex(lines[0], rf"^\[proxy_supervisor\] {STAMP} proxy exited with code 0; restart 1 in 0 s$")
        self.assertRegex(lines[1], rf"^\[proxy_supervisor\] {STAMP} proxy exited with code 2; restart 2 in 0 s$")
        self.assertRegex(lines[2], rf"^\[proxy_supervisor\] {STAMP} proxy exited with code 3; "
                                   r"giving up after 2 restarts within 600 s$")

    def test_no_restart_budget_gives_up_after_the_first_exit(self):
        completed = self.supervise("--restart-delay", "0", "--max-restarts", "0")
        self.assertEqual(len(self.launches()), 1)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("giving up after 0 restarts within 600 s", completed.stderr)

    def test_restarts_older_than_the_window_do_not_count(self):
        exits = iter((0.0, 1.0, 100.0, 101.0, 102.0))
        restores: list[bool] = []
        delays: list[float] = []

        def launch(command, restart):
            self.assertEqual(command, ["proxy.py", "--port", "11435"])
            restores.append(restart)
            return 1

        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = proxy_supervisor.supervise(
                ["proxy.py", "--port", "11435"], restart_delay=3.0, max_restarts=2, window=10.0,
                launch=launch, sleep=delays.append, clock=lambda: next(exits),
            )
        # Two quick exits spend the budget; the window then forgets them, so two more restarts fit.
        self.assertEqual(result, 1)
        self.assertEqual(restores, [False, True, True, True, True])
        self.assertEqual(delays, [3.0] * 4)
        self.assertIn("restart 4 in 3 s", stderr.getvalue())
        self.assertIn("giving up after 2 restarts within 10 s", stderr.getvalue())

    def test_the_launch_environment_adds_the_restore_flag_only_on_a_restart(self):
        seen: list[dict] = []

        class _Child:
            def __init__(self, command, env):
                seen.append({"command": command, "restore": env.get(RESTORE), "token": env.get("AIRI_TEST_KEEP")})

            @staticmethod
            def wait():
                return 0

        with mock.patch.dict(os.environ, {RESTORE: "on", "AIRI_TEST_KEEP": "kept"}), \
                mock.patch.object(proxy_supervisor.subprocess, "Popen", _Child):
            self.assertEqual(proxy_supervisor._launch(["proxy.py", "--port", "11435"], False), 0)
            self.assertEqual(proxy_supervisor._launch(["proxy.py", "--port", "11435"], True), 0)
            self.assertEqual(os.environ[RESTORE], "on")
        self.assertEqual([entry["restore"] for entry in seen], [None, "on"])
        self.assertEqual([entry["token"] for entry in seen], ["kept", "kept"])
        self.assertEqual(seen[0]["command"], [sys.executable, "proxy.py", "--port", "11435"])

    def test_a_bad_command_line_is_refused_before_any_launch(self):
        proxy = [str(self.child), str(self.record)]
        for arguments in ([], ["--"], proxy, ["--restart-delay", "-1", "--", *proxy],
                          ["--restart-delay", "nan", "--", *proxy], ["--max-restarts", "-1", "--", *proxy],
                          ["--window", "0", "--", *proxy]):
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, str(SUPERVISOR), *arguments], capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertIn("usage: proxy_supervisor.py", completed.stderr)
                self.assertEqual(self.launches(), [])


if __name__ == "__main__":
    unittest.main()
