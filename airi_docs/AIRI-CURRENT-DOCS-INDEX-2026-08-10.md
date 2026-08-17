# AIRI Documentation Index

문서는 상태별 폴더로 분류한다 (2026-08-12 재구성). 파일명은 유지했으므로
과거 문서가 언급하는 파일은 이름으로 검색하면 찾을 수 있다.

## 폴더 구조

| 폴더 | 의미 | 규칙 |
|---|---|---|
| `진행중/` | 현행 계약·미해결 게이트가 남은 문서 | 여기 있는 문서의 주장은 현재 브랜치 상태로 취급한다 |
| `진행예정/` | 승인됐거나 제안된 계획 (미실행 분량 존재) | 착수 전 반드시 정독 |
| `로드맵/` | 전체 로드맵 지도 (방향 문서 3종 + 현황판) | **매 작업 배치마다 `AIRI-ROADMAP-STATUS.md` 갱신 의무** — 상태 폴더와 별개로 관리 |
| `완료/` | 완료된 작업의 유효한 증거 기록 (실측·감사·구현 설계) | 수치 인용 가능. 단 이후 변경으로 stale해질 수 있으니 날짜 확인 |
| `보류/` | 명시적으로 보류된 작업 흐름의 기록 | 재개 조건이 각 문서 또는 아래에 명시됨 |
| `아카이브/` | 대체·과거 기록 | 현재 상태 검증에 사용 금지 (과거 해시·테스트 총계 포함) |
| `참조/` | 시점 무관 참고 자료 (스타일 계약·기술 레퍼런스·리서치) | |
| `patches/` | 패치 아티팩트 + 매니페스트 | **이동 금지** — `test-patch-manifest.ps1`과 CI가 경로를 핀함 |

## 진행중 — 현행 계약

- `AIRI-LOCAL-LLM-CANDIDATE-AB-RESULT-2026-08-14.md` — 여섯 후보 exact
  provenance, P0–P7 실제 실행, 방송 지능 리허설, foreground 결정과 검토-PC
  인간 packet SSoT.
- `AIRI-LOCAL-LLM-CANDIDATE-DIALOGUE-REVIEW-2026-08-14.md` — P6 실제 대화
  140 turn과 common 방송 지능 리허설 60 prompt/response를 모델명으로 대조하는
  UTF-8 원문 검토 자료. 로컬 실행·보존 경계와 빈 응답도 함께 고정한다.
- `AIRI-NEXT-SESSION-HANDOFF-2026-08-13.md` — 최신 세션 진입점. B3-c/d의
  정확한 완료 경계, Motif-2.6B v1.1-LC 평가 후보 승격 결정, 라이선스 표시·
  `trust_remote_code` 보안 경계, 8 GB prove-or-stop 평가 순서와 금지 작업을
  고정한다.
- `AIRI-REVIEW-PC-HANDOFF-2026-08-13.md` — 검토 브랜치의 정확한 완료·미완료,
  설치 AIRI 실기와 offline simulation의 경계, CI runner-allocation 실패, 검토
  우선순위를 한곳에 고정한 review PC 인수 문서.
- `AIRI-FINAL-HANDOFF-2026-08-10.md` — 패치·sender 계약과 검증 경계.
- `AIRI-SERVER-CHANNEL-PLAYBACK-CHECKPOINT-2026-08-10.md` — 취소·상관·
  재생 시작 증명의 권위 문서.
- `AIRI-GROUNDED-DIALOGUE-QUALITY-HANDOFF-2026-08-12.md` — 그라운딩 품질
  후속 계약.
- `AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md` — EXAONE→Mi:dm 전환 분석.
  게이트 중 model SSoT 강제·eval provenance·ACK metadata·digest pin은
  2026-08-12 코드·dev PC 실기 해소 완료(commit `932eae6`). 설치 Electron
  matched 모델 A/B와 장문 context/memory/card 합성 비교도 완료했다. 장문
  exact는 EXAONE 3/12, Mi:dm 0/12로 양 모델 FAIL이다. **남은 게이트**:
  인간 검수 100건과 장문 회귀 개선.
- `AIRI-DEV-PC-HANDOFF-2026-08-12.md` — **검토 PC 선행 작업 배치의
  인수인계.** SSoT·I1 후보 실측 및 B3 배선 3종은 완료했지만 extraction은
  통과 후보 부재로 off다. B0-1 offline 측정 코어는 완료됐으나 live quota 판정은
  API key/OAuth/quota/project/test-broadcast 승인 및 수동 Cloud Console 실측 전
  NOT COMPLETE다. 활성 추출 MEM-04, 사람·자격증명 게이트 등 잔여 작업을 관리한다.
- `AIRI-CLOUD-CHAT-LATENCY-MEASUREMENT-2026-08-12.md` — cloud streaming
  latency 하네스·테스트와 live TTFT 보류(API key·외부 승인) 현황.
- `AIRI-LOCAL-TECH-SPECS.md` — 현행 스펙 문서. 2026-08-12 갱신 완료
  (STT=large-v3-turbo GPU·LLM=midm-airi:2.0-mini·TTS=GPT-SoVITS 반영,
  롤백 태그·SSoT 실기 결과·확인 필요 항목 명시).

## 진행예정 — 계획

- `AIRI-G1A-CORRECTION-WORDING-DECISION-2026-08-17.md` — A4.3의 8개 synthetic
  correction 장면을 최후 fallback과 정상 캐릭터 발화 목표로 나눈 사용자 검토 시트.
  감정 원인·화면 근거·불확실성을 함께 보여 주지만 코드/운영 채택은 아니다.
- `AIRI-AFFECTIVE-CHARACTER-CONTINUITY-PLAN-2026-08-16.md` — G1a 감정·
  캐릭터 연속성 엔진 상세 계획. 공개 MIT/Apache 프로젝트의 bounded affect,
  event-sourced reducer, memory-layer 패턴만 인용하고 repo-native typed reducer를
  자체 제작한다. constitution v2 사용자 결정, 기본 OFF proxy greybox, 독립
  합성 6×24 OFF/ON·인간 검수, 이후 B4/TTS/Live2D·장시간 리허설 순서를 정의한다.
  A1/A2와 A4 실제 Mi:dm OFF/ON, A4.1 reply-act 3조건 blind review까지 완료했으나
  품질 gate는 FAIL이다. A4.2 guarded-delta는 commits `f612fd8`/`6cf4045` 후속의
  zero-network retrospective compositor이며 current 23-test suite와 독립 재검토 GO까지 완료했다.
  canonical A4.1 bundle의 exact historical `reply_act` response와 fixed 22행의 실제
  zero-call composition 및 두 model review도 완료했다. thank·최초 deescalate·repair에는
  탐색적 양성 신호, generic correct에는 음성 신호가 나왔으며, fresh human review·A0
  사용자 승인·A3·운영 ON은 미완료다. A4.3은 generic correction 승격 대신 여덟 synthetic
  target/direction의 closed offline eligibility까지만 추가했다.
- `AIRI-CHARACTER-CONSTITUTION-V2-DECISION-2026-08-16.md` — G1a A0 사용자
  결정 시트. 기존 확정 정체성·말투·안전 경계와 미정 likes/dislikes/pride/
  embarrassment/conflict/repair/fatigue 및 metric threshold 선택지를 분리한다.
  문서 작성은 승인이나 운영값 채택을 뜻하지 않는다.
- `AIRI-KOREAN-LIVE-CHAT-REPLAY-PLAN-2026-08-15.md` — G3/C0·M3의
  실제 한국 방송 채팅 흐름 평가 계획. 탬탬버린·아카네 리제·아이네의 공개
  채널을 관찰 대상으로 삼되 공식 권한 없는 수집은 금지한다. 승인된 비공개
  export만 명시 identity/정형 PII 패턴/금액을 모델 전달 전에 제거해 시간순
  replay하고,
  원문은 git·일반 report·학습 데이터에 넣지 않는다. privacy replay 기반은
  구현됐고 실제 캡처·Mi:dm OFF/ON 실측은 권한 대기다.
- `AIRI-LOCAL-LLM-CANDIDATE-AB-PLAN-2026-08-13.md` — 즉시 착수하는
  G3/C0 최우선 배치. Mi:dm 대조군과 Motif·Ministral·Qwen3·Phi-4-mini·
  Granite 전 후보에 대해 모델별 공식 사용법 manifest, official-native와
  AIRI-common 이중 profile, raw/context/persona/proxy/인간 검수/full-stack
  동일 조건 평가를 정의한다.
- `AIRI-BROADCAST-CHARACTER-PLAN-2026-08-12.md` — 지능·캐릭터성·방송 통합
  계획. 사용자 결정 중 1·3·4 확정, 2 조건부. 결정 3은 정식 팬덤명 유보·
  일반 호칭 “시청자들” 사용, T-05 126번 예비 후보 보존·현행 음성 유지다.
  근거는
  `참조/AIRI-BROADCAST-RESEARCH-2026-08-12.md`.
- `AIRI-CHARACTER-CONSTITUTION-DRAFT-2026-08-12.md` — C1 캐릭터 헌법
  초안 v5. **결정 1·3 반영(2026-08-12), 코드 미반영**. 정체성(이름 AIRI
  확정)·가치관·말버릇 후보·관계 규정(안 B 채택 + 메타 서사 "사장님"
  절)·리액션 톤 3단계를 포함하며, `AIRI_SYSTEM_PROMPT`를 대체하지 않고
  확장한다. 정식 팬덤명은 유보하고 “시청자들”을 일반 호칭으로 사용한다.
  남은 확정: 인간 검수.

## 로드맵 — 지도와 현황판 (상태 폴더와 별개 관리)

- `AIRI-ROADMAP-STATUS.md` — **살아있는 현황판.** G0~G6(G1a 포함)·C0~C5·지연·M1~M5
  전 축의 상태와 근거, 사용자 결정 차단 지점, 배치별 갱신 로그.
  **매 작업 배치 커밋마다 갱신 의무** (검토 PC·dev PC 공통).
- `AIRI-GROWTH-STRATEGY.md` — **사용자 승인 방향.**
  G0~G6 성장 로드맵 정의 (G1/G1a 캐릭터·감정 연속성 루프 → G2 장기 기억 → G3 평가
  플라이휠 → G4 파인튜닝 → G5 자발 행동·방송 디렉터 → G6 게임 에이전트).
  (옛 이름 `AIRI-EXAONE-GROWTH-STRATEGY-2026-08-07.md` — 2026-08-12 모델
  중립 개정으로 개명. 개정 전 원본은 `아카이브/`에 옛 이름으로 보존.)
- `AIRI-MODEL-CUSTOMIZATION-PLAN.md` — C0~C5 모델 커스터마이징 게이트 정의.
  (옛 이름 `AIRI-EXAONE-MODEL-CUSTOMIZATION-PLAN-2026-08-07.md` — 2026-08-12
  모델 중립 개정으로 개명. 모델이 Mi:dm으로 바뀌어도 게이트 구조는 유효)
- `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md` (v2.1) — 지연 마스터 계획. §6 지연
  예산·§12 완료 기준은 2026-08-12 사용자 결정으로 원문 유지 확정(재정의
  제안 기각). 2026-08-12 모델 중립 개정(파일명 유지), 개정 전 원본은
  `아카이브/AIRI-NEUROSAMA-LOW-LATENCY-PLAN-pre-midm.md`.

## 완료 — 유효한 증거 기록 (최신순)

- `AIRI-G1A-CORRECTION-TARGET-FOUNDATION-2026-08-17.md` — A4.3의 평가 전용
  closed correction-target foundation. 기존 `correct` 8행을 exact semantic ID와 direction에
  결합해 offline human-review eligibility만 판정한다. ID는 pinned synthetic assertion이며
  live fact가 아니다. 대사·selector·runtime wiring·운영 승격은 없고 gate는 FAIL/OFF다.

- `AIRI-G1A-GUARDED-DELTA-REVIEW-2026-08-17.md` — A4.2 canonical 22행
  zero-call composition과 두 separate model-review session의 unblind aggregate. 둘 다 같은 14행에서
  guarded, 같은 6행에서 control을 선호했으나 template identity가 부분 노출됐고 human
  review가 아니며 locked review provenance도 보존되지 않아 탐색 증거다. thank·최초
  deescalate·repair는 좁은 fallback 후보,
  generic correct는 5/8 control 우세이며 operational gate는 FAIL/OFF다.

- `AIRI-G1A-GUARDED-DELTA-FOUNDATION-2026-08-17.md` — A4.2 guarded-delta
  zero-call retrospective compositor foundation. 31 target / 22 fixed / 9 human-only /
  91 non-target oracle, legacy receipt/arm-key authenticity 한계, partial blinding을 기록한다.
  foundation 당시 22 tests·독립 재검토 GO를 기록하며 current suite는 summary contract를
  포함해 23 tests다. 실제 composition/review는 후속 결과 문서로 분리한다.

- `AIRI-G1A-MUST-ACT-REALIZATION-FOUNDATION-2026-08-17.md` — G1a A4.2의
  offline/default-inert foundation. A4.1 B가 affect_only보다 expected act 68.9% vs 60.7%,
  reversal 5 vs 10으로 나았으나, OFF 대비 grounding 63.1% vs 60.7%, pathology 18 vs 24,
  donation thank 0/3으로 gate FAIL 및 operational OFF가 유지됨을 기록한다. five-act
  input-free renderer/content-free oracle와 local 27-test 증거를 기록하며,
  production/proxy/event/B4b/live model-TTS/operational ON은 범위 밖이다.

- `AIRI-G1A-REPLY-ACT-TRIPLET-2026-08-17.md` — G1a A4.1의 context-only /
  affect-only / affect+reply-act 122 triplet·366응답과 두 blind review 기록.
  reply-act는 affect-only보다 act/grounding/reversal을 개선했지만 OFF를 넘지 못하고
  pathology와 후원 감사 0/3 때문에 다시 품질 gate FAIL. 운영 gate는 OFF다.

- `AIRI-G1A-AFFECT-BROADCAST-AB-2026-08-17.md` — G1a A4의 실제 Mi:dm
  합성 방송 122쌍·244응답과 blind human review 기록. unblind 결과 OFF가
  causal/repair/safety와 fallback에서 근소하게 낫고 ON은 개선을 입증하지 못해
  품질 gate FAIL. 대표 OFF/ON 원문과 다음 grounded reply-act 보완 방향을 담으며,
  운영 affect gate는 기본 OFF를 유지한다.

- `AIRI-G1A-AFFECT-BROADCAST-EVAL-FOUNDATION-2026-08-16.md` — G1a A4의
  offline foundation 완료. 독립 한국어 방송 6×24 fixture, A1 reducer 144/144
  oracle, 122개 OFF/ON paired request/transport 계약, frozen Mi:dm profile,
  content-free report·blind private packet 경계를 고정한다. 실제 Mi:dm 응답과
  blind human review, 운영 ON은 포함하지 않는다.

- `AIRI-G1A-AFFECT-CORE-FOUNDATION-2026-08-16.md` — G1a A1 scoped 완료.
  strict typed affect schema, deterministic one-step reducer, decay/recovery/safety,
  bounded in-memory LRU/ring과 content-free health. A1 배치 자체는 proxy/prompt/env에
  미배선이었고 같은 날 후속 A2 greybox가 별도 완료 문서로 이어졌다.

- `AIRI-G1A-AFFECT-PROXY-GREYBOX-2026-08-16.md` — G1a A2 scoped 완료.
  기본 OFF, explicit-session typed snapshot의 384-byte request-local projection,
  평가/quality/proactive 비변이, content-free enabled/ready health와 launcher reuse
  fail-closed를 고정한다. 운영 event source·Mi:dm A/B·운영 ON은 포함하지 않는다.

- `AIRI-B4C-DEV-PC-FOLLOWUP-2026-08-14.md` — 검토 PC B4c 배치와 직전
  로컬 자산 통합의 dev PC 인수 기록. retired 11439 gateway의 정확한
  비스트리밍·`max_tokens=1..128` 소스 계약, canonical 11435/v1 방송 경로
  checkpoint, B1b style-gate 종단 실증 체크리스트와 B4a 명시적 후원 이름 호명
  action을 다룬다. 계약 ON·파라미터 승격은 포함하지 않는다.
- `AIRI-LOCAL-ASSET-CONSOLIDATION-2026-08-14.md` — 분산 worktree·검증 clone·
  모델 평가 자산의 main 통합 기록. 최종 Mi:dm runtime만 유지하면서 후보
  weights는 제거하고, source bundle·P0 provenance·중간 patch·Codex session
  inventory·ignored 실측 결과를 재현 경계에 맞춰 보존한 근거다.
- `AIRI-LOCAL-TEMP-AND-FAILED-MODEL-CLEANUP-2026-08-13.md` records the completed
  user-requested local cleanup after the approval/candidate-failure block (not
  context exhaustion): removed temporary/reproducible data, preserved
  authoritative state, precise measured space, and the no-recycle-bin recovery
  boundary.

- `AIRI-NEW-LOCAL-EXTRACTION-CANDIDATE-SMOKES-2026-08-13.md` — Ministral 3
  3B·Phi-4-mini 3.8B·Granite 3.3 2B의 공식 원본/라이선스와 local isolated
  `persistent_trait` smoke를 tracked JSON으로 고정한 evidence. 세 후보 모두
  FAIL이며 full balanced gate가 아니므로 extraction OFF, 11436 stopped,
  active Stage-B contention test 없음, production 11434/11435 불변이다.

- `AIRI-B0-1-STREAMLIST-QUOTA-MEASUREMENT-CORE-2026-08-13.md` — streamList의
  injected-transport-only·content-free 오프라인 quota measurement core. focused 20,
  all chat-ingress 47, checkpoint, independent review PASS; provider B1b/OAuth/live polling은
  범위 밖이다. 공식 quota 문서는 exact streamList charging을 명시하지 않으므로 live
  B0-1은 승인된 API/OAuth/project/test broadcast와 idle/message/reconnect 수동
  before/after Cloud Console 실측 전 NOT COMPLETE다.

- `AIRI-DEV-PC-SSOT-REVERIFICATION-2026-08-13.md` — `main`
  `c916f485565d29396e1580f16a4d72236bb724f5`의 설치 Electron SSoT 후속 재검증.
  Mi:dm exact pin·단일 GPU runner, EXAONE unpinned rollback, evaluator/export
  provenance, 불일치 digest fail-closed, Python STT·Electron voice input OFF 및 Mi:dm
  baseline 복원을 기록한다. PR #8
  문맥 run `31671561496`, 병합 `main` push run `31671652918`, branch 최종 run
  `31668787730`은 모두 13/13 green이다. 재검증 commit `e694b4f`의 run
  `31673311636`과 마이크 OFF 복원 commit `a42b5e9`의 run `31673428754`는 runner
  배정 전 GitHub Actions billing 오류로 실패했다. 최신 사용자 결정에 따라 이 원격 실패는
  역사 기록일 뿐 로컬 실기 배치 완료를 막지 않는다. 2026-08-12 증거도 역사 기록으로 보존한다.

- `AIRI-MEMORY-RETRIEVAL-SHUTDOWN-DRAIN-2026-08-13.md` — PR #7 push CI의
  memory shard가 159 passed 뒤 `memory.db` teardown `WinError 32`로 실패한
  실제 lifecycle race를 기록하고, tracked/shielded retrieval task·협력 취소·기존
  deadline 내 shutdown drain·stopping fail·기본 8의 bounded admission을 검증한
  오프라인 증거. focused 62 passed, CI-equivalent shard 166 passed + 27 subtests /
  4 warnings다. native SQLite 호출은 즉시 중단할 수 없고 deadline 뒤에도 tracked
  worker가 남을 수 있으며, 설치 AIRI·서비스·모델·runtime DB 변경이나 STT/mic
  실기는 포함하지 않는다. 최종 Python 3.12 전체 회귀는 881 passed / 1 skipped /
  738 subtests / 7 warnings이며 offline checkpoint와 독립 retrieval 검토도
  PASS다. post-push run `31653832303`의 2 FAIL은 검토 PC `22a6add`에서
  store/extraction worker 추적·drain과 deterministic ProcessProvider로 해소됐고,
  main `c916f48`에 병합됐다. 후속 전체 900 passed, checkpoint PASS, lifecycle
  10회 안정이다. native store 호출의 비협력 취소 한계는 문서대로 유지한다.

- `AIRI-LATENCY-DASHBOARD-SUBSTANTIVE-KPI-2026-08-13.md` — 상단 대시보드가
  raw `playback.start`가 아니라 strict substantive playback KPI만으로
  newest-five/P50/P95/worst/pass를 계산하도록 정합성을 고정한 오프라인 증거.
  Node 5/5, focused latency Python 32 passed + 15 subtests, checkpoint,
  independent review 및 별도 전체 Python 3.12 875 passed / 1 skipped / 738
  subtests / 7 warnings (49.88s)를 기록한다. live mic/runtime 실측, 설치
  AIRI·서비스·모델 변경, 물리적 5-turn gate 완료를 뜻하지 않는다.

- `AIRI-SOURCE-ASAR-PREFLIGHT-2026-08-13.md` — source ASAR 후보·설치
  baseline·unpacked·patch provenance를 묶는 read-only 사전점검과 합성 계약
  시험. 실경로 호출은 설치 AIRI 프로세스 7개에서 fail-closed 거부했으며
  설치 승인·파일 변경·runtime TTS PASS를 뜻하지 않는다.

- `AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.md` — 고정 source commit/tree에서
  설치 후보 ASAR를 생성해 digest·28,167 entries·핵심 payload·설치본과 동일한
  135-file unpacked manifest를 검증한 기록. outer `electron-builder`는 후보 생성
  뒤 winCodeSign symlink 권한에서 실패했으므로 full portable build PASS는 아니며,
  설치와 runtime duration/pitch는 issue #2 승인 뒤 남는다. 기계 판독 sidecar는
  `evidence/AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.json`이다.

- `AIRI-SOURCE-ASAR-DEPLOY-SAFETY-2026-08-13.md` — source-built ASAR의
  fail-closed install/restore 안전 도구와 >1 MiB synthetic PASS, 실제 설치
  ASAR의 read-only full-validator PASS 기록. 실제 설치 AIRI는 변경하지
  않았으며, 설치·runtime TTS duration/pitch는
  [GitHub issue #2](https://github.com/kkp8121-rgb/airi-local-stack/issues/2)
  승인 게이트 뒤 별도 검증이 필요하다.

- `AIRI-B4A-CHAT-PRIORITY-POLICY-2026-08-13.md` — B1 screened event를 위한 순수·무상태 결정론적 우선순위 정책의 좁은 오프라인 완료 기록. 개인정보 비보존 문자열 매처, strict 입력 검증, Korean-first 휴리스틱 및 로컬 broadcast 집중 시험 24/24·독립 combined 검토 36/36을 다루며 B4a/G5/M4 전체 완료나 런타임 증거를 의미하지 않는다.

- `AIRI-B4A-BROADCAST-DIRECTOR-FOUNDATION-2026-08-13.md` — 기본 OFF/inert,
  Node 내장 모듈만 쓰는 B4a 오프라인 broadcast-director 기반. caller monotonic
  `nowMs`의 20분×6 블록·질문/침묵/후원/토픽 lease·pause/kill 계약과 집중 테스트
  17 PASS·독립 최종 검토 PASS를 기록한다. compressed deterministic simulation일
  뿐 실제 2시간 방송·무오디오 공백·YouTube/OAuth·런타임 adapter·AIRI/TTS/OBS·외부
  killswitch·실제 moderation·설치 ASAR 변경의 증거는 아니다.

- `AIRI-I2A-VIEWER-MEMORY-FOUNDATION-2026-08-13.md` — I2a default-OFF
  separate SQLite viewer-memory foundation, content-free observation boundary,
  strict HMAC pseudonyms, bounded retention/facts/tier/deletion/count-only
  donation contracts, and focused JS 17/Python unittest 19 PASS. B1b/live
  adapter/AIRI injection/runtime integration은 포함하지 않았고 I2는 partial이다.
- `AIRI-TTS-PCM-SAMPLE-RATE-HARDENING-2026-08-13.md` — progressive
  GPT-SoVITS PCM의 32 kHz→AudioContext output-rate resampling, lossless bounded
  backpressure와 bounded fallback retention을 구현·빌드 검증한 source 증거.
  설치 ASAR 교체와 duration/pitch 실기는 아직 수행하지 않았다.
- `AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md` — Kakao 공식
  Kanana-2-3B commit/shard 기반 프로젝트 자체 Q4_K_M 변환 provenance와
  11436 격리 CPU smoke FAIL 증적. full은 생략했고 extraction은 off이며,
  공개 방송 라이선스는 법률/Kakao 확인 전 미승인이다.
- `AIRI-NEW-EXTRACTION-CANDIDATE-GATE-2026-08-12.md` — 11436 격리 CPU의
  Qwen3.5·Granite 4.0 smoke FAIL 및 Gemma3 smoke PASS/full 7-row FAIL 고정
  증적. 문서의 Kanana 미시험 경계는 당시 기록이며 2026-08-13 후속 문서로
  대체됐다.
- `AIRI-LONG-CONTEXT-MEMORY-CARD-AB-2026-08-12.md` — `num_ctx=2048`의
  활성 card·초기 화자·최신 부정 정정·tail memory를 EXAONE/Mi:dm 각
  4압력×3회 비교한 실측과 양 모델 FAIL 판정.
- `AIRI-DEV-PC-SSOT-VERIFICATION-2026-08-12.md` — 설치 Electron 정규화,
  Mi:dm 단일 runner, EXAONE 롤백, evaluator/eval provenance, digest pin
  일치·불일치와 운영 기본 pin의 dev PC 실기 증거.
- `AIRI-MIDM-EXTRACTION-GATE-MEASUREMENT-2026-08-12.md` — 11436 격리 CPU
  Mi:dm balanced 추출 게이트 FAIL(품질·Stage B 연결 미달, 추출 off 유지).
- `AIRI-B3-ELECTRON-MODERATION-VERIFICATION-2026-08-12.md` — B3 3종 배선,
  신규 3층 source 검증 및 설치 Electron "필터당함" 배지 실기 증거.
- `AIRI-B0-RESOURCE-MEASUREMENT-2026-08-12.md` — VRAM 3단계·NVENC 및 x264
  실제 설치 Electron 턴 자원 실측.
- `AIRI-INSTALLED-MODEL-RENDER-AB-2026-08-12.md` — 동일 설치 ASAR·warm
  TTS에서 Mi:dm/EXAONE 교차 matched text→render A/B(모델별 n=10).
- `AIRI-T05-KOREAN-SPEAKER-CANDIDATES-2026-08-12.md` — 라이선스 확인 한국어
  화자 후보 3종 샘플과 사용자 청취 판정. 126번은 예비 후보로 보존하지만
  운영은 낭독조·감정 부족 때문에 현행 일본어 참조 음성을 유지한다.
- `AIRI-FANDOM-NAME-COLLISION-CHECK-2026-08-12.md` — “아이리스”의 VTuber·
  방송인·K-pop·과거 팬클럽 충돌 확인과 공개 사용 FAIL 판정.

- `AIRI-ELECTRON-TEXT-TTS-MEASUREMENT-2026-08-12.md` — Electron 실기
  text→render 실측 (P50 1,963ms / P95 2,720ms) + 스트리밍 WAV 결함 수정.
- `AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md` — Upgrade Scout 구현·실측
  (KURE fp16 −1,083MiB, prefix 캐시 235.6→12.7ms 등) + 실기 게이트 목록.
- `AIRI-UPGRADE-SCOUT-2026-08-11.md` / `-DATA-` — 업그레이드 경로 조사와
  타당성 판정. 기존 전제 3건 정정 (TTS cold 비노출·half-duplex 원인·
  소스 빌드 완료).
- `AIRI-INDEPENDENT-REVIEW-2026-08-10.md` / `-DATA-` — 주말 델타 독립 검토
  (발견 81건 + 신설 목표 149건 + 충돌 6건).
- `AIRI-STABILITY-CHECKPOINT-2026-08-10.md` — 재현성·검증 안정화 기록.
- `AIRI-LATENCY-ACCEPTANCE-2026-08-09.md` — 지연 실측 기준선 (저장 WAV).
- `AIRI-MEMORY-LIVE-SMOKE-2026-08-09.md` — 기억 라이브 스모크.
- `AIRI-VTUBER-STYLE-REVIEW-2026-08-09.md` — 스타일 게이트 기준선 실측.
- `AIRI-KNOWLEDGE-RAG-DESIGN-2026-08-09.md` — 지식 저장소 설계 (구현됨).
- `AIRI-LOCAL-STACK-REVIEW-2026-08-07.md` — 기준선 감사 (이후 CRITICAL
  다수 해소됨 — 현재 상태 판정에는 이후 문서 사용).

## 보류 — 재개 조건 명시

**토픽 거버넌스 운영 배포** (재개 조건: G5 방송 디렉터 착수 — 방송 계획
B4·I3이 이 자산을 소비한다): `AIRI-LOCAL-TOPIC-BOARD-DESIGN/
-IMPLEMENTATION-2026-08-09.md`, `AIRI-APPROVED-TOPICS/-KNOWLEDGE-2026-08-09.md`,
`AIRI-TOPIC-CURATION/-WORKFLOW-STATUS-CHECKPOINT-2026-08-10.md`,
`AIRI-WIKIMEDIA-*-CHECKPOINT-2026-08-10.md` 3종.
승인 지식 fixture는 테스트 재현성만 보장하며 운영 배포는 별도 승인 과제.

**스타일 데이터셋 승격** (재개 조건: G4 파인튜닝 착수 — 현 단계 LoRA 보류):
`AIRI-STYLE-PROMOTION-CHECKPOINT-2026-08-10.md`.

## 참조

- `AIRI-BROADCAST-OBSERVATION-STUDY-2026-08-14.md` — 저스트챗 방송 방식
  관찰 연구 (사용자 지정 4인 트랜스크립트 1차 실측). 공통 패턴 10종·차이
  스펙트럼·기존 설계 수정 지점 7건·B4c 파라미터 후보. 2차 자료 기반이던
  방송 설계의 실증 검증.
- `AIRI-BROADCAST-RESEARCH-2026-08-12.md` — 저스트챗 방송 구조·뉴로사마
  벤치마크·한국 씬 + 채팅 API·OBS·안전장치 기술 조사 (출처 포함).
- `AIRI-VTUBER-JUST-CHATTING-REFERENCE-2026-08-08.md` — **현행 스타일 계약**
  (한국어 1~2문장·직접 반응·상담식 금지·실존 창작자 모방 금지).
- `AIRI-MEMORY-TECH-REFERENCE.md` — 기억 계층 기술 레퍼런스.
- `rtk-setup-guide.md` — rtk 토큰 절감 설치 가이드.

## 아카이브 이용 시 주의

- 과거 해시·테스트 총계·설치 절차로 현재 체크아웃을 검증하지 말 것.
- `patch-airi-*.ps1` 개별 호출 예시를 따르지 말 것 — 지원 진입점은
  `apply-airi-patches.ps1` / `restore-airi-original.ps1`뿐.
- **현 설치본 기준:** B3 후 `app.asar` SHA-256은
  `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`이다.
  기본 런타임은 moderation off, Mi:dm pin, TTS cache 7/7로 복원됐다.
  아카이브의 과거 SHA-256은 현재 설치본 판정에 사용하지 말 것.
- `아카이브/AIRI-NARRATIVE-CHECKPOINT-2026-08-09.md` — AIRI 고유 서사
  (signal garden 등) 결정 기록. 캐릭터 헌법(C1) 작업 시 참조.

## patches/ — 런타임 패치 계약 (이동 금지)

- `patches/AIRI-v0.11.3-round-cancel-source-replacement.md` — 통합 런타임
  패치 매니페스트 (SHA-256·크기·범위).
- `patches/AIRI-v0.11.3-upgrade-scout-runtime-20260811.md` — Upgrade Scout
  클라이언트 레이어 매니페스트.
- 적용 순서: **통합 패치 → context sanitizer → Upgrade Scout 레이어** 3층.
  그 외 `.patch`는 보존된 과거 스냅샷 — 적용 금지 (3종은 적용 불가 결함이
  기록돼 있으며 `test-patch-manifest.ps1`이 결함 존속을 검사한다).

## 검증 경계

소스·패치 계약은 오프라인 테스트, dev PC 실기는 각 `완료/` 증거 문서의
명시된 범위로만 해석한다. 거버넌스 토픽 보드 생성, 실제 마이크 텍스트
전송, 원시 ID·대화 노출, default-render 신호를 물리 음압·자연 재생 종료로
확대 해석하는 것은 금지한다.

## 최신 검증 증거 (2026-08-13)

- `완료/AIRI-B3C-INPUT-SCREENING-AND-LOCAL-CHAT-SPINE-2026-08-13.md` —
  default-OFF deterministic prefilter와 local screened delivery spine의 구현,
  loopback proof, 언어·UI/TTS·provider 비주장 경계.
- `완료/AIRI-B3D-PERSONA-JAILBREAK-MARKER-CORPUS-2026-08-13.md` —
  exact 4×5 multilingual corpus와 direct Mi:dm marker-contract FAIL 증거.
- `evidence/AIRI-B3C-INPUT-SCREENING-LIVE-PROBE-2026-08-13.json` — fresh
  loopback-only B3-c policy probe: unchanged installed ASAR and seven AIRI
  processes; source screening ON/ready; five category blocks, benign Korean
  allow twice (12 inspected/2 allowed/10 blocked); output moderation/extraction
  OFF and STT listener absent. It is not installed UI/TTS proof.
- `ollama-proxy/eval/results/airi-persona-jailbreak-marker-midm-2026-08-13.json`
  — B3-d exact 20-case ko/en/ja/zh content-free direct local Ollama corpus,
  fixed provenance and latency. Structural 20/20 PASS but standalone marker
  contract 5/20 PASS, so overall FAIL; it makes no semantic-safety, proxy,
  Electron, UI, or TTS claim and installed red-team remains pending.
- Current B3 scope: B3-c deterministic local prefilter + local B1 downstream
  spine is default OFF and independently reviewed PASS; B3-d corpus/direct
  prefilter evidence is complete but its marker contract is FAIL; B3-e installed
  UI badge + TTS/current-policy rehearsal remains pending. The latter recheck
  stopped before model/TTS because cleanup removed `@moeru/std`; installed ASAR
  was untouched. Provider streamList/OAuth/quota/live AIRI integration also
  remains unimplemented, and actions billing is blocked.

- **현재 안전 게이트 상태** (로드맵 M3 B3-c/d/e): B3-c의 default-OFF
  결정론적 로컬 prefilter와 screened downstream spine은 구현·독립 검토 PASS지만
  다국어 semantic classifier는 아니며 미검증 언어는 hold한다. B3-d의 20-case
  direct marker corpus는 실행됐으나 5/20로 FAIL이고 설치 Electron red-team은
  미완료다. B3-e category별 설치 UI·TTS 차단 반응 실기는 여전히 미완료이며
  output moderation 기본값도 OFF다. 따라서 방송 안전 완료 선언은 금지한다.
- **현재 결정/후속 읽기 전용 점검** — §2 로컬 실기 배치는 완료이며 push/CI green은 더 이상
  완료 조건이 아니다. 저장소는 private 유지·public visibility 변경 없음이고, 사용자가 요청할
  때까지 push하지 않는다. historical Actions billing 실패(run `31673311636`,
  `31673428754`: 각각 13 jobs, 모두 `runner_id=0`/steps 0)는 사실대로 보존한다.
  §3은 Mi:dm을 포함한 승인된 기존 extraction 후보가 모두 FAIL이고,
  verifier `EXTRACTION_GATE_GATE_NOT_PASSED`, 11436/runner 없음/extraction OFF 상태이며 새
  full balanced PASS 전 failed weight를 extraction runner에서 재실행하거나
  extraction을 활성화하면 안 된다. 동일 weight의 foreground-chat A/B는 새 G3
  계획에 따라 별도로 허용한다. §4는 설치 ASAR
  `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`, live TTS cache
  7/7, 기본 moderation OFF로 완료·중복 재시작 불필요다. §9-b는 126번 예비 보존, 현행 일본어
  음성 유지, STT/mic 보류로 완료다. cloud call은 명시적 전송·지출·모델 승인, B0-1 live는
  YouTube API/OAuth/quota/project/test-broadcast 승인과 수동 Cloud Console
  idle/message/reconnect before/after 실측이 필요하다.

- `완료/AIRI-PRODUCTION-CONTEXT-CONTINUITY-GATE-2026-08-13.md` — version 2.0 실제 proxy context shaping의 0/8/20/48 압력×3회 권위 결과. generic structured-output 계약으로 spoken style 충돌을 제거하고 source-oriented fields·답 canary가 없는 질문·swapped/reordered anti-overfit test를 적용했다. 구조·privacy·ordering PASS, 7개 필드 중 6개 12/12이며 두 continuity color는 v1보다 개선됐지만 `dialogue_marker` 0/12가 memory marker `silver-fern`을 결정적으로 복사해 semantic/gate/authoritative FAIL이다. dialogue-vs-memory는 모델 한계이므로 prompt tuning을 계속하지 않는다. default 2048·extraction OFF, STT/mic은 사용자 보류 상태다.

- `완료/AIRI-CONTEXT-WINDOW-SSOT-AND-4096-TRIAGE-2026-08-13.md` — root context
  window SSoT(512..32768, 기본 2048), health mismatch fail-closed와 content-free
  prompt-budget telemetry의 측정/관측 증거. Mi:dm raw 4096은 초기 사용자 물리 절단을
  해소했지만 exact/card/부정 FAIL이고 GPU 최소 여유 543 MiB여서 운영 승격하지 않는다.
  current Python 3.12 41-path matrix는 833 passed / 1 skipped / 708 subtests /
  7 warnings (64.98s) PASS다. proxy full은 286 passed / 377 subtests / 5 warnings
  (2.23s), API shard는 323 passed / 569 subtests다.

- `완료/AIRI-STT-OFF-BROADCAST-PROFILE-2026-08-12.md` — 기본 방송 프로파일
  chat/text 입력 + STT OFF, Electron 마이크 OFF 결정 및 런처 OFF 실기 기록.
  `-Stt on`/`AIRI_STT=on`은 명시적 opt-in이며, GPU 1044 MiB는 동시 무관 작업이
  있는 paired observation으로 formal clean B0 capacity proof가 아니다.

- 통합 Python historical base: **829 passed / 1 skipped / 706 subtests** (`aef5300`의 CI
  `python-core-tests` matrix 41개 추적 경로를 Python 3.12 dev PC에서 재실측,
  SSoT·I1 게이트·MEM-04·B3 모더레이션·cloud latency 하네스 포함).
- `node --test test-send-airi-local-text.mjs`: 27/27.
- `test-current-checkpoint.ps1`: PASS(기본 실행의 applicability는 의도적
  SKIP). 별도 `test-patch-applicability.ps1 -BaseCheckout <pinned>`에서 3층
  정방향·역방향 PASS, plain apply+stage의 최종 tree `d40b4a3d…` 일치.
- Upgrade Scout 클라이언트: Stage UI·Tamagotchi 타입검사 + 집중 42 테스트
  통과. 최신 `main` 포팅 브랜치: 25/25 빌드 + 집중 168 테스트.
- CI: `offline-contracts` + `python-core-tests` 두 job green
  (tip `294c4e6` 기준; `7dc4e76`·`932eae6` 이후 커밋은 push 시 재검증).
- 실기 게이트 미통과 항목은 `완료/AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md`
  §판정 참조 (실제 마이크 20+20, barge-in, speaker AEC, STT-06 등).
- dev PC 추가 완료: B3 3종 배선·설치본 배지, B0-2 VRAM/NVENC, B0-3 x264
  및 설치 Electron matched 모델 render A/B
  (`완료/AIRI-B3-ELECTRON-MODERATION-VERIFICATION-2026-08-12.md`,
  `완료/AIRI-B0-RESOURCE-MEASUREMENT-2026-08-12.md`,
  `완료/AIRI-INSTALLED-MODEL-RENDER-AB-2026-08-12.md`).
