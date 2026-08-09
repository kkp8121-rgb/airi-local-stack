"""Compact Stage-B decision contract and deterministic operation compiler."""
from __future__ import annotations
import hashlib
import json
from typing import Any

_DECISION_ALIAS = {"type": "string", "minLength": 1}
_DECISION_REASON = {"type": "string", "minLength": 1, "maxLength": 500}


def decision_schema_for_count(count: int) -> dict[str, Any]:
    """Return the exact Stage-B structured-output contract for ``count`` items."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("decision count must be a non-negative integer")
    index = {"type": "integer", "minimum": 0}
    if count:
        index["maximum"] = count - 1
    def action(action: str, alias: dict[str, Any], reason: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False,
                "required": ["sourceItemIndex", "action", "candidateAlias", "reason"],
                "properties": {"sourceItemIndex": index, "action": {"const": action},
                               "candidateAlias": alias, "reason": reason}}
    return {"type": "object", "additionalProperties": False, "required": ["decisions"],
            "properties": {"decisions": {"type": "array", "minItems": count, "maxItems": count,
                "items": {"oneOf": [
                    action("add", {"type": "null"}, {"type": "null"}),
                    action("update", _DECISION_ALIAS, {"type": "null"}),
                    action("noop", _DECISION_ALIAS, {"type": "null"}),
                    action("supersede", _DECISION_ALIAS, _DECISION_REASON),
                ]}}}}


def decision_schema_for_items(extracted: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a bounded, content-free decision schema scoped to each source item.

    The model can only select aliases from candidates of the corresponding
    extracted item's kind.  Compiler validation remains the final authority.
    """
    if not isinstance(extracted, list) or not isinstance(candidates, list):
        raise ValueError("extracted and candidates must be lists")
    kinds: list[str] = []
    for item in extracted:
        kind = item.get("kind") if isinstance(item, dict) else None
        if kind not in {"entity", "fact", "relation"}:
            raise ValueError("extracted item has an invalid kind")
        kinds.append(kind)
    aliases_by_kind: dict[str, list[str]] = {"entity": [], "fact": [], "relation": []}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        alias, kind = candidate.get("alias"), candidate.get("kind")
        if kind in aliases_by_kind and isinstance(alias, str) and alias:
            aliases_by_kind[kind].append(alias)
    # Preserve candidate order (the bounded store selection is deterministic),
    # while de-duplicating an enum without embedding any source text.
    for kind, aliases in aliases_by_kind.items():
        aliases_by_kind[kind] = list(dict.fromkeys(aliases))

    indices_by_kind: dict[str, list[int]] = {"entity": [], "fact": [], "relation": []}
    for index, kind in enumerate(kinds):
        indices_by_kind[kind].append(index)

    def branch(indices: list[int], action: str, alias: dict[str, Any], reason: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False,
                "required": ["sourceItemIndex", "action", "candidateAlias", "reason"],
                "properties": {"sourceItemIndex": {"enum": indices}, "action": {"const": action},
                               "candidateAlias": alias, "reason": reason}}

    alternatives: list[dict[str, Any]] = []
    for kind in ("entity", "fact", "relation"):
        indices = indices_by_kind[kind]
        if not indices:
            continue
        alternatives.append(branch(indices, "add", {"type": "null"}, {"type": "null"}))
        aliases = aliases_by_kind[kind]
        if aliases:
            allowed = {"enum": aliases}
            alternatives.extend((
                branch(indices, "update", allowed, {"type": "null"}),
                branch(indices, "noop", allowed, {"type": "null"}),
                branch(indices, "supersede", allowed, _DECISION_REASON),
            ))
    items: dict[str, Any] = {"oneOf": alternatives} if alternatives else {}
    count = len(kinds)
    return {"type": "object", "additionalProperties": False, "required": ["decisions"],
            "properties": {"decisions": {"type": "array", "minItems": count, "maxItems": count,
                                            "items": items}}}


# Stable one-item template used only for legacy imports and reproducibility IDs.
# Requests must use ``decision_schema_for_items(extracted, candidates)``.
DECISION_SCHEMA_TEMPLATE = decision_schema_for_count(1)
DECISION_SCHEMA = DECISION_SCHEMA_TEMPLATE


def decision_factory_probe_sha256() -> str:
    """Fingerprint the active grouped-schema factory without user content."""
    probe_extracted = [{"kind": "entity"}, {"kind": "fact"}, {"kind": "relation"}]
    probe_candidates = [
        {"kind": "entity", "alias": "e0"}, {"kind": "entity", "alias": "e0"},
        {"kind": "entity", "alias": "e1"}, {"kind": "fact", "alias": "f0"},
    ]
    schema = decision_schema_for_items(probe_extracted, probe_candidates)
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DecisionContractError(ValueError):
    def __init__(self, code: str): self.code=code; super().__init__(code)

def parse_stage_b_decisions(raw: str | bytes | dict[str, Any]) -> dict[str, Any]:
    try: value = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (TypeError, json.JSONDecodeError) as exc: raise DecisionContractError("decision_invalid_json") from exc
    if not isinstance(value, dict) or set(value) != {"decisions"} or not isinstance(value["decisions"], list): raise DecisionContractError("decision_invalid_root")
    for item in value["decisions"]:
        if not isinstance(item, dict) or set(item) != {"sourceItemIndex","action","candidateAlias","reason"}: raise DecisionContractError("decision_invalid_fields")
        index, action, alias, reason = item["sourceItemIndex"], item["action"], item["candidateAlias"], item["reason"]
        if not isinstance(index, int) or isinstance(index, bool) or index < 0: raise DecisionContractError("decision_invalid_index")
        if action not in {"add","update","supersede","noop"}: raise DecisionContractError("decision_invalid_action")
        if alias is not None and (not isinstance(alias, str) or not alias): raise DecisionContractError("decision_invalid_alias")
        if reason is not None and (not isinstance(reason, str) or not reason or len(reason) > 500): raise DecisionContractError("decision_invalid_reason")
        if action == "add" and (alias is not None or reason is not None): raise DecisionContractError("decision_add_null")
        if action in {"update","noop"} and (alias is None or reason is not None): raise DecisionContractError("decision_existing_null")
        if action == "supersede" and (alias is None or reason is None): raise DecisionContractError("decision_supersede_reason")
    return value

def format_stage_b_input(extracted: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> str:
    safe=[]
    for c in candidates:
        item={key:c.get(key) for key in ("alias","kind","subtype","name","sourceAlias","targetAlias","subjectAliases") if key in c}
        item["content"] = str(c.get("content", ""))[:500]
        safe.append(item)
    return json.dumps({"extracted":[dict(item,sourceItemIndex=i) for i,item in enumerate(extracted)],"candidates":safe},ensure_ascii=False,separators=(",",":"))

def compile_decisions(extracted: list[dict[str, Any]], candidates: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(decisions) != len(extracted): raise DecisionContractError("decision_coverage")
    by_index={}
    for decision in decisions:
        i=decision["sourceItemIndex"]
        if i in by_index or i >= len(extracted): raise DecisionContractError("decision_coverage")
        by_index[i]=decision
    if set(by_index) != set(range(len(extracted))): raise DecisionContractError("decision_coverage")
    aliases={str(c.get("alias")):c for c in candidates if isinstance(c,dict) and isinstance(c.get("alias"),str)}
    if len(aliases)!=len(candidates): raise DecisionContractError("candidate_aliases")
    used=set(aliases)
    def new_alias(kind: str) -> str:
        prefix={"entity":"e","fact":"f","relation":"r"}[kind]; n=0
        while prefix+str(n) in used: n+=1
        value=prefix+str(n); used.add(value); return value
    chosen={}
    for i,item in enumerate(extracted):
        decision=by_index[i]; action=decision["action"]; candidate=aliases.get(decision["candidateAlias"]) if decision["candidateAlias"] else None
        if action != "add" and not candidate: raise DecisionContractError("candidate_missing")
        if action != "add" and candidate.get("kind") != item.get("kind"): raise DecisionContractError("candidate_kind")
        chosen[i]=new_alias(item["kind"]) if action=="add" else str(decision["candidateAlias"])
    names: dict[str,list[str]]={}
    for c in candidates:
        if c.get("kind")=="entity" and isinstance(c.get("name"),str): names.setdefault(c["name"],[]).append(c["alias"])
    for i,item in enumerate(extracted):
        if item["kind"]=="entity": names.setdefault(item["name"],[]).append(chosen[i])
    def resolve(name: str) -> str:
        values=list(dict.fromkeys(names.get(name,[])))
        if not values: raise DecisionContractError("entity_reference_missing")
        if len(values)!=1: raise DecisionContractError("entity_reference_ambiguous")
        return values[0]
    operations=[]
    for i,item in enumerate(extracted):
        d=by_index[i]; action=d["action"]; kind=item["kind"]; alias=chosen[i]
        if action=="noop": operations.append({"op":"NOOP","sourceItemIndex":i,"sourceTurnNumber":item["turnNumber"],"alias":alias}); continue
        op={"op":({"add":"ADD_","update":"UPDATE_","supersede":"SUPERSEDE_"}[action]+kind.upper()),"sourceItemIndex":i,"sourceTurnNumber":item["turnNumber"],"alias":alias}
        if kind=="entity": op.update(subtype=item["subtype"],name=item["name"],content=item["content"],turnRange=None,reason=d["reason"])
        elif kind=="fact": op.update(subtype=item["subtype"],content=item["content"],subjectAliases=[resolve(n) for n in item["subjectNames"]],turnRange=item["turnRange"],reason=d["reason"])
        else: op.update(subtype=item["subtype"],sourceAlias=resolve(item["sourceName"]),targetAlias=resolve(item["targetName"]),content=item["content"],reason=d["reason"])
        operations.append(op)
    return sorted(operations,key=lambda op: ({"ENTITY":0,"FACT":1,"RELATION":2}.get(op["op"].rsplit("_",1)[-1],3),op["sourceItemIndex"]))
