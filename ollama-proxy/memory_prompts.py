"""Stage A/B extraction prompts, lifted verbatim from the tech reference.

Source: airi_docs/AIRI-MEMORY-TECH-REFERENCE.md §1 (talkain production prompts).
These strings are a ported asset, not a design surface: the reference is explicit
that they must not be re-invented, so this module keeps them byte-identical and
carries no logic. Every `{` in here is literal - never run .format() on them.
"""

from __future__ import annotations

STAGE_A_SYSTEM_PROMPT = """\
You extract atomic memory items from input.
Input = CHARACTER SHEET (sections under [turn 1]) OR CONVERSATION turns.

## Input format
The user message is wrapped in two blocks:
  <character>...meta header about the speaker/scope (e.g., "name: 하람", "persona for room=345, name: 토카인")...</character>
  <turns>...the actual sheet or conversation lines to extract from...</turns>
Treat <character> as orientation only — it identifies who the input is about.
NEVER emit entity/fact/relation derived from the <character> block itself.
Extract ONLY from <turns>.

## CRITICAL — output shape (do NOT violate)
"kind" MUST be EXACTLY one of: "entity" | "fact" | "relation".
NEVER put a subtype value (person/location/item/moment/trait) in the "kind" field.
  ✅ {"kind":"entity","subtype":"location",...}     ❌ {"kind":"location","subtype":"location",...}
  ✅ {"kind":"fact","subtype":"moment",...}         ❌ {"kind":"moment","subtype":"moment",...}

## Subtypes (strict)
- entity.subtype: person | location | item | organization | event
- fact.subtype:   trait | moment  (REQUIRED, exactly one. role/preference/boundary/warning/ability/goal → trait. event-fact → moment.)
- relation.subtype: free-form Korean noun (인물간: 가족/친구/호적수/라이벌/동행자/연인 후보 ... 인물↔장소: 방문지/근거지/출입처 ... 인물↔조직: 소속/재학 ... 인물↔아이템: 소지/사용)

## Connectivity rule — graph must stay connected
EVERY new location/organization/item entity MUST come paired with AT LEAST ONE relation tying it to a person (typically the main character).
Emitting an entity without its relation = isolated node = INCOMPLETE.

## What to extract
CHARACTER SHEETS: EXTRACT EXHAUSTIVELY — author-curated, every section / bullet / NPC entry / lorebook line is meaningful.
CONVERSATION turns: SIGNAL FILTER — "Will a future turn likely reference this?" If unsure → SKIP. 0–3 items/turn normal.

EXTRACT: identity reveals, persistent state shifts, key events with consequences, new entities, relationship changes.
SKIP (CONVERSATION only): posture/movement, ephemeral emotion, single dialogue summaries, routine actions, restatements, scene state.

## Kind rules
### entity
- Emit ONLY on FIRST appearance OR canonical identity change. Recurring entity with unchanged identity → emit NOTHING.
- content = WHO/WHAT they ARE (role, traits, appearance). 1 sentence under 120 chars.
- FORBIDDEN content patterns: "X did Y", "X felt Z", "X said ...", "X is at LOCATION" — those are moments, not identity.

### fact (REQUIRED subtype: trait OR moment)
- **trait** = persistent identity attribute. Character sheets: every distinctive ability/principle/goal/trigger/personality bullet → ONE trait, subjectNames=[character].
- **moment** = turn-bounded event/state shift/environment change. subjectNames = involved entities (people, locations). Omit if ambient.
- ⚠️ Enduring tie BETWEEN TWO entities → relation, NOT moment.
- Dedup: if you emit moment for X, do NOT also emit entity for X. Pick one — fact wins.

### relation
- Directed link between two entities. sourceName + targetName + free-form subtype.

## Character sheet trigger patterns (ALWAYS apply when input is a sheet)
**Main character (introduction + role)**: entity(person) + multiple trait facts for distinctive attributes.

**{{user}} (the user, ALWAYS emit as a person entity)**: If {{user}} appears anywhere in the input,
emit ONE entity(person, name="{{user}}", content = the user's role in this world — e.g., "역대 최고로 평가받는 용사, 마족으로 위장한 수석 보좌관.").
Skipping this leaves {{user}}-related relations (호적수/보좌/소지 etc) dangling in the graph.

**NPC mapping section** ("NPC 관계 매핑"): For EACH NPC, emit ALL THREE:
  (a) entity(person)
  (b) relation(main char → NPC, subtype = labeled role: 가족/친구/라이벌/연인 후보/지인 etc)
  (c) 1–3 trait facts for NPC's distinctive 말투/행동/능력 (subjectNames=[NPC])

**Structured trait sections** (말투톤, 트리거 모드, 행동 지침, 불가침 원칙, 목표, 성격, 능력):
  Each meaningful bullet → ONE trait fact, subjectNames=[main character].

**Lorebook entries** (`[location aliases] event description`): emit ALL THREE:
  (a) entity(location), first name only inside the bracket (other names are aliases)
  (b) fact(moment), subjectNames=[main char + named participants], content = the described event
  (c) relation(main char → location, subtype: 방문지/근거지/출입처)

**Organizations** (schools/guilds/kingdoms in world scenario/intro): entity(organization) + relation(main char → org, subtype: 소속/재학).
  Coexist with location entities for specific places within: 마왕 사관학교(organization) + 마왕 사관학교 옥상(location).

**Items** (recurring objects — weapons, artifacts, signature documents): entity(item) + relation(owner → item, subtype: 소지/사용/보관).

## General rules
- Use natural-language names, NOT IDs. Same name across all items referring to the same entity.
- Preserve original language (Korean → Korean content). Do NOT translate or invent.
- {{user}} placeholder represents the user. Treat as a person entity — keep "{{user}}" literally in name/content; do NOT invent a real name. ALWAYS emit entity(person, name="{{user}}") if it appears in the input.
- Skip [R-N] suggested replies and [S] scene meta.

## Examples (✅ correct shape)
{"kind":"entity","subtype":"person","name":"한나","content":"마을 우물지기, 50대 여성."}
{"kind":"entity","subtype":"location","name":"마을 우물","content":"마을 중앙의 우물."}
{"kind":"entity","subtype":"organization","name":"마왕 사관학교","content":"미래의 마왕들이 마왕학을 배우는 학교."}
{"kind":"entity","subtype":"item","name":"위장 신분증","content":"{{user}}가 마족으로 위장해 사용하는 신분증."}
{"kind":"fact","subtype":"trait","subjectNames":["한나"],"content":"위험 앞에서 침착하다.","turnRange":[1,1]}
{"kind":"fact","subtype":"moment","subjectNames":["한나","마을 우물"],"content":"우물가에서 한나가 무릎을 꿇었다.","turnRange":[5,5]}
{"kind":"relation","subtype":"가족","sourceName":"체이스","targetName":"라임","content":"후견인 관계."}
{"kind":"relation","subtype":"방문지","sourceName":"체이스","targetName":"마왕 사관학교 옥상","content":"가면을 내려놓는 공간."}
{"kind":"relation","subtype":"소속","sourceName":"체이스","targetName":"마왕 사관학교","content":"수석 후보생."}
{"kind":"relation","subtype":"소지","sourceName":"{{user}}","targetName":"위장 신분증","content":"마족 위장용."}

## ❌ wrong patterns to avoid
{"kind":"location",...}                                          → use {"kind":"entity","subtype":"location",...}
{"kind":"entity","subtype":"person","content":"한나가 칼을 뽑았다."}  → entity content cannot be an action. Use fact(moment).
location entity emitted alone without relation                   → ALWAYS pair with relation(person → location).

## Output schema (strict JSON, no prose)
{
  "extracted": [
    {"turnNumber":1,"kind":"entity","subtype":"person","name":"...","content":"..."},
    {"turnNumber":1,"kind":"fact","subtype":"trait","subjectNames":["..."],"content":"...","turnRange":[1,1]},
    {"turnNumber":1,"kind":"fact","subtype":"moment","subjectNames":["..."],"content":"...","turnRange":[1,1]},
    {"turnNumber":1,"kind":"relation","subtype":"...","sourceName":"...","targetName":"...","content":"..."}
  ]
}
"""

STAGE_B_SYSTEM_PROMPT = """\
You decide how to apply extracted memory items to the existing knowledge base.

Given:
- extracted[]: Stage A output (entity/fact/relation items, with subjectNames/sourceName/targetName).
- candidates[]: existing memory rows mapped to short aliases (e.g., e0, f1, r2) plus their content.

For each extracted item, produce one MemoryOperation:
- ADD_ENTITY / ADD_FACT / ADD_RELATION   — new item not in candidates
- UPDATE_ENTITY / UPDATE_FACT / UPDATE_RELATION — refines an existing candidate (reuse its alias)
- SUPERSEDE_ENTITY / SUPERSEDE_FACT / SUPERSEDE_RELATION — replaces an outdated candidate
- NOOP — extracted item duplicates an existing candidate exactly (skip)

Rules:
1. Map names → aliases when referring to candidates (alias / sourceAlias / targetAlias / subjectAliases).
2. For ADD_*, assign a new alias starting with e/f/r prefix (e.g., e10).
3. ADD_ENTITY / UPDATE_ENTITY MUST include the `name` field verbatim from the extracted item.
   Keep "{{user}}" placeholder literal — do NOT substitute with a real user name.
4. ADD_RELATION / UPDATE_RELATION MUST include `sourceAlias` and `targetAlias`.
5. ADD_FACT / UPDATE_FACT MUST include `subjectAliases` mapped from extracted subjectNames.
6. SUPERSEDE_* requires a non-empty `reason` field.
7. Keep content terse: facts ≤ 200 chars.
8. Preserve original language.

Respond with JSON only. Field set per op type shown below — include ALL listed fields:
{
  "operations": [
    { "op": "ADD_ENTITY", "sourceTurnNumber": 1,
      "alias": "e10", "subtype": "person",
      "name": "{{user}}", "content": "...",
      "turnRange": null, "reason": null },
    { "op": "ADD_FACT", "sourceTurnNumber": 1,
      "alias": "f10", "subtype": "trait", "content": "...",
      "subjectAliases": ["e10"], "turnRange": [1,1],
      "reason": null },
    { "op": "ADD_RELATION", "sourceTurnNumber": 1,
      "alias": "r10", "subtype": "소지",
      "sourceAlias": "e10", "targetAlias": "e0",
      "content": "...", "reason": null },
    { "op": "UPDATE_ENTITY", "sourceTurnNumber": 1,
      "alias": "e0", "subtype": "person",
      "name": "...", "content": "...",
      "reason": null },
    { "op": "SUPERSEDE_ENTITY", "sourceTurnNumber": 1,
      "alias": "e0", "reason": "페르소나 변경" },
    { "op": "NOOP", "sourceTurnNumber": 1, "alias": "f3" }
  ]
}
"""
