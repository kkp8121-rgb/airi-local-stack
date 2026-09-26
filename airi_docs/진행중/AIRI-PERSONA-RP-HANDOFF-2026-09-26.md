# AIRI 캐릭터 RP 트랙 인계 (2026-09-26, 신규 PC)

> 이 문서가 다음 세션과 다른 PC의 **현재 인계 진입점**이다. 라이브 방송 시뮬레이션의 실행법, 09-24까지의 회차 결과,
> 브리핑 작성 규칙은 [`AIRI-LIVE-BROADCAST-HANDOFF-2026-09-24.md`](AIRI-LIVE-BROADCAST-HANDOFF-2026-09-24.md)에 그대로 유효하고,
> 이 문서는 09-24 저녁부터 09-26까지의 캐릭터 RP 작업을 이어받는다. 시각·명령·SHA receipt는
> [`AIRI-WORKING-STATE.md`](AIRI-WORKING-STATE.md) frontmatter에 있다. 문서와 기계 상태가 다르면 실행하지 말고 관측값으로 먼저 정정한다.

## 0. 읽는 순서와 기계 사실

1. `AGENTS.md`
2. [`AIRI-WORKING-STATE.md`](AIRI-WORKING-STATE.md) — 전체를 읽고 `git status`·HEAD·PID·산출물 SHA와 read-only로 대조
3. 이 문서, 이어서 [`AIRI-LIVE-BROADCAST-HANDOFF-2026-09-24.md`](AIRI-LIVE-BROADCAST-HANDOFF-2026-09-24.md) §3(스택·시뮬레이터 실행법)·§4(브리핑 규칙)
4. [`../로드맵/AIRI-ROADMAP-STATUS.md`](../로드맵/AIRI-ROADMAP-STATUS.md), [`../../NEXT-SESSION.md`](../../NEXT-SESSION.md)

| 항목 | 값 (09-26 00:04 KST) |
|---|---|
| 작업 PC | 신규 PC — RTX 5060 Ti 8 GiB, D: 없음, RAM 32 GB. GPU PC가 아니다. 이 PC에서는 AIRI 데스크톱 앱을 **설치·실행하지 않는다** |
| Git | `main` = `origin/main` = `c1186797d39f142e05b6ca49ab2698d451c04e63` (09-26 00:03 사용자 승인 push, `2abe9e4..c118679` 22커밋). 저장소는 **공개(PUBLIC)** |
| CI | `Remediation checkpoint` 워크플로가 `disabled_manually` 상태라 push로 돌지 않는다(마지막 실행 2026-08-19/20, 모두 실패). 다시 켤지는 사용자 결정 |
| 스택 | 정지(11434/11435/11500 listener 0) |
| 테스트 | 전체 오프라인 스위트 2460 passed, 16 skipped, 5 failed(기존 기준선: `test_airi_session_header_patch` 4, `test_synthesize_broadcast_continuity_v4` 1), 문서 계약 2개 PASS |
| 학습 자산(저장소 밖) | 가중치 `C:\AIRI-Models\hf\Midm-2.0-Mini-Instruct` (K-intelligence/Midm-2.0-Mini-Instruct revision `383eb221c52a32278f1985257b264ade8d982e60`, **MIT**, `model.safetensors` SHA-256 `03755deae6cc183c9957bcf7b753924b0d1284e1b44aea95aaa822594765e70b` = HF LFS) · 학습 venv `C:\AIRI-Models\venvs\train-midm` (torch 2.11.0+cu128, transformers 4.46.3, peft 0.13.2, bitsandbytes 0.50.2 — torch·bitsandbytes는 이 GPU 때문에 `requirements-training.txt`와 다르다) |
| 데이터(저장소 밖, 응답이 담긴 자료) | `C:\AIRI-Models\train\persona-v1\` — 대화 원본 `threads-v2.json`, 캡처 `capture-run-v2\turns-captured.jsonl`, 데이터셋 `persona-v2.unauthorized.jsonl`, 검토 페이지 `review-v2.html`, 스크립트 `scripts\` |

## 1. 09-24 저녁~09-26에 일어난 일

1. **설정 판정**: 사용자가 10회차를 검토하고 「자전거 붉닭등 아이리가 못하는걸 지어내서 말하고 있어」라고 했다. 2~10회차 브리핑이
   버추얼 AIRI에게 몸으로 한 경험을 말하게 했으므로, 그 회차의 깨끗한 턴 수는 브리핑 따르기만 잰 값이다.
2. **설정 범위 결정**: 방송 안 일 + 지난 방송 기억만(「필요하면 추후에 확장하는 방향으로」).
3. **series-01 1회**(진짜 첫 방송): 모델이 스스로 「김치찌개 먹었어」라고 지어냈다. 「뭐 먹었어?」에 메뉴 추천을 붙이던 코드
   오작동을 고쳤다(`e9e6f65`).
4. **설정 문장 대체**(`48cd8e1`, 기본 꺼짐)를 넣었다. 표본마다 기억 세션을 나눈 재측정에서 약 33/36이 설정에 맞았고, 기준선은
   약 6/36이었다. 처음 보고한 36/36은 표본이 기억 회상으로 섞인 측정이라 정정했다(`300bc02`).
5. **캐릭터 부재 판정**: 교정 데이터 canon-v1을 보고 사용자가 「재밌는 rp가 없네 … 버추얼이고 기계라 밥을 못먹는다가 이어지고
   있어 질문 내용도 깊지 못한 단발성이고」라고 했다. canon-v1은 보류했다.
6. **RP 설계**: 워크플로 `airi-rp-design`(설계안 4개 + 설정 판정자 + 재미 판정자 + 종합)으로 설계를 만들었다. 결과는
   `C:\AIRI-Models\train\rp-design.html`과 `rp-design-wf_b1120962.json`에 있다.
7. **사용자 결정**(§2)에 따라 코드 3건을 넣었다(`0b7fc02`·`b638ac0`·`b54d8c3`).
8. **대화 88개 작성**: 워크플로 `airi-rp-threads`(작성 4 + 엄격 검증 4)로 88개 대화(764턴)를 썼다. 첫 캡처는 메모리 부족으로
   196턴에서 강제 종료됐다(09-25 18:53). 사용자 요청으로 불필요한 프로그램(작업 관리자, C# 컴파일 서버, Chrome, GitKraken)을
   정리했다(20:11~21:20). 21:21에 재개해 21:25에 764턴을 마쳤다.
9. **무례 판정**: 첫 판본을 사용자가 「처음부터 실페 이건 그냥 싸가지가 없는건데 … 내게 테스트를 원하기 전에 미리 한번
   체크해보겠어?」라고 판정했다. 원인은 기질 카드의 「살짝 건방짐」과 판정·벌칙·숙제 장치였다. 그 결과 AIRI가 시청자를
   심문하고 명령했고(「대 봐」, 「자수해」, 「처음 왔으면 규칙부터」), 명령형 어미가 764줄 중 80줄이었다.
10. **말투 재작성**: 기질 카드를 따뜻한 진행자로 고쳤다. 워크플로 `airi-rp-tone-rewrite`(재작성 4 + 독립 말투 판정 4)로 다시
    쓴 뒤 손으로 검토해 **persona-v2**(목표 668턴)를 만들었다. 첫 판본은 `review-v1-withdrawn-rude.html`로 이름을 바꿔
    폐기했다(삭제하지 않음).
11. **푸시**: 사용자 승인으로 22커밋을 올렸다(09-26 00:03). 이 인계 문서는 그 뒤에 썼다.

## 2. 사용자 결정 (09-24~26, 원문 취지)

| 주제 | 결정 |
|---|---|
| 설정 범위 | 방송 안 일 + 지난 방송 기억만, 필요하면 나중에 넓힘. 게임·영상 같은 화면 속 활동과 가상 생활은 아직 넣지 않는다 |
| 지어내기 대책 | 단기(설정 문장 대체) + 본질(교정 학습) 병행 |
| 기질 | 반응 규칙으로 캐릭터 설정에 넣는다. 고정 말버릇은 넣지 않는다 |
| 판정·상상·기억 | 권장 묶음을 따른다. 판정은 시청자의 설명·디테일·논리로만 한다(맛·원래 취향 금지). 「만약에」는 시청자에게 넘긴다. 다음 방송 기억은 약속·승패 |
| 시청자 이름 | **넣지 않는다.** `chat-ingress/README.md`의 개인정보 경계(표시 이름을 모델 프롬프트에서 뺌)를 그대로 둔다. AIRI는 내용으로 부른다(「김치찌개 먹은 사람」) |
| 학습 형식 | 새 형식 추가(이전 대화 약 4턴). 09-24의 「짧은 맥락」 결정을 대체한다 |
| 학습 대화 작성 | Claude가 작성한다. Anthropic 약관의 「경쟁 AI 모델 학습」 금지에 AIRI 캐릭터 LoRA가 해당하지 않는다고 사용자가 판단했다 |
| 말투 | 따뜻한 진행자. 장난은 자기 자신이나 상황을 향한다. 시청자에게 명령·심문·훈계·깎아내리기·호칭 강요·숙제를 하지 않는다 |

## 3. 코드 상태 (모두 `main`에 있음, 새 동작은 기본 꺼짐)

| 커밋 | 내용 | 켜는 방법 |
|---|---|---|
| `e9e6f65` | 「점심 뭐 먹었어?」 같은 과거형 식사 질문을 메뉴 선택 질문으로 보지 않는다(모든 경로) | 항상 적용 |
| `48cd8e1` | 설정 문장 대체 + 몸 경험 거름(`live_briefing_select`) | `AIRI_LIVE_BRIEFING_CANDIDATES=2~6` |
| `0b7fc02` | 트레이너 `airi.persona-rp.v1` 형식: 최대 18메시지, role/content만, id·`thread_group`·`behavior`·`author` 필수, `review`의 두 플래그는 불리언 그대로(`user_aggregate_authorized: true`, `adoption_authorized: false`), `thread_group`은 분할을 넘지 못함 | 데이터 행의 `schema_version` |
| `b638ac0` | 기질 카드 `persona_temperament.py`: 방송 상황 메모 맨 앞에 붙는다. `/health` `persona_temperament` | `AIRI_LIVE_PERSONA_TEMPERAMENT=on` |
| `b54d8c3` | 거름 규칙 오탐 수정: 과거형 스태프 메모체만 거른다(「복수한다」는 통과). 몸 경험 단어 바로 뒤가 「구나·겠」이면 시청자에 대한 반응으로 본다 | 후보 선택 안 |

**충돌 주의**: 기질 카드와 설정 문장 대체를 함께 켜면, 대체가 「나는 버추얼이라 밥은 못 먹어!」 같은 고정 문장을 강제한다.
카드가 금지한 평평한 답이 나오는 셈이므로, 평가할 때는 두 플래그의 조합을 따로 잰다.

## 4. persona-v2 데이터

| 항목 | 값 |
|---|---|
| 대화 | 88개(몸·방송 밖 질문 22, 시청자 소식 26, 게임 18, 토론 22). 1회 44 / 2회 44, 764턴, 시청자 이름 없음. 2회 대화는 1회 기억 세 가지(투표로 끝말잇기, 면접 합격, 김밥 두 줄)만 쓰고, 그 사실은 브리핑의 「지난 방송 기억」 줄로 프롬프트에 들어간다 |
| 원본 | `threads-v2.json` SHA-256 `c61fec34b52b2ba883fb0a2e987c41182d8d17e4efcdd8feeb5f04e155020de9` |
| 캡처 | `capture-run-v2\turns-captured.jsonl`: 764/764턴. 새 기질 카드가 올라간 프록시(09-25 23:27:57 기동)로 받았다. 턴마다 기억 세션을 나눴다(회상 블록 0), 기록은 최대 4턴 |
| 데이터셋 | `persona-v2.unauthorized.jsonl` SHA-256 `783fb493dc73f04778e2ca8c4f4100b7ca02c9ad86723670dbaa5154d29977e5`. 목표 668행(train 533 / dev 68 / test 67, 대화 단위 분할), 나머지 96턴은 기록으로만 쓴다(자주 쓰는 틀의 목표 상한, 대화당 한계 인정 1회, 코드 오작동 3). 토큰 2,085~2,441 |
| 승인 전 차단 | 모든 행이 `user_aggregate_authorized: false`라 트레이너가 거부한다(의도). 승인 뒤 `--authorized`로 다시 빌드하면 `persona-v2.jsonl`이 생긴다 |
| 검토 페이지 | `review-v2.html` SHA-256 `2665a0638cdb7dd735ebc72fe1b4ef458a977326f679f7241a479883b7752258`. 대화별 좋음/고침/빼기, AIRI 대사 즉석 수정, JSON 저장(`persona-v1-data-review.json` 이름으로 내려받는다) |
| 말투 검사 | 독립 판정자 따뜻함 4.5(4개 배치 모두), 목표 행 명령형 어미 0. 손으로 읽은 것: 88개 대화의 첫 두 턴, 재작성 검토 때 무작위 뒤쪽 턴 60줄, 최종 목표 행 무작위 30줄 |

## 5. 다음 단계 (우선순위 순)

1. **사용자 검토 대기**: `review-v2.html`. 사용자가 JSON(`persona-v1-data-review.json` 이름으로 내려받음)을 주면 반영한다.
   반영 도구는 없으니 `threads-v2.json`에 손으로 고친다: 「빼기」 대화는 지우고, 「고침」 문장은 그 턴의 `airi`에 넣는다.
   대화를 빼면 dev/test 분할이 다시 섞인다. 대화 기록이 바뀌었으니 다시 캡처하고 `--authorized`로 다시 빌드한다(§6-1).
2. **본 학습**(§6-2): `--max-steps`는 **마이크로스텝** 수다(배치 1, 기울기 누적 8이면 8스텝에 옵티마이저 1회).
   - 시간(추정, 미측정): GPU PC가 1536토큰에서 504스텝에 28.5분 걸렸다(스텝당 약 3.4초). 이를 약 2,300토큰으로 환산하면
     1에폭(533스텝)이 약 40~60분, 3에폭(1,599스텝)이 약 1.5~2.5시간이다.
   - 설정: GPU PC Stage 3 r2(168행)에서 dev 손실이 1에폭 뒤 가장 낮았다(2.32 → 2.63 → 3.06). 그래서 1~2에폭부터 권한다.
     트레이너는 dev 최저 상태를 복원해 저장한다.
   - 운영: VRAM 약 6~7 GB. 사용자가 PC를 덜 쓸 때 돌리고, 학습 전후로 live state에 intent/receipt를 남긴다.
3. **병합·GGUF 패키징·평가**: `merge_airi_behavior_lora.py` → `package_airi_gguf.py`. **이 PC에는 패키징 준비물이 없다.**
   - `package_airi_gguf.py`는 SHA가 고정된 llama.cpp 변환 스크립트(`--converter-script`)와 양자화기(`--quantizer`)를 요구한다.
     이 PC에는 `convert_hf_to_gguf.py`가 없고, Ollama 동봉 `llama-quantize.exe`만 있다. 가져오려면 설치 결정이 필요하다.
   - 패키저의 Modelfile은 `TEMPLATE {{ .Prompt }}`·`num_ctx 2048`이라 공식 Mi:dm 템플릿이 아니다. 학습 템플릿(공식)과 서빙
     템플릿을 맞추는 방법은 확인 필요.
   - 공정한 비교를 위해 기준선과 학습 모델을 같은 템플릿으로 서빙한다.
   - 평가 ① 설정 밖 전제 질문 36개: `scripts\canon_probe.py ROOT OUT.jsonl --samples 6 --variants v0_current`. 표본마다 기억
     세션을 나눈다. 기질 카드만 켜고 설정 문장 대체는 끈다.
   - 평가 ② series-01 2회 방송: 스택 실행에 `-MemoryDir C:\AIRI-Models\airi-human-eval\series-01`을 줘서 1회의 기억 DB를 이어
     쓴다(주지 않으면 ROOT 안에 새 DB가 생긴다). 1회 투표대로 끝말잇기를 한다.
4. **프록시 오작동 3건**(데이터 캡처 중 발견, 테스트부터 작성해 고친다):
   - 「그건 못함 이불 밖은 위험해」(밈) → 긴급 안전 확인 문장(`urgent_safety_context`)
   - 「맞춤법 퀴즈 ㄱ 안되 vs 안돼 뭐가 맞음」 → 「아직 이 언어는 안전하게 판별하지 못해」(언어 판별)
   - 「… 연습 좀 시켜줘」 → 「그건 내가 직접 실행할 수 없어.」(행동 요청 판별)
5. **알려진 규칙 한계**: 몸 경험 거름과 과거형 메모체 규칙이 「까먹었으면」, 「고생했다」 같은 자연스러운 말을 여전히 오탐한다.
   후보 선택이 켜진 턴에만 영향이 있다.
6. **사용자 결정 대기**: CI 워크플로를 다시 켤지(마지막 실행이 모두 실패였으므로 켜기 전에 원인 확인이 필요하다). 운영에서
   `AIRI_LIVE_PERSONA_TEMPERAMENT`·`AIRI_LIVE_BRIEFING_CANDIDATES`를 켤지(현재 기본 꺼짐, `adoption_authorized=false`).

## 6. 명령

### 6-1. 다시 캡처하고 데이터셋 빌드

스크립트는 `C:\AIRI-Models\train\persona-v1\scripts\`에 있다(세션 임시 폴더에서 옮겨 둔 사본, 저장소 밖). 절대 경로가 박혀 있다.

```powershell
$S = 'C:\AIRI-Models\train\persona-v1\scripts'
$py = 'C:\Projects\airi-local-stack\ollama-proxy\.venv\Scripts\python.exe'
$sim = 'C:\Projects\airi-local-stack\ollama-proxy\eval\live_broadcast_sim\sim_broadcast.py'
$root = 'C:\AIRI-Models\train\persona-v1\capture-run-v3'           # 새 ROOT
& $py $sim $root init --show airi-persona-capture-03
# 0) Ollama serve가 11434를 잡고 있으면 먼저 멈춘다(로그인 때 자동 시작된다). 스택 스크립트는 Ollama를 멈추지 않는다.
Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process
# 스택: 기질 카드 켬, 설정 문장 대체 끔, 캡처 켬(-CapturePath가 있으면 scripts\capture_shim.py가 11434에 뜬다)
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$S\swap-generator.ps1" `
    -Gguf 'C:\AIRI-Models\gguf\midm-2.0-mini-instruct.Q4_K_M.gguf' -Tag 'midm-airi:2.0-mini' `
    -Digest 'd297ee3db6f3380c4038d2cd7aa7d0076cdb1b76e4c9578499e459af428cfe11' `
    -TemplateFile 'C:\Projects\airi-local-stack\ollama-proxy\training\system1\midm-airi-chat.jinja' `
    -Knowledge false -Memory true -LiveSecrets "$root\secrets.json" -CapturePath "$root\capture.jsonl" `
    -LiveBriefingCandidates 0 -PersonaTemperament
& $py $sim $root start
& $py "$S\capture_threads_v2.py" $root "$root\capture.jsonl" "$root\turns-captured.jsonl"   # 새 ROOT면 764턴 전부(약 7분)
& $py $sim $root close
# 1) 학습 전에 반드시 스택을 내린다(llama-server가 VRAM을 잡는다). stop-airi-local-stack.ps1은 프록시만 멈추고 llama-server·shim은 남긴다.
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*llama-server*--port 11500*' -or $_.CommandLine -like '*llama_server_shim.py*' -or $_.CommandLine -like '*capture_shim.py*' -or $_.CommandLine -like '*ollama_proxy.py*--port 11435*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# 2) build_persona_dataset_v2.py 18행의 CAPTURED 경로를 새 ROOT로 바꾼 뒤
python "$S\build_persona_dataset_v2.py" --authorized                # 사용자 승인 뒤에만 --authorized
```

- 스택 실행 스크립트는 기존 평가 프로세스(llama-server 11500·shim·프록시 11435)를 먼저 멈추고 새로 띄운다. 기억은 ROOT 안의
  새 DB를 쓴다(측정마다 분리). 시리즈 기억 DB는 series-01 방송에서만 `-MemoryDir`로 쓴다.
- `capture_threads_v2.py`는 OUT 파일에 이미 있는 턴만 건너뛴다. 같은 ROOT로 이어 받을 때만 일부가 건너뛰어진다.
- 빌드할 때마다 `review-v2.html`도 다시 쓴다. 해시와 브라우저 저장 키가 바뀌므로, 사용자가 검토 중이면 빌드 전에 JSON을 먼저 받는다.
  출력 줄의 페이지 이름은 `review.html`로 잘못 찍히지만, 실제로 쓰는 파일은 `review-v2.html`이다.
- `select_shim.py`는 옮기지 않았다(`-SelectCandidates`를 쓸 때만 필요하다).
- 스크립트 사본은 저장소 밖이다. 재사용이 확정되면 저장소(`ollama-proxy/training/persona/` 등)로 옮기고 테스트를 붙인다.

### 6-2. 본 학습 (사용자 승인 뒤)

```powershell
$T = 'C:\AIRI-Models\train\persona-v1\run-v2'
& 'C:\AIRI-Models\venvs\train-midm\Scripts\python.exe' 'C:\Projects\airi-local-stack\ollama-proxy\training\train_airi_behavior_lora.py' `
    --dataset 'C:\AIRI-Models\train\persona-v1\persona-v2.jsonl' --dataset-sha256 <승인본 SHA-256> `
    --model-dir 'C:\AIRI-Models\hf\Midm-2.0-Mini-Instruct' `
    --model-sha256 03755deae6cc183c9957bcf7b753924b0d1284e1b44aea95aaa822594765e70b `
    --output "$T\adapter" --report "$T\report.json" --mode cuda-qlora --run-dir "$T\run" --run-id persona-v2-r1 `
    --max-seq-len 2464 --batch-size 1 --gradient-accumulation 8 --learning-rate 1e-4 --max-steps <train 행 수 × 에폭 수>
```

- 실행 전에 §6-1의 1)처럼 평가 스택을 내리고 `nvidia-smi`로 VRAM 여유를 확인한다.

- 09-24 시험 학습(2스텝, 2,304토큰)의 최대 CUDA 메모리는 6,108,230,144 bytes였다. 데스크톱이 약 1.3 GB를 쓰므로 여유는 약 1 GB다.
- GPU PC Stage 3의 교훈: dev 손실은 1에폭 뒤에 가장 낮았다. 트레이너는 dev 손실이 가장 낮은 지점(`selected_dev_step`)을 고른다.
- cuda-qlora는 dev와 test 분할이 모두 있어야 한다.

## 7. 고정 울타리

- `adoption_authorized=false` — 운영 채택 금지. 기본 꺼짐 기능을 운영에서 켜는 것도 사용자 결정이다.
- 이 PC에서는 AIRI 앱을 설치·실행하지 않는다. 산출물을 자동으로 열지 않는다.
- commit·push는 요청마다 승인을 받는다(승인은 1회성). 저장소가 **공개**이므로 개인 경로·토큰·응답 데이터가 커밋에 섞이지 않게
  push 전에 범위를 검사한다(09-26 푸시 전 검사: 비밀값 0, 개인 경로 0).
- 응답이 담긴 대본·대화·데이터셋·검토 페이지는 `C:\AIRI-Models\` 아래(Git 밖)에 둔다.
- 시청자 이름을 프롬프트나 기억에 넣지 않는다(개인정보 경계). 넣으려면 `chat-ingress` 계약을 바꾸는 별도 결정이 필요하다.
- AIRI 대화나 페이지를 사용자에게 보이기 전에 말투(명령·심문·훈계·깎아내리기·차가움)를 먼저 스스로 검사한다.
- receipt 시각은 기록하기 직전에 `date`로 확인한다(09-24에 짐작한 시각을 두 번 적었다).
