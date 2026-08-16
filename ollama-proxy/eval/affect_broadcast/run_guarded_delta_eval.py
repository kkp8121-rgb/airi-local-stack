"""Offline, retrospective A4.2 comparison compositor; it never contacts a model."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
from copy import deepcopy
from pathlib import Path
from typing import Any

import must_act_realization as realization
import run_affect_broadcast_eval as legacy


HERE = Path(__file__).resolve().parent
LOCAL_RESULTS_DIR = HERE / "local-results"
LOCAL_OPERATOR_KEYS_DIR = HERE / "local-operator-keys"
SAFE_RUN_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
RESERVED = frozenset({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)})
REVIEW_KEYS = ("act_realization", "grounding_fidelity", "causal_expression", "continuity", "positivity_collapse", "repair", "safety_privacy", "notes")
SOURCE_NAMES = ("public-report.json", "private-review-packet.json", "local-run-receipt.json")
MAX_SOURCE = {"public-report.json": 256 * 1024, "private-review-packet.json": 8 * 1024 * 1024, "local-run-receipt.json": 16 * 1024, "private-arm-key.json": 8192}
MAX_OUTPUT = {"public-report.json": 256 * 1024, "private-review-packet.json": 512 * 1024, "local-run-receipt.json": 16 * 1024, "private-operator-key.json": 16 * 1024}


class EvalError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvalError("source artifact rejected")
        result[key] = value
    return result


def _regular(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise EvalError("source artifact rejected") from None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise EvalError("source artifact rejected")


def read_canonical_json(path: Path, limit: int) -> tuple[Any, bytes]:
    _regular(path)
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > limit or raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise EvalError("source artifact rejected") from None
    if canonical_bytes(value) != raw:
        raise EvalError("source artifact rejected")
    return value, raw


def _safe_name(name: str) -> str:
    if not SAFE_RUN_BASENAME.fullmatch(name) or name.upper() in RESERVED:
        raise EvalError("run name rejected")
    return name


def _child(root: Path, name: str, *, create: bool = False) -> Path:
    _safe_name(name)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    base = root.resolve()
    lexical = base / name
    try:
        info = lexical.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        raise EvalError("run name rejected") from None
    else:
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise EvalError("run name rejected")
    target = lexical.resolve()
    if target.parent != base:
        raise EvalError("run name rejected")
    return target


def _key_child(root: Path, run_name: str, *, create: bool = False) -> Path:
    _safe_name(run_name)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    base = root.resolve()
    lexical = base / (run_name + ".json")
    try:
        info = lexical.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        raise EvalError("run name rejected") from None
    else:
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise EvalError("run name rejected")
    target = lexical.resolve()
    if target.parent != base:
        raise EvalError("run name rejected")
    return target


def _directory(root: Path, *, create: bool = False) -> None:
    try:
        if create:
            root.mkdir(parents=True, exist_ok=True)
        info = root.lstat()
    except OSError:
        raise EvalError("custody path rejected") from None
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise EvalError("custody path rejected")


def _absent(path: Path) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError:
        raise EvalError("output path rejected") from None
    raise EvalError("output already exists")


def _blank_review() -> dict[str, None]:
    return {key: None for key in REVIEW_KEYS}


def _sha(path: Path) -> str:
    _regular(path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise EvalError("source artifact rejected") from None


def _code_hashes() -> dict[str, str]:
    return {"compositor": _sha(Path(__file__)), "legacy_runner": _sha(HERE / "run_affect_broadcast_eval.py"), "must_act_realization": _sha(HERE / "must_act_realization.py"), "broadcast_reply_act": _sha(HERE.parents[1] / "broadcast_reply_act.py"), "fixture": _sha(legacy.FIXTURE_PATH), "sidecar": _sha(legacy.REPLY_ACT_FIXTURE_PATH), "oracle": _sha(realization.ORACLE_PATH)}


def _validate_source(report: Any, packet: Any, receipt: Any, key: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fixture = legacy.load_fixture()
    execution = None
    if type(report) is not dict or report.get("schema_version") != legacy.REPORT_SCHEMA_VERSION:
        raise EvalError("source bundle rejected")
    # Recompute exact current public shape from the supplied execution evidence.
    if type(packet) is not dict or set(packet) != {"schema_version", "local_only", "synthetic_only", "human_review_required", "arm_labels_blinded", "rows"}:
        raise EvalError("source bundle rejected")
    if packet["schema_version"] != "airi.affect-broadcast-private-review.v3" or packet["local_only"] is not True or packet["synthetic_only"] is not True or packet["human_review_required"] is not True or packet["arm_labels_blinded"] is not True:
        raise EvalError("source bundle rejected")
    if type(key) is not dict or set(key) != {"schema_version", "local_only", "arm_mapping", "execution_order_offset"} or key.get("schema_version") != "airi.affect-broadcast-private-arm-key.v3" or key.get("local_only") is not True:
        raise EvalError("source bundle rejected")
    mapping = key["arm_mapping"]
    if mapping != {"a": "off", "b": "reply_act", "c": "affect_only"} or key["execution_order_offset"] != 3:
        raise EvalError("source mapping rejected")
    if type(receipt) is not dict or set(receipt) != {"schema_version", "local_only", "integrity_scope", "authenticity_claim", "artifact_sha256", "private_arm_key_custody"}:
        raise EvalError("source bundle rejected")
    if (receipt.get("schema_version") != "airi.affect-broadcast-local-run-receipt.v1" or receipt.get("local_only") is not True
            or receipt.get("integrity_scope") != "canonical_sha256_of_report_and_blinded_review_packet"
            or receipt.get("authenticity_claim") != "none_hostile_local_environment_not_addressed"
            or receipt.get("private_arm_key_custody") != "separate_operator_only_not_receipt_bound"
            or type(receipt.get("artifact_sha256")) is not dict
            or set(receipt["artifact_sha256"]) != {"public-report.json", "private-review-packet.json"}
            or any(type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value) for value in receipt["artifact_sha256"].values())):
        raise EvalError("source bundle rejected")
    # Packet rows are the historical response custody; verify their exact fixture join.
    expected = [(s["id"], t) for s in fixture["scenarios"] for t in s["turns"] if t["selected_message"] is not None]
    expected_acts = {entry["turn_id"]: entry["expected_reply_act"] for entry in legacy.load_reply_act_fixture(fixture=fixture)["entries"]}
    rows = packet["rows"]
    if type(rows) is not list or len(rows) != 122:
        raise EvalError("source bundle rejected")
    response_rows = []
    for row, (scenario_id, turn) in zip(rows, expected):
        required = ["scenario_id", "turn_id", "prior_airi", "context", "selected_message", "expected_reply_act", "response_a", "response_b", "response_c", "review_a", "review_b", "review_c"]
        if type(row) is not dict or set(row) != set(required) or row["scenario_id"] != scenario_id or row["turn_id"] != turn["id"] or row["prior_airi"] != turn["prior_airi"] or row["context"] != turn["context"] or row["selected_message"] != turn["selected_message"]:
            raise EvalError("source bundle rejected")
        if row["expected_reply_act"] != expected_acts[turn["id"]]:
            raise EvalError("source bundle rejected")
        for field in ("response_a", "response_b", "response_c"):
            if type(row[field]) is not str or not row[field] or len(row[field]) > 4000:
                raise EvalError("source bundle rejected")
        if any(type(row[field]) is not dict or set(row[field]) != set(REVIEW_KEYS) or any(value is not None for value in row[field].values()) for field in ("review_a", "review_b", "review_c")):
            raise EvalError("source bundle rejected")
        response_rows.append({"scenario_id": scenario_id, "turn_id": turn["id"], "expected_reply_act": row["expected_reply_act"], "off": row["response_a"], "reply_act": row["response_b"], "affect_only": row["response_c"]})
    execution = {"status": "triplet_transport_complete", "selected_turn_count": 122, "model_call_count": 366, "response_count_by_arm": {x: 122 for x in legacy.CONDITIONS}, "response_char_count_by_arm": {x: sum(len(r[x]) for r in response_rows) for x in legacy.CONDITIONS}, "health_profile_sha256": hashlib.sha256(legacy.canonical_bytes(legacy._expected_health_profile(legacy.EVAL_PROFILE))).hexdigest(), "private_responses": response_rows, "execution_order_offset": 3}
    legacy._validate_execution(fixture, execution, legacy.EVAL_PROFILE)
    if canonical_bytes(report) != canonical_bytes(legacy.public_report(fixture, legacy.EVAL_PROFILE, execution)):
        raise EvalError("source bundle rejected")
    hashes = {"public-report.json": hashlib.sha256(canonical_bytes(report)).hexdigest(), "private-review-packet.json": hashlib.sha256(canonical_bytes(packet)).hexdigest()}
    if receipt["artifact_sha256"] != hashes:
        raise EvalError("source bundle rejected")
    return fixture, packet, execution


def _eligible(fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    oracle = realization.load_oracle()
    all_rows = {t["id"]: t for s in fixture["scenarios"] for t in s["turns"] if t["selected_message"] is not None}
    fixed: dict[str, dict[str, Any]] = {}
    for item in oracle["entries"]:
        if item["direction"] == "fixed_korean_template" and item["postcondition"] == "exact_template_only":
            fixed[item["turn_id"]] = item
    if len(oracle["entries"]) != 31 or len(fixed) != 22 or set(fixed) - set(all_rows):
        raise EvalError("oracle rejected")
    return fixed


def _hmac(secret: bytes, domain: str, value: Any) -> str:
    return hmac.new(secret, domain.encode("ascii") + b"\0" + canonical_bytes(value), hashlib.sha256).hexdigest()


def load_source_bundle(source_name: str) -> dict[str, Any]:
    _directory(LOCAL_RESULTS_DIR)
    _directory(LOCAL_OPERATOR_KEYS_DIR)
    source = _child(LOCAL_RESULTS_DIR, source_name)
    source_key = _key_child(LOCAL_OPERATOR_KEYS_DIR, source_name)
    try:
        source_info = source.lstat()
    except OSError:
        raise EvalError("source bundle rejected") from None
    if not stat.S_ISDIR(source_info.st_mode) or stat.S_ISLNK(source_info.st_mode) or getattr(source_info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise EvalError("source bundle rejected")
    values: dict[str, Any] = {}
    raw_hashes: dict[str, str] = {}
    for name in SOURCE_NAMES:
        value, raw = read_canonical_json(source / name, MAX_SOURCE[name])
        values[name] = value
        raw_hashes[name] = hashlib.sha256(raw).hexdigest()
    key, raw = read_canonical_json(source_key, MAX_SOURCE["private-arm-key.json"])
    raw_hashes["private-arm-key.json"] = hashlib.sha256(raw).hexdigest()
    fixture, packet, execution = _validate_source(values["public-report.json"], values["private-review-packet.json"], values["local-run-receipt.json"], key)
    return {"source": source, "source_key": source_key, "raw_hashes": raw_hashes, "fixture": fixture, "packet": packet, "execution": execution, "values": values, "key": key}


def verify_source_unchanged(bundle: dict[str, Any]) -> None:
    paths = {name: bundle["source"] / name for name in SOURCE_NAMES} | {"private-arm-key.json": bundle["source_key"]}
    if any(_sha(path) != bundle["raw_hashes"][name] for name, path in paths.items()):
        raise EvalError("source changed during composition")


def compose(source_name: str, output_name: str, *, secret: bytes | None = None, comparison_id: str | None = None, bundle: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _safe_name(source_name)
    _safe_name(output_name)
    if source_name.casefold() == output_name.casefold():
        raise EvalError("source and output must differ")
    bundle = load_source_bundle(source_name) if bundle is None else bundle
    fixture, old_packet = bundle["fixture"], bundle["packet"]
    fixed = _eligible(fixture)
    secret = os.urandom(32) if secret is None else secret
    if type(secret) is not bytes or len(secret) != 32:
        raise EvalError("secret rejected")
    comparison_id = _hmac(secret, "comparison-id", [source_name, output_name])[:32] if comparison_id is None else comparison_id
    if type(comparison_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", comparison_id):
        raise EvalError("comparison id rejected")
    selected = [row for row in old_packet["rows"] if row["turn_id"] in fixed]
    ranks = sorted(((_hmac(secret, "guarded-arm-rank", row["turn_id"]), row["turn_id"]) for row in selected))
    guarded_a = {turn_id for _, turn_id in ranks[:11]}
    rows = []
    for row in selected:
        entry = fixed[row["turn_id"]]
        rendered = realization.render_must_act(row["expected_reply_act"], oracle_context={"emergency_context": True} if entry.get("emergency_context") else None)
        realization.validate_rendered_artifact(rendered, expected_act=row["expected_reply_act"]["act"])
        guarded = rendered["text"]
        control = row["response_b"]
        a_guarded = row["turn_id"] in guarded_a
        rows.append({"scenario_id": row["scenario_id"], "turn_id": row["turn_id"], "prior_airi": row["prior_airi"], "context": deepcopy(row["context"]), "selected_message": row["selected_message"], "expected_reply_act": deepcopy(row["expected_reply_act"]), "response_a": guarded if a_guarded else control, "response_b": control if a_guarded else guarded, "review_a": _blank_review(), "review_b": _blank_review()})
    packet = {"schema_version": "airi.affect-broadcast-guarded-delta-private-review.v1", "local_only": True, "synthetic_only": True, "human_review_required": True, "labels_randomized": True, "condition_identity_blinding": "partial_known_template_fingerprint", "comparison_id": comparison_id, "run_binding": _hmac(secret, "packet-binding", [comparison_id, [r["turn_id"] for r in rows]]), "rows": rows}
    source_digests = bundle["raw_hashes"]
    counts: dict[str, int] = {}
    for entry in fixed.values(): counts[entry["expected_act"]] = counts.get(entry["expected_act"], 0) + 1
    report = {"schema_version": "airi.affect-broadcast-guarded-delta-report.v1", "local_only": True, "synthetic_only": True, "operational_adoption": False, "method": "retrospective_post_hoc_deterministic_compositor", "network_calls": 0, "model_calls": 0, "passthrough_tested": False, "human_review_labels": "human_only", "condition_identity_blinding": "partial_known_template_fingerprint", "historical_source_authenticity": "legacy_receipt_integrity_plus_tracked_mapping_no_hostile_local_authenticity", "coverage": {"oracle_entries": 31, "fixed_renderable": 22, "human_review_only": 9, "non_target": 91, "fixed_act_distribution": counts, "guarded_in_a": 11, "guarded_in_b": 11}, "code_data_sha256": _code_hashes(), "source_bundle_hmac": _hmac(secret, "source-bundle", source_digests)}
    projection = {key: value for key, value in packet.items() if key != "rows"} | {"rows": [{key: value for key, value in row.items() if not key.startswith("review_")} for row in rows]}
    private_key = {"schema_version": "airi.affect-broadcast-guarded-delta-operator-key.v1", "local_only": True, "comparison_secret_hex": secret.hex(), "comparison_id": comparison_id, "guarded_arm_a_turn_ids": sorted(guarded_a), "packet_projection_hmac": _hmac(secret, "packet-projection", projection), "report_hmac": _hmac(secret, "report", report)}
    validate_output(report, packet, private_key, source_digests, bundle)
    return report, packet, private_key


def validate_output(report: Any, packet: Any, key: Any, source_digests: dict[str, str] | None = None, bundle: dict[str, Any] | None = None) -> None:
    try:
        if (type(report) is not dict or type(packet) is not dict or type(key) is not dict
                or set(report) != {"schema_version", "local_only", "synthetic_only", "operational_adoption", "method", "network_calls", "model_calls", "passthrough_tested", "human_review_labels", "condition_identity_blinding", "historical_source_authenticity", "coverage", "code_data_sha256", "source_bundle_hmac"}
                or set(packet) != {"schema_version", "local_only", "synthetic_only", "human_review_required", "labels_randomized", "condition_identity_blinding", "comparison_id", "run_binding", "rows"}
                or set(key) != {"schema_version", "local_only", "comparison_secret_hex", "comparison_id", "guarded_arm_a_turn_ids", "packet_projection_hmac", "report_hmac"}
                or report["schema_version"] != "airi.affect-broadcast-guarded-delta-report.v1" or packet["schema_version"] != "airi.affect-broadcast-guarded-delta-private-review.v1" or key["schema_version"] != "airi.affect-broadcast-guarded-delta-operator-key.v1"
                or not all(item is True for item in (report["local_only"], report["synthetic_only"], packet["local_only"], packet["synthetic_only"], packet["human_review_required"], packet["labels_randomized"], key["local_only"]))
                or report["operational_adoption"] is not False or type(report["network_calls"]) is not int or type(report["model_calls"]) is not int or report["network_calls"] != 0 or report["model_calls"] != 0
                or report["method"] != "retrospective_post_hoc_deterministic_compositor" or report["passthrough_tested"] is not False or report["human_review_labels"] != "human_only" or report["historical_source_authenticity"] != "legacy_receipt_integrity_plus_tracked_mapping_no_hostile_local_authenticity"
                or packet["condition_identity_blinding"] != "partial_known_template_fingerprint" or report["condition_identity_blinding"] != "partial_known_template_fingerprint"
                or type(key["comparison_secret_hex"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", key["comparison_secret_hex"])
                or packet["comparison_id"] != key["comparison_id"] or not re.fullmatch(r"[0-9a-f]{32}", packet["comparison_id"])):
            raise EvalError("output rejected")
        secret = bytes.fromhex(key["comparison_secret_hex"])
        rows = packet["rows"]
        if type(rows) is not list or len(rows) != 22 or type(key["guarded_arm_a_turn_ids"]) is not list or len(key["guarded_arm_a_turn_ids"]) != 11:
            raise EvalError("output rejected")
        ids = [row["turn_id"] for row in rows if type(row) is dict]
        fixed = _eligible(legacy.load_fixture())
        expected_rows = [(scenario["id"], turn) for scenario in legacy.load_fixture()["scenarios"] for turn in scenario["turns"] if turn["id"] in fixed]
        expected_a = sorted(turn_id for _, turn_id in sorted((_hmac(secret, "guarded-arm-rank", turn_id), turn_id) for turn_id in ids)[:11])
        if len(ids) != 22 or len(set(ids)) != 22 or ids != [turn["id"] for _, turn in expected_rows] or any(type(value) is not str for value in key["guarded_arm_a_turn_ids"]) or key["guarded_arm_a_turn_ids"] != expected_a or set(key["guarded_arm_a_turn_ids"]) - set(fixed): raise EvalError("output rejected")
        # The expected act and oracle-template text are the only allowed guarded material.
        source_rows = {} if bundle is None else {row["turn_id"]: row for row in bundle["packet"]["rows"]}
        for row, (scenario_id, turn) in zip(rows, expected_rows):
            if type(row) is not dict or set(row) != {"scenario_id", "turn_id", "prior_airi", "context", "selected_message", "expected_reply_act", "response_a", "response_b", "review_a", "review_b"}:
                raise EvalError("output rejected")
            if row["scenario_id"] != scenario_id or row["prior_airi"] != turn["prior_airi"] or row["context"] != turn["context"] or row["selected_message"] != turn["selected_message"] or row["expected_reply_act"] != legacy.load_reply_act_fixture(fixture=legacy.load_fixture())["entries"][[entry["turn_id"] for entry in legacy.load_reply_act_fixture(fixture=legacy.load_fixture())["entries"]].index(row["turn_id"])]["expected_reply_act"]:
                raise EvalError("output rejected")
            if any(type(row[name]) is not str or not row[name] or len(row[name]) > 4000 for name in ("scenario_id", "turn_id", "prior_airi", "selected_message", "response_a", "response_b")):
                raise EvalError("output rejected")
            if any(type(row[name]) is not dict or set(row[name]) != set(REVIEW_KEYS) or any(value is not None for value in row[name].values()) for name in ("review_a", "review_b")):
                raise EvalError("output rejected")
            rendered = realization.render_must_act(row["expected_reply_act"], oracle_context={"emergency_context": True} if row["expected_reply_act"].get("act") == "deescalate" else None)["text"]
            in_a = row["turn_id"] in key["guarded_arm_a_turn_ids"]
            if (row["response_a"] == rendered) != in_a or (row["response_b"] == rendered) == in_a:
                raise EvalError("output rejected")
            if source_rows and (row["response_b"] if in_a else row["response_a"]) != source_rows[row["turn_id"]]["response_b"]:
                raise EvalError("output rejected")
        projection = {name: value for name, value in packet.items() if name != "rows"} | {"rows": [{name: value for name, value in row.items() if not name.startswith("review_")} for row in rows]}
        if packet["run_binding"] != _hmac(secret, "packet-binding", [packet["comparison_id"], ids]) or key["packet_projection_hmac"] != _hmac(secret, "packet-projection", projection) or key["report_hmac"] != _hmac(secret, "report", report):
            raise EvalError("output rejected")
        coverage = report["coverage"]
        expected_coverage = {"oracle_entries": 31, "fixed_renderable": 22, "human_review_only": 9, "non_target": 91, "fixed_act_distribution": {"thank": 3, "close": 3, "correct": 8, "repair": 7, "deescalate": 1}, "guarded_in_a": 11, "guarded_in_b": 11}
        if type(coverage) is not dict or canonical_bytes(coverage) != canonical_bytes(expected_coverage):
            raise EvalError("output rejected")
        if type(report["code_data_sha256"]) is not dict or set(report["code_data_sha256"]) != {"compositor", "legacy_runner", "must_act_realization", "broadcast_reply_act", "fixture", "sidecar", "oracle"} or report["code_data_sha256"] != _code_hashes():
            raise EvalError("output rejected")
        if type(report["source_bundle_hmac"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", report["source_bundle_hmac"]):
            raise EvalError("output rejected")
        if source_digests is not None and report["source_bundle_hmac"] != _hmac(secret, "source-bundle", source_digests):
            raise EvalError("output rejected")
    except (KeyError, TypeError, ValueError):
        raise EvalError("output rejected") from None


def reserve(output_name: str) -> dict[str, Path]:
    _directory(LOCAL_RESULTS_DIR, create=True)
    _directory(LOCAL_OPERATOR_KEYS_DIR, create=True)
    target = _child(LOCAL_RESULTS_DIR, output_name, create=True)
    key = _key_child(LOCAL_OPERATOR_KEYS_DIR, output_name, create=True)
    stage = target.parent / (".guarded-delta-" + output_name)
    key_stage = key.parent / (".guarded-delta-key-" + output_name)
    for path in (LOCAL_RESULTS_DIR, LOCAL_OPERATOR_KEYS_DIR, target, key, stage, key_stage):
        try:
            info = path.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise EvalError("output path rejected")
        if path in (target, key, stage, key_stage):
            raise EvalError("output already exists")
    try:
        stage.mkdir()
        key_stage.mkdir()
    except OSError:
        try: stage.rmdir()
        except OSError: pass
        try: key_stage.rmdir()
        except OSError: pass
        raise EvalError("unable to reserve output") from None
    return {"target": target, "key": key, "stage": stage, "key_stage": key_stage}


def abort(reservation: dict[str, Path]) -> None:
    for path in (
        *(reservation["stage"] / name for name in (*SOURCE_NAMES, "private-operator-key.json")),
        reservation["key_stage"] / "private-operator-key.json",
    ):
        try: path.unlink()
        except OSError: pass
    for path in (reservation["stage"], reservation["key_stage"]):
        try: path.rmdir()
        except OSError: pass


def publish(reservation: dict[str, Path], report: dict[str, Any], packet: dict[str, Any], key: dict[str, Any], bundle: dict[str, Any]) -> Path:
    if type(bundle) is not dict or "raw_hashes" not in bundle:
        raise EvalError("publication failed")
    validate_output(report, packet, key, bundle["raw_hashes"], bundle)
    encoded = {"public-report.json": canonical_bytes(report), "private-review-packet.json": canonical_bytes(packet)}
    receipt = {"schema_version": "airi.affect-broadcast-guarded-delta-local-run-receipt.v1", "local_only": True, "integrity_scope": "canonical_sha256_of_report_and_private_review_packet", "authenticity_claim": "none_hostile_local_environment_not_addressed", "artifact_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in encoded.items()}, "private_operator_key_custody": "separate_operator_only_not_receipt_bound"}
    encoded["local-run-receipt.json"] = canonical_bytes(receipt)
    if any(len(value) > MAX_OUTPUT[name] for name, value in encoded.items()) or len(canonical_bytes(key)) > MAX_OUTPUT["private-operator-key.json"]:
        raise EvalError("publication failed")
    moved_key = False
    try:
        _directory(reservation["target"].parent)
        _directory(reservation["key"].parent)
        _directory(reservation["stage"])
        _directory(reservation["key_stage"])
        _absent(reservation["target"])
        _absent(reservation["key"])
        for name, value in encoded.items():
            with (reservation["stage"] / name).open("xb") as handle:
                handle.write(value); handle.flush()
                try: os.fsync(handle.fileno())
                except OSError: pass
        with (reservation["key_stage"] / "private-operator-key.json").open("xb") as handle:
            handle.write(canonical_bytes(key)); handle.flush()
            try: os.fsync(handle.fileno())
            except OSError: pass
        verify_source_unchanged(bundle)
        os.rename(reservation["key_stage"] / "private-operator-key.json", reservation["key"])
        moved_key = True
        reservation["key_stage"].rmdir()
        os.rename(reservation["stage"], reservation["target"])
    except Exception:
        for path in (*(reservation["stage"] / n for n in encoded), reservation["key_stage"] / "private-operator-key.json"):
            try: path.unlink()
            except OSError: pass
        try: reservation["stage"].rmdir()
        except OSError: pass
        try: reservation["key_stage"].rmdir()
        except OSError: pass
        if moved_key:
            try: reservation["key"].unlink()
            except OSError: pass
        raise EvalError("publication failed") from None
    return reservation["target"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--output-run", required=True)
    args = parser.parse_args()
    reservation = reserve(args.output_run)
    try:
        bundle = load_source_bundle(args.source_run)
        report, packet, key = compose(args.source_run, args.output_run, bundle=bundle)
        verify_source_unchanged(bundle)
        publish(reservation, report, packet, key, bundle)
    except Exception:
        abort(reservation)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
