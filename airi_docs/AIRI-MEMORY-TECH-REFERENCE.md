# AIRI 기억 계층 기술 레퍼런스 (트랙 M 구현 자산)

- 작성일: 2026-08-06
- 목적: 계획서 v2.1 트랙 M(기억 계층 + 클라우드 LLM)을 **클론 레포 없는 환경에서** 구현할 수 있도록, 원본 코드에서 추출한 프롬프트 원문·공식·알고리즘을 자기완결적으로 수록
- 출처: `ovencode-avatarplay/talkain-api`(C#/.NET 캐릭터 챗봇 프로덕션), `ovencode-avatarplay/rag_rnd`(Python RAG 연구) — 실측 감사는 `AIRI-RAG-REPOS-AUDIT-2026-08-06.md`
- 사용법: 아래 자산은 검증된 원문/공식이므로 **재발명하지 말고 이식**한다. 언어는 자유(프록시는 Python/Node 권장), C# 고유 부분은 로직만 옮긴다.

---

## §1. 기억 추출 프롬프트 (talkain Stage A/B — 원문 그대로)

2단 추출: Stage A가 대화/캐릭터 시트를 원자적 항목으로 분해하고, Stage B가 기존 기억 후보(top-5)와 대조해 적용 연산을 결정한다. 입력은 `<character>`(메타)/`<turns>`(본문) 블록, Stage B는 `<extracted>`/`<candidates>` 블록으로 감싼 user 메시지 1개.

주의사항 (원본 운영 경험):
- 원본은 gpt-5.4-mini 사용 — **"분해는 결정론적이라 nano급 충분" 가정은 품질 미달로 실패**했음. 로컬 EXAONE 적용 시 M0 게이트 실측 필수.
- 원본은 structured output 미사용(코드펜스 스트립+JSON 파싱, fail-soft). 소형 모델은 준수력이 낮으므로 **JSON schema/GBNF 강제 권장**.
- 캐릭터 base(페르소나 시트) 추출은 Stage B 생략 fast-path (후보가 없으므로).
- 트리거: 응답 완료 후 fire-and-forget, 미추출 메시지 ≥3 + 세션 종료 시 강제 flush. 실패 5회 시 skip(dead-letter), 세션 재시작 시 리셋.

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
```

**canon-snapshot**: 방송 세션 시작 시 `session_id IS NULL`인 canon 행을 세션 id로 복제(**vector BLOB까지 복사 — 재임베딩 0원**). id 리맵은 entity → fact(+fact_subject) → relation 3단 순서. 스냅샷 없는 세션은 `(session_id = ? OR session_id IS NULL)` 폴백 — 백필 불필요.

**워터마크 히스토리 절삭** (프록시의 컨텍스트 조립 규칙):
```text
recent = messages.filter(id > extracted_up_to_msg)     # 미추출 턴만 raw로
if len(recent) > 60: recent = recent[-60:]             # 추출 지연 시 graceful degrade
context = [인트로(장면설정, 항상 보존)] + [메모리 블록] + recent
# 요약 LLM 호출 0회 — "요약" = 추출된 fact 그 자체
```

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
    """한국어는 띄어쓰기 경계가 없어 set 룩업 부족 → 길이 내림차순 부분문자열 스캔.
    (인물 수십 명 규모면 충분. 폭증 시 Aho-Corasick 교체)"""
    def scan(self, question, names):       # names: 길이 내림차순 정렬된 인물명
        hits = [n for n in names if n and n in question]
        # 긴 이름에 포함된 짧은 이름 제거
        return [n for n in hits if not any(n != m and n in m for m in hits)]
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

1. **fail-soft 3원칙 — 기억이 발화를 절대 막지 않는다**: ① 임베딩 실패 행만 vector=NULL로 저장(검색에서 자동 제외) ② 검색 실패 시 빈 블록 반환하고 채팅 지속 ③ 추출 파싱 실패 시 워터마크 미갱신 → 다음 트리거에 자연 재시도(별도 재시도 큐 불필요).
2. **임베딩은 로컬만** — API 임베딩 200~400ms 실측(talkain ADR-001)은 150ms 예산 초과. KURE-v1(한국어 특화) 또는 BGE-M3, SentenceTransformer, 배치 16, `normalize_embeddings=True`(cosine=dot).
3. **그래프 DB 도입 금지** — talkain Neo4j 폐기 근거: "모든 쿼리가 1-hop, 2-hop+ 0건". 관계형 테이블(§3)로 충분.
4. **벡터 검색은 브루트포스로 시작** — 후보 ~100행에서 <1ms 실측. 1만 행 초과 시 sqlite-vec 전환.
5. **프롬프트 캐싱 배치**: 정적 블록(가이드라인→페르소나→관계단계) 선두 고정 + `cache_control`, 변동 블록(메모리·최근 턴)은 뒤에. (talkain은 이걸 안 해서 캐시 활용 0 — 반면교사)
6. **사용량 로깅**: 호출별 토큰·duration만 적재, 비용은 조회 시점 단가로 계산(단가 변경이 과거 집계에 자동 반영).
7. **스트리밍 fallback 불가** — 토큰 전송 시작 후엔 모델 교체 불가. fallback 판정(429/5xx만)은 첫 토큰 전. SSE로 토큰을 보낼 땐 JSON 인코딩(멀티라인 델타 프레임 깨짐 방지).
8. **소형 모델 추출은 미검증 가정** — talkain: nano 품질 미달로 mini 상향. rag_rnd: 처음부터 Opus. EXAONE 추출은 M0 게이트 실측 후 결정, 미달 시 추출만 클라우드 mini급(비실시간·배치).
