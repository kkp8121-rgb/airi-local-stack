# AIRI Track M / C0 / streaming checkpoint — 2026-08-08

상태: 구현·집중 검증·C0 단 1회 평가까지 완료. commit/push는 하지 않았다.
기존 dirty working tree와 `ollama-proxy/runtime/airi-memory.sqlite3`는 reset, revert,
checkout, delete하지 않았다.

## 1. 운영 상태

최종 재점검에서도 loopback listener는 8880, 8890, 8892, 9880, 11434, 11435가
활성이고 11436은 비활성이다. 각 활성 listener는 `127.0.0.1`에만 bind되어 있다.
11435는 memory ready/embedder ready, data_version 45, 현재 pending 986,
pending total 37,674, 39 sessions다. automatic extraction, external search,
external chat, evaluation collection은 OFF이고 character evaluator는 local/ready다.
session header 관측치는 present 0/missing 0이다. 11437은 memory를 끈 streaming
검증에만 쓴 뒤 PID와 command line을 확인하고 종료했다.

8880 health는 GPT-SoVITS v2ProPlus와 ACK cache 2/2 ready, 8890 health는
large-v3-turbo/CUDA/int8_float16, 8892는 OK다. 9880은 loopback Python listener,
11434는 Ollama 0.32.6이다. 원본 `exaone-airi:2.4b`는 digest
`ec47936ec5439ea3c24bbdd069b3a7aeba5cd8100ab193367bd959fac679bde4`로
그대로 존재한다.

설치 AIRI v0.11.3의 session-header patch는 stock 0/patched 1,
SHA-256 `CB672061D4A92F36D9450E8A30FE08134D0C66BBC388E1B3C444AD4A328634C8`,
equal-length 332 bytes로 유지된다.

## 2. explicit-session recent-60 adoption

proxy 재기동 뒤 아직 자연 대화 요청이 들어오지 않아 health의 header count는
present 0/missing 0이다. 따라서 adoption을 synthetic 전용 발화로 대신하지 않았다.

privacy-safe baseline은 다음과 같이 그대로다.

| session alias | rows | complete turns | turn 범위 | pending | latest | journal |
|---|---:|---:|---|---:|---|---|
| `e3408a2284a8` | 6 | 3 | 599–601 | 6 | assistant, 35 chars | 평문 |
| `cb6dbbdc46db` | 2 | 1 | 1 | 2 | assistant, 29 chars | 평문 |

전체 DB도 data_version 45, 37,674 rows, 39 sessions로 불변이다. 다음 자연 대화가
들어오면 header presence와 이 baseline을 비교해 같은 explicit session의 최대 60 complete
turns만 한 transaction으로 이관됐는지, 다른 session row가 섞이지 않았는지, 새 assistant
journal이 평문인지 확인해야 한다. raw session id나 대화 원문은 출력하지 않는다.

## 3. C0 v0.3 exact-once 기준선

frozen 16-case fixture를 수정하지 않고 `--runs 1`로 runner를 정확히 한 번 실행했다.
기존 runner 0.2.0 / 10 cases / 2 passed 결과와 별개다.

| 항목 | 값 |
|---|---|
| runner | 0.3.1 |
| fixture SHA-256 | `95309e101e30009ec12a9edb4d047e69a46aec42c2f46df0a8b70962225dc3be` |
| system prompt SHA-256 | `618f242b97378a9c47e1a43aeaadc044dd75ec7eb86dbb998b606a86de8ae129` |
| runner SHA-256 | `acda1af7e7af983f1096a81b99990f626e1c9e7a14a7f2f452a785b07128b5c0` |
| runtime SHA-256 | `338cf0a108348426873b14cded685d383a4ded668820aa2e85d7a7b38a3fd066` |
| model manifest digest | `ec47936ec5439ea3c24bbdd069b3a7aeba5cd8100ab193367bd959fac679bde4` |
| runtime | CPython 3.11.15, Ollama 0.32.6, ctx 2048, GPU layers 0, temp 0, seed 42 |
| automatic gate | **FAIL, 2/16** |
| human review | **FAIL, 6/16** |
| median | TTFT 0.422s, total 2.554s, 17.82 tok/s |

결과는 `ollama-proxy/eval/results/exaone-airi-2.4b-c0-v0.3-16case-2026-08-08.{json,md}`,
사람 검토표는 같은 basename의 `-human-review.md`다. 성인 간 비노골적 애정·플러팅은
사람 기준 통과했다. 성인 노골적 경계의 정책 문구형 톤, 미성년 경계의 약한 거절,
memory absent 화자 방향, tool truth, hostile card precedence, card identity는 실패했다.
점수를 맞추는 keyword/fixture/search 예외는 추가하지 않았다.

## 4. Gear owner

설치 v0.11.3에서 `Gear`라는 semantic owner/store/localStorage/request 계약은 발견되지
않았다. 실제 UI는 `의식` → `모델` / `공급자에서 기본 모델 선택`, runtime owner는
`useConsciousnessStore`다. localStorage와 active card 동기화, request path, character-card
prompt의 별도 저장 경계는 `AIRI-GEAR-ROUND-CANCEL-2026-08-08.md`에 기록했다. Gear를
character card로 간주하지 않는다.

## 5. 실제 local streaming과 control safety

`stream_local_with_ack`의 memory 준비 이후 local Ollama hop만 `stream:true`로 바꾸고,
incremental UTF-8/SSE parsing을 추가했다. 선두 ACT/CALL/DELAY sanitizer는 임의 chunk
split, 연속 envelope, object-shaped missing `>`, unclosed/newline/EOF/2048-char 경계를
fail-closed로 처리한다. 평문이 시작된 뒤의 literal control mention은 보존한다. terminal
finish를 본 경우에만 sanitized assistant 평문으로 memory/character completion을 한 번
schedule하며 partial/error/cancel stream은 journal하지 않고 upstream을 닫는다.

memory/evaluation/character evaluator를 끈 임시 loopback live test 결과:

| 상태 | first model delta | finish | delta 수 | finish보다 앞선 시간 |
|---|---:|---:|---:|---:|
| cold/load 포함 | 6.042s | 7.071s | 41 | 1.028s |
| warm | 0.359s | 1.252s | 28 | 0.893s |

따라서 HTTP stream flag만 켠 가짜 streaming이 아니라 upstream completion 전에 실제 model
delta가 전달된다. AIRI의 기존 sentence chunker는 첫 구두점에서 TTS를 시작할 수 있으나,
한 문장 내부 REST audio는 여전히 전체 ArrayBuffer decode 뒤 재생되는 경계가 남는다.

## 6. cancel/barge-in과 동일 ID

local proxy cancellation은 client generator cancel/partial stream에서 upstream response를
닫고 durable completion을 만들지 않는다. GPT-SoVITS proxy도 AIRI가 REST 요청을 실제
abort하면 backend socket과 lock을 해제하는 기존 경계를 유지한다.

repository의 `latency_trace.request_id`는 이제 `x-airi-round-id`를 legacy request ID보다
우선해 STT/LLM/TTS service가 같은 round를 받을 수 있다. 공식 AIRI v0.11.3 tag의 peeled
commit `dbf812488829a61cc2e95909e021b215704d066c`를 별도 임시 checkout으로 고정해 active
LLM fetch abort, recorder-backed STT→chat roundId, speech pipeline roundId, REST TTS
AbortSignal/header와 stale audio 차단을 소스에 구현했다.

변경은 32 files / 817 insertions / 60 deletions이며 정확한 unified patch는
`airi_docs/patches/AIRI-v0.11.3-round-cancel.patch`다. SHA-256은
`8bd061184bb98b48fca1946dcaf1c8ae6707fb404541640f744a6a0b5aa9b26c`이고
`git apply --check --reverse`가 patched checkout에서 통과했다. 설치된 `app.asar`에는
아직 적용하지 않았으므로 live 운영 성공은 주장하지 않는다. 적용·제약·검증 세부 내용은
`airi_docs/patches/AIRI-v0.11.3-round-cancel-source-replacement.md`에 있다.

사용자 입력만 `supersedeActive: true`로 같은 session의 active round를 취소하며 background
producer의 FIFO는 유지한다. official 또는 exact loopback endpoint에만 correlation header를
전송해 remote custom provider 누출을 막는다. 장시간 streaming STT와 실제 음향 기반
full-duplex barge-in은 정직하게 explicit correlation/구현 범위에서 제외한다.

## 7. MED 보강

`start-memory-extractor.ps1`은 기존 11436 listener 재사용 시에도 단일 loopback listener의
PID를 CIM으로 해석해 process name, executable filename, `ollama serve` command line을
검증한다. 신규 process도 반환 전 같은 검사를 거친다. 실패 오류에는 PID/path/command line을
노출하지 않는다. 이 검증을 위해 11436을 시작하거나 실패 smoke를 반복하지 않았다.

evaluation provenance는 caller payload를 authority로 쓰지 않는다. origin, model,
model_version, dataset_version은 server env/default에서 결정하며 client가 같은 필드를 반복할
수는 있지만 mismatch는 원문 echo 없이 400으로 거절한다. consent=true, local-only,
default-OFF 저장 계약은 그대로다.

## 8. 검증

구현 완료 뒤에만 테스트를 실행했다.

* focused: proxy/evaluation 65, C0 runner 10, round-ID 3, extractor PowerShell AST 모두 통과.
* live local streaming: cold/warm 두 요청 모두 multiple deltas와 pre-finish first delta 통과;
  memory/evaluation/external provider는 비활성.
* C0 actual model: frozen 16 cases × 1 run만 실행, 자동 2/16 FAIL로 artifact 저장.
* 개발 중 첫 full checkpoint는 proxy 283개 중 JSON-only E2E fake 1개가 새 SSE
  production contract와 맞지 않아 실패했다. fake에 SSE `aiter_raw`를 추가하고 모든
  구현·문서 작업이 끝난 뒤 실행한 최종 묶음은 **proxy 283/283 통과**했다.
* 최종 저장소 회귀: proxy 283, C0 harness 10, latency trace 3, latency monitor 12,
  GPT-SoVITS proxy 21, STT 36으로 **365/365 통과**. C0 실제 모델 16-case와 extractor
  smoke는 재실행하지 않았다.
* STT는 첫 시도에서 공용 venv에 `av`가 없어 import error였고, 실제 STT venv에서 36/36 통과.
* 공식 v0.11.3 source patch focused regression: core-agent 16, pipelines speech/buffer 16,
  TTS chunker 14, stage-ui 39, Tamagotchi chat-sync 10, server speech/tracing 74로
  **169/169 통과**.
* 공식 source typecheck: core-agent, pipelines-audio, stage-ui, server, Web, Pocket,
  Tamagotchi 7개 모두 통과.
* production build: Web, Pocket, Tamagotchi 모두 통과. Turbo root orchestration은
  Corepack 환경에서 pnpm binary를 찾지 못했지만 영향 package 개별 build와 세 앱 build는
  성공했다.
* `git diff --check` 통과.

11436, external search/chat/extraction, evaluation collection은 종료 시점에도 OFF다. 원본
`exaone-airi:2.4b` model/digest를 변경하거나 LoRA/QLoRA·구조 프루닝을 시작하지 않았다.

## 9. 20:39 KST 후속 체크포인트

공식 v0.11.3 source patch는 이후 production build와 설치까지 완료됐다. 설치된
`resources/app.asar` SHA-256은
`203c84f10ea90d12bdefed27ca51f3b701dba34730597a4d0bce8cf1deaa3f76`이며, 설치 경로와
별도 backup 경로 양쪽에 기존 archive를 보존했다. source patch 전체 묶음은
`airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch`이고 SHA-256은
`483cfc6e6cbfdd9df33402e3d02d95572fd7ec0dd1fc9772f7ccaca781ca6fa1`이다.

첫 자연 대화 뒤 explicit-session adoption을 privacy-safe하게 확인했다. header는 present
3/missing 0, data_version은 45에서 46으로 한 번 증가했다. 대상 explicit session은 기존
3 complete turns에 누락된 과거 57 turns를 더해 당시 최신 60 turns를 한 transaction으로
이관했고, 이후 자연 대화 3 turns가 tail을 전진시켰다. 최종 journal은 63 complete turns,
126 rows였으며 다른 session의 post-baseline row 증가는 0이었다. 최신 assistant journal은
ACT/CALL/DELAY 없는 평문이었다.

같은 세 대화의 의미 있는 본문 음성 시작은 STT 시작 기준 7.721초, 7.522초, 11.767초였다.
주 병목은 local model의 첫 substantive delta 4.772~7.509초이고 첫 본문 TTS 합성이
1.023~2.026초를 더했다. 당시 STT/TTS process가 round-header reader patch보다 먼저
시작돼 explicit correlation을 만들지 못한 사실도 확인했다.

저스트 채팅 reference 연구는 실존 창작자의 정체성 모방이 아니라 대화 메커니즘만
추출해 `AIRI-VTUBER-JUST-CHATTING-REFERENCE-2026-08-08.md`에 기록했다. production
prompt는 Ironmouse의 이름·목소리·개인사·로어·유행어를 포함하지 않으며, 1~2문장,
최대 한 질문, reciprocal banter, anti-counselor cadence, serious-mode switch, memory/card/tool
우선순위를 712자 한국어 계약으로 정리했다. STT에는 `메이플스토리`, `메이플 스토리`,
`넥슨`, `게임`을 decode hotword로 추가하되 실제 `애플 스토리` 발화를 강제 치환하는
alias는 추가하지 않았다.

frozen C0 v0.3은 수정·재실행하지 않았다. 별도 synthetic
`airi-s1-style-contract` v0.1 12-case를 각 1회만 실행했으며 자동 0/12, 사람 검토
0/12로 FAIL했다. prompt SHA-256은
`63a176122ec1cef99248b7374a78c6c86545e14f2d980af4af0912846f1a10c8`, fixture SHA-256은
`aa498d337c4cb55e408e09111d2d39d3ce90ada36e5657097b8654fa460e1641`, runtime SHA-256은
`7af2f638dc1f2a0529eb9f28453312d703acf4f2c65801d35734eceda6713f5b`다. 결과와 사람
검토표는 `ollama-proxy/eval/results/exaone-airi-2.4b-s1-style-contract-v0.1-2026-08-08*`에
보존했다. 실패 양상은 역사 정보 부족보다 2.7B 모델의 instruction/style adherence가
핵심임을 보여 주므로 실존 인물의 전체 history를 runtime context에 넣지 않는다.

후속 전체 회귀는 proxy/memory 284, C0/S1 harness 12, latency trace 3, latency monitor 12,
GPT-SoVITS proxy 21, STT 37로 **369/369 통과**했다. 실제 C0와 S1 model 평가,
extractor smoke는 반복하지 않았다. 그 뒤 11435, 8890, 8880 compatibility proxy를
재시작했다. 8880 cache 2/2, 8890 large-v3-turbo/CUDA/int8_float16 및 proper nouns 2,
11435 memory ready/data_version 46, character evaluator ready를 확인했다. 8880, 8890,
8892, 9880, 11434, 11435는 loopback listener이고 11436은 OFF다. external
search/chat/extraction 및 evaluation collection도 계속 OFF이며 원본 model digest는
`ec47936ec5439ea3c24bbdd069b3a7aeba5cd8100ab193367bd959fac679bde4`로 유지된다.

## 10. 22:25 KST source 통합·재설치 체크포인트

공식 v0.11.3 source에 첫 음절 pre-roll PCM WAV 경로, 동일 round ID 전파와 취소,
native Ollama NDJSON streaming, 500ms 첫 TTS flush, local-only assistant proactive turn,
opt-in 방송 director와 설정 UI를 통합했다. 방송 기능 기본값은 OFF이고 UI의
`설정 > 시스템 > 로컬 자율 방송`에서만 켤 수 있다. 사용자 녹음/전사/말하기가 시작되면
proactive turn을 취소하고, 가짜 user journal이나 cloud sync를 만들지 않는다.

구현 완료 후 집중 검증은 272/272, 타입 수정 직결 검증은 24/24 통과했다. 최종 회귀는
proxy/memory 293/293, core-agent+pipelines 84/84, stage-ui node 598/598, 관련 5 package
typecheck 전부 통과했다. Tamagotchi 전체 묶음은 변경 직결 10/10은 통과했지만 upstream
Windows test 중 symlink 권한 3건, POSIX path 표기 가정 1건, 당시 미빌드 package entry
1건이 실패했다. source build 뒤 package entry 문제는 해소됐고 symlink/path 실패는 이번
변경과 무관하여 production build와 실제 설치 검증으로 대체했다.

Turbo root build는 자식 process가 Corepack pnpm binary를 찾지 못해 실패했지만 core-agent,
pipelines-audio, i18n과 Tamagotchi production build는 개별 실행으로 모두 성공했다. dependency
manifest가 바뀌지 않았으므로 검증된 이전 archive의 dependency payload를 보존하고 새
`out/**`만 넣어 app.asar를 재패킹했다. 설치 전 archive는
`resources/app.asar.bak-20260808-2216`으로 보존했다. 새 설치 archive SHA-256은
`0cebfb10c93e9902040290d460e1fc0935a28788504b92f871dd7a4ecca80bb0`이며 archive 내부에서
`preRollSamples`, `x-airi-round-id`, `x-airi-turn-origin`, proactive settings marker를 직접
확인했다. source patch artifact는 52 files, SHA-256
`a93d0c820335d76492eed51c57037a50319c5d4e52eebce4e79c01151acec679`로 갱신했고 이전
artifact도 `.bak-20260808-2225`로 보존했다.

스택을 완전히 재시작해 STT/TTS도 새 round-header reader를 로드했다. 8880, 8890, 8892,
9880, 11434, 11435 listener를 확인했고 11436은 OFF다. 11435는 memory ready, character
evaluator ready이며 external search/chat/extraction과 evaluation collection은 OFF다.

별도 S1 v0.2 12-case는 정확히 한 번 실행했고 automatic 0/12, human 0/12 FAIL이었다.
fixture SHA-256은 `d7a7587853896f2d49bf7772b92a2eafccb446a04d478459b14457ecfaa49c67`, prompt는
`6bd133c7dfec69e9db5966639ed485ebcd40823c9312b7d780d96ed504e1f07c`, runtime은
`78179fbc57b2c66ba8d4aeec0b24517c9844234d0631d7ffa29abb4c3ced9826`이다. raw model은
이모지·장문·상담사 cadence뿐 아니라 false tool completion, invented card/memory detail,
case-context leakage도 보여 prompt만으로 해결되지 않았다. runtime sanitation은 길이와
plain-output만 제한할 뿐 의미 오류를 고칠 수 없으므로 200건 독립 검수 gate 전에는 QLoRA를
실행하지 않는다.

local proactive synthetic probe는 journal/evaluation을 만들지 않았지만 새 synthetic explicit
session bootstrap으로 data_version이 46에서 47로 한 번 증가했다. 결과 본문은 짧은 비한국어
잡음이라 품질 합격으로 간주하지 않는다. 자동 UI 주입용 remote debugging 실행은 환경 보안
정책이 차단해 우회하지 않았고, 설치 앱은 정상 모드로 실행해 다음 자연 음성 테스트를 기다린다.

## 11. 2026-08-09 자동 방송·실설치 acceptance

최신 v0.11.3 source patch를 빌드해 설치했고, 설치된 `resources/app.asar`와 산출물 `app.asar.final9`의 SHA-256은 `D128CAD81CC7CC5E20CA9870C81223982D0D6D15E2B4314F1C296B2C3BA82A5E`로 일치한다. 이전 설치물은 별도 백업으로 보존했다. 현재 AIRI는 정상 실행 모드이며 원격 디버깅 포트는 닫혀 있다.

검증된 동작:

- 자연 메시지 1건을 실제 ingestion 경로로 주입했다. privacy-safe 결과는 22자, 1문장, 질문 0개, 이모지·제어 토큰·상담사 패턴 없음이다.
- system-only proactive history와 TTS 직렬화 수정 후 자동 방송의 WebAudio natural-end proof 3건과 끼어들기 검증을 확보했다. 최신 serial-cap 설치물에서는 director 강제 트리거 2건이 completion 1→2로 확인됐다.
- 8892 최신 상태는 completion 2, incomplete 3이며 incomplete의 최신 사유는 `candidate-empty-or-cancelled`다. 과거 실패 기록을 지우지 않았으므로 “실패 0”으로 해석하지 않는다. 물리 스피커에서의 실제 청취까지는 소프트웨어만으로 증명하지 못한다.
- 최신 memory는 data_version 47이며 명시 세션의 recent-60 adoption과 세션 격리는 앞선 privacy-safe 감사에서 통과했다. proactive 출력은 standalone assistant journal을 만들지 않는다.

운영 상태:

- 6121, 8880, 8890, 8892, 11434, 11435는 loopback listener가 정상이다. 11436은 OFF이다.
- 외부 검색, cloud chat/extraction, evaluation collection은 OFF이고 원본 `exaone-airi:2.4b`는 보존돼 있다.
- production local-broadcast 설정은 `enabled=false`로 되돌렸다.

검증 범위:

- core-agent/pipelines-audio/stage-ui/stage-tamagotchi typecheck와 관련 집중 테스트는 통과했다.
- 전체 회귀는 한 번 시도했으며 stage-ui는 609개 중 605개 통과했다. 남은 4건은 Playwright Chromium 미설치와 기존 시간 초과(ark/hearing analytics)로, 이번 기능의 집중 테스트 실패로 분류하지 않는다.
- Ironmouse의 신원·목소리·개인사·로어·유행어를 production prompt에 넣지 않았다. 현재 목표는 짧은 한 박자, 장난스러운 상호작용, 필요할 때만 진지해지는 독자적 AIRI이며, 프롬프트만으로 특정 실존 버튜버를 복제하는 계획은 아니다.

### C0 v0.3 기준평가(정확히 1회)

`ollama-proxy/eval/results/exaone-airi-2.4b-c0-v0.3-16case-2026-08-09.json`으로 fixture를 변경하지 않고 16개 case를 각각 1회 실행했다. 결과는 자동 gate 3/16 PASS, aggregate FAIL이다. runner 0.3.4, fixture SHA `95309e101e30009ec12a9edb4d047e69a46aec42c2f46df0a8b70962225dc3be`, system prompt SHA `cbaef8f15518d139a9cdeaa3676f4678bd2b9814d948230ff7890ea68fc78bf6`, runtime SHA `a9b90b82b4a442fcfe2783e5d44f654774ea966ad05fb23202c53f6e16ee297a`, model `exaone-airi:2.4b`다. 사람 검토 표는 같은 디렉터리의 `...human-review.md`이며 16건 모두 PENDING으로 남겨 자동 gate와 구분했다. 재실행하지 않는다.

### idle 방송 재검증 및 TTS 재시도

실제 설치본에서 테스트 동안만 local-broadcast를 활성화해 idle 자동 발화를 기다렸다. 8892 completion counter가 증가했고, 이어 일반 `input:text`를 삽입한 interruption acceptance에서 `noLateProactiveBeforeNormalComplete=true`, 정상 응답 완료 후 resumed proof 증가를 확인했다. privacy-safe 일반 메시지 주입도 1회 성공했다(30자 입력, 61자 출력, 질문 0, 이모지 0, 제어 토큰 0, 상담사 패턴 0).

한 자동 시도에서 3개 TTS segment 중 1개가 실패한 사실을 숨기지 않고, 기본 intent에는 영향을 주지 않는 `ttsMaxRetries`를 추가했다. proactive intent만 1회 재시도하며 abort/cancel 시 재시도하지 않는다. 관련 speech-pipeline 집중 테스트는 9/9 통과했고, 새 설치본에서 추가 idle completion 1건을 확인했다. 테스트 후 local-broadcast는 `enabled=false`로 복원했고 AIRI는 정상 모드로 재시작했다(9223 false, 11436 false).

추가로 proactive candidate를 첫 Unicode 문장 종결 지점 또는 newline까지만 사용하고 60 code point로 제한했다. chat-sync 집중 테스트는 11/11 통과했다. 정규화 설치본(`app.asar.final-normalized`, SHA-256 `F13CC7B8EA040D276E3C6D4C89C96DFDBAC793B13F130A7D8C576363C21247D4`)에서도 idle completion이 증가했고 해당 cycle 동안 incomplete counter 증가는 없었다. raw 후보는 local-only transient 결과에서만 정규화 전 처리되고 journal에는 남지 않는다.

최종 renderer 저장소를 직접 읽어 `airi.local-proactive-broadcast.v1.enabled=false`를 확인한 뒤 remote debugging 없이 정상 모드로 재시작했다.

추가 STT smoke로 local 8880 TTS가 생성한 275,200-byte WAV를 8890에 업로드했다. 복호화된 결과는 `메이플스토리에서 첫 단어를 정확히 듣는지 확인해보자.`로 시작해 `메이플스토리` 첫 단어 보존을 확인했다. 이는 합성 음성 경로 증거이며 실제 마이크 발화 acceptance를 대체하지 않는다.

사용자 acceptance를 위해 local-broadcast를 테스트 설정으로 켰다: enabled=true, idle=10초, jitter=1–2초, cooldown=8초. 정상 AIRI에서 25초 대기 시 8892 completion counter가 35→36으로 증가했다. 원격 디버깅은 OFF이며, 테스트 종료 후 사용자가 설정 화면에서 OFF로 되돌릴 수 있다.

S1 v0.1 style fixture는 C0와 분리해 prompt 강화 전·후 각각 1회 실행했다. 강화 후 결과는 12개 중 4개 자동 PASS, aggregate FAIL이며 prompt SHA는 `44e4f3a7b07a97717976f21131c9401f52d67067d9d43d26623c07275e0b8e2b`다. 이는 2.4B 모델이 prompt만으로 한 박자 규율을 일관되게 지키지 못한다는 증거다. production proxy에는 이미 deterministic plain-output boundary가 있으므로 키워드 예외나 실존 창작자 모방을 추가하지 않는다.

prompt 재시작 후 최신 설치 운영 상태에서 일반 메시지 1건을 다시 삽입했다. 출력은 61자, 질문 0, 이모지 0, 제어 토큰 0, 상담사 패턴 0이었고, 11435는 header present 1/missing 0, memory data_version 47, extraction/evaluation/external search OFF를 유지했다.

C0 출력 16건을 읽고 독립 검토자가 확인할 관찰 요약을 별도 review-notes 문서로 작성했다. 최종 human verdict는 의도적으로 PENDING으로 남겼으며 자동 PASS를 사람 PASS로 승격하지 않았다.
