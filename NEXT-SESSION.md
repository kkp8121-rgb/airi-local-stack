# AIRI 다음 세션 안내

> **2026-08-22 goal resume:** 사용자 `/goal` 명령으로 AIRI 본 goal은 `active`다.
> 운영 모델 채택과 기본 서비스 모델 변경만 별도 사용자 승인 전까지 금지한다.
> 전원 종료 복구용 P0 checkpoint/resume/durable runner/safe-pause 계층을 먼저
> 구현·실증한 뒤에만 E2를 시작한다.
> `goal_status=active`; `adoption_authorized=false`
> `execution_order=P0_A>P0_B>E2_LAUNCH>E2_PROVENANCE>PACKAGE>T3_36>CAMPAIGN_3X500>USER_DECISION`

**진입점은 네 개다** (2026-08-22 live-state 지속성 규칙 추가):

1. `airi_docs/진행중/AIRI-WORKING-STATE.md` — **가장 먼저 읽는 live SSoT.**
   세션 시작·goal resume·재부팅·compact 직후 실제 goal status, HEAD/worktree,
   PID, 산출물과 대조하고 불일치하면 이 문서를 먼저 정정한다. active goal에서는
   최대 60분 heartbeat와 단계 전후 intent/receipt checkpoint를 유지한다.
2. `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md` — **현행 GPU 인계 단일
   SSoT.** runtime-shaped v4 1,000행의 exact SHA, E1 완료 결과, E2 전 P0 내구성
   게이트와 중단한 E2의 step 0 재실행 명령, merge/GGUF 핀, calibration 2종+blind 180분 T3의
   36-report 행렬, 이후 3×500 live campaign 순서를 고정한다. 현재 E1은
   `adoption_authorized=false`, `t3_status=pending`이며 서비스 모델은 바꾸지 않았다.
   코덱스든 클로드든 먼저 이 문서부터 읽는다. 08-20판의 greybox·추출 이력은
   근거로 보존하지만 방송 GPU 작업 상태는 새 문서가 대체한다.
3. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md` — **최상위 SSoT.** 북극성·
   주 지표(발화 실질)·돌파 3축(P1 쇼 러너 브리핑 / P2 결정론 발화 /
   P3 조건부 생성 상한)·사용자 결정 큐·코덱스 대기열이 전부 여기 있다.
4. `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` — 문서 지도.

행동 재설계 근거: `airi_docs/참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md`.
기계 판독 관찰 데이터는 `airi_docs/참조/data/`, AIRI 원본 파일럿은
`ollama-proxy/training/seed/airi_broadcast_response_pilot_pending.jsonl`이다.

토큰 실측 기록: `airi_docs/진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md`.
Serena MCP는 로컬 A/B 순손실로 등록 롤백됐고 Caveman trial은 미실행이다.

최근 배치 이력은 `airi_docs/로드맵/AIRI-ROADMAP-LOG.md`(최신이 위).
**매 배치 커밋마다 LOG에 기록**하고, STATUS는 상태 변화 시에만 고친다.
과거 인계 문서(2026-08-13 이전)는 전부 `airi_docs/아카이브/`로 이동했다 —
현재 상태 검증에 사용 금지.

현행 순서는 GPU 인계 §8의 체크리스트 한 곳만 따른다:
`P0 전원 종료 내구성 구현·실증 → E2 preflight/step 0 → provenance →
E1/E2 merge/package → 36 T3 → 승자 3×500 →
실제 응답·증거 제출 → 사용자 채택 판단`.

## 운영 기본값 (변경 시 이 절 갱신)

- Chat model: Mi:dm (`midm-airi:2.0-mini`) digest pin 유지 (사용자 결정 6)
- `num_ctx=2048` (주의: 고정 주제 블록+카드 병합 시 2,246토큰 — 시뮬레이션
  실측은 4096 필요. 예산 재배분은 P1 과제)
- 방송 기본 프로파일: chat/text 입력, STT/마이크 OFF (마이크는 사용자
  "마이크 테스트 시작" 요청 시에만 `-Stt on`)
- 기억 추출 OFF (통과 extractor 없음 — 다음 수순은 Stage A 재설계이지
  모델 확대가 아님)
- 런처 기본 ON (2026-08-19 `3ead135`, 사용자 결정 5·6 완료): `AIRI_IMMEDIATE_ACK=marker`·
  침묵 폴백 풀·방송 계약 v3·기억 가드(`AIRI_MEMORY_CLAIM_GUARD`).
  output moderation은 기본 OFF 유지
- 기억 추출 greybox 3종 기본 OFF·런처 미노출 (`AIRI_MEMORY_EXTRACTION_STAGE_A_CONTRACT`·
  `_ALIAS_RESOLUTION`·`_TAXONOMY_GATE`) — 켜기 전 선행 조건은 인계문 §3
- `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS`는 **유효 범위 1~30초**, 벗어나면
  경고 없이 8초로 클램프된다 (2026-08-20 실측 함정)
- 음성: 현행 일본어 참조 유지, T-05 126번 예비. 팬덤명 유보("시청자들")

## 작업 원칙 (v3)

- 모든 배치는 STATUS §1 더하기 지표 중 하나를 올려야 한다. 빼기
  지표(존댓말·이탈 등)는 회귀 가드로만 확인한다.
- 프롬프트 지시보다 결정론 계층 우선 (상한 2회 실증 — dn04·gr01).
- 완료·통과 주장은 직전 fresh 실측 증거 동반. raw 경로 시뮬레이션은 검토
  근거 불인정(11435 게이트 경유 의무 — 사용자 결정 7).
