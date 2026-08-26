# M7 S0·S1 receipt — 복제 노이즈 측정과 되먹임 고리 차단 (2026-08-26)

> 타계책(`AIRI-BREAKTHROUGH-PLAN-2026-08-26.md`) S0(측정 위생)과 S1(런타임 되먹임 고리 차단)의 실행 기록이다.
> 아래 수치는 전부 **자동 시그니처(표시 전용, 계약 §6)**이며 채택 판정은 사람 채점(M7-3)이 한다.
> 산출물 root: `D:\AIRI-Models\airi-human-eval\`(저장소 밖). 응답 본문·가명은 이 문서에 넣지 않는다.

## 1. 실행 receipt

| run | 변수 | 구성 | exit | 시각 |
|---|---|---|---|---|
| `20260826-replay-05r1..r3` | 없음(복제) | run 05와 동일: pseudo-korean 1,500건, max-turns 100, history 8, 브리핑 on, stock Mi:dm 2.0 Mini Q4 digest pinned, `feedback_hygiene=off` | 0/0/0 | 16:53~16:59 |
| `20260826-replay-06a-r1..r3` | history 구성 | + `AIRI_FEEDBACK_HYGIENE=on`(foreground '?'/오프너 반복 쌍 미유지 + journal assistant 제외) | 0/0/0 | 17:00~17:06 |
| `20260826-replay-06j-r1..r3` | history 구성 | + `AIRI_FEEDBACK_HYGIENE=journal`(journal assistant 제외만) | 0/0/0 | 17:06~17:12 |
| `20260826-replay-06b-r1..r3` | history 구성 | on + 브리핑 자기 에코 차단(scratch fixture 사본 `briefing.min_echo_response_chars`=10^9; report `fixture_sha256` `2d361ef3…`, 원본 `6af5c2ae…`) | 0/0/0 | 17:15~17:21 |

- 각 run은 스택 기동→99턴 재생→정지(≈2분). health `feedback_hygiene`는 run별 `health-before.json`에 기록됐다(off/on/journal/on).
- 코드: S1 flag `098c887`(`foreground_context.py`·`ollama_proxy.py`, 새 `test_foreground_context.py` 10건, proxy unittest 394 OK, CI 샤드 등록, 기본 off는 byte 동일).
  `summarize_ratings.py` 3축 합성·`--baseline` delta `f748cae`. 브리핑 에코 차단은 코드 변경 없이 fixture 값으로만 했다.
- 픽업 결정론: 13 run 모두 같은 99 `message_id`. 생성은 seed 20260818(하니스 스트림 seed; 샘플링 seed는 요청에 없음)에도 재현되지 않는다(run 05 대비 동일 응답 10/2/0).
- 집계: `20260826-m7-signatures/signatures.{json,md}`(scratchpad `s0_signatures.py`).

## 2. 시그니처 (99턴, run별 값 / 붕괴 = "음" 오프너 ≥40 또는 "?" 종결 ≥60)

| arm (n) | "음" 오프너 | "?" 종결 | 뜻 되묻기 | 완전 에코 | topic_anchored | 재료 사용 | 고유 오프너 | 글자 p50 | 붕괴 run |
|---|---|---|---|---|---|---|---|---|---:|
| off (4: run05, r1~r3) | 48/56/1/89 | 78/71/15/84 | 27/0/0/0 | 10/5/0/0 | 45/28/10/4 | 0/1/1/1 | 63/43/17/22 | 13/16/17/10 | **3/4** |
| on (3) | 5/18/67 | 33/14/55 | 1/0/0 | 4/1/0 | 25/8/34 | 3/1/4 | 85/41/82 | 11/8/16 | 1/3 |
| journal (3) | 1/96/2 | 3/68/89 | 0/1/5 | 0/0/15 | 33/52/58 | 0/2/0 | 84/88/95 | 12/15/8 | 2/3 |
| on + 브리핑 에코 차단 (3) | 4/2/22 | 7/17/16 | 0/3/3 | 0/0/0 | 43/6/60 | 1/0/1 | 85/33/39 | 9/7/15 | **0/3** |

## 3. 읽기

1. **S0 — n=1은 무의미하다.** 같은 구성 4회에서 "?" 종결이 15~84, "음" 오프너가 1~89로 흔들린다(SD ≈ 30/99). 붕괴는 run 단위로
   일어나거나 안 일어나는 쌍봉 현상이다. 08-19 이후의 모든 단일 run 비교(합성 매트릭스 포함)와 run 04→05 비교는 이 노이즈 안에 있다.
   앞으로 후보 비교는 복제 ≥3의 **붕괴 빈도·분포**로 읽고, 사람 채점은 사전 등록 규칙으로 고른 1회만 한다.
2. **S1 — 되먹임 고리가 붕괴의 원인이다.** 되먹임 채널은 셋이었다: (a) foreground 투영이 5어절 이하 채팅에서 '?'가 든 직전 AIRI 응답을
   유지, (b) journal 회수의 assistant 행, (c) 브리핑 "방금 흐름 → 나: <직전 응답>"(`broadcast_sim.py:520-525`, 코드 주석에도 T35에서
   문형 전염을 실측했다고 적혀 있음). (a)+(b)만 끊으면 붕괴 3/4 → 1/3, (b)만 끊으면 2/3(무효), **셋 다 끊으면 0/3**이고 완전 에코 0,
   "?" 종결 ≤17. 규칙 문장이나 문형 땜질 없이, 모델에게 자기 출력을 보여주지 않는 것만으로 붕괴가 사라졌다.
3. **아직 판정이 아니다.** history가 없어진 만큼 맥락 유지가 떨어질 수 있고(topic_anchored 43/6/60, 글자 p50 9/7/15), 재료 사용은
   여전히 0~1/99다. 방송다움·맥락·반응 3축은 사람 채점(M7-3)만이 답한다. 채점 대상은 사전 등록 규칙(최종 S1 arm 3회 중 "?" 종결
   중앙값)으로 **`06b-r3`**(`20260826-replay-06b-r3/rating-sheet.html`, 99턴)이며, run 05(A+B 대조군) 시트도 그대로 남아 있다.
   보조로 `06a-r1/rating-sheet.html`(on만)도 만들어 두었다.

## 4. 운영 반영과 다음 단계

- proxy flag는 병합됐지만 **기본값은 off**다. 운영에서 켜는 것(`AIRI_FEEDBACK_HYGIENE=on`)과 디렉터 브리핑의 자기 에코 차단은 M7-3 사람
  채점이 기준선 대비 3축 +0.2 이상일 때만 별도 승인으로 한다.
- 브리핑 자기 에코(c)는 평가 하니스(`broadcast_sim.py`)의 브리핑에만 있고 운영 디렉터(B4 `broadcast-director/`)에는 없다(`→ 나`/response
  에코 없음, 2026-08-26 grep). 따라서 운영 경로의 되먹임은 (a)+(b)=proxy flag가 전부이며, 하니스는 채택 시 runner 플래그
  (`--briefing-self-echo off`)로 같은 조건을 재현 가능하게 고정해야 한다.
- 다음 변수(S2 오프너 재샘플·S3 예시·S4 픽업)는 모두 06b 구성 위에서 복제 3회로 잰다. 파인튜닝 금지는 그대로다(2026-09-09까지).
