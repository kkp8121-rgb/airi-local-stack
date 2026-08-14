# AIRI 로드맵 체크리스트 (living document)

**갱신 규칙: 매 작업 배치(커밋 단위)마다 이 문서를 갱신한다.** 상태 변화가
없어도 갱신 로그에 한 줄을 남긴다. 검토 PC(Claude)·dev PC(codex) 공통
의무이며, 배치 커밋에 이 문서 갱신이 없으면 배치가 완결되지 않은 것으로
본다.

- 표기: `[x]` 완료(일자 병기) / `[~]` 진행중·부분 / `[ ]` 미착수.
  보류는 `[ ]` + (보류: 재개 조건). 완료 표시는 근거 문서 또는 커밋이
  있어야 한다.
- 축 정의(원 문서, 이 폴더): G = `AIRI-GROWTH-STRATEGY.md` §6 /
  C = `AIRI-MODEL-CUSTOMIZATION-PLAN.md` §6 /
  지연 = `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md` (v2.1)
- 실행 계획(M1~M5 상세): `진행예정/AIRI-BROADCAST-CHARACTER-PLAN-2026-08-12.md`

최종 갱신: 2026-08-15

- **2026-08-15** (dev PC, G3/B3-f 착수): moderation과 분리된
  epistemic-confidence greybox를 기본 OFF로 구현해 현재/live 정보 무근거
  단정, 무조건 동의, 문맥 없는 지시어·짧은 미확립 대상을 모델 호출 전에
  한국어 fallback으로 차단했다. 실제 한국 방송 채팅 흐름은 탬탬버린·아카네
  리제·아이네를 관찰 대상으로 정하되, 공식 권한 없는 VOD/chat scraping은
  금지했다. 권한·보존 sidecar, 모델 전달 전 명시 identity/정형 PII 패턴/
  후원 금액 삭제,
  시간순·중복·잡음 보존, content-free report와 ignored private review를 갖춘
  local replay 기반을 추가했다. 실제 캡처와 Mi:dm OFF/ON 실측, 운영 ON 채택은
  아직 완료가 아니다.
- **2026-08-14** (dev PC, B4c 인수 후속): 검토 PC 배치와 직전 로컬 자산
  통합 경계를 최신 main에서 대조했다. retired 11439 gateway의 보존 소스로
  비스트리밍·`max_tokens=1..128` 정확 계약을 확인했고, listener와 Tailscale
  Serve가 이미 비활성임을 확인했다. canonical AIRI source patch의 exact
  11435/v1 허용·11434/원격 거부 marker를 checkpoint에 추가했다. B4a 후원
  action은 `donation_name_callout_request`로 명시했으며 실제 1회 호명 강제는
  B4b 리허설 게이트로 남겼다. `AIRI_BROADCAST_CONTRACT` 기본 OFF와 사용자
  승인 전 운영 ON 금지는 유지한다.
  (`완료/AIRI-B4C-DEV-PC-FOLLOWUP-2026-08-14.md`)
- **2026-08-14** (dev PC): 분산 개발 자산을 main 기준으로 통합했다. 최종
  LLM은 사용자 확정 Mi:dm Q4 두 Ollama 태그로 단일화하고 비최종 후보
  11태그와 재다운로드 가능한 native snapshot·평가 환경, 비최종 TTS의
  venv/model cache를 제거했다. 후보별
  revision/hash/사용법/실측/실패 판단은 삭제하지 않고 tracked 문서, P0 metadata,
  source bundle, TTS 중간 patch 6종, content-free Codex session inventory로
  보존했다. ignored A/B 결과 119개와 TTS sample 9개는 main 로컬 자산에
  무충돌 합쳤다. checkpoint PASS, Python 3.12 core `1061 passed, 2 skipped,
  916 subtests passed`. main `26b0a93` push 후 Actions run `31807207795`는
  기존 결제 차단과 같은 13 job 모두 steps 0 실패로, 코드 테스트 결과가 아니다. 상세:
  `완료/AIRI-LOCAL-ASSET-CONSOLIDATION-2026-08-14.md`.
- **2026-08-14** (검토 PC): 원격 방송 채팅 A/B — 실측 시청자 채팅 38건으로
  Mi:dm Q4 vs Motif NF4를 Tailscale 원격 경로(방송 중 원격 LLM 시나리오
  근사)에서 76/76 실측. **완료 p50 357.8ms vs 9,842.6ms(27.5배)**, 형식
  규격(10~45자) 55% vs 0%, Motif는 접두사 누수·반복 루프 아티팩트 —
  **Mi:dm 유지 확정(사용자 확정)**. 공통 발견: raw 직접 호출 시 존댓말 미러링
  (35~37/38 — 방송 경로가 프록시 스타일 게이트를 경유하는지 배선 확인
  필요). 원격 서버 계약 2건은 dev PC 후속에서 해소·경계 확정: retired 평가
  gateway는 비스트리밍이며 정확한 `max_tokens` 상한은 128, 현재 배포는 없음.
  (`완료/AIRI-REMOTE-BROADCAST-CHAT-AB-2026-08-14.md`,
  픽스처·러너 `ollama-proxy/eval/broadcast_chat/`)
- **2026-08-14** (검토 PC): 브랜치 정리 실행(사용자 승인, dev PC 완료
  후) — 주석 태그 `archive/llm-backend-modes-2026-08-07`(재사용 인덱스:
  CodexBackend 하드닝·hybrid 반사 3함수·bench-llm-modes 하네스)와
  `archive/memory-layer-2026-08-07`(is_true 진위 방화벽·fake 결정론
  임베더) 생성 후 원격 브랜치 11개 삭제(병합 9 + 태그 보존된 프로토타입
  2). 잔존: main + chore/dev-pc-live-gates-2026-08-13. 커밋 유실 0
  (병합 9는 main 도달 가능, 프로토타입 2는 태그 도달 가능).
- **2026-08-14** (검토 PC): 전 브랜치(12개) 실측 감사 — 분산·유실 작업
  없음 확정. ① 병합 9종: main 조상 관계 실측(9/9), 내용은 현행 전체
  스위트로 검증됨 ② 활성 브랜치: 987 passed/1 skipped/863 subtests +
  manifest/checkpoint PASS ③ 옛 프로토타입 2종은 worktree 체크아웃 후
  당시 테스트 전수 재실행(llm-backend-modes 87 항목·memory-layer 169
  항목 — 당시 주장 정확 재현, 실패 0) + 기술 단위 main 대조:
  llm-backend-modes 16기술(재구축 6·부분 5·미반영 5 — hybrid 반사
  레이스·모드 벤치 하네스·CodexBackend 하드닝·클라우드 감정 태그),
  memory-layer 30기술(재구축 21·부분 3·미반영 6 — is_true 진위
  방화벽·fake 결정론 임베더 등). 두 감사 모두 "태그 보존 후 삭제 이의
  없음". 참조 리서치 문서의 stale `AIRI_LLM_MODE` 문장 교정(현행 스위치
  병기 + 반사 1.36s 재측정 단서). **백로그 승격 2건**: is_true 쿼리 레벨
  진위 필터(I2 시청자 기억 — 시청자 주장은 신뢰 불가 입력), 의미 보존
  결정론 임베더(검색 랭킹 회귀 게이트 픽스처 — 현행 테스트 임베더는
  상수 벡터라 랭킹 회귀 검출 불가). 추가 발견: 검색 캡·가중치
  (CAP_*/ALPHA/BETA/LAMBDA)가 모듈 상수 하드코딩 — 상수 테이블화 원칙
  위반, 튜닝 착수 시 선행 정리 대상.
- **2026-08-14** (검토 PC): 저스트챗 방송 방식 관찰 연구 완료 — 사용자
  지정 4인(시구레 우이·탬탬버린·아이네·아카네 리제)의 "혼자 저챗 좋아요
  최다" 영상 트랜스크립트를 타이밍 포함 정량+정성 분석. 핵심: 발화 이중
  레이어(≤2초 조각 40~60% + 명분 있는 긴 블록), 낭독→응답 중앙값
  1.06~1.2초(한 단위 원자화 필요), 무선언 무음 상한 10~27초, 발화
  점유율은 오디오 베드 유무에 종속(34~92%), 화제 전환 엔진은 블록 선언이
  아니라 채팅. 기존 설계 수정 지점 7건과 파라미터 후보 도출.
  M4에 B4c(방송 발화 계약) 등록.
  (`참조/AIRI-BROADCAST-OBSERVATION-STUDY-2026-08-14.md`)
- **2026-08-13 (all eligible local LLM candidates — immediate AIRI A/B):**
  사용자는 명확한 허용 라이선스 후보와 평가 전용 조건부 Motif 예외를 모두
  Mi:dm에 적용한 것과 같은 AIRI 평가 경로로 지금 비교하도록 우선순위를
  변경했다. 대상은
  Mi:dm 기준선 + Motif 2.6B v1.1-LC + Ministral 3 3B + Qwen3 4B +
  Phi-4-mini 3.8B + Granite 3.3 2B다. 각 모델은 공식 chat template,
  system-role 처리, thinking, EOS/stop, sampling, context, dtype/attention,
  quantization과 engine 지원을 exact revision의 usage manifest로 먼저 고정한다.
  official-native와 AIRI-common profile을 분리해 raw 16-case×3, context
  4압력×3, persona 20-case, proxy 120-turn, 한국어 방송 대화 인간 검수,
  full-stack n=10을 수행한다. P0 provenance/P1 8 GB에서 멈춘 모델도 명시적
  BLOCKED/UNRUNNABLE 결과로 남기며 다른 후보는 계속한다. 운영 Mi:dm은 최종
  사용자 재승인까지 유지한다. 상세 SSoT:
  `진행예정/AIRI-LOCAL-LLM-CANDIDATE-AB-PLAN-2026-08-13.md`.
- **2026-08-13 (Motif evaluation-candidate decision / next-session handoff):**
  사용자는 `Motif-Technologies/Motif-2.6b-v1.1-LC`를 라이선스 불명확성을
  기록한 상태에서 Mi:dm과 비교할 정식 실측 후보로 승격했다. 이는 운영 기본
  모델 교체나 공개 방송 법률 승인 완료가 아니다. v1.1-LC metadata의
  `license: mit`와 `license_name: motif-license`/삭제된 LICENSE 이력, 기반
  Motif-2.6B의 별도 Agreement를 함께 보존한다. 실제 채택 시 채널 소개와 방송
  설명란에 `Built with Motif`를 표시하고 적용 license/Notice 의무를 따른다.
  mutable remote code를 실행하지 않으며 pinned revision 코드 감사 → 8 GB 4-bit
  실행 prove-or-stop → 동일 AIRI fixture Mi:dm A/B 순으로 진행한다. EXAONE은
  NC 라이선스 때문에 공개·수익 방송 승격 후보에서 제외하고 과거 증거/호환
  이력만 보존한다. 근거와 다음 순서는
  `진행중/AIRI-NEXT-SESSION-HANDOFF-2026-08-13.md`에 고정했다.
- **2026-08-13 (B3-c/B3-d evidence completion):** B3-c's local deterministic
  input prefilter and local B1 downstream spine are implemented, default OFF,
  and independently reviewed PASS. It blocks the categories
  `persona_takeover`, `profanity`, `sexual_explicit`, `targeted_harassment`, and
  `privacy` before upstream; it has bounded normalization/obfuscation and PII
  patterns, protocol variants, proactive exemption, exact loopback endpoint,
  and fail-closed launch health/policy-digest checks. Model-facing Node text is
  deliberately `[YouTube] ${text}`: public `displayName` stays only in the
  separate viewer observation. This is not a live YouTube/OAuth/provider
  adapter, nor a multilingual semantic classifier. Japanese/Chinese and
  unvalidated Latin spans fail closed as `unsupported_language`; only 14 exact
  benign product/acronym tokens are accepted inside Korean. Novel euphemisms
  and other languages remain rehearsal/human/model-gate work. Output moderation
  remains default OFF. Focused evidence: Python input+launcher+eval 43 passed
  (later input-only 19), chat-ingress 47, sender 32; latest combined Node 79.
  Final local substitute for billing-blocked Actions: Python 3.12 full suite
  911 passed/1 skipped/863 subtests/7 warnings in 53.13 s; checkpoint (including
  manifest and source-ASAR deployment/preflight contracts) PASS; both launcher
  parsers and diff checks PASS.
- **2026-08-13 (B3-c loopback probe):**
  `evidence/AIRI-B3C-INPUT-SCREENING-LIVE-PROBE-2026-08-13.json` records an
  unchanged installed ASAR (1,356,257,019 B, `1b68ae...b88b0`) and seven AIRI
  processes. The current proxy source was ON and ready with policy SHA
  `67739c...b9d7a`; all five categories blocked and a benign Korean YouTube
  message was allowed twice, with counters inspected=12/allowed=2/blocked=10.
  Output moderation and extraction were OFF and the STT listener was absent.
  This proves loopback policy only. A fresh installed UI/TTS recheck stopped
  before model/TTS because cleanup had removed sender SDK `@moeru/std`; the
  installed ASAR remained untouched. Earlier five-category TTS proof is
  historical, not current-policy proof; B3-e remains pending installed UI badge
  + TTS/current-policy rehearsal.
- **2026-08-13 (B3-d corpus/direct prefilter):** the content-free direct local
  Ollama 20-case exact ko/en/ja/zh corpus covers benign, direct jailbreak,
  indirect injection, profanity-harassment, and sexual explicit cases. Report
  `ollama-proxy/eval/results/airi-persona-jailbreak-marker-midm-2026-08-13.json`
  is 14,395 B SHA-256
  `9308b0c1527eaf42b58496bd3c36520feabeaa38c70623139981357cb65509c8`, with
  Mi:dm digest `92a9...485f`: structural 20/20 PASS, exact standalone marker
  contract 5/20 PASS -> overall FAIL. P50/P95/max 211.371/809.552/928.064 ms.
  It makes no semantic safety, proxy, Electron, UI, or TTS claim. B3-d
  corpus/direct-prefilter evidence is complete, but installed red-team execution
  remains pending, so the broadcast safety gate is not complete.

- **2026-08-13** (검토 PC): dev PC 브랜치 독립 검토 — 코드·증거 차단 사유
  없음(승격 오인·실기/합성 혼동·개인정보 전건 반증 실패). blocker 보완 3건:
  streamlist-quota의 ① provider발 에러 sanitize 우회 차단(module-private
  brand) ② reconnect 자연 종료의 connection_cap 오분류 수정 ③ 발생한
  연결·폐기 응답 카운트 누락 수정(discardedResponses 신설 — 쿼터 귀속
  과대평가 편향 제거). 신규 테스트 5종(수정 전 재현 FAIL 실측), chat-ingress
  32→37, checkpoint에 최소 테스트 수 가드 추가(빈 glob 조용한 초록 방지).
  문서 정합 6건(smoke 기록 복원·B3-c/d/e 미완료 게이트 등록·push 시점
  한정). 전체 900/1/738 + checkpoint/manifest PASS. CI는 Actions 결제 차단
  으로 실행 불가 — 로컬 전체 검증으로 대체(사용자 결제 확인 대기).
- **2026-08-13** (review PC handoff): 검토 브랜치
  `chore/dev-pc-live-gates-2026-08-13`의 완료·미완료와 실제 설치 AIRI 시험 경계를
  `진행중/AIRI-REVIEW-PC-HANDOFF-2026-08-13.md`에 고정했다. 실제 송출을 빼도
  extraction 품질/활성 락, 인간 검수, runtime wiring, ASAR 설치 검증 등이 남는다.
  push run `31683115216`은 13 jobs 모두 runner_id 0/steps 0으로 코드 실행 전
  실패했다.

- **2026-08-13** (local cleanup after blocked extraction/broadcast work): The goal
  was blocked by absent explicit Cloud/YouTube transmission and spend approvals,
  and by all extraction candidates failing; it was not blocked by context
  exhaustion. On the user's cleanup request, removed failed Ollama tags
  `ministral-3:3b-instruct-2512-q4_K_M`, `phi4-mini:3.8b-q4_K_M`, and
  `granite3.3:2b`: 13 unique unshared blobs / 6.511 GiB. Also removed old ignored
  `.codex` generated ASAR/runtime-package/patch-check directories and three
  obsolete ignored `airi_docs` ASARs (37.882 GiB), generated staging
  `node_modules`/`.cache`/`.turbo`/`dist`/`out` (2.167 GiB; empty `node_modules`
  directories may remain), Python caches/egg-info
  (20.07 MiB), and a clean registered audit worktree (18.43 MiB). Approximate C:
  free space changed 12.41 -> 58.99 GiB (~46.58 GiB). Preserved authoritative git
  worktrees, staging source at clean HEAD `bf173f2d`, `verify` and `verify2`
  trees, Python 3.12 audit venv, runtime DB/logs, patches/evidence JSON, installed AIRI, and
  production services. Deleted data is not recycle-bin recoverable; models,
  dependencies, builds, and worktrees are reproducible, and evidence reports
  remain. No push at the time of this batch (the branch was pushed afterwards
  for review handoff). Details:
  `완료/AIRI-LOCAL-TEMP-AND-FAILED-MODEL-CLEANUP-2026-08-13.md`.

- **2026-08-13** (dev PC, 복원된 기록 — `31ff0e6`이 실수로 삭제한 항목):
  신규 공개 라이선스 추출 후보 3종 단일 fixture smoke — Ministral 3 3B
  recall 0.0 / Phi-4-mini 3.8B recall 0.0 / Granite 3.3 2B critical_recall
  0.5, 전부 FAIL(fail-fast, full gate 미실행). 추출 OFF 유지.
  (`완료/AIRI-NEW-LOCAL-EXTRACTION-CANDIDATE-SMOKES-2026-08-13.md`)

---

## 사용자 결정 (2026-08-12 5건 처리)

- [x] 결정 1 — 관계 축: AI 단독형 + 메타 서사("사장님") 채택 — 2026-08-12
  (호칭은 당초 "주인님"에서 같은 날 "사장님"으로 변경)
- [~] 결정 2 — 방송 중 클라우드 LLM: 조건부 — dev PC 실측 2종
  (B0-3 x264 완료, cloud streaming live TTFT는 자격증명·외부 승인 대기) 후 재결정
- [x] 결정 3 — 캐릭터 방향 확정: 이름 AIRI·호칭 “사장님”·시그니처 인사
  (메타 개그형)·클로징(메타 개그형) 유지. 정식 팬덤명은 유보하고 일반 호칭
  “시청자들”만 사용. T-05는 126번을 예비 후보로 보존하되 낭독조·감정 부족
  때문에 현행 일본어 참조 음성을 유지 — 2026-08-12
- [x] 결정 4 — 첫 방송 목표 시점: 조건 기반(M3 달성 → 비공개 리허설 통과 →
  데뷔), 날짜 고정 없음 — 2026-08-12
- [x] 결정 5 — 지연 목표: 재정의 제안(첫 반응 ≤1.5s / 본답변 ≤2.5s)
  기각 — §12 원문 유지 확정 — 2026-08-12
- [x] 결정 6 — 로컬 LLM: Mi:dm 확정 — 2026-08-14 (사용자 확정). 근거:
  원격 방송 채팅 A/B 실측 — 완료 p50 357.8ms vs 9,842.6ms(27.5배), 형식
  규격(10~45자) 55% vs 0%, Motif는 접두사 누수·반복 루프 아티팩트
  (`완료/AIRI-REMOTE-BROADCAST-CHAT-AB-2026-08-14.md`)

## G축 — 성장 로드맵

- [x] **G0. 작업 트리 재조정** — 2026-08-10 (`완료/AIRI-INDEPENDENT-REVIEW-2026-08-10.md`, `완료/AIRI-STABILITY-CHECKPOINT-2026-08-10.md`)
- [~] **G1. 캐릭터 루프**
  - [x] 세션 상태 필드 구현 (`character_state.py`, G1 최소 상태와 ≈1:1 — 2026-08-10 검토 확인)
  - [x] 상태 프롬프트 주입의 prompt-injection/privacy hardening — 2026-08-13
  - [ ] evaluator 재활성 (보류: 품질 평가 재개 조건 확정 후; 방송 계획 C2)
- [~] **G2. 장기 기억**
  - [x] 저장·검색·저널 회상 운영 — 2026-08-09 라이브 스모크, KURE fp16 2026-08-11
  - [x] 추출 승격 루프 코드 + 게이트 프로파일 strict/balanced — 2026-08-12 (`932eae6`)
  - [x] MEM-04 SQLite WAL·busy_timeout — 2026-08-12 (`932eae6`)
  - [x] 검색 bounded admission + retrieval/store/extraction shutdown drain —
    retrieval에는 기본 8의 bounded admission을 적용했고, retrieval 및
    store/extraction `to_thread`를 추적해 shutdown drain에 포함했다. 검토 PC
    `22a6add`, main `c916f48`; 전체 900 passed / checkpoint PASS / lifecycle
    10회 안정 — 2026-08-13
    (`완료/AIRI-MEMORY-RETRIEVAL-SHUTDOWN-DRAIN-2026-08-13.md` §후속 반영).
    native store 호출은 협력 취소 지점이 없어 최악 2×flush window 순수 대기 및
    장기 `SQLITE_BUSY`에서 deadline 뒤 tracked worker 잔류 가능성이 알려진 한계다.
  - [~] 게이트 리포트 생산 → 추출 발효 (Mi:dm balanced, Qwen3.5·Granite 4.0·
    Kanana smoke, Gemma3 full 모두 FAIL; Ministral 3 3B·Phi-4-mini 3.8B·
    Granite 3.3 2B 단일 fixture smoke도 전부 FAIL; 독립 verifier 거부, 추출
    off 유지 — 통과 후보 미확정,
    `완료/AIRI-NEW-EXTRACTION-CANDIDATE-GATE-2026-08-12.md`,
    `완료/AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md`,
    `완료/AIRI-NEW-LOCAL-EXTRACTION-CANDIDATE-SMOKES-2026-08-13.md`)
  - [ ] MEM-04 활성 추출 락 경합 실측 (코드 완료; 통과 extractor와
    `extraction_enabled=true` 이후 Stage B commit↔foreground 겹침 증거 필요)
  - [ ] I2 시청자 기억 시스템 (M2)
- [~] **G3. 평가·데이터 플라이휠**
  - [x] 전 로컬 LLM 후보 동일 AIRI A/B — 완료 후 사용자가 Mi:dm Q4를
    최종 운영 모델로 확정. 비최종 후보 weight는 2026-08-14 정리했고 pinned
    manifest·실패/실측 기록만 보존한다. 후보 A/B를 다음 작업으로 다시 실행하지
    않는다. (`진행예정/AIRI-LOCAL-LLM-CANDIDATE-AB-PLAN-2026-08-13.md`,
    `완료/AIRI-LOCAL-ASSET-CONSOLIDATION-2026-08-14.md`)
  - [x] 오프라인 eval 하네스·120턴 A/B — 2026-08-12 (`진행중/AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md`)
  - [x] 장문 context·memory·card 합성 A/B 실측 — EXAONE exact 3/12,
    Mi:dm 0/12로 양 모델 FAIL — 2026-08-12
    (`완료/AIRI-LONG-CONTEXT-MEMORY-CARD-AB-2026-08-12.md`)
  - [x] 장문 context budget·card/정정 표현 및 고정 4압력×3회 production 회귀 측정 완료 — **FAIL**
    (v2: 7개 필드 중 6개 12/12, `dialogue_marker` 0/12가 `silver-fern` 복사; 두 continuity color는 v1보다 개선됐으나 dialogue-vs-memory 모델 한계. 운영 기본값 2048·extraction OFF 유지)
  - [x] eval provenance 해소 (수집 데이터를 승격 근거로 사용 가능) — 2026-08-12 (`932eae6`)
  - [~] epistemic-confidence gate — 2026-08-15 greybox 구현. output
    moderation과 독립, env 기본 OFF, 무근거 현재/live 상태·무조건 동의·문맥
    없는 지시어/짧은 미확립 대상을 pre-publication 한국어 fallback으로 처리하고
    content-free health counter를 제공한다. 실제 승인 채팅 Mi:dm OFF/ON 비교와
    운영 ON 채택은 미완료이며 사용자 확인 전 자동 승격하지 않는다.
  - [~] 승인 실제 한국 방송 채팅 흐름 replay — 권한 sidecar와 hash-bound
    local provenance artifact,
    명시 identity·정형 PII 패턴·후원 금액 pre-model 삭제, 순서·상대 시간·
    중복·잡음 보존,
    content-free report/ignored private review 기반 구현. 탬탬버린·아카네 리제·
    아이네 실제 캡처는 방송인/플랫폼 공식 권한 대기이며 무단 scraping하지 않는다.
    상세: `진행예정/AIRI-KOREAN-LIVE-CHAT-REPLAY-PLAN-2026-08-15.md`.
  - [ ] 인간 검수 100건 수집 (dev PC)
  - [ ] 16케이스 자동 게이트 PASS (현재 양 모델 FAIL)
- [ ] **G4. 성격 파인튜닝 (QLoRA)** — (보류: G3 인간 검수 데이터 축적)
  - [x] 학습 스택 핀 (`training/` transformers+peft+bitsandbytes) — 2026-08-11 확인
  - [ ] 스타일 데이터셋 승격 재개 (`보류/AIRI-STYLE-PROMOTION-CHECKPOINT-2026-08-10.md`)
- [~] **G5. 자발 행동·방송 디렉터**
  - [x] 설계 (방송 계획 §B4 20분 블록 상태기계 = G5 실체화) — 2026-08-12
  - [~] B4a 오프라인 방송 디렉터 기반 — 기본 OFF/inert, caller monotonic `nowMs`,
    20분×6 블록·질문/침묵/후원/토픽 lease·pause/kill 계약과 집중 테스트 17 PASS,
    독립 최종 검토 PASS — 2026-08-13
    (`완료/AIRI-B4A-BROADCAST-DIRECTOR-FOUNDATION-2026-08-13.md`). 실제 런타임,
    AIRI/TTS/OBS, YouTube/OAuth·쿼터, 외부 killswitch·모더레이션 및 2시간 실기는 미증명.
    2026-08-14 후속에서 후원 즉시 action을 명시적
    `donation_name_callout_request`로 바꾸고 broadcast-director 전체 24/24
    PASS; 이름 1회 실제 호명은 B4b adapter 리허설 대기.
  - [x] B4a B1 screened event 우선순위 정책 — strict B1 shape/ID/Unicode code point/timestamp·descriptor snapshot 검증, 개인정보 비보존 수동 문자열 매처, 질문>화제 확장>진심 리액션>응원>긍정 fallback. 로컬 broadcast 집중 시험 24/24 PASS, 독립 combined ingress/policy/director 검토 36/36 PASS — 2026-08-13 (`완료/AIRI-B4A-CHAT-PRIORITY-POLICY-2026-08-13.md`). B4a/G5/M4는 partial이다.
  - [~] B4c 방송 발화 계약 — 수신자 지향 구조(인용→반응 2박자·문체
    스위칭·태그의문·호명 정책) + 디렉터 상태별 가변 길이 + 낭독·응답
    원자화(응답 개시 ≤1.3초). 실증 근거:
    `참조/AIRI-BROADCAST-OBSERVATION-STUDY-2026-08-14.md`(4인 트랜스크립트
    실측 — 공통 패턴 10종·설계 차이표·파라미터 후보). 파라미터 확정은
    사용자 확인 경유. 계약 greybox 구현 완료 2026-08-14 (`f0ff26e` —
    `ollama-proxy/broadcast_contract.py` env 게이트 `AIRI_BROADCAST_CONTRACT`
    기본 OFF·계약 블록 369자·관찰 연구 §6 후보값 상수 테이블·21 tests
    PASS·OFF 시 프롬프트 바이트 동일). 전/후 실측 완료 2026-08-14 —
    단발(38픽스처) 방송통과 0%→50%·반말 8%→66%·존댓말 위반 35→13건,
    멀티턴(2×24턴)은 첫 턴 앵커 고정 관측(계약 단독으론 불충분 —
    proxy 스타일 게이트 이중 배선 필요), 흐름 마커 콜백 창안 1/1·
    창밖 0/1(I2 시청자 기억 필요성 실증)
    (`완료/AIRI-B4C-CONTRACT-AB-2026-08-14.md`). 남은 것: 파라미터
    확정·운영 ON 채택(사용자 확인 경유). 후원 호명은 B4c 문구가 아니라
    B4a explicit action으로 정리했으며 B4b 실제 호명 실증은 남는다.
  - [~] 스타일 게이트 방송 경로 배선 확인 — 코드 실측 완료 2026-08-14: 게이트는
    치환(`normalize_korean_register`)+미해결 존댓말 문장 드롭(fail-closed)이며
    proxy `chat/completions` 출력 전부에 적용, 우회 플래그 없음. 레포 내 방송
    체인은 AIRI 앱 WS 전달에서 끊김(B4a는 라이브 어댑터 없음) — AIRI 앱
    provider 설정(proxy 11435) 의존이라 라이브 실증은 B1b 실제 AIRI 주입
    착수 시 확인 필요. 원격 A/B 존댓말 35/38은 벤치마크가 raw 서버(11439)를
    직접 호출한 설계 차이로 설명됨(방송 경로 우회 아님).
    - [x] source/checkpoint: canonical AIRI patch는 exact loopback `11435/v1`만
      허용하고 `11434`, 잘못된 `/api`, 원격 HTTPS provider를 거부. 의미 marker를
      `test-patch-manifest.ps1`에 고정 — 2026-08-14
    - [ ] B1b live: screened event→실제 AIRI 모델 요청→11435 proxy→스타일
      치환/미해결 문장 drop→public wire/TTS를 같은 turn으로 증명. 현재
      approved `broadcast_line` 직접 반환 분기는 모델 출력 게이트 실증이 아님.
      계약 ON 증거는 별도 사용자 승인 후에만 추가.
  - [x] 멀티턴 방송 리허설 평가 (오프라인 흐름 축) — 구축 완료 2026-08-14
    (`88700ac` — 시나리오 2×24턴·콜백 창 안/밖 분리·여론 집계·후원 호명
    스코핑·politeness_drift·34 tests·CI evaluations shard 등록). 원격 Mi:dm
    실측 완료 2026-08-14(96턴 실패 0, 첫 턴 앵커 고정·콜백 창밖 미스
    포착 — 평가 설계 목적 달성). 정기 회귀 편입은 후속.
  - [ ] B4b 어댑터·승인 비공개 리허설 (보류: B1b 외부 자격증명·쿼터 실측·운영 승인;
    STT OFF/deferred 유지)
- [ ] **G6. 화면·게임·채팅 에이전트** (G5 이후)

## C축 — 모델 커스터마이징 게이트

- [~] **C0. 기준선·평가 세트 고정**
  - [x] 16케이스 fixture·A/B 하네스 고정 — 2026-08-12
  - [~] 실제 채팅 구조 기반 합성 replay fixture — 기반과 독립 작성 synthetic
    smoke fixture 완료; 승인 실제 캡처 분석 뒤 패턴 회귀 세트 확정 필요
  - [ ] 인간 검수 평가 세트 고정 (G3와 동일 병목)
- [ ] **C1. 성격 SFT LoRA** — (보류: G4와 동일 조건)
  - [x] 캐릭터 헌법 초안 (학습 목표 정의의 입력) — 2026-08-12 (`7dc4e76`)
  - [ ] 헌법 확정 (관계·인사·클로징·시청자 일반 호칭·T-05 운영 방향 반영
    완료 — 남은 것: 인간 검수)
- [ ] **C2. 선호 학습** (C1 이후)
- [ ] **C3. 선택적 제어 토큰** (ACT 계약 Mi:dm 재측정 필요)
- [ ] **C4. 구조 프루닝 연구**
- [ ] **C5. Ollama 배포**
  - [x] digest pin 배포 — 2026-08-12 (dev PC 실측 Mi:dm digest를 운영 런처
    기본 pin으로 고정, 명시 override·EXAONE unpinned 롤백 유지)

## 지연 마스터 플랜 (v2.1)

- [x] 첫 반응 ≤1.5s — ACK 수백 ms (2026-08-12 실측 문서)
- [~] 본답변 지연 — §12 원문 목표(뉴로사마급) 기준으로 계속 추구(결정 5,
  2026-08-12 재정의 제안 기각 확정). 텍스트 경로 P50 1,963ms 달성
  (`완료/AIRI-ELECTRON-TEXT-TTS-MEASUREMENT-2026-08-12.md`), 실제 마이크
  음성 전체 체인은 미실측. TTS progressive chunk 재생은 이미 설치본에서 증명됐고,
  32 kHz source→AudioContext output-rate 보정과 lossless bounded backpressure도
  source 구현·빌드 검증을 완료했다. 고정 source의 설치 후보 ASAR 생성과
  digest·구조·unpacked 호환성 검증도 완료했다. 남은 활성 목표는 issue #2의
  명시적 설치 권한 뒤 안전 백업·채택 및 실제 duration/pitch·text→render 회귀다.
- [x] matched Electron 모델 A/B — 같은 설치 ASAR·TTS warm, 교차 블록
  모델별 n=10. Mi:dm first substantive render P50/P95 1,501.5/2,597.2ms,
  EXAONE 1,752.5/3,233.0ms — 2026-08-12
  (`완료/AIRI-INSTALLED-MODEL-RENDER-AB-2026-08-12.md`)
- [ ] 실제 마이크 음성 체인 P50/P95 실측 (보류: 사용자 요청. “마이크 테스트
  시작” 요청 시 dev PC의 `마이크(USB Audio Device)`로 재개)
- [x] 상단 대시보드 substantive KPI 정합성 — raw `playback.start` 대신
  `kpi.substantive_playback_start`만으로 newest-five/P50/P95/worst/pass를
  집계. non-synthetic cloud-search와 explicit STT/LLM/playback 상관 및
  시간 순서를 엄격히 요구하고 raw scalar는 진단용 유지 — 2026-08-13
  (`완료/AIRI-LATENCY-DASHBOARD-SUBSTANTIVE-KPI-2026-08-13.md`; 이는
  live mic/runtime 실측 또는 물리적 5-turn gate 완료가 아님)
- [x] §12 완료 기준 공식 개정 (결정 5) — 2026-08-12 결정 완료: 재정의
  제안 기각, 원문 유지 확정

## 방송 실행 (M1~M5)

- [~] **M1** (B0 실측 ∥ I1 추출 ∥ C1 헌법)
  - [~] B0-1 `liveChatMessages.streamList` offline quota measurement core — injected
    transport-only, content-free, bounded duration/messages/responses/connections,
    monotonic timings, transient resume token, abort/cleanup; focused 20 PASS, all
    chat-ingress 47 PASS, checkpoint/review PASS. **Live is NOT COMPLETE** pending
    explicit API key/OAuth/quota/project/test-broadcast approval and isolated manual
    Cloud Console before/after snapshots for idle/message/reconnect. Official quota docs
    do not state exact streamList charging; no cost inference (`완료/AIRI-B0-1-STREAMLIST-QUOTA-MEASUREMENT-CORE-2026-08-13.md`)
  - [x] B0-2 VRAM 3단계 델타 — 6,084/6,131/6,289MiB, +47/+158MiB(+205), 최소 여유 1,736MiB, NVENC H.264 1080p60 — 2026-08-12
  - [x] B0-3 5600X x264 1080p30 veryfast — 설치 Electron 실제 턴 CPU 평균 44.8%/최대 70%/최소 headroom 30%, 정상 5,346 frames — 2026-08-12 (`완료/AIRI-B0-RESOURCE-MEASUREMENT-2026-08-12.md`)
  - [x] I1 추출 활성화 코드 — 2026-08-12 (`932eae6`, 발효는 G2 리포트 대기)
  - [x] C1 헌법 초안·사용자 방향 결정 반영 — 2026-08-12
    (헌법 최종 승인은 인간 검수 후이며 C축 C1과 동일 병목)
- [~] **M2** (B1 채팅 브리지 ∥ C2 루프 배선 ∥ I2 시청자 기억)
  - [x] B1a offline transport-neutral chat-ingress core — strict YouTube candidate admission, HMAC pseudonyms, bounded FIFO screening/delivery, established AIRI envelope (`data.text` only; viewer sidecar 없음), Node contract tests; 기본 OFF, B1 persistence 없음 — 2026-08-13
  - [x] I2a viewer-memory foundation — separate opt-in SQLite, strict `yt:v1`/`viewer:v1`/`broadcast:v1` HMAC pseudonyms, content-free B1 observation boundary, manual capped tiers, bounded explicit facts, retention/deletion, count-only donations, and untrusted callback candidates; no runtime wiring or AIRI injection. I2 remains partial pending an authorized next-broadcast callback smoke — 2026-08-13 (`완료/AIRI-I2A-VIEWER-MEMORY-FOUNDATION-2026-08-13.md`)
  - [ ] B1b live adapter/quota/OAuth 및 실제 AIRI 주입 (보류: 외부 YouTube 자격증명·쿼터 실측·운영 승인)
- [~] **M3** (B2 송출 + B3 안전)
  - [x] B3 모더레이션 게이트 코드 (사전 113항목+패턴 7, 기본 off) — 2026-08-12 (`932eae6`)
  - [x] B3 배선 3종 — TTS 폴백 7/7·런처 env·Electron "필터당함" 배지,
    신규 3층 source test/typecheck/build 및 설치본 실제 차단 턴 확인 — 2026-08-12 (`완료/AIRI-B3-ELECTRON-MODERATION-VERIFICATION-2026-08-12.md`)
  - [x] B3-c deterministic local input prefilter + local B1 downstream spine —
    default OFF; five fixed categories, bounded normalization/obfuscation·PII,
    loopback/protocol variants/proactive exemption, pre-upstream historical-entry
    block, fail-closed health/policy digest; independent review PASS. This is not
    multilingual semantic classification: ja/zh and unvalidated Latin fail closed
    as `unsupported_language`, and only 14 exact benign Korean-embedded tokens
    are permitted. No live YouTube/OAuth/provider adapter; output moderation OFF.
  - [~] B3-d exact marker corpus + direct local prefilter evidence — 20-case
    ko/en/ja/zh content-free report structural 20/20 PASS, standalone marker 5/20
    PASS -> overall FAIL; installed Electron red-team remains pending and this is
    not semantic-safety/proxy/UI/TTS proof
  - [ ] B3-e category별(욕설·음란성 등) 설치 UI/TTS 차단 반응 실기 — 현재는
    dictionary/unit + generic match-all 배선 확인만. output moderation 기본 OFF
  - [~] B3-f 실제 한국 방송 채팅 흐름/확신도 replay — local privacy·권한·
    replay 기반 완료, 세 채널 승인 캡처·Mi:dm 대응 검수·설치 Electron/B1b
    종단 실증 대기. 실제 원문은 git/학습 데이터에 넣지 않는다.
  - [ ] B2 송출 (OBS Browser Source + App Audio Capture — 결정 2 이후)
- [~] **M4** (B4 방송 디렉터 + C3/C4 ∥ I3 주제 풀)
  - [~] B4a 기반 구현 — 기본 OFF/inert; simulation-only 집중 테스트 17 PASS·독립 최종 검토 PASS.
    B4b 런타임 어댑터와 실제 비공개 리허설은 미착수
    (`완료/AIRI-B4A-BROADCAST-DIRECTOR-FOUNDATION-2026-08-13.md`)
- [ ] **M5** (리허설 → 데뷔 → I4 플라이휠)

## 모델 SSoT 게이트 (전환 고정 선언의 전제)

- [x] model SSoT 강제 (`resolve_chat_model`, EXAONE 하드코딩 0건) — 2026-08-12 (`932eae6`)
- [x] eval provenance — 2026-08-12 (`932eae6`)
- [x] ACK metadata 교정 — 2026-08-12 (`932eae6`)
- [x] digest pin 코드 (opt-in) — 2026-08-12 (`932eae6`)
- [x] SSoT 실기 검증 + digest 실값 pin 고정 — 2026-08-12
  (`완료/AIRI-DEV-PC-SSOT-VERIFICATION-2026-08-12.md`)
- [x] 장문 context·memory·card 비교 측정 — 2026-08-12 (양 모델 FAIL,
  개선 후 회귀 필요)
- [x] context window SSoT·fail-closed·prompt-budget 관측성 — 2026-08-13
  (측정/관측 완료, 4096 품질 승격 아님;
  `완료/AIRI-CONTEXT-WINDOW-SSOT-AND-4096-TRIAGE-2026-08-13.md`)
- [ ] 인간 검수 100건 (G3와 공유)

---

## 갱신 로그 (최신이 위)

- **2026-08-15** (dev PC, G3/B3-f 실제 채팅 평가 기반): default-OFF
  epistemic-confidence pre-publication gate와 승인/보존 fail-closed local chat
  replay를 구현했다. replay는 실제 채팅의 명시 identity·정형 PII 패턴·후원
  금액을 모델 전달
  전에 제거하고 순서·상대 시간·중복·잡음을 보존하며, 일반 report에는 원문과
  응답 원문을 남기지 않는다. 탬탬버린·아카네 리제·아이네의 실제 로그는
  치지직/SOOP 공식 권한 없이는 수집하지 않으며, 승인 캡처·Mi:dm OFF/ON 실측·
  운영 ON 채택은 후속이다. 계획:
  `진행예정/AIRI-KOREAN-LIVE-CHAT-REPLAY-PLAN-2026-08-15.md`.
- **2026-08-14** (dev PC, B4c 인수 후속): 직전 자산 통합의
  `archived_not_deployed` 경계를 보존한 채 검토 PC 세 후속을 정리했다.
  retired 11439 gateway 소스 계약은 비스트리밍·`max_tokens=1..128`로 확정,
  현행 listener/Tailscale Serve 없음. canonical AIRI source patch의 exact
  11435/v1 allow와 11434/원격 reject를 checkpoint 의미 marker로 고정했다.
  B4a 후원 action은 `donation_name_callout_request`로 명시하고 missing/unsafe
  이름을 fail-closed했다. B1b style-gate 종단 실증과 B4b 이름 1회 실제 호명은
  미완료이며, 계약 ON·파라미터 채택은 사용자 승인 전 자동 승격하지 않는다.
  로컬 broadcast-director 24/24, B4c+멀티턴 55/55, current checkpoint PASS;
  CI billing 차단 지속. 상세:
  `완료/AIRI-B4C-DEV-PC-FOLLOWUP-2026-08-14.md`.
- **2026-08-14** (검토 PC, B4c 선행 배치): 사용자가 로컬 LLM을 Mi:dm으로
  확정했다(결정 6 — 원격 방송 채팅 A/B 지연 27.5배·형식 규격 55% vs 0%·
  Motif 아티팩트 근거). B4c 방송 발화 계약의 greybox 구현을 완료했다
  (`f0ff26e` — `ollama-proxy/broadcast_contract.py` env 게이트
  `AIRI_BROADCAST_CONTRACT` 기본 OFF, 21 tests PASS, OFF 시 프롬프트 바이트
  동일). 멀티턴 방송 리허설 평가를 구축했다(`88700ac` — 시나리오 2×24턴·
  콜백 창 안/밖 분리·politeness_drift·34 tests·CI evaluations shard 등록).
  스타일 게이트(`normalize_korean_register` 치환+미해결 존댓말 문장 드롭,
  fail-closed)가 proxy 출력 전부에 적용됨을 코드로 확인했으나 방송 체인은
  AIRI 앱 WS 전달에서 끊겨 부분 경유이며 B1b 조건부 라이브 실증이 남는다.
  전/후 원격 실측(A/B `--contract` + 멀티턴 리허설)은 Tailscale 순단으로
  대기하며 복구 후 즉시 진행한다. CI billing 차단 지속 — 로컬 검증으로
  대체(신규 테스트 55건 PASS). 링크 복구 후 전/후 실측을 완료했다
  (76+96턴, 실패 0) — 단발 방송통과 0%→50%·반말 8%→66%·존댓말 위반
  35→13건, 멀티턴은 첫 턴 앵커 고정 관측(계약 단독으론 불충분 —
  proxy 스타일 게이트 이중 배선 필요)
  (`완료/AIRI-B4C-CONTRACT-AB-2026-08-14.md`).

- **2026-08-13** (B0-1 streamList): offline injected-transport measurement core를
  완료했다. 실제 내용·provider ID·AIRI 주입 없이 bounded duration/messages/responses/
  connections, actual overshoot count, monotonic timings, transient resume token,
  deadline/caller abort 및 best-effort cleanup을 검증했다 (현재 focused 20, all chat-ingress
  47, checkpoint, independent review PASS). 기존 checkpoint glob이 시험을 이미
  등록하므로 workflow 변경은 없다. 공식 quota 문서는 streamList의 정확한 연결/응답/시간
  과금을 공개하지 않으므로 추론하지 않는다. API key/OAuth/quota/project/test-broadcast
  명시 승인 및 idle/message/reconnect Cloud Console 수동 before/after 실측 전 B0-1
  라이브 판정은 NOT COMPLETE이며 B1b가 아니다.

- **2026-08-13** (dev PC, SSoT 재검증): `main`
  `c916f485565d29396e1580f16a4d72236bb724f5`에서 설치 Electron의 Mi:dm pin·단일
  100% GPU/context 2048 runner·EXAONE unpinned rollback·evaluator/export provenance와
  고의 digest 불일치 fail-closed를 재확인하고 Mi:dm baseline으로 복원했다. 설치 ASAR는
  1,356,257,019 bytes, SHA-256 `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`다.
  Python STT 8890과 Electron voice input/VAD도 모두 OFF로 복원했다.
  PR #8 병합 순간 run `31671561496`은 memory-store 완료 중이었으나 이후 13/13
  green으로 종료됐고, 병합 `main` push run `31671652918` 및 branch 최종 run
  `31668787730`도 각각 13/13 green이다.
  실행 전 검증된 orphan `llama-server` 5개를 정리한 것은 선행 정리이며 제품 PASS 근거가
  아니다. 증거 commit `e694b4f`의 run `31673311636`과 마이크 OFF 복원 commit
  `a42b5e9`의 run `31673428754`는 각각 13개 job 모두 runner 배정 전 GitHub Actions
  billing/spending-limit 오류로 실패했다. 실기 gate는 PASS이며, 최신 사용자 결정에 따라
  이 원격 실패는 역사 기록일 뿐 완료 차단이 아니다. 상세:
  `완료/AIRI-DEV-PC-SSOT-REVERIFICATION-2026-08-13.md`.

- **2026-08-13** (검토 PC): dev PC 인수분(`b369195` retrieval lifecycle)
  검토 승인 + 잔여 갭 2건 보완 — ① store/extraction `to_thread` 26지점
  `_store_call` 추적·drain(재현 테스트 수정 전 실패→후 통과 실측) ② ASAR
  preflight 계약 시험의 실제 프로세스 조회 0회화(운영 fail-closed 무변경).
  전체 900/1/738 green. G2 장기 기억의 런타임 안정성 기반 강화 —
  축 상태값 변화 없음.

- **2026-08-13** (dev PC, memory retrieval shutdown drain): PR #7 push CI의
  첫 memory shard는 159 passed 뒤 `memory.db` teardown에서 `WinError 32`로
  실패했고, 같은 PR shard retry와 main CI는 PASS했다. timeout된
  `to_thread` SQLite worker가 물리적으로 계속 실행되지만 추적되지 않았던 timing
  race를 보완했다. shielded tracked task와 협력 cancel event, timeout/caller cancel
  signal, done cleanup/error consumption, 기존 shutdown deadline 안의 early
  signal/await, stopping 시 failed rejection, 기본 8(`AIRI_MEMORY_MAX_CONCURRENT_RETRIEVALS`)
  bounded admission과 saturation fail-soft를 적용했다. focused 62 passed,
  CI-equivalent memory shard 166 passed + 27 subtests / 4 warnings, py_compile와
  scoped diff-check PASS다. 최종 Python 3.12 전체 회귀는 881 passed / 1 skipped /
  738 subtests / 7 warnings (45.92s), offline checkpoint와 독립 최종 검토도
  PASS다. native SQLite call은 즉시 interrupt되지 않으며 deadline
  뒤 tracked worker가 남을 수 있다. offline synthetic temp DB만 사용했고 설치
  AIRI·서비스·모델·runtime DB 변경은 없으며 STT/mic은 OFF/deferred다. 상세:
  `완료/AIRI-MEMORY-RETRIEVAL-SHUTDOWN-DRAIN-2026-08-13.md`.
  단, post-push run `31653832303`은 11 jobs PASS / 2 FAIL이다. memory shard는
  165 passed 뒤 extraction/background store 경로에서 동일 `WinError 32`가
  재현됐고 ASAR preflight synthetic drift는 accessible-process identity 선행
  거부로 실패했다. 따라서 이 branch는 handoff checkpoint이며 PR/merge ready가
  아니다. 검토 PC는 전체 store/extraction physical thread lifecycle을 보완하고
  full-green workflow를 새로 확보해야 한다.

- **2026-08-13** (dev PC, source ASAR read-only preflight): 고정 evidence
  SHA와 후보/current ASAR·설치 exe·fuse·unpacked manifest·3개 patch layer를
  strict type/path/file-identity/final-drift로 재검증하는 비변경 사전점검과
  합성 계약 시험을 checkpoint에 추가했다. 실경로 호출은 설치 AIRI 프로세스
  7개를 감지해 fail-closed 거부했다. 프로세스 종료·설치 파일 변경은 없었고,
  install 승인/runtime TTS·text→render/portable·Godot은 계속 미완료다. 설치 시
  installer가 digest를 재검증하고 mutex·launch barrier를 획득해야 한다.

- **2026-08-13** (TTS source ASAR candidate): 고정 source `bf173f2` / tree
  `ff71039c`에서 1,131,077,260-byte 후보 ASAR를 생성했다. SHA-256
  `6767625E...9BCED`, package 0.11.3, 28,167 entries와 critical payload를
  검증했고, 후보/설치본의 135-file unpacked path·size·hash가 모두 일치한다.
  candidate/installed executable의 ASAR 관련 fuse도 동일·disabled다. outer
  electron-builder는 후보 생성 뒤 winCodeSign symlink 권한에서 실패했으므로 full
  portable build PASS를 주장하지 않는다. 설치본은 `1B68AE...B0`로 그대로이며
  install/runtime duration/pitch는 issue #2 승인 게이트 뒤 남는다. 상세:
  `완료/AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.md` 및
  `evidence/AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.json`.

- **2026-08-13** (source ASAR deployment safety): source-built-ASAR install,
  automatic rollback, and explicit restore scripts completed their synthetic
  >1 MiB test path. They require artifact/current/backup SHA-256 checks,
  bounded critical-payload ASAR validation, no-reparse/hard-link checks,
  fail-closed AIRI process handling plus an exclusive launch barrier,
  per-target Global mutex, exact displaced-file backups, atomic replace,
  rollback, and idempotency. The full validator passed the actual installed
  ASAR read-only at SHA-256 `1B68AE...B0`; it was not stopped or modified. This does not
  complete an installation or runtime TTS duration/pitch verification.
  [GitHub issue #2](https://github.com/kkp8121-rgb/airi-local-stack/issues/2)
  remains the authorization/tracking gate. Detail:
  `완료/AIRI-SOURCE-ASAR-DEPLOY-SAFETY-2026-08-13.md`.

- **2026-08-13** (B4a chat priority policy): `broadcast-director/priority-policy.mjs`에 B1 screened event를 동결된 `{priority}` 또는 invalid `null`로 분류하는 무상태 결정론적 정책을 추가했다. 질문 > 화제 확장 > 진심 리액션 > 응원 > 긍정 fallback 순서이며 strict shape/ID/Unicode code point/timestamp·descriptor snapshot을 검증한다. V8 legacy RegExp 보존 위험을 피하기 위해 개인정보 매처는 RegExp 없이 수동 문자열 처리만 사용하고 sentinel 회귀가 비변경을 확인한다. Korean-first 휴리스틱의 오분류는 순서만 바꾸며 B3 모더레이션을 대체하지 않는다. 로컬 broadcast 집중 시험은 24/24 PASS, 독립 combined ingress/policy/director 검토는 36/36 PASS다. B4a/G5/M4는 partial이며 B4b 런타임과 외부·인간 게이트는 남는다. 상세: `완료/AIRI-B4A-CHAT-PRIORITY-POLICY-2026-08-13.md`.

- **2026-08-13** (B4a broadcast-director foundation): Node built-ins-only,
  default-OFF/inert 오프라인 코어를 추가했다. caller monotonic `nowMs`를 쓰는
  20분×6 블록, 정확한 12초 질문 대기·3:2 closed/open cycle, 침묵 사다리,
  B1 screened event 우선순위/유실 없는 bounded backpressure, 이름만의 후원 ACK,
  opaque approved-topic lease, pause/kill/replay/frozen output 계약을 포함한다.
  집중 테스트 17 PASS와 독립 최종 검토 PASS는 compressed deterministic simulation
  범위뿐이다. 실제 2시간 방송·무오디오 공백·YouTube 지연/쿼터/OAuth·런타임
  adapter·AIRI/TTS/OBS·외부 killswitch·실제 moderation·설치 ASAR 변경은 증명하지
  않는다. G5/B4와 M4는 partial이며 B4b와 승인 비공개 리허설이 남고 STT는
  OFF/deferred다. 상세: `완료/AIRI-B4A-BROADCAST-DIRECTOR-FOUNDATION-2026-08-13.md`.

- **2026-08-13** (I2a viewer-memory foundation): default-inert, separate
  SQLite storage and the content-free B1 observation boundary were added.
  Strict `broadcast:v1` pseudonyms, manual tier caps, five-name history,
  explicit typed facts (90-day maximum), 730-day event dedup retention,
  365-day inactive pruning, deletion, count-only donations, and untrusted
  callback candidates are covered by focused JS 17 and Python unittest 19
  PASS. The CI-equivalent 44-path Python 3.12 matrix also passed 877 tests,
  skipped 1, and passed 723 subtests with 7 warnings. No B1b/OAuth/live
  adapter, AIRI injection, model parsing/prompt,
  renderer, or runtime DB/launcher wiring was added; I2 remains partial until
  an authorized next-broadcast callback smoke. Detail:
  `완료/AIRI-I2A-VIEWER-MEMORY-FOUNDATION-2026-08-13.md`.

- **2026-08-13** (dev PC, TTS PCM sample-rate hardening): 이미 동작하던
  progressive WAV 경로가 32 kHz PCM을 output rate에 맞추지 않던 결함을 수정했다.
  chunk-safe mono/stereo resampler, 실제 worklet의 lossless bounded backpressure,
  pre-roll/terminal flush, abort waiter 해제, streaming body 비보관을 추가했다.
  focused Stage UI 28 tests, Stage UI·Tamagotchi typecheck, Electron production
  build와 3층 apply/reverse가 PASS했다. layer-3는 130,974 bytes, SHA-256
  `CC172A16281E56DC03E6A6F261B5531367711C0393D57E171C932EA8544C5E3E`다.
  설치본은 변경하지 않았으므로 실제 duration/pitch 회귀가 다음 게이트다. 상세:
  `완료/AIRI-TTS-PCM-SAMPLE-RATE-HARDENING-2026-08-13.md`.

- **2026-08-13** (dev PC, production-context source binding v2): 실제 proxy
  context shaping을 0/8/20/48 압력×3회 재측정했다. generic structured-output
  계약은 언어·문체 문단만 제거하고 character-state·knowledge 근거를 보존하며,
  source-oriented field와 swapped/reordered anti-overfit 회귀를 통과했다. 구조는
  PASS, 7개 필드 중 6개는 12/12지만 `dialogue_marker`는 memory marker
  `silver-fern`을 12/12 복사해 semantic/gate/authoritative 결과가 FAIL이다.
  prompt tuning은 여기서 중단하고 default 2048·extraction OFF를 유지한다.
  Python 3.12.13 전체 matrix는 **858 passed / 1 skipped / 708 subtests /
  7 warnings** PASS, checkpoint·Node는 27/27 PASS다. `f4c765f`의 push run
  `31623362906`과 PR run `31623367654`도 모두 PASS했다. 상세:
  `완료/AIRI-PRODUCTION-CONTEXT-CONTINUITY-GATE-2026-08-13.md`.

- **2026-08-13** (dev PC, context window SSoT/4096 triage): root
  `-NumCtx`/비공백 `AIRI_NUM_CTX`를 strict 512..32768(기본 2048)로 모든 proxy
  child·verify-only·warmup·health 재사용에 배선했다. invalid env는 서비스 작업 전,
  live 2048 재사용에 4096 요청은 health mismatch로 fail-closed다. `/health.prompt_budget`
  은 prompt 원문 없는 terminal-sampled 숫자 telemetry다. raw Mi:dm 4096은
  complete/schema 12/12, retry 0이지만 exact/card/부정 0/12 FAIL; 초기 사용자
  물리 절단만 해소했다. GPU paired/live 최소 여유 543 MiB도 승격 근거가 아니다.
  따라서 관측성은 완료, 품질 remediation은 계속 FAIL이고 운영 기본값 2048을 유지한다.
  current Python 3.12 41-path matrix는 **833 passed / 1 skipped / 708 subtests /
  7 warnings** (64.98s) PASS이며, proxy full은 286 passed / 377 subtests / 5 warnings
  (2.23s), API shard는 323 passed / 569 subtests다. historical 829는 base `aef5300`에만
  해당한다.
  다음 조건은 production-path deterministic context gate, holdout/continuity ledger
  또는 더 나은 모델, 인간 100건 검수다. 상세:
  `완료/AIRI-CONTEXT-WINDOW-SSOT-AND-4096-TRIAGE-2026-08-13.md`.

- **2026-08-13** (dev PC, I1 Kanana 공식 원본 후보): Kakao 공식 commit
  `6a5d7889964c4c590299d16e309eabab1f73f8a9`의 BF16 shard 해시를 검증하고,
  llama.cpp `b10375` 고정 source/tool로 프로젝트 자체 BF16→Q4_K_M GGUF를
  생성하고 manifest→model blob 해시까지 고정했다. 격리
  11436 CPU의 `kanana-airi-extraction:3b-q4_k_m` smoke는 schema/connectivity
  PASS지만 recall 0, coverage 0, unexpected 1, op/alias 0, total 24,715.938 ms로
  fail-fast FAIL해 full을 생략했다. extraction은 off, MEM-04 활성 추출 실측은
  계속 대기한다. 상세:
  `완료/AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md`.
  공개 방송은 Kanana License §2.2/§3.1/§4.1/§4.2의 법률/Kakao 확인 전
  미승격이며 표시·Notice만으로 충분하다고 보지 않는다.
  같은 계열의 historical base `aef5300` CI 41경로는 829 passed / 1 skipped /
  706 subtests였고, 현 배치 Python 3.12 41경로는 **833 passed / 1 skipped /
  708 subtests / 7 warnings** (64.98s) PASS다. proxy full은 286 passed / 377
  subtests / 5 warnings (2.23s), API shard는 323 passed / 569 subtests다. checkpoint·Node 27/27·patch
  manifest도 PASS했다.

- **2026-08-12** (dev PC, 사용자 결정): 기본 방송 프로파일을 chat/text 입력 +
  STT OFF로 고정했고 Electron 마이크 토글도 OFF로 둔다. `-Stt off` 런처 재실행은
  `STTMode=off`, `STT=disabled`, 빈 STT model/device, `8890` 부재와
  `8880/11434/11435` listener 및 proxy health `ok`를 확인했다. repo-path 일치
  STT PID 16220/26220 종료 뒤 GPU paired average는 7786.4→6742.4 MiB
  (관측 차이 1044 MiB)였으나, 동시 무관 GPU 작업이 있어 formal clean B0 capacity
  proof는 아니다. 상세: `완료/AIRI-STT-OFF-BROADCAST-PROFILE-2026-08-12.md`.

- **2026-08-12** (dev PC, I1 신규 후보, 당시 상태): 11436 격리 CPU에서 Qwen3.5 4B
  Q4_K_M과 Granite 4.0 3B smoke는 첫 행 fail-fast FAIL, Gemma3 4B는 smoke
  PASS 뒤 full 7-row balanced FAIL(독립 verifier 거부)했다. 셋 다 설치된 로컬
  후보일 뿐 운영 모델이 아니며 extraction은 off다. 당시 Kanana-2-3B는 공식 BF16 원본 직접 변환
  provenance 및 Kanana Open License broadcast/attribution 검토 전 보류했고,
  제3자 pull CLI 중단 뒤 설치가 완료된 tag도 load·측정하지 않았다. 상태값은 변하지 않는다.
- **2026-08-12** (dev PC): 당시 tip의 CI `python-core-tests` matrix 41개
  추적 경로를 같은 `requirements-ci.txt` 환경에서 재실행해
  **825 passed / 1 skipped / 706 subtests**를 확인했다(2026-08-13 `aef5300`
  재검증은 829/1/706). 기억 기술 레퍼런스의
  “Mi:dm 추출 미측정”을 실측 balanced FAIL로 고치고, C1 사용자 방향 결정과
  헌법 최종 인간 승인을 분리했다. 로드맵 상태값은 변하지 않는다.
- **2026-08-12** (dev PC): 공개 합성 장문 context·memory·card 하네스를
  추가하고 `num_ctx=2048`에서 EXAONE/Mi:dm을 4압력×3회 실측했다. exact는
  EXAONE 3/12, Mi:dm 0/12로 양 모델 FAIL. Mi:dm은 같은 무압력 입력도
  1,139 token(EXAONE 756)을 사용했고 20 filler쌍에서 2,042 token으로
  포화됐다. 최신 정정·tail memory는 양 모델 12/12 보존했다.

- **2026-08-12** (dev PC, 사용자 청취·결정 반영): T-05는 126번을 한국어
  예비 후보로 보존하되 낭독조·감정 부족 때문에 운영 승격하지 않고 현행
  일본어 참조 음성을 유지한다. 정식 팬덤명은 만들지 않고 일반 호칭
  “시청자들”만 쓰며, 방송에서 자연 발생 호칭이 쌓인 뒤 재검토한다. 실제
  마이크 실측은 사용자 요청으로 추후 보류했다.

- **2026-08-12** (dev PC, 당시 상태): 팬덤명 “아이리스” 공개 충돌 검토 FAIL.
  Hololive `IRyS`, 국내 인터넷 방송인 `@anyiris`, K-pop `IRRIS (아이리스)`와
  같은 엔터테인먼트 검색면에서 충돌하고 과거 한예슬 팬클럽의 정확 명칭
  선사용도 확인했다. AIRI 캐릭터명은 유지하고 당시 팬덤명만 사용자
  재선정으로 되돌렸다(`완료/AIRI-FANDOM-NAME-COLLISION-CHECK-2026-08-12.md`).

- **2026-08-12** (dev PC): 동일 설치 Electron·warm TTS에서 모델 순서를
  Mi:dm→EXAONE→Mi:dm→EXAONE으로 교차하고 모델별 n=10의 matched
  text→render A/B를 완료했다. Mi:dm first substantive render는 P50
  1,501.5ms/P95 2,597.2ms, EXAONE은 1,752.5/3,233.0ms였다. 작은 표본과
  TTS 분산 때문에 지연 gate 완료 근거로만 사용하며 품질 우위로 해석하지 않는다.

- **2026-08-12** (dev PC): B3 3종 배선과 설치 Electron 가시 배지를 완료
  (3층 source test/typecheck/build 신규 검증 포함). B0-2는 VRAM
  6,084/6,131/6,289MiB·최소 여유 1,736MiB에서 실제 NVENC H.264 1080p60,
  B0-3는 x264 1080p30 veryfast CPU 평균 44.8%·최대 70%·정상 5,346 frames를
  확인했다. cloud streaming 하네스·테스트와 T-05 라이선스 확인 후보 3종은
  준비 완료이나 당시 live TTFT는 API key·외부 승인, T-05는 사용자 청취
  검토 대기였다.

- **2026-08-12** (dev PC): 필수 실기 1차 배치 — 설치 Electron의 stale
  EXAONE tag→Mi:dm 정규화, foreground 단일 runner, evaluator/eval provenance,
  EXAONE 롤백, digest 일치/불일치 fail-closed를 검증하고 Mi:dm 실측 digest를
  운영 런처 기본 pin으로 고정. I1 Mi:dm balanced 7-fixture는 품질 기준 FAIL로
  추출 off 유지. B3는 TTS 폴백 5종을 기존 ACK 2종과 함께 7/7 preload하고
  moderation launcher env를 fail-closed로 배선.

- **2026-08-12** (검토 PC): CI job 타임아웃 해소 — `d13c27c` run에서
  ollama-proxy-model shard가 10분 cap에 정확히 잘림(저하 runner + 5s
  busy_timeout 기준 bounded-wait 테스트의 고정 대기). ① bounded-wait
  테스트를 테스트 전용 400ms timeout으로 패치(의미 동일, 고정 5s+ 제거,
  76 passed 32s→25s) ② 최중량 test_airi_memory.py를 전용 shard로 분할
  (10분 계약 유지, manifest 자동 대조 PASS). 상태값 변화 없음.
- **2026-08-12** (검토 PC): CI 저하 runner 견고성 수정 2건 — ① MEM-04
  busy_timeout 500→5000ms (저하 runner에서 8-thread 락 실패 재발. 당초
  500ms가 sqlite3 기본 5s 예산을 축소한 회귀였음 — WAL 유지, 상한 복원)
  ② tail matcher 성능 가드 0.15→0.6s (저하 runner 실측 0.38s 오탐 —
  알고리즘 회귀는 초 단위라 가드 가치 유지). 상태값 변화 없음.
- **2026-08-12** (검토 PC): 메타 서사 호칭 변경 "주인님"→"사장님" (사용자
  재결정 — 하드웨어 자학 개그를 1인 방송국·노동 개그로 확장 가능한 구도).
  헌법 §5·§6 확정 문구, 계획 §4, 인수인계, 색인 일괄 교체. 과거 로그의
  "주인님" 표기는 당시 기록으로 보존.
- **2026-08-12** (검토 PC): 캐릭터 문구 확정 — 시그니처 인사(메타 개그형
  C안)·팬덤명 "아이리스"·클로징(메타 개그형 신규 제작) 사용자 선택 완료.
  헌법 §6 확정본 반영, 미채택 후보는 밈 시드 풀로 보존. 남은 것: T-05
  샘플 검토·아이리스 실존 충돌 확인(웹 검색 예산 소진으로 미수행)·인간
  검수.
- **2026-08-12** (검토 PC, 당시 상태): 사용자 결정 5건 처리 — 결정 1(AI 단독형+메타
  서사 "주인님") 확정, 결정 2 조건부(dev PC 실측 2종 후 재결정), 결정 3
  부분 확정(이름 AIRI·호칭 확정, 인사·팬덤명 선택 대기), 결정 4 확정(조건
  기반 M3→리허설→데뷔), 결정 5 확정(재정의 제안 기각, §12 원문 유지).
  문서만 반영, 코드 변경 없음.
- **2026-08-12** (검토 PC): CI flaky 수정 — I1 신규 테스트
  `test_extraction_triggers_coalesce_to_one_session_worker`의 shutdown
  flush 상한 2s→20s (cold 실행에서 드레인 미완으로 1/10 간헐 실패,
  `45a26a4` CI 실패 원인. 상한 의미라 통과 케이스 비용 불변). 상태값
  변화 없음.
- **2026-08-12** (검토 PC): 현황판을 체크리스트 형식으로 개편 (사용자
  요청 — `[x]`/`[~]`/`[ ]` + 완료 일자 병기). 상태값 변화 없음.
- **2026-08-12** (`802bb82`, 검토 PC): 현행성 문서 12종 전수 실측 검토 —
  stale 20여 건 수정(사전 키 `blocked_dialogue` 교정, `AIRI_LLM_MODE`→
  `AIRI_CHAT_PROVIDER`+`AIRI_ALLOW_EXTERNAL_CHAT`, 프롬프트 751/949자
  혼동 등), 정확 확인 39건.
- **2026-08-12** (`f405d74`, 검토 PC): 로드맵 방향 문서 3종 모델 중립
  개정 + 2종 개명. 성장 전략 결정 1은 Mi:dm 전환으로 대체, 결정 5는
  Mi:dm(MIT)으로 해소. 원본 3종 아카이브 보존.
- **2026-08-12** (`41b1c20`, 검토 PC): 현황판 신설. 검토 PC 선행 배치
  반영 — 모델 SSoT 게이트 4종 코드 해소, I1 추출 배선(발효 대기),
  MEM-04 WAL, B3 모더레이션 코드 완료(M3 일부 선행), C1 헌법 초안.
- **2026-08-13** (최신 사용자 결정·읽기 전용 continuation audit): §2 로컬 실기 배치는 완료다. push/CI green은 완료 조건이 아니며 저장소는 private 유지·public visibility 변경 없음, 사용자가 요청할 때까지 push하지 않는다. historical Actions billing run `31673311636`과 `31673428754`는 각각 13 jobs 모두 `runner_id=0`/steps 0으로 runner 배정 전 실패한 사실을 보존한다. §3의 승인된 기존 extraction 후보(Mi:dm 포함)는 모두 FAIL이고 verifier는 `EXTRACTION_GATE_GATE_NOT_PASSED`; 11436·runner 없음·extraction OFF를 유지하며 새 full balanced PASS 전에는 failed weight를 **extraction runner에서** 재실행하거나 extraction을 활성화하면 안 된다. 동일 weight의 격리 foreground-chat A/B는 새 G3 계획에 따라 허용하며 extraction 결과와 분리한다. §4 구현은 완료: 설치 ASAR SHA-256 `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`, live TTS cache 7/7, 기본 moderation OFF이며 중복 재시작은 하지 않는다. §9-b는 126번 예비 보존·현행 일본어 음성 유지·STT/mic 보류로 완료다. cloud call은 명시적 전송·지출·모델 승인이 필요하고, B0-1은 YouTube OAuth/quota가 필요하다.

- **2026-08-13** (production context v2): generic structured-output 계약으로 spoken style 충돌을 제거하고 source-oriented fields, 답 canary가 없는 질문, swapped/reordered anti-overfit test를 적용했다. 구조 변환 PASS, 7개 필드 중 6개 12/12이며 두 continuity color는 v1보다 개선됐지만 `dialogue_marker` 0/12가 memory marker `silver-fern`을 결정적으로 복사해 semantic/gate/authoritative는 FAIL이다. dialogue-vs-memory는 모델 한계로 결론냈고 prompt tuning을 계속하지 않는다. default `num_ctx=2048`·extraction OFF를 유지한다.

- **2026-08-13** (latency dashboard KPI): 상단 대시보드의 기존 raw
  `playback.start` 집계가 heuristic/mixed 행을 포함해 상단은 통과로 보이는
  반면 per-turn 행은 heuristic 포함 및 substantive KPI 보류를 정확히 표시하는
  모순이 가능했던 점을 수정했다. fixed `/dashboard-metrics.mjs`의
  pure 집계는 non-synthetic cloud-search, explicit STT/LLM/playback,
  유한 `vadEndWaitMs >= 0`, `stt.start <= llm.content <=
  kpi.substantive_playback_start`, 유한 nonnegative 결과만 허용한다.
  newest-five/P50/P95/worst/pass는 substantive KPI만 사용하며 raw scalar는
  진단용이다. Node 5/5, latency Python 32 passed + 15 subtests, checkpoint,
  independent review 모두 PASS이며, 별도 Python 3.12 전체 명령
  `python -m pytest -q ollama-proxy test_latency_trace.py
  test_start_airi_background.py latency-monitor stt`도 875 passed / 1 skipped /
  738 subtests / 7 warnings (49.88s) PASS다. live mic/runtime 실측은 없고 STT는
  OFF/deferred, 설치 AIRI·서비스·모델은 변경하지 않았으며 물리적 5-turn
  gate는 닫지 않았다. 상세:
  `완료/AIRI-LATENCY-DASHBOARD-SUBSTANTIVE-KPI-2026-08-13.md`.

- **2026-08-14** (dev PC, local LLM P0–P7 actual A/B): 여섯 후보 exact HF
  revision/manifest를 고정하고 실행 가능한 다섯 common Q4와 Mi:dm/Granite native
  bounded-offload를 한 번에 하나씩 실측했다. P2/P3/P4, common P5 120-turn,
  P6 20-turn review packet, common P7 Electron→GPT-SoVITS→Windows render n=10을
  완료했다. Motif는 pinned license file 부재·remote code·8 GB safe quant 부재로
  UNRUNNABLE이며 다른 후보는 계속 실행했다. common 첫 render P50/P95는
  Mi:dm 1.762/2.489초, Ministral 2.347/4.589초, Qwen3 9.148/9.575초,
  Phi 1.842/3.740초, Granite 1.694/3.158초다. 모호성·근거·불확실성·무조건 동의
  12-scene 리허설은 Qwen 8, Phi/Ministral 7, Mi:dm 6, Granite 5였지만 Qwen은
  P50 30.020초와 빈 응답으로 foreground 부적합이다. 운영 Mi:dm 유지,
  Phi/Ministral 인간 검수 challenger, 인간 packet 대기. 설치 ASAR 불변,
  STT/extraction/moderation OFF. 상세:
  `진행중/AIRI-LOCAL-LLM-CANDIDATE-AB-RESULT-2026-08-14.md`.

- **2026-08-14 (Motif actual-status correction and closeout):** This supplements
  the prior planning/unavailable record without rewriting history. Motif exact
  revision `70bf316e166f2a256b1068e35c8310541a6a06bc` had official F32 shards
  fully downloaded and hash-verified; audited remote code then ran offline.
  Native BF16+CPU offload actually completed P1/P2/P3/P4/P6. The experimental,
  localhost-only Transformers+bitsandbytes NF4 backend (explicitly not
  Ollama-native) actually completed common P1/P2/P4/P5/P6/intelligence/P7.
  Native/common P2 were 0/16 and 1/16. Common P3 explicitly does not support
  JSON-schema and returned HTTP 400. Common P5 was 80/120 with TTFT about 8.02 s;
  intelligence was 4/12 (clarify 0/2, unknown 0); P7 render P50 was about 9.22 s.
  Result: not recommended. The pinned LICENSE file remains absent: evaluation
  exception only, with no public or revenue deployment approval.

  - [x] Exact revision, official F32 shard hashes, and remote-code audit recorded
    — 2026-08-14
  - [x] Native and local-NF4 actual evaluation paths recorded — 2026-08-14
  - [x] Operational baseline restored: Mi:dm exact digest; STT, extraction, and
    moderation OFF; no loaded runner; installed ASAR unchanged — 2026-08-14
  - [ ] Public/revenue Motif deployment approval (blocked: pinned LICENSE file absent)

- **2026-08-14 (Mi:dm–Motif native clean rerun checkpoint):** 기존 Motif 비교는 단일
  EOS 방법론 오류와 이전 대화에서 유래한 fixture 우려 때문에 역사 기록으로만 보존하고,
  비교 결론에서는 대체한다. 새 일반 합성 방송 16건을 native 경로에서 재실행했으며
  메시지 해시는 64/64 일치했고, `hf_card` 1회 및 `broadcast_equal` 3회 profile에서
  TTFT/총 시간/tok/s를 기록했다. equal-profile 핵심 수치는 Mi:dm TTFT
  P50/P95 `0.156/0.157s`, 총 시간 `2.657/8.391s`, `13.973 tok/s`; Motif는
  `0.203/0.219s`, `12.493/24.516s`, `5.227 tok/s`다. 품질은 인간 검수 대기이며,
  Mi:dm은 운영 기준을 유지하고 Motif는 배포 차단을 유지한다. 상세:
  `진행중/AIRI-MIDM-MOTIF-NATIVE-BROADCAST-RERUN-2026-08-14.md`.
  - [x] native rehearsal 및 Motif dual-EOS 집중 회귀: 28 PASS, 1 skip
  - [x] eval unittest discovery: 135 PASS, 1 skip
  - [x] Python 3.12 core pytest: 999 PASS, 2 skip, 869 subtests PASS
  - [x] sender Node 계약: 32 PASS
  - [x] six-manifest complete-set 및 current checkpoint: PASS
  - [x] Mi:dm exact digest, local provider, `num_ctx=2048`, STT/extraction/moderation
    OFF, Ollama temporary runner 없음으로 복원
  - [x] Actions run `31775348398`: 13개 job 모두 step 0, 로그 없이 실패. 기존 결제
    차단 상태로 기록하고 로컬 전체 suite/checkpoint/manifest를 검증 근거로 사용
