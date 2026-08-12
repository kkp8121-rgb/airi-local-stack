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

- `AIRI-FINAL-HANDOFF-2026-08-10.md` — 패치·sender 계약과 검증 경계.
- `AIRI-SERVER-CHANNEL-PLAYBACK-CHECKPOINT-2026-08-10.md` — 취소·상관·
  재생 시작 증명의 권위 문서.
- `AIRI-GROUNDED-DIALOGUE-QUALITY-HANDOFF-2026-08-12.md` — 그라운딩 품질
  후속 계약.
- `AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md` — EXAONE→Mi:dm 전환 분석.
  게이트 중 model SSoT 강제·eval provenance·ACK metadata·digest pin은
  2026-08-12 코드·dev PC 실기 해소 완료(commit `932eae6`). 설치 Electron
  matched 모델 A/B도 완료했다. **남은 게이트**: 인간 검수 100건과 장문
  context/memory/card corpus.
- `AIRI-DEV-PC-HANDOFF-2026-08-12.md` — **검토 PC 선행 작업 배치의
  인수인계.** SSoT·I1 실측 및 B3 배선 3종은 완료; B0-1과 사람·자격증명
  게이트 등 잔여 dev PC 작업을 관리한다.
- `AIRI-CLOUD-CHAT-LATENCY-MEASUREMENT-2026-08-12.md` — cloud streaming
  latency 하네스·테스트와 live TTFT 보류(API key·외부 승인) 현황.
- `AIRI-LOCAL-TECH-SPECS.md` — 현행 스펙 문서. 2026-08-12 갱신 완료
  (STT=large-v3-turbo GPU·LLM=midm-airi:2.0-mini·TTS=GPT-SoVITS 반영,
  롤백 태그·SSoT 실기 결과·확인 필요 항목 명시).

## 진행예정 — 계획

- `AIRI-BROADCAST-CHARACTER-PLAN-2026-08-12.md` — 지능·캐릭터성·방송 통합
  계획. 사용자 결정 중 1·4 확정, 2 조건부, 3은 팬덤명 충돌 FAIL과 T-05
  청취 때문에 부분 완료 상태다. 근거는
  `참조/AIRI-BROADCAST-RESEARCH-2026-08-12.md`.
- `AIRI-CHARACTER-CONSTITUTION-DRAFT-2026-08-12.md` — C1 캐릭터 헌법
  초안 v4. **결정 1·3 반영(2026-08-12), 코드 미반영**. 정체성(이름 AIRI
  확정)·가치관·말버릇 후보·관계 규정(안 B 채택 + 메타 서사 "사장님"
  절)·리액션 톤 3단계를 포함하며, `AIRI_SYSTEM_PROMPT`를 대체하지 않고
  확장한다. 남은 확정: 팬덤명 재선정·T-05 후보 청취 검토·인간 검수.

## 로드맵 — 지도와 현황판 (상태 폴더와 별개 관리)

- `AIRI-ROADMAP-STATUS.md` — **살아있는 현황판.** G0~G6·C0~C5·지연·M1~M5
  전 축의 상태와 근거, 사용자 결정 차단 지점, 배치별 갱신 로그.
  **매 작업 배치 커밋마다 갱신 의무** (검토 PC·dev PC 공통).
- `AIRI-GROWTH-STRATEGY.md` — **사용자 승인 방향.**
  G0~G6 성장 로드맵 정의 (G1 캐릭터 루프 → G2 장기 기억 → G3 평가
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
  화자 후보 3종 샘플(사용자 청취 검토 대기).
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

## 최신 검증 증거 (2026-08-12)

- 통합 Python: 816 passed / 1 skipped / 706 subtests (dev PC 재실측,
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
