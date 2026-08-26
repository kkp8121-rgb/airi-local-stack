# AIRI 다음 세션 안내

> **2026-08-26 17:25 KST 최우선 — M7 S0·S1 완료(`진행중/AIRI-M7-S0-S1-RECEIPT-2026-08-26.md`): 복제 3회 기준 되먹임 고리 3채널 차단 시 붕괴 0/3(off 3/4).
> **정정(2026-08-26 17:32):** 문구 고정은 2/3에 남고(비트 큐 되풀이), 참고 채점 06b-r3 3축 1.59 < 기준선 1.76 — 개선 없음. 되먹임은 증폭기,
> 원인은 맥락 빈곤 입력. **사람 채점 확정(2026-08-26 17:54): 06b-r3 3축 1.90(+0.14), filler 55.6%, 치명 1 — S1 단독 기각, flag off 유지.**
> **S6 실행(2026-08-26 19:10): run 07(발화 정렬 공급) 전 복제 무붕괴 — 첫 arm, 화면 맥락 정답 최초, 참고 채점 +0.62. M7-10 가드 `f48b1ed`
> 실전 발동. 사용자 결정 대기: `20260826-replay-07-r2/rating-sheet.html` 채점, 로컬 commit push 승인.**

> **2026-08-26 16:55 KST — M7 열림(타계책 실행): 로드맵 M7-1~8·원칙 5~7·주 지표 표·재진입 조건까지 반영 완료.
> 사용자 결정 대기: S0 복제 측정 승인, S1 proxy 되먹임 flag 승인, run 05 사람 채점, push.**

> **2026-08-26 16:35 KST — 타계책 확정(`진행중/AIRI-BREAKTHROUGH-PLAN-2026-08-26.md`): 병목은 코드/학습이 아니라 런타임 자기 되먹임
> 고리·재료 미수용·n=1 측정. 순서 S0 복제 측정 → S1 proxy 되먹임 차단 flag(승인 필요) → S2~S5, 한 run 한 변수, 돌파 정의
> 3축 합성 ≥3.0. 파인튜닝 2주 금지. 사용자 결정: S0·S1 승인 + run 05 사람 채점.**

> **2026-08-26 15:35 KST — A+B 적용 run 05 완료(`beb0559`): 후원 경로 결함 0, 그러나 모델의 "음... 뭐가 X인데?" 되묻기
> 붕괴(37턴)가 드러남. 사용자 채점(`D:\AIRI-Models\airi-human-eval\20260826-replay-05\rating-sheet.html`) 뒤 M6-10 결정:
> D 되먹임 위생 일반화 / E qwen3:8b 평가 전용 재생 / F 프롬프트 규칙 (`진행중/AIRI-REAL-CHAT-REPLAY-RUN05-2026-08-26.md`).**

> **2026-08-26 14:15 KST — 사람 채점 기준선 확정(run 04: 방송다움 1.87·맥락 1.58·반응 1.83·말투 3.60·사실성 2.75,
> 치명 7.1%, 무의미 대꾸 45.5%). 다음은 첫 개선 후보 결정(M6-8: A 후원 의례 오발동·축자 인용·안전 회피 / B "고마워."
> 붕괴 / C 에코 반문·챗봇 말투) → red/green → run 05 → 사람 채점 비교.**

> **2026-08-26 12:35 KST — 실제 채팅 재생 run 04 완료(기록):** 공개 치지직 저챗 채팅을
> 가명화해 운영 구성 스택에 99턴 재생했다(`진행중/AIRI-REAL-CHAT-REPLAY-RUN04-2026-08-26.md`). Claude 1차
> 참고 채점은 방송다움 1.89·맥락 1.85·반응 1.99·말투 4.03·사실성 3.99, 무의미 대꾸 44%. 핵심 결함: 후원
> 감사 문형 되먹임으로 모델이 "고마워."로 붕괴(23턴), P5 echo의 후원 본문 축자 인용(부적절 문장 포함), 따라
> 말하기. 다음: 사용자가 `D:\AIRI-Models\airi-human-eval\20260826-replay-04\rating-sheet.html`로 최종 채점 →
> `summarize_ratings.py` → 기준선(M6-7) → 첫 개선 후보 결정(M6-8, 후보: 감사 되먹임 제거/echo 요약형/되묻기 억제).
> 로컬 HEAD는 origin/main보다 2 commit 앞(`6dd8b22`, `f408eb7`) + 문서 배치; push 별도 승인.

> **2026-08-26 11:45 KST — M6 활성(사용자 4건 승인), 채택 게이트는 실제 대화 사람 채점 하나:**
> 진입점 `airi_docs/진행중/AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`(실태) + `AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md`(평가 계약).
> 완료(로컬 commit, push 미승인): `a9583c3` step 2 수리, `cdbb6eb` grounding 게이트 live-broadcast 완화
> (unittest 414 OK), `776b462` `ollama-proxy/eval/human_review/` export·채점 HTML·요약 도구(16 passed, CI
> 등록). 문서 다이어트(WORKING 235행, heartbeat 120/30분), 로드맵 v4(M6 8행 중 5 완료).
> 다음: 사용자가 비공개 테스트 방송 또는 직접 채팅 50~100턴을 캡처 → export → 채점 → 기준선(M6-6/7).
> 파인튜닝·합성 blind 매트릭스·운영 채택·push는 별도 승인 전 시작 금지. `goal_status=active`,
> `adoption_authorized=false`.

> **2026-08-26 11:29 KST — M5 피벗(사용자 결정 C), 실태 문서 진입점(피벗 기록):
> `airi_docs/진행중/AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`:** 사용자가 5라운드 blind 대화를
> HTML 뷰어로 확인한 뒤 합성 fixture 매트릭스 루프를 공회전으로 판정하고 v7 저작·matrix·campaign을
> 중단시켰다. 실태: 08-19 이후 commit 156, GPU 후보 4(채택 0), blind 6라운드 216 report 전부
> no_winner(대부분 계측·저작 결함), 운영 모델은 stock Mi:dm 2.0 Mini Q4, 실제 시청자 데이터 0, 사람
> 검수 0, 학습 데이터 100% 합성, greybox 단조 하락. **파인튜닝은 중단 권고**(재개 조건: 실제 대화
> 코퍼스·사람 채점 평가·결정론으로 못 닫는 행동 실측·일반 능력 게이트). 다음은 사용자 결정 큐 —
> 실제 대화 로그·사람 채점 세트 확보, `needs_grounding_retry` 평서문 침묵 수리 승인, 검증된 step 2
> 코드 commit 여부. POST-M4 handoff §4 Goal의 step 4~7은 대체됐다. `goal_status=active`,
> `adoption_authorized=false`, matrix·campaign·GPU·commit·push 0.

> **2026-08-26 11:20 KST — M5 활성, step 2 수리 구현(피벗 전 기록):**
> 사용자가 `AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md` §4의 Goal 명령을 Claude에 제출했다.
> 시작 대조는 HEAD/local/origin/remote `d7c6283` exact·clean, d1v6 48/48·exit 0·no_winner(29
> gate)·listener 0이다. step 1 진단(M5-1 `[x]`)은 공통 polite 43행 = sealed v6
> `aggregation_openers` 존댓말 저작 artefact, invented 5 = `모아` 동사 substring 충돌 2 + briefing
> author 라벨 grader pool 불일치 3, transition required miss 89 = proxy grounding 침묵 폴백 72/모델
> 15/`어느` 2, probe miss 32 = P3 미발동 29(회피 문구 15·추측 15)/폴백 2/근거 부재 1로 분류했다.
> step 2(M5-2 `[~]`)는 계층(`_REJECTED_BRANCH_RE` 주어 2~12자·목적격, recall 결과 보호, `자고`
> 동사, `어느`, content-free 폴백 대체 ack, P3 evidence-echo)과 harness grader pool(briefing
> handle 합산)을 red/green으로 구현했고 pre-fix `d7c6283` worktree에서 새 테스트 18+1+1 FAIL,
> 수정 tree에서 계층/guard/runtime 90 passed, broadcast_sim+launcher 251 passed, proxy/runtime
> unittest 405 OK, affect/training은 알려진 behavior-v2 2건만 실패(494 passed)다. 다음은 M5-3
> 검증 receipt → M5-4 blind v7 저작·seal(반말 opener·seal lint, seed_checks는 공개 fixture 관례).
> matrix·campaign·GPU·adoption 0, commit/push 0(`adoption_authorized=false`). 단일 진입점은 위
> Claude handoff이며 live state는 `airi_docs/진행중/AIRI-WORKING-STATE.md`다.

> **2026-08-26 10:10 KST — M4 완료, 다음 세션은 Claude POST-M4 handoff:**
> exact-once d1v6 matrix는 exit 0, report·health·run-contract·packet 48/48, duplicate/missing 0,
> 두 flag 48/48 attest, context/service error 0, owned PID/listener 0으로 끝났다. verdict는
> `winner=null`(실패 gate 29개)이라 campaign·자동 후속·운영 채택은 0이다. P5 donation과 P4
> decoy는 닫혔지만 P3 required recall, P2 잔여 호명, 공통 polite gate가 남았다. 과거 raw
> checklist 55행 중 31개 상태를 정정하고 12행을 분리해 전체 77행을 정규화했으며, 공통 계약
> 하나를 참조하는 Codex·Claude `airi-roadmap-dashboard` project skill과 invariant test를
> 검증했다. handoff §5는 문서에 고정된 기존 환경/behavior-v2 실패만 재현했고 M4 affected
> clean run과 checkpoint·continuity·dashboard·skill validator는 PASS했다. exact 13-path
> primary commit `c7500a3`, receipt `8463e80`, final sync `09de314`와 이 Claude 이관 배치를
> 사용자가 승인한 한 번의 final push로 게시한다. M4는 `goal_status=complete`, 정상 완료율
> 9/9다. 다음 단일 진입점은
> `airi_docs/진행중/AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md`이며, Claude는 파일이
> `origin/main`에서 도달 가능한지와 final HEAD/local/origin/remote exact·clean을 먼저 확인한다.
> M5는 사용자가 그 문서의 Goal 명령을 Claude에 실제로 제출한 뒤에만 시작한다.
> `adoption_authorized=false`다.

> **2026-08-25 22:55 KST 최우선 — M4 blind v6 봉인·계약·preflight·precommit PASS:** live 배선과
> P3 정규식 수리, pre-fix 실패 증명, 새 v6 저작/독립 충돌 감사/no-overwrite 봉인, body-free
> commitment·d1v6 launcher/verifier/tests/CI, 실제 comparator synthetic 48-report 검증과 fresh
> external root의 실제 `-PreflightOnly` 48/48까지 PASS했다. flag OFF exact와 P3 predicate
> P1 수리 후 fresh precommit은 proxy/runtime 403 OK, affected 435 passed/3 skipped/276 subtests,
> 독립 P0/P1/P2 0이고 exact stage 기준 patch/checkpoint/continuity/diff 계약도 PASS했다.
> 다음 순서는 WORKING intent대로 exact 20-path repo commit/push →
> detached exact-once 48-report matrix다. 현재 matrix·서비스·
> GPU 학습 0, adoption=false. 단일 진입점은 M4 handoff이며 blind v1~v6 재봉인/재사용 금지.
>
> **2026-08-25 21:39 KST — M4 Codex 인계 문서 작성:** 다음 라운드(계층 입력 배선 수정 + live
> 경로 통합 테스트 + P3 정규식 + blind v6 재측정)의 단일 진입점은
> `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-25-M4.md`다. 착수는 사용자 `/goal` 승인 뒤.
>
> **2026-08-25 21:22 KST 최우선 — d1v5 `no_winner`, 다음 라운드는 사용자 결정:** 계측은
> 이제 실제로 작동한다(service_error 0, probe 36/40). 남은 실패의 근본 원인은 **결정론 계층이
> 운영 live 경로에서 브리핑·후원 note를 못 받는 배선 결함**(`build_layer_inputs`에 주입 전
> 메시지만 전달)이다. 다음 라운드 후보: ① 주입 후 메시지 또는 `context_note`를 계층 입력에
> 전달 + runtime이 브리핑 마커 부착 + live 경로 통합 테스트, ② P3 `_REJECTED_BRANCH_RE` 1글자
> 토큰·띄어쓴 구 확장, ③ blind v6(handle을 주제 어휘와 분리) 봉인 후 재측정. 어느 것도 승인
> 없이 시작하지 않는다. 상세: contract §7, D1 handoff 머리글, WORKING 21:22 receipt.

> **2026-08-25 17:05 KST 최우선 — M2 goal 완료, 다음은 사용자 결정 3건:** ① 프롬프트 마커·
> `num_ctx` 4096으로 프롬프트가 바뀌어 과거 blind와 비교가 끊겼으므로 **새 blind v5 봉인 →
> 4-arm 48-report 재측정** 여부(GPU 학습 불필요, ~3.5h). ② lm-eval 일반 능력 게이트(≤2%p)
> 강제 여부 — 기준선은 `완료/AIRI-M2-GREYBOX-EVAL-2026-08-25.md`. ③ CI matrix에 있는
> `eval/test_airi_native_baseline.py` 픽스처 핀 불일치(변경 전부터 실패) 수리. 어느 것도
> 승인 없이 시작하지 않는다.

> **2026-08-25 16:24 KST 최우선 — M2 배치 A 완료(`num_ctx` 4096 · F7 코드 게이트 · 검토 문서
> 편입), 배치 B(lm-eval·perplexity greybox) 진행:** M1에서 확정한 프록시 400
> `exceed_context_size_error`의 고정비 원인이 GGUF 내장 KT 프리앰블(≈514토큰, GPU PC
> 패키징 태그에서 재검증)임을 `참조/AIRI-CLAUDE-REVIEW-2026-08-25.md` §5로 확인하고
> `num_ctx` 기본값을 4096으로 올렸다. `run-airi-live-broadcast-campaign.ps1`은 이제 필수
> `-ComparatorVerdict`/`-ModelManifest`로 blind 승자 arm의 exact tag/digest가 아니면 서비스
> 기동 전에 거부한다(R2 F7 종결). 재측정은 새 blind가 필요하며 별도 승인 사항이다.

> **2026-08-25 13:05 KST 최우선 — D1 종결(`no_winner`), 다음 행동은 사용자 지시 대기:**
> 48-report matrix는 12:38:14 KST exit 0으로 완주했고 comparator는 `winner=null`이다.
> goal의 `no_winner` 경로대로 **3×500 campaign을 실행하지 않았고 자동 후속 라운드도
> 시작하지 않았다.** 실패 root `D:\AIRI-Models\airi-d1-blind-matrix-20260825\` 보존,
> blind v4 소비·재사용 금지, adoption=false 유지다.
>
> **다음 세션이 먼저 알아야 할 것: 이번 라운드는 게이트를 측정하지 못했다.** 전 arm
> 턴의 33.9~35.3%가 프록시 `LOCAL_ERROR_DIALOGUE`라 모델 발화가 없었고(세 blind 라운드
> 공통, `summary.fallback` 미계수), P3 `answer_recall_question`이 `continuity_callback`
> 320행 중 176행을 회수 폴백으로 대체했다(D1 신규 회귀). 그 결과 `long_callback`·
> `complete_show_arc`·`memory_probe`·`unknown_identity_safe`가 전 arm 정확히 0.0이다.
> 따라서 **게이트 임계값이나 모델 체급을 논하기 전에 계측 2건을 고쳐야 한다** —
> ① 프록시 오류율의 근본 원인(프록시 stdout을 남기는 짧은 재현 실행 필요, GPU 불필요),
> ② P3 발동 범위 축소. 둘 다 코드 계층이고 GPU 재학습이 필요 없다. 어떤 것도 사용자
> 승인 없이 시작하지 않는다. 상세: `진행중/AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md`
> §6, `진행중/AIRI-D1-CODEX-HANDOFF-2026-08-25.md` §0·§2.3, WORKING-STATE 13:05 receipt.

> **2026-08-25 10:27 KST 최우선 — D1 실행 감독을 Claude Code가 인수:** detached
> wrapper PID 7832는 exact command 그대로 live이고 reports/health 15/48, stdout
> 75,211 B, stderr 0 B, exit receipt absent다. Codex monitor subagent만 중단했고 matrix·
> 서비스 제어는 0이다. blind v4는 이미 소비됐으므로 launcher/wrapper를 재실행·재시도하지
> 않는다. Claude는 `airi_docs/진행중/AIRI-D1-CODEX-HANDOFF-2026-08-25.md` 하나를 단일
> 진입점으로 읽고 PID/로그/report를 read-only 감시한 뒤 48/48에서 기존 comparator
> verdict 분기를 수행한다. Codex는 이관 후 감시·verdict·campaign을 수행하지 않는다.

> **2026-08-25 09:26 KST 최우선 — D1 preflight PASS, detached matrix intent 직전:**
> `d1` 4-arm/48-run 프로파일과 guard+deterministic layer 이중 health attestation을
> 구현·검증해 `9e6b1f4`+receipt `a510004`로 origin/main push했다. external D1 matrix
> root와 model manifest(SHA `050ae10f...e330`)를 만들고 `-PreflightOnly` 48/48 unique
> key·blind v4 binding을 통과했으며 run/응답 생성은 0이다. 다음 순서는 exit-code
> receipt wrapper 고정 → WORKING-STATE matrix intent commit/push → detached 실행
> 정확히 1회다.

> **2026-08-25 07:10 KST 최우선 진입점 — D1(결정론 계층) 3/5 단계 완료, 코덱스 인계
> 중:** 사용자 승인 goal D1은 **GPU 학습 없이** 결정론 계층으로 hard/perfect 게이트를
> 닫으려는 라운드다. 완료: (1) 계층 설계 동결, (2) `deterministic_utterance_layer.py`
> 구현(P1 history 근거 확장 / P2 과거-전용 토큰 가드 / P3 결정·사실 회수 렌더러 /
> P4 거부-옵션 억제 / P5 후원 echo, 기본 off·off 무변화, 프록시 3번째 gate + /health
> 노출), (3) blind v4 봉인 + D1 commitment/policy/verifier + 4-arm comparator +
> CI 등록. 남은 것: **launcher `d1` 프로파일(3 arm/36 → 4 arm/48 일반화, 가드+계층
> 두 플래그 ON 강제, attestation schema) → 48-report matrix → winner면 3×500
> campaign / no_winner면 진단 후 대기.**
>
> **인계 문서 하나만 보면 된다: `airi_docs/진행중/AIRI-D1-CODEX-HANDOFF-2026-08-25.md`**
> (남은 단계의 exact 지시, 봉인 pin, model manifest 값, 환경 함정까지 포함). 설계
> 원문은 `AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md`. HEAD=origin/main
> `a3f2f39`, GPU/AIRI PID 0, adoption=false 유지.

> **(이력) 2026-08-25 02:40 KST — E2-C2 NO_WINNER 종결:** 언더트레이닝 교정 후보 E2-C2(E2 adapter init, 1536 microsteps/96 opt steps
> = 3 epochs, LR 2e-5, frozen dataset 그대로)는 학습 자체는 이상적으로 끝났다 — dev
> loss 2.0723→1.8219→1.6105 3 epoch 단조 하강(E2-C1 2.2351 대비 -0.62), smoke/merge/
> Q4_K_M 패키징 전부 exit 0. 그러나 새 blind v3(직조 공방/간이역 신호소/가마터, 가드
> 신호 ON 측정, 전 run /health attest)에서 **winner=null, 후보 score 0.1875 < E2
> 0.2019(첫 역전)**, improved additive 2/5, invented_handle 14/27/33(가드 신호 ON에도
> 학습 단조 악화), 13개 게이트 전부 실패. 진단 3축: ① dev 개선↔blind 후퇴 절연 =
> 교정 480행의 좁은 도메인에 6× 선량이 표면 과적합(형식화된 donation composite만
> 0.458→0.583 개선) ② invented_handle 경향은 행동 학습의 구조적 부작용(채점기 보정은
> 절대 수를 낮췄지만 기울기를 못 바꿈) ③ 전 arm이 절대 최소선의 2-4배 미달 — E2-C1/
> E2-C2 두 후보로 "선량·LR 재조정으로는 안 닫힌다"가 실증됨. campaign·adoption 금지
> 유지, 실패 root `D:\AIRI-Models\airi-e2c2-blind-matrix-20260824\` 보존, blind
> v1/v2/v3 전부 소비(재사용 금지). **자동 E2-C3는 goal 금지 조항으로 시작하지 않았다.**
> 다음 후보 방향(예: 교정 데이터 도메인 다변화, 결정론 계층 확대, 게이트 체계 재설계
> 논의)은 사용자 결정 후 새 `/goal`로 시작한다. 상세: E2-C2 contract §7, handoff §-8,
> ROADMAP-LOG 2026-08-25.

> **(이력) 2026-08-24 16:33 KST — E2-C1 NO_WINNER 진단 완료, 가드+채점기 수정
> SHIPPED, 다음은 E2-C2 설계:** E2-C1 36-report blind matrix는 `winner=null`로
> 끝났다(score는 최고지만 `invented_handle` 위반 28→40→53으로 학습할수록 악화, hard/
> legacy/perfect-rate 13개 게이트 전부 실패). 사용자 승인 goal로 원인을 진단한 결과,
> 53건 중 47건(89%)은 실제 memory 회수가 정확했는데 채점기가 그 근거를 볼 수 없어
> 오분류한 경우였다 — 모델이 이름을 지어낸 게 아니었다. 이어서 forensic 재검토로 더
> 정밀하게 나눠 보니, 문법적으로 사람을 부르는 형태(-님 vocative)는 53건 중 7건(13%)뿐
> 이고 나머지 46건(87%)은 회수된 이름을 그냥 일반 명사처럼 쓴 경우였다 — 이 비중이
> 가드와 채점기 수정의 실제 담당 범위를 결정했다.
>
> 사용자의 "1과 2함께" 지시로 신규 `ollama-proxy/handle_grounding_guard.py`(기본 off,
> `AIRI_HANDLE_GROUNDING_GUARD`)를 구현했다: 이번 턴 실제 근거 풀(유저 발화+브리핑+
> memory 회수+journal)을 한 번 계산해 (1) -님 vocative 호칭만 좁게 스트립·치환하고
> (2) 그 계산의 memory/journal 부분을 기존 in-band `airi_moderation` SSE 신호로 항상
> 노출한다. `run_broadcast_chat_ab.py`가 캡처하고 `run_broadcast_sim.py`가 roster
> 부분일치로 `fact_tokens`에 합친다 — `invented_handle` 게이트 정의(무엇이 위반인가)는
> 그대로, 판정에 쓰는 근거 범위만 넓혔다. 프록시 flag가 off면 완전 no-op(시뮬레이터
> union도 자동 무동작), 실제 버그 1건(flag-off 경로에서도 속성 조기 접근으로
> AttributeError → 370개 중 62 FAIL/6 ERROR)과 이중 flag monkeypatch 위험 1건을 구현
> 중 발견·수리했다. 검증: 신규 모듈 16 + 프록시 373(ON/OFF/grounded 통합 3 포함) +
> 시뮬레이터/코드체인 88+85 + blind commitment 6 전부 pass, `test-current-checkpoint.ps1`
> PASS, work-continuity PASS, diff-check 0. fix `a0020dd` + docs 3개 commit으로
> `59d1836`까지 push, HEAD/local/remote exact 확인.
>
> **다음 세션 진입점 순서는 그대로 4개다** (아래 참조). GPU 학습은 아직 없다 —
> 이 배치는 순수 코드/채점기 수정이었다. E2-C1의 학습 계약(`AIRI-E2-C1-FROZEN-
> CONTRACT-2026-08-24.md` §1-10: correction 480/replay 200/mixture 680, 512/32,
> LR 1e-5 등)은 변경되지 않았다 — E2-C2는 그 계약을 재검토해서 만드는 **새** 후보이고,
> **새 blind가 필요하다(v1/v2 모두 이미 소비돼 재사용 금지)**. 상세는 handoff `-7`,
> frozen contract `12`, ROADMAP-LOG 2026-08-24 최신 두 배치.
>
> **2026-08-24 03:24 KST 검토 PC 최우선 진입점 — E2-C1 ADAPTER-INIT OFFLINE PASS / PUBLISHED:**
> latest Goal은 E2 adapter weight를 초기값으로 쓰고 optimizer/scheduler/RNG/cursor는
> 새로 시작하는 `E2-C1` 교정 후보다. correction 480, v4 replay 200, mixture 680과
> 새 retained blind 3종/4 seeds/3 arms의 계약은 동결됐다. final 감사에서 확인한 exact
> five `으로/로` target 오류는 helper/template/independent verifier와 mutation regression의
> 최소 수리로 닫혔다. current bytes는 full unit 12, blind pytest 5, generator byte check,
> repository/external verifier, independent semantic/grammar/split/replay/collision 감사와
> diff/security를 PASS했다. milestone commit `2e61842ba72875bff4d473653b635541e6e0b82a`와
> receipt commit `3dba3ca43a161d69f677eec2a8d10c3ddd061fca`는 origin/main에 push됐고,
> push 직후 HEAD/local main/local origin/main/remote main exact·worktree/stage clean·PID 0이다.
> 현재 `freeze_status=pass`, `gpu_authorized=false`, E2-C1 0 microstep/0 optimizer step이다.
> E2 weights-only init과 fresh optimizer/scheduler/RNG/cursor/progress, v2/v3 provenance와
> closed inventory의 최소 구현은 pinned pycompile, focused 27/2·50/2·67/1, combined
> 144 passed/5 skipped, continuity/full current-checkpoint/diff-check와 actual E2 helper를
> PASS했다. implementation `6dd2412`와 receipt `3c4b1a9`는 origin/main에 push됐고
> HEAD/local·remote exact, clean, related PID 0을 확인했다. blocker/다음 gate는 fresh
> reconciliation 뒤 별도 intent를 쓰는 bounded GPU smoke다.
>
> 새 PC에서는 다른 실행보다 먼저 `AGENTS.md` → `AIRI-WORKING-STATE.md` → 현행 handoff →
> `AIRI-ROADMAP-STATUS.md` → 이 파일을 전체 읽고 Goal/Git/PID/E2/T3/blind를 read-only로
> 대조한다. PID 0이면 `pause-airi-safely.ps1`을 실행하지 않는다. 현재 checkpoint의
> exact 설계·SHA·blind gate와 adapter-init receipt는
> `airi_docs/진행중/AIRI-E2-C1-FROZEN-CONTRACT-2026-08-24.md`에 있다. 다음 무-GPU 동작은
> adapter-init commit/push SHA와 clean/PID 0을 먼저 확인하는 것이다. counts/splits/replay,
> v4/base/E2, seed 42·batch 1·accumulation 16·seq 2048·512 microsteps·LR 1e-5·constant/K=3,
> blind fixture/seed/threshold는 변경하지 않는다. milestone publication이 끝났어도 GPU를
> 자동 시작하지 않는다. review PC는 `6dd2412`/`3c4b1a9`와 remote SHA/clean/PID 0을 대조하고,
> fresh external output root·success/failure/pause/resume identity를 담은 bounded smoke intent를
> 별도로 기록한 뒤에만 GPU smoke를 한 번 수행한다.

> **2026-08-23 22:38 KST E1/E2 사용자 검토 경계:** baseline/E1/E2는 모두 같은
> Mi:dm 계열의 기존 broadcast v3/continuity-v4 1 epoch/2 epoch 후보다. E2는 E1 대비
> topic 572→586, fact 180→193, memory 8→11, invented handle 46→37, callback 6→8,
> complete arc 1→5로 상대 우세하고 dev loss도 epoch 1 `2.893371758116589`에서 epoch 2
> `2.735453106217887`로 낮아졌다. 그러나 final blind invented handle은 E1 26→E2 34,
> long memory는 양쪽 0/12이고 E2 donation은 55/56이다. E2는 후속 교정 학습의 검토상
> 우세한 출발점일 뿐 T3 winner/adopted가 아니다. 사용자는 external T3 root의 E1/E2
> 각 12개 원본 report와 대표 실제 응답을 검토 중이다. response-bearing report/packet/
> runtime은 Git에 넣지 않는다. same-data 3 epoch 반복은 승인·권고하지 않으며, 다음 실행
> gate는 이 five-doc 배치 commit/push·clean 뒤 새 교정 데이터/비오염 blind/후보 범위를
> 사용자가 별도 승인하는 것이다. 그전에는 GPU 학습, 같은 T3, campaign, 운영 채택을 금지한다.

> **2026-08-23 20:56 KST 현재 gate: T3 FAILED CLOSED.** controlled GPU와
> authoritative E2 1,600/1,600, E1/E2 merge·BF16/Q4_K_M package는 완료·미채택이다.
> authoritative T3는 baseline/E1/E2 각 12, 총 36 reports와 두 comparator까지 실행했으나
> 두 comparison 모두 `status=fail`, adoption false, paired reports 0, reason
> `polite violation or invented handle`로 종료했고 launcher exit 1, `summary.json` absent다.
> 전 arm transport failure는 0이나 invented handle baseline/E1/E2 30/46/37,
> memory 5/36·8/36·11/36, fact 173/752·180/752·193/752, donation
> 56/56·56/56·55/56이다. comparison 두 파일은 각 196 bytes SHA `5f2b4213...3afa`;
> report/packet/evidence/runtime/comparison inventory SHA는 `e5241341...16b4`/
> `00b90c95...859a`/`7cb97aea...3dee`/`0417f814...4e8a`/`5a4793b9...d75`다.
> launcher/관련 PID/owned listener는 0이다. winner 0이므로 3×500 campaign과 운영 채택을
> 금지하며, 실패 root를 보존하고 같은 공개 blind matrix나 hard gate를 반복·약화하지 않는다.
> terminal failure 다섯 SSoT commit `d3724b1ea3d0df7cff8e14fd511f4b8244b8838c`은
> `90a436e..d3724b1 main -> main`으로 origin/main push됐고 HEAD/local·remote exact,
> 관련 PID/listener 0을 확인했다. 다음 실행 gate는 campaign이 아니라, 공개된 blind를
> 재사용하지 않는 새 모델링/evaluation iteration에 대한 사용자 방향이다.

> **2026-08-23 controlled GPU P0-B PASS receipt:** 최신 Goal status는 `active`,
> `goal_status=active`다. 첫 K=5 baseline은 480/30 계산 뒤 actual interval max
> `705.902827`초와 final-evidence 결속 실패로 FAIL해 보존했고 같은 K=5를 반복하지 않았다.
> exact internal manifest receipt row 결속으로 최소 수정한 뒤 fresh K=3 baseline과 실제
> `SAFE_TO_POWER_OFF` pause/checkpoint/resume arm을 모두 terminal 480/30으로 완주했다.
> final equivalence receipt는 48,323 bytes SHA `d913992e...e84b9`, `pass=true`, adoption
> false, 672 tensors exact/max abs·rel 0, normal interval 10개/max `551.5176357`초다.
> Windows producer/verifier의 `README.md` receipt-order false reject는 platform `Path` 순서
> 한 줄과 targeted 회귀로 최소 수정했고 targeted 1 PASS, suite 62 passed/1 skipped,
> actual GPU verifier와 final offline checkpoint도 PASS했다. 운영 채택과 기본 모델 변경
> 금지는 유지한다.
>
> 07:38 KST verifier/test+five SSoT commit `87dfabd`와 commit receipt `29080be`는
> `0454ca8..29080be main -> main`으로 origin/main push됐다. push 직후 HEAD/local·remote
> origin/main exact, worktree clean, 관련 durable runner/trainer/verifier/test PID와 AIRI GPU
> workload 0이다. source/chat/base와 E1 adapter/config/report SHA는 exact, E2 adapter/report
> absent, 기존 로그 두 개 각 0 bytes, E2 microstep 0이다. 현재 gate는 actual push receipt
> five-doc final 검증·commit/push와 clean 재확인뿐이다. 그 뒤 fresh timestamped E2 root/
> manifest를 만들고 authoritative
> durable runner로 seed 42·1,600 microsteps를 step 0부터 시작한다. direct trainer는 금지한다.
> 새 감사 라운드는 추가하지 않으며 문서 인덱스는 현행 handoff를 정확히 가리켜 변경하지 않는다.
>
> **이전 권한 이력 — 2026-08-22 goal resume:** 사용자 `/goal` 명령으로 당시 AIRI 본 goal은 `active`였다.
> 운영 모델 채택과 기본 서비스 모델 변경만 별도 사용자 승인 전까지 금지한다.
> 전원 종료 복구용 P0-A checkpoint/full-state/atomic fault 계층은 offline 구현·독립
> P0/P1 0 감사까지 완료되어 `6f0c1358`로 origin/main push됐다. P0-B timing/
> exact-equivalence evidence gate와 external expected-run 결속도 offline 회귀·독립
> P0/P1 0을 거쳐 `e970cf7`·`8cd69b5`로 origin/main push됐다. `pause-airi-safely.ps1`은
> RunDir 생략 시 exactly-one verified active durable run만 자동 선택하도록 actual-process
> 0/1/multiple/spoof/fallback 회귀와 독립 P0/P1 0을 통과했다. controlled GPU 동등성과 실제 E2 속도 10분 checkpoint 상한은
> 아직 미실측이며, 둘을 실증한 뒤에만 E2를 시작한다.
> 현재 계약은 `goal_status=active`; 이전 pause 인계 이력은
> `goal_status=paused-user-session-handoff`; `adoption_authorized=false`
> `execution_order=P0_A>P0_B>E2_LAUNCH>E2_PROVENANCE>PACKAGE>T3_36>CAMPAIGN_3X500>USER_DECISION`

**진입점은 네 개다** (2026-08-22 live-state 지속성 규칙 추가):

1. `airi_docs/진행중/AIRI-WORKING-STATE.md` — **가장 먼저 읽는 live SSoT.**
   세션 시작·goal resume·재부팅·compact 직후 실제 goal status, HEAD/worktree,
   PID, 산출물과 대조하고 불일치하면 이 문서를 먼저 정정한다. active goal에서는
   최대 60분 heartbeat와 단계 전후 intent/receipt checkpoint를 유지한다.
2. `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md` — **현행 GPU 인계 단일
   SSoT.** runtime-shaped v4 1,000행의 exact SHA, E1 완료 결과, P0-A offline 완료와
   `e970cf7` P0-B timing/exact-equivalence gate 및 `8cd69b5` expected-run 결속,
   E2 전 controlled GPU 내구성 실증,
   중단한 E2의 step 0 재실행 명령, merge/GGUF 핀, calibration 2종+blind 180분 T3의
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
Serena MCP는 로컬 A/B 순손실로 등록 롤백됐으며 2026-08-23 사용자 결정으로
사용·재도입하지 않는다. 관련 token-order 문서는 실행 지시가 아닌 역사 기록이다.
Caveman trial은 미실행이다.

최근 배치 이력은 `airi_docs/로드맵/AIRI-ROADMAP-LOG.md`(최신이 위).
**매 배치 커밋마다 LOG에 기록**하고, STATUS는 상태 변화 시에만 고친다.
과거 인계 문서(2026-08-13 이전)는 전부 `airi_docs/아카이브/`로 이동했다 —
현재 상태 검증에 사용 금지.

학습 중 사용량 종료나 PC 종료 준비에는 저장소 루트에서 다음만 실행한다.

```powershell
.\pause-airi-safely.ps1
```

검증된 active durable run이 정확히 하나면 자동 선택한다. 0개면 실행 중 학습 없음으로,
2개 이상이면 후보를 표시하고 중단한다. 수동 지정은 계속
`.\pause-airi-safely.ps1 -RunDir '<run-state가 있는 폴더>'`로 가능하다. 두 경우 모두
`SAFE_TO_POWER_OFF`가 출력되기 전에는 전원을 끄지 않는다.

현행 순서는 GPU 인계 §8의 체크리스트 한 곳만 따른다:
`P0 전원 종료 내구성 구현·실증 → E2 preflight/step 0 → provenance →
E1/E2 merge/package → 36 T3 → 승자 3×500 →
실제 응답·증거 제출 → 사용자 채택 판단`.

## 운영 기본값 (변경 시 이 절 갱신)

- Chat model: Mi:dm (`midm-airi:2.0-mini`) digest pin 유지 (사용자 결정 6)
- `num_ctx=4096` (2026-08-25 M2에서 2048→4096. 근거: 세 blind 라운드에서 전 arm 턴의
  ~34%가 Ollama 400 `exceed_context_size_error`로 죽었고 관측 `n_prompt_tokens`
  2,552~2,827; GGUF 내장 KT 프리앰블 ≈514토큰이 고정비라 실효 예산이 ~1,534였다.
  프록시 `NUM_CTX`·세 런처 기본값 동시 변경, 태그 재패키징 없음, `/health`에
  `prompt_budget.context_exceeded_observations` 추가)
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
- 음성: 현행 일본어 참조 유지, T-05 126번 예비 — **2026-08-24 결정 회신 `t05=샘플요청`**:
  126번 대화체 재합성 A/B 청취 샘플 준비가 열린 비GPU-학습 작업(운영 승격 아님).
  팬덤명 유보("시청자들"). DeepL 키 회전은 `보류(위험 인지)`

## 작업 원칙 (v3)

- 모든 배치는 STATUS §1 더하기 지표 중 하나를 올려야 한다. 빼기
  지표(존댓말·이탈 등)는 회귀 가드로만 확인한다.
- 프롬프트 지시보다 결정론 계층 우선 (상한 2회 실증 — dn04·gr01).
- 완료·통과 주장은 직전 fresh 실측 증거 동반. raw 경로 시뮬레이션은 검토
  근거 불인정(11435 게이트 경유 의무 — 사용자 결정 7).
