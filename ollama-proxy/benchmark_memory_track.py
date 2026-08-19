"""M0 memory gate benchmark.  No cloud request is possible without --allow-cloud."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable

from airi_memory import MemoryStore, pack_vector

from memory_prompts import STAGE_A_SCHEMA, STAGE_A_CONVERSATION_SYSTEM_PROMPT, STAGE_A_SYSTEM_PROMPT, STAGE_B_DECISION_SYSTEM_PROMPT
from memory_prompts import STAGE_A_SPAN_SCHEMA, STAGE_A_SPAN_SYSTEM_PROMPT
from memory_stage_b import DECISION_SCHEMA_TEMPLATE, DecisionContractError, compile_decisions, decision_factory_probe_sha256, decision_schema_for_items, format_stage_b_input, parse_stage_b_decisions
from verify_extraction_gate import GATE_PROFILES, gate_metrics_pass, resolve_gate_thresholds

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "memory_benchmark_fixtures.json"
DEFAULT_OLLAMA = "http://127.0.0.1:11434/api/chat"


def schema_sha256(schema: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


class ValidationError(ValueError):
    pass


MAX_GRAPH_REFS = 16


def _exact_keys(value: dict[str, Any], keys: set[str]) -> None:
    if set(value) != keys:
        raise ValidationError("field set does not match schema")


def _string(v: Any, name: str) -> None:
    if not isinstance(v, str) or not v:
        raise ValidationError(f"{name} must be a non-empty string")


def _turn_range(v: Any) -> None:
    if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in v) and v[0] <= v[1]):
        raise ValidationError("turnRange must be [positive int, positive int]")


def parse_stage_a(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    """Strictly parse Stage A JSON; intentionally does not accept prose/fences."""
    try:
        value = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError("root must be object")
    _exact_keys(value, {"extracted"})
    if not isinstance(value["extracted"], list):
        raise ValidationError("extracted must be array")
    for item in value["extracted"]:
        if not isinstance(item, dict) or not isinstance(item.get("turnNumber"), int) or isinstance(item.get("turnNumber"), bool) or item["turnNumber"] < 1:
            raise ValidationError("invalid extraction turnNumber")
        kind = item.get("kind")
        if kind == "entity":
            _exact_keys(item, {"turnNumber", "kind", "subtype", "name", "content"})
            if item["subtype"] not in {"person", "location", "item", "organization", "event"}:
                raise ValidationError("invalid entity subtype")
            _string(item["name"], "name"); _string(item["content"], "content")
        elif kind == "fact":
            _exact_keys(item, {"turnNumber", "kind", "subtype", "subjectNames", "content", "turnRange"})
            if item["subtype"] not in {"trait", "moment"} or not isinstance(item["subjectNames"], list) or not item["subjectNames"] or len(item["subjectNames"]) > MAX_GRAPH_REFS or len(set(item["subjectNames"])) != len(item["subjectNames"]):
                raise ValidationError("invalid fact")
            for name in item["subjectNames"]: _string(name, "subject name")
            _string(item["content"], "content"); _turn_range(item["turnRange"])
        elif kind == "relation":
            _exact_keys(item, {"turnNumber", "kind", "subtype", "sourceName", "targetName", "content"})
            for field in ("subtype", "sourceName", "targetName", "content"): _string(item[field], field)
        else:
            raise ValidationError("kind must be entity, fact, or relation")
    return value


def parse_stage_a_span(raw: str | bytes | dict[str, Any], turns_text: str) -> tuple[dict[str, Any], int]:
    """Parse the span contract and code-verify every evidence quote.

    An item survives only when its evidence is a verbatim substring of the
    turns and every name it references appears inside that evidence. Failing
    items are dropped (and counted) rather than fatal: the point of the
    contract is that hallucination becomes structurally impossible, so a bad
    quote silently costs the model recall instead of poisoning the store.
    Surviving items are returned in the classic shape (evidence stripped) so
    scoring and Stage B stay byte-compatible.
    """
    try:
        value = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError("root must be object")
    _exact_keys(value, {"extracted"})
    if not isinstance(value["extracted"], list):
        raise ValidationError("extracted must be array")

    def names_of(item: dict[str, Any]) -> list[str]:
        if item.get("kind") == "entity":
            return [item.get("name", "")]
        if item.get("kind") == "fact":
            return list(item.get("subjectNames") or [])
        return [item.get("sourceName", ""), item.get("targetName", "")]

    survivors: list[dict[str, Any]] = []
    dropped = 0
    for item in value["extracted"]:
        if not isinstance(item, dict) or not isinstance(item.get("evidence"), str) or not item["evidence"]:
            raise ValidationError("every span item needs a non-empty evidence string")
        evidence = item["evidence"]
        stripped = {key: item[key] for key in item if key != "evidence"}
        # 구조 검증은 기존 파서를 그대로 재사용한다 — 계약 이중화 방지.
        parse_stage_a({"extracted": [stripped]})
        if evidence not in turns_text:
            dropped += 1
            continue
        if any(name != "{{user}}" and name not in evidence for name in names_of(stripped)) or                 any(name == "{{user}}" and "{{user}}" not in evidence for name in names_of(stripped)):
            dropped += 1
            continue
        survivors.append(stripped)
    return {"extracted": survivors}, dropped


_ADD_OR_UPDATE = {"ADD_ENTITY", "ADD_FACT", "ADD_RELATION", "UPDATE_ENTITY", "UPDATE_FACT", "UPDATE_RELATION"}
_SUPERSEDE = {"SUPERSEDE_ENTITY", "SUPERSEDE_FACT", "SUPERSEDE_RELATION"}


def parse_stage_b(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("invalid JSON") from exc
    if not isinstance(value, dict): raise ValidationError("root must be object")
    _exact_keys(value, {"operations"})
    if not isinstance(value["operations"], list): raise ValidationError("operations must be array")
    for op in value["operations"]:
        if not isinstance(op, dict) or not isinstance(op.get("op"), str): raise ValidationError("invalid operation")
        kind = op["op"]
        if kind == "NOOP":
            _exact_keys(op, {"op", "sourceItemIndex", "sourceTurnNumber", "alias"})
        elif kind.endswith("ENTITY") and kind in (_ADD_OR_UPDATE | _SUPERSEDE):
            _exact_keys(op, {"op", "sourceItemIndex", "sourceTurnNumber", "alias", "subtype", "name", "content", "turnRange", "reason"})
            if op["subtype"] not in {"person", "location", "item", "organization", "event"}: raise ValidationError("invalid entity subtype")
            _string(op["name"], "name"); _string(op["content"], "content")
            if op["turnRange"] is not None: _turn_range(op["turnRange"])
        elif kind.endswith("FACT") and kind in (_ADD_OR_UPDATE | _SUPERSEDE):
            _exact_keys(op, {"op", "sourceItemIndex", "sourceTurnNumber", "alias", "subtype", "content", "subjectAliases", "turnRange", "reason"})
            if op["subtype"] not in {"trait", "moment"} or not isinstance(op["subjectAliases"], list) or not op["subjectAliases"] or len(op["subjectAliases"]) > MAX_GRAPH_REFS or len(set(op["subjectAliases"])) != len(op["subjectAliases"]): raise ValidationError("invalid fact op")
            _string(op["content"], "content"); _turn_range(op["turnRange"])
        elif kind.endswith("RELATION") and kind in (_ADD_OR_UPDATE | _SUPERSEDE):
            _exact_keys(op, {"op", "sourceItemIndex", "sourceTurnNumber", "alias", "subtype", "sourceAlias", "targetAlias", "content", "reason"})
            for field in ("subtype", "sourceAlias", "targetAlias", "content"): _string(op[field], field)
        else: raise ValidationError("unknown operation")
        if not isinstance(op.get("sourceItemIndex"), int) or isinstance(op.get("sourceItemIndex"), bool) or op["sourceItemIndex"] < 0:
            raise ValidationError("invalid source item index")
        if not isinstance(op.get("sourceTurnNumber"), int) or isinstance(op.get("sourceTurnNumber"), bool) or op["sourceTurnNumber"] < 1:
            raise ValidationError("invalid source turn")
        if kind != "NOOP":
            _string(op.get("alias"), "alias")
            if kind in _SUPERSEDE: _string(op.get("reason"), "reason")
            if kind.startswith("ADD_"):
                prefix = {"ENTITY": "e", "FACT": "f", "RELATION": "r"}[kind.rsplit("_", 1)[1]]
                if not op["alias"].startswith(prefix): raise ValidationError("ADD alias prefix mismatch")
    return value


def percentile(values: Iterable[float], p: float) -> float | None:
    seq = sorted(values)
    if not seq: return None
    if len(seq) == 1: return round(seq[0], 3)
    pos = (len(seq) - 1) * p / 100.0; low = int(pos); high = min(low + 1, len(seq) - 1)
    return round(seq[low] + (seq[high] - seq[low]) * (pos - low), 3)


def latency_summary(ms: Iterable[float]) -> dict[str, float | None]:
    values = list(ms)
    return {"count": len(values), "p50_ms": percentile(values, 50), "p90_ms": percentile(values, 90), "p95_ms": percentile(values, 95)}


def load_fixtures(path: Path = FIXTURES) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f: return json.load(f)

def stage_a_prompt_for_contract(contract: str) -> str:
    if contract == "legacy":
        return STAGE_A_SYSTEM_PROMPT
    if contract == "conversation-v2b":
        return STAGE_A_CONVERSATION_SYSTEM_PROMPT
    if contract == "conversation-v3-span":
        return STAGE_A_SPAN_SYSTEM_PROMPT
    raise ValueError("stage_a_contract must be legacy, conversation-v2b, or conversation-v3-span")


def comparison_contract_for_stage_a(contract: str) -> str:
    if contract == "legacy":
        return "v2_to_v2.1_same_options"
    if contract == "conversation-v2b":
        return "v2.1_stage_a_legacy_to_conversation_v2b_same_options"
    if contract == "conversation-v3-span":
        return "v2.1_stage_a_conversation_v2b_to_v3_span_same_options"
    raise ValueError("stage_a_contract must be legacy, conversation-v2b, or conversation-v3-span")


def reproducibility_metadata(fixture_path: Path, stage_a_contract: str = "conversation-v2b") -> dict[str, str]:
    digest = lambda value: hashlib.sha256(value).hexdigest()
    active_prompt = stage_a_prompt_for_contract(stage_a_contract)
    return {"fixture_sha256":digest(fixture_path.read_bytes()),
            "stage_a_active_prompt_sha256":digest(active_prompt.encode("utf-8")),
            "stage_a_prompt_sha256":digest(STAGE_A_SYSTEM_PROMPT.encode("utf-8")),
            "stage_a_conversation_prompt_sha256":digest(STAGE_A_CONVERSATION_SYSTEM_PROMPT.encode("utf-8")),
            "stage_b_decision_prompt_sha256":digest(STAGE_B_DECISION_SYSTEM_PROMPT.encode("utf-8")),
            "stage_a_schema_sha256":digest(json.dumps(STAGE_A_SCHEMA,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")),
            "stage_b_decision_schema_template_sha256":digest(json.dumps(DECISION_SCHEMA_TEMPLATE,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")),
            "stage_b_decision_factory_probe_sha256":decision_factory_probe_sha256()}

def model_digest(value: str) -> str:
    value=str(value or "")
    if value and not re.fullmatch(r"[0-9a-fA-F]{64}",value): raise argparse.ArgumentTypeError("model digest must be 64 hex characters")
    return value.lower()


def _matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        actual_value = actual.get(key)
        if key in {"subjectNames", "subjectAliases"}:
            if not isinstance(actual_value, list) or not isinstance(value, list) or len(actual_value) != len(set(actual_value)) or set(actual_value) != set(value):
                return False
        elif actual_value != value:
            return False
    return True


def _semantic_item_key(item: dict[str, Any]) -> str:
    """Canonicalize only unordered graph-reference arrays for duplicate checks."""
    normalized = dict(item)
    for key in ("subjectNames", "subjectAliases"):
        if isinstance(normalized.get(key), list): normalized[key] = sorted(set(normalized[key]))
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def score_extraction(stage_a: dict[str, Any] | None, stage_b: dict[str, Any] | None, fixture: dict[str, Any]) -> dict[str, Any]:
    a = (stage_a or {}).get("extracted", []); b = (stage_b or {}).get("operations", [])
    expected_a = fixture["expected_stage_a"]; expected_b = fixture["expected_stage_b"]
    def consume(items: list[dict[str, Any]], patterns: list[dict[str, Any]], used: set[int] | None = None) -> tuple[int, set[int]]:
        consumed = set() if used is None else set(used)
        found = 0
        for pattern in patterns:
            index = next((i for i, item in enumerate(items) if i not in consumed and _matches(item, pattern)), None)
            if index is not None: consumed.add(index); found += 1
        return found, consumed
    found_a, consumed_a = consume(a, expected_a)
    found_b, _consumed_b = consume(b, expected_b)
    required = expected_a + expected_b
    found = found_a + found_b
    # `allowed` records legitimate, model-dependent optional extraction choices.
    # It is deliberately a pattern list, never a free pass: every emitted item
    # must match a required or allowed pattern or is a hallucination.
    allowed = fixture.get("allowed", [])
    allowed_a = fixture.get("allowed_stage_a", []) + allowed
    # Hallucination is measured on extracted memory items. Stage-B emits one
    # operation for every accepted Stage-A item, so counting those operations
    # again would double-penalize legitimate optional extraction choices.
    _allowed_found, consumed_a = consume(a, allowed_a, consumed_a)
    unexpected = len(a) - len(consumed_a)
    placeholders = [goal for goal in required if "{{user}}" in json.dumps(goal, ensure_ascii=False)]
    placeholder_ok = all(any(_matches(item, goal) for item in a + b) for goal in placeholders)
    alias_ok = all(any(_matches(item, goal) for item in b) for goal in expected_b)
    return {"critical_total": len(required), "critical_found": found, "critical_recall": found / len(required) if required else 1.0,
            "unexpected": unexpected, "placeholder_preserved": placeholder_ok, "stage_b_op_alias_accuracy": (sum(any(_matches(x, y) for x in b) for y in expected_b) / len(expected_b) if expected_b else 1.0), "alias_ok": alias_ok}

def score_stage_a(stage_a: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    items = stage_a.get("extracted", [])
    expected = fixture.get("expected_stage_a", [])
    used: set[int] = set(); found = 0
    for pattern in expected:
        index = next((i for i, item in enumerate(items) if i not in used and _matches(item, pattern)), None)
        if index is not None: used.add(index); found += 1
    for pattern in fixture.get("allowed_stage_a", []) + fixture.get("allowed", []):
        index = next((i for i, item in enumerate(items) if i not in used and _matches(item, pattern)), None)
        if index is not None: used.add(index)
    placeholders=[goal for goal in expected if "{{user}}" in json.dumps(goal,ensure_ascii=False)]
    return {"critical_recall":found/len(expected) if expected else 1.0,"unexpected":len(items)-len(used),
            "placeholder_preserved":all(any(_matches(item,goal) for item in items) for goal in placeholders)}


def stage_b_coverage_diagnostics(stage_a: dict[str, Any], stage_b: dict[str, Any], candidates: list[dict[str, Any]]) -> list[str]:
    """Privacy-safe structural Stage-A/B diagnostics (never values/content)."""
    extracted = stage_a.get("extracted", [])
    operations = stage_b.get("operations", [])
    codes: set[str] = set()
    keys = [_semantic_item_key(item) for item in extracted if isinstance(item, dict)]
    if len(keys) != len(set(keys)): codes.add("duplicate_extracted_item")
    if len(operations) != len(extracted):
        codes.add("operation_count_mismatch")
    indexes = [op.get("sourceItemIndex") for op in operations if isinstance(op, dict)]
    if len(indexes) != len(set(indexes)):
        codes.add("duplicate_source_index")
    if set(indexes) != set(range(len(extracted))):
        codes.add("source_index_coverage")
    existing_aliases = {str(candidate.get("alias")) for candidate in candidates if candidate.get("alias")}
    candidate_by_alias = {str(candidate.get("alias")): candidate for candidate in candidates if candidate.get("alias")}
    added_aliases: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict):
            codes.add("operation_shape_mismatch"); continue
        alias, op_name = str(operation.get("alias", "")), str(operation.get("op", ""))
        if op_name.startswith("ADD_"):
            if alias in existing_aliases or alias in added_aliases: codes.add("add_alias_collision")
            added_aliases.add(alias)
        elif alias not in existing_aliases:
            codes.add("unknown_existing_alias")
    alias_names = {
        str(candidate.get("alias")): str(candidate.get("name"))
        for candidate in candidates
        if candidate.get("alias") and candidate.get("name")
    }
    all_add_entity_aliases = {
        str(operation.get("alias")) for operation in operations
        if isinstance(operation, dict) and operation.get("op") == "ADD_ENTITY" and operation.get("alias")
    }
    prefix_family = {"e": "entity", "f": "fact", "r": "relation"}
    for operation in operations:
        if not isinstance(operation, dict): continue
        index = operation.get("sourceItemIndex")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(extracted):
            continue
        item = extracted[index]
        op_name = str(operation.get("op", ""))
        family = prefix_family.get(str(operation.get("alias", ""))[:1]) if op_name == "NOOP" else op_name.rsplit("_", 1)[-1].lower()
        if family != item.get("kind") or operation.get("sourceTurnNumber") != item.get("turnNumber"):
            codes.add("kind_or_turn_mismatch")
            continue
        if op_name == "NOOP":
            candidate = candidate_by_alias.get(str(operation.get("alias")))
            candidate_kind = candidate.get("kind") if candidate else None
            if candidate_kind is None:
                candidate_kind = prefix_family.get(str(operation.get("alias", ""))[:1])
            mismatch = candidate is None or candidate_kind != item.get("kind")
            for field in ("subtype", "content"):
                if candidate is None or candidate.get(field) != item.get(field): mismatch = True
            if family == "entity" and (candidate is None or candidate.get("name") != item.get("name")):
                mismatch = True
            if family == "fact":
                candidate_subjects = candidate.get("subjectNames") if candidate else None
                expected_subjects = item.get("subjectNames")
                if (not isinstance(candidate_subjects, list) or len(candidate_subjects) != len(set(candidate_subjects))
                        or set(candidate_subjects) != set(expected_subjects or [])):
                    mismatch = True
                # Trait ranges are intentionally not identity; moments are turn-bound.
                if item.get("subtype") == "moment" and (candidate is None or candidate.get("turnRange") != item.get("turnRange")):
                    mismatch = True
            if family == "relation":
                if (candidate is None or candidate.get("sourceName") != item.get("sourceName")
                        or candidate.get("targetName") != item.get("targetName")):
                    mismatch = True
            if mismatch: codes.add("noop_candidate_mismatch")
            continue
        if operation.get("subtype") != item.get("subtype") or operation.get("content") != item.get("content"):
            codes.add("copied_field_mismatch")
        if family == "entity" and operation.get("name") != item.get("name"):
            codes.add("copied_field_mismatch")
        if family == "fact":
            if operation.get("turnRange") != item.get("turnRange"):
                codes.add("copied_field_mismatch")
            names = {alias_names.get(str(alias)) for alias in operation.get("subjectAliases", [])}
            if None in names or names != set(item.get("subjectNames") or []):
                if any(str(alias) in all_add_entity_aliases and str(alias) not in alias_names for alias in operation.get("subjectAliases", [])):
                    codes.add("graph_forward_reference")
                else: codes.add("fact_subject_mapping")
        if family == "relation":
            source = alias_names.get(str(operation.get("sourceAlias")))
            target = alias_names.get(str(operation.get("targetAlias")))
            if source is None or target is None:
                refs = (str(operation.get("sourceAlias")), str(operation.get("targetAlias")))
                if any(ref in all_add_entity_aliases and ref not in alias_names for ref in refs): codes.add("graph_forward_reference")
                else: codes.add("relation_endpoint_unknown")
            elif source != item.get("sourceName") or target != item.get("targetName"):
                codes.add("relation_endpoint_direction")
        if op_name == "ADD_ENTITY" and operation.get("name"):
            # Only earlier ADD_ENTITY operations can resolve subsequent refs.
            alias_names[str(operation.get("alias"))] = str(operation["name"])
    return sorted(codes)


def stage_b_coverage(stage_a: dict[str, Any], stage_b: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
    """Compatibility boolean view of ``stage_b_coverage_diagnostics``."""
    return not stage_b_coverage_diagnostics(stage_a, stage_b, candidates)


def ollama_chat(endpoint: str, model: str, system: str, user: str, schema: dict[str, Any], timeout: float = 60,
                num_ctx: int = 8192, num_gpu: int = 0, seed: int = 42, max_tokens: int = 2048) -> str:
    body = {"model": model, "stream": False, "think": False, "options": {"temperature": 0, "num_ctx": num_ctx, "num_gpu": num_gpu, "seed": seed, "num_predict": max_tokens}, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "format": schema}
    request = urllib.request.Request(endpoint, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["message"]["content"]


def _benchmark_chat(chat: Callable[..., str], args: argparse.Namespace, system: str, user: str, schema: dict[str, Any]) -> str:
    """Keep injected legacy test transports compatible while production gets V2 options."""
    call = (args.ollama_url, args.model, system, user, schema, args.timeout, args.num_ctx, args.num_gpu)
    if chat is ollama_chat:
        return chat(*call, args.seed, args.max_tokens)
    return chat(*call)


def run_extraction(args: argparse.Namespace, fixtures: dict[str, Any], chat: Callable[..., str] = ollama_chat) -> dict[str, Any]:
    # Resolve the gate before measuring so a misconfigured profile fails in
    # milliseconds instead of after a full multi-minute extraction run.
    gate_profile, gate_thresholds = resolve_gate_thresholds(getattr(args, "gate_profile", None))
    rows, stage_a_latencies, stage_b_latencies, total_latencies = [], [], [], []
    stopped_early = False
    stop_reason: str | None = None
    requested = set(args.fixture_id or [])
    extraction_fixtures = [item for item in fixtures["extraction"] if not requested or item["id"] in requested]
    missing = requested - {item["id"] for item in extraction_fixtures}
    if missing:
        raise ValueError("unknown extraction fixture id: " + ", ".join(sorted(missing)))
    stage_a_prompt = stage_a_prompt_for_contract(args.stage_a_contract)
    for _ in range(args.runs):
     for item in extraction_fixtures:
            user_a = "<character>%s</character>\n<turns>%s</turns>" % (item["character"], item["turns"])
            stage_a_schema = STAGE_A_SPAN_SCHEMA if args.stage_a_contract == "conversation-v3-span" else STAGE_A_SCHEMA
            span_dropped = 0
            total0 = time.perf_counter(); a0 = total0
            try:
                raw_a = _benchmark_chat(chat, args, stage_a_prompt, user_a, stage_a_schema)
                if args.stage_a_contract == "conversation-v3-span":
                    a, span_dropped = parse_stage_a_span(raw_a, item["turns"])
                else:
                    a = parse_stage_a(raw_a)
                a_ms = (time.perf_counter() - a0) * 1000
            except (ValidationError, ValueError, KeyError, json.JSONDecodeError):
                a_ms = (time.perf_counter() - a0) * 1000; b_ms = 0.0
                score = {"id":item["id"],"schema_pass":False,"stage_a_schema_pass":False,"stage_b_schema_pass":False,"error_stage":"stage_a","error_code":"stage_a_invalid","connectivity":False,"stage_b_coverage":False,"critical_recall":0.0,"unexpected":0,"placeholder_preserved":False,"stage_b_op_alias_accuracy":0.0,"stage_a_count":0,"decision_count":0,"stage_b_count":0,"failure_codes":["stage_a_invalid"]}
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                a_ms = (time.perf_counter() - a0) * 1000; b_ms = 0.0
                score = {"id":item["id"],"schema_pass":False,"stage_a_schema_pass":False,"stage_b_schema_pass":False,"error_stage":"transport","error_code":"stage_a_transport","connectivity":False,"stage_b_coverage":False,"critical_recall":0.0,"unexpected":0,"placeholder_preserved":False,"stage_b_op_alias_accuracy":0.0,"stage_a_count":0,"decision_count":0,"stage_b_count":0,"failure_codes":["stage_a_transport"]}
            else:
                base = score_extraction(a, {"operations":[]}, item); stage_a_quality = score_stage_a(a, item)
                score = dict(base, id=item["id"], schema_pass=True, stage_a_schema_pass=True, stage_b_schema_pass=False,
                             stage_a_count=len(a["extracted"]), decision_count=0, stage_b_count=0,
                             stage_a_critical_recall=stage_a_quality["critical_recall"], stage_a_unexpected=stage_a_quality["unexpected"],
                             stage_a_placeholder_preserved=stage_a_quality["placeholder_preserved"], connectivity=_connectivity(a,item["candidates"]), stage_b_coverage=False, failure_codes=[])
                if args.stage_a_contract == "conversation-v3-span":
                    score["stage_a_span_dropped"] = span_dropped
                score["stage_b_decision_schema_sha256"] = schema_sha256(decision_schema_for_items(a["extracted"], item["candidates"]))
                if not a["extracted"]:
                    b={"operations":[]}; diagnostics=[]; b_ms=0.0; score.update(stage_b_schema_pass=True,stage_b_count=0,stage_b_coverage=True)
                else:
                    b0=time.perf_counter()
                    try:
                        schema = decision_schema_for_items(a["extracted"], item["candidates"])
                        raw=_benchmark_chat(chat, args, STAGE_B_DECISION_SYSTEM_PROMPT, format_stage_b_input(a["extracted"],item["candidates"]), schema)
                        decisions=parse_stage_b_decisions(raw); score["decision_count"]=len(decisions["decisions"]); score["stage_b_schema_pass"]=True
                    except DecisionContractError as exc:
                        b_ms=(time.perf_counter()-b0)*1000; score.update(error_stage="stage_b_parse",error_code=exc.code,failure_codes=[exc.code])
                    except Exception:
                        b_ms=(time.perf_counter()-b0)*1000; score.update(error_stage="transport",error_code="stage_b_transport",failure_codes=["stage_b_transport"])
                    else:
                        try: b={"operations":compile_decisions(a["extracted"],item["candidates"],decisions["decisions"])}
                        except DecisionContractError as exc: b_ms=(time.perf_counter()-b0)*1000; score.update(error_stage="stage_b_compile",error_code=exc.code,failure_codes=[exc.code])
                        except Exception: b_ms=(time.perf_counter()-b0)*1000; score.update(error_stage="stage_b_compile",error_code="stage_b_compile_internal",failure_codes=["stage_b_compile_internal"])
                        else:
                            b_ms=(time.perf_counter()-b0)*1000; diagnostics=stage_b_coverage_diagnostics(a,b,item["candidates"]); score.update(score_extraction(a,b,item),stage_b_count=len(b["operations"]),stage_b_coverage=not diagnostics,failure_codes=diagnostics,stage_b_schema_pass=True)
                score["schema_pass"] = bool(score["stage_a_schema_pass"] and score["stage_b_schema_pass"])
            stage_a_latencies.append(a_ms); stage_b_latencies.append(b_ms); total_latencies.append((time.perf_counter() - total0) * 1000); rows.append(score)
            row_gate_pass = (score["schema_pass"] and score["connectivity"] and score["stage_b_coverage"]
                             and score["critical_recall"] == 1 and score["placeholder_preserved"]
                             and score["stage_b_op_alias_accuracy"] == 1 and score["unexpected"] == 0)
            if args.fail_fast and not row_gate_pass:
                stopped_early = True
                stop_reason = score.get("error_code") or "gate_row_failed"
                break
     if stopped_early:
         break
    n = len(rows) or 1
    failure_code_counts: dict[str, int] = {}
    for row in rows:
        for code in row["failure_codes"]: failure_code_counts[code] = failure_code_counts.get(code, 0) + 1
    attempted_fixture_ids = [row["id"] for row in rows]
    result = {"status": "measured", "stage_a_contract": args.stage_a_contract, "stage_b_contract": "decision-v2.1", "comparison_contract": comparison_contract_for_stage_a(args.stage_a_contract), "model": args.model, "runs":args.runs, "seed":args.seed, "max_tokens":args.max_tokens, "fail_fast":args.fail_fast, "stopped_early":stopped_early, "stop_reason":stop_reason, "attempted_fixture_ids":attempted_fixture_ids, "attempted_row_count":len(rows), "fixture_ids": sorted(set(attempted_fixture_ids)), "fixtures": rows, "latency":{"stage_a":latency_summary(stage_a_latencies), "stage_b":latency_summary(stage_b_latencies), "total":latency_summary(total_latencies)}, "schema_pass_rate": sum(x["schema_pass"] for x in rows)/n, "stage_a_schema_pass_rate":sum(x["stage_a_schema_pass"] for x in rows)/n,"stage_b_schema_pass_rate":sum(x["stage_b_schema_pass"] for x in rows)/n,"connectivity_rate": sum(x["connectivity"] for x in rows)/n, "stage_b_coverage_rate": sum(x["stage_b_coverage"] for x in rows)/n, "critical_recall": sum(x["critical_recall"] for x in rows)/n, "unexpected": sum(x["unexpected"] for x in rows), "placeholder_rate": sum(x["placeholder_preserved"] for x in rows)/n, "stage_a_critical_recall":sum(x.get("stage_a_critical_recall",0.0) for x in rows)/n,"stage_a_unexpected":sum(x.get("stage_a_unexpected",0) for x in rows),"stage_a_placeholder_rate":sum(x.get("stage_a_placeholder_preserved",False) for x in rows)/n,"stage_b_op_alias_accuracy": sum(x["stage_b_op_alias_accuracy"] for x in rows)/n, "failure_code_counts":dict(sorted(failure_code_counts.items()))}
    # The verifier owns the gate formula; the report only records which
    # thresholds produced this verdict so an operator cannot silently activate
    # a model that was measured under a looser profile.
    result["gate_profile"] = gate_profile
    result["gate_thresholds"] = gate_thresholds
    result["gate_pass"] = bool(rows) and gate_metrics_pass(result, len(rows), gate_thresholds)
    return result


def _connectivity(a: dict[str, Any], candidates: list[dict[str, Any]] | None = None) -> bool:
    people = {x.get("name") for x in a["extracted"] if x.get("kind") == "entity" and x.get("subtype") == "person"}
    for candidate in candidates or []:
        alias, name = str(candidate.get("alias", "")), candidate.get("name")
        if isinstance(name, str) and name and (candidate.get("subtype") == "person" or alias.startswith("e")):
            people.add(name)
    for x in a["extracted"]:
        if x.get("kind") == "entity" and x.get("subtype") in {"location", "organization", "item"}:
            name = x.get("name")
            if not any(r.get("kind") == "relation" and name in (r.get("sourceName"), r.get("targetName")) and (r.get("sourceName") in people or r.get("targetName") in people) for r in a["extracted"]): return False
    return True


def _embedding_specs(specs: list[str]) -> list[tuple[str, str]]:
    parsed = []
    for spec in specs:
        if "=" not in spec: raise ValueError("--embedding-model must be name=path")
        parsed.append(tuple(spec.split("=", 1)))
    return parsed


def run_embedding(args: argparse.Namespace, fixtures: dict[str, Any]) -> dict[str, Any]:
    if not args.embedding_model: return {"status": "skipped", "reason": "no --embedding-model name=path supplied; no model download attempted"}
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError: return {"status": "skipped", "reason": "sentence_transformers is not installed"}
    corpus, queries, results = fixtures["embedding"]["corpus"], fixtures["embedding"]["queries"], []
    for name, path in _embedding_specs(args.embedding_model):
        try:
            constructor_kwargs: dict[str, Any] = {
                "device": None if args.embedding_device == "auto" else args.embedding_device,
                "local_files_only": args.local_files_only,
            }
            if args.embedding_dtype == "float16":
                if args.embedding_device != "cuda":
                    raise ValueError("float16 embedding benchmark requires --embedding-device cuda")
                import torch
                constructor_kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
            load0 = time.perf_counter(); model = SentenceTransformer(path, **constructor_kwargs)
            load_ms = (time.perf_counter()-load0)*1000
            actual_device = str(getattr(model, "device", getattr(model, "_target_device", "unknown")))
            corpus0 = time.perf_counter(); vectors = model.encode([x["text"] for x in corpus], batch_size=16, normalize_embeddings=True); corpus_ms = (time.perf_counter()-corpus0)*1000
            times=[]; ranks=[]
            for query in queries:
                t=time.perf_counter(); q = model.encode([query["text"]], batch_size=16, normalize_embeddings=True)[0]; times.append((time.perf_counter()-t)*1000)
                ranked = [corpus[i]["id"] for i in sorted(range(len(corpus)), key=lambda i: float(sum(a*b for a,b in zip(q, vectors[i]))), reverse=True)]
                rank = next((i+1 for i,x in enumerate(ranked) if x in query["relevant"]), None); ranks.append(rank)
            mrr = statistics.mean(1/r for r in ranks if r) if any(ranks) else 0.0
            results.append({"name": name, "status": "measured", "requested_device":args.embedding_device, "requested_dtype":args.embedding_dtype, "device":actual_device, "model_load_ms":round(load_ms,3), "corpus_batch_build_ms":round(corpus_ms,3), "query_warm_latency":latency_summary(times), "mrr": round(mrr,4), "recall_at_1": round(sum(r is not None and r<=1 for r in ranks)/len(ranks),4), "recall_at_3": round(sum(r is not None and r<=3 for r in ranks)/len(ranks),4)})
        except Exception as exc: results.append({"name": name, "status": "error", "requested_device":args.embedding_device, "requested_dtype":args.embedding_dtype, "reason": type(exc).__name__})
    for r in results:
        if r["status"] == "measured": r["gate_pass"] = r["query_warm_latency"]["p50_ms"] <= 80 and r["recall_at_3"] == 1 and r["mrr"] >= 0.8
    return {"status": "measured" if any(x["status"] == "measured" for x in results) else "error", "models": results}


def _sse_content(provider: str, line: str) -> bool:
    if not line.startswith("data:"): return False
    data = line[5:].strip()
    if not data or data == "[DONE]": return False
    try: payload=json.loads(data)
    except json.JSONDecodeError: return False
    if provider == "openai": return bool(payload.get("choices", [{}])[0].get("delta", {}).get("content"))
    return bool(payload.get("delta", {}).get("text"))


def cloud_ttft(provider: str, model: str, messages: list[dict[str, str]], api_key: str, timeout: float = 60) -> float:
    import httpx
    if provider == "openai":
        url="https://api.openai.com/v1/chat/completions"; headers={"Authorization": "Bearer "+api_key}; body={"model":model,"messages":messages,"stream":True}
    elif provider == "anthropic":
        url="https://api.anthropic.com/v1/messages"; headers={"x-api-key":api_key,"anthropic-version":"2023-06-01"}; body={"model":model,"messages":messages,"stream":True,"max_tokens":16}
    else: raise ValueError("provider must be openai or anthropic")
    start=time.perf_counter()
    with httpx.Client(timeout=timeout, http2=True) as client:
        with client.stream("POST", url, headers=headers, json=body) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if _sse_content(provider, line): return (time.perf_counter()-start)*1000
    raise RuntimeError("stream ended before content token")


def run_cloud(args: argparse.Namespace, fixtures: dict[str, Any], measure: Callable[..., float] = cloud_ttft) -> dict[str, Any]:
    if not args.allow_cloud: return {"status":"skipped", "reason":"cloud outbound disabled; pass --allow-cloud", "candidate_d_requires_end_to_end":True}
    key_name = "OPENAI_API_KEY" if args.cloud_provider == "openai" else "ANTHROPIC_API_KEY"; key=os.environ.get(key_name)
    if not key: return {"status":"skipped", "reason":f"{key_name} is not set", "candidate_d_requires_end_to_end":True}
    values=[]; ids=[]
    for fixture in fixtures["cloud"]:
        try: values.append(measure(args.cloud_provider, args.cloud_model, fixture["messages"], key, args.timeout)); ids.append(fixture["id"])
        except Exception as exc: return {"status":"error", "reason":type(exc).__name__, "fixture_ids":ids, "candidate_d_requires_end_to_end":True}
    return {"status":"measured", "provider":args.cloud_provider, "model":args.cloud_model, "fixture_ids":ids, "ttft":latency_summary(values), "candidate_d_requires_end_to_end":True}


def inventory(args: argparse.Namespace, fixtures: dict[str, Any]) -> dict[str, Any]:
    return {"status":"inventory", "network_used":False, "fixtures":{"extraction":[x["id"] for x in fixtures["extraction"]], "embedding_corpus":len(fixtures["embedding"]["corpus"]), "cloud":[x["id"] for x in fixtures["cloud"]]}, "recommended_models":["nlpai-lab/KURE-v1", "BAAI/bge-m3"], "schema_names":["stage_a", "stage_b"]}


class _RetrievalEmbedder:
    """Deterministic, normalized 1024-dimension local benchmark embedder."""
    def __init__(self) -> None: self.calls = 0
    def encode(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        # Query variants intentionally share a direction: this isolates
        # retrieval/cache timing from embedding-model semantic drift.
        return [_retrieval_vector(0) for _text in texts]


def _retrieval_vector(seed: int) -> list[float]:
    """Dense, deterministic unit vector without model/network work."""
    # A rotated two-coordinate signal keeps fixture rows distinguishable while
    # requiring the real 1024-float decode/matrix path for every candidate.
    vector = [0.0] * 1024
    index = seed % 1024
    vector[index] = 0.8
    vector[(index * 37 + 17) % 1024] = 0.6
    return vector


def _validate_retrieval_args(rows: int, runs: int) -> None:
    if not 10 <= rows <= 100000: raise ValueError("--retrieval-rows must be 10..100000")
    if not 1 <= runs <= 100: raise ValueError("--retrieval-runs must be 1..100")


def _seed_retrieval_fixture(store: MemoryStore, rows: int, *, session_id: str | None, source: str) -> None:
    """Direct, one-transaction fixture seed; no runtime extraction/model path."""
    with store._session(immediate=True) as conn:  # benchmark-owned temporary DB
        entity_ids = []
        entity_count = min(50, rows)
        for index in range(entity_count):
            content = f"memory {index:05d} retrieval fixture"
            cur = conn.execute(
                "INSERT INTO memory(session_id,source,kind,subtype,name,content,content_hash,vector) VALUES (?,?,?,?,?,?,?,?)",
                (session_id, source, "entity", "person", f"memory {index:05d}", content, str(index), pack_vector(_retrieval_vector(index))),
            )
            entity_ids.append(cur.lastrowid)
        for index in range(entity_count, rows):
            content = f"memory fact {index:05d} retrieval fixture"
            cur = conn.execute(
                "INSERT INTO memory(session_id,source,kind,subtype,content,content_hash,vector) VALUES (?,?,?,?,?,?,?)",
                (session_id, source, "fact", "trait", content, str(index), pack_vector(_retrieval_vector(index))),
            )
            conn.execute("INSERT INTO fact_subject(fact_id,entity_id) VALUES (?,?)", (cur.lastrowid, entity_ids[index % len(entity_ids)]))
        store._touch(conn)


def _retrieval_mode(store: MemoryStore, session_id: str | None, query: str, runs: int) -> dict[str, Any]:
    cold_started = time.perf_counter(); cold_result = store.retrieve(session_id, query, current_turn=0)
    cold_wall_ms = (time.perf_counter() - cold_started) * 1000
    internal, wall, cache_hits = [], [], 0
    for turn in range(runs):
        started = time.perf_counter()
        # Unique text defeats exact-result cache while remaining close enough
        # for static semantic-cache reuse with the deterministic vectors.
        result = store.retrieve(session_id, f"{query} variant {turn}", current_turn=turn + 1)
        elapsed = (time.perf_counter() - started) * 1000
        internal.append(result.duration_ms)
        wall.append(elapsed)
        cache_hits += int(result.cache_hit)
    return {"cold": {"internal_duration_ms": round(cold_result.duration_ms, 3), "wall_duration_ms": round(cold_wall_ms, 3)}, "warm":{"internal_duration": latency_summary(internal), "wall_duration": latency_summary(wall), "cache_hits":cache_hits}}


def run_retrieval(args: argparse.Namespace) -> dict[str, Any]:
    _validate_retrieval_args(args.retrieval_rows, args.retrieval_runs)
    paths = []
    for mode in ("dynamic", "static"):
        fd, raw_path = tempfile.mkstemp(prefix=f"airi-retrieval-{mode}-", suffix=".sqlite3")
        os.close(fd); paths.append(raw_path)
    try:
        dynamic_embedder, static_embedder = _RetrievalEmbedder(), _RetrievalEmbedder()
        dynamic_store = MemoryStore(paths[0], embedder=dynamic_embedder, cache_enabled=False)
        seed_started = time.perf_counter()
        _seed_retrieval_fixture(dynamic_store, args.retrieval_rows, session_id="bench-dynamic", source="conversation")
        dynamic_seed_ms = (time.perf_counter() - seed_started) * 1000
        query = f"what is memory {args.retrieval_rows - 1:05d}?"
        dynamic = _retrieval_mode(dynamic_store, "bench-dynamic", query, args.retrieval_runs)
        static_store = MemoryStore(paths[1], embedder=static_embedder, cache_enabled=True)
        seed_started = time.perf_counter()
        _seed_retrieval_fixture(static_store, args.retrieval_rows, session_id=None, source="base")
        static_seed_ms = (time.perf_counter() - seed_started) * 1000
        static = _retrieval_mode(static_store, None, query, args.retrieval_runs)
        with dynamic_store._session() as conn: dynamic_rows = conn.execute("SELECT count(*) FROM memory").fetchone()[0]
        with static_store._session() as conn: static_rows = conn.execute("SELECT count(*) FROM memory").fetchone()[0]
        semantic_entries = len(static_store._semantic_cache)
        result = {"status":"measured", "network_used":False, "row_count":args.retrieval_rows, "runs":args.retrieval_runs,
                  "fixture":{"dimensions":1024,"normalized":True,"seed_duration_ms":{"dynamic":round(dynamic_seed_ms,3),"static":round(static_seed_ms,3)}},
                  "modes":{"dynamic_conversation_cache_bypass":{**dynamic,"db_row_count":dynamic_rows,"embed_calls":dynamic_embedder.calls,"semantic_entries":len(dynamic_store._semantic_cache)}, "static_base_canon_semantic_warm":{**static,"db_row_count":static_rows,"embed_calls":static_embedder.calls,"semantic_entries":semantic_entries}}}
        p50s = [dynamic["warm"]["internal_duration"]["p50_ms"], static["warm"]["internal_duration"]["p50_ms"]]
        result["gate"] = {"p50_ms_lte":150, "pass": all(value is not None and value <= 150 for value in p50s)}
        return result
    finally:
        for raw_path in paths:
            if os.path.exists(raw_path): os.remove(raw_path)


def run_journal_recall(args: argparse.Namespace) -> dict[str, Any]:
    """Measure the local FTS journal path on a 10k-message temporary DB."""
    rows, runs = args.journal_rows, args.retrieval_runs
    if rows < 10000 or rows % 2 or not 1 <= runs <= 100:
        raise ValueError("--journal-rows must be an even value >=10000; --retrieval-runs must be 1..100")
    fd, path = tempfile.mkstemp(prefix="airi-journal-recall-", suffix=".sqlite3"); os.close(fd)
    try:
        store = MemoryStore(path, cache_enabled=False)
        with store._session(immediate=True) as c:
            c.executemany(
                "INSERT INTO conversation_message(session_id,turn_no,role,content,content_hash,recall_chars) VALUES (?,?,?,?,?,?)",
                (("journal-bench", turn, role,
                  (f"archive marker-{turn:05d}" if role == "user" else "acknowledged"),
                  f"{turn}-{role}", 32)
                 for turn in range(1, rows // 2 + 1) for role in ("user", "assistant")),
            )
        query = f"marker-{rows // 2:05d}"
        timings = []
        for _ in range(runs):
            started = time.perf_counter(); recalled = store.journal_recall("journal-bench", query, ())
            timings.append((time.perf_counter() - started) * 1000)
        health = store.health()
        return {"status": "measured", "network_used": False, "message_rows": rows, "runs": runs,
                "journal_fts": health["journal_fts"], "warm": latency_summary(timings),
                "recalled_messages": len(recalled),
                "gate": {"p95_ms_lte": 150,
                         "pass": health["journal_fts"] and bool(recalled)
                         and (latency_summary(timings)["p95_ms"] or 0) <= 150}}
    finally:
        if os.path.exists(path): os.remove(path)


def build_parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(); p.add_argument("--mode", choices=["inventory","extraction","embedding","cloud","retrieval","journal-recall","all"], default="all"); p.add_argument("--report", type=Path)
    p.add_argument("--fixtures", type=Path, default=FIXTURES); p.add_argument("--runs", type=int, default=1); p.add_argument("--model", default="exaone-airi:2.4b"); p.add_argument("--model-digest",type=model_digest,default=""); p.add_argument("--ollama-url", default=DEFAULT_OLLAMA); p.add_argument("--timeout", type=float, default=60); p.add_argument("--num-ctx", type=int, default=8192); p.add_argument("--num-gpu", type=int, default=0); p.add_argument("--seed", type=int, default=42); p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--fixture-id", action="append", default=[], help="Run only the named extraction fixture; repeat to select more than one.")
    p.add_argument("--fail-fast", action="store_true", help="Stop extraction after the first row that fails a gate condition.")
    p.add_argument("--stage-a-contract", choices=["legacy", "conversation-v2b", "conversation-v3-span"], default="conversation-v2b")
    p.add_argument("--gate-profile", choices=sorted(GATE_PROFILES), default=None,
                   help="Extraction gate thresholds; defaults to $AIRI_MEMORY_EXTRACTION_GATE_PROFILE.")
    p.add_argument("--embedding-model", action="append", default=[]); p.add_argument("--embedding-device", choices=["auto","cpu","cuda"], default="auto"); p.add_argument("--embedding-dtype", choices=["float32","float16"], default="float32"); p.add_argument("--local-files-only", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--allow-cloud", action="store_true"); p.add_argument("--cloud-provider", choices=["openai","anthropic"], default="anthropic"); p.add_argument("--cloud-model", default="claude-3-5-haiku-latest")
    p.add_argument("--retrieval-rows", type=int, default=10000); p.add_argument("--retrieval-runs", type=int, default=20); p.add_argument("--journal-rows", type=int, default=10000)
    return p


def main(argv: list[str] | None = None) -> int:
    args=build_parser().parse_args(argv); fixtures=load_fixtures(args.fixtures); modes=[args.mode] if args.mode != "all" else ["inventory","extraction","embedding","cloud"]
    report={"config":{"mode":args.mode,"runs":args.runs,"retrieval_rows":args.retrieval_rows,"retrieval_runs":args.retrieval_runs,"model":args.model,"model_digest":args.model_digest,"timeout_seconds":args.timeout,"temperature":0,"num_ctx":args.num_ctx,"num_gpu":args.num_gpu,"seed":args.seed,"max_tokens":args.max_tokens,"think":False,"fail_fast":args.fail_fast,"stage_a_contract":args.stage_a_contract,"stage_b_contract":"decision-v2.1","comparison_contract":comparison_contract_for_stage_a(args.stage_a_contract),"embedding_batch_size":16,"normalize_embeddings":True,"embedding_device":args.embedding_device,"embedding_dtype":args.embedding_dtype,"local_files_only":args.local_files_only,"allow_cloud":args.allow_cloud,"reproducibility":reproducibility_metadata(args.fixtures, args.stage_a_contract)}, "results":{}}
    actions={"inventory":inventory,"extraction":run_extraction,"embedding":run_embedding,"cloud":run_cloud,"retrieval":run_retrieval,"journal-recall":run_journal_recall}
    for mode in modes: report["results"][mode]=actions[mode](args) if mode in {"retrieval", "journal-recall"} else actions[mode](args, fixtures)
    output=json.dumps(report, ensure_ascii=False, indent=2)
    if args.report: args.report.write_text(output+"\n", encoding="utf-8")
    print(output); return 0

if __name__ == "__main__": raise SystemExit(main())
