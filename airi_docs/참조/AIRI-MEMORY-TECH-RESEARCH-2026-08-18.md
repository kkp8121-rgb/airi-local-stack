# AIRI 장기기억 기술 리서치 종합 — 2026-08-18

- 작성일: 2026-08-18 (클로드 PC)
- 목적: 로컬 2~4B 추출 모델이 M0 게이트에서 전부 FAIL한 상황에서,
  프레임워크 교체가 답인지 검증 — 3트랙(학술 논문 서베이 / OSS
  프레임워크 20여종 실사 / 자체 레포 3종 재감사) 병렬 실사
- 근거 등급: **[P]** = 원문 직접 확인(논문 본문·소스 코드 정독) /
  **[S]** = 검색 요약 기반(2차 확인 필요)
- 원자료: 학술 서베이 워커 보고(2026-08-18), OSS 실사 워커 보고
  (2026-08-18), 자체 레포 감사 워커 보고 + 보충·정정 보고(2026-08-18)

---

## 1. 결론

**3트랙이 독립적으로 동일한 결론에 도달했다: 프레임워크 교체 없음,
현행 자체 스택 유지 + 선별 차용.** 실사한 20여 개 OSS 프레임워크와
서베이한 학술 후보 중 AIRI의 실제 병목("로컬 추출 모델이 품질
게이트를 통과하지 못함")을 직접 해소하는 것은 하나도 없었다. 오히려
AIRI는 이미 constrained decoding(`"format": schema`) 1회 호출이라는
업계 최소 호출 기법을 쓰고 있어, 다른 프레임워크로 바꾸면 같거나 더
약한 기법으로 2~9배 많은 LLM 호출을 하게 된다(OSS 실사 실측).

**병목의 정체는 기법 부족이 아니라 로컬 2~4B 모델의 구조화 추출
역량 한계다.** 이는 세 트랙이 서로 다른 근거로 독립 확증했다.

| 트랙 | 근거 | 핵심 수치 |
|---|---|---|
| 학술 | *Anatomy of Agentic Memory* [P] (arXiv:2602.19320) | Qwen-2.5-3B가 Nemori 메모리 연산에서 포맷 오류 **30.38%**(gpt-4o-mini는 17.91%) — "작은 로컬 모델의 조용한 실패"가 학계에 정량 보고된 일반 현상 |
| OSS 실사 | Graphiti 이슈 #868 실측 + Cognee `ollama_support.py` 배포 실패모델 목록 + Graphiti 메인테이너 공식 입장, 3중 교차 | constrained decoding 전제 시 **qwen2.5:7b·llama3.1:8b = 6/6 성공, qwen2.5:3b·phi3.5 = 3/6**. Cognee가 레포에 직접 배포하는 목록에 Qwen2.5 7B 미만·Phi3·Mistral 7B·Gemma2를 "problematic"으로 명시(권장 llama3.1:8b / qwen2.5:14b+) |
| 자체 레포(AIRI M0 게이트 실측 이력) | 로드맵 G2 §게이트 리포트 생산 | 지금까지 테스트한 로컬 추출 후보 **9종(EXAONE 2.4B, Qwen3 4B, Mi:dm, Qwen3.5, Granite 4.0, Kanana, Gemma3, Ministral 3B, Phi-4-mini 3.8B, Granite 3.3 2B)이 전부 2~4B이고 전부 FAIL** — 통과 후보 미확정 |

즉 **AIRI가 2~4B 후보를 전부 불합격 판정한 것은 옳았고, 프레임워크를
바꿔도 이 벽은 뚫리지 않는다.** 다음 실행 단계는 "더 나은 프레임워크
찾기"가 아니라 ① 병목을 우회하는 LLM 0회 설계 채용 ② 더 큰(그러나
여전히 로컬 가능한) 8B급 모델 실측 ③ 임베딩·회상 경로 등 프레임워크와
무관한 구간의 통제 실험이다. 상세는 §3 실행 로드맵.

---

## 2. 트랙별 핵심 발견

### 2-1. 학술 서베이 — 이식 가치 TOP 3

전제: 프레임워크 통째 도입은 전부 부적합(지연·인프라·추출 LLM
의존)하므로, 아래는 **아이디어 차용** 관점의 순위다.

**🥇 1위 — Eywa "증거 우선(Evidence before Belief)" 2계층 쓰기 +
LLM 0회 읽기** [P] (arXiv:2605.30771)
원문 턴을 먼저 불변 저장하고 결정론적 signal detector로 typed
anchor(날짜·엔티티·금액·URL 등)를 뽑는 Tier 0(LLM 0회)을 먼저 만든
뒤, LLM이 제안한 fact 후보는 원문 대조 검증기를 통과해야만 승격되는
Tier 1을 얹는다. 읽기 경로는 vector·SQLite FTS5 BM25·temporal·
entity 순회를 가중 RRF로 융합하며 **LLM 호출이 단 한 번도 없다**.
hot vector search 1~3ms, LoCoMo 90.19%/LongMemEval-S 88.2%.
AIRI 함의: **추출 FAIL이 데이터 전손으로 이어지지 않는 유일한
설계** — 병목을 없애는 게 아니라 무해화한다.

**🥈 2위 — Nemori "LLM-free fallback + BM25 우선"** [S/P]
(arXiv:2508.03341, 포맷오류 수치는 arXiv:2602.19320 [P])
에피소드 경계 검출이 LLM 실패·타임아웃 시 rule-based 검출 +
TF-IDF 요약으로 자동 강등(손실 약 5%). 검색은 임베딩이 아니라
BM25가 대화체 데이터에서 더 낫다는 것이 저자 주장. 단
Qwen-2.5-3B에서 포맷 오류 30.38% 실측이 있으므로 LLM 경로는
반드시 fallback과 쌍으로 배선해야 한다.

**🥉 3위 — LightMem "1B급 전용 SLM + 소량 LoRA"** [P]
(arXiv:2604.07798)
메모리 쓰기 전용으로 Llama-3.2-1B-Instruct 또는
Qwen2.5-1.5B-Instruct를 대화용 모델과 분리 배치하고 LoRA
2,000샘플로 태스크를 좁혀 품질 게이트 통과율을 올린다. "추출 LLM
품질 미달"의 해법이 더 큰 모델이 아니라 더 작고 좁게 튜닝된
모델이라는 반직관적 실증. RTX 4090 기준 검색 median 83ms/P95 167ms.

**⚠️ 별도 최중요 경고 — MemDelta** [P] (arXiv:2606.29914)
LongMemEval-S에서 MiniLM 임베딩 사용 시 Mem0 72.7% vs 순수 RAG
61.4%로 Mem0 압승처럼 보이나, **임베딩만 교체**(코드·데이터·검색
로직·프롬프트는 고정)하면 RAG 73.9%로 역전해 **Mem0가 1.2%p
패배**한다. 저자 결론: "임베딩 선택을 통제하면 정교한 메모리
아키텍처의 이득은 제한적이다." → §3 ③ 임베딩 A/B의 직접 근거.

**한계·정정 사항**: 2026년 arXiv 항목은 일부만 본문 정독([P])했고
나머지는 검색 요약([S])이므로 [S] 수치는 2차 확인 필요. LoCoMo
단독 벤치마크는 §7 한계 참조.

### 2-2. OSS 실사 — 20여종 표 요약

| 프레임워크 | ★ | 완전 로컬 | 추출 LLM 요구 | 한국어 | 판정 |
|---|---:|---|---|---|---|
| Letta | 24,293 | △ | tool-calling 강제 | 없음 | 기각(주력 개발이 TypeScript `letta-code`로 이동, Python 서버는 은퇴) |
| Mem0 | 63,509 | ✅ | 1회, **제약 없음**(`find`/`rfind` 문자열 절단) | 기본 OFF | 기각 |
| Zep | 4,847 | ❌ | — | — | 기각(90일 커밋 전부 Cloud SaaS, OSS 사실상 폐기) |
| Graphiti | 30,037 | △ | **3+M회**(엣지 5개=8~9콜, 12~36초/건) | 구조적 결함 | 기각 |
| Cognee | 30,095 | ✅ | 2회/청크(프롬프트 주입·json_mode, constrained decoding보다 약함) | 교체 가능 | **부분 차용** |
| LangMem | 1,614 | ✅ | trustcall 강제 | 영어 고정 | 기각(사실상 정지) |
| Memobase | 2,848 | △ | 필수 | en/zh만 | 기각, **택소노미 설계만 차용** |
| ReMe(구 MemoryScope) | 3,323 | ✅ | 2~7콜(검색은 LLM 0회) | 토크나이저 결함 | **부분 차용** |
| MIRIX | 3,432 | ❌ | **4~8콜** | 없음 | 기각 |
| Second-Me | 15,663 | — | LoRA 파인튜닝 | — | 기각(2025-09 이후 커밋 0, 사실상 사망) |
| TeleMem | 484 | ✅ | **Qwen3-8B 실증** | CJK 실증 | PoC 가치(§3 ②의 근거) |
| OpenMemory | 4,444 | ✅ | 0회(정규식) | 영어 전용 | 아이디어만(엔티티 추출 자체를 안 함 — 해법 아닌 기능 삭제) |
| Ombre-Brain | 1,202 | ✅ | 선택적 | 중국어 문서 | 설계 차용 |
| memU | 14,315 | △ | 호스트 위임 | — | 기각 |
| Haystack/LangChain memory | — | ✅ | 롤링 요약 | — | 기각 |

**AIRI 코드 실측 대조**: `memory_extraction_provider.py:174`가 이미
Ollama에 `"format": schema`(네이티브 constrained decoding)를 넘기고
`memory_stage_b.py`는 content-free `add/update/noop/supersede` +
bounded enum으로 축소되어 있다. 그 결과 **모든 후보 모델의
`schema_pass_rate`가 1.0** — 게이트 FAIL은 스키마 준수가 아니라
recall/alias/placeholder 등 "모델 판단" 지표에서 발생한다.

**차용 4건(우선순위순)**: ① alias 매핑을 LLM에서 제거하고 KURE-v1
임베딩 유사도+규칙으로 결정론 처리(최우선 — `op_alias_accuracy`
0.0~0.57 문제군을 통째로 제거) ② Memobase의 고정 택소노미(개방형
추출을 슬롯 채우기로 축소) ③ GLiNER2(205M~340M 비-LLM zero-shot
NER, Graphiti `gliner2_client.py`가 사용) ④ Cognee
`litellm_native`의 검증 실패 재프롬프트 자기교정 루프(최대 3회).

**정정 사항**: (a) Letta는 표에서 가장 오해를 부르는 항목 —
★24,293은 은퇴한 랜딩 페이지(Python V1은 `archive` 브랜치)이고
실제 개발은 ★3,031의 TypeScript `letta-ai/letta-code`로 이동해
Python FastAPI 스택에 임베드 불가. (b) OpenMemory의 "LLM 0회"는
`classify_content()`(정규식) 5섹터 라우팅일 뿐 entity/fact/relation
추출을 하지 않는 것 — 병목을 푸는 게 아니라 기능을 삭제한 것이며
영어 리터럴 패턴이라 한국어는 전 섹터 0점. (c) 롤링 요약은 기각 —
CS-Sum(arXiv:2505.13559) 실측상 Gemma-2-2B가 대화 요약에서 화자를
35~70% 오귀속, 버튜버 기억에서 "시청자 발화 vs AIRI 발화" 혼동은
허용 불가. (d) 배제한 오진 1건: 무음 truncation 우려 제기됐으나
`num_ctx=8192` 명시(`benchmark_memory_track.py:352`)와 최악 입력
3,513자 확인으로 원인 아님을 확인. (e) 한국어권 기억 프레임워크는
전수 조회(nlpai-lab·naver·NCSOFT·kakao) 결과 존재하지 않음 —
AIRI 자체 스택이 이 영역 최선단.

### 2-3. 자체 레포 발굴 — 개정 TOP 3와 정정 사항

**병목 재확인(실측 재현)**: `airi-production-context-gate` 결과
필드별 재집계에서 구조화 블록(card/memory/ledger)은 압력 0~48
전 구간 **12/12**인 반면 대화 회상(dialogue_marker)은 **0/12** —
num_ctx 용량 문제가 아니라 "구조화로 주입 안 된 것은 전부 사라짐"이
원인. 원인 3중: ① 전경 투영이 최대 5개 메시지로 잘림
(`foreground_context.py:86-117`) ② 추출 OFF로 구조화 기억이
canon 6행뿐 ③ 유일한 회상 경로(journal recall)의 결함.

**신규 발견 — journal recall 어휘 매칭 결함**: `airi_memory.py:1219
-1222`가 FTS5 prefix 질의로 후보를 뽑아놓고 재점수는 완전일치
토큰 교집합으로 계산해 버린다. `'포지 기억나?'` → MISS 실측 재현.
`bm25()`가 기존 `conversation_message_fts` 인덱스에서 오늘 그대로
동작함을 실측 확인(의존성 0, 스키마 변경 0).

**개정 이식 후보 TOP 3**:

1. **journal recall 어휘 스코어링 교체** — 난도 낮음/효과 큼.
   완전일치 교집합을 FTS5 `bm25()`로 교체. 사내 선례
   `knowledge_store.py:453,478-480` 재사용 가능. 현재 유일하게
   살아있는 회상 경로의 미스를 제거한다.
2. **LLM 0회 축적 계층** — 난도 중/효과 큼(talkain 신규 발견으로
   구성 개정). (a) `tb_user_interest` 패턴 이식 — 이벤트별 가중치
   (Like 1.0/Comment 1.5/Bookmark 2.0/View 0.3) 누적 + 6시간마다
   0.95 감쇠 + 0.1 미만 GC, **LLM 호출 0회**. AIRI의 `affect_state`
   familiarity(3단 하드코딩, 영속화 전무)를 이 형태로 대체.
   (b) 세션 에피소드 헤더 — 구조(`CB_OpenAiPrompt.cs:86-108`)와
   생산자(`CB_MemoryStoryService.cs:126-135`, moment fact 연결
   LLM 0회)가 talkain에 각각 존재하나 미연결. **AIRI는 반드시 둘을
   함께 붙여야 함**(talkain은 안 붙여서 죽은 컬럼이 됨).
   (c) `viewer_memory.py` 배선(이미 테스트 green, B4c가 필요성 실증).
3. **추출 부담 완화** — 난도 중/효과 불확실하나 유일한 활성화 경로.
   3-a(저비용 선행): talkain scene-analyze식 "bool/enum만 묻고
   산술은 코드"(`CB_OpenAiService.cs:449-458`)를 AIRI의 죽은
   `story_day`/`time_of_day` 컬럼에 적용, 세션당 1회 호출.
   3-b(본격): Stage A를 "생성"에서 "스팬 선택 + 코드 검증"으로
   전환(rag_cache `game.py:1624-1660` 앵커 패턴 이식) —
   `parse_stage_a`가 이름의 `<turns>` 실재 여부를 검증하지 않는
   비대칭을 제거해 `unexpected`·`placeholder_rate` 실패를 구조적으로
   없앤다.

**AIRI가 이미 앞선 부분**: talkain 대비 세션 GC·워터마크 전진·추출
배치 상한·relation UPDATE 가능성·alias 충돌 검증·structured
output·decay 단위 일치 등 6종 함정을 이미 회피 중(역이식 금지
목록). rag_cache 대비도 KURE-v1·SQLite 브루트포스·워터마크·
canon-snapshot·LLM 0회 검색·fail-soft 등 다수 채택 완료(§3 근거
표 참고).

**정정 사항(보충 보고에서 자체 수정)**: (a) talkain
`## Past`(세션 요약) 블록은 **쓰기 경로가 레포 전체에 0건**이라
"검증된 해법"이 아니라 "구조는 있으나 생산자가 없는 설계도"로
격하 — 이식 시 반드시 생산자(moment fact 연결)를 함께 붙여야
죽은 컬럼이 되지 않는다. (b) rag_rnd "하이브리드"는 dense+sparse가
아니라 **Vector+Graph+Community의 하이브리드**이며 융합은
RRF/가중합이 아니라 프롬프트 섹션 concat(스코어는 버려짐).
(c) rag_rnd의 BM25는 존재하되 **이미지 재랭킹 경로 전용**
(`rank_bm25.BM25Okapi` + char bigram + RRF k=60) — 텍스트 RAG는
100% dense-only. (d) rag_rnd의 CrossEncoder는 "실시간 부적합"이
아니라 현재 런타임 2곳에서 상시 동작 중(3.3s→~0.9s로 pool
조정해 채택). (e) RAG 게이트가 항상 LLM 0회인 것은 아님 —
`needs_retrieval`의 `ig_qtype` 첫 분기는 LLM 1회(~0.8s).

**보안 통보**는 §6 참조.

---

## 3. 실행 로드맵

① **journal recall BM25 교체** — 근거: 자체 레포 발굴 1위.
`airi_memory.py:1219-1222`의 완전일치 교집합을 FTS5 `bm25()`로
교체. 의존성 0·스키마 변경 0·`bm25()` 실측 동작 확인 완료.
소관: dev PC 구현, 회귀 테스트 4케이스 + 컨텍스트 게이트
재실행(dialogue_marker 0/12 변화 확인)으로 검증.

② **Qwen3-8B를 M0 게이트에 투입** — **실행 완료(2026-08-18), 결과
FAIL.** `persistent_trait` 단일 스모크는 만점 통과(2~4B 후보 9종은
전부 실패했던 지점)했으나 full balanced는 recall 0.429·alias 0.286로
불통과. 같은 하네스 3점 계열(2.4B/4B/8B) 대조에서 **크기는
unexpected를 9→2로 줄였지만 critical recall은 0.43~0.50에서 정체**해,
아래 "2~4B 역량 한계" 가설은 recall 축에서는 성립하지 않는다.
다음 수순은 모델 확대가 아니라 ⑤의 Stage A 재설계다 —
`완료/AIRI-QWEN3-8B-EXTRACTION-GATE-2026-08-18.md`. 원래 근거는 아래와 같았다:
OSS 실사(TeleMem이
Qwen3-8B로 ZH-4O 86.33% 실증, LogicKor 8.71 vs Qwen3-4B 7.77·
Llama-3.2-3B 3.11) + 학술(LightMem — "더 큰 모델"이 아니라
"태스크를 좁힌 모델"이 정공이라는 반직관적 실증, 단 Qwen3-8B는
지금까지 테스트된 9개 후보가 전부 2~4B였다는 공백을 메움) +
자체 레포(32GB RAM + 추출이 이미 async라 물리적 여유 확인).
소관: 게이트 실측(§7 한계 — 아직 미실행).

③ **임베딩 A/B (BGE-M3 / KURE-v1 / Kanana-Nano-2.1B)** — **KURE-v1 vs
BGE-M3 실행 완료(2026-08-18): 두 모델 구분 불가, 교체 없음.** 신규 48문서
/24질의 한국어 평가셋에서 24개 중 1개만 갈렸다(MRR 0.921 vs 0.942).
MemDelta식 역전은 재현되지 않았다 — KURE-v1이 BGE-M3의 한국어 파인튜닝인
만큼 예상과 부합한다. 남은 실패는 임베더가 아니라 암묵적 부정·속성 질의
추론 간극이다. `완료/AIRI-EMBEDDING-AB-KURE-BGEM3-2026-08-18.md`.
원래 근거는 아래와 같았다:
학술 MemDelta 실측(임베딩 교체만으로 시스템 순위 역전, §2-1
참고) — **최저비용·최고기대값이라 최우선 실행 권고**. 소관: 실측
실험, AIRI 실제 한국어 대화로 A/B.

④ **LLM 0회 축적 계층 도입** — 근거: 자체 레포 발굴 신규
`tb_user_interest`(가중 누적+주기 감쇠+GC, talkain 프로덕션 실측)
+ 학술 MemoryBank의 Ebbinghaus 지수감쇠(순수 산술, LLM 비용 0) +
Eywa Tier 0 원칙(원문+typed anchor 우선 저장). 소관: `affect_state`
familiarity·`continuity_ledger`를 `airi-memory.sqlite3`에 영속화하고
임계값을 테이블화(매직넘버 금지 원칙 부합), 세션 에피소드 헤더의
구조+생산자를 함께 배선.

⑤ **보완 항목** — GLiNER2 한국어 NER 품질 실측(학술+OSS 공통
미확인 사항, §7), alias 매핑 LLM 제거(OSS 실사 차용 1위),
Memobase 고정 택소노미 슬롯화(OSS 실사 차용 2위), Stage A
스팬 선택+코드 검증 전환(자체 레포 TOP3 3위), Stage B만 제약
디코딩 해제 A/B(OSS 실사 — "Let Me Speak Freely?" arXiv:2408.02442가
JSON 제약이 추론형 태스크를 파괴함을 보임, Claude-3-Haiku GSM8K
86.5%→23.4%).

---

## 4. 기각 목록

| 후보 | 기각 사유(1줄) |
|---|---|
| HippoRAG2 | 쿼리마다 LLM 1회 추가 호출(recognition memory) + NV-Embed-v2 7B 임베더 — 저지연 예산(14.9ms)과 자릿수 차이 |
| A-MEM | 메모리 1건당 LLM 2~3회, 독립 감사에서 오프라인 구축 15시간 실측 |
| MemOS | Neo4j+Qdrant 필수 — 8GB dev PC에 인프라 과중 |
| MemoryOS | 독립 감사에서 턴당 32.4초 지연 실측 — 방송 중 사용 불가 |
| MIRIX | 6종 메모리+멀티에이전트 구조로 에이전트마다 LLM 호출, 극도로 높은 의존도 |
| Letta | 실제 개발이 TypeScript `letta-code`로 이동, Python FastAPI 스택에 임베드 불가 |
| Mem0 | 추출 LLM 필수 + 제약 없는 파싱(`find`/`rfind` 문자열 절단), 한국어 기본 OFF |
| Zep | GitHub 레포 90일 커밋 전부 Cloud SaaS — OSS로서는 사실상 폐기 |
| Graphiti | 엣지 1개당 LLM 3+회(엣지 5개=8~9콜), 12~36초/건 실측 |
| Cognee | 프롬프트 주입 방식(json_mode)이 constrained decoding보다 약한 추출 기법, 2회/청크(단 부분 차용은 유지) |
| MemoryBank | 프레임워크 자체는 무겁고 불필요 — Ebbinghaus 감쇠 아이디어만 차용 |
| 롤링 요약(LangChain/Haystack) | CS-Sum 실측 Gemma-2-2B 화자 오귀속 35~70% — 시청자/AIRI 발화 혼동 위험 |
| LangMem | 40개 최근 커밋 전부 봇, 사실상 정지, trustcall 강제, 영어 고정 |
| Memobase | 2026-01-11 이후 커밋 0, en/zh만 지원 — 고정 택소노미 설계만 차용 |
| Nemori(프레임워크 자체) | LLM-free fallback·BM25 우선 아이디어는 차용하되 프레임워크 통째 도입은 대상 아님 |
| OpenMemory | "LLM 0회"는 entity/fact/relation 추출을 안 하는 것 — 해법이 아니라 기능 삭제 |

---

## 5. "위그로어" 탐색 결과

학술·OSS 두 트랙에 각각 독립적으로 발음 유사 검색을 위임했으며,
결론이 일치했다 — **"위그로어"라는 이름의 기억 연구
프로젝트/논문은 찾지 못했다.**

- **학술 트랙**: Wigro/Vigro/Wygro/Ygg/Hygro/위그드라실 등 변형
  검색 결과 2건 후보. ① **Yggdrasil**(`yggdrasil-memory`, PyPI/
  GitHub `VonderVuflya/Yggdrasil`) — 상시 구동 로컬 데몬(~21MB
  RAM), SQLite+FTS5 기본·zero-dependency·시맨틱은 선택(로컬
  Ollama), 발음 유사도 최상이나 Elastic License 2.0(순수 OSS
  아님). ② **Egregore**(`egregore-labs/egregore`) — Claude Code용
  git 기반 팀 공유 인지 계층, 음절 구성이 유사.
- **OSS 실사 트랙**: `wigroar`·`wigrower`·`wygroar`·`wigro`·
  `wegrow`·`vigror`·`hygro`·`ygg` 전 변형 GitHub 검색 무수확.
  Yggdrasil이 가장 유력하나 **★0~21로 채택 가치 없음**.

**결론**: 두 트랙 모두 Yggdrasil을 최유력 후보로 지목했으나 실
채택 가치는 낮다고 일치 판정했다. 다만 학술 트랙이 지적한
"SQLite+FTS5 기본, 시맨틱은 옵션" 계층 분리 설계는 참고할 만하다.
사용자가 들은 맥락(어느 발표·글에서 언급됐는지)을 알려주면
재탐색 가능.

---

## 6. 별건 — talkain DeepL 키 평문 보안 통보

자체 레포 감사 중 별도로 발견된 보안 이슈. 코드 기능과 무관하므로
여기 분리 기록한다.

`external/talkain-api/TalkainAPI/Extension/DeepLExtensions.cs:11-12`
에 **DeepL API 키가 소스에 평문 하드코딩**되어 있다(값은 보고서에
옮기지 않았음 — 본 문서에도 미출력). 같은 파일 `:14-16`은 호출마다
`new Translator(_apiKey)`를 생성해 커넥션 재사용도 없다. 신규
`DeepLService.cs:32-33`은 env→config 순으로 올바르게 읽으므로
구버전 확장(`DeepLExtensions.cs`)만 잔존한 상태다.

**권고**: 해당 키 폐기·회전 및 git 히스토리 정리, 구버전 확장
정리(신규 `DeepLService.cs` 경로로 통합).

---

## 7. 한계

- **LoCoMo 신뢰 주의**: LoCoMo-Plus(arXiv:2602.10715, [S])가
  LoCoMo에서 near-perfect인 모델이 MemoryArena에서 40~60%로
  급락함을 보고 — 본 문서에 인용된 LoCoMo 수치는 절대치가 아니라
  **상대비교용으로만** 사용해야 한다.
- **GLiNER2 한국어 미실측**: GLiNER-Multi의 다국어(Multiconer
  11개 언어) 실측은 ChatGPT를 상회하나, **한국어 개별 수치는
  확인하지 못했다**. §3 ⑤의 다음 액션 대상.
- ~~**Qwen3-8B 게이트 미실측**~~ — **2026-08-18 해소.** 실측 결과
  full balanced FAIL(스모크는 PASS). 이로써 §1 표의 "2~4B 역량 한계"
  3중 확증은 **스키마·포맷 축에 한정**됨이 드러났다 — AIRI는
  constrained decoding으로 2.4B에서도 `schema_pass_rate` 1.0이라 학술·
  OSS가 보고한 그 실패 모드가 애초에 발생하지 않으며, 실제 병목인
  recall/alias는 8B에서도 개선되지 않았다.
  (`완료/AIRI-QWEN3-8B-EXTRACTION-GATE-2026-08-18.md`)
- **한국어 OpenIE/트리플 추출 품질**: 저하가 강하게 의심되나(조사·
  주어 생략 취약) 정량 근거를 찾지 못했다.
- **talkain `cb_chat_session.summary` 최초 기록 주체 미확인**:
  레거시로 표기되어 있으나 현행 쓰기 경로를 특정하지 못했다.
- **rag_cache 계측 공백**: Neo4j 쿼리 지연·캐시 적중률을 재는
  계측 코드가 없다.
- **rag_rnd 임베딩 비교 수치 미확인**: KURE-v1 vs BGE-M3 비교
  수치가 있는 `eval_results.md`가 gitignore되어 있어 확인 못함.
- **학술 자료 신뢰도 편차**: 2026년 arXiv 항목(26xx.xxxxx)은
  일부만 본문 정독([P])했다 — [S] 표시 수치는 2차 확인 전제로
  읽어야 한다.
