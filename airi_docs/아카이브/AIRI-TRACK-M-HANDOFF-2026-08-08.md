# AIRI Track M 장기 기억/RAG 인수인계 — 2026-08-08

## 1. 현재 결론

Track M은 더 이상 설계만 있는 상태가 아니다. 로컬 SQLite 그래프 저장소, canon snapshot, 대화 저널/워터마크, LLM 없는 검색, KURE-v1 임베딩, fail-soft 프록시 연동, memory latency 계측까지 구현되어 있다.

운영 11435에는 다음 제한 상태로 활성화했다.

- memory runtime: enabled / ready
- embedder: `nlpai-lab/KURE-v1`, CUDA, local cache only
- DB: `ollama-proxy/runtime/airi-memory.sqlite3` (git ignore)
- 자동 대화 추출: **비활성화**
- 이유: EXAONE 2.4B Stage A/B 품질 gate 실패. 불확실한 기억을 영구 저장하는 것보다 비활성화가 안전하다.

커밋/푸시는 하지 않았다.

## 2. M0 실측

### 임베딩

| 모델 | 장치 | query P50 | Recall@3 | MRR | gate |
|---|---:|---:|---:|---:|---:|
| KURE-v1 | CPU | 132.072 ms | 1.0 | 1.0 | Fail |
| BGE-M3 | CPU | 134.438 ms | 1.0 | 1.0 | Fail |
| KURE-v1 | CUDA | 31.679 ms | 1.0 | 1.0 | Pass |
| BGE-M3 | CUDA | 33.124 ms | 1.0 | 1.0 | Pass |

KURE-v1을 선택했다. 결과 JSON은 `ollama-proxy/bench-results/`에 있다.

실제 `MemoryRuntime + KURE-v1/CUDA + temp SQLite` 합성 통합 측정:

- cold model load: 10.934 s
- retrieval 내부: 15.00 ms
- payload prepare 전체: 33.70 ms
- `[Character Memory]` 주입: 성공
- entity 1 / trait 1 검색: 성공

### 로컬 추출

수정된 SUPERSEDE schema로 `exaone-airi:2.4b`, `num_ctx=8192`, 6 fixtures를 재측정했다.

- gate: Fail
- schema / connectivity: 100% / 100%
- critical recall: 55.56%
- unexpected: 18
- placeholder: 83.33%
- Stage-B op/alias: 66.67%
- total P50/P90/P95: 9.511 / 16.854 / 17.519 s

따라서 `AIRI_MEMORY_EXTRACTION_MODEL`은 빈 값이다. 클라우드 TTFT/추출은 API key와 외부 대화 전송 승인이 없으므로 실행하지 않았다.

이 수치는 당시 6-fixture 역사 결과다. 이후 평가 계약을 runtime과 대조하면서
`conversation_skip`이 Stage A에서 0개를 요구하면서 Stage B에서는 NOOP 1개를
요구하던 모순을 발견했다. 현재 fixture는 no-signal의 Stage B도 0개로 맞추고,
실제 중복 trait를 별도 NOOP 케이스로 분리한 7개다. 프롬프트나 모델을 바꾸지 않은
상태에서 숫자만 다시 만들기 위한 전체 재측정은 하지 않았다. 기존 결과는 unexpected
18, placeholder 83.33%, Stage-B 66.67%에서도 독립적으로 불합격이므로 자동 추출
비활성 결정은 유지한다. 다음 전체 측정은 extractor 후보나 prompt 계약이 실제로
변경될 때 한 번만 수행한다.

`qwen3:8b`, CPU-only(`num_gpu=0`, `num_ctx=8192`)도 같은 6 fixtures로
측정했으나 Stage A 6/6이 각각 180초 제한에 도달했다. schema pass/critical
recall은 0%, gate는 Fail이다. 품질 판정 이전에 운영 지연 기준을 통과하지
못하므로 반복 측정은 중단했고 모델도 Ollama에서 unload했다. 결과는
`ollama-proxy/bench-results/m0-extraction-qwen3-8b-cpu.json`이다.

방송 응답과 분리한 11436 worker에서 `qwen3:4b-instruct`를 단일
`persistent_trait` fixture로만 smoke했다. Stage A/B/total은
25.485/16.185/41.669초로 timeout은 피했지만 critical recall 50%, unexpected 1,
Stage-B op/alias 0%여서 gate Fail이다. 사전 규칙에 따라 전체 6-fixture로
확장하지 않았다. 결과는
`ollama-proxy/bench-results/m0-extraction-qwen3-4b-instruct-smoke.json`이다.

평가기 감사에서 허용된 Stage-A 선택의 Stage-B 연산을 hallucination으로
중복 계산하던 결함을 수정했다. 현재 gate는 Stage-A hallucination만 세고,
Stage-B는 sourceItemIndex exact-once·turn/kind/content·fact subject·relation
방향 coverage를 별도 100% 조건으로 검사한다. 수정 평가기로 이미 설치된
순정 `exaone3.5:2.4b`를 `persistent_trait` 한 건만 재측정한 결과:

- Stage A/B/total: 21.075 / 21.843 / 42.918초
- schema/recall/op accuracy: 100% / 100% / 100%
- Stage-B coverage: 0%, Stage-A unexpected: 1, gate: Fail

결과는 `m0-extraction-exaone35-24b-smoke-v2.json`이다. 따라서 EXAONE
persona/base, Qwen3 4B/8B 모두 불합격이며 로컬 후보 반복은 종료했다.
이번 작업에서만 받은 Qwen3 4B/8B 모델은 약 7.7GB를 회수하기 위해
Ollama에서 제거했고, 원래 있던 두 EXAONE 모델은 유지했다.

## 3. 구현된 M1/M2 범위

- OpenAI stream ACK 뒤 memory retrieval, upstream 전 memory block 주입
- `/api/chat` 최종 응답 저널링 (`X-AIRI-Immediate-Ack: false`; 즉시 ACK 계약은 OpenAI SSE 경로)
- final content yield 전에 background journal 예약, shutdown bounded flush
- user/assistant 한 쌍 atomic append, SQLite `BEGIN IMMEDIATE` 동시성 직렬화
- process/session UUID와 `x-airi-session-id` 지원, ordered completed-turn tail로 headerless reset 감지
- canon snapshot idempotency, empty snapshot marker, global canon 불변
- Stage A/B 원자 commit, 실패 시 watermark 불변, restart 시 dead-letter retry reset
- complete-turn 단위 추출 batch, 60 messages / 24,000 chars, 전역 extraction semaphore
- Stage-B `sourceItemIndex` exact-once, 실제 journal turn/range, subtype/content/name,
  fact subject와 relation 방향 coverage 검증
- ADD/UPDATE/NOOP/SUPERSEDE; SUPERSEDE는 replacement row/`superseded_by` 연결과
  활성 fact/relation/heard-from 참조 이관
- operation embeddings batch=16, CUDA embedder lock, embedding 실패 row는 vector NULL
- embedding model fingerprint/dimension/content-hash 검증 및 불일치 startup reindex
- session별 extraction trigger coalescing, 종료 timeout 후 task 부활 방지
- 방송 응답 11434와 CPU 추출 11436을 별도 Ollama 프로세스로 격리;
  extraction upstream은 HTTP loopback만 허용
- oversized 단일 turn은 양쪽 시작/끝을 제한 길이로 추출해 session dead-letter 방지
- NameScanner NFC/casefold occurrence span longest-match
- 한 query embedding, entity top10, traits8, moments5, scene raw20/final8, relation5, one-hop facts3
- score `0.7*cosine + 0.3*exp(-0.05*turn_delta)`
- TTL 600 cache, `RAG_CACHE=off`, data-version invalidation
- memory retrieve/extract latency event와 8892 dashboard bar; raw memory/content 미노출

## 4. 현재 검증

- memory 집중 회귀 (`test_airi_memory.py` + `test_memory_runtime.py`): 88
- `ollama-proxy` 전체 `test_*.py`: 205
- `latency-monitor/test_monitor_server.py`: 8
- `stt/test_transcription_filter.py`: 36
- C0 evaluator: 7
- Python compile: 통과
- `git diff --check`: 통과

## 5. 현재 런타임

- 11435: localhost, health OK, `num_gpu=0`
- memory: enabled=true, ready=true, embedder=true, extraction_enabled=false,
  extraction_isolated=false, extraction_ready=false, data_version=43
  (자동 추출 비활성 상태의 정상값; 기존 DB 보존 후 최신 코드로 재기동 완료)
- memory DB: sessions=37, messages/pending total=37,666, snapshots=45,
  session activity=37, materialized tail=2,220(각 session 최대 60)
- character evaluator: enabled/configured/ready=true, pending/running=0,
  active character card prompt mode=`merge`
- 8892: localhost, health OK, memory timeline dashboard 포함
- 8890/8880/9880/11434: 기존 서비스 유지
- KURE 상주 후 GPU 여유 약 1.16 GB. 추가 GPU 모델 동시 적재 금지.

## 6. 남은 Track M gate

1. EXAONE 2.4B는 품질 gate 실패, Qwen3 8B CPU는 180초 timeout으로 실패했다.
   다음 extractor 후보는 별도 경량 모델/격리 자원 또는 명시 승인된 cloud batch가 필요하다.
2. 통과 모델이 있을 때만 `AIRI_MEMORY_EXTRACTION_MODEL` 활성화 후 실제 대화 저장/검색 통합 검증.
3. AIRI 클라이언트가 실제 conversation id를 `x-airi-session-id`로 전달하도록 연결. 헤더 없는 완전 stateless client는 대화 경계를 완벽히 판별할 수 없다.
4. 30분 대화 cross-question consistency, proxy/provider down 발화 지속, 비용/외부 전송 승인 gate.
5. 사용자 음성 테스트에서 STT 전사·repeat count·director action·memory retrieve·첫 음성 지연을 같은 시간축으로 검증.

음성 테스트는 구현 선행 조건이 아니지만 M3 최종 합격 조건이다.

### AIRI v0.11.3 클라이언트 연결 조사

현재 Git 추적 작업트리에는 `packages/stage-ui` 클라이언트 소스가 없고 설치본
`app.asar`만 있다. v0.11.3의 `streamWithStageAdapters`는 이미 안정적인
`requestCorrelation.conversationId`를 갖지만 `official` provider에서만
`x-airi-session-id`를 보낸다. 11435의 openai-compatible/ollama provider에도
보내도록 official 분기 밖으로 옮기는 소스 패치를
`airi_docs/patches/AIRI-v0.11.3-session-header.patch`에 준비했다. 설치본
동일 동작을 안전한 equal-length byte patch로 적용하는
`patch-airi-session-header.ps1`도 기존 `apply-airi-patches.ps1` 세트에 추가했다.
현재 AIRI Electron 프로세스가 실행 중이어서 스크립트가 변경 전에 거부하고
archive가 그대로임을 확인했다. AIRI를 완전히 종료한 뒤에만 적용할 수 있다.

## 7. 후속 구현 체크포인트 — 2026-08-08

로컬 extractor 후보 반복은 종료한 상태를 유지했다. 이번 체크포인트에서는 모델을
추가로 내려받거나 벤치하지 않고, 남아 있던 M1/M2 배선과 결정론적 계약을 닫았다.

- `memory_extraction_provider.py`: Ollama/OpenAI/Anthropic Stage A/B provider.
  외부 provider는 `AIRI_MEMORY_ALLOW_EXTERNAL_EXTRACTION=1`, 모델, 해당 API key가
  모두 있을 때만 동작한다. 기본값은 Ollama이며 외부 요청은 0회다.
- `cloud_chat_provider.py`: OpenAI/Anthropic 직접 SSE provider. 기본값은 `local`이고,
  `AIRI_ALLOW_EXTERNAL_CHAT=1`, 모델, API key가 모두 있어야 HTTP/2 client가 생긴다.
  첫 cloud content 전 장애만 로컬 EXAONE으로 폴백하며, 첫 content 뒤에는 모델을
  바꾸지 않는다. 정상 stop + terminal event가 없는 부분 응답은 장기 기억에 쓰지 않는다.
- `airi-canon.json`: LLM 없이 적재하는 기본 canon 6개(인물 2, trait 3, 관계 1).
  `canon_source` stable key로 재기동 시 idempotent하며, 변경 시 기존 행을
  `superseded_by`로 보존하고 활성 graph reference를 새 entity로 옮긴다.
- `{{user}}`는 SQLite에 literal로 보존한다. `AIRI_MEMORY_USER_NAME`이 있을 때만
  upstream memory block에서 표시명으로 바꾸며, 받침과 `이가/가`, `이야/야`,
  `으로/로`를 포함한 한국어 조사를 고른다.
- 실제 FastAPI 프록시 요청을 deterministic Stage A/B fixture로 흘려
  `proxy → journal → extractor → SQLite → 다음 질문 retrieval` E2E를 통과했다.
- OpenAI structured output은 `finish_reason=stop`, Anthropic은
  `stop_reason=end_turn`일 때만 commit한다. 잘렸지만 JSON이 유효한 응답도 거부한다.

최신 로컬 회귀 기준은 `ollama-proxy` 161개, latency monitor 8개, STT 36개로
총 205개다. 외부 API 실호출과 추가 모델 벤치는 포함하지 않는다.

11435 재기동 실측:

- `chat_provider`: local / external_approved=false / ready=false
- memory: enabled=true / ready=true / embedder=true
- global active base canon=6 / canon source key=6 / entity=2
- extraction: 비활성(합격 extractor가 없으므로 정상)

남은 gate는 코드 미구현과 외부 조건을 구분한다.

1. Cloud extraction/chat 실측은 사용자 외부 전송 승인과 credential이 있어야 한다.
   그 전에는 두 feature flag를 false로 유지한다.
2. AIRI 설치본의 session header patch는 AIRI가 완전히 종료된 뒤 적용한다.
3. 승인된 extractor로 실제 자동 대화 기억 품질을 확인한 뒤 30분 cross-question
   consistency와 provider-down 발화 지속 시험을 한다.
4. 사용자 음성 시험에서 STT·repeat count·director action·memory retrieve·첫 음성을
   같은 trace 시간축으로 확인해야 M3를 판정할 수 있다.

## 8. 운영 프라이버시·비용 계측 체크포인트 — 2026-08-08

- 외부 검색도 `AIRI_ALLOW_EXTERNAL_SEARCH=false`가 기본이다. 승인하지 않은 상태에서
  검색형 발화는 Codex subprocess를 호출하지 않고 로컬 대화 경로로 내려간다.
- cloud chat과 cloud Stage A/B extraction은 같은 로컬 usage ledger에 호출별
  provider/model/duration/status/input/output/cache token만 기록한다. 대화·프롬프트·
  응답·API key는 기록하지 않는다.
- 비용은 저장 시점에 고정하지 않고 `provider_usage.py report`에서 전달한 최신 단가로
  계산한다. 단가가 없는 모델은 0원으로 가장하지 않고 `unknown`이다.
- OpenAI/Anthropic SSE parser는 UTF-8 분할, multiline event, 정상 stop+terminal,
  max-token/truncation 거부와 error usage 기록까지 단위 테스트로 검증했다.
- 최신 로컬 회귀 기준은 `ollama-proxy` 161개, latency monitor 8개, STT 36개로
  총 205개 통과다. 실제 cloud 호출과 추가 모델 벤치는 실행하지 않았다.

## 9. G1 캐릭터 상태 루프 기반 — 2026-08-08

장기 기억 확장을 반복하기 전에 성장 전략의 G1 경계를 먼저 만들었다.

- `character_state.py`는 `x-airi-session-id` 기준의 bounded LRU 단기 상태를 관리한다.
  헤더가 없으면 현재 proxy process 안에서만 `implicit-local-session`을 사용하며,
  이를 재시작을 넘는 안정 ID로 간주하지 않는다.
- 상태는 현재 화제, 대화 목표, 사용자/AIRI 관심, 감정과 원인, 관계 단계와 근거,
  마지막 사용자 요청·실제 행동·도구 결과, 반복 의도·이전 답변 충족 여부,
  침묵 시간·최근 응답/자발 발화 시각을 명시적으로 가진다.
- 현재 턴의 사용자 발화는 길이가 제한된 관찰값으로만 보관한다. 관심·관계·감정 같은
  해석 필드는 allowlist된 model state update만 받을 수 있으며, 키워드 또는 반복 횟수로
  대사나 행동을 선택하는 규칙은 없다.
- `character_state_evaluator.py`는 정상 완료 turn 뒤 local `exaone-airi:2.4b`에 strict
  JSON schema로 상태 해석만 비동기 요청한다. launcher 기본값은 enabled이며 외부 host,
  대사·행동·도구·안전 판정 필드는 허용하지 않는다.
- evaluator는 session별 latest-turn coalescing, 전역 동시성 1, 최대 256 session을
  지킨다. schedule 당시 version/snapshot과 apply 직전 non-mutating version이 다르면
  stale 결과를 버리고, 오류·timeout·partial 응답은 상태를 바꾸지 않는다.
- 새 사용자 turn이 시작되면 같은 11434 queue의 evaluator 작업을 먼저 취소·추적해
  foreground TTFT를 우선한다. 종료 시 지연 취소 task까지 bounded하게 회수한다.
- local/director/search/cloud/fallback의 최종 완료 경계에서 실제 실행 action, emotion,
  tool status를 관찰한다. 오류 안내는 단기 상태에는 남기되 장기 memory journal에는
  넣지 않고 model evaluator에도 보내지 않는다.
- 다음 요청의 static identity prompt에 bounded `[Character State]`를 붙인다. 반복
  dialogue director도 동일 블록을 보지만, allowed action 중 무엇을 택할지는 모델이
  결정한다.
- AIRI가 보낸 system character card는 사용자 메시지와 분리해 4,096 chars로 제한하고
  proxy 출력/제어 규칙 뒤에 병합한다. 고정 25자·매번 감탄사 규칙은 제거하고, 간단한
  질문은 짧게 하되 설명·감정·관계 맥락을 1~3문장으로 완결하는 일반 규칙으로 바꿨다.
- health는 상태 내용과 session id를 노출하지 않고 session 수와 capacity만 보고한다.
  현재 11435 실측은 state enabled, evaluator enabled/configured/ready=true다.

합성 한 턴 smoke에서 evaluator는 8.399초 후 화제·사용자 관심·감정 원인·관계 단계를
구조화해 `last_status=ok`로 갱신했다. 이 시간은 완료 발화 뒤 background 시간이며 새
사용자 turn에는 취소된다. 자발 발화 scheduler는 아직 구현하지 않았다. 이 미완료
항목을 횟수 if문이나 검색 전용 규칙으로 대신하지 않는다.

## 10. G2 no-header 재시작 복구 보강 — 2026-08-08

안정적인 `x-airi-session-id`가 최종 계약이라는 원칙은 유지하면서, 앱이 아직 헤더를
보내지 않는 현재 운영에서도 proxy 재시작이 곧바로 대화 기억 단절로 이어지지 않도록
보수적인 복구 경로를 추가했다.

- cold start의 첫 no-header 요청에서 client가 보낸 완료 user/assistant turn의 SHA-256
  pair tail을 최근 SQLite session과 비교한다. 대화 원문은 후보 검색에 읽거나 기록하지
  않는다.
- 최대 최근 256 sessions, session별 최근 60 completed turns로 탐색을 제한한다.
- 2 turns 이상 exact suffix가 일치하고 최고 점수 session이 하나일 때만 복구한다.
  한 턴짜리 인사/상투 답변과 동일 최고 점수의 모호한 후보는 복구하지 않는다.
- recovery가 없으면 fresh configured scope에 history를 bootstrap한다. 기존 session의
  watermark를 새 대화에 적용하지 않는다.
- launcher의 기본 base scope를 매번 새 GUID가 아니라 `broadcast-default`로 고정했다.
  다른 history는 runtime이 UUID child로 회전하므로, 같은 base를 재기동할 때 canon
  snapshot row와 `data_version`이 계속 늘어나는 문제를 막는다.
- 실제 11435를 stable base로 연속 두 번 재기동한 결과 첫 migration 기동은
  `data_version=9`, 두 번째 기동도 `data_version=9`로 유지됐다.
- 같은 process가 이미 implicit session을 claim한 뒤에는 한 턴 tail도 연속성 신호로
  사용할 수 있지만, cold start에서는 절대 한 턴만으로 과거 session을 선택하지 않는다.
- 명시적인 session header는 언제나 우선하며 implicit recovery 상태를 변경하지 않는다.
- session 탐색과 bootstrap/publish는 같은 async lock 안에서 처리해 동시 첫 요청이
  아직 비어 있는 rotated session을 함께 claim하지 못하게 한다.

이 복구는 header가 없는 과도기 fail-soft다. 완료 history가 2턴 미만이거나 client가
history를 보내지 않으면 재시작 전 session을 안전하게 식별할 수 없다. AIRI client의
stable header patch가 G2의 최종 session-isolation 조건이라는 점은 변하지 않는다.

## 11. G3/C0 재현 가능한 기준 평가 세트 — 2026-08-08

모델 학습 코드보다 먼저 현재 `exaone-airi:2.4b`의 고정 기준선을 남겼다. 이 작업은
LoRA/QLoRA나 구조 pruning을 시작하지 않으며 원본 Ollama 모델을 변경하지 않는다.

- `ollama-proxy/eval/airi_baseline_cases.json`: 실제 사용자 데이터가 없는 합성 fixture
  10개. 한국어 일반, AIRI 말투, 모호한 반복/잘린 답변 복구, memory 있음/없음 쌍,
  ACT/control 노출, 실행하지 않은 tool 주장 안전성을 포함한다.
- `run_airi_baseline.py`: proxy를 import하지 않고 AST로 현재 system prompt literal을
  읽는다. loopback이 아닌 endpoint는 명시적 `--allow-host` 없이는 거부한다.
- Ollama NDJSON은 임의 UTF-8 byte split을 처리하고 `done:true` terminal이 없으면
  결과를 쓰지 않는다. `--runs 1..10`은 실제 반복하고 케이스 시간은 중앙값으로 낸다.
- report에는 fixture/system-prompt hash, Ollama manifest digest, Modelfile SHA-256,
  GGUF family/parameter/quantization, 설정, RAM/VRAM, 각 합성 output/check, TTFT/총 시간/
  tok/s만 기록한다. 원문 Modelfile, 실제 대화, prompt 본문, secret은 기록하지 않는다.
- 결과 파일은 `ollama-proxy/eval/results/exaone-airi-2.4b-c0-baseline-2026-08-08.json`
  및 같은 이름의 Markdown이다.

고정 설정은 `num_ctx=2048`, `num_gpu=0`, `temperature=0`, `seed=42`, `runs=1`이다.
설치 모델 digest는
`ec47936ec5439ea3c24bbdd069b3a7aeba5cd8100ab193367bd959fac679bde4`, Modelfile
SHA-256은 `b2c0386309f4072c3ca97101f3c1198fdfcada80d8fe11ce9126458276be9cb7`이다.
G1 자연 대화 규칙 반영 뒤 system prompt SHA-256은
`618f242b97378a9c47e1a43aeaadc044dd75ec7eb86dbb998b606a86de8ae129`다.

최초 warm/loaded 기준선은 10개 중 2개 PASS로 전체 gate가 FAIL이다. 단문 설명과
대화 이력을 이용한 잘린 답변 복구는 통과했다. 최신 raw-model 실패는 이모지·2문장
초과, 모호한 요청의 확인 질문 누락, 실행하지 않은 파일 삭제 경계 실패가 중심이다.
memory 있음/없음 쌍은 필요한 사실 사용과 이름 비창작은 했지만 raw 길이 gate를 넘었다.
케이스 중앙값의 전체 중앙값은 TTFT 약 0.384초, 총 응답 약 2.298초, 생성 약
18.01 tok/s다. 이 실패는 단기
예외문이나 검색 전용 규칙으로 덮지 않고 G1 상태 전이 평가와 후속 데이터 후보로 쓴다.

최신 회귀는 proxy 205개, latency monitor 8개, STT 36개, C0 evaluator 7개로
총 256개 통과다. C0의 합성 자동 기준선 산출물은 생겼지만 human rating,
반복 3회 이상 분산, cold/warm 분리, 실제 음성 및 T0→첫 음절 평가는 아직 남아 있다.
따라서 G3/C0 기반은 시작됐지만 모델 커스터마이징 착수 gate가 완료된 것은 아니다.

## 12. 자동 추출 availability 복구 — 2026-08-08

품질 gate를 통과한 extractor를 나중에 활성화할 때, worker 준비 지연이나 일시 장애가
기억 전체를 dead-letter시키지 않도록 운영 경계를 닫았다.

- local Ollama는 시작과 재시도 전에 `/api/tags`로 지정 모델을 확인한다. tag 없는
  `name`과 Ollama의 `name:latest`는 같은 모델로 정규화한다.
- worker 미기동, 모델 미적재, transport 오류는 `fail_count`를 올리지 않는다.
  conversation journal과 watermark는 그대로 두고 단일 global recovery task에서
  1초부터 최대 60초까지 exponential backoff한다.
- 여러 session의 실패는 session별 timer를 만들지 않고 한 retry queue로 합친다.
  provider가 복구되면 SQLite의 기존 pending session까지 자동으로 drain한다.
- malformed/truncated JSON, Stage A/B coverage 실패, 외부 provider의 영구 4xx는
  품질·설정 실패로 남아 기존 5회 cap을 따른다. 외부 429/5xx와 transport만 backoff한다.
- health는 원문·session id 없이 `extraction_availability`, `extraction_retrying`,
  `extraction_retry_sessions`를 보고한다. 외부 provider health는 network probe를 하지
  않고 마지막 runtime 상태만 노출한다.
- shutdown은 retry/extraction task를 모두 bounded drain/cancel하므로 shared HTTP client
  종료 뒤 task가 부활하지 않는다.

이 변경은 자동 추출을 켜지 않는다. 현재 `AIRI_MEMORY_EXTRACTION_MODEL` 빈 값과
품질 gate 우선 원칙은 그대로다.

## 13. G3 명시적 평가·교정 데이터 기반 — 2026-08-08

모델 학습이나 자동 대화 수집을 시작하지 않고, 사람이 명시적으로 고른 평가만 로컬에
보존하는 G3 검토 큐를 추가했다. 기본값은 비활성이며 chat 응답 경로가 이 저장소에
자동으로 쓰는 코드는 없다.

- `evaluation_store.py`는 rating(`good|bad|revise`)과 chosen/rejected preference를
  SQLite schema v1로 저장한다. `consent`는 JSON boolean `true`일 때만 인정하며,
  `revise`에는 correction, 부정 평가와 preference에는 허용된 reason tag가 필요하다.
- 각 record에는 model/model version, system prompt SHA-256, memory schema version,
  dataset version, `synthetic|user_approved` origin을 붙인다. API key, tool payload,
  내부 식별자와 자동 수집된 실대화는 저장하지 않는다.
- 새 record는 `needs_review`로 시작하고 사람이 `approved|rejected`로 한 번만 전이한다.
  export 기본값은 approved-only이며 한 페이지는 최대 1,000건이다. 삭제 API는 실제로
  해당 record를 제거한다.
- 저장소는 기본 10,000건, 설정 가능한 최대 1,000,000건 상한을 갖는다. 상한에 닿으면
  기존 데이터를 자동 삭제하지 않고 새 수집을 거부한다. count와 insert는
  `BEGIN IMMEDIATE` 한 transaction 안에서 실행해 동시 writer도 상한을 넘지 않는다.
- `AIRI_EVAL_ENABLED=true`를 명시해야만 저장소가 열리고, launcher 기본값은 false다.
  record마다 별도 `consent=true`도 필요하므로 기능 승인과 개별 데이터 승인이 분리된다.
- `/v1/airi/evaluations/status|rating|preference|export|{id}` API를 제공하지만 기존
  loopback/Origin 경계를 그대로 적용한다. Origin 검사는 문자열 prefix가 아니라
  scheme과 정확한 hostname을 비교한다. `localhost`의 정상 개발 port는 허용하되
  `localhost.evil`, userinfo 삽입, HTTPS 스킴 변경은 403이다.
- 저장소 오류와 입력 오류는 원문을 되비추지 않고 fail-soft로 격리한다. health에는
  경로·대화 내용 없이 활성 여부, schema, review count, total, max records만 나온다.

보안 재감사에서 기존 Origin suffix 우회와 무제한 저장/export 문제는 닫힌 것으로
확인했다. 독립 store 25개가 동시에 max 5에 쓰는 재현도 성공 5건/용량 오류 20건으로
정확히 제한됐다. 최신 회귀는 proxy 176개, latency monitor 8개, STT 36개,
C0 evaluator 7개로 총 227개 통과다.

이 단계는 학습 데이터셋 확정이나 LoRA/QLoRA 착수가 아니다. 실제 사용자 평가를
켜기 전 별도 승인과 UI/운영 절차가 필요하고, approved record의 사람 검토 품질과
버전 고정 export가 후속 G3 gate다. 원본 `exaone-airi:2.4b`는 변경하지 않았다.

## 14. 추출기 미가용 회상과 no-header 세션 증식 차단 — 2026-08-08

자동 추출기는 품질 gate 때문에 계속 비활성화 상태다. 이 상태에서 pending journal이
60 messages를 넘으면 오래된 사실이 raw tail과 structured memory 양쪽에서 사라지는
HIGH 회상 공백을 합성 DB로 재현했다. 498 completed turns/996 pending messages에서
turn 1의 고유 사실은 질문 retrieval gate가 true여도 upstream payload에 없었다.

이를 막기 위해 같은 resolved session의 미추출 complete pair만 대상으로 하는 bounded
local journal recall을 추가했다. 최신 4,096 messages를 lexical scan하고 최대 4 turns/
1,200 chars만 `[Untrusted Journal Recall]` 증거 블록으로 삽입한다. LLM/API/embedder를
호출하지 않으며 watermark, extracted flag, pending count, data version을 변경하지 않는다.
498-turn 재현에서는 고유 사실 1건을 15.032ms에 회수했고 상태가 전부 동일했다.

동시에 AIRI wire assistant history의 ACK/ACT wrapper와 journal의 canonical speech가
달라 pair-tail 복구가 매 요청 실패하고, full history를 새 UUID session에 반복 복제하는
O(n²) 증식을 재현했다. 기존 운영 DB는 삭제하지 않았고, 보호를 위해 11435 memory를
일시 비활성화한 뒤 다음과 같이 수정했다.

- 명시 session header 최우선, exact pair-tail 우선, guarded user-hash fallback 후순위
- active 3 users/2 distinct, cold 4 users/3 distinct 및 unique-candidate/anchor 조건
- 최근 256 sessions와 session별 최신 60 completed turns만 materialized tail로 탐색
- 새 scope bootstrap은 최신 60 completed turns, 단일 transaction, 원래 turn ordinal 보존
- `session_activity`/`session_turn_tail`을 append/bootstrap과 atomic하게 유지

집중 테스트 `test_airi_memory.py` + `test_memory_runtime.py` 88개가 통과했다. 독립
100,000-turn 임시 DB 검토에서 tail은 60개로 유지됐고 pair/user lookup은
0.4–0.8ms, `_resolve_session`은 2.5–8.8ms였다. backfill, 동시 pair 완성,
session isolation, journal recall의 watermark/data-version 불변성에서 잔존 HIGH/MED는
발견되지 않았다. 이어서 `ollama-proxy` 전체 205개도 한 번 통과했다. 기존 별도
latency 8개, STT 36개, C0 evaluator 7개를 합친 최신 로컬 근거는 총 256개다.

11435는 기존 DB를 보존한 채 memory enabled/ready/embedder=true로 재기동했다.
재기동 직후 구조 migration 결과는 extraction jobs=45, messages=37,666,
snapshots=45, memory rows=252, pending total=37,666, `data_version=43`으로
이전과 동일하고, 실제 활동 scope를 나타내는 `session_activity=37`,
`session_turn_tail=2,220`, session별 tail 최대 60이다.
추출 모델은 여전히 미설정이며 평가 저장소도 비활성화다. 다음 실제 대화에서 session 수가
요청마다 증가하지 않고 한 completed turn당 journal이 약 2 rows만 증가하는지 확인하는
운영 관측은 남아 있다. AIRI 종료 후 stable `x-airi-session-id` patch를 적용하는 것이
여전히 최종 G2 isolation 조건이다.

## 15. 정적 memory cache와 10k retrieval gate — 2026-08-08

기술 참조의 semantic/context cache를 답변 캐시로 확대하지 않고, 정적 memory block
재사용으로 제한해 구현했다. 네 cache layer는 각각 TTL 600초/최대 512 entries이며
짧은 질문이 retrieval gate에서 빠지는 경우에도 `RAG_CACHE=off` 또는 runtime cache
disable이면 먼저 전부 비운다.

- semantic cache는 `source=base`, `turn_range=NULL`인 정적 canon scope에서만
  cosine `>=0.97`을 허용한다. session id, 정렬 attendees, 명시 entity names와
  `DATA_VERSION`이 모두 격리 키에 들어간다.
- conversation memory나 동적 turn range가 하나라도 있으면 semantic/context cache를
  우회한다. context cache는 embedder가 없는 fail-soft 경로에서만 top-1과 동일
  filter signature를 재사용한다. 임베딩 질의는 top-1만 같다는 이유로 graph 결과를
  재사용하지 않는다.
- 캐시에는 memory block/count/vector metadata만 들어가고 assistant response는 넣지
  않는다. 미추출 journal recall은 cache hit마다 현재 질문으로 다시 계산한다.
- 여러 `to_thread` retrieval의 dict prune/lookup/put은 짧은 `RLock` 구간으로 보호하며
  DB/embedding 작업 동안 lock을 잡지 않는다. exact result cache도 caller에게 반환한
  mutable 객체와 분리된 deep copy를 저장해 호출자 변경이 다음 hit를 오염시키지 않는다.

`test_airi_memory.py` 51개에서 near/dissimilar vector, 동적 scope 우회, session/attendee
격리, data-version/TTL/cap, cache-off, 질문별 journal, mutable result, 동시 접근을
검증했다. 독립 재현에서도 반환 객체 오염과 gate-false cache 잔존 수정 뒤 잔여
HIGH/MED는 발견되지 않았다.

`benchmark_memory_track.py --mode retrieval`을 추가해 실 DB 대신 정확히 10,000 rows인
임시 SQLite 두 개를 deterministic 2D vector와 graph fixture로 만든다. 기존 `all`에는
무거운 측정을 자동 포함하지 않으며 network/model/service를 호출하지 않고 두 임시 파일을
항상 제거한다. 재현 결과는
`bench-results/m2-retrieval-10k-2026-08-08.json`에 고정했다.

- dynamic conversation/cache bypass 20회: internal P50/P95 `47/63ms`, wall
  P50/P95 `52.643/57.517ms`, cache hit 0
- static base/canon semantic warm 20회: internal P50/P95 `31/32ms`, wall
  P50/P95 `26.142/32.744ms`, cache hit 20
- 두 경로 모두 retrieval P50 `<=150ms` gate PASS, DB row count 각각 10,000

최신 전체 회귀는 `ollama-proxy` 214개, latency monitor 8개, STT 36개, C0 evaluator
7개로 총 265개 통과다. 이 단계도 자동 extractor를 켜거나 모델을 학습하지 않는다.
추출 품질 gate와 AIRI stable session header, 실제 사용자 음성/대화 시간축 검증은 계속
후속 gate로 남는다.

## 16. Stage-B decision 계약 보정과 gated smoke — 2026-08-08

Stage B는 원문을 다시 쓰는 연산 schema가 아니라, 각 Stage-A 항목에 대한 작은 **결정**만
받도록 `decision-v2`로 고정했다. 출력은 정확히 `N`개(`minItems=maxItems=N`)의
`decisions`이며 각 원소는 `sourceItemIndex`, `action`, `candidateAlias`, `reason` 네 필드만
가진다. `action`은 `add|update|noop|supersede`이고, add는 alias/reason 모두 null,
update·noop는 기존 alias와 null reason, supersede는 기존 alias와 non-empty reason을 쓴다.
결정 compiler가 Stage-A의 kind/content/turn/graph 참조를 복사해 최종 operation으로 만들며,
index exact-once와 모든 참조/alias 검증은 계속 결정론적으로 수행한다.

`decision-v2.1`은 이 schema를 source item kind별로 분기한다. 각 index는 자신의
entity/fact/relation kind에만 들어가고, update/noop/supersede의 alias enum도 같은 kind의
candidate로 제한한다. 따라서 schema 크기는 `N=60`, `C=185`에서 약 7,359 B로 bounded이며,
compact generic prompt와 content-free schema를 유지한다. candidate builder도 `fact_subject`를
현재 scoped fact id로만 chunk query하도록 고쳤다. 무관한 300k `fact_subject` 행이 있는
재현에서 candidate build는 1.70–3.34 ms였고, 이전의 235.1 ms 전역 scan을 제거했다.

동일 옵션(`seed=42`, `max_tokens=2048`)의 2-fixture gated smoke 결과는 다음과 같다.

- `m0-extraction-exaone-v2-decision-smoke.json`: Stage-B schema 2/2, null/count 계약은
  고정됐지만 `candidate_kind` 2건으로 coverage 0/2, gate false. SHA-256
  `CA899D3B0652EC44753C7F5E7EBA9973AD2FA02E045B24AB0494CB60AC3A5A69`.
- `m0-extraction-exaone-v2-1-decision-smoke.json`: kind-scoped enum으로 `candidate_kind`는
  사라졌지만 `entity_reference_missing` 2건으로 coverage 0/2, gate false. SHA-256
  `FE0F413AFDB4C860E5A42EDE5E1D17844C6AA40EA1774EF8081C690220690B96`.
- `m0-extraction-exaone-v2b-conversation-smoke.json`: Stage-B schema/coverage 2/2,
  `update_alias`는 회복했다. 다만 `moment_signal`은 Stage-A recall 0, unexpected 3이고,
  aggregate는 Stage-A recall 0.5, unexpected 4, overall gate false다. SHA-256
  `06D16039F4E60A9A80A10D70128E7F27F60891520F9D5041165AAC2A88726FE6`.

`seed=42`와 `max_tokens=2048`은 이제 report/runtime 옵션으로 남긴다. 다만 V1은 직접 비교에
필요한 옵션이 같지 않아 인과를 주장하지 않는다. 인과 비교는 같은 옵션의 V2→V2.1 및
V2.1→V2b에만 한정한다. 최신 검증은 memory-focused **141개**, `ollama-proxy` 전체
**248개**, latency monitor **8개**, STT **36개**가 각각 통과했다.

실패한 gated smoke 뒤에는 full 7-fixture run을 수행하지 않았다. extractor는 의도적으로 OFF이며,
수정된 frozen full-fixture gate를 통과하기 전에는 운영 활성화하지 않는다. fixture별 hardcoding이나
prompt 미세조정으로 수치를 맞추지 않는다. 이번 결과는 compact generic prompt 아래의 모델 역량
증거이며, 다음 경로는 더 나은 extraction 후보 또는 향후 eval-data/LoRA 연구이지 prompt
micro-tuning이 아니다.

운영 활성화는 `verify_extraction_gate.py`와 두 launcher에서도 강제한다. extraction model을
지정하려면 local frozen fixture SHA-256, model/digest, `conversation-v2b`/`decision-v2.1`,
런처의 고정 runtime options (`temperature=0`, `num_ctx=8192`, `num_gpu=0`, `seed=42`, `max_tokens=2048`, `think=false`), prompt/schema 및 current Stage-B factory probe hash,
11434 local tag의 live 64-hex digest binding 및 11436 extractor tag 재검증; gate-only preflight 뒤 extractor 검증/기동 후 proxy를 기동하며, extraction-enabled 기존 proxy는 재사용하지 않고, 실패 cleanup은 이번 실행이 소유한 verified PID에만 적용,
전체 fixture×runs coverage와 `gate_pass=true`가 일치하는 report가 필요하다. 현재 V2b smoke는
guard 강화 전 artifact라 `EXTRACTION_GATE_CONTRACT_HASH_MISMATCH`로 거부됐고, 같은 결과를
새 계약으로 재생성해도 품질 gate를 통과하지 못한다. 기존 11435 PID와 DB는 그대로이고
11436도 시작되지 않음을 실측했다. model-empty 기본 경로에는 이 검증을 적용하지 않아 기존
OFF 기동을 유지한다.

## 17. 별도 local extractor 후보의 bounded smoke — 2026-08-08

기본 채팅 모델 `exaone-airi:2.4b`는 변경하지 않고, 자동 memory extraction 전용 후보로
공식 `qwen3:4b` Q4_K_M(2.5 GB, digest
`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`) 하나만
추가했다. RTX 3060 Ti의 당시 여유 VRAM이 약 1.8 GB였으므로 기존 방송 스택과 경쟁하지
않도록 별도 11436 Ollama를 `num_gpu=0`으로 실행했다.

첫 요청은 Ollama의 Qwen3 default thinking이 활성화된 채 실행되어 `moment_signal` Stage A가
180초 제한에서 HTTP 500으로 종료됐다. 공식 API의 `think=false`를 structured extraction의
고정 계약으로 추가하고, benchmark와 production local provider 및 gate verifier가 같은 값을
사용하도록 맞췄다. 기존 중단 증거는
`bench-results/m0-extraction-qwen3-4b-v2b-smoke-aborted.json`에 보존한다.

동일한 `conversation-v2b` / `decision-v2.1`, `temperature=0`, `num_ctx=8192`,
`seed=42`, `max_tokens=2048`, CPU 조건에서 thinking만 끈 corrected smoke는 24.118초에
첫 row를 완료했다(Stage A 16.836초, Stage B 7.281초). schema/connectivity/Stage-B coverage는
모두 1.0이었지만 `moment_signal` critical recall 0, unexpected 1,
Stage-B alias accuracy 0으로 품질 gate가 false였다. `--fail-fast`가 즉시 멈춰
`update_alias`와 full 7-fixture는 실행하지 않았다. 결과 SHA-256은
`9A0F23B6FAA8293326C59E7FC94A05A08C741B2BCD68B9B60E1989BF9B729067`이며 파일은
`bench-results/m0-extraction-qwen3-4b-v2b-nothink-smoke.json`이다.

11436은 각 실행이 소유한 PID만 확인해 종료했고 11435는 같은 PID와 상태를 유지했다.
memory extraction은 계속 OFF이며 pending journal이나 watermark를 변경하지 않았다. 이 결과를
이유로 prompt를 미세조정하거나 fixture/model 전용 예외를 추가하지 않는다.

후속 smoke가 같은 방식으로 불필요한 다음 호출을 만들지 않도록 벤치 CLI에 opt-in
`--fail-fast`를 추가했다. 기본값은 false라 기존 full measurement 동작은 바뀌지 않는다.
활성화 시 첫 row가 schema/connectivity/coverage/recall/placeholder/alias/unexpected 중 하나라도
gate 조건을 만족하지 못하면 남은 fixture와 run을 중단하고, attempted row/fixture와 제한된
reason code만 report에 남긴다. 운영 gate는 여전히 전체 fixture coverage를 요구하므로 partial
smoke report는 extraction 활성화 증거가 될 수 없다.
`think=false` request/report/verifier와 fail-fast를 포함한 집중 테스트 56개가 통과했다.

## 18. Extractor-OFF journal RAG와 backlog 관측 보강 — 2026-08-08

자동 extractor가 품질 gate에 실패해 OFF인 동안에도 long conversation이 raw tail에서 밀려난
사실을 회상할 수 있도록 active-memory retrieval gate와 unextracted-journal recall gate를
분리했다. 짧은 질문이 기존 active gate를 통과하지 않더라도, same-session에 user/assistant가
모두 있는 pending turn이 있고 질문에 stopword가 아닌 lexical token이 있으면 bounded journal
recall만 수행한다. 특정 코드명·검색어·반복 횟수로 대사를 고르는 규칙은 없고, NFC/casefold
token overlap으로 관련 turn을 찾는다. 인사·공백·stopword-only, 불완전 turn, 다른 session은
회수하지 않는다.

client가 stable session id와 현재 질문만 보내는 truncated history에서도 DB의 오래된 pending
turn을 회수한다. 반대로 client가 이미 보낸 최근 최대 60 message의 turn id는 항상 제외해 같은
대화를 prompt에 중복 삽입하지 않는다. recall은 최신 4,096 journal messages만 보고, 최대 4개
complete turn/1,200 chars를 `[Untrusted Journal Recall]` evidence block으로 넣으며 watermark,
pending, data version을 변경하지 않는다. 새 journal row는 append 시 bounded `recall_chars`를
기록한다. covering index만으로 최신 4,096개의 turn 완결성과 1,200-char pair 상한을 먼저
판별하고 통과한 pair만 원문을 읽는다. 기존 DB에서 metadata가 NULL인 row는 startup 원문
scan이나 backfill 없이 recall 대상에서 fail-closed로 제외한다.

health는 기존 선택 session의 `pending`을 호환 유지하면서 원문/session id 없이
`pending_total`, `pending_sessions`, `journal_recall_window_messages=4096`을 추가했다. 실제
서비스에는 다음 proxy 재기동부터 반영된다. memory store/runtime 집중 테스트 108개가 통과했다.

## 19. Stable session patch 적용 전 안전성 및 G5 경계 — 2026-08-08

`patch-airi-session-header.ps1`은 AIRI `ProductVersion=0.11.3.0`과 검증된 두 stock→patched
`app.asar` SHA-256 쌍에 결속한다. pristine stock
`B3433A29D2E8357A84068DFFCAD80A2A23A4D4C0F5F803764C66839C84B788AF`의 patched hash는
`0E1E4B03D132283F06F6AED743B3AC57C15BEC9C94C942097B00EA236239135C`이고, 현재 latency-patched
stock `93DFF73B984A74C71D0BB05F4DC710B8B2DDEDB2724F18D389613995AACD4891`의 patched hash는
`CB672061D4A92F36D9450E8A30FE08134D0C66BBC388E1B3C444AD4A328634C8`이다. marker와 전체
archive hash가 같은 상태를 가리킬 때만 stock/patched로 인정하며 `-Force`도 이 결속을
우회하지 않는다. 332-byte in-place write 뒤 예상 patched hash까지 확인하고, write 또는
post-verify가 실패하면 같은 offset의 stock bytes만 복원·flush한 뒤 marker를 다시 확인한다.
전체 pristine archive 자동 restore로 기존 latency patch를 지우지 않는다. hash-mismatch,
mixed-marker, rollback, idempotent 재진입을 포함한 테스트 8개가 통과했다.

현재 설치본은 session marker가 stock 1/patched 0이고 pristine backup이 일치하지만 AIRI
process 8개가 실행 중이라 적용하지 않았다. AIRI가 완전히 종료된 뒤 session-only patch를
적용하고, stock 0/patched 1 및 실제 custom-provider request header를 확인해야 한다.
proxy health에는 raw conversation id를 저장하거나 노출하지 않고 `session_header.observed`,
`present_requests`, `missing_requests`만 보고하는 process-local telemetry를 추가했다. 따라서
재기동 직후 0에서 시작해 실제 AIRI 요청 한 번으로 present count가 증가하는지 확인할 수 있다.

자발 발화는 현재 proxy request/response와 latency monitor만으로 AIRI renderer의 TTS queue에
전달할 수 없다. 내부 scheduler만 만들어 완료로 포장하지 않는다. G5에서는 AIRI source build의
`speechPipeline`/`speechRuntimeStore`에 opt-in local event transport, client ack, cooldown/dedupe,
사용자 끼어들기 cancel을 함께 추가해야 한다. 이는 Track M의 후속이며 equal-length app.asar
patch 범위를 넘는다.

## 20. C0 관계·경계·character-card 평가 확장 — 2026-08-08

C0 fixture를 10개에서 16개로 확장했다. 추가 범위는 성인 간 가벼운 플러팅과 비노골적 애정
표현을 정책 문구로 과잉 거부하지 않는지, 노골적 성행위와 미성년 성적 맥락에서는 짧고 분명한
경계를 지키는지, active character card의 이름·말투가 반영되는지, 악의적인 card 문구가 도구
진실성 제약을 덮어쓰지 못하는지다. 이는 응답을 고르는 runtime keyword 규칙이 아니라 고정
합성 평가·human-review rubric이다.

runner v0.3은 proxy와 같은 4,096-char bounded `[Active Character Card]` 블록 뒤 memory를
조립하고 fixture/model/system/runtime hash를 분리 기록한다. 현재 fixture SHA-256은
`95309E101E30009EC12A9EDB4D047E69A46AEC42C2F46DF0A8B70962225DC3BE`다. 기존 10-case 2/10
report는 역사적 v0.2 baseline이며 새 gate 결과가 아니다. stable session patch와 최신 proxy를
올린 뒤 v0.3을 한 번 실행하고 사람 검토를 붙인다. PASS 수를 올리기 위한 prompt/fixture
미세조정이나 LoRA 시작은 하지 않는다.

“Gear”라는 별도 model/card/state 계약은 현재 repository와 AIRI v0.11.3 source snapshot에서
찾지 못했다. character card와 같다고 추측하지 않고 실제 UI 설정의 정확한 이름·owner·입력
경로를 사용자 테스트에서 식별한 뒤 integration fixture를 추가한다.

## 21. Stable-session 적용 및 수정 후 실제 음성 검증 — 2026-08-08

AIRI를 정확한 설치 경로의 프로세스만 종료한 뒤 session-header patch를 적용했고,
`VerifyOnly`에서 stock marker 0/patched marker 1 및 현재 설치본의 post-session SHA-256
`CB672061D4A92F36D9450E8A30FE08134D0C66BBC388E1B3C444AD4A328634C8`을 확인했다. AIRI와
최신 proxy를 다시 시작한 뒤 실제 custom-provider 요청은 header present 1/missing 0으로
관측됐다. raw session id는 health/log에 노출하지 않는다.

첫 실제 대화에서는 local model이 마지막 `>`를 빠뜨린 `<|ACT {...}|` envelope를 반환해
2자 immediate ACK만 TTS로 전달되고 본문 음성이 사라졌다. 완료 경계를 통합해 valid/malformed
leading ACT/CALL/DELAY envelope를 wire metadata로만 처리하고 character state와 journal에는
평문만 전달하도록 수정했다. streaming/non-streaming 회귀를 추가했으며 기존 pending journal도
RAG 재주입 시 leading ACT를 제거한다.

수정 후 실제 음성 turn은 STT 557.7 ms, STT 종료→LLM 시작 541 ms, ACK playback은 STT
시작 기준 1,211 ms였다. LLM substantive content는 STT 시작 +6,049 ms에 준비됐고,
두 번째 TTS는 +6,194 ms에 시작해 +8,907 ms에 끝났으며 substantive playback은 +8,968 ms에
시작했다. TTS는 2 segments(2자 cached ACK + 35자 본문)였으므로 본문 음성 누락 회귀는
닫혔다. repeat count는 1, candidate=false라 dialogue director는 호출되지 않았다. 계층별
request/intent id가 아직 달라 KPI는 fail-closed로 비워 두되, numeric-only TTS/playback
timeline을 최대 64 events 보존해 ACK와 본문을 같은 epoch-ms 축에서 사후 구분한다.

같은 요청에서 최종 assistant journal은 35자 평문이며 ACT/CALL/DELAY가 없고, 다른 37개
session과 completed pair 공유도 0이라 cross-session merge 징후는 없었다. 다만 AIRI client의
assistant history에는 ACK/wire framing이 포함되고 canonical journal에는 없어서 최초 recent-60
adoption은 안전하게 fail-closed됐다(기존 599~600에 새 601만 추가, 6 rows/pending 6,
data_version 44 유지). 이를 특정 문구로 제거하지 않고, 동일 explicit header 안의 정확하고 서로
다른 completed user-turn anchor가 2개 이상일 때만 assistant wire mismatch를 허용하도록
보완했다. no-overlap, user mismatch, 단일/중복 anchor는 계속 거부하며 다른 session은 조회하지
않는다. 관련 집중 테스트 6개가 통과했고 proxy를 다시 시작했다. 이후 일반 대화가 들어오면
동일 세션 recent 60 complete turns가 한 transaction으로 이관되며 별도 전용 테스트 발화는
요구하지 않는다.

최종 변경 전 전체 회귀는 proxy/memory 276, latency monitor 12, STT 36개가 통과했고,
마지막 explicit-adoption 보완 뒤 관련 집중 테스트 6개와 `git diff --check`가 통과했다.
memory extraction은 frozen 품질 gate를 통과하지 않았으므로 계속 OFF이고, bounded journal RAG는
활성 상태다. commit/push는 수행하지 않았다.
