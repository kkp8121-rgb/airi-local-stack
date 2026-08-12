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

최종 갱신: 2026-08-13

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
  - [~] 게이트 리포트 생산 → 추출 발효 (Mi:dm balanced, Qwen3.5·Granite 4.0·
    Kanana smoke, Gemma3 full 모두 FAIL; 독립 verifier 거부, 추출 off 유지 — 통과
    후보 미확정, `완료/AIRI-NEW-EXTRACTION-CANDIDATE-GATE-2026-08-12.md`,
    `완료/AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md`)
  - [ ] MEM-04 활성 추출 락 경합 실측 (코드 완료; 통과 extractor와
    `extraction_enabled=true` 이후 Stage B commit↔foreground 겹침 증거 필요)
  - [ ] I2 시청자 기억 시스템 (M2)
- [~] **G3. 평가·데이터 플라이휠**
  - [x] 오프라인 eval 하네스·120턴 A/B — 2026-08-12 (`진행중/AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md`)
  - [x] 장문 context·memory·card 합성 A/B 실측 — EXAONE exact 3/12,
    Mi:dm 0/12로 양 모델 FAIL — 2026-08-12
    (`완료/AIRI-LONG-CONTEXT-MEMORY-CARD-AB-2026-08-12.md`)
  - [x] 장문 context budget·card/정정 표현 및 고정 4압력×3회 production 회귀 측정 완료 — **FAIL**
    (v2: 7개 필드 중 6개 12/12, `dialogue_marker` 0/12가 `silver-fern` 복사; 두 continuity color는 v1보다 개선됐으나 dialogue-vs-memory 모델 한계. 운영 기본값 2048·extraction OFF 유지)
  - [x] eval provenance 해소 (수집 데이터를 승격 근거로 사용 가능) — 2026-08-12 (`932eae6`)
  - [ ] 인간 검수 100건 수집 (dev PC)
  - [ ] 16케이스 자동 게이트 PASS (현재 양 모델 FAIL)
- [ ] **G4. 성격 파인튜닝 (QLoRA)** — (보류: G3 인간 검수 데이터 축적)
  - [x] 학습 스택 핀 (`training/` transformers+peft+bitsandbytes) — 2026-08-11 확인
  - [ ] 스타일 데이터셋 승격 재개 (`보류/AIRI-STYLE-PROMOTION-CHECKPOINT-2026-08-10.md`)
- [~] **G5. 자발 행동·방송 디렉터**
  - [x] 설계 (방송 계획 §B4 20분 블록 상태기계 = G5 실체화) — 2026-08-12
  - [ ] 구현 (선행: 결정 1~4 + M1~M3. 착수 시 토픽 거버넌스 보류 자산 해제)
- [ ] **G6. 화면·게임·채팅 에이전트** (G5 이후)

## C축 — 모델 커스터마이징 게이트

- [~] **C0. 기준선·평가 세트 고정**
  - [x] 16케이스 fixture·A/B 하네스 고정 — 2026-08-12
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
  음성 전체 체인은 미실측. 후속 최적화(운영 설치본의 source rebuild·채택 검증,
  TTS 청크 스트리밍)가 활성 목표로 남음. 여기서 source build 전환은 개발 측정의
  즉시 운영 채택이 아니라 설치본 rebuild와 실기 검증을 뜻한다.
- [x] matched Electron 모델 A/B — 같은 설치 ASAR·TTS warm, 교차 블록
  모델별 n=10. Mi:dm first substantive render P50/P95 1,501.5/2,597.2ms,
  EXAONE 1,752.5/3,233.0ms — 2026-08-12
  (`완료/AIRI-INSTALLED-MODEL-RENDER-AB-2026-08-12.md`)
- [ ] 실제 마이크 음성 체인 P50/P95 실측 (보류: 사용자 요청. “마이크 테스트
  시작” 요청 시 dev PC의 `마이크(USB Audio Device)`로 재개)
- [x] §12 완료 기준 공식 개정 (결정 5) — 2026-08-12 결정 완료: 재정의
  제안 기각, 원문 유지 확정

## 방송 실행 (M1~M5)

- [~] **M1** (B0 실측 ∥ I1 추출 ∥ C1 헌법)
  - [ ] B0-1 `liveChatMessages.streamList` 쿼터 과금 실측 (보류: 자격증명·외부 YouTube)
  - [x] B0-2 VRAM 3단계 델타 — 6,084/6,131/6,289MiB, +47/+158MiB(+205), 최소 여유 1,736MiB, NVENC H.264 1080p60 — 2026-08-12
  - [x] B0-3 5600X x264 1080p30 veryfast — 설치 Electron 실제 턴 CPU 평균 44.8%/최대 70%/최소 headroom 30%, 정상 5,346 frames — 2026-08-12 (`완료/AIRI-B0-RESOURCE-MEASUREMENT-2026-08-12.md`)
  - [x] I1 추출 활성화 코드 — 2026-08-12 (`932eae6`, 발효는 G2 리포트 대기)
  - [x] C1 헌법 초안·사용자 방향 결정 반영 — 2026-08-12
    (헌법 최종 승인은 인간 검수 후이며 C축 C1과 동일 병목)
- [ ] **M2** (B1 채팅 브리지 ∥ C2 루프 배선 ∥ I2 시청자 기억)
- [~] **M3** (B2 송출 + B3 안전)
  - [x] B3 모더레이션 게이트 코드 (사전 113항목+패턴 7, 기본 off) — 2026-08-12 (`932eae6`)
  - [x] B3 배선 3종 — TTS 폴백 7/7·런처 env·Electron "필터당함" 배지,
    신규 3층 source test/typecheck/build 및 설치본 실제 차단 턴 확인 — 2026-08-12 (`완료/AIRI-B3-ELECTRON-MODERATION-VERIFICATION-2026-08-12.md`)
  - [ ] B2 송출 (OBS Browser Source + App Audio Capture — 결정 2 이후)
- [ ] **M4** (B4 방송 디렉터 + C3/C4 ∥ I3 주제 풀)
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
- **2026-08-13** (production context v2): generic structured-output 계약으로 spoken style 충돌을 제거하고 source-oriented fields, 답 canary가 없는 질문, swapped/reordered anti-overfit test를 적용했다. 구조 변환 PASS, 7개 필드 중 6개 12/12이며 두 continuity color는 v1보다 개선됐지만 `dialogue_marker` 0/12가 memory marker `silver-fern`을 결정적으로 복사해 semantic/gate/authoritative는 FAIL이다. dialogue-vs-memory는 모델 한계로 결론냈고 prompt tuning을 계속하지 않는다. default `num_ctx=2048`·extraction OFF를 유지한다.
