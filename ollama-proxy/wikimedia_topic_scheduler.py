"""Opt-in, single-owner scheduler for the Wikimedia evidence adapter.

The scheduler deliberately owns no queue or review state.  Its only durable
artifact is the ``OwnershipLock`` sidecar used to keep a second scheduler
process from running against the same Wikimedia cache.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from topic_review_contract import OwnershipLock, TopicReviewError
from wikimedia_topic_source import _cache_path, collect_wikimedia


DEFAULT_INTERVAL = 21600.0
DEFAULT_RETRY_INTERVAL = 900.0
MIN_INTERVAL = 900.0
MAX_INTERVAL = 86400.0
MIN_RETRY_INTERVAL = 60.0
MAX_RETRY_INTERVAL = 3600.0


class SchedulerError(ValueError):
    """Content-free scheduler configuration failure."""


def _status(output: TextIO, status: str) -> None:
    # Status-only records intentionally cannot contain source content, paths,
    # identifiers, exception text, or collector return values.
    output.write(json.dumps({"status": status}, separators=(",", ":")) + "\n")
    output.flush()


def _duration(value: Any, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchedulerError("invalid interval")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise SchedulerError("invalid interval")
    return result


def scheduler_lock_target(cache_path: str | Path) -> Path:
    """Return the topic-review-local target whose sidecar owns the schedule."""
    cache = _cache_path(cache_path)
    return cache.with_name("wikimedia-topic-scheduler.state")


def _collector_result(value: Any) -> dict[str, int]:
    if (
        not isinstance(value, dict)
        or set(value) != {"raw_count", "added_count"}
        or type(value["raw_count"]) is not int
        or type(value["added_count"]) is not int
        or value["raw_count"] < 0
        or not 0 <= value["added_count"] <= value["raw_count"]
    ):
        raise SchedulerError("invalid collector result")
    return value


def run_scheduler(*, collect: Callable[[], Any], interval: float,
                  retry_interval: float, monotonic: Callable[[], float] = time.monotonic,
                  sleep: Callable[[float], None] = time.sleep,
                  output: TextIO, max_cycles: int | None = None,
                  stop: Callable[[], bool] | None = None) -> int:
    """Run serial collection cycles; test controls are injection-only, not CLI flags."""
    interval = _duration(interval, minimum=MIN_INTERVAL, maximum=MAX_INTERVAL)
    retry_interval = _duration(retry_interval, minimum=MIN_RETRY_INTERVAL,
                               maximum=MAX_RETRY_INTERVAL)
    if max_cycles is not None and (isinstance(max_cycles, bool) or not isinstance(max_cycles, int) or max_cycles < 0):
        raise SchedulerError("invalid cycle limit")
    stop = stop or (lambda: False)
    completed = 0
    while max_cycles is None or completed < max_cycles:
        if stop():
            _status(output, "stopped")
            return completed
        # Read the injected monotonic clock at cycle boundaries.  Scheduling is
        # completion-based, so a slow collector never overlaps a following run.
        monotonic()
        try:
            _collector_result(collect())
        except KeyboardInterrupt:
            raise
        except (OSError, RuntimeError, ValueError, TopicReviewError):
            _status(output, "rejected")
            delay = retry_interval
        else:
            _status(output, "complete")
            delay = interval
        completed += 1
        monotonic()
        if max_cycles is not None and completed >= max_cycles:
            break
        if stop():
            _status(output, "stopped")
            return completed
        sleep(delay)
    return completed


def _float_argument(value: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("invalid number") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("invalid number")
    return parsed


def run_cli(argv: list[str] | None = None, *, output: TextIO | None = None) -> int:
    output = output or sys.stdout
    arguments = list(sys.argv[1:] if argv is None else argv)
    # The exact enable flag is the first gate. Irrelevant or malformed options
    # cannot make a default-off invocation inspect paths or numeric settings.
    if "--enable-wikimedia-schedule" not in arguments:
        _status(output, "disabled")
        return 0
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--enable-wikimedia-schedule", action="store_true")
    parser.add_argument("--source-policies")
    parser.add_argument("--raw-discoveries")
    parser.add_argument("--cache")
    parser.add_argument("--policy-id")
    parser.add_argument("--user-agent")
    parser.add_argument("--interval", type=_float_argument, default=DEFAULT_INTERVAL)
    parser.add_argument("--retry-interval", type=_float_argument, default=DEFAULT_RETRY_INTERVAL)
    try:
        args, unknown = parser.parse_known_args(arguments)
        if unknown or not all((args.source_policies, args.raw_discoveries, args.cache,
                               args.policy_id, args.user_agent)):
            raise SchedulerError("invalid request")
        interval = _duration(args.interval, minimum=MIN_INTERVAL, maximum=MAX_INTERVAL)
        retry_interval = _duration(args.retry_interval, minimum=MIN_RETRY_INTERVAL,
                                   maximum=MAX_RETRY_INTERVAL)
        target = scheduler_lock_target(args.cache)
        lock = OwnershipLock(target, wait_seconds=0)
        try:
            # Use explicit ownership cleanup: if an interrupt arrives after
            # __enter__ created and identified the sidecar but before it
            # returns, Python would not invoke a normal ``with`` __exit__.
            lock.__enter__()
            run_scheduler(
                collect=lambda: collect_wikimedia(
                    policies_path=args.source_policies, raw_path=args.raw_discoveries,
                    cache_path=args.cache, policy_id=args.policy_id,
                    user_agent=args.user_agent,
                ),
                interval=interval, retry_interval=retry_interval,
                monotonic=time.monotonic, sleep=time.sleep, output=output,
            )
        finally:
            if lock.fd is not None:
                lock.__exit__(None, None, None)
        return 0
    except KeyboardInterrupt:
        _status(output, "stopped")
        return 0
    except (argparse.ArgumentError, OSError, RuntimeError, ValueError, TopicReviewError):
        _status(output, "rejected")
        return 2
    except Exception:
        # Keep unexpected implementation failures content-free at the CLI
        # boundary, but do not turn them into an infinite retry loop.
        _status(output, "rejected")
        return 2


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
