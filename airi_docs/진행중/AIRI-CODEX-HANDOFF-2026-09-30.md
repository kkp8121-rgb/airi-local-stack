# AIRI 인계 — Codex용 (2026-09-30 19:5x 기준, Claude 작성 · 2026-10-01 갱신 §6-2·§8)

> 사용자 목표(2026-09-29): 「계속 개선해 실제 방송에 사용 가능할 때까지」 — `goal_status=active`, `adoption_authorized=false`.
> 2026-09-30 세션은 사용자 지시(「커밋 푸시하고 오늘은 종료」)로 끝났다. 이 문서는 Codex가 이어받는 첫 문서다.
> 상세 근거는 `AIRI-BROADCAST-READINESS-HANDOFF-2026-09-29.md`(§7 운영자 절차, §8-1~§8-8 라운드별 기록)와
> `AIRI-WORKING-STATE.md`의 2026-09-30 receipt들이다. 이 문서와 어긋나면 live state와 실제 기계 상태가 이긴다.

## 0. 한 줄 상태

아직 실제 방송에 채택할 단계가 아니다(사용자 결정: 채택 보류, 시뮬레이션으로 결함을 계속 찾는다). 방송 모델은 persona-v4
(NUL 종료 GGUF `d914dc16…`)이고, 품질은 대부분 프록시의 고정 문장·앞말·걸러내기 규칙이 지킨다. 오늘 v6 재학습은 v4보다
낫지 않아 후보에서 뺐고, 평가와 모의 방송에서 찾은 프록시 결함 13건(`214a7bd` 4건, `59586da` 9건)을 고쳐 push했다.

## 1. 먼저 읽을 것 (순서대로)

1. `AGENTS.md` — 저장소 계약(세션 시작·heartbeat·intent/receipt 규칙 포함).
2. `airi_docs/진행중/AIRI-WORKING-STATE.md` — live SSoT. 머리말(`goal_status`·`git_head`·`worktree_state`·`active_trainer_count`)을
   `git status`·HEAD·실행 중 PID와 read-only로 대조한다. 최신 receipt: `ep19_fix_receipt_20260930`, `session_end_20260930`.
3. 이 문서.
4. `airi_docs/진행중/AIRI-BROADCAST-READINESS-HANDOFF-2026-09-29.md` — §7(운영자 형식), §8-7(v6), §8-8(ep19), §9.
5. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`, `NEXT-SESSION.md`.

## 2. 기계 사실 (신규 PC — 이전 GPU PC(Codex PC)와 다른 PC)

- RTX 5060 Ti 8 GiB, D: 없음. **이 PC에는 AIRI 데스크톱 앱을 설치하거나 켜지 않는다**(사용자 지시). TTS(GPT-SoVITS)·STT 없음.
- **이 PC의 GPU는 모델 개선·학습에만 쓴다(학습, 변환, 평가 스택·모의 방송). TTS는 이 PC에서 쓰지 않는다**(사용자 2026-10-01).
- 스마트 앱 컨트롤(강제)이 `train-midm` venv의 CUDA torch를 막는다(`WinError 4551`). **끄지 않는다.** 학습은
  `C:\AIRI-Models\venvs\probe-cu128`, 병합·GGUF·토크나이저는 `C:\AIRI-Models\venvs\llamacpp-convert`, 테스트는 `ollama-proxy\.venv`.
- 평가 도구와 대화가 담긴 결과는 저장소 밖이다: 스크립트 `C:\AIRI-Models\train\persona-v1\scripts\`, 결과
  `C:\AIRI-Models\airi-human-eval\persona-v4-eval-20260929\`·`persona-v6-eval-20260930\`. 대화·후보·캡처는 Git에 넣지 않는다.
- 세션 종료 시점: 평가 스택·학습·Ollama 모두 꺼짐(포트 11434/11435/11500 비어 있음), `active_trainer_count 0`.

## 3. 2026-09-30에 한 일과 커밋 (모두 origin/main에 push)

| 커밋 | 내용 |
|---|---|
| `214a7bd` fix | 방송 중 부고 위로 문장 순환(방송 모드), 앞말은 실제로 붙을 때만 "말함"으로 기록, 게임·기기 "죽었어"는 사별 아님, 시청자에게 하는 말("잠들어도 괜찮아")은 통과·아이리 주어 주장은 거부 |
| `4e9608f` docs | v6 라운드 기록 |
| `59586da` fix | ep19 모의 첫 방송 결함: 첫 방송 "어제 방송" 교정, 오늘 순서 형식, 나쁜 소식에 핀잔·축하 거름, 먼저 여는 끝말잇기 거름, 가족 수술·병에 희망 앞말, 롤 하다가 죽은 말, "토요일 몇 시?" 후속 질문과 지어낸 시각, 마무리의 다른 소식, 계획·끝인사 한 번만 |
| (이 문서가 든 docs 커밋) | ep19 기록, 인계서 §8-8, 이 문서 |

- persona-v6(말투 보강 재학습): 사용자가 승인한 146행 + v4 재학습분 240행으로 v4에서 이어 학습했다. 보류 데이터·R1 설정 질문·
  51턴 방송·끝말잇기 방송 모두 비기거나 v4가 조금 나았다(§8-7). 산출물 `run-v6`는 남겨 두되 후보가 아니다.
- 교훈: 새 행 100개 규모의 재학습으로는 말투가 거의 안 바뀐다. 다음 재학습을 제안할 때는 데이터가 몇 배 필요하다고 먼저 말한다.

## 4. 방송 스택 (평가용, 기본 꺼짐 기능 포함)

- 띄우기(분리 실행): `powershell -File C:\AIRI-Models\train\persona-v1\scripts\launch-detached.ps1 -MemoryDir <root>
  -LiveSecrets <root>\secrets.json -SuperviseProxy`. 기본 GGUF = persona-v4 NUL. 안에서 `swap-generator.ps1`이 이전 스택을 끄고
  llama-server(:11500) → shim(:11434) → 프록시(:11435)를 올린다. 켜지는 방송 기능: 후보 선택 3개
  (`AIRI_LIVE_BRIEFING_CANDIDATES`), 태그 문맥, 끝말잇기 심판 단어표, 방송 이월 메모, 기질 카드, 감시 재시작, `PYTHONFAULTHANDLER=1`.
- 모의 방송: `sim_broadcast.py <root> init|start`(저장소 `ollama-proxy/eval/live_broadcast_sim/`), 구간·상황은
  `sim_tag.py <root> context --topic … --segment … --situation …`, 시청자 한 턴은 `sim_tag.py <root> turn --chat "…"`.
  시청자는 **아이리의 실제 답에 반응**해야 한다(대본을 미리 쓰지 않는다). 끝말잇기는 아이리가 실제로 낸 단어에서 잇는다.
- 같은 채팅 다시 돌리기·비교: `replay_tag_show.py <새 root> <원본 tag-turns.jsonl> <contexts.json>`,
  `compare_shows.py OUT.txt 이름=root …`(반복 문장·짧은 답·"오늘도"·걸러내기 수). 모델 비교는 `eval_v6.sh`·`eval_v6_chain.sh`,
  보류 데이터는 `gen_test_gguf.py` + `heldout_metrics_v6.py`, 설정 질문 R1은 `canon_probe.py … --variants v0_current`.
- 운영자 형식(§7): 오늘 순서 "오늘 순서는 A, B, C다."(또는 "오늘은 A, B, C 순서다."), 다음 방송 "다음 방송은 토요일 저녁이다."
  (적지 않은 시각은 걸러진다), 꼭 말할 문장 "- 이번 턴에 말할 것: …", 이월 메모 "- 약속: …"/"- 결과: …".

## 5. 규칙과 함정 (Claude가 오늘 겪은 것 포함 — 반드시 지킨다)

- **커밋·push는 사용자 승인 뒤에만, push는 매번 따로.** 작성자 `kkp8121-rgb <kkp8121@gmail.com>`. 공개 저장소라 push 전에 추가된 줄에서
  개인 경로·비밀값을 검사한다. push는 kkp8121-rgb 계정 토큰을 그 명령에서만 쓰는 방식(credential helper 일회 주입)으로 하고, 토큰을
  출력하지 않는다. `.claude/agent-memory/implementer/*`는 커밋하지 않는다(합의).
- 새 프록시 동작은 기본 꺼짐, `adoption_authorized=false` 유지. 아이리 대사를 사용자에게 보이기 전에 말투(명령·캐묻기·훈계·
  깎아내림·냉담)를 먼저 직접 검사한다. 모델을 추천할 때는 1차 출처에서 라이선스를 확인해 함께 적는다.
- **live state**: 시각은 반드시 `date`로 잰다(추정 금지). 머리말 값은 YAML 큰따옴표 문자열이라 Windows 경로는 `C:/…`로 쓰고,
  수정 뒤 `yaml.safe_load`로 파싱을 확인한다(09-26~09-30 동안 파싱이 깨져 있었다). 작업본은 CRLF다. 10분 넘는 명령은
  intent → receipt. `goal_status`는 `active|paused|complete|blocked`만 되고, 바꾸면 `test-airi-work-continuity.ps1`이
  NEXT-SESSION·`AIRI-CODEX-HANDOFF-2026-08-21.md`·로드맵에 같은 `goal_status=…` 문자열을 요구한다.
- **테스트**: `ollama-proxy\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider ollama-proxy test_latency_trace.py
  test_start_airi_background.py latency-monitor`(stt 제외). 알려진 실패 5건(session-header-patch 4, continuity-v4 1)이 기준선이다
  (오늘 끝 2681 통과). `test-current-checkpoint.ps1`은 머신 `PSModulePath`와 `llamacpp-convert\Scripts`를 PATH 앞에 두고 돌리면
  B4c 전까지 통과하고(학습 내구성 단계는 가끔 30초 타임아웃 — 다시 돌린다), B4c는 저장소 venv로 따로
  (`-m unittest -v ollama-proxy/eval/broadcast_chat/test_run_broadcast_rehearsal.py`, 85개 ≥ 37), 이어지는 Node 세 묶음도 따로 돌린다.
- **걸러내기 규칙을 넓히거나 예외를 둘 때**: 먼저 반례 테스트를 쓴다 — 아이리가 주어인 문장(나/나도/나두/나는/난/내가), 같은 말의
  다른 형태(과거형, "되게", 쉼표 뒤 다음 절, "얘기부터 할게"), 사별 단어라면 실제 사망 쪽(고양이한테 죽은 햄스터, 게임 이름을 딴
  반려동물 "메이플", "게임하다가 죽었어"). 조건마다 되돌려 테스트가 실패하는지(변이 검사) 확인하고, 안전 경로 정규식은 독립 리뷰를
  받는다. 오늘 첫 수정에서만 새는 곳이 13 + 11건 나왔다.
- Windows 함정: WMI `Win32_Process.Create`로 띄울 때 명령 앞에 `conhost.exe --headless`(안 붙이면 Windows Terminal 창이 떠
  포커스를 뺏는다). `swap-generator.ps1` 출력을 `Select-Object`/`Out-Null`로 파이프하지 않는다(호출 셸이 멈춘다). Git Bash heredoc은
  백슬래시를 깨뜨리므로 Windows 경로가 든 파이썬은 파일로 쓴다. 파이썬 `read_text()`+`write_bytes()`는 CRLF를 LF로 바꾼다 —
  바이트로 고친다. 프록시의 `candidate_is_unfit`는 NFKC로 정규화하는데 NFKC는 "ㅊㅋ"·"ㅂㅂ" 같은 호환 자모를 조합 자모로 바꾼다 —
  자모는 원문에서 찾는다. Ollama 모델 태그 "nul"은 Windows 예약 이름이라 사라진다(`midm-airi:v4-nul` 사용).
- 학습기: 진행 중인 run이 있으면 `train_airi_behavior_lora.py`를 고치지 않는다(재개가 소스 해시를 확인해 거부한다). 안전 일시정지는
  `run/control/pause.request.json`. 메모리 감시는 `memory_guard.ps1`.

## 6. 다음 첫 일 (우선순위)

1. live state와 기계 상태 대조(스택·학습 모두 꺼져 있어야 한다). 사용자에게 오늘 세션이 끝났다는 것과 채택 보류를 전제로 시작한다.
2. ~~끝말잇기 심판의 무효 판정 문장 반복~~ — 2026-10-01 고침(미커밋, live state `wc_referee_receipt_20261001`,
   `AIRI-BROADCAST-READINESS-HANDOFF-2026-09-29.md` §8-9). 판정마다 변형 4개, 방송 안에서 말한 문장은 다시 쓰지 않는다.
3. 새 모의 방송(두 번째 방송 — 1회 기억 이월, 나쁜 소식·게임·마무리 섞기)으로 남은 결함을 찾는다. 남은 모델 한계: 짧은 답
   ("괜찮을 거야."), 시청자의 증상·상태를 자기 것으로 말함, 나쁜 소식에 가벼운 첫 문장("망치면 재수강이 답이지"). 프록시로 막을 수
   있는 것(보류 턴 걸러내기·앞말)부터 테스트 먼저 고친다.
4. 이전 GPU PC(Codex PC)로 옮길 때: Ollama에 NUL GGUF(`midm-airi:v4-nul`)를 올려 멈춤과 TTS 포함 지연을 잰다(이 PC에서는 TTS 금지).

## 7. 사용자 결정 기록 (2026-09-30)

- 운영 채택: 「아직 보류」. 프록시 충돌: 감시 프로그램 자동 재시작(기본 꺼짐, `-SuperviseProxy`). 단어표: 그대로 사용.
- R1 기준: 「한 방송에서 같은 문장 두 번 금지」. 말투 보강 재학습 v6: 실행 → 결과 후보 아님(규칙대로 v4 유지).

## 8. 2026-10-01 이어진 작업 (Claude, 미커밋)

- 사용자 「이어서 진행」으로 §6-2를 했다: 끝말잇기 심판의 판정 문장(이어지지 않음·이미 나옴·시청자 포기·아이리 패)마다
  변형 4개를 두고, 한 방송에서 이미 말한 문장은 다시 쓰지 않는다(변형을 다 쓰면 단어 이름이 든 판정 문장만 말한다).
  ep19 같은 채팅 재실행에서 반복 문장 4+2 → 0. 상세는 `AIRI-BROADCAST-READINESS-HANDOFF-2026-09-29.md` §8-9,
  live state `wc_referee_receipt_20261001`.
- 문서 현행화: 로드맵 대시보드(09-24에 멈춰 있었음), 문서 색인, `참조/claude-guide/` 테스트 기준선·인계 경로, NEXT-SESSION.
- 기계: 평가 스택은 12:43:30에 내렸다. 포트 11434/11435/11500 비어 있음, 학습 없음.
- 커밋 대기: 코드 3·테스트 3(`word_chain_referee.py`, `live_briefing_select.py`, `ollama_proxy.py`와 각 테스트)과 문서.
  사용자 지시: 작업은 되도록 백그라운드에서, 화면에 띄울 일은 먼저 묻고, 보고서는 복사 가능한 경로만 준다.
