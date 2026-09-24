# AIRI 라이브 방송 시뮬레이션 인계 (2026-09-24, 신규 PC)

> 이 문서가 다음 세션·다른 PC의 **현재 인계 진입점**이다. 결과의 상세 근거는
> [`airi_docs/진행중/AIRI-SYSTEM1-CANDIDATE-JUDGE-2026-09-23.md`](AIRI-SYSTEM1-CANDIDATE-JUDGE-2026-09-23.md) §0~§8,
> 시각·명령·SHA receipt는 [`airi_docs/진행중/AIRI-WORKING-STATE.md`](AIRI-WORKING-STATE.md)에 있다.
> 문서와 기계 상태가 다르면 실행하지 말고 관측값으로 기록을 먼저 정정한다.

## 0. 읽는 순서와 기계 사실

1. `AGENTS.md`
2. [`airi_docs/진행중/AIRI-WORKING-STATE.md`](AIRI-WORKING-STATE.md) — 전체를 읽고 `git status`·HEAD·PID·산출물 SHA와 read-only로 대조
3. 이 문서
4. [`airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`](../로드맵/AIRI-ROADMAP-STATUS.md)
5. [`NEXT-SESSION.md`](../../NEXT-SESSION.md)

| 항목 | 값 (09-24) |
|---|---|
| 작업 PC | **신규 PC** — RTX 5060 Ti 8 GiB, D: 없음. GPU PC(Codex PC)가 아니다 |
| AIRI 앱 | 이 PC에는 **설치·실행하지 않는다** (사용자 지시 「이 pc에서는 아이리를 직접 설치하거나 켜지는 마」) |
| TTS·STT | GPT-SoVITS·STT(faster-whisper) 설치본 없음 → TTS 포함 지연은 GPU PC 과제 |
| Ollama | 0.34.2. `midm-airi:2.0-mini` digest `d297ee3db6f3380c4038d2cd7aa7d0076cdb1b76e4c9578499e459af428cfe11` (런처 고정값 `92a9ba2e…485f`와 manifest만 다르고 가중치 동일), 평가용 `midm-airi-evaltpl:2.0-mini` (`c1237f70…`, 제거 가능) |
| 저장소 밖 자산 | `C:\AIRI-Models\gguf\` (midm-2.0-mini-instruct.Q4_K_M, A.X-4.0-Light-Q4_K_M, kanana-1.5-8b-instruct-2505.Q4_K_M, 평가용 템플릿 교체본 midm-2.0-mini-instruct.airi-template.Q4_K_M) · `C:\AIRI-Models\system1\` (judge-v1, contradiction-v1) · `C:\AIRI-Models\venvs\system1\` (학습 venv, gguf 0.19.0) · `C:\AIRI-Models\airi-human-eval\` (방송 대본·후보·평가 산출물 — 응답이 담긴 자료라 Git 밖) |
| Git | `main`은 코드 기준 `4f278f18c98aad5d8b75ab5ad113ed3a02c5353e`, 그 뒤 문서 커밋(`f022712` 09-24 현행화 — 이 문서 신설, 이어진 수치 정정). origin/main `2abe9e49e94d73721ba0a73a06957f7462704c45`보다 앞선 커밋은 **전부 push 없음**(정확한 HEAD·개수는 `git log --oneline 2abe9e4..HEAD`). 커밋 author `kkp8121-rgb` |
| GPU PC 자산 위치 | `AIRI-CODEX-HANDOFF-2026-08-27.md` §0-A(그 문서의 M7 판정은 무효)와 `AIRI-GPU-PC-HANDOFF-2026-09-01-STAGE3.md`를 따른다 |

## 1. 09-23~24에 일어난 일

1. 09-23: 문서 현행화 뒤 사용자 /goal 「실행 계획을 끝까지 진행」(Jev식 System1: 측정 → 데이터 → 학습 → 비교)을
   끝냈다. 결과는 판정기 문서 §0~§6.
2. 09-23 저녁: 사용자 지적으로 v1 시나리오 모순(주체 모호, 작성된 채팅, 1대1 입력)을 확인하고 v2(AIRI 1인칭 +
   육하원칙)를 만들었다(§7). 블라인드 검토에서 사용자가 대본형 평가를 무효로 판정했다(「이런 방식은 의미가 없어보여」).
3. 09-23 밤~09-24: **라이브 방송 시뮬레이션**으로 바꿨다. 첫 방송부터 히스토리를 쌓으며 Claude가 시청자·쇼러너를
   턴마다 연기한다. 1회차 뒤 사용자 「훨씬 좋네 이대로 튜닝 시작해」(§8). 10회차까지 돌렸다.
4. 09-24: 사용자 목표 「사실 뭐라 할지 모르겠지만 모든 수단을 동원해서 아이리의 성능을 향상시켜」(active). 이어
   「jev 도입의 효과는 어떄」에 답했고(§5-2), 「문서들 모두 현행화」 요청에 따라 09-24 문서 현행화를 했다(실행 없음,
   편집은 미커밋일 수 있다 — 마지막 receipt는 `AIRI-WORKING-STATE.md`).
5. 커밋(오래된 순, push 없음): 269e13d System1 판정 seam · d82c81e 라벨·학습 파이프라인 · d2d7c91 문서 ·
   9a3a0ed 후보 선택 기능 · 34f6fa6 v2 시나리오·판정 도구 · 1b073b5 문서 · 7e0b207 브리핑 문장 대체 · 50787d8 문서 ·
   4ea23d0 긴급 안전 판정 수정 · 038fa00 선택 개선 · 462848b 시뮬레이터·모순 판정기 도구 · 4f278f1 문서 ·
   f022712 09-24 문서 현행화(이 문서 신설). 그 뒤 10회차 수치 정정 문서 커밋이 이어진다.

## 2. 현재 결과와 프록시에 들어간 것

### 2-1. 라이브 방송 시뮬레이션 결과 (AI 판독 — 사람 판정은 아직 없다)

| 회차 | 조건 | 깨끗한 턴 | 비고 |
|---|---|---|---|
| 01 | native /api/chat, 구간 브리핑 통째 | — | 같은 문장 반복 2, 브리핑 반박 4 |
| 02 | 턴마다 사실 하나 | 8~10/23 | 반복 0, 반박 4, 지어내기 6 |
| 03 | AIRI 말투 브리핑 + 평가 전용 후보 선택 shim | 약 16/23 | 「음, 잠깐만.」 1턴(출력 경계가 말줄임표 답을 비움) |
| 04 | **앱 경로 /v1 스트리밍** 기준선, 선택 없음 | 약 6~8/25 | 22/25가 한 문장, 일대일 코드 답 오작동 2(이름→「아직 기록이 없어」, 저녁→식사 추천) |
| 05 | /v1 + 후보 6개 | 약 15/23 | 대사 도착 중앙 1.0 s, 최대 2.3 s |
| 06 | /v1 + 후보 3개 + 모두 탈락 시 브리핑 문장(사용자 선택) | 약 18/24 | 중앙 0.59 s, 최대 1.07 s, 브리핑 문장 9턴 |
| 07 | 새 이야기(요리·지하철), 06 설정 | 약 8/14 | 「무슨 사고」 긴급 문장 오작동, 전제 따라 지어낸 소화기가 기록으로 이어짐 |
| 08 | 새 이야기(화분·노래방), 기준 0.4 | 약 5~6/9 | 「아직 말하지 말 것」 누설, 「설거지는 아니고」 정정 무시 |
| 09 | 새 이야기(헬스장·고양이 카페), 수정 전부, 방송 중 2건 추가 수정 | 최종 코드 턴 3 깨끗·2 부분·0 실패 | 「위험했겠다 다쳤어?」 긴급 오작동, 「ㅋㅋ」로 끝난 브리핑 문장 잘림·침묵 |
| 10 | 새 이야기(자전거·라면), 커밋 `4f278f1` 그대로 | **10/11 + 작은 누락 1, 실패 0** | 대사 도착 중앙 0.64 s·최대 0.97 s, 브리핑과 글자 그대로 같은 답 8/11턴(대체 7 + 후보가 그대로 옮긴 1, 대본 읽기처럼 들릴 수 있음 — 사람 판정 필요) |

- 1~3회차와 재실행은 native /api/chat(캠페인 도구 경로)이었다. AIRI 앱 공급자는 `11435/v1`이며 방송 턴 토큰을
  보내는 앱 패치는 아직 없다. 대본은 저장소 밖 `C:\AIRI-Models\airi-human-eval\sim-*`에 있다.
- **09-24 사용자 판정: 2~10회차 이야기는 AIRI 설정 밖이었다.** 10회차 검토에서 「자전거 붉닭등 아이리가 못하는걸 지어내서
  말하고 있어」, 「5번째 방송」 첫인사는 1~4회 기록이 없어 뜬금없다고 했다. 브리핑(Claude가 쓴 쇼러너 메모)이 버추얼 AIRI에게
  몸으로 한 경험(목 통증·요리·지하철·헬스장·자전거·라면 등)을 말하게 했고, 브리핑 문장 대체가 그것을 그대로 읽었다. 위 표의
  깨끗한 턴 수는 **브리핑을 따르는 능력만 잰 값**이며 방송 품질·설정 적합의 근거가 아니다(live state `human_review_sim10`·
  `scenario_canon_finding`, 판정 JSON `C:\AIRI-Models\airi-human-eval\sim-fifth-story-10\human-review-2026-09-24.json`).

### 2-2. 운영 프록시에 들어간 것 (모두 기본 꺼짐, 커밋됨)

**브리핑 후보 선택** — `ollama-proxy/live_briefing_select.py` + `ollama_proxy.py` 연결(/v1 스트리밍, native /api/chat 두 경로).

| 환경 변수 | 값 | 기본 |
|---|---|---|
| `AIRI_LIVE_BRIEFING_CANDIDATES` | 2~6, 권장 3 (7 이상은 6, 비었거나 1이면 꺼짐) | 꺼짐 |
| `AIRI_LIVE_BRIEFING_COVERAGE` | 조기 채택 커버리지 (0, 1] | 0.4 |

- 런처 파라미터는 없다. 프록시 프로세스의 환경 변수로 준다.
- 브리핑에 `- 이번 턴에 말할 것:` 줄이 있을 때만 작동한다(선제 발화 턴은 제외). 켜지면 첫 문장 조기 송출을 보류하고,
  기억 부재 즉답·일대일 교정 재시도를 생략하고, 후보를 뽑아 글자 2-gram 커버리지로 고른다. 모두 탈락하면 브리핑
  문장(끝 웃음 제거·마침표 보장)을 말한다. `- 아직 말하지 말 것:` 줄은 모델에 넘기기 전에 뺀다.
- 부적합: 존댓말·글말 어미, 라벨 누출, 하지 않은 조회, 직전 답과 20자 반복, 정정된 단어 재단정, 축하 되받기·감정 짐작.
- 관측: `/health`의 `live_briefing_select` (`candidates`, `coverage`, `turns`, `extra_draws`, `early_accepts`,
  `first_draft_replaced`, `briefing_line_spoken`).

**긴급 안전 판정** — `urgent_safety_context`(모든 경로, 기본 적용). 강한 단어(자살·자해·죽고 싶·크게 다쳤·응급·폭력)는
항상 긴급이다. 「사고·위험」은 본인 표시·도움 요청·서술형 피해면 긴급이고, AIRI 직전 답을 되묻거나 남에 대해 묻거나
짐작하면 긴급이 아니다.

**설정 문장·몸 경험 거름 (09-24, 후보 선택 안, 기본 꺼짐)** — `live_briefing_select.canon_say_line`·`with_canon_say_line`:
시청자가 AIRI의 몸이나 방송 밖 생활(먹기·잠·운동·사는 곳·주말·여행)을 전제로 묻고 브리핑에 말할 문장이 없으면 설정 문장
(예: 「나는 버추얼이라 밥은 못 먹어! 대신 너는 오늘 뭐 먹었어?」)을 말할 문장으로 넣는다. 부적합 규칙에 「먹었·잤·운동했·
살고 있·밖에서 따로 살·음식을 좋아」 같은 AIRI 자신의 몸·방송 밖 생활 단정을 더했다(시청자에게 묻는 문장·시청자 이야기는 제외).
이 규칙은 브리핑 문장에도 적용되므로 설정 밖 브리핑 문장은 그대로 읽히지 않는다. 관측: `/health` `canon_lines_added`.

**식사 과거형 질문 (09-24, `e9e6f65`, 모든 경로)** — 「점심 뭐 먹었어?」를 메뉴 선택 질문으로 보던 오분류를 고쳐, 코드 고정
추천문(「든든하게는 김치찌개나 덮밥…」)과 메뉴 제안 지시가 붙지 않는다.

**평가·학습 도구** — `ollama-proxy/eval/live_broadcast_sim/sim_broadcast.py`(+ `test_sim_broadcast.py`, CI 평가 샤드):
방송 제어·/v1 스트리밍·전달 확인·강제 히스토리 재실행. `ollama-proxy/training/system1/`: 라벨·학습 파이프라인,
모순 합성·판정기 학습. judge-v1(반응 판정)·contradiction-v1(모순 판정)은 **운영 미연결**이다.

### 2-3. 설정 안 시리즈 series-01 (09-24~)

사용자 결정: AIRI가 말할 수 있는 것은 **방송 안에서 일어난 일 + 지난 방송 기억**뿐이다(「필요하면 추후에 확장하는 방향으로」).
1회를 진짜 첫 방송으로 시작하고, 이후 회차는 같은 기억 DB `C:\AIRI-Models\airi-human-eval\series-01\airi-memory.sqlite3`를
이어 쓴다(각 회차 폴더 `series-01\epNN`, 측정용은 따로 `series-01-probes\` — 시리즈 기억을 오염시키지 않는다).

| 항목 | 결과 (AI 판독) |
|---|---|
| 1회 방송 (11턴, 커밋 `bf4af27` 코드) | 설정 밖 발언 1(「오늘 점심에는 김치찌개 먹었어」 — 모델 스스로), 코드 오작동 1(「뭐 먹었어?」에 메뉴 추천 고정문), 자기 모순 1(첫 턴 「떨린다」 → T07 「떨림을 못 느낀다」), 투표 공지·결과·마무리 전달. 대사 도착 중앙 454 ms·최대 1063 ms (`series01_ep01_receipt`) |
| 설정 밖 전제 질문 6종 × 6 (먹기·주말·잠·운동·사는 곳·좋아하는 음식) | 수정 전 약 27/36 지어냄, 상황 메모에 설정 문장을 넣어도 약 32/36(효과 없음) (`canon_probe_receipt`). **이 측정과 아래 1차 측정은 모든 표본이 한 기억 세션을 써서 앞 표본의 문답이 회상으로 섞였다** — 표본마다 세션을 나눈 재측정: 기준선 약 30/36 지어냄(답이 매번 다름) |
| 같은 36개, 설정 문장 대체 + 몸 경험 거름 (`48cd8e1`) | 섞인 측정에서 33/36 → 규칙 보강 뒤 36/36(`canon_line_receipt`)이었으나, **세션 분리 재측정은 약 33/36 설정 적합**(빠져나간 3: 「운동 좋아하긴 하는데」, 「게임이나 가상 세계에서는 꽤 활발하게 움직여」, 「나는 아직 밥을 못 먹어」), 대사 도착 중앙 540 ms·최대 829 ms (`measurement_independence_correction`) |

## 3. 방송 시뮬레이션 실행법

### 3-1. 스택

**이 PC의 평가 스택** (receipt 기준, 모두 loopback):

1. Ollama serve를 멈춰 11434를 비운다.
2. Ollama 동봉 llama-server를 11500에 띄운다 — 작업 디렉터리 `lib/ollama/cuda_v13`, `-c 4096 -ngl 999 --jinja`,
   Mi:dm 머리말이 없는 AIRI 채팅 템플릿 `ollama-proxy/training/system1/midm-airi-chat.jinja`(d82c81e 커밋)를 `--chat-template-file`로
   넘긴다, 방송 회차는 `--cache-ram 0`(기본값에서 llama-server 작업 집합이 9.0 GiB였고 원인은 RAM 프롬프트 캐시로 추정 — receipt).
3. `ollama-proxy/eval/llama_server_shim.py`를 11434에 띄운다(기본값: llama-server `http://127.0.0.1:11500`,
   모델 `midm-airi:2.0-mini`로 보고).
4. 프록시 `ollama-proxy/start-local-ollama-proxy.ps1`(PowerShell 5.1)을 `-LiveBroadcast -InputScreening on`과
   ROOT의 `secrets.json` 토큰(`-LiveBroadcastMasterToken`, `-LiveBroadcastObserverToken`)으로 띄운다. 토큰은 변수로
   읽어 넘기고 화면·로그·문서에 **출력하지 않는다**. 기억은 켜고 이야기마다 새 DB(`-MemoryDbPath`를 ROOT 안으로),
   지식은 끈다(`-EnableKnowledge $false` — 무관한 용어 문서 검색 문제). 후보 선택은 `$env:AIRI_LIVE_BRIEFING_CANDIDATES='3'`.
5. 프록시는 분리된 프로세스(`Start-Process`)로 띄운다. `Start-Job` 안의 프록시는 소유 PowerShell 세션과 함께 사라질 수
   있다(5회차 T19 뒤 프록시 소실의 유력 원인, 메모리 부족 종료는 아니었다).

**운영 PC**: llama-server·shim 없이 Ollama가 11434에서 모델을 서빙한다. 루트 런처를 쓰면
`.\start-airi-local-stack.ps1 -LiveBroadcast -InputScreening on -LiveBroadcastMasterTokenOverride … -LiveBroadcastObserverTokenOverride …`
처럼 두 토큰을 함께 준다(주지 않으면 런처가 새 토큰을 메모리에만 만들어 시뮬레이터가 쓸 수 없다). 루트 런처는 digest를
`92a9ba2e…485f`로 고정하므로, 태그 digest가 다른 PC(이 PC는 `d297ee3d…`)에서는 `-ChatModelDigest`를 명시해야 한다.

### 3-2. 한 방송 돌리기

```powershell
$py  = 'ollama-proxy\.venv\Scripts\python.exe'
$sim = 'ollama-proxy\eval\live_broadcast_sim\sim_broadcast.py'
$root = 'C:\AIRI-Models\airi-human-eval\sim-<이름>'          # 저장소 밖 (turns.jsonl에 응답이 담긴다)
& $py $sim $root init --show airi-show-11                     # secrets.json·state.json·history.json 생성, 토큰 미출력
# → 이 ROOT의 secrets.json 토큰으로 프록시를 띄운다 (3-1)
& $py $sim $root start
& $py $sim $root turn --chat '<시청자 채팅>' --topic '<주제>' --segment '<구간>' --situation '<상황>' `
    --briefing-text '- 이번 턴에 말할 것: <AIRI 반말 문장>'
& $py $sim $root turn --chat '<다음 채팅>' --briefing-file '<브리핑 파일>'   # topic·segment·situation은 이어진다
& $py $sim $root close
```

- 첫 `turn`에는 `--topic`·`--segment`·`--situation`이 모두 필요하다. `--turn-type` 기본은 `selected_chat`이다.
- 턴마다 출력(지연 ms, marker·dialogue ms, status, receipt, `AIRI:` 답)을 읽고 다음 채팅을 쓴다. 답은 `history.json`에
  쌓여 앱처럼 다음 턴 히스토리로 간다. 브리핑 머리말은 도구가 붙인다.

### 3-3. 강제 히스토리 재실행 (replay)

```powershell
$new = 'C:\AIRI-Models\airi-human-eval\sim-replay-<이름>'     # 새 ROOT
& $py $sim $new init --show airi-replay-<이름>                # 이 ROOT의 토큰으로 프록시를 띄운다
& $py $sim $new start
& $py $sim $new replay --source '<SHOW_ROOT>' --contexts '<contexts.json>' [--capture '<capture.jsonl>']
& $py $sim $new close
```

- 턴 N을 SHOW_ROOT `turns.jsonl`의 1..N-1 턴을 히스토리로, 같은 채팅·같은 브리핑으로 다시 묻는다 → `<new>\replay.jsonl`.
  스택 변형을 같은 대화 위에서 비교하는 용도다.
- `contexts.json` 형식: `{"<segment_label>": {"topic_title": "…", "situation": "…"}}`.
- **기억을 켜야 한다.** 라이브 receipt는 메모리 저널을 요구해, 기억을 끄면 첫 receipt가 400이 되고 이후 턴이 브리핑 없이
  처리된다(2회차 재실행 1차 시도 1/24).
- `--capture`는 업스트림 캡처 JSONL의 줄 범위를 턴마다 적는 선택 옵션이다. 저장소 shim에는 캡처 옵션이 없고, 이 PC에서
  프롬프트를 캡처한 방식은 확인 필요.

## 4. 브리핑 작성 규칙 (측정 근거)

1. 턴마다 지금 말할 사실 하나(1회차 반복 2 → 2회차 0).
2. 「이번 턴에 말할 것」은 AIRI 반말 문장으로 쓴다 — 후보가 모두 탈락하면 그대로 말해진다. 스태프 메모체(「…먹었다.」,
   「운만 뗀다」)는 읽히지 않고 선택도 약해진다.
3. 「아직 말하지 말 것」 목록을 쓰지 않는다(누설 17% → 7%; 후보 선택이 켜지면 프록시도 이 줄을 뺀다).
4. 정정은 「X는 아니고 …」로 쓴다 — 프록시가 X를 다시 단정하는 후보를 거른다.
5. **(가장 먼저) AIRI 설정과 대조한다** — 방송 안에서 일어난 일과 지난 방송 기억만 쓴다. 먹기·잠·이동·운동·방송 밖 생활·없는
   취향과 관계는 쓰지 않는다. 회차 번호와 「지난 방송에서」는 실제로 쌓인 기록만 쓴다(이야기마다 새 기억 DB면 매번 첫 방송이다).
   2~10회차는 이 규칙이 없어 무효가 됐다(§2-1).

## 5. 측정했지만 채택하지 않은 것과 Jev 평가

### 5-1. 측정했지만 채택하지 않은 것

| 항목 | 결과 |
|---|---|
| 의미 모순 판정기 (Qwen2.5-0.5B LoRA) | 합성 검증 AUC 0.986, 실제 후보 0.631 (무학습 A.X 0.716, Mi:dm 0.620, 2-gram 0.532, KURE 0.541) |
| 첫 문장 조기 판정 | AUC 0.65~0.69 (2-gram·KURE 동일), 전체 답 0.81~0.88. 지연 본체는 판정이 아니라 추가 생성(재생성 363 → 237 → 180 ms, 프롬프트 재사용). 슬롯 3개 동시 생성 597 ms·GPU +1.5 GB로 이득 없음 |
| Ollama 템플릿 교체 | Ollama 0.34.2는 GGUF 내장 공식 템플릿(약 500토큰 안내문, 경어체·의인화 금지 지시 포함)을 쓴다. 템플릿 4종 초안 비교(시드 6) 38~44% — 차이 없음. 운영 변경 불필요 |
| A.X-4.0-Light (Apache-2.0) | 강한 머리말에 반응(43 → 54/69)하나 단독 약 4.5 GB VRAM — TTS·STT와 8 GB 동거 어려울 전망(미실측) |
| 프롬프트 배치·머리말 변경 | Mi:dm 무반응 (39~42%) |

### 5-2. Jev(System1) 평가 요약 — 「jev 도입의 효과」 답

- **구조(후보 생성 + 빠른 결정 + 대체)는 효과가 크다.** /v1 경로에서 선택 없음 약 6~8/25(04회차) →
  후보 3개 + 브리핑 문장 약 18/24(06회차), 새 이야기 10/11(10회차)(§2-1).
- **학습된 작은 판정기는 실제 방송에서 아직 규칙을 못 넘는다**(§5-1 모순 판정기 0.631).
- 대본형(09-23) 비교에서는 System1 0.6이 규칙보다 +15%p(독립 판정 71% 대 56%)였으나 그 시나리오는 무효 판정됐다.

## 6. 테스트 상태

- 전체 오프라인 스위트(09-24 13:17, 스택 내림, 설정 문장 변경 포함 미커밋 트리,
  `python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor`):
  **2449 passed, 16 skipped, 5 failed** (11:10 실행 2445 + 새 테스트 4). 5개는 기존 기준선이다 — 이 PC의 PowerShell 실행 정책으로 막히는
  `test_airi_session_header_patch` 4개, HEAD `d2d7c91`에서도 같은 해시로 실패하는 `test_synthesize_broadcast_continuity_v4` 1개.
  STT 테스트는 프록시 venv에 `av`가 없어 제외했다.
- 문서 계약 테스트 `test-airi-work-continuity.ps1`, `test-airi-roadmap-dashboard-contract.ps1`: 현행화 전 PASS, 현행화 편집 뒤
  최종 재실행(2026-09-24 11:59 KST)도 둘 다 PASS(exit 0). 같은 시각 `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`
  exit 0 — 이 검사는 추적 파일만 보므로 미추적 새 문서(이 문서, `참조/claude-guide/` 6개)는 따로 검사했다(끝 공백 0, BOM 없음, CRLF 통일).

## 7. 다음 단계와 고정 울타리

### 7-1. 남은 일 (우선순위 순)

1. **교정 학습(본질안 — 사용자 선택 「단기 + 본질 병행」)**: 설정 밖 전제 질문에 설정대로, 여러 표현으로 답하는 교정 데이터로
   Mi:dm LoRA를 학습해 모델 버릇 자체를 고친다. 이 PC 가능 여부(09-24 조사): GPU PC도 8 GiB 카드였고 Stage 3 학습 최대
   CUDA 메모리는 약 5.3 GB(`gpu_pc_stage3_r2_receipt`)라 VRAM은 맞을 전망이다. 없는 것: Mi:dm 2.0 Mini HF 가중치
   (`C:\AIRI-Models\hf\`에는 Qwen2.5-0.5B만), 학습 venv의 bitsandbytes(RTX 5060 Ti 지원 버전 확인 필요). 라이선스는 문서
   기준 MIT(`K-intelligence/Midm-2.0-Mini-Instruct`, 원본 모델 카드 재확인 필요). 다운로드·설치·GPU 장시간 사용은 사용자 승인 뒤.
2. **series-01 2회**: 1회 투표대로 끝말잇기(방송 안 활동), 같은 기억 DB — 1회 기억(투표 결과, 시청자 면접 이야기)을 불러오는지
   확인한다. 1회 첫 턴에 기억이 비어 있어 「지난 방송」 호출은 아직 한 번도 검증되지 않았다.
3. 1회에 남은 결함: 자기 모순(「떨린다」 → 「떨림을 못 느낀다」), 한 문장짜리 짧은 반응(T02·T06·T09).
4. 설정 문장이 질문마다 거의 같다 — 같은 방송에서 반복되면 대본처럼 들릴 수 있다(사람 판정 필요, 1이 근본 해결).
5. GPU PC: TTS 포함 첫 음성 지연, 8 GB 동거 실측.
6. 운영 반영 결정: `AIRI_LIVE_BRIEFING_CANDIDATES=3`을 켤지(현재 기본 꺼짐 — 설정 문장·몸 경험 거름도 이 안에 있다), 방송 턴을
   보낼 앱 쪽 연결(B1b/B4) 미구현.
7. System1 재도전은 실제 방송 후보에 사람 정답을 매긴 데이터로 한다.

10회차 사람 판정은 끝났다(설정 밖 이야기로 무효 — §2-1). 7회차 소화기 지어내기도 설정 밖 이야기에서 나온 것이라 2·1로 흡수됐다.

기존 로드맵 M8 체크리스트·완료율은 이번 작업으로 **바뀌지 않는다**(M8 항목이 아니다).

### 7-2. 고정 울타리

- `adoption_authorized=false` — 운영 채택 금지. 기본 꺼짐 기능을 운영에서 켜는 것도 사용자 결정이다.
- 이 PC에서는 AIRI 앱을 설치·실행하지 않는다.
- 커밋은 사용자 승인 뒤에만, push는 **매번** 승인을 받는다(origin/main `2abe9e4` 이후 커밋 전부 미push).
- 응답이 담긴 대본·후보·평가 산출물은 `C:\AIRI-Models\` 아래(Git 밖)에 두고, `secrets.json` 토큰·`.env` 값은 출력·기록하지 않는다.
