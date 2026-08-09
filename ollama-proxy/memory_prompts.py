"""Canonical Stage A/B prompts and JSON schemas for the memory M0 gate.

Keep these strings separate from the benchmark runner: M1/M2 can import the
same contract without depending on a benchmarking executable.
"""

from __future__ import annotations


STAGE_A_SYSTEM_PROMPT = r'''You extract atomic memory items from input.
Input = CHARACTER SHEET (sections under [turn 1]) OR CONVERSATION turns.

## Input format
The user message is wrapped in two blocks:
  <character>...meta header about the speaker/scope...</character>
  <turns>...the actual sheet or conversation lines to extract from...</turns>
Treat <character> as orientation only — it identifies who the input is about.
NEVER emit entity/fact/relation derived from the <character> block itself.
Extract ONLY from <turns>.

## CRITICAL — output shape (do NOT violate)
"kind" MUST be EXACTLY one of: "entity" | "fact" | "relation".
NEVER put a subtype value (person/location/item/moment/trait) in the "kind" field.

## Subtypes (strict)
- entity.subtype: person | location | item | organization | event
- fact.subtype: trait | moment (REQUIRED, exactly one. role/preference/boundary/warning/ability/goal = trait. event-fact = moment.)
- relation.subtype: free-form Korean noun (family/friend/enemy/rival/lover, residence/visited/access point, affiliation/enrollment, item ownership/use)

## Connectivity rule — graph must stay connected
EVERY new location/organization/item entity MUST come paired with AT LEAST ONE relation tying it to a person (typically the main character).
Emitting an entity without its relation = isolated node = INCOMPLETE.

## What to extract
CHARACTER SHEETS: EXTRACT EXHAUSTIVELY — author-curated, every section / bullet / NPC entry / lorebook line is meaningful.
CONVERSATION turns: SIGNAL FILTER — "Will a future turn likely reference this?" If unsure — SKIP. 0 items/turn normal.
EXTRACT: identity reveals, persistent state shifts, key events with consequences, new entities, relationship changes.
SKIP (CONVERSATION only): posture/movement, ephemeral emotion, single dialogue summaries, routine actions, restatements, scene state.

## Kind rules
### entity
- Emit ONLY on FIRST appearance OR canonical identity change. Recurring entity with unchanged identity — emit NOTHING.
- content = WHO/WHAT they ARE (role, traits, appearance). 1 sentence under 120 chars.
- FORBIDDEN content patterns: "X did Y", "X felt Z", "X said ...", "X is at LOCATION" — those are moments, not identity.
### fact (REQUIRED subtype: trait OR moment)
- trait = persistent identity attribute. Character sheets: every distinctive ability/principle/goal/trigger/personality bullet — ONE trait, subjectNames=[character].
- moment = turn-bounded event/state shift/environment change. subjectNames = involved entities (people, locations). Omit if ambient.
- Enduring tie BETWEEN TWO entities = relation, NOT moment.
- Dedup: if you emit moment for X, do NOT also emit entity for X. Pick one — fact wins.
### relation
- Directed link between two entities. sourceName + targetName + free-form subtype.

## Character sheet trigger patterns (ALWAYS apply when input is a sheet)
Main character (introduction + role): entity(person) + multiple trait facts for distinctive attributes.
{{user}} (the user, ALWAYS emit as a person entity): If {{user}} appears anywhere in the input, emit ONE entity(person, name="{{user}}", content = the user's role in this world). Skipping this leaves {{user}}-related relations dangling.
NPC mapping section: for EACH NPC emit entity(person), relation(main character -> NPC, labeled role), and 1+ trait facts for distinctive speech/behavior/ability.
Structured trait sections (speech, trigger mode, behavior guidelines, values, goals, personality, abilities): each meaningful bullet = ONE trait fact, subjectNames=[main character].
Lorebook entries ([location aliases] event description): entity(location; first bracket name only), fact(moment; main character + named participants), relation(main character -> location; residence/visited/access point).
Organizations: entity(organization) + relation(main character -> organization; affiliation/enrollment). Coexist with location entities for specific places within.
Items: entity(item) + relation(owner -> item; ownership/use/keeping).

## General rules
- Use natural-language names, NOT IDs. Same name across all items referring to the same entity.
- Preserve original language (Korean = Korean content). Do NOT translate or invent.
- {{user}} placeholder represents the user. Treat as a person entity — keep "{{user}}" literally in name/content; do NOT invent a real name. ALWAYS emit entity(person, name="{{user}}") if it appears in the input.
- Skip [R-N] suggested replies and [S] scene meta.

## Output schema (strict JSON, no prose)
{"extracted":[
 {"turnNumber":1,"kind":"entity","subtype":"person","name":"...","content":"..."},
 {"turnNumber":1,"kind":"fact","subtype":"trait","subjectNames":["..."],"content":"...","turnRange":[1,1]},
 {"turnNumber":1,"kind":"fact","subtype":"moment","subjectNames":["..."],"content":"...","turnRange":[1,1]},
 {"turnNumber":1,"kind":"relation","subtype":"...","sourceName":"...","targetName":"...","content":"..."}
]}'''

# Compact production contract for live conversation extraction.  The full prompt
# above remains the legacy character-sheet control in the benchmark.
STAGE_A_CONVERSATION_SYSTEM_PROMPT = r'''You extract atomic memory items from conversation input.
Use <turns> as the only factual evidence. <character> is only for speaker/scope name resolution.
Extract only information a future turn will likely reference: durable identity, trait, goal, boundary,
consequential event, or relationship change. An existing entity's durable identity change may be an entity.
Skip ephemeral movement, emotion, routine utterances, restatements, [S], and [R-N]. Zero items is normal.
Every subjectNames, sourceName, and targetName value must be an exact name appearing in <turns>, {{user}},
or the speaker name in <character>; never invent a name. A new location, organization, or item entity needs
a relation to a person. Follow the exact JSON schema and output JSON only.'''

STAGE_B_SYSTEM_PROMPT = r'''You decide how to apply extracted memory items to the existing knowledge base.

Given:
- extracted[]: Stage A output (entity/fact/relation items, with subjectNames/sourceName/targetName).
- candidates[]: existing memory rows mapped to short aliases (e.g., e0, f1, r2) plus their content.

For each extracted item, produce one MemoryOperation. Copy that item's
`sourceItemIndex` exactly into the operation; every index must appear once:
- ADD_ENTITY / ADD_FACT / ADD_RELATION — new item not in candidates
- UPDATE_ENTITY / UPDATE_FACT / UPDATE_RELATION — refines an existing candidate (reuse its alias)
- SUPERSEDE_ENTITY / SUPERSEDE_FACT / SUPERSEDE_RELATION — replaces an outdated candidate
- NOOP — extracted item duplicates an existing candidate exactly (skip)

Rules:
1. Map names → aliases when referring to candidates (alias / sourceAlias / targetAlias / subjectAliases).
2. For ADD_*, assign a new alias starting with e/f/r prefix (e.g., e10).
3. ADD_ENTITY / UPDATE_ENTITY MUST include the `name` field verbatim from the extracted item. Keep "{{user}}" placeholder literal — do NOT substitute with a real user name.
4. ADD_RELATION / UPDATE_RELATION MUST include `sourceAlias` and `targetAlias`.
5. ADD_FACT / UPDATE_FACT MUST include `subjectAliases` mapped from extracted subjectNames.
6. SUPERSEDE_* creates a replacement row, marks the old alias superseded, and
   links old.superseded_by to the replacement. Include the same content and
   reference fields as UPDATE_* plus a non-empty `reason`.
7. Copy subtype and content verbatim from that indexed extracted item. For
   entities also copy name; for facts also copy turnRange. Do not rewrite them.
8. Keep content terse: facts ≤200 chars.
9. Preserve original language.

Respond with JSON only. Field set per op type shown below — include ALL listed fields:
{"operations":[
 {"op":"ADD_ENTITY","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"e10","subtype":"person","name":"{{user}}","content":"...","turnRange":null,"reason":null},
 {"op":"ADD_FACT","sourceItemIndex":1,"sourceTurnNumber":1,"alias":"f10","subtype":"trait","content":"...","subjectAliases":["e10"],"turnRange":[1,1],"reason":null},
 {"op":"ADD_RELATION","sourceItemIndex":2,"sourceTurnNumber":1,"alias":"r10","subtype":"...","sourceAlias":"e10","targetAlias":"e0","content":"...","reason":null},
 {"op":"UPDATE_ENTITY","sourceItemIndex":3,"sourceTurnNumber":1,"alias":"e0","subtype":"person","name":"...","content":"...","reason":null},
 {"op":"SUPERSEDE_ENTITY","sourceItemIndex":4,"sourceTurnNumber":1,"alias":"e0","subtype":"person","name":"...","content":"replacement","turnRange":null,"reason":"why the old row is outdated"},
 {"op":"NOOP","sourceItemIndex":5,"sourceTurnNumber":1,"alias":"f3"}
]}'''

STAGE_B_DECISION_SYSTEM_PROMPT = r'''For every sourceItemIndex, emit exactly one compact decision JSON object.

Action table:
- add: new item or no equivalent candidate; candidateAlias=null; reason=null.
- noop: exact duplicate of an existing same-kind candidate; use its supplied alias; reason=null.
- update: non-contradictory refinement of the same existing item; use its supplied alias; reason=null.
- supersede: existing item is outdated or contradicted; use its supplied alias; reason is short and nonempty.

Use only supplied candidate aliases. Do not echo source content, names, subtypes, turns, or
references, and do not invent aliases. Output JSON only.'''

_POSITIVE_INT = {"type": "integer", "minimum": 1}
_NON_NEGATIVE_INT = {"type": "integer", "minimum": 0}
_TURN_RANGE = {"type": "array", "items": _POSITIVE_INT, "minItems": 2, "maxItems": 2}
_TEXT = {"type": "string", "minLength": 1}
_GRAPH_REFS = {"type":"array", "items":_TEXT, "minItems":1, "maxItems":16, "uniqueItems":True}
STAGE_A_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["extracted"],
    "properties": {"extracted": {"type": "array", "items": {"oneOf": [
        {"type":"object","additionalProperties":False,"required":["turnNumber","kind","subtype","name","content"],"properties":{"turnNumber":_POSITIVE_INT,"kind":{"const":"entity"},"subtype":{"enum":["person","location","item","organization","event"]},"name":_TEXT,"content":_TEXT}},
        {"type":"object","additionalProperties":False,"required":["turnNumber","kind","subtype","subjectNames","content","turnRange"],"properties":{"turnNumber":_POSITIVE_INT,"kind":{"const":"fact"},"subtype":{"enum":["trait","moment"]},"subjectNames":_GRAPH_REFS,"content":_TEXT,"turnRange":_TURN_RANGE}},
        {"type":"object","additionalProperties":False,"required":["turnNumber","kind","subtype","sourceName","targetName","content"],"properties":{"turnNumber":_POSITIVE_INT,"kind":{"const":"relation"},"subtype":_TEXT,"sourceName":_TEXT,"targetName":_TEXT,"content":_TEXT}}
    ]}}},
}
STAGE_B_SCHEMA = {
    "type":"object", "additionalProperties":False, "required":["operations"],
    "properties":{"operations":{"type":"array","items":{"oneOf":[
        {"type":"object","additionalProperties":False,"required":["op","sourceItemIndex","sourceTurnNumber","alias","subtype","name","content","turnRange","reason"],"properties":{"op":{"enum":["ADD_ENTITY","UPDATE_ENTITY"]},"sourceItemIndex":_NON_NEGATIVE_INT,"sourceTurnNumber":_POSITIVE_INT,"alias":_TEXT,"subtype":{"enum":["person","location","item","organization","event"]},"name":_TEXT,"content":_TEXT,"turnRange":{"anyOf":[_TURN_RANGE,{"type":"null"}]},"reason":{"anyOf":[_TEXT,{"type":"null"}]} }},
        {"type":"object","additionalProperties":False,"required":["op","sourceItemIndex","sourceTurnNumber","alias","subtype","content","subjectAliases","turnRange","reason"],"properties":{"op":{"enum":["ADD_FACT","UPDATE_FACT"]},"sourceItemIndex":_NON_NEGATIVE_INT,"sourceTurnNumber":_POSITIVE_INT,"alias":_TEXT,"subtype":{"enum":["trait","moment"]},"content":_TEXT,"subjectAliases":_GRAPH_REFS,"turnRange":_TURN_RANGE,"reason":{"anyOf":[_TEXT,{"type":"null"}]}}},
        {"type":"object","additionalProperties":False,"required":["op","sourceItemIndex","sourceTurnNumber","alias","subtype","sourceAlias","targetAlias","content","reason"],"properties":{"op":{"enum":["ADD_RELATION","UPDATE_RELATION"]},"sourceItemIndex":_NON_NEGATIVE_INT,"sourceTurnNumber":_POSITIVE_INT,"alias":_TEXT,"subtype":_TEXT,"sourceAlias":_TEXT,"targetAlias":_TEXT,"content":_TEXT,"reason":{"anyOf":[_TEXT,{"type":"null"}]}}},
        {"type":"object","additionalProperties":False,"required":["op","sourceItemIndex","sourceTurnNumber","alias","subtype","name","content","turnRange","reason"],"properties":{"op":{"const":"SUPERSEDE_ENTITY"},"sourceItemIndex":_NON_NEGATIVE_INT,"sourceTurnNumber":_POSITIVE_INT,"alias":_TEXT,"subtype":{"enum":["person","location","item","organization","event"]},"name":_TEXT,"content":_TEXT,"turnRange":{"anyOf":[_TURN_RANGE,{"type":"null"}]},"reason":_TEXT}},
        {"type":"object","additionalProperties":False,"required":["op","sourceItemIndex","sourceTurnNumber","alias","subtype","content","subjectAliases","turnRange","reason"],"properties":{"op":{"const":"SUPERSEDE_FACT"},"sourceItemIndex":_NON_NEGATIVE_INT,"sourceTurnNumber":_POSITIVE_INT,"alias":_TEXT,"subtype":{"enum":["trait","moment"]},"content":_TEXT,"subjectAliases":_GRAPH_REFS,"turnRange":_TURN_RANGE,"reason":_TEXT}},
        {"type":"object","additionalProperties":False,"required":["op","sourceItemIndex","sourceTurnNumber","alias","subtype","sourceAlias","targetAlias","content","reason"],"properties":{"op":{"const":"SUPERSEDE_RELATION"},"sourceItemIndex":_NON_NEGATIVE_INT,"sourceTurnNumber":_POSITIVE_INT,"alias":_TEXT,"subtype":_TEXT,"sourceAlias":_TEXT,"targetAlias":_TEXT,"content":_TEXT,"reason":_TEXT}},
        {"type":"object","additionalProperties":False,"required":["op","sourceItemIndex","sourceTurnNumber","alias"],"properties":{"op":{"const":"NOOP"},"sourceItemIndex":_NON_NEGATIVE_INT,"sourceTurnNumber":_POSITIVE_INT,"alias":_TEXT}}
    ]}}},
}
