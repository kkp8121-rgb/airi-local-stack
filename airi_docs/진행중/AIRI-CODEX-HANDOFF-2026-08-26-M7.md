# AIRI Codex 인수인계 — M7 타계책 실행 (2026-08-26 21:10 KST)

> **다음 세션 단일 진입점.** 세션 시작 시 `AIRI-WORKING-STATE.md` 전체 → 이 문서 → `로드맵/AIRI-ROADMAP-STATUS.md`
> 순서로 읽고, `git status`·HEAD·PID·산출물 sha를 read-only로 대조한 뒤에만 실행한다. 이전 인계
> (`AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md`, `AIRI-CODEX-HANDOFF-2026-08-21.md`)는 이력이며 진입점이 아니다.

기계 판독 계약: `goal_status=active`;
`execution_order=RUN07_R2_HUMAN_RATING>BASELINE_DELTA_JUDGE>NEXT_SINGLE_VARIABLE_ON_07_CONFIG>OPTIONAL_S5_QWEN_DIAGNOSTIC>FINETUNE_REENTRY_CHECK`

## 0. 오늘(08-26) 하루의 결론 — 무엇이 증명됐나

1. **합성 blind 루프 폐기(사용자 결정 C)**: 채택 게이트는 실제 채팅 사람 채점 하나다
   (`AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md` §4; 돌파 정의 3축 합성 ≥3.0·critical 0·filler ≤25%).
2. **S0 — n=1 비교는 무효**: 같은 구성 4회 재생에서 "?" 종결 15~84, "음" 오프너 1~89(SD ≈30/99). 픽업은 결정론
   (rows.message_id, 16 run 동일), 생성은 하니스 seed 20260818로도 비재현. 후보 비교는 **복제 ≥3의 붕괴 빈도·분포**로 읽고,
   사람 채점은 사전 등록 규칙("?" 종결 중앙값 replicate)으로 고른 1회만 한다. 자동 시그니처는 표시 전용(판정·kill 금지).
3. **S1 — 되먹임은 증폭기, 원인 아님**: 되먹임 3채널(foreground `_short_direct_answer` 유지, journal assistant 회수, 하니스
   브리핑 `→ 나:` 에코)을 다 끊으면 템플릿 고정("음... 뭐가 X인데?")은 0/3이 되지만 **문구 고정**(한 문장 28~78회)은 남는다.
   사람 채점 06b-r3: 3축 1.90(기준선 1.76, +0.14) — 채택 미달, S1 단독 기각. proxy flag `AIRI_FEEDBACK_HYGIENE`(`098c887`)는
   병합됐으나 **기본 off이고 운영 on 요청 없음**.
4. **S6 — 입력 정합이 진짜 돌파구**: 재생 채팅은 원 방송 화면·발화에 대한 반응이다. VOD 스트리머 발화(로컬 STT 618세그먼트)를
   픽업 직전 45초 assistant 턴으로 공급(`--replay-transcript`, `5a5e225`)하자 **run 07 3복제 전부 무붕괴**(최빈 응답 8/3/3,
   고유 77/93/96 — 첫 arm)이고 화면 맥락 정답이 최초로 나왔다(서버 장애·트래커 눕기·링피트·장갑). Claude 참고 채점 07-r2:
   3축 2.37(+0.62)·filler 40%·critical 0. **판정은 사람 채점(대기 중)**.
5. **M7-10 안전 가드**: 의혹·루머 질문 + 선행 긍정 → "그런 얘기는 내가 확인한 적 없어."로 교체(`f48b1ed`,
   `deflect_leading_affirmation`, 계층 마지막 단계). run 07-r2 24턴 실전 발동 — 단 이어지는 문장이 발화를 반쯤 시인하는 한계
   확인(후속 후보: 민감 질문에서 후속 문장도 차단할지는 사람 채점 뒤 1변수로).
6. **파인튜닝은 2026-09-09까지 금지**(`AIRI-BREAKTHROUGH-PLAN-2026-08-26.md` §2). 재진입 조건 전부: S1~S5 뒤 3축 <3.0 +
   S5 진단에서 큰 모델 +0.6 이상(용량 병목 실측) + 실제 채팅 입력·사람 4점 이상 검증 답변 ≥300턴(채점 루프 산출만).
7. 업스트림 moeru-ai/airi v0.12.0-beta.1·main(+222)에는 이 병목 관련 변경 없음(결정 큐 22).

## 1. 다음 작업 (순서 고정, 한 run 한 변수)

1. **run 07-r2 사람 채점** — `D:\AIRI-Models\airi-human-eval\20260826-replay-07-r2\rating-sheet.html`(99턴). 저장 JSON을
   `ratings-human.json`으로 복사 → `summarize_ratings.py --baseline`(run 04 `summary-human.json`) → +0.2 이상·filler 비악화면
   **07 구성(hygiene on + 브리핑 에코 차단 fixture + 전사 공급)을 평가 기본 구성으로 채택**하고 ROADMAP M7-11 `[x]`.
2. 다음 1변수(07 구성 위, 복제 3회 + 사전 등록 1회 채점): 우선 후보는 (a) "응, X!" 내용 없는 긍정 에코 대응(S3 예시 4쌍 —
   규칙 문장 추가 금지, 반말 U/A 예시 모방 채널) 또는 (b) 문장 끊김("...") 대응. 타계책 §3 금지 목록 준수.
3. 선택: S5 모델 축 1회 진단(qwen3:8b, TTS 미기동·전량 GPU 적재 확인·think off·같은 샘플링·seed 2개, **채택 아님**).
4. 판정·기록 규율: intent→실행→receipt, 배치마다 ROADMAP-LOG, 대시보드 계약
   (`test-airi-roadmap-dashboard-contract.ps1`)·work-continuity·`test-current-checkpoint.ps1` PASS 후 commit. push는 매번 별도 승인.

## 2. 재현 명령과 자료 (전부 저장소 밖, Git 반입 금지)

- **도구 사본**(`D:\AIRI-Models\airi-eval-tools\20260826\`, 세션 scratchpad에서 복사; sha 앞 16자):
  `run_replay.ps1` abe9ed6601e4143d(스택 기동→99턴 재생→정지 런처; `-FeedbackHygiene on`, `-Fixture`, `-ReplayTranscript`,
  `-TranscriptWindowMs`), `run_s6.ps1` 4f311f7c(run 07 드라이버), `stt_vod.py` 4836e731(faster-whisper large-v3-turbo CUDA;
  torch lib PATH 필요: `external\GPT-SoVITS\.venv\Lib\site-packages\torch\lib`), `s0_signatures.py` 88eb0c6e(표시용 시그니처),
  `transcript_coverage.py` 5b66aece, `real_chat_fixture_no_self_echo.json` f850dc38(원본 fixture에서 `briefing.min_echo_response_chars`
  =10^9만 변경), `claude_prelim_rating_07_r2.py` 659b74c2(참고 채점 예시).
- **run 07 표준 구성**: `run_replay.ps1 -ReplayJsonl D:\AIRI-Models\airi-real-chat\pseudo-korean\chzzk-12901656.jsonl
  -RunRoot <새 경로> -MaxTurns 100 -MaxMessages 1500 -NumCtx 4096 -FeedbackHygiene on -Fixture <no_self_echo 사본>
  -ReplayTranscript D:\AIRI-Models\airi-real-chat\vod\chzzk-12901656-0-3625.stt.jsonl` — RunRoot는 재사용 금지(no-overwrite).
- **자료 sha**: 재생 채팅(가명) 21896a49242ea98f, 스트리머 전사 7ed54d6121097a56(618세그먼트, VOD 절대 ms). VOD 오디오·전사는
  `D:\AIRI-Models\airi-real-chat\vod\`. run 산출물: `D:\AIRI-Models\airi-human-eval\20260826-replay-*`(04=기준선, 05=A+B,
  05r*=off 복제, 06a/06j/06b=S1 arm, 07-r*=S6), 시그니처 집계 `20260826-m7-signatures\signatures.{json,md}`.
- **채점 파이프라인**: `export_session_dialogue.py --db <RunRoot>\runtime\memory.sqlite3 --all-sessions --output review.jsonl` →
  `build_rating_sheet.py` → 사람 채점 JSON → `summarize_ratings.py --ratings … --baseline …`(3축 합성·delta 내장, `f748cae`).
- **고정 인터프리터**: pytest `D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe`; proxy unittest WindowsApps
  `python.exe`(3.14, httpx); 재생 runner `C:\Projects\airi\stt\.venv\Scripts\python.exe`(3.11, httpx). 기본 `python`(3.14)은 pytest 없음.

## 3. 금지 (타계책·계약에서 확정)

- 계약 규칙 문장 추가·문형별 땜질·메모형 브리핑 줄 추가·저널 시청자 행 주입 금지. 한 run 두 변수 금지.
- blind v1~v7 합성 매트릭스 부활 금지. 정규식·시그니처로 사람 채점 대체 금지.
- 운영 채택(모델·태그·flag on)·GPU 학습·push는 각각 별도 사용자 승인. 실제 채팅 본문·닉네임·원 영상 식별자는 Git·문서에 금지
  (HMAC 가명·sha만). qwen3:8b 운영 승격 금지(TTS와 8GB VRAM 공존 불가).
- 알려진 flake: `test-airi-training-durability.ps1`은 백그라운드 부하 중 간헐 실패(2회 관측), 단독 재실행 PASS — 실패 시 단독
  재실행으로 확인. Bash heredoc에 백슬래시 포함 텍스트 금지(BEL/octal 변환 실측) — 스크립트는 파일로 작성해 실행.
