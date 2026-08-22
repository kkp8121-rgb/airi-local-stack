"""Durable, fail-closed checkpoint generations for behavior training.

The module deliberately has no torch dependency so its integrity and recovery
rules are covered on the smallest CI workers as well.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class CheckpointError(ValueError):
    """A checkpoint is absent, corrupt, or belongs to another exact run."""


class CheckpointIntegrityError(CheckpointError):
    """A checkpoint cannot be trusted because bytes or structure are invalid."""


class CheckpointIdentityError(CheckpointError):
    """A valid checkpoint does not match the explicitly requested run."""


SCHEMA_VERSION = 1
TRANSACTION_INDEX_SCHEMA = "airi.behavior-checkpoint-index.v2"
CHECKPOINT_EVENT_SCHEMA = "airi.behavior-checkpoint-event.v2"
ARTIFACT_SCHEMA = "airi.behavior-adapter-artifact.v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb+") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    # Windows does not permit opening a directory this way.  Rename is still
    # atomic there; POSIX gets the stronger directory-entry durability barrier.
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_write_through(source: Path, target: Path) -> None:
    if source.resolve().anchor.lower() != target.resolve().anchor.lower():
        raise CheckpointError("checkpoint replacement must remain on one volume")
    if os.name != "nt":
        os.replace(source, target)
        _fsync_dir(target.parent)
        return
    import ctypes  # noqa: PLC0415

    move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
    move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    move_file.restype = ctypes.c_int
    if not move_file(str(source), str(target), 0x1 | 0x8):
        error = ctypes.get_last_error()
        raise CheckpointError(
            f"write-through checkpoint replacement failed with Windows error {error}")


def atomic_json(path: Path, value: dict[str, Any], *, keep_previous: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if keep_previous and path.is_file():
            previous = path.with_name(path.stem + ".prev" + path.suffix)
            previous_tmp = previous.with_name(f".{previous.name}.{uuid.uuid4().hex}.tmp")
            try:
                with previous_tmp.open("xb") as handle:
                    handle.write(path.read_bytes())
                    handle.flush()
                    os.fsync(handle.fileno())
                _replace_write_through(previous_tmp, previous)
            finally:
                previous_tmp.unlink(missing_ok=True)
        _replace_write_through(temporary, path)
        if path.read_bytes() != encoded:
            raise CheckpointIntegrityError("atomic JSON verification failed")
    finally:
        temporary.unlink(missing_ok=True)


def publish_fresh_json(path: Path, value: dict[str, Any]) -> bytes:
    """Publish an immutable canonical receipt without replacing a competitor."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "nt":
            import ctypes  # noqa: PLC0415
            move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
            move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            move_file.restype = ctypes.c_int
            # WRITE_THROUGH only; never REPLACE_EXISTING for immutable evidence.
            if not move_file(str(temporary), str(path), 0x8):
                raise CheckpointError("immutable receipt target appeared during publication")
        else:
            os.link(temporary, path)
            _fsync_dir(path.parent)
            temporary.unlink()
        if path.read_bytes() != payload:
            raise CheckpointIntegrityError("immutable receipt publication verification failed")
        return payload
    except FileExistsError as exc:
        raise CheckpointError("immutable receipt target appeared during publication") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_path(run_dir: Path, generation: str) -> Path:
    return run_dir / "checkpoints" / generation / "manifest.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(_read_regular_file_snapshot(path).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"invalid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise CheckpointError(f"JSON object required: {path}")
    return data


def _read_regular_file_snapshot(path: Path) -> bytes:
    """One no-follow regular-file observation for all authoritative evidence."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if os.name == "nt":
        import ctypes  # noqa: PLC0415
        import msvcrt  # noqa: PLC0415
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                           ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        create.restype = ctypes.c_void_p
        # GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING, OPEN_REPARSE_POINT.
        handle = create(str(path), 0x80000000, 0x1, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise CheckpointIntegrityError("checkpoint evidence cannot be opened safely")
        close = kernel.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        class _Info(ctypes.Structure):
            _fields_ = [("attributes", ctypes.c_uint32), ("pad", ctypes.c_byte * 48)]
        info = _Info()
        get_info = kernel.GetFileInformationByHandle
        get_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Info)]
        get_info.restype = ctypes.c_int
        if not get_info(handle, ctypes.byref(info)) or info.attributes & 0x400:
            close(handle)
            raise CheckpointIntegrityError("checkpoint evidence must be a regular non-reparse file")
        try:
            descriptor = msvcrt.open_osfhandle(handle, flags)
        except OSError as exc:
            close(handle)
            raise CheckpointIntegrityError("checkpoint evidence cannot be adopted safely") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CheckpointIntegrityError("checkpoint evidence must be a regular file")
            return os.read(descriptor, metadata.st_size)
        finally:
            os.close(descriptor)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CheckpointIntegrityError("checkpoint evidence cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise CheckpointIntegrityError("checkpoint evidence must be a regular non-reparse file")
        chunks: list[bytes] = []
        while block := os.read(descriptor, 1024 * 1024):
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _quarantine_file(run_dir: Path, path: Path, label: str) -> None:
    if not path.is_file():
        return
    payload = path.read_bytes()
    quarantine = run_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / f"{label}.{uuid.uuid4().hex}.{_sha256(payload)[:12]}.corrupt.json"
    _replace_write_through(path, target)
    _fsync_dir(quarantine)


def _quarantine_generation(run_dir: Path, generation: str) -> None:
    source = run_dir / "checkpoints" / generation
    if not os.path.lexists(source):
        return
    quarantine = run_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    _replace_write_through(source, quarantine / f"{generation}.{uuid.uuid4().hex}.corrupt")
    _fsync_dir(quarantine)


def _validated_index(path: Path) -> dict[str, Any]:
    index = _read_json(path)
    required_index = {"schema_version", "run_id", "latest", "previous", "previous_index_sha256"}
    if (set(index) != required_index or index.get("schema_version") != TRANSACTION_INDEX_SCHEMA
            or not isinstance(index["run_id"], str) or not index["run_id"]):
        raise CheckpointIntegrityError("checkpoint index must use the current v2 transaction schema")
    if index["previous_index_sha256"] is not None and not re.fullmatch(r"[0-9a-f]{64}", index["previous_index_sha256"]):
        raise CheckpointIntegrityError("checkpoint transaction predecessor hash invalid")
    for position in ("latest", "previous"):
        entry = index[position]
        if entry is None:
            continue
        required = {"relative_path", "manifest_sha256", "event_relative_path", "event_sha256"}
        if (not isinstance(entry, dict) or set(entry) != required
                or not isinstance(entry["relative_path"], str)
                or not re.fullmatch(r"checkpoint-[0-9]{8}", entry["relative_path"])
                or not isinstance(entry["manifest_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry["manifest_sha256"])):
            raise CheckpointIntegrityError("checkpoint index entry invalid")
        if (entry["event_relative_path"] != f"checkpoint-events/{entry['relative_path']}.json"
                or not re.fullmatch(r"[0-9a-f]{64}", entry["event_sha256"])):
            raise CheckpointIntegrityError("checkpoint event index entry invalid")
    return index


def _load_index_with_previous(run_dir: Path) -> dict[str, Any] | None:
    checkpoints = run_dir / "checkpoints"
    for name, label in (("checkpoint-index.json", "checkpoint-index"),
                        ("checkpoint-index.prev.json", "checkpoint-index-prev")):
        path = checkpoints / name
        if not path.is_file():
            continue
        try:
            return _validated_index(path)
        except CheckpointError:
            _quarantine_file(run_dir, path, label)
    return None


def _verify_index_event(run_dir: Path, entry: dict[str, Any], run_id: str) -> None:
    """An event is evidence only when its index commits its exact bytes."""
    path = run_dir / entry["event_relative_path"]
    try:
        raw = _read_regular_file_snapshot(path)
        event = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointIntegrityError("indexed checkpoint event is missing or invalid") from exc
    if raw != (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"):
        raise CheckpointIntegrityError("indexed checkpoint event is not canonical")
    if (_sha256(raw) != entry["event_sha256"] or event.get("schema_version") != CHECKPOINT_EVENT_SCHEMA
            or event.get("run_id") != run_id or event.get("generation") != entry["relative_path"]
            or event.get("checkpoint_manifest_sha256") != entry["manifest_sha256"]):
        raise CheckpointIntegrityError("indexed checkpoint event does not bind its generation")


def verify_generation(run_dir: Path, generation: str,
                      expected_pins: dict[str, Any] | None = None,
                      expected_run_id: str | None = None) -> dict[str, Any]:
    manifest_path = _manifest_path(run_dir, generation)
    manifest = _read_json(manifest_path)
    required = {"schema_version", "generation", "run_id", "payload", "pins"}
    if set(manifest) != required or manifest["schema_version"] != SCHEMA_VERSION:
        raise CheckpointIntegrityError("checkpoint manifest schema mismatch")
    if manifest["generation"] != generation or not isinstance(manifest["run_id"], str):
        raise CheckpointIntegrityError("checkpoint manifest identity mismatch")
    if expected_run_id is not None and manifest["run_id"] != expected_run_id:
        raise CheckpointIdentityError("checkpoint run_id mismatch")
    payload = manifest["payload"]
    if set(payload) != {"name", "bytes", "sha256"} or payload["name"] != "state.pt":
        raise CheckpointIntegrityError("checkpoint payload schema mismatch")
    if not isinstance(payload["bytes"], int) or not isinstance(payload["sha256"], str):
        raise CheckpointIntegrityError("checkpoint payload metadata invalid")
    payload_path = manifest_path.parent / payload["name"]
    try:
        data = _read_regular_file_snapshot(payload_path)
    except CheckpointError as exc:
        raise CheckpointIntegrityError("checkpoint payload missing") from exc
    if len(data) != payload["bytes"] or _sha256(data) != payload["sha256"]:
        raise CheckpointIntegrityError("checkpoint payload integrity mismatch")
    canonical = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if _read_regular_file_snapshot(manifest_path) != canonical:
        raise CheckpointIntegrityError("checkpoint manifest is not canonical")
    if expected_pins is not None and manifest["pins"] != expected_pins:
        raise CheckpointIdentityError("checkpoint exact pins mismatch")
    return {"manifest": manifest, "payload": data,
            "manifest_sha256": _sha256(canonical)}


def verify_artifact_directory(directory: Path,
                              expected_pins: dict[str, Any] | None = None,
                              expected_run_id: str | None = None) -> dict[str, Any]:
    manifest_path = directory / "artifact-manifest.json"
    manifest = _read_json(manifest_path)
    if (set(manifest) != {"schema_version", "run_id", "pins", "files"}
            or manifest["schema_version"] != ARTIFACT_SCHEMA
            or not isinstance(manifest["run_id"], str)
            or not isinstance(manifest["pins"], dict)
            or not isinstance(manifest["files"], list)
            or not manifest["files"]):
        raise CheckpointIntegrityError("adapter artifact manifest schema mismatch")
    if expected_run_id is not None and manifest["run_id"] != expected_run_id:
        raise CheckpointIdentityError("adapter artifact run_id mismatch")
    if expected_pins is not None and manifest["pins"] != expected_pins:
        raise CheckpointIdentityError("adapter artifact exact pins mismatch")
    canonical = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if _read_regular_file_snapshot(manifest_path) != canonical:
        raise CheckpointIntegrityError("adapter artifact manifest is not canonical")
    seen: set[str] = set()
    for entry in manifest["files"]:
        if (not isinstance(entry, dict)
                or set(entry) != {"path", "bytes", "sha256"}
                or not isinstance(entry["path"], str)
                or Path(entry["path"]).is_absolute()
                or ".." in Path(entry["path"]).parts
                or entry["path"] in seen
                or not isinstance(entry["bytes"], int)
                or entry["bytes"] < 0
                or not isinstance(entry["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise CheckpointIntegrityError("adapter artifact file entry is invalid")
        seen.add(entry["path"])
        path = directory / Path(entry["path"])
        try:
            data = _read_regular_file_snapshot(path)
        except CheckpointError as exc:
            raise CheckpointIntegrityError("adapter artifact file is missing or linked") from exc
        if len(data) != entry["bytes"] or _sha256(data) != entry["sha256"]:
            raise CheckpointIntegrityError("adapter artifact file integrity mismatch")
    actual = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name != "artifact-manifest.json"
    }
    if actual != seen:
        raise CheckpointIntegrityError("adapter artifact file inventory mismatch")
    return {"manifest": manifest, "manifest_sha256": _sha256(canonical)}


def publish_artifact_directory(stage: Path, final: Path, run_id: str,
                               pins: dict[str, Any]) -> dict[str, Any]:
    """Flush, inventory, verify, and write-through publish a final adapter."""
    if (not stage.is_dir() or stage.is_symlink() or final.exists()
            or stage.parent.resolve() != final.parent.resolve()
            or not run_id or not isinstance(pins, dict)):
        raise CheckpointError("adapter artifact publication paths are invalid")
    rows: list[dict[str, Any]] = []
    for path in sorted(stage.rglob("*")):
        if path.is_symlink():
            raise CheckpointError("adapter artifact cannot contain links")
        if path.is_file():
            _fsync_file(path)
            rows.append({
                "path": path.relative_to(stage).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path.read_bytes()),
            })
    if not rows:
        raise CheckpointError("adapter artifact is empty")
    manifest = {"schema_version": ARTIFACT_SCHEMA, "run_id": run_id,
                "pins": pins, "files": rows}
    atomic_json(stage / "artifact-manifest.json", manifest)
    _fsync_dir(stage)
    staged = verify_artifact_directory(stage, pins, run_id)
    _replace_write_through(stage, final)
    published = verify_artifact_directory(final, pins, run_id)
    if published["manifest_sha256"] != staged["manifest_sha256"]:
        raise CheckpointIntegrityError("adapter artifact changed during publication")
    return published


def publish_checkpoint(run_dir: Path, run_id: str, generation: str, payload: bytes,
                       pins: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Publish one immutable generation after staging and re-verifying it."""
    if (not run_id or not re.fullmatch(r"checkpoint-[0-9]{8}", generation)
            or not isinstance(payload, bytes) or not payload or not isinstance(pins, dict)
            or not isinstance(event, dict)):
        raise CheckpointError("checkpoint identity and payload are required")
    publish_started_ns = time.perf_counter_ns()
    publish_started_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    control_keep = _live_control_checkpoint_generations(run_dir, run_id)
    checkpoints = run_dir / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    final = checkpoints / generation
    old = _load_index_with_previous(run_dir)
    if os.path.lexists(final):
        referenced = {
            entry["relative_path"]
            for entry in ((old or {}).get("latest"), (old or {}).get("previous"))
            if isinstance(entry, dict)
        }
        if generation in referenced:
            raise CheckpointError("checkpoint generation already exists in the durable index")
        # A power cut may leave the immutable directory durable but lose the
        # later index replacement.  Preserve that orphan for diagnosis, then
        # allow deterministic replay to publish the same generation number.
        _quarantine_generation(run_dir, generation)
        orphan_event = run_dir / "checkpoint-events" / f"{generation}.json"
        if orphan_event.is_file():
            _quarantine_file(run_dir, orphan_event, "checkpoint-event")
        if os.path.lexists(final):
            raise CheckpointError("unindexed checkpoint generation could not be quarantined")
    stage = checkpoints / f".{generation}.{uuid.uuid4().hex}.tmp"
    stage.mkdir()
    state = stage / "state.pt"
    with state.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    manifest = {"schema_version": SCHEMA_VERSION, "generation": generation, "run_id": run_id,
                "payload": {"name": "state.pt", "bytes": len(payload), "sha256": _sha256(payload)},
                "pins": pins}
    atomic_json(stage / "manifest.json", manifest)
    # A staged generation must pass the same reader used by resume before it
    # becomes visible.  Use a temporary sibling run root to retain the API.
    canonical = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if (stage / "manifest.json").read_bytes() != canonical or _sha256(state.read_bytes()) != manifest["payload"]["sha256"]:
        raise CheckpointError("staged checkpoint verification failed")
    _fsync_dir(stage)
    _replace_write_through(stage, final)
    published = verify_generation(run_dir, generation, pins, run_id)
    index_path = checkpoints / "checkpoint-index.json"
    previous_index_sha256 = (_sha256(index_path.read_bytes())
                             if old is not None and index_path.is_file() else None)
    previous = None
    if old is not None:
        for position in ("latest", "previous"):
            candidate = old[position]
            if candidate is None:
                continue
            try:
                verified = verify_generation(
                    run_dir, candidate["relative_path"], pins, run_id)
                if verified["manifest_sha256"] != candidate["manifest_sha256"]:
                    raise CheckpointIntegrityError("existing checkpoint index hash mismatch")
                previous = candidate
                break
            except CheckpointIdentityError:
                raise
            except CheckpointError:
                if position == "latest":
                    _quarantine_generation(run_dir, candidate["relative_path"])
                continue
    # The immutable event is deliberately published before the authoritative
    # index. A crash here leaves an unreferenced generation/event pair which
    # recovery quarantines; it cannot create a sequence gap or self-authenticate.
    if (event.get("run_id") != run_id
            or event.get("generation") != generation):
        raise CheckpointError("checkpoint event identity mismatch")
    previous_event_sha256 = None
    if isinstance((old or {}).get("latest"), dict):
        previous_event_sha256 = old["latest"].get("event_sha256")
    event = dict(event)
    event.update({
        "schema_version": CHECKPOINT_EVENT_SCHEMA,
        "checkpoint_manifest_sha256": published["manifest_sha256"],
        "checkpoint_payload_sha256": published["manifest"]["payload"]["sha256"],
        "pins_sha256": _sha256((json.dumps(pins, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")),
        "previous_event_sha256": previous_event_sha256,
        "previous_index_sha256": previous_index_sha256,
        "publish_started_at_utc": publish_started_at_utc,
        "checkpoint_durable_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "publish_elapsed_ns": time.perf_counter_ns() - publish_started_ns,
    })
    event_path = run_dir / "checkpoint-events" / f"{generation}.json"
    event_bytes = publish_fresh_json(event_path, event)
    event_receipt = {"relative_path": event_path.relative_to(run_dir).as_posix(),
                     "sha256": _sha256(event_bytes)}
    latest = {"relative_path": generation,
              "manifest_sha256": published["manifest_sha256"],
              "event_relative_path": event_receipt["relative_path"],
              "event_sha256": event_receipt["sha256"]}
    index = {"schema_version": TRANSACTION_INDEX_SCHEMA, "run_id": run_id,
             "latest": latest, "previous": previous,
             "previous_index_sha256": previous_index_sha256}
    atomic_json(index_path, index, keep_previous=True)
    keep = {generation, previous.get("relative_path") if isinstance(previous, dict) else None}
    keep.update(control_keep)
    _retain_last_two(run_dir, keep)
    published = dict(published)
    published["event"] = event_receipt
    published["index_sha256"] = _sha256(index_path.read_bytes())
    return published


def _live_control_checkpoint_generations(run_dir: Path, run_id: str) -> set[str]:
    """Pin checkpoints named by live pause evidence until controls are archived."""
    control = run_dir / "control"
    specifications = (
        ("pause.ack.json", "airi.behavior-pause-ack.v1", {
            "schema_version", "run_id", "request_id", "checkpoint_manifest_sha256",
            "checkpoint_relative_path", "acknowledged_at_utc", "safe_to_power_off",
        }),
        ("resume.accepted.json", "airi.behavior-resume-accepted.v1", {
            "schema_version", "run_id", "request_id", "checkpoint_manifest_sha256",
            "checkpoint_relative_path",
        }),
    )
    references: list[dict[str, Any]] = []
    for filename, schema, keys in specifications:
        path = control / filename
        receipt = _read_live_control_snapshot(path)
        if receipt is None:
            continue
        if (set(receipt) != keys or receipt.get("schema_version") != schema
                or receipt.get("run_id") != run_id
                or not isinstance(receipt.get("request_id"), str)
                or not receipt["request_id"]
                or not isinstance(receipt.get("checkpoint_relative_path"), str)
                or not re.fullmatch(
                    r"checkpoint-[0-9]{8}", receipt["checkpoint_relative_path"])
                or not isinstance(receipt.get("checkpoint_manifest_sha256"), str)
                or not re.fullmatch(
                    r"[0-9a-f]{64}", receipt["checkpoint_manifest_sha256"])
                or (filename == "pause.ack.json"
                    and (receipt.get("safe_to_power_off") is not True
                         or not isinstance(receipt.get("acknowledged_at_utc"), str)
                         or not receipt["acknowledged_at_utc"]))):
            raise CheckpointIntegrityError("live pause control receipt is invalid")
        references.append(receipt)
    if len(references) == 2:
        for key in ("request_id", "checkpoint_relative_path",
                    "checkpoint_manifest_sha256"):
            if references[0][key] != references[1][key]:
                raise CheckpointIdentityError("live pause control receipts disagree")
    keep: set[str] = set()
    for receipt in references:
        generation = receipt["checkpoint_relative_path"]
        verified = verify_generation(run_dir, generation, expected_run_id=run_id)
        if verified["manifest_sha256"] != receipt["checkpoint_manifest_sha256"]:
            raise CheckpointIntegrityError("live pause control checkpoint hash mismatch")
        keep.add(generation)
    return keep


def _read_live_control_snapshot(path: Path) -> dict[str, Any] | None:
    """Read one immutable receipt snapshot while tolerating a concurrent archive move."""
    for _attempt in range(3):
        if not os.path.lexists(path):
            return None
        if path.is_symlink():
            raise CheckpointIntegrityError("live pause control receipt cannot be a link")
        if not path.is_file():
            if not os.path.lexists(path):
                continue
            raise CheckpointIntegrityError("live pause control receipt must be a regular file")
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            continue
        try:
            receipt = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CheckpointIntegrityError("live pause control receipt is invalid JSON") from exc
        if not isinstance(receipt, dict):
            raise CheckpointIntegrityError("live pause control receipt must be an object")
        return receipt
    if os.path.lexists(path):
        raise CheckpointIntegrityError("live pause control receipt could not be snapshotted")
    return None


def _retain_last_two(run_dir: Path, keep: set[str | None]) -> None:
    checkpoints = run_dir / "checkpoints"
    for candidate in checkpoints.iterdir() if checkpoints.exists() else ():
        if candidate.is_dir() and not candidate.name.startswith(".") and candidate.name not in keep:
            # Only complete, verified generations are candidates for rotation.
            try:
                verify_generation(run_dir, candidate.name)
            except CheckpointError:
                continue
            archive = run_dir / "archive"
            archive.mkdir(parents=True, exist_ok=True)
            _replace_write_through(candidate, archive / candidate.name)
    _fsync_dir(checkpoints)


def load_generation(run_dir: Path, relative_path: str, expected_pins: dict[str, Any],
                    expected_run_id: str | None = None) -> dict[str, Any]:
    """Load one explicit immutable generation; never substitute another one."""
    if (not isinstance(relative_path, str) or Path(relative_path).name != relative_path
            or not relative_path.startswith("checkpoint-")):
        raise CheckpointError("checkpoint reference invalid")
    return verify_generation(run_dir, relative_path, expected_pins, expected_run_id)


def load_latest_or_previous(run_dir: Path, expected_pins: dict[str, Any],
                            expected_run_id: str | None = None) -> dict[str, Any]:
    """Load latest, quarantining a corrupt latest before trying previous."""
    index = _load_index_with_previous(run_dir)
    if index is None:
        raise CheckpointIntegrityError("no valid checkpoint index is available")
    errors: list[str] = []
    for position in ("latest", "previous"):
        entry = index.get(position)
        if entry is None:
            continue
        generation = entry["relative_path"]
        try:
            loaded = verify_generation(run_dir, generation, expected_pins, expected_run_id)
            if loaded["manifest_sha256"] != entry["manifest_sha256"]:
                raise CheckpointError("checkpoint index manifest hash mismatch")
            _verify_index_event(run_dir, entry, loaded["manifest"]["run_id"])
            loaded["position"] = position
            return loaded
        except CheckpointIdentityError:
            raise
        except CheckpointError as exc:
            errors.append(f"{position}: {exc}")
            if position == "latest":
                _quarantine_generation(run_dir, generation)
    raise CheckpointError("no valid checkpoint: " + "; ".join(errors))
