"""Explicit human gate for creating a local Korean Wikimedia source policy."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

from topic_discovery_contract import POLICY_FILE_RE, PROMPT_RE, load_source_policies
from topic_review_contract import (CONTROL_RE, UNSAFE_TEXT_RE, OwnershipLock,
                                   TopicReviewError, canonical_json, review_output_path)
import wikimedia_topic_source as wikimedia


SOURCE_LABEL = "Korean Wikimedia"
CREATE_FLAG = "--create-wikimedia-policy"


class PolicyCreationError(ValueError):
    """Content-free source-policy creation failure."""


def _status(output: TextIO, status: str, policy_count: int = 0) -> None:
    """Emit the deliberately tiny, non-content-bearing CLI result."""
    output.write(json.dumps({"status": status, "policy_count": policy_count}, separators=(",", ":")) + "\n")
    output.flush()


def _valid_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        raise PolicyCreationError("invalid text")
    value = value.strip()
    if (not value or len(value) > limit or CONTROL_RE.search(value)
            or UNSAFE_TEXT_RE.search(value) or PROMPT_RE.search(value)):
        raise PolicyCreationError("invalid text")
    return value


def _reviewed_at(now: Callable[[], datetime]) -> str:
    value = now()
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise PolicyCreationError("invalid time")
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _policy(policy_id: str, reviewer: str, reviewed_at: str) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "source_kind": "feed",
        "source": SOURCE_LABEL,
        "feed_url": wikimedia.API_URL,
        "article_host": wikimedia.ARTICLE_HOST,
        "article_path_prefix": wikimedia.ARTICLE_PREFIX,
        "license": {
            "spdx": wikimedia.SPDX,
            "license_url": wikimedia.LICENSE_URL,
            "attribution": "Wikipedia contributors",
            "attribution_url": wikimedia.PORTAL_URL,
        },
        "approved": True,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
    }


def _canonical_existing(path: Path) -> dict[str, dict[str, Any]]:
    """Load only an exactly canonical existing registry, never repair it."""
    try:
        encoded = path.read_bytes()
        root = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyCreationError("invalid source policies") from exc
    if encoded != canonical_json(root):
        raise PolicyCreationError("noncanonical source policies")
    try:
        return load_source_policies(path)
    except TopicReviewError as exc:
        raise PolicyCreationError("invalid source policies") from exc


def _same_immutable(existing: dict[str, Any], proposed: dict[str, Any]) -> bool:
    return all(existing.get(key) == proposed[key] for key in proposed if key not in {"reviewer", "reviewed_at"})


def _confirm(input_fn: Callable[[str], str], expected: str) -> bool:
    try:
        return input_fn("") == expected
    except (EOFError, KeyboardInterrupt):
        return False


def _target_bytes(path: Path) -> bytes | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise PolicyCreationError("invalid source policies")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PolicyCreationError("invalid source policies") from exc


def _assert_unchanged(path: Path, expected: bytes | None, parent_identity: tuple[int, int]) -> None:
    try:
        current_parent = path.parent.stat()
    except OSError as exc:
        raise PolicyCreationError("invalid source policies") from exc
    if (current_parent.st_dev, current_parent.st_ino) != parent_identity:
        raise PolicyCreationError("invalid source policies")
    if _target_bytes(path) != expected:
        raise PolicyCreationError("source policies changed")


def _write_registry(
    path: Path,
    policies: list[dict[str, Any]],
    *,
    expected_target: bytes | None,
    parent_identity: tuple[int, int],
) -> None:
    root = {"schema_version": 1, "policies": policies}
    encoded = canonical_json(root)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix="source-policies-", suffix=".json", dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        # Reuse the production validator before the atomic replacement.
        loaded = load_source_policies(temporary)
        if len(loaded) != len(policies):
            raise PolicyCreationError("invalid source policies")
        _assert_unchanged(path, expected_target, parent_identity)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def run_cli(
    argv: list[str] | None = None, *, input_fn: Callable[[str], str] = input,
    output: TextIO | None = None, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    output = output or sys.stdout
    arguments = list(sys.argv[1:] if argv is None else argv)
    # This gate intentionally precedes parsing, filesystem work, and clock access.
    if CREATE_FLAG not in arguments:
        _status(output, "disabled")
        return 0
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument(CREATE_FLAG, action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--policy-id")
    parser.add_argument("--reviewer")
    try:
        args, unknown = parser.parse_known_args(arguments)
        if (
            unknown or arguments.count(CREATE_FLAG) != 1 or not args.create_wikimedia_policy
            or not args.output or not args.policy_id or not args.reviewer
            or arguments.count("--output") != 1
            or arguments.count("--policy-id") != 1
            or arguments.count("--reviewer") != 1
        ):
            raise PolicyCreationError("invalid request")
        policy_id = _valid_text(args.policy_id, 120)
        reviewer = _valid_text(args.reviewer, 500)
        target = review_output_path(args.output)
        if not POLICY_FILE_RE.fullmatch(target.name):
            raise PolicyCreationError("invalid source policies")
        # The confirmations are intentionally before all registry reads/writes.
        if not _confirm(input_fn, "approve-source") or not _confirm(input_fn, "approve-license") or not _confirm(input_fn, policy_id):
            _status(output, "cancelled")
            return 0
        proposed = _policy(policy_id, reviewer, _reviewed_at(now))
        lock = OwnershipLock(target, wait_seconds=0)
        terminal_status: str
        policy_count: int
        try:
            lock.__enter__()
            # Confirm that the path still resolves to the same approved local
            # target after the potentially long human confirmation step.
            if review_output_path(args.output) != target:
                raise PolicyCreationError("invalid source policies")
            parent_stat = target.parent.stat()
            parent_identity = (parent_stat.st_dev, parent_stat.st_ino)
            expected_target = _target_bytes(target)
            if target.exists():
                existing = _canonical_existing(target)
            else:
                existing = {}
            old = existing.get(policy_id)
            if old is not None:
                if old.get("reviewer") == reviewer and _same_immutable(old, proposed):
                    terminal_status = "already-present"
                    policy_count = len(existing)
                else:
                    raise PolicyCreationError("policy collision")
            else:
                policies = list(existing.values()) + [proposed]
                policies.sort(key=lambda value: value["policy_id"])
                _write_registry(
                    target,
                    policies,
                    expected_target=expected_target,
                    parent_identity=parent_identity,
                )
                terminal_status = "created"
                policy_count = len(policies)
        finally:
            if lock.fd is not None:
                lock.__exit__(None, None, None)
        _status(output, terminal_status, policy_count)
        return 0
    except (argparse.ArgumentError, OSError, RuntimeError, ValueError, TopicReviewError):
        _status(output, "rejected")
        return 2
    except Exception:
        _status(output, "rejected")
        return 2


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
