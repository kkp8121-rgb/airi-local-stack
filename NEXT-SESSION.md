# AIRI 다음 세션 안내

**진입점은 세 개다** (2026-08-21 v4 GPU 인계 갱신):

1. `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md` — **현행 GPU 인계 단일
   SSoT.** runtime-shaped v4 1,000행의 exact SHA, E1 완료 결과, 사용자 요청으로
   중단한 E2의 재실행 명령, merge/GGUF 핀, calibration 2종+blind 180분 T3의
   36-report 행렬, 이후 3×500 live campaign 순서를 고정한다. 현재 E1은
   `adoption_authorized=false`, `t3_status=pending`이며 서비스 모델은 바꾸지 않았다.
   코덱스든 클로드든 먼저 이 문서부터 읽는다. 08-20판의 greybox·추출 이력은
   근거로 보존하지만 방송 GPU 작업 상태는 새 문서가 대체한다.
2. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md` — **최상위 SSoT.** 북극성·
   주 지표(발화 실질)·돌파 3축(P1 쇼 러너 브리핑 / P2 결정론 발화 /
   P3 조건부 생성 상한)·사용자 결정 큐·코덱스 대기열이 전부 여기 있다.
3. `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` — 문서 지도.

행동 재설계 근거: `airi_docs/참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md`.
기계 판독 관찰 데이터는 `airi_docs/참조/data/`, AIRI 원본 파일럿은
`ollama-proxy/training/seed/airi_broadcast_response_pilot_pending.jsonl`이다.

병행 지시서: `airi_docs/진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md`
(코덱스 PC Serena MCP 도입 — 이 인계문과 독립).

최근 배치 이력은 `airi_docs/로드맵/AIRI-ROADMAP-LOG.md`(최신이 위).
**매 배치 커밋마다 LOG에 기록**하고, STATUS는 상태 변화 시에만 고친다.
과거 인계 문서(2026-08-13 이전)는 전부 `airi_docs/아카이브/`로 이동했다 —
현재 상태 검증에 사용 금지.

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
