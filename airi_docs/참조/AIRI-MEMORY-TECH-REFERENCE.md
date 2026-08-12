# AIRI 기억 계층 기술 레퍼런스 (트랙 M 구현 자산)

- 작성일: 2026-08-06
- 목적: 계획서 v2.1 트랙 M(기억 계층 + 클라우드 LLM)을 **클론 레포 없는 환경에서** 구현할 수 있도록, 원본 코드에서 추출한 프롬프트 원문·공식·알고리즘을 자기완결적으로 수록
- 출처: `ovencode-avatarplay/talkain-api`(C#/.NET 캐릭터 챗봇 프로덕션), `ovencode-avatarplay/rag_rnd`(Python RAG 연구) — 실측 감사는 `AIRI-RAG-REPOS-AUDIT-2026-08-06.md`
- 사용법: 아래 자산은 검증된 원문/공식이므로 **재발명하지 말고 이식**한다. 언어는 자유(프록시는 Python/Node 권장), C# 고유 부분은 로직만 옮긴다.

---

## §1. 기억 추출 프롬프트 (talkain Stage A/B — 원문 그대로)

2단 추출: Stage A가 대화/캐릭터 시트를 원자적 항목으로 분해하고, Stage B가 기존 기억 후보(top-5)와 대조해 적용 연산을 결정한다. 입력은 `<character>`(메타)/`<turns>`(본문) 블록, Stage B는 `<extracted>`/`<candidates>` 블록으로 감싼 user 메시지 1개.

주의사항 (원본 운영 경험):
- 원본은 gpt-5.4-mini 사용 — **"분해는 결정론적이라 nano급 충분" 가정은 품질 미달로 실패**했음. 로컬 소형 모델 적용 시 M0 게이트 실측 필수. (작성 당시 로컬 모델은 EXAONE이었고, 2026-08-11~12에 `midm-airi:2.0-mini`로 교체됐다. Mi:dm은 추출기 후보로 아직 미측정이다.)
- 원본은 structured output 미사용(코드펜스 스트립+JSON 파싱, fail-soft). 소형 모델은 준수력이 낮으므로 **JSON schema/GBNF 강제 권장**.
- 캐릭터 base(페르소나 시트) 추출은 Stage B 생략 fast-path (후보가 없으므로).
- 트리거: 응답 완료 후 fire-and-forget, 미추출 메시지 ≥3 + 세션 종료 시 강제 flush. JSON/coverage 같은 품질 실패 5회 시 skip(dead-letter), 세션 재시작 시 리셋. worker/model/transport 일시 장애는 품질 실패에 포함하지 않고 pending을 보존해 bounded backoff한다.

### Stage A 시스템 프롬프트 (원문)

```text
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
```

### Stage B 시스템 프롬프트 (원문)

```text
You decide how to apply extracted memory items to the existing knowledge base.

Given:
- extracted[]: Stage A output (entity/fact/relation items, with subjectNames/sourceName/targetName).
- candidates[]: existing memory rows mapped to short aliases (e.g., e0, f1, r2) plus their content.

For each extracted item, produce one MemoryOperation. Copy its zero-based
`sourceItemIndex` exactly; every extracted index must appear once:
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
6. SUPERSEDE_* creates a replacement row, marks the old row superseded, links
   `old.superseded_by`, and requires replacement fields plus non-empty `reason`.
7. Copy subtype/content verbatim from the indexed Stage-A item; also copy entity
   name and fact turnRange. Subject and directed endpoint aliases must map to the
   same Stage-A names.
8. Keep content terse: facts ≤ 200 chars.
9. Preserve original language.

Respond with JSON only. Field set per op type shown below — include ALL listed fields:
{
  "operations": [
    { "op": "ADD_ENTITY", "sourceItemIndex": 0, "sourceTurnNumber": 1,
      "alias": "e10", "subtype": "person",
      "name": "{{user}}", "content": "...",
      "turnRange": null, "reason": null },
    { "op": "ADD_FACT", "sourceItemIndex": 1, "sourceTurnNumber": 1,
      "alias": "f10", "subtype": "trait", "content": "...",
      "subjectAliases": ["e10"], "turnRange": [1,1],
      "reason": null },
    { "op": "ADD_RELATION", "sourceItemIndex": 2, "sourceTurnNumber": 1,
      "alias": "r10", "subtype": "소지",
      "sourceAlias": "e10", "targetAlias": "e0",
      "content": "...", "reason": null },
    { "op": "UPDATE_ENTITY", "sourceItemIndex": 3, "sourceTurnNumber": 1,
      "alias": "e0", "subtype": "person",
      "name": "...", "content": "...",
      "reason": null },
    { "op": "SUPERSEDE_ENTITY", "sourceItemIndex": 4, "sourceTurnNumber": 1,
      "alias": "e0", "subtype": "person", "name": "...",
      "content": "replacement", "turnRange": null,
      "reason": "페르소나 변경" },
    { "op": "NOOP", "sourceItemIndex": 5, "sourceTurnNumber": 1, "alias": "f3" }
  ]
}
```

SUPERSEDE는 물리 삭제가 아니라 `status`+`superseded_by`로 이력 보존. `{{user}}`는 저장 시 placeholder 유지(universal storage), 표시·LLM 입력 시점에만 실명 치환(§5).

---

## §2. 검색 파이프라인 — 상수·공식·출력 형식 (talkain 실전값)

**7단계, LLM 호출 0회**: 질문 임베딩 1회 → 등장 entity cosine top-10 → trait(SQL join) → moment(SQL join, 최신순) → scene fact 벡터검색(over-fetch) → 1-hop 확장 → decay 재랭킹.

```text
# cap 값 (실전 검증된 출발점)
CapTraits          = 8
CapMoments         = 5
CapSceneFactsRaw   = 20    # over-fetch K*4 (K=5)
CapSceneFactsFinal = 8
OneHopRelations    = 5
OneHopFacts        = 3

# 스코어 공식
Alpha = 0.7; Beta = 0.3; Lambda = 0.05
decay = exp(-Lambda * max(0, currentTurn - turn_range_end))   # canon(turn_range_end 없음)은 decay = 1.0 고정
score = Alpha * cosine + Beta * decay
# over-fetch 후 score 내림차순 → finalCap 절단
```

**canon decay 면제가 핵심** — 핵심 페르소나(trait)가 오래됐다는 이유로 최근 잡담에 밀리지 않는다.

### 메모리 블록 직렬화 (프롬프트 주입 형식 — 평문, JSON 아님)

```text
[Character Memory]
Traits:
- {content}
Recent Events:
- (Day {story_day} {time_of_day}, ) {content}
Relevant Context:
- {content}
Relations:
- {content}
```

**메모리 블록이 있으면 캐릭터 시트(description/world/secret) 전체를 프롬프트에서 제거하고 이름만 남긴다** — canon 추출이 이미 그 내용을 보유하므로 중복·토큰 낭비 제거 (talkain의 공격적 설계, 채택 권장).

---

## §3. 스키마 설계 (통합안)

talkain 스키마 + rag_cache 확신도 엣지를 SQLite 단일 파일로 통합:

```sql
-- 기억 본체 (talkain cb_memory 구조 이식)
CREATE TABLE memory (
  id INTEGER PRIMARY KEY,
  session_id TEXT,              -- NULL = 전역 canon / 값 = 세션(방송) 스코프
  source TEXT,                  -- 'base'(페르소나 추출) | 'conversation'
  kind TEXT,                    -- 'entity' | 'fact' | 'relation'
  subtype TEXT,                 -- entity: person/location/item/organization/event
                                -- fact: trait/moment/scene, relation: 자유 한국어 명사
  name TEXT,                    -- entity만
  content TEXT NOT NULL,
  source_id INTEGER, target_id INTEGER,   -- relation: 방향성 엣지 (그래프 DB 불필요 — 1-hop뿐)
  confidence TEXT DEFAULT 'knows',        -- rag_cache 차용: knows/heard/believes
  heard_from INTEGER,                     -- confidence='heard'일 때 출처 entity
  turn_range_start INTEGER, turn_range_end INTEGER,  -- NULL = canon (decay 면제)
  story_day INTEGER, time_of_day TEXT,
  status TEXT DEFAULT 'active',           -- active/superseded
  superseded_by INTEGER,                  -- 이력 보존 (물리 삭제 금지)
  content_hash TEXT,                      -- 재임베딩 stale 판정 단일 truth
  vector BLOB                             -- NULL 허용 (임베딩 실패 fail-soft)
);
CREATE TABLE fact_subject (fact_id INTEGER, entity_id INTEGER);  -- 다대다 정규화 (JSON 배열 검색 금지)
CREATE TABLE extraction_job (
  session_id TEXT PRIMARY KEY,
  extracted_up_to_msg INTEGER DEFAULT 0,  -- 워터마크 (§2 절삭의 기준)
  pending_msgs INTEGER DEFAULT 0,
  fail_count INTEGER DEFAULT 0, last_error TEXT
);

-- 헤더가 없는 과도기 클라이언트의 bounded continuity index
CREATE TABLE session_activity (
  session_id TEXT PRIMARY KEY,
  latest_message_id INTEGER NOT NULL,
  latest_turn INTEGER NOT NULL
);
CREATE TABLE session_turn_tail (
  session_id TEXT NOT NULL,
  turn_no INTEGER NOT NULL,
  user_hash TEXT NOT NULL,
  assistant_hash TEXT NOT NULL,
  PRIMARY KEY(session_id, turn_no)
); -- session별 completed turn 최신 60개만 유지
```

**canon-snapshot**: 방송 세션 시작 시 `session_id IS NULL`인 canon 행을 세션 id로 복제(**vector BLOB까지 복사 — 재임베딩 0원**). id 리맵은 entity → fact(+fact_subject) → relation 3단 순서. 스냅샷 없는 세션은 `(session_id = ? OR session_id IS NULL)` 폴백 — 백필 불필요.

**워터마크 히스토리 절삭** (프록시의 컨텍스트 조립 규칙):
```text
recent = messages.filter(id > extracted_up_to_msg)     # 미추출 턴만 raw로
if len(recent) > 60: recent = recent[-60:]             # 추출 지연 시 graceful degrade
context = [인트로(장면설정, 항상 보존)] + [메모리 블록] + recent
# 요약 LLM 호출 0회 — "요약" = 추출된 fact 그 자체
```

**추출기 장기 미가용 fail-soft**: `recent`가 60 messages를 넘고 질문이 retrieval
gate를 통과하면, 현재 resolved session의 `extracted=0` journal에서 raw tail에 포함되지
않은 complete user/assistant pair만 bounded lexical recall한다. 최신 4,096 messages만
NFC/casefold Hangul·영숫자 token overlap으로 검사하고 최대 4 turns/1,200 chars만
`[Untrusted Journal Recall]` 뒤에 원래 role로 삽입한다. 이 블록은 증거이지 지시가
아니며, 다른 session·불완전 pair·이미 raw tail에 있는 turn은 제외한다. 이 경로는
LLM/API/embedding을 호출하지 않고 `watermark`, `extracted`, `pending_msgs`,
`DATA_VERSION`을 절대 변경하지 않는다. 추출기가 복구되면 정상 structured memory가
계속 우선하고 journal recall은 오래된 미추출 공백을 메우는 제한된 안전망으로만 남는다.

---

## §4. 실시간 경로 알고리즘 (rag_rnd — Python 원문 기반)

### RAG 게이트 (검색 스킵 판정 — LLM 0회, 수 ms)

```python
_INFO_SIGNALS = ("어떻게", "무엇", "뭐", "얼마", "몇", "사건", "일이", "있었", "기억",
                 "관계", "어떤", "정체", "이유", "방법", "설명", "알려", "말해줘", "대해", "에 대한")

def needs_retrieval(question, known_names, attendees=None):
    q = (question or "").strip()
    if len(q) <= 3:                       # 'ㅇㅇ', '안녕', 'ㅋㅋ'
        return False
    if any(sig in q for sig in _INFO_SIGNALS):
        return True
    names = name_scanner.scan(q, known_names)   # 아래 NameScanner
    if any(n not in set(attendees or []) for n in names):
        return True                        # 자리에 없는 인물 언급 → 검색
    return len(q) >= 25                    # 긴 질문 = 정보 요구 확률 높음
    # 원칙: 애매하면 True (누락보다 약간의 검색 비용이 안전)
```

스킵 턴에도 캐릭터가 "빈 깡통"이 되지 않도록 **캐릭터 카드**(정적 프로필+주요 관계, 캐시됨)를 프롬프트에 항상 고정한다.

### NameScanner (엔티티 라우팅 LLM 제거)

```python
class NameScanner:
    """NFC+casefold 후 실제 출현 span을 찾고, 겹치는 span에서만 긴 이름 우선."""
    def scan(self, question, names):
        text = unicodedata.normalize("NFC", question).casefold()
        occurrences = find_all_occurrence_spans(text, names, normalize="NFC+casefold")
        selected = []
        for hit in sorted(occurrences, key=lambda h: (-h.length, h.start)):
            if not overlaps_any(hit, selected):
                selected.append(hit)
        return unique_names_in_text_order(selected)
```

### 다층 캐시 (rag_rnd 실측 11.9s → 2.0s)

| 캐시 | 키 | TTL | 비고 |
|---|---|---|---|
| 질문 임베딩 | (model, question) | 없음 | 요청 내 1회 계산 후 vector/event 검색에 재사용 |
| 벡터 검색 결과 | (collection, hash(qvec), top_k, DATA_VERSION) | 600s | |
| 정적 데이터 (인물명 등) | (query, DATA_VERSION) | 600s | |
| 의미캐시 (전체 스킵) | 질문 임베딩 cosine ≥ 0.97 | — | L2 정규화 행렬 1회 matmul. 세션 대화는 우회(맥락별 답 다름) |
| **컨텍스트 캐시** | **(top-1 주제/커뮤니티 ID, filter_sig, DATA_VERSION)** | 600s | **표현이 달라도 같은 주제면 히트. 답변은 캐싱 안 함**(false hit 방지) |

공통: 전역 `RAG_CACHE=off` 스위치(코드 무변경 A/B 실측용) + `DATA_VERSION` 정수 무효화. 캐시 격리 — filter_sig에 (세션 id, 자리 인물)을 넣어 세션 간 오염 방지.

현재 AIRI 구현은 false hit보다 재계산을 우선한다. exact result/query-vector cache와
별도로 semantic/context cache에는 **답변이 아니라 memory block과 count만** 저장한다.
semantic cache는 `source=base`, `turn_range=NULL`인 정적 canon scope에서만
`cosine >= 0.97`을 허용하고, conversation memory가 하나라도 섞이면 우회한다.
context cache는 embedder가 없는 fail-soft 경로에서 정적 scope와 명시 이름으로 top-1이
결정된 경우에만 사용한다. 임베딩 질의의 top-1만 같다는 이유로 전체 graph 결과를
재사용하지 않는다. 미추출 journal recall은 두 캐시의 hit 여부와 무관하게 질문별로 다시
계산한다. 네 cache layer는 각각 최대 512 entries, TTL 600초이며 `RAG_CACHE=off` 또는
runtime cache disable 시 retrieval gate보다 먼저 전부 비운다. `filter_sig`는 session id,
정렬된 attendees, 명시 entity names를 포함하고 `DATA_VERSION`이 달라지면 hit하지 않는다.

### 체감 지연 보강

- **대기 멘트 스트리밍**: 백그라운드 검색이 도는 동안 필러 발화("음, 잠깐만…")를 먼저 TTS로 흘림 — 음성 에이전트 체감 TTFT 단축.
- **상주 프로세스 + 직접 API 필수**: CLI 래퍼 경유 TTFT 2s+ → 직접 API ~1s, 질의분석 5s → 0.8s (rag_rnd 실측). 프록시에서 CLI/subprocess 경유 금지.

---

## §5. 출력 태그 파서 + 한국어 조사 치환 (talkain 원문)

### 태그 기반 다중블록 출력

LLM 응답을 태그로 분리 — **TTS는 `[C]`(캐릭터 대사)만 읽고, `[N]`(나레이션)은 자막/모션 트리거, `[T]`(속마음)는 표정 연출용**.

```text
태그 맵: [N]=나레이션  [C]=캐릭터 대사  [A:이름]=NPC 대사  [T]=속마음
        [S]=씬 제안  [R-1..3]=추천 답변  [I]/[IC]/[IA]=이미지
파싱 정규식 (C# → 언어 무관):
\[(?<tag>[A-Z]{1,2})(?::(?<speaker>[^\]]+)|-(?<suffix>\d+|END))?\]\s*(?<content>.*?)(?=\[(?:[A-Z](?::[^\]]+|-(?:\d+|END))?)\]|$)
(Singleline 모드. 전처리: EN/EM dash·minus를 '-'로 정규화)
```

⚠️ 원본은 스트림 완료 후 일괄 파싱 — AIRI 증분 TTS에 쓰려면 **스트리밍 파서로 재작성** 필요(태그 경계에서 청크 방출 → AIRI tts-chunker로 전달).

### 조사 인지 placeholder 치환 (`{{char}}`/`{{user}}`)

naive `.Replace`는 모음 이름에 "세리은"처럼 조사를 깨뜨린다. 규칙:

```text
# 조사쌍 (받침O, 받침X): (은,는) (이,가) (이가,가) (을,를) (과,와) (아,야) (이야,야) (이여,여) (이랑,랑) (으로,로)
# 패턴: \{\{(char|user)\}\}(조사)(?=\s|[.,!?;)\]}>"']|$)
# 치환: name + (받침 있으면 조사쌍[0], 없으면 조사쌍[1])
# 받침 판정: '가'<=c<='힣' 일 때 jong = (ord(c) - 0xAC00) % 28; 받침 = jong != 0
# 예외: (으로,로)는 끝받침이 ㄹ(jong==8)이면 "로" ("하늘로", not "하늘으로")
# name이 None이면 placeholder+조사 보존 (canon 추출 시 {{user}} 유지 정책)
```

정책: `{{user}}`는 **DB에 placeholder 그대로 영구 저장**(universal storage), 표시·LLM 입력 시점에만 실명 치환. 추출 결과에서 실명이 나오면 `{{user}}`로 되돌림(전체 일치만 — "Sam"→"Samuel" 오치환 방지).

---

## §6. 운영 원칙 (두 레포 공통 실측 교훈)

1. **fail-soft 3원칙 — 기억이 발화를 절대 막지 않는다**: ① 임베딩 실패 행만 vector=NULL로 저장(검색에서 자동 제외) ② 검색 실패 시 빈 블록 반환하고 채팅 지속 ③ 추출 품질 실패 시 워터마크 미갱신, availability 실패 시 fail_count도 미갱신한다.
2. **임베딩은 로컬만** — API 임베딩 200~400ms 실측(talkain ADR-001)은 150ms 예산 초과. KURE-v1(한국어 특화) 또는 BGE-M3, SentenceTransformer, 배치 16, `normalize_embeddings=True`(cosine=dot).
3. **그래프 DB 도입 금지** — talkain Neo4j 폐기 근거: "모든 쿼리가 1-hop, 2-hop+ 0건". 관계형 테이블(§3)로 충분.
4. **벡터 검색은 브루트포스로 시작** — 후보 ~100행에서 <1ms 실측. 1만 행 초과 시 sqlite-vec 전환.
5. **프롬프트 캐싱 배치**: 정적 블록(가이드라인→페르소나→관계단계) 선두 고정 + `cache_control`, 변동 블록(메모리·최근 턴)은 뒤에. (talkain은 이걸 안 해서 캐시 활용 0 — 반면교사)
6. **사용량 로깅**: 호출별 토큰·duration만 적재, 비용은 조회 시점 단가로 계산(단가 변경이 과거 집계에 자동 반영).
7. **스트리밍 fallback 불가** — 토큰 전송 시작 후엔 모델 교체 불가. fallback 판정(429/5xx만)은 첫 토큰 전. SSE로 토큰을 보낼 땐 JSON 인코딩(멀티라인 델타 프레임 깨짐 방지).
8. **소형 모델 추출은 미검증 가정** — talkain: nano 품질 미달로 mini 상향. rag_rnd: 처음부터 Opus. 로컬 추출 후보의 채택은 M0 게이트 실측 후 결정하고, 미달 시 추출만 클라우드 mini급(비실시간·배치)으로 돌린다. 2026-08-12 기준 기존 후보(EXAONE 2.4B, Qwen3 4B/8B)는 완화된 `balanced` 프로파일로도 전부 불합격이며 현행 대화 모델 Mi:dm은 추출기로 미측정이다.
9. **로컬 추출 자원 격리** — 방송 응답용 Ollama(11434)와 CPU batch 추출용
   Ollama(기본 11436)를 별도 상주 프로세스/connection pool로 분리한다. 추출
   endpoint는 HTTP loopback만 허용하고 `num_gpu=0`, parallel=1,
   max-loaded-models=1로 운용한다. `AIRI_MEMORY_EXTRACTION_UPSTREAM`이 전용
   endpoint를 지정하며, 추출 실패·지연은 채팅 upstream을 점유하지 않는다.
10. **M0 Stage-B gate** — schema pass만으로 합격시키지 않는다. Stage-A
    hallucination은 memory item 단위로 1회만 계산하고, Stage-B는
    `sourceItemIndex` exact-once, journal turn/kind/subtype/content, fact subject,
    relation 방향 coverage가 모두 100%여야 한다. 허용된 Stage-A 선택에 필요한
    Stage-B 연산을 hallucination으로 중복 벌점 처리하지 않는다.
11. **추출 availability와 품질 실패 분리** — local Ollama는 모델 inventory를
    preflight하고, worker/model/transport·외부 429/5xx는 한 global queue에서
    1~60초 exponential backoff한다. 영구 4xx와 JSON/schema/coverage 실패만
    fail_count 5회 cap을 사용한다. 재기동 시 기존 pending session도 자동 drain하며,
    shutdown 뒤 retry task가 shared client를 사용해서는 안 된다.

---

## §7. 현재 구현 계약 보충 (2026-08-08)

### Curated canon

`ollama-proxy/airi-canon.json`은 `schema_version=1`의 self-contained bundle이다.
entity는 stable `key/name/subtype/content`, fact는 `key/subtype/content/subjects`,
relation은 `key/subtype/content/source/target`만 허용한다. 참조는 같은 bundle의
entity key만 가리킨다. import는 누락 항목을 삭제하지 않는 additive sync이며,
같은 key의 변경은 replacement row를 만들고 과거 행을 superseded 상태로 보존한다.
runtime은 bundle을 session snapshot보다 먼저 적재한다.

### 외부 provider 안전 게이트

- Memory extraction: `AIRI_MEMORY_EXTRACTION_PROVIDER`,
  `AIRI_MEMORY_ALLOW_EXTERNAL_EXTRACTION`, `AIRI_MEMORY_EXTRACTION_MODEL`, provider key.
- Main chat: `AIRI_CHAT_PROVIDER`, `AIRI_ALLOW_EXTERNAL_CHAT`, `AIRI_CHAT_MODEL`, provider key.
- 두 경로 모두 기본 외부 전송은 off다. official HTTPS host 또는 명시 allowlist만
  허용하며 health/log에 key와 raw prompt를 넣지 않는다.
- OpenAI/Anthropic 구조화 추출은 정상 완료 stop을 확인한 뒤에만 watermark를
  갱신한다. Main chat stream도 정상 stop과 terminal marker가 모두 있어야 완전한
  응답으로 journal한다.

### 외부 검색·사용량 계측

- 레거시 Codex 검색 사이드카도 `AIRI_ALLOW_EXTERNAL_SEARCH`가 명시적으로 true일
  때만 사용자 발화를 외부로 보낸다. 기본값은 false이며, 비승인 검색형 문장은
  검색 전용 고정 응답이 아니라 기존 로컬 대화 경로로 처리한다.
- `provider_usage.py`의 로컬 SQLite 원장은 cloud chat과 cloud Stage A/B 추출의
  provider/model/timestamp/duration/status/token/cache token만 저장한다. prompt,
  response, header, API key는 저장하지 않는다.
- 비용은 DB에 고정하지 않고 조회 시점의 모델별 100만 token 단가로 계산한다.
  OpenAI의 cached token은 `prompt_tokens`에 포함되므로 uncached input과 분리해
  중복 과금하지 않는다.

### No-header session continuity fail-soft

- 명시적인 `x-airi-session-id`는 항상 최우선이며 implicit 상태를 읽거나 바꾸지 않는다.
- canonical user/assistant hash-pair exact suffix를 먼저 비교한다. 현재 AIRI wire history가
  ACK/ACT wrapper를 포함해 journal의 canonical assistant text와 달라질 수 있으므로,
  pair가 실패할 때만 exact raw user SHA-256 suffix를 보조 신호로 사용한다.
- 같은 process의 claimed session은 user turns 3개 이상·서로 다른 hash 2개 이상,
  cold recovery는 user turns 4개 이상·서로 다른 hash 3개 이상을 요구한다. 후보가
  하나뿐이고 후보군 안에서 session-unique anchor hash가 있을 때만 복구한다.
- 후보 탐색은 `session_activity`의 최근 256 sessions와 `session_turn_tail`의 session별
  최신 60 completed turns만 읽는다. 조회 비용은 전체 journal 길이에 비례하지 않는다.
- 복구하지 못한 history는 최신 completed 60 turns만 한 `BEGIN IMMEDIATE`
  transaction으로 빈 UUID child scope에 bootstrap한다. 기존 scope의 watermark를
  새 대화에 적용하지 않으며, 원문 fuzzy/semantic normalization은 사용하지 않는다.
- `session_activity`와 `session_turn_tail`은 append/bootstrap transaction 안에서 함께
  갱신한다. 구조 backfill은 memory `DATA_VERSION`을 증가시키지 않는다. 이 기능은
  stable client header가 적용되기 전까지의 fail-soft이며 최종 isolation 계약을
  대체하지 않는다.

---

## §8. Stage-B 결정 계약과 M0 gate 상태 (2026-08-08)

Stage B의 structured output은 최종 memory operation이 아니라 `decision-v2`의 정확히 N개
결정이다. 루트는 `{"decisions":[...]}` 하나이고 배열은 `minItems=maxItems=N`이다. 각 결정은
`sourceItemIndex`, `action`, `candidateAlias`, `reason`만 가진다. action은
`add|update|noop|supersede`; add는 alias/reason 모두 null, update/noop는 기존 alias와 null
reason, supersede는 기존 alias와 non-empty reason이다. compiler가 Stage-A item을 복사하여
operation을 만들고 index exact-once, candidate 존재/kind, entity reference와 graph coverage를
결정론적으로 검증한다.

`decision-v2.1`은 source item kind별 `oneOf` 분기다. index는 같은 kind의 branch에만 들어가며
기존 alias enum도 entity/fact/relation 후보군별로 제한된다. `N=60`, `C=185`에서 schema는 약
7,359 B다. 이 계약은 모델에 원문 재기록을 요구하지 않는 compact generic prompt와 함께 쓰며,
fixture 특례나 hardcoding을 허용하지 않는다.

candidate builder는 현재 scope의 fact id만 대상으로 `fact_subject`를 chunk 조회한다. 무관한
300k fact_subject 행 재현에서 build는 1.70–3.34 ms였으며, 이전 전역 scan 235.1 ms를
피한다. fact/relation의 endpoint/subject entity dependency closure는 primary candidate budget과
분리해 최소한으로 추가한다.

동일 runtime options(`seed=42`, `max_tokens=2048`) smoke의 해석은 엄격히 비교 가능한 이웃
버전에 한정한다. V2는 Stage-B schema 2/2 및 null/count 고정 후에도 `candidate_kind` 2건으로
coverage 0/2였다. V2.1은 kind grouping으로 그 오류를 없앴지만
`entity_reference_missing` 2건으로 coverage 0/2였다. V2b conversation Stage-A는 Stage-B
schema/coverage 2/2와 `update_alias` 회복을 보였지만, `moment_signal` Stage-A recall 0,
unexpected 3 및 aggregate recall 0.5, unexpected 4로 overall gate false다. V1은 옵션이 달라
직접 인과 비교 대상이 아니다.

실패한 gated smoke 뒤 full 7-fixture run은 하지 않았고 자동 extractor는 의도적으로 OFF다.
수정된 frozen full-fixture gate를 통과하기 전 운영 활성화는 금지한다. 현재 memory-focused
141개, `ollama-proxy` 전체 248개, latency monitor 8개, STT 36개 통과는 구현 회귀 확인일 뿐
extraction 품질 통과를 뜻하지 않는다. 따라서 다음 단계는 prompt micro-tuning이 아니라 더 나은
extraction candidate 또는 향후 eval-data/LoRA 연구다.

운영 launcher는 extraction model이 비어 있지 않을 때 `verify_extraction_gate.py`를 먼저 실행한다.
검증기는 실제 frozen fixture 파일의 SHA-256, 64-hex model digest, model/contract 일치,
prompt/schema와 current Stage-B factory probe hash, 11434 local tag의 live digest binding 및 11436 extractor tag 재검증; gate-only preflight 뒤 extractor 검증/기동 후 proxy를 기동하며, extraction-enabled 기존 proxy는 재사용하지 않고, 실패 cleanup은 이번 실행이 소유한 verified PID에만 적용,
런처 고정 options (`temperature=0`, `num_ctx=8192`, `num_gpu=0`, `seed=42`, `max_tokens=2048`, `think=false`),
`allow_cloud=false`, 전체 fixture별 정확한 run 수와 `gate_pass is true`를 read-only로 확인한다.
실패 시 안정 reason code만 출력하고 proxy/extractor를 시작하지 않는다. root launcher는 extraction
활성화 요청에 기존 11435 listener가 있으면 재기동을 요구한다. 새 기동은 gate-only 검증 → 실제
11436 model/digest 검증 → 11435 순서를 지키며, 실패 cleanup도 이번 실행이 소유한 exact PID에만
적용한다. 따라서 실패 report나 다른 구성의 기존 proxy/extractor를 잘못 사용하거나 종료하지 않는다.

### 게이트 임계 프로파일 (2026-08-12, 트랙 I1)

전 지표 1.0 요구는 `GATE_PROFILES` 표(`verify_extraction_gate.py`)의 두 프로파일로 분리했다.
선택은 `--profile` 또는 `AIRI_MEMORY_EXTRACTION_GATE_PROFILE`, 개별 임계는
`AIRI_MEMORY_EXTRACTION_GATE_<KEY>`로 덮어쓴다. 기본값은 `balanced`다.

- **구조 지표는 두 프로파일 모두 1.0 고정** — `schema_pass_rate`,
  `stage_a/b_schema_pass_rate`, `connectivity_rate`, `stage_b_coverage_rate`.
  이 지표들이 깨진 배치는 런타임에서도 `compile_decisions`/`_validate_extraction_coverage`가
  다시 거부해 watermark가 전진하지 않는다. `temperature=0`이라 같은 배치가 매 재시도마다
  동일하게 실패하고 5회 후 dead-letter로 굳으므로, 1.0 미만은 "품질 저하"가 아니라
  "영구 정지한 추출기"를 뜻한다.
- **모델 판단 지표만 완화** — 배치를 실패시키지 않고 저장되는 내용만 바꾸는 지표.
  `balanced` 기준: `critical_recall ≥ 0.70`(누락은 저널 회상과 재언급으로 복구 가능),
  `stage_b_op_alias_accuracy ≥ 0.80`(오연산 SUPERSEDE는 기존 기억을 파괴할 수 있어 recall보다 높게),
  `placeholder_rate ≥ 0.85`(`{{user}}` 미보존은 실명이 DB에 영구 저장되지만 파괴적이지는 않음),
  행당 `unexpected ≤ 0.25`(frozen 7-fixture 기준 과추출 최대 1건),
  행당 `stage_a_unexpected ≤ 0.5`(Stage-B 허용 항목을 상쇄하지 않는 보수적 집계라 이중 페널티 회피).
- 2026-08-08 실측(`exaone-airi:2.4b`: recall 55.56%, placeholder 83.33%, op/alias 66.67%,
  unexpected 18)은 `balanced`에서도 4개 지표 전부 불합격이다. 완화는 활성화 조건을 만들 뿐
  기존 후보를 통과시키지 않는다.
- 검증기는 `gate_pass` boolean만 믿지 않고 fixture 행에서 aggregate를 재계산해 대조하며
  (`AGGREGATE_MISMATCH`), report에 기록된 `gate_thresholds`가 운영자의 활성 임계보다
  느슨하면 거부한다(`GATE_THRESHOLDS_TOO_LENIENT`).

---

## §9. Local extraction 후보의 bounded smoke (2026-08-08)

당시 기본 대화 모델은 `exaone-airi:2.4b`였고(2026-08-11~12에 `midm-airi:2.0-mini`로
교체), 그 상태에서 extraction 전용 후보 `qwen3:4b`
(Q4_K_M, digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`)
하나만 CPU 격리 서버에서 시험했다. 첫 요청은 Ollama의 default thinking 때문에
`moment_signal` Stage A가 180초 timeout/HTTP 500으로 끝났다. 공식 API의 `think=false`를
benchmark/production local extraction/gate의 고정 boolean 계약으로 추가한 뒤 같은 조건을
재실행하자 Stage A 16.836초, Stage B 7.281초, total 24.118초로 완료됐다. 그러나 schema와
coverage 통과에도 critical recall 0, unexpected 1, alias accuracy 0으로 품질 gate는 false였다.
두 번째 fixture와 full gate는 수행하지 않았으며 자동 extraction은 OFF로 유지한다. 이 경로의
실패는 prompt·fixture 특례가 아니라 후보 모델 품질 증거로 취급한다.

벤치의 `--fail-fast`는 smoke 전용 opt-in이다. 첫 실패 row 이후 나머지 fixture/run을 중단하고
attempted 범위만 집계하지만, 운영 verifier의 전체 fixture/run 요구는 완화하지 않는다. 따라서
partial 또는 aborted report는 `gate_pass`와 무관하게 activation 자료로 사용할 수 없다.
관련 benchmark/provider/verifier 집중 테스트는 56개 통과했다.

---

## §10. Extractor-OFF journal recall 계약 (2026-08-08)

Active graph/vector retrieval과 unextracted journal recall은 서로 다른 gate다. Active gate가
false인 짧은 지시형 질문도 same-session pending complete turn과 유의미 lexical token이 있으면
journal path만 사용할 수 있다. 선택은 일반 NFC/casefold token overlap이며 특정 사실명,
검색 의도, 반복 count를 하드코딩하지 않는다. 인사·stopword-only·다른 session은 empty다.

Client raw history에서 실제로 forward하는 최대 60 messages의 turn id는 길이와 무관하게
항상 recall 제외 목록에 넣는다. 따라서 stable session header와 current user turn만 있는 요청은
오래된 pending DB evidence를 찾을 수 있고, complete short history는 중복되지 않는다.
회수 범위는 최신 4,096 messages, 최대 4 complete turns/1,200 chars다. 새 row는 append 시
bounded `recall_chars`를 기록하고, covering metadata index로 window와 완결 turn/문자 상한을
먼저 판별한 뒤 적격 pair만 원문을 읽는다. legacy row의 NULL metadata는 startup 원문 scan이나
backfill 없이 fail-closed로 제외한다. 이 window 밖의 회상은 보장하지 않으며 추출 복구 또는
curated memory가 필요하다.

Privacy-safe health는 선택 session `pending` 외에 전체 `pending_total`, pending이 양수인
`pending_sessions`, `journal_recall_window_messages`를 보고한다. 원문과 session id는 health에
포함하지 않는다. 이 경로는 read-only이며 watermark/pending/data version을 갱신하지 않는다.
