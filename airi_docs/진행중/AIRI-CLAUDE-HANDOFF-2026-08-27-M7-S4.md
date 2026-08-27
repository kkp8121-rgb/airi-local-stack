# AIRI Claude 인수인계 — M7 S4 사람 채점 대기 및 세션 종료 (2026-08-27)

> 이 문서는 현재 세션을 중단하고 Claude에 전달하는 단일 작업 안내입니다. 먼저
> `AGENTS.md` → `airi_docs/진행중/AIRI-WORKING-STATE.md` 전체 → 이 문서 →
> `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md` → `NEXT-SESSION.md` 순서로 읽고,
> 실제 Git SHA·worktree·프로세스·listener·외부 replay 산출물을 read-only로 대조하십시오.
> 문서와 기계 상태가 다르면 실행하지 말고 관측값으로 문서부터 정정하십시오.

기계 판독 계약: `goal_status=paused`; `adoption_authorized=false`;
`execution_order=P0_A>P0_B>E2_LAUNCH>E2_PROVENANCE>PACKAGE>T3_36>CAMPAIGN_3X500>USER_DECISION`

## 1. 현재 결론

- 사용자 요청으로 M7 후속 모니터링은 중단하고 이 handoff를 전달합니다. 운영 flag, S5,
  GPU 학습, 파인튜닝은 실행하지 않습니다. 파인튜닝 금지는 2026-09-09까지 유지합니다.
- S2는 `[F]`입니다. 대표 r2 사람 채점은 99/99턴·3축 2.2290·critical 0·filler
  76.77%로 동결 게이트를 통과하지 못했고 채택하지 않습니다.
- S3는 `[x]`입니다. 대표 r2 사람 채점은 99/99턴·3축 3.0976·critical 0·filler
  14.14%로 게이트를 통과했지만 `AIRI_BROADCAST_EXAMPLES` 기본값은 OFF입니다.
- S4는 `[P]`입니다. 구현·회귀·CI 등록과 고정 07 replay r1/r2/r3가 완료됐고,
  세 회차는 exit 0·99턴·empty/service_error/invented_handle/polite_violation 0,
  `skipped=30`, `batched=0`입니다. q_end 5/13/22의 사전 등록 대표는 r2입니다.

## 2. 증거 위치와 Git 상태

- 대표 평가표: `D:\AIRI-Models\airi-human-eval\20260826-replay-07-s4-r2\rating-sheet.html`
- S4 외부 root: `D:\AIRI-Models\airi-human-eval\20260826-replay-07-s4-r1..r3`
  (각 root의 runtime/health/report/packet/runner/review/rating-sheet를 보존)
- 인계 작성 전 관측 HEAD: `cfb7fd41819cbfad5536ab3aa55e1d8f631c49c7`;
  local/origin/remote main이 일치했습니다. 이 handoff 배치는 사용자의 명시 승인으로
  commit/push합니다. Claude는 시작할 때 실제 SHA를 다시 읽으십시오.
- 저장소에는 실제 채팅 원문·코멘트·개인 오디오를 기록하지 않습니다.

## 3. 대기 중인 유일한 다음 변수

S4 r2 평가표에 사람이 저장한 JSON이 나타나는지뿐입니다. 현재 S4 사람 JSON은 없습니다.
JSON이 생기면 아래 순서만 수행하십시오.

1. 99/99턴, 고유 turn 1..99, 스키마와 점수 범위를 검증합니다.
2. `summarize_ratings.py`로 공식 요약과 동결 게이트를 계산합니다.
3. S2 `[F]`·S3 `[x]`를 보존한 채 S4 채택 여부를 `AIRI-ROADMAP-STATUS.md`,
   `AIRI-ROADMAP-LOG.md`, `AIRI-WORKING-STATE.md`, `NEXT-SESSION.md`와 이 handoff에 기록합니다.
4. 결과와 다음 한 변수만 보고 멈춥니다. 자동 점수 추정, replay 재실행, S5, GPU,
   파인튜닝, 운영 flag 활성화는 하지 않습니다.

## 4. 재현·금지 경계

- S4 replay를 다시 실행하지 마십시오. 새 사람 JSON이 없는 동안 품질을 추정하지 마십시오.
- 운영 모델·태그·flag를 바꾸지 마십시오. GPU 학습·파인튜닝·합성 blind matrix·S5는 금지입니다.
- push는 이번 사용자 요청으로만 허가된 현재 문서 배치에 한정됩니다. 이후 push는 별도
  사용자 승인이 필요합니다.
- 이 문서 자체의 최종 commit SHA를 미리 자가 참조하지 마십시오. Claude는 원격을 직접
  확인하고, 문서의 `goal_status=paused`와 실제 worktree를 대조해야 합니다.
