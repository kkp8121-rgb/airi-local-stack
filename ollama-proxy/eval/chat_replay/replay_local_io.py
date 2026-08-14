"""Ignored-directory path and atomic-write helpers for local chat replay."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterable


HERE = Path(__file__).resolve().parent


def _is_reparse(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _secure_inside(path: Path, parent: Path) -> bool:
    candidate = Path(os.path.abspath(path))
    trusted_parent = Path(os.path.abspath(parent))
    trusted_root = Path(os.path.abspath(HERE))
    try:
        candidate.relative_to(trusted_parent)
        relative = candidate.relative_to(trusted_root)
    except ValueError:
        return False
    current = trusted_root
    if _is_reparse(current):
        return False
    for part in relative.parts:
        current /= part
        if os.path.lexists(current) and _is_reparse(current):
            return False
    return True


def _atomic_text(path: Path, text: str, parent: Path) -> None:
    if not _secure_inside(path, parent):
        raise RuntimeError("output path escaped its local ignored directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _secure_inside(path, parent):
        raise RuntimeError("output path became unsafe")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
    try:
        if not _secure_inside(path, parent):
            raise RuntimeError("output path became unsafe")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_atomic_json(
    path: Path, value: object, parent: Path, *, max_bytes: int | None = None,
) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if max_bytes is not None and len(text.encode("utf-8")) > max_bytes:
        raise ValueError("serialized JSON exceeds the configured size limit")
    _atomic_text(path, text, parent)


def write_atomic_jsonl(
    path: Path, rows: Iterable[dict[str, object]], parent: Path,
) -> None:
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    _atomic_text(path, text, parent)
