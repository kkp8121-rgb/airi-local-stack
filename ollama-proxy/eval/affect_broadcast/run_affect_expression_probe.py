"""Small, local-only Mi:dm probe for affect-to-expression realization.

The tracked synthetic fixture remains read-only.  Each triplet has identical
history, user text, sampling options, and model seed.  The second arm appends
only the existing typed affect snapshot; the third appends only the new closed
expression contract.  This evaluator never enables operational affect state.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
PROXY_ROOT = HERE.parents[1]
if str(PROXY_ROOT) not in sys.path:
    sys.path.insert(0, str(PROXY_ROOT))

from affect_expression import render_affect_expression_contract
from affect_state import render_continuity_snapshot


_SPEC = importlib.util.spec_from_file_location(
    "airi_affect_broadcast_base", HERE / "run_affect_broadcast_eval.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("affect broadcast evaluator is unavailable")
_BASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASE)


REPORT_SCHEMA_VERSION = "airi.affect-expression-probe.v1"
RUNNER_VERSION = "1.0.0"
ARMS = ("off", "snapshot", "expression")
ARM_ORDERS = (
    ("off", "snapshot", "expression"),
    ("snapshot", "expression", "off"),
    ("expression", "off", "snapshot"),
)
DEFAULT_CASE_IDS = (
    "teasing-11",       # playful_annoyed
    "correction-07",    # skeptical
    "game-17",          # competitive
    "callback-20",      # pleased
    "fatigue-09",       # safety de-escalation
)
DEFAULT_SEEDS = (42, 43, 44)
DEFAULT_TEMPERATURE = 0.6
DEFAULT_MAX_TOKENS = 96
LOCAL_RESULTS = HERE / "local-results"
MAX_OUTPUT_BYTES = 512 * 1024


class ProbeError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def load_fixture() -> dict[str, Any]:
    return _BASE.load_fixture()


def _find_turn(fixture: dict[str, Any], turn_id: str) -> tuple[dict[str, Any], int, dict[str, Any]]:
    for scenario in fixture["scenarios"]:
        for turn_index, turn in enumerate(scenario["turns"]):
            if turn["id"] == turn_id:
                if turn["selected_message"] is None:
                    raise ProbeError("probe case cannot be a no-response turn")
                return scenario, turn_index, turn
    raise ProbeError("probe case is not present in the pinned fixture")


def _local_note(body: bytes) -> tuple[dict[str, Any], int, str]:
    value = json.loads(body)
    notes = [
        (index, message) for index, message in enumerate(value.get("messages", []))
        if isinstance(message, dict)
        and message.get("role") == "system"
        and message.get("name") == "airi_request_local"
    ]
    if len(notes) != 1 or not isinstance(notes[0][1].get("content"), str):
        raise ProbeError("request must contain exactly one request-local note")
    return value, notes[0][0], notes[0][1]["content"]


def _assert_only_appended(previous: bytes, current: bytes, addition: str) -> None:
    left, left_index, left_content = _local_note(previous)
    right, right_index, right_content = _local_note(current)
    if left_index != right_index or right_content != left_content + "\n\n" + addition:
        raise ProbeError("probe arm differs outside its declared prompt addition")
    right["messages"][right_index]["content"] = left_content
    if canonical_bytes(left) != canonical_bytes(right):
        raise ProbeError("probe arm has an undeclared request delta")


def build_triplet(
    fixture: dict[str, Any], turn_id: str, seed: int,
    *, temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ProbeError("model seed is invalid")
    if not 0 <= temperature <= 2 or type(max_tokens) is not int or not 1 <= max_tokens <= 256:
        raise ProbeError("generation profile is invalid")
    scenario, turn_index, turn = _find_turn(fixture, turn_id)
    request = _BASE.base_request(scenario, turn_index, _BASE.EVAL_PROFILE)
    request["options"] = {
        "num_ctx": _BASE.EVAL_PROFILE["num_ctx"],
        "temperature": temperature,
        "seed": seed,
        "num_predict": max_tokens,
    }
    context = _BASE.canonical_context_note(turn)
    snapshot = render_continuity_snapshot(turn["expected_state"])
    expression = render_affect_expression_contract(turn["expected_state"])
    off = _BASE._inject_request_local_system_note(canonical_bytes(request), context)
    snapshot_body = _BASE._inject_request_local_system_note(off, snapshot)
    expression_body = _BASE._inject_request_local_system_note(snapshot_body, expression)
    _assert_only_appended(off, snapshot_body, snapshot)
    _assert_only_appended(snapshot_body, expression_body, expression)
    return {
        "off": off,
        "snapshot": snapshot_body,
        "expression": expression_body,
    }, {
        "turn_id": turn_id,
        "primary": turn["expected_state"]["primary"],
        "cause": turn["expected_state"]["cause"],
        "drive": turn["expected_state"]["drive"],
        "selected_message": turn["selected_message"],
        "prior_airi": turn["prior_airi"],
    }


def _health_signature(
    transport: Callable[[str, str, bytes | None, dict[str, str]], Any], endpoint: str,
) -> dict[str, Any]:
    health = _BASE._transport_result(
        transport("GET", _BASE._health_url(endpoint), None, {}), "health",
    )
    return _BASE._health_profile(health, _BASE.EVAL_PROFILE)


def execute(
    fixture: dict[str, Any], endpoint: str,
    transport: Callable[[str, str, bytes | None, dict[str, str]], Any],
    *, case_ids: tuple[str, ...] = DEFAULT_CASE_IDS,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    _BASE.ensure_loopback(endpoint)
    if not case_ids or len(set(case_ids)) != len(case_ids) or not seeds or len(set(seeds)) != len(seeds):
        raise ProbeError("probe cases and seeds must be nonempty and unique")
    before = _health_signature(transport, endpoint)
    rows: list[dict[str, Any]] = []
    arm_position_counts = {arm: [0, 0, 0] for arm in ARMS}
    ordinal = 0
    for turn_id in case_ids:
        for seed in seeds:
            bodies, metadata = build_triplet(
                fixture, turn_id, seed,
                temperature=temperature, max_tokens=max_tokens,
            )
            responses: dict[str, str] = {}
            order = ARM_ORDERS[ordinal % len(ARM_ORDERS)]
            for position, arm in enumerate(order):
                arm_position_counts[arm][position] += 1
                payload = _BASE._transport_result(
                    transport(
                        "POST", endpoint, bodies[arm],
                        {"x-airi-turn-origin": "local-evaluation"},
                    ),
                    f"{arm} model",
                )
                responses[arm] = _BASE._response_content(payload)
            rows.append({
                **metadata,
                "seed": seed,
                "execution_order": list(order),
                "request_sha256": {
                    arm: hashlib.sha256(bodies[arm]).hexdigest() for arm in ARMS
                },
                "responses": responses,
            })
            ordinal += 1
    after = _health_signature(transport, endpoint)
    if before != after:
        raise ProbeError("loopback profile changed during the probe")
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "synthetic_only": True,
        "operational_affect_enabled": False,
        "adoption_authorized": False,
        "status": "exploratory_no_gate",
        "profile": {
            "model": _BASE.EVAL_PROFILE["model"],
            "model_digest": _BASE.EVAL_PROFILE["model_digest"],
            "num_ctx": _BASE.EVAL_PROFILE["num_ctx"],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "seeds": list(seeds),
        },
        "fixture_sha256": _BASE.FIXTURE_SHA256,
        "case_ids": list(case_ids),
        "request_delta_verified": True,
        "arm_position_counts": arm_position_counts,
        "row_count": len(rows),
        "model_call_count": len(rows) * len(ARMS),
        "changed_pairs": {
            "snapshot_vs_off": sum(row["responses"]["snapshot"] != row["responses"]["off"] for row in rows),
            "expression_vs_off": sum(row["responses"]["expression"] != row["responses"]["off"] for row in rows),
            "expression_vs_snapshot": sum(row["responses"]["expression"] != row["responses"]["snapshot"] for row in rows),
        },
        "health_profile_sha256": hashlib.sha256(canonical_bytes(before)).hexdigest(),
        "rows": rows,
    }


def _parse_csv(value: str, *, integers: bool = False) -> tuple[Any, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise argparse.ArgumentTypeError("value must not be empty")
    if integers:
        try:
            return tuple(int(item) for item in items)
        except ValueError as error:
            raise argparse.ArgumentTypeError("seeds must be integers") from error
    return items


def _write_fresh_local_report(output: Path, report: dict[str, Any]) -> None:
    candidate = output.resolve()
    if candidate.parent != LOCAL_RESULTS.resolve() or candidate.suffix.lower() != ".json":
        raise ProbeError("output must be a JSON file directly under affect_broadcast/local-results")
    payload = canonical_bytes(report) + b"\n"
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ProbeError("probe report exceeds its output cap")
    descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            candidate.unlink()
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11435/api/chat")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cases", default=",".join(DEFAULT_CASE_IDS))
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in DEFAULT_SEEDS))
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--overall-timeout", type=float, default=900.0)
    args = parser.parse_args()
    case_ids = _parse_csv(args.cases)
    seeds = _parse_csv(args.seeds, integers=True)
    fixture = load_fixture()
    if not args.execute:
        print(json.dumps({
            "status": "offline_plan", "case_ids": case_ids, "seeds": seeds,
            "model_call_count": len(case_ids) * len(seeds) * len(ARMS),
            "operational_affect_enabled": False,
        }, ensure_ascii=False, sort_keys=True))
        return 0
    if args.output is None:
        raise ProbeError("--execute requires --output")
    transport = _BASE.make_local_transport(
        args.endpoint,
        request_timeout=args.request_timeout,
        overall_timeout=args.overall_timeout,
    )
    report = execute(
        fixture, args.endpoint, transport,
        case_ids=case_ids, seeds=seeds,
        temperature=args.temperature, max_tokens=args.max_tokens,
    )
    _write_fresh_local_report(args.output, report)
    print(json.dumps({
        "status": report["status"],
        "row_count": report["row_count"],
        "model_call_count": report["model_call_count"],
        "changed_pairs": report["changed_pairs"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
