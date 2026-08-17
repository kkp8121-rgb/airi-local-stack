"""A4.4 fresh, blinded eight-pair correction-target evaluator.

This module is intentionally independent from historical A4 output.  Without
``--execute`` it only validates the pinned inputs and writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ENDPOINT = "http://127.0.0.1:11435/api/chat"
RUNNER_VERSION = "1.1.0"
PROTOCOL_ID = "a44_correction_target_contextual_review_v2"
SAFE_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
RESERVED = frozenset({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)})
MAX_PACKET_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_CHARS = 4000
RESULTS = HERE / "local-results"
KEYS = HERE / "local-operator-keys"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("required local evaluation module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _load("airi_a44_base", HERE / "run_affect_broadcast_eval.py")
targets = _load("airi_a44_targets", HERE / "correction_target.py")


class EvalError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _serializer(candidate: dict[str, str]) -> str:
    """Use the shared broadcaster serializer; absence is an eligibility failure."""
    path = ROOT / "broadcast_correction_target.py"
    if not path.is_file(): raise EvalError("shared correction candidate serializer is unavailable")
    module = _load("airi_a44_broadcast_target", path)
    value = module.serialize_correction_target_candidate(candidate)
    if not isinstance(value, str): raise EvalError("correction candidate serializer is malformed")
    return value


def load_cohort() -> list[dict[str, Any]]:
    fixture = base.load_fixture()
    sidecar = base.load_reply_act_fixture(fixture=fixture)
    oracle = targets.load_oracle()
    reply = {row["turn_id"]: row["expected_reply_act"] for row in sidecar["entries"]}
    turns = {turn["id"]: (scenario, index, turn) for scenario, index, turn in base._selected_turns(fixture)}
    rows: list[dict[str, Any]] = []
    for entry in oracle["entries"]:  # oracle order is the experimental order
        turn_id = entry["turn_id"]
        if turn_id not in turns or turn_id not in reply:
            raise EvalError("pinned oracle membership is incomplete")
        candidate = {"schema_version": targets.CANDIDATE_SCHEMA_VERSION, "act": "correct", "target_id": entry["target_id"], "direction": entry["direction"], "evidence_basis": entry["evidence_basis"]}
        targets.validate_target_for_turn(turn_id, candidate, oracle)
        scenario, index, turn = turns[turn_id]
        if reply[turn_id].get("act") != "correct":
            raise EvalError("oracle turn is not a correction reply-act row")
        rows.append({"scenario": scenario, "turn_index": index, "turn": turn, "reply_act": reply[turn_id], "candidate": candidate})
    if len(rows) != 8 or [r["turn"]["id"] for r in rows] != [e["turn_id"] for e in oracle["entries"]]:
        raise EvalError("correction cohort must be the exact eight-row oracle")
    return rows


def pair_requests(row: dict[str, Any]) -> dict[str, bytes]:
    profile = base.validate_profile(base.EVAL_PROFILE)
    control = base.triplet_requests(row["scenario"], row["turn_index"], profile, row["reply_act"])["reply_act"]
    candidate = _serializer(row["candidate"])
    try:
        value = json.loads(control)
        messages = value["messages"]
        user = max(i for i, item in enumerate(messages) if item.get("role") == "user")
        reply_name = base._reply_act().REPLY_ACT_MESSAGE_NAME
        reply = max(i for i, item in enumerate(messages[:user]) if item.get("role") == "system" and item.get("name") == reply_name)
        value["messages"].insert(reply + 1, {"role": "system", "name": "airi_synthetic_correction_target", "content": candidate})
        target = canonical_bytes(value)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise EvalError("control request is malformed") from error
    assert_target_only_delta(control, target, candidate)
    return {"control": control, "target": target}


def assert_target_only_delta(control: bytes, target: bytes, candidate: str) -> None:
    try:
        a, b = json.loads(control), json.loads(target)
        if {k: v for k, v in a.items() if k != "messages"} != {k: v for k, v in b.items() if k != "messages"}:
            raise EvalError("request options differ")
        am, bm = a["messages"], b["messages"]
        users = [i for i, m in enumerate(am) if m.get("role") == "user"]
        reply_name = base._reply_act().REPLY_ACT_MESSAGE_NAME
        reply = max(i for i, m in enumerate(am[:users[-1]]) if m.get("role") == "system" and m.get("name") == reply_name)
        inserted = {"role": "system", "name": "airi_synthetic_correction_target", "content": candidate}
        if len(bm) != len(am) + 1 or bm[reply + 1] != inserted or am[:reply + 1] != bm[:reply + 1] or am[reply + 1:] != bm[reply + 2:]:
            raise EvalError("target request differs outside its one candidate message")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, EvalError): raise
        raise EvalError("request pair is malformed") from error


def eligibility() -> dict[str, Any]:
    rows = load_cohort()
    bodies = [pair_requests(row) for row in rows]
    return {"eligible": True, "protocol_id": PROTOCOL_ID, "cohort_count": len(rows), "fixture_sha256": base.FIXTURE_SHA256, "reply_act_fixture_sha256": base.REPLY_ACT_FIXTURE_SHA256, "oracle_sha256": targets.ORACLE_SHA256, "operational_adoption": False}


def _response(value: Any) -> str:
    try: return base._response_content(base._transport_result(value, "model"))
    except Exception as error: raise EvalError("bounded assistant response required") from error


def _shuffle(values: list[Any], randbelow: Callable[[int], int]) -> None:
    for index in range(len(values) - 1, 0, -1):
        other = randbelow(index + 1)
        if type(other) is not int or not 0 <= other <= index: raise EvalError("CSPRNG returned an invalid index")
        values[index], values[other] = values[other], values[index]


def execute(endpoint: str, transport: Callable[[str, str, bytes | None, dict[str, str]], Any], *, randbelow: Callable[[int], int] = secrets.randbelow) -> dict[str, Any]:
    base.ensure_loopback(endpoint)
    rows = load_cohort(); profile = base.validate_profile(base.EVAL_PROFILE)
    before = base._health_profile(base._transport_result(transport("GET", base._health_url(endpoint), None, {}), "health"), profile)
    pair_orders = ["CT"] * 4 + ["TC"] * 4
    # Fisher-Yates with CSPRNG: rows and within-pair arm order are both hidden.
    _shuffle(pair_orders, randbelow)
    if pair_orders.count("CT") != 4 or pair_orders.count("TC") != 4: raise EvalError("within-pair order is not exactly balanced")
    order = list(range(8))
    _shuffle(order, randbelow)
    raw: list[dict[str, Any]] = []
    for ordinal in order:
        bodies = pair_requests(rows[ordinal]); responses = {}
        for arm in pair_orders[ordinal]:
            name = "control" if arm == "C" else "target"
            responses[name] = _response(transport("POST", endpoint, bodies[name], {"x-airi-turn-origin": "local-evaluation"}))
        raw.append({"ordinal": ordinal, "responses": responses})
    after = base._health_profile(base._transport_result(transport("GET", base._health_url(endpoint), None, {}), "health"), profile)
    if before != after: raise EvalError("loopback profile changed during execution")
    return {"schema_version":"airi.correction-target-execution.v1", "rows": raw, "orders": pair_orders, "row_order": order, "health_profile_sha256": hashlib.sha256(canonical_bytes(before)).hexdigest(), "transport_contract":{"scope":"normal_cli_path_not_external_transport_proof","literal_loopback":True,"no_proxy":True,"no_redirect":True,"bounded":True}}


def build_packet(execution: dict[str, Any], *, randbelow: Callable[[int], int] = secrets.randbelow) -> tuple[dict[str, Any], dict[str, Any]]:
    execution = validate_execution(execution); rows = load_cohort(); observed = {x["ordinal"]: x["responses"] for x in execution["rows"]}
    packet_rows=[]; key_rows=[]
    for ordinal, row in enumerate(rows):
        labels = ["A", "B"]
        draw=randbelow(2)
        if type(draw) is not int or draw not in {0,1}: raise EvalError("CSPRNG label draw is invalid")
        if draw: labels.reverse()
        mapping = dict(zip(labels, ("control", "target")))
        blank = {"target_grounding": None, "correction_direction": None, "act": None, "continuity": None, "safety": None, "notes": None}
        turn = row["turn"]
        packet_rows.append({
            "pair": ordinal + 1,
            "review_context": {
                "prior_airi": turn["prior_airi"],
                "selected_message": turn["selected_message"],
                "screen": turn["context"]["screen"],
                "topic": turn["context"]["topic"],
                "expected_act": "correct",
            },
            "response_a": observed[ordinal][mapping["A"]],
            "response_b": observed[ordinal][mapping["B"]],
            "review_a": deepcopy(blank),
            "review_b": deepcopy(blank),
            "preference_or_tie": None,
        })
        key_rows.append({"pair": ordinal + 1, "labels": mapping, "target_id": row["candidate"]["target_id"], "direction": row["candidate"]["direction"]})
    packet={"schema_version":"airi.correction-target-blinded-review.v2","local_only":True,"synthetic_only":True,"locked_review_overlay_required":True,"pairs":packet_rows}
    key={"schema_version":"airi.correction-target-operator-key.v2","protocol_id":PROTOCOL_ID,"local_only":True,"pair_mappings":key_rows,"execution_pair_orders":execution["orders"],"execution_row_order":execution["row_order"]}
    return packet,key


def validate_execution(value: Any) -> dict[str, Any]:
    keys={"schema_version","rows","orders","row_order","health_profile_sha256","transport_contract"}
    if type(value) is not dict or set(value)!=keys or value["schema_version"]!="airi.correction-target-execution.v1": raise EvalError("execution schema is malformed")
    if not isinstance(value["orders"],list) or len(value["orders"])!=8 or value["orders"].count("CT")!=4 or value["orders"].count("TC")!=4: raise EvalError("execution order is malformed")
    if type(value["row_order"]) is not list or sorted(value["row_order"]) != list(range(8)): raise EvalError("execution row order is malformed")
    if not isinstance(value["health_profile_sha256"],str) or re.fullmatch(r"[0-9a-f]{64}", value["health_profile_sha256"]) is None or value["health_profile_sha256"] != hashlib.sha256(canonical_bytes(base._expected_health_profile(base.EVAL_PROFILE))).hexdigest(): raise EvalError("execution health binding is malformed")
    if value["transport_contract"] != {"scope":"normal_cli_path_not_external_transport_proof","literal_loopback":True,"no_proxy":True,"no_redirect":True,"bounded":True}: raise EvalError("execution transport contract is malformed")
    if not isinstance(value["rows"],list) or len(value["rows"])!=8: raise EvalError("execution rows are malformed")
    if [item.get("ordinal") if type(item) is dict else None for item in value["rows"]] != value["row_order"]: raise EvalError("execution rows are incomplete")
    for item in value["rows"]:
        if type(item) is not dict or set(item)!={"ordinal","responses"} or type(item["ordinal"]) is not int or type(item["responses"]) is not dict or set(item["responses"])!={"control","target"}: raise EvalError("execution response is malformed")
        for response in item["responses"].values():
            if not isinstance(response,str) or not 1<=len(response)<=MAX_RESPONSE_CHARS or response != response.strip() or any(ord(char)<32 and char != "\n" for char in response): raise EvalError("execution response is malformed")
    return deepcopy(value)


_REVIEW_KEYS = {"target_grounding", "correction_direction", "act", "continuity", "safety", "notes"}


def validate_packet(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value)!={"schema_version","local_only","synthetic_only","locked_review_overlay_required","pairs"} or value["schema_version"]!="airi.correction-target-blinded-review.v2" or value["local_only"] is not True or value["synthetic_only"] is not True or value["locked_review_overlay_required"] is not True or type(value["pairs"]) is not list or len(value["pairs"])!=8:
        raise EvalError("review packet schema is malformed")
    source_rows = load_cohort()
    for ordinal,pair in enumerate(value["pairs"],1):
        if type(pair) is not dict or set(pair)!={"pair","review_context","response_a","response_b","review_a","review_b","preference_or_tie"} or pair["pair"]!=ordinal or pair["preference_or_tie"] is not None:
            raise EvalError("review packet pair is malformed")
        source_turn = source_rows[ordinal - 1]["turn"]
        expected_context = {
            "prior_airi": source_turn["prior_airi"],
            "selected_message": source_turn["selected_message"],
            "screen": source_turn["context"]["screen"],
            "topic": source_turn["context"]["topic"],
            "expected_act": "correct",
        }
        if pair["review_context"] != expected_context:
            raise EvalError("review packet context is not the pinned synthetic source")
        for name in ("response_a","response_b"):
            if not isinstance(pair[name],str) or not 1<=len(pair[name])<=MAX_RESPONSE_CHARS: raise EvalError("review packet response is malformed")
        for name in ("review_a","review_b"):
            if type(pair[name]) is not dict or set(pair[name])!=_REVIEW_KEYS or any(item is not None for item in pair[name].values()): raise EvalError("review packet must be blank")
    return deepcopy(value)


def validate_locked_overlay(value: Any, packet: Any) -> dict[str, Any]:
    clean_packet=validate_packet(packet)
    if type(value) is not dict or set(value)!={"schema_version","locked","packet_sha256","reviews"} or value.get("schema_version")!="airi.correction-target-review-overlay.v2" or value.get("locked") is not True or not re.fullmatch(r"[0-9a-f]{64}", value.get("packet_sha256", "")) or not isinstance(value.get("reviews"), list) or len(value["reviews"])!=8:
        raise EvalError("a locked review overlay is required before unblinding")
    if value["packet_sha256"] != hashlib.sha256(canonical_bytes(clean_packet)).hexdigest(): raise EvalError("locked overlay packet binding is invalid")
    for index, review in enumerate(value["reviews"], 1):
        if type(review) is not dict or set(review)!={"pair","review_a","review_b","preference_or_tie"} or review["pair"]!=index or review["preference_or_tie"] not in {"A","B","tie"}:
            raise EvalError("locked overlay is incomplete")
        for name in ("review_a","review_b"):
            fields=review[name]
            if type(fields) is not dict or set(fields)!=_REVIEW_KEYS or any(type(fields[x]) is not bool for x in _REVIEW_KEYS-{"notes"}) or not isinstance(fields["notes"],str) or len(fields["notes"])>1000: raise EvalError("locked overlay is incomplete")
    return deepcopy(value)


def _safe_path(run: str) -> dict[str, Path]:
    if not SAFE_RUN.fullmatch(run) or run.upper() in RESERVED: raise EvalError("run name is unsafe")
    RESULTS.mkdir(exist_ok=True); KEYS.mkdir(exist_ok=True)
    if RESULTS.resolve() != RESULTS.absolute() or KEYS.resolve() != KEYS.absolute(): raise EvalError("output roots must not be redirected")
    for directory in (RESULTS, KEYS):
        for child in directory.iterdir():
            if child.name.casefold() in {run.casefold(), (run + ".json").casefold(), (".reservation-" + run).casefold(), (".reservation-" + run + ".json").casefold()}:
                raise EvalError("case-insensitive output collision")
    target, key = RESULTS / run, KEYS / f"{run}.json"
    stage = RESULTS / f".reservation-{run}"; key_stage = KEYS / f".reservation-{run}.json"
    for path in (RESULTS, KEYS, target, key, stage, key_stage):
        if path.exists() and (stat.S_ISLNK(path.lstat().st_mode) or getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)): raise EvalError("reparse output path rejected")
    if target.exists() or key.exists() or stage.exists() or key_stage.exists(): raise EvalError("run output must be fresh")
    try:
        os.mkdir(stage)
        with key_stage.open("xb"):
            pass
    except OSError as error:
        if stage.exists():
            try: stage.rmdir()
            except OSError: pass
        raise EvalError("unable to exclusively reserve output paths") from error
    s=stage.stat(); k=key_stage.stat()
    return {"run":run,"results_root":RESULTS.absolute(),"keys_root":KEYS.absolute(),"target":target,"key":key,"stage":stage,"key_stage":key_stage,"stage_identity":(s.st_dev,s.st_ino),"key_stage_identity":(k.st_dev,k.st_ino)}


def _revalidate_reservation(reservation: dict[str, Path]) -> None:
    required={"run","results_root","keys_root","target","key","stage","key_stage","stage_identity","key_stage_identity"}
    if type(reservation) is not dict or set(reservation)!=required or not isinstance(reservation["run"],str) or not SAFE_RUN.fullmatch(reservation["run"]): raise EvalError("reservation schema is malformed")
    if reservation["results_root"] != RESULTS.absolute() or reservation["keys_root"] != KEYS.absolute() or reservation["target"] != RESULTS / reservation["run"] or reservation["key"] != KEYS / (reservation["run"]+".json") or reservation["stage"] != RESULTS / (".reservation-"+reservation["run"]) or reservation["key_stage"] != KEYS / (".reservation-"+reservation["run"]+".json"): raise EvalError("reservation caller does not own these paths")
    for name in ("target","key"):
        if reservation[name].exists(): raise EvalError("final output appeared during execution")
    for name, identity in (("stage",reservation["stage_identity"]),("key_stage",reservation["key_stage_identity"])):
        try: info=reservation[name].lstat()
        except OSError as error: raise EvalError("output reservation disappeared") from error
        if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0): raise EvalError("reservation reparse path rejected")
        if (info.st_dev, info.st_ino) != identity: raise EvalError("output reservation identity changed")


def _abort_reservation(reservation: dict[str, Path]) -> None:
    try: _revalidate_reservation(reservation)
    except (EvalError, OSError): return
    for name in ("public-report.json","private-review-packet.json","local-run-receipt.json"):
        try: (reservation["stage"] / name).unlink()
        except FileNotFoundError: pass
        except OSError: return
    try: reservation["stage"].rmdir(); reservation["key_stage"].unlink()
    except OSError: pass


def publish(run: str, execution: dict[str, Any], *, reservation: dict[str, Path] | None = None) -> Path:
    reservation = _safe_path(run) if reservation is None else reservation
    published_key_identity: tuple[int, int] | None = None
    try:
        if reservation.get("run") != run:
            raise EvalError("reservation does not belong to the requested run")
        _revalidate_reservation(reservation)
        execution=validate_execution(execution); packet,key=build_packet(execution)
        report={"schema_version":"airi.correction-target-public-report.v2","runner_version":RUNNER_VERSION,"protocol_id":PROTOCOL_ID,"supersedes_packet_schema":"airi.correction-target-blinded-review.v1","superseded_schema_status":"obsolete_incomplete_review_context","cohort_count":8,"model_call_count":16,"fixture_sha256":base.FIXTURE_SHA256,"reply_act_fixture_sha256":base.REPLY_ACT_FIXTURE_SHA256,"oracle_sha256":targets.ORACLE_SHA256,"eligibility":True,"transport_contract":execution["transport_contract"],"profile_sha256":hashlib.sha256(canonical_bytes(base.EVAL_PROFILE)).hexdigest(),"health_profile_sha256":execution["health_profile_sha256"],"operational_adoption":False}
        encoded={"public-report.json":canonical_bytes(report),"private-review-packet.json":canonical_bytes(packet)}
        receipt={"schema_version":"airi.correction-target-local-run-receipt.v2","protocol_id":PROTOCOL_ID,"integrity_only_not_authenticity":True,"hostile_local_authenticity_not_addressed":True,"v1_review_artifacts_obsolete":True,"artifacts":{n:hashlib.sha256(v).hexdigest() for n,v in encoded.items()}}
        encoded["local-run-receipt.json"]=canonical_bytes(receipt)
        if any(len(v)>MAX_PACKET_BYTES for v in encoded.values()): raise EvalError("artifact exceeds bound")
        _revalidate_reservation(reservation)
        for name,data in encoded.items():
            _revalidate_reservation(reservation)
            path=reservation["stage"] / name
            with path.open("xb") as handle: handle.write(data)
        _revalidate_reservation(reservation)
        with reservation["key_stage"].open("r+b") as handle:
            info=os.fstat(handle.fileno())
            if (info.st_dev,info.st_ino)!=reservation["key_stage_identity"]: raise EvalError("key reservation identity changed")
            handle.truncate(0); handle.write(canonical_bytes(key)); handle.flush(); os.fsync(handle.fileno())
        # Publish the operator key first: public results never appear without it.
        _revalidate_reservation(reservation)
        info=reservation["key_stage"].stat(); published_key_identity=(info.st_dev, info.st_ino)
        os.rename(reservation["key_stage"], reservation["key"])
        if reservation["target"].exists() or not reservation["stage"].is_dir(): raise EvalError("result output appeared during key publication")
        os.rename(reservation["stage"], reservation["target"])
        return reservation["target"]
    except Exception:
        _abort_reservation(reservation)
        if published_key_identity is not None and not reservation["target"].exists():
            try:
                current=reservation["key"].stat()
                if (current.st_dev,current.st_ino)==published_key_identity: reservation["key"].unlink()
            except OSError: pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); parser.add_argument("--run"); parser.add_argument("--endpoint", default=ENDPOINT); parser.add_argument("--request-timeout", type=float, default=30); parser.add_argument("--overall-timeout", type=float, default=900)
    args=parser.parse_args(argv); print(json.dumps(eligibility(), ensure_ascii=False, sort_keys=True))
    if args.execute:
        if not args.run: raise EvalError("--execute requires a fresh --run name")
        base.ensure_loopback(args.endpoint)
        transport = base.make_local_transport(args.endpoint, request_timeout=args.request_timeout, overall_timeout=args.overall_timeout)
        # Reserve before health or model transport, so a collision burns no calls.
        reservation = _safe_path(args.run)
        try:
            result = execute(args.endpoint, transport)
            publish(args.run, result, reservation=reservation)
        except Exception:
            _abort_reservation(reservation)
            raise
    return 0

if __name__ == "__main__": main()
