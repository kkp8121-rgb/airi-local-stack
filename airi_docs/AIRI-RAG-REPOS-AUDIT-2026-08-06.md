# RAG 레포 3종 코드 실측 감사 — AIRI 기억 계층 설계 입력

- 실측일: 2026-08-06
- 목적: 사용자 자체 레포 3종에서 AIRI 기억 계층(후보 D: 클라우드 LLM=생각, 로컬 vector+graph RAG=기억, 127.0.0.1 메모리 프록시)에 재사용할 기술 식별
- 대상: `external/talkain-api`(C#/.NET 캐릭터 챗봇 프로덕션), `external/rag_rnd`(Python 하이브리드 RAG 연구), `external/rag_cache`(Python+Neo4j 추리 게임)
- 관련 문서: `AIRI-CODE-AUDIT-2026-08-06.md`(AIRI 본체 실측), `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md`(계획 v2)

## 요약 판정

세 레포를 합치면 **메모리 프록시의 핵심 설계 문제 대부분에 실전 검증된 답이 이미 있다.** talkain-api는 "무엇을 만들 것인가"(추출·절삭·격리·검색 파이프라인)를, rag_rnd는 "어떻게 150ms 안에 돌릴 것인가"(게이트·캐시·로컬 임베딩·체감 지연)를, rag_cache는 "캐릭터 지식을 어떻게 모델링할 것인가"(확신도 엣지·정보 방화벽)를 제공한다. 동시에 talkain의 실패 회고(ADR-001)가 우리 계획의 위험 가정 2개를 정확히 짚는다.

---

## 1. talkain-api — 기억 시스템의 본체 설계 (가장 높은 재사용 가치)

⚠️ **ADR 문서와 코드가 크게 어긋나 있음 — 코드가 truth.** (Qdrant·로컬 ONNX 임베딩·Neo4j·idle sweeper·outbox는 전부 폐기됨. 현행: MySQL `vector_bin` BLOB + C# 인메모리 cosine + OpenAI `text-embedding-3-small`)

### 채택할 핵심 설계 5개

1. **워터마크 dual-memory 히스토리 절삭** (`CB_ChatService.cs:381-408`, `CB_MemoryService.cs:73-109`)
   - `extracted_up_to_msg` 워터마크 이하의 raw 턴은 컨텍스트에서 제거하고 구조화 메모리 블록으로 대체. 인트로(장면 설정)는 항상 보존. 추출이 밀리면 last-60 cap으로 graceful degrade.
   - **요약 LLM 호출 0회** — 요약 = 추출된 fact 그 자체. AIRI의 "매 턴 전체 히스토리 무절삭 전송" 문제(본체 감사 §1-1)를 정확히 해결하는 절삭 정책.
2. **canon-snapshot 세션 격리** (`CB_MemoryService.cs:148-244`, `CB_InlineMemoryVectorSearch.cs:47-60`)
   - 세션(방) 시작 시 페르소나 canon을 복제(벡터까지 복사 → 재임베딩 0원). 세션 학습이 원본 페르소나를 오염시키지 않음. 스냅샷 부재 시 canon 폴백(백필 불필요). entity→fact→relation 3단 id 리맵이 구현 핵심.
3. **Stage A/B 2단 추출 + 9 op alias 시스템** (`CB_OpenAiService.cs:150-256`, `:302-350`)
   - Stage A: 대화→원자적 사실 분해(한국어 예시·트리플 강제·안티패턴 포함 106줄 프롬프트). Stage B: 기존 후보 top-5와 대조해 ADD/UPDATE/SUPERSEDE/NOOP 결정. LLM은 DB id가 아닌 alias(e0/f1/r2)로 조작. SUPERSEDE는 이력 보존(`superseded_by`).
   - **프롬프트 원문이 최대 자산 — 재발명 금지, 그대로 이식.**
4. **LLM 0회 검색 파이프라인 + canon decay 예외** (`CB_MemoryRetrieveService.cs:14-23, 45-133, 197-212`)
   - 임베딩 1회 → entity cosine top-10 → trait(cap 8)/moment(cap 5) SQL join → scene 벡터(over-fetch K*4) → 1-hop 확장(5·3) → `score = 0.7·cosine + 0.3·exp(-0.05·Δturn)` 재랭킹 top 8.
   - **canon은 decay=1.0 고정** — 핵심 페르소나가 오래됐다고 밀려나지 않음. 캡 값 전부 실전 검증된 출발점.
5. **fail-soft 3종** — 임베딩 실패 행만 NULL(검색서 자동 제외), 검색 실패 시 빈 블록 반환(발화 지속), 파싱 실패 시 워터마크 미갱신→자연 재시도. **기억 계층이 발화를 절대 막지 않는 원칙.**

### 그대로 포팅할 언어 무관 자산

- **한국어 조사 인지 치환** (`CB_MemoryTokenNormalizer.cs`, `ReplacePlaceholdersJosaAware`) — `{{char}}`/`{{user}}` 치환 시 받침 판정으로 조사 교정. 한국어 버튜버 필수.
- **태그 기반 다중블록 출력** (`[N]`나레이션/`[C]`대사/`[A:name]`NPC/`[R]`추천답, `TextUtil.cs:43-103`) — **TTS는 `[C]`만 읽고 `[N]`은 자막·모션 트리거로**. 단 현행은 스트림 완료 후 일괄 파싱이라 증분 TTS용 스트리밍 파서 재작성 필요.
- SSE 토큰 JSON 인코딩(멀티라인 델타 프레임 깨짐 방지, `CB_LlmService.cs:168-170`), flow 기반 모델 레지스트리+fallback 체인, 토큰만 적재하고 비용은 read-time 계산하는 사용량 설계.
- 메모리 블록 형식: 평문 마크다운형(`Traits:/Recent Events:/Relevant Context:/Relations:`) — JSON 아님.
- 메모리 보유 시 캐릭터 시트 전체를 프롬프트에서 제거(이름만 남김)하는 토큰 절감 설계(`CB_ChatService.cs:641-650`).

### 반면교사 (이식 금지 / 위험 가정)

| 항목 | 근거 | AIRI 결론 |
|---|---|---|
| OpenAI 임베딩 API 200-400ms | ADR-001:262 실측 (로컬 ONNX는 20-80ms) | **150ms 예산 초과 — 로컬 임베딩 필수** (후보 D는 GPU 여유 있음) |
| 취소 미배선 (메인 채팅 CancellationToken 미전달) | `CB_ChatService.cs:694` | barge-in 선례 없음 — 직접 설계 |
| structured output 미사용(프롬프트 규약+fail-soft 파싱) | `CB_OpenAiService.cs:283-291` | 로컬 소형 LLM은 준수력 낮음 — JSON schema/GBNF 강제 필수 |
| "분해는 싼 모델로 충분" 가정 실패 (nano→mini 상향) | `CB_OpenAiService.cs:138`, ADR-001:66 | **로컬 EXAONE 추출 품질 게이트 실측 선행** — 미달 시 클라우드 mini급 폴백 (추출은 비실시간이라 배치·저가로 감당 가능) |
| "로컬 모델 비용 0" 가정 실패 (콜드스타트·운영) | ADR-001:219-280 | 우리는 로컬 상주라 콜드스타트는 해소되나 운영 비용 인식 유지 |
| 브루트포스 벡터 검색 | ADR-005:150 (~100행 <1ms) | **초기엔 이 방식이 옳음** (1만 행 미만) — 이후 sqlite-vec/LanceDB 전환 |
| Neo4j 폐기 근거 | ADR-001:22 "모든 Cypher가 1-hop, 2-hop+ 쿼리 0건" | **1-hop이면 관계형 테이블로 충분** — 아래 §4 결정에 반영 |

### 캐릭터성 메커니즘 (부가 차용)

호감도 수치(`affection_value`) + 관계 단계 프롬프트(`cb_character_affection_stage` → "tone/distance/openness를 이 단계에 맞춰라"), 속마음(inner thought) 별도 flow, 스토리 시간선(`story_day`/`time_of_day`/`location`) + moment fact 타임스탬프. 구조화된 감정 태깅은 없음(프롬프트 텍스트뿐).

---

## 2. rag_rnd — 저지연 실행 기법 (150ms 예산의 실측 근거)

인스타그램 아카이브 기반 AI 페르소나 채팅으로 진화한 연구 레포 — 후보 D의 프로토타입에 가장 가깝다. 유일한 박제 실측치: 캐시 off 11.9s → on 2.0s (5.85x, CLAUDE.md:204).

### 실시간 경로에 바로 차용 (코드로 확인됨)

1. **RAG 게이트** (`hybrid_rag.py:420-447`) — 규칙 기반(LLM 0회)으로 잡담·인사엔 검색 자체를 스킵. "가장 큰 절감은 검색을 안 하는 것."
2. **NameScanner** (`cache.py:192-247`) — 정적 인물명 집합 부분문자열 스캔으로 질의분석 LLM 호출 제거.
3. **다층 캐시 스택** (`cache.py` 7종, 전역 `RAG_CACHE=off` 스위치 + `DATA_VERSION` 무효화) — 특히 **top-1 커뮤니티 ID를 키로 쓰는 컨텍스트 캐시**(`hybrid_rag.py:574-594`): 표현이 달라도 같은 주제면 히트. SemanticCache(cosine≥0.97 전체 스킵)도 존재.
4. **캐릭터 카드 프롬프트 고정** (`hybrid_rag.py:373-408`) — 검색 스킵 턴에도 정적 프로필+관계를 고정 주입해 "빈 깡통" 방지. (talkain의 메모리 블록과 결합 가능)
5. **대기 멘트 스트리밍** (`hybrid_rag.py:1585-1607`) — 백그라운드 검색 동안 필러 발화를 먼저 흘려 체감 TTFT 단축. **음성 버튜버 UX에 가장 직결되는 기법.**
6. **세션 오버레이 그래프** (`graph_store.py:150-196, 439-456`, `session_graph.py`) — 원본 그래프 불변 + 세션 이벤트만 append/회수(clear_session). talkain의 canon-snapshot과 같은 문제의 다른 해법 — 프록시 설계 시 둘 중 택일.
7. **로컬 임베딩 실증** (`embedder.py`, `config.py:93-129`) — BGE-M3 / Qwen3-0.6B / **KURE-v1(한국어 검색 특화)** SentenceTransformer 로컬 실행, 배치 16, L2 정규화. 임베딩 모델 후보와 래퍼 코드 그대로 재사용 가능.
8. **CLI 경유 금지 실측** (`hybrid_rag.py:126-141`, `llm_extract.py:375-419`) — CLI 경유 TTFT 2s+ → 직접 API ~1s, 질의분석 5s→0.8s. **메모리 프록시는 상주 프로세스 + 직접 API 호출로.**

### 백그라운드 추출 경로 참고 (배치 전용)

- GraphRAG 자체 구현: Neo4j + LLM 엔티티·관계 추출(`llm_extract.py:22-60, 115-130` — 화자 추론 등 정교한 프롬프트) + **Leiden 계층 커뮤니티**(graspologic, `community.py:115-138`) + bottom-up LLM 롤업 요약. Microsoft graphrag 패키지 미사용.
- 추출 LLM은 전부 Claude Opus — **로컬 소형 LLM 추출은 이 레포에서도 미검증** (talkain 반면교사와 동일 결론).
- CrossEncoder 리랭크(bge-reranker-v2-m3)는 최적화해도 0.8~3.3s — 실시간 경로 부적합, 백그라운드 정리 용도만.

---

## 3. rag_cache — 캐릭터 지식 모델링 (제한적 차용)

정정: 이름과 달리 **semantic cache 없음**(임베딩/벡터 코드 0건). 실체는 한국어 추리 게임의 pre-bake 아키텍처 + Neo4j 지식 그래프.

차용 요소:

1. **확신도-출처 태깅 지식 엣지**: `KNOWS`(직접 목격, conf 1.0) / `HEARD_ABOUT`(소문, conf 낮음+출처 기록) / `BELIEVES`(오신념) + `CONTRADICTS` — 버튜버가 "직접 아는 것/전해들은 것/잘못 믿는 것"을 구분해 발화 일관성 유지.
2. **인식론적 방화벽** (`app/retrieval/character_view.py:1-19`) — 캐릭터용 지식 조회에서 `is_true`를 쿼리 레벨에서 아예 SELECT하지 않음. 민감 정보 누출 차단을 프롬프트가 아닌 **쿼리로 강제**하는 원칙.
3. **pre-bake 패턴** (`app/engine/game.py` prebake 계열) — 유휴 시간에 예측 가능한 콘텐츠를 백그라운드 선생성. 감정 리액션 음성 등 예측 가능 반응에 응용 여지.

한계: 그래프가 매 게임 `DETACH DELETE`되는 휘발성(장기 기억 아님), 캐시 적중률 계측 없음.

---

## 4. 종합 — 메모리 프록시 설계 결정 (실측 근거 기반)

| 결정 항목 | 채택안 | 근거 |
|---|---|---|
| 임베딩 | **로컬** KURE-v1 또는 BGE-M3 (GPU, 20-80ms급) | talkain ADR-001:262 (API 200-400ms는 예산 초과) + rag_rnd embedder.py 실증. 후보 D는 LLM이 GPU에서 빠져 여유 있음 |
| 벡터 저장 | 초기 **SQLite + 브루트포스** → 1만 행 초과 시 sqlite-vec/LanceDB | talkain ADR-005:150 (~100행 <1ms 실측) |
| 그래프 | **Neo4j 도입하지 않음** — 관계형 테이블(source/target id + fact_subject 정규화)로 1-hop | talkain ADR-001:22 ("2-hop+ 쿼리 0건" 폐기 근거). rag_cache의 확신도 엣지 타입만 스키마에 차용 |
| 히스토리 절삭 | 워터마크 dual-memory (요약 LLM 0회) | talkain 1위 설계. AIRI 무한 히스토리 문제 직접 해결 |
| 페르소나 격리 | canon-snapshot (방송 세션 단위) | talkain 2위 설계 (rag_rnd 세션 오버레이와 택일) |
| 추출 | Stage A/B 프롬프트 이식 + **로컬 EXAONE 품질 게이트 실측** → 미달 시 클라우드 mini급 (JSON schema 강제) | talkain 프롬프트 자산 + 두 레포 공통 반면교사("싼 모델 추출"은 미검증) |
| 검색 경로 | LLM 0회: RAG 게이트 → NameScanner → 임베딩 1회 → vector top-k + 1-hop → decay 재랭킹(canon 예외) | talkain 4위 + rag_rnd 1·2번. 150ms 예산 실현 근거 확보 |
| 캐시 | 다층 캐시 + 주제 키 컨텍스트 캐시 + 전역 off 스위치 | rag_rnd cache.py (11.9s→2.0s 실측) |
| 안정성 | fail-soft 3종 (기억이 발화를 막지 않음) | talkain 5위 |
| 프록시 형태 | **상주 프로세스 + 직접 API 호출** (CLI 경유 금지) | rag_rnd 실측 (TTFT 2s+→1s) |
| 출력 파싱 | `[N]`/`[C]` 태그 → TTS는 `[C]`만 (스트리밍 파서 신규 작성) | talkain TextUtil + AIRI tts-chunker 연계 |
| 체감 지연 | 대기 멘트 스트리밍 + (선택) pre-bake 리액션 | rag_rnd + rag_cache |
| 한국어 처리 | 조사 인지 치환(JosaAware) 포팅 | talkain — 한국어 필수 |
| 프롬프트 캐싱 | talkain 미활용 — 우리는 정적 블록(가이드라인·페르소나) 선두 배치 + Anthropic cache_control 적용 | talkain 조립 순서 반면교사 + claude-api 캐싱 원칙 |

## 5. 남은 확인 필요 항목

1. 로컬 EXAONE(2.4b)의 Stage A/B 추출 품질 — 두 레포 모두 클라우드 모델만 검증. 품질 게이트 벤치 필요
2. KURE-v1 vs BGE-M3 한국어 대화 기억 검색 정확도·지연 비교 (RTX 3060 Ti)
3. 태그 스트리밍 파서와 AIRI tts-chunker의 결합 지점 설계 (`[C]` 추출 후 chunker 통과)
4. talkain Stage A/B 프롬프트의 버튜버 도메인 적응 (게임 방송 맥락 사실 유형 추가)
