# AIRI Documentation Index

문서는 상태별 폴더로 분류한다 (2026-08-12 재구성). 파일명은 유지했으므로
과거 문서가 언급하는 파일은 이름으로 검색하면 찾을 수 있다.

## 폴더 구조

| 폴더 | 의미 | 규칙 |
|---|---|---|
| `진행중/` | 현행 계약·미해결 게이트가 남은 문서 | 여기 있는 문서의 주장은 현재 브랜치 상태로 취급한다 |
| `진행예정/` | 승인됐거나 제안된 계획 (미실행 분량 존재) | 착수 전 반드시 정독 |
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
  **미해결 게이트**: model SSoT 강제(프록시에 EXAONE 하드코딩 폴백 3곳),
  eval provenance, ACK metadata, digest pin, 인간 검수 100건.
- `AIRI-LOCAL-TECH-SPECS.md` — 현행 스펙 문서. ⚠️ **stale** (STT=CPU·
  EXAONE·Chatterbox 기재 — 실제는 GPU STT·Mi:dm·GPT-SoVITS). 갱신 대상.

## 진행예정 — 계획

- `AIRI-BROADCAST-CHARACTER-PLAN-2026-08-12.md` — 지능·캐릭터성·방송 통합
  계획. **사용자 결정 4건 대기** (관계 축·방송 중 클라우드 LLM·캐릭터
  확정·목표 시점). 근거는 `참조/AIRI-BROADCAST-RESEARCH-2026-08-12.md`.
- `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md` (v2.1) — 마스터 계획. §6 지연 예산·
  §12 완료 기준은 실측 후 재정의 제안(첫 반응 ≤1.5s / 본답변 ≤2.5s)과
  공존 중 — 공식 개정은 사용자 결정 사항.
- `AIRI-EXAONE-GROWTH-STRATEGY-2026-08-07.md` — **사용자 승인 방향.**
  G0~G6 성장 로드맵 (G1 캐릭터 루프 → G2 장기 기억 → G3 평가 플라이휠 →
  G4 파인튜닝 → G5 자발 행동·방송 디렉터 → G6 게임 에이전트).
- `AIRI-EXAONE-MODEL-CUSTOMIZATION-PLAN-2026-08-07.md` — C0~C5 모델
  커스터마이징 게이트. (모델이 Mi:dm으로 바뀌어도 게이트 구조는 유효)

## 완료 — 유효한 증거 기록 (최신순)

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
- **예외적으로 여전히 유일한 정보원인 것**:
  - `아카이브/AIRI-WORK-CHECKPOINT-2026-08-10.md` **:88-105** — 완료된
    소스 빌드와 설치본 SHA-256의 유일한 기록. 클라이언트 작업 계획 전
    반드시 읽을 것.
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

현재 브랜치 검증은 소스·패치·오프라인 테스트 한정. 거버넌스 토픽 보드
생성, 실제 마이크 텍스트 전송, 원시 ID·대화 노출, 재생 시작 증거의 자연
종료 해석 금지.

## 최신 검증 증거 (2026-08-12)

- 통합 Python: 733 passed / 1 skipped / 504 subtests (검토 PC 실측).
- `node --test test-send-airi-local-text.mjs`: 27/27.
- `test-current-checkpoint.ps1`: PASS. 3층 런타임 패치가 핀 checkout에서
  정방향·역방향 적용 통과.
- Upgrade Scout 클라이언트: Stage UI·Tamagotchi 타입검사 + 집중 42 테스트
  통과. 최신 `main` 포팅 브랜치: 25/25 빌드 + 집중 168 테스트.
- CI: `offline-contracts` + `python-core-tests` 두 job green
  (tip `a231ab0` 기준; 이후 커밋은 push 시 재검증).
- 실기 게이트 미통과 항목은 `완료/AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md`
  §판정 참조 (Mi:dm first-audible, 실제 마이크 20+20, barge-in 등).
