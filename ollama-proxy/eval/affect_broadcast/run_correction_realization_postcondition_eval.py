"""A4.5 zero-network retrospective correction-realization scorer.

Default invocation reads tracked oracle inputs only.  Explicit evaluation is
restricted to the pinned A4.4 local run and publishes content-free aggregates.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
RESULTS = HERE / "local-results"
KEYS = HERE / "local-operator-keys"
SAFE_RUN = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
OUTPUT_FILES = ("public-report.json", "private-detail.json", "local-run-receipt.json")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RetrospectiveEvalError("a4.5 evaluator unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        raise RetrospectiveEvalError("a4.5 evaluator unavailable") from None
    return module


class RetrospectiveEvalError(ValueError):
    """Sanitized local-evaluation failure."""


realization = _load_module("airi_a45_realization", HERE / "correction_target_realization.py")


def _invalid_source() -> RetrospectiveEvalError:
    return RetrospectiveEvalError("a4.5 source rejected")


def _invalid_output() -> RetrospectiveEvalError:
    return RetrospectiveEvalError("a4.5 output rejected")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _load(path: Path) -> Any:
    try:
        info_before = path.stat()
        if not (0 < info_before.st_size <= MAX_SOURCE_BYTES):
            raise _invalid_source()
        raw = path.read_bytes()
        info_after = path.stat()
        if (
            info_before.st_size != info_after.st_size
            or (info_before.st_dev, info_before.st_ino)
            != (info_after.st_dev, info_after.st_ino)
        ):
            raise _invalid_source()
        return json.loads(raw.decode("utf-8"))
    except RetrospectiveEvalError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise _invalid_source() from None


def _a44():
    return _load_module(
        "airi_a45_a44_source", HERE / "run_correction_target_ab_eval.py"
    )


def eligibility() -> dict[str, object]:
    oracle = realization.load_oracle()
    return {
        "schema_version": "airi.correction-realization-postcondition-eligibility.v1",
        "decision": "eligible_for_zero_network_retrospective_scoring",
        "entry_count": len(oracle["entries"]),
        "new_proxy_post_count": 0,
        "new_model_call_count": 0,
        "operational_adoption": False,
    }


def _safe_run(name: object) -> str:
    if (
        type(name) is not str
        or SAFE_RUN.fullmatch(name) is None
        or name.upper() in RESERVED
        or name.casefold() == realization.SOURCE_RUN.casefold()
    ):
        raise _invalid_output()
    return name


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return bool(
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _validate_roots(results: Path, keys: Path) -> None:
    for root in (results, keys):
        try:
            if (
                not root.is_dir()
                or root.resolve() != root.absolute()
                or _is_reparse(root)
            ):
                raise _invalid_source()
        except OSError:
            raise _invalid_source() from None


def _hash64(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_source(
    report: object, packet: object, receipt: object, key: object,
    oracle: object,
) -> None:
    a44 = _a44()
    report_keys = {
        "schema_version", "runner_version", "protocol_id",
        "supersedes_packet_schema", "superseded_schema_status",
        "cohort_count", "model_call_count", "fixture_sha256",
        "reply_act_fixture_sha256", "oracle_sha256", "eligibility",
        "transport_contract", "profile_sha256", "health_profile_sha256",
        "operational_adoption",
    }
    expected_transport = {
        "scope": "normal_cli_path_not_external_transport_proof",
        "literal_loopback": True,
        "no_proxy": True,
        "no_redirect": True,
        "bounded": True,
    }
    expected_profile_hash = hashlib.sha256(
        canonical_bytes(a44.base.EVAL_PROFILE)
    ).hexdigest()
    expected_health_hash = hashlib.sha256(
        canonical_bytes(a44.base._expected_health_profile(a44.base.EVAL_PROFILE))
    ).hexdigest()
    if (
        type(report) is not dict
        or set(report) != report_keys
        or report.get("schema_version") != "airi.correction-target-public-report.v2"
        or report.get("runner_version") != "1.1.0"
        or report.get("protocol_id") != realization.A44_PROTOCOL_VERSION
        or report.get("supersedes_packet_schema")
        != "airi.correction-target-blinded-review.v1"
        or report.get("superseded_schema_status")
        != "obsolete_incomplete_review_context"
        or type(report.get("cohort_count")) is not int
        or report["cohort_count"] != len(oracle["entries"])
        or type(report.get("model_call_count")) is not int
        or report["model_call_count"] != len(oracle["entries"]) * 2
        or report.get("fixture_sha256") != realization.BASE_FIXTURE_SHA256
        or report.get("reply_act_fixture_sha256")
        != realization.REPLY_ACT_FIXTURE_SHA256
        or report.get("oracle_sha256") != realization.A43_ORACLE_SHA256
        or report.get("eligibility") is not True
        or report.get("transport_contract") != expected_transport
        or report.get("profile_sha256") != expected_profile_hash
        or report.get("health_profile_sha256") != expected_health_hash
        or report.get("operational_adoption") is not False
    ):
        raise _invalid_source()
    try:
        clean_packet = a44.validate_packet(packet)
    except Exception:
        raise _invalid_source() from None
    packet_digest = hashlib.sha256(canonical_bytes(clean_packet)).hexdigest()
    if packet_digest != realization.SOURCE_PACKET_SHA256:
        raise _invalid_source()
    receipt_keys = {
        "schema_version", "protocol_id", "integrity_only_not_authenticity",
        "hostile_local_authenticity_not_addressed", "v1_review_artifacts_obsolete",
        "artifacts",
    }
    expected_source_artifacts = {
        "private-review-packet.json": packet_digest,
        "public-report.json": hashlib.sha256(canonical_bytes(report)).hexdigest(),
    }
    if (
        type(receipt) is not dict
        or set(receipt) != receipt_keys
        or receipt.get("schema_version")
        != "airi.correction-target-local-run-receipt.v2"
        or receipt.get("protocol_id") != realization.A44_PROTOCOL_VERSION
        or receipt.get("integrity_only_not_authenticity") is not True
        or receipt.get("hostile_local_authenticity_not_addressed") is not True
        or receipt.get("v1_review_artifacts_obsolete") is not True
        or receipt.get("artifacts") != expected_source_artifacts
    ):
        raise _invalid_source()
    key_keys = {
        "schema_version", "protocol_id", "local_only", "pair_mappings",
        "execution_pair_orders", "execution_row_order",
    }
    if (
        type(key) is not dict
        or set(key) != key_keys
        or key.get("schema_version") != "airi.correction-target-operator-key.v2"
        or key.get("protocol_id") != realization.A44_PROTOCOL_VERSION
        or key.get("local_only") is not True
        or type(key.get("pair_mappings")) is not list
        or len(key["pair_mappings"]) != len(oracle["entries"])
        or type(key.get("execution_pair_orders")) is not list
        or len(key["execution_pair_orders"]) != len(oracle["entries"])
        or key["execution_pair_orders"].count("CT") != len(oracle["entries"]) // 2
        or key["execution_pair_orders"].count("TC") != len(oracle["entries"]) // 2
        or type(key.get("execution_row_order")) is not list
        or sorted(key["execution_row_order"]) != list(range(len(oracle["entries"])))
    ):
        raise _invalid_source()
    for ordinal, (mapping, expected) in enumerate(
        zip(key["pair_mappings"], oracle["entries"]), 1
    ):
        if (
            type(mapping) is not dict
            or set(mapping) != {"pair", "labels", "target_id", "direction"}
            or mapping.get("pair") != ordinal
            or type(mapping.get("labels")) is not dict
            or set(mapping["labels"]) != {"A", "B"}
            or set(mapping["labels"].values()) != {"control", "target"}
            or mapping.get("target_id") != expected["target_id"]
            or mapping.get("direction") != expected["direction"]
        ):
            raise _invalid_source()


def _score(
    report: dict[str, Any], packet: dict[str, Any], receipt: dict[str, Any],
    key: dict[str, Any], oracle: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    counts = {
        "both_pass": 0,
        "target_only": 0,
        "control_only": 0,
        "neither": 0,
        "control_pass": 0,
        "target_pass": 0,
        "fallback_pass": 0,
    }
    details: list[dict[str, object]] = []
    for ordinal, (row, expected, mapping) in enumerate(
        zip(packet["pairs"], oracle["entries"], key["pair_mappings"]), 1
    ):
        labels = mapping["labels"]
        by_label: dict[str, dict[str, object]] = {}
        for label in ("A", "B"):
            by_label[label] = realization.evaluate(
                expected["turn_id"], expected["target_id"], expected["direction"],
                row[f"response_{label.lower()}"], oracle,
            )
        control_result = by_label["A"] if labels["A"] == "control" else by_label["B"]
        target_result = by_label["A"] if labels["A"] == "target" else by_label["B"]
        fallback = realization.fallback_for(
            expected["turn_id"], expected["target_id"], expected["direction"], oracle
        )
        fallback_result = realization.evaluate(
            expected["turn_id"], expected["target_id"], expected["direction"],
            fallback["text"], oracle,
        )
        control_pass = control_result["decision"] == "candidate_satisfies_structural_postcondition"
        target_pass = target_result["decision"] == "candidate_satisfies_structural_postcondition"
        fallback_pass = fallback_result["decision"] == "candidate_satisfies_structural_postcondition"
        counts["control_pass"] += int(control_pass)
        counts["target_pass"] += int(target_pass)
        counts["fallback_pass"] += int(fallback_pass)
        bucket = (
            "both_pass" if control_pass and target_pass
            else "control_only" if control_pass
            else "target_only" if target_pass
            else "neither"
        )
        counts[bucket] += 1
        details.append({
            "pair_ordinal": ordinal,
            "control_pass": control_pass,
            "target_pass": target_pass,
            "fallback_pass": fallback_pass,
            "control_failure_mask": control_result["failure_mask"],
            "target_failure_mask": target_result["failure_mask"],
        })
    public = {
        "schema_version": "airi.correction-realization-postcondition-public.v1",
        "source_protocol_id": realization.A44_PROTOCOL_VERSION,
        "pair_count": len(oracle["entries"]),
        "counts": counts,
        "lexical_only": True,
        "new_proxy_post_count": 0,
        "new_model_call_count": 0,
        "strategy_selection": "not_evaluated",
        "operational_adoption": False,
        "source_operator_key_receipt_bound": False,
        "integrity_only_not_authenticity": True,
    }
    detail = {
        "schema_version": "airi.correction-realization-postcondition-detail.v1",
        "synthetic_only": True,
        "pairs": details,
    }
    receipt_out = {
        "schema_version": "airi.correction-realization-postcondition-receipt.v1",
        "source_operator_key_receipt_bound": False,
        "integrity_only_not_authenticity": True,
        "hostile_local_authenticity_not_addressed": True,
        "consumed_artifacts": {
            "source_report": hashlib.sha256(canonical_bytes(report)).hexdigest(),
            "source_packet": hashlib.sha256(canonical_bytes(packet)).hexdigest(),
            "source_receipt": hashlib.sha256(canonical_bytes(receipt)).hexdigest(),
            "source_operator_key": hashlib.sha256(canonical_bytes(key)).hexdigest(),
            "realization_oracle": hashlib.sha256(canonical_bytes(oracle)).hexdigest(),
            "realization_code": hashlib.sha256(
                (HERE / "correction_target_realization.py").read_bytes()
            ).hexdigest(),
            "retrospective_runner_code": hashlib.sha256(
                (HERE / "run_correction_realization_postcondition_eval.py").read_bytes()
            ).hexdigest(),
            "a44_runner_code": hashlib.sha256(
                (HERE / "run_correction_target_ab_eval.py").read_bytes()
            ).hexdigest(),
            "a44_base_runner_code": hashlib.sha256(
                (HERE / "run_affect_broadcast_eval.py").read_bytes()
            ).hexdigest(),
            "a43_oracle_code": hashlib.sha256(
                (HERE / "correction_target.py").read_bytes()
            ).hexdigest(),
        },
        "artifacts": {
            "public-report.json": hashlib.sha256(canonical_bytes(public)).hexdigest(),
            "private-detail.json": hashlib.sha256(canonical_bytes(detail)).hexdigest(),
        },
    }
    return public, detail, receipt_out


def _reserve_output(run: str, results: Path) -> dict[str, object]:
    run = _safe_run(run)
    if not results.is_dir() or results.resolve() != results.absolute() or _is_reparse(results):
        raise _invalid_output()
    stage_name = f".reservation-a45-{run}"
    forbidden = {run.casefold(), stage_name.casefold()}
    try:
        if any(child.name.casefold() in forbidden for child in results.iterdir()):
            raise _invalid_output()
        target = results / run
        stage = results / stage_name
        os.mkdir(stage)
        root_info = results.stat()
        stage_info = stage.stat()
    except RetrospectiveEvalError:
        raise
    except OSError:
        raise _invalid_output() from None
    return {
        "run": run,
        "results": results.absolute(),
        "target": target,
        "stage": stage,
        "root_identity": (root_info.st_dev, root_info.st_ino),
        "stage_identity": (stage_info.st_dev, stage_info.st_ino),
    }


def _revalidate_reservation(reservation: object) -> None:
    required = {
        "run", "results", "target", "stage", "root_identity", "stage_identity"
    }
    if type(reservation) is not dict or set(reservation) != required:
        raise _invalid_output()
    run = _safe_run(reservation["run"])
    results = reservation["results"]
    if (
        not isinstance(results, Path)
        or results != results.absolute()
        or reservation["target"] != results / run
        or reservation["stage"] != results / f".reservation-a45-{run}"
        or reservation["target"].exists()
    ):
        raise _invalid_output()
    try:
        root_info = results.lstat()
        stage_info = reservation["stage"].lstat()
    except OSError:
        raise _invalid_output() from None
    if (
        _is_reparse(results)
        or _is_reparse(reservation["stage"])
        or (root_info.st_dev, root_info.st_ino) != reservation["root_identity"]
        or (stage_info.st_dev, stage_info.st_ino) != reservation["stage_identity"]
        or not stat.S_ISDIR(stage_info.st_mode)
    ):
        raise _invalid_output()


def _write_stage_artifact(
    reservation: dict[str, object], name: str, data: bytes
) -> None:
    if name not in OUTPUT_FILES or not (0 < len(data) <= MAX_OUTPUT_BYTES):
        raise _invalid_output()
    _revalidate_reservation(reservation)
    path = reservation["stage"] / name
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        raise _invalid_output() from None


def _abort_reservation(reservation: object) -> None:
    try:
        _revalidate_reservation(reservation)
    except (RetrospectiveEvalError, OSError):
        return
    stage = reservation["stage"]
    for name in OUTPUT_FILES:
        try:
            (stage / name).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return
    try:
        stage.rmdir()
    except OSError:
        pass


def _publish(
    run: str, results: Path, public: dict[str, Any], detail: dict[str, Any],
    receipt: dict[str, Any],
) -> Path:
    reservation = _reserve_output(run, results)
    encoded = {
        "public-report.json": canonical_bytes(public),
        "private-detail.json": canonical_bytes(detail),
        "local-run-receipt.json": canonical_bytes(receipt),
    }
    try:
        for name in OUTPUT_FILES:
            _write_stage_artifact(reservation, name, encoded[name])
        _revalidate_reservation(reservation)
        os.rename(reservation["stage"], reservation["target"])
        return reservation["target"]
    except Exception:
        _abort_reservation(reservation)
        raise


def evaluate(
    source_run: str, run: str, *, results: Path = RESULTS, keys: Path = KEYS,
) -> dict[str, object]:
    if source_run != realization.SOURCE_RUN:
        raise _invalid_source()
    _safe_run(run)
    _validate_roots(results, keys)
    source = results / source_run
    packet = _load(source / "private-review-packet.json")
    report = _load(source / "public-report.json")
    source_receipt = _load(source / "local-run-receipt.json")
    key = _load(keys / f"{source_run}.json")
    oracle = realization.load_oracle()
    _validate_source(
        report, packet, source_receipt, key, oracle,
    )
    public, detail, receipt = _score(
        report, packet, source_receipt, key, oracle
    )
    _publish(run, results, public, detail, receipt)
    return public


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--source-run")
    parser.add_argument("--run")
    args = parser.parse_args(argv)
    if not args.evaluate:
        if args.source_run or args.run:
            parser.error("--source-run and --run require --evaluate")
        print(json.dumps(eligibility(), ensure_ascii=False, sort_keys=True))
        return 0
    if not args.source_run or not args.run:
        parser.error("--evaluate requires --source-run and --run")
    try:
        result = evaluate(args.source_run, args.run)
    except RetrospectiveEvalError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
