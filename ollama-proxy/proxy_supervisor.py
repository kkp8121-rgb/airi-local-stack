"""Default-off supervisor that starts the AIRI Ollama proxy again after it exits.

Usage: python proxy_supervisor.py [--restart-delay SECONDS] [--max-restarts N] [--window SECONDS]
       -- <proxy script> [proxy args...]

The proxy runs as ``[sys.executable, script, *args]`` with this process's environment, so the live
broadcast tokens reach it through the environment and never through a command line. Every restart,
never the first launch, adds AIRI_LIVE_RESTORE_SHOW_STATE=on so the proxy replays its saved shows.
The proxy script path and ``--port`` stay on this process's command line, so the stop scripts that
match the proxy by command line stop the supervisor as well.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import math
import os
import subprocess
import sys
import time
from typing import Callable, Sequence

RESTORE_ENV = 'AIRI_LIVE_RESTORE_SHOW_STATE'
# Long enough that a stop script that killed the proxy first also kills this process before a restart.
DEFAULT_RESTART_DELAY_SECONDS = 3.0
DEFAULT_MAX_RESTARTS = 5
DEFAULT_WINDOW_SECONDS = 600.0
USAGE = '%(prog)s [--restart-delay SECONDS] [--max-restarts N] [--window SECONDS] -- <proxy script> [proxy args...]'


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    print(f'[proxy_supervisor] {stamp} {message}', file=sys.stderr, flush=True)


def _launch(command: Sequence[str], restart: bool) -> int:
    """Run the proxy once and return its exit code."""
    env = dict(os.environ)
    # A fresh start must reset the saved shows, even when a caller exported the flag.
    env.pop(RESTORE_ENV, None)
    if restart:
        env[RESTORE_ENV] = 'on'
    child = subprocess.Popen([sys.executable, *command], env=env)
    try:
        return child.wait()
    except BaseException:
        child.terminate()
        raise


def supervise(
    command: Sequence[str],
    *,
    restart_delay: float,
    max_restarts: int,
    window: float,
    launch: Callable[[Sequence[str], bool], int] = _launch,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Restart the proxy after every exit; return 1 once more than max_restarts fall within window."""
    recent: deque[float] = deque()
    restarts = 0
    while True:
        code = launch(command, restarts > 0)
        now = clock()
        while recent and now - recent[0] > window:
            recent.popleft()
        if len(recent) >= max_restarts:
            _log(f'proxy exited with code {code}; giving up after {len(recent)} restarts within {window:g} s')
            return 1
        recent.append(now)
        restarts += 1
        _log(f'proxy exited with code {code}; restart {restarts} in {restart_delay:g} s')
        sleep(restart_delay)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='proxy_supervisor.py', usage=USAGE)
    parser.add_argument('--restart-delay', type=float, default=DEFAULT_RESTART_DELAY_SECONDS, metavar='SECONDS')
    parser.add_argument('--max-restarts', type=int, default=DEFAULT_MAX_RESTARTS, metavar='N')
    parser.add_argument('--window', type=float, default=DEFAULT_WINDOW_SECONDS, metavar='SECONDS')
    split = arguments.index('--') if '--' in arguments else len(arguments)
    options = parser.parse_args(arguments[:split])
    command = arguments[split + 1:]
    if not command:
        parser.error('a proxy script is required after --')
    if not (math.isfinite(options.restart_delay) and options.restart_delay >= 0):
        parser.error('--restart-delay must be a finite number of seconds, 0 or more')
    if options.max_restarts < 0:
        parser.error('--max-restarts must be 0 or more')
    if not (math.isfinite(options.window) and options.window > 0):
        parser.error('--window must be a finite number of seconds above 0')
    try:
        return supervise(
            command, restart_delay=options.restart_delay,
            max_restarts=options.max_restarts, window=options.window,
        )
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
