# AIRI Work Checkpoint — 2026-08-10

이 문서는 `fix/code-audit-remediation-2026-08-07`에서 이어진 Track M, 로컬 음성, 대화 품질, 자동 방송 작업을 다음 에이전트가 재탐색 없이 이어가기 위한 privacy-safe 체크포인트다.

## 1. 저장소와 운영 원칙

- 체크포인트 작성 전 기준 HEAD: `b234abe0fe195c19212327ffbd6bdecefb9787e1`.
- 사용자 지시에 따라 기존 dirty worktree와 로컬 memory DB는 reset/revert/checkout/delete하지 않았다.
- 앞으로 기능·검증이 논리적 분기에 도달할 때마다 현재 브랜치에 커밋하고 origin으로 push한다.
- 원본 `exaone-airi:2.4b`는 보존한다. 구조 프루닝은 LoRA/QLoRA와 검수 데이터 이후다.
- 외부 검색, cloud chat/extraction, 평가 수집은 기본 OFF다. 11436 자동 memory extractor도 frozen full fixture gate 전까지 OFF다.
- `.codex/`, ASAR, 로그, SQLite, runtime DB, live/eval raw results는 릴리스 커밋에서 제외한다.

## 2. 이번 체크포인트에 포함된 큰 구현

### Track M과 지식

- SQLite 기반 conversation journal, explicit-session adoption, bounded journal RAG, canon snapshot, extraction stage A/B, provider isolation과 extraction gate를 구현했다.
- explicit header는 authoritative하며 다른 세션과 섞지 않는다. 실사용 감사에서 3턴 explicit session에 과거 57쌍을 더해 당시 최신 60 complete turns를 한 transaction으로 이관했고, 이후 3턴이 tail을 전진시켰다.
- KURE-v1 CUDA embedder, knowledge store/ingest, 한국어 조사 정규화, title/content FTS v2, semantic fallback, answer summary와 reviewed provenance를 추가했다.
- 자동 구조화 기억 추출은 품질 gate 실패 상태를 유지하며 활성화하지 않았다.

### 캐릭터와 평가

- bounded character state와 session별 coalescing evaluator, foreground interrupt, local-only 설정을 추가했다.
- evaluation store는 명시적 consent + local bounded queue이며 기본 OFF다.
- C0/S1 fixture, baseline/conversation/proactive runner, human-review contract와 training gate/pending review workflow를 추가했다.
- pending S1 데이터는 production-approved가 아니며 QLoRA 입력으로 사용할 수 없다.

### 음성·지연·취소

- VAD PCM pre-roll을 손실 없는 WAV로 STT에 전달하고 manual MediaRecorder 경로와 분리했다.
- quiet speech recovery를 한 번으로 제한하고, 업로드 길이를 크게 벗어난 Whisper segment timestamp를 증거에서 제외한다. quiet recovery는 frame gate, logprob, no-speech, timing 검증을 모두 통과해야 한다.
- STT/LLM/TTS/playback에 opaque round correlation과 privacy-safe latency telemetry를 전파했다.
- local Ollama header acquisition과 partial raw progress에 bounded watchdog을 추가했다. terminal 이전 journal scheduling으로 downstream close 뒤에도 completed turn이 누락되지 않게 했다.
- TTS는 첫 speakable deadline, Unicode segmentation, 짧은 선행 fragment 결합, proactive attempt timeout/retry를 갖는다.
- AIRI v0.11.3 source patch에는 same-session supersede/cancel, AbortSignal 전달, server-channel single producer, proactive local broadcast, passive voice-status API, channel initialization liveness가 포함된다.

### 로컬 무포커스 API와 자동 방송

- `send-airi-local-text.mjs`는 마우스·키보드 focus를 빼앗지 않고 loopback server channel로 텍스트를 보내며 matching completion을 기다린다.
- `get-airi-local-voice-status.mjs`는 capture를 시작하지 않고 stage/VAD/mic permission의 allowlisted 상태만 조회한다.
- 자동 방송은 local-only assistant intent로 생성하며 cloud/server outbox에 보내지 않는다. UI에서 주기와 enabled 상태를 조절하고, topic board는 승인된 로컬 항목만 사용한다.
- proactive speech는 실제 WebAudio natural completion에만 content-free completion proof를 남긴다.

## 3. 2026-08-10 대화 품질·지연 실측

로컬 무포커스 API로 서로 다른 합성 일상 장면 3건을 순차 시험했다. 사용자 원문은 이 문서에 보존하지 않는다.

| 시도 | matching completion | 결과 | 판정 |
|---|---:|---|---|
| 1 | 2.465s | 대상에 대한 요청하지 않은 주의로 바뀜 | 문체 FAIL |
| 2 | 0.839s | 관찰을 일반 상태 평가로 요약 | 문체 FAIL |
| 3 | 1.427s | 원인 없는 장난 의인화 | 문체 FAIL |

- 세 시도 모두 과거 7~30초 first-content 병목보다 빨랐다. warm local generation과 header/raw watchdog 방향은 유효하다.
- 다만 `exaone-airi:2.4b`는 짧은 system contract만으로도 감탄사·상태 요약·근거 없는 의인화에 반복 수렴했다.
- grounding correction은 실행됐지만 필요한 근거 두 개 중 한 개만 반영해 후보를 폐기했다. 검사를 느슨하게 하면 감정 추정·조언·다문장 후보가 공개되므로 완화하지 않았다.
- prompt를 더 쌓는 대신 영구 prompt의 중복된 `비유/다음 장면/친구처럼` 허용 문구를 제거하고, request-local style contract 하나로 통합했다.

격리 모델 비교도 실패했다.

- `exaone-airi-runtime:2.4b`: 약 4.0s, 83자, 감정 추정과 안전 조언 추가.
- `qwen3:4b`: 약 36.5s, 내부 영어 추론 약 5.8k자를 공개. `think:false`만으로 현재 Ollama/template 경계에서 억제되지 않았다.
- 결론: 현재 runtime 모델을 바꾸지 않는다. 원본 Exaone 유지가 속도·노출 면에서 가장 낫다.

다음 품질 실험은 같은 모델이 JSON schema로 `관찰 근거 2개 + 관계 + speech`를 생성하게 하고, 검증된 speech만 기존 plain dialogue boundary로 보내는 방식이다. 고정 대사/횟수 if문은 사용하지 않으며 memory/card/character loop를 그대로 통과시킨다. 이 실험 시작 직전에 로컬 스택 전체 listener가 사라져 모델 호출은 완료하지 못했다.

### Push 이후 structured grounding 실험

로컬 스택을 안전 기본값으로 다시 기동한 뒤 원본 `exaone-airi:2.4b`에 합성 일상 장면 3건을 직접 보냈다. 이 경로는 proxy, DB, UI, TTS, journal을 사용하지 않았다.

- JSON schema의 `anchors` 두 개는 3/3 grounded했다.
- 생성 시간은 0.393~0.783초로 충분히 짧았다.
- 최종 `speech`는 1/3만 grounded했다. 나머지 두 건은 관찰되지 않은 안도감·불편함을 추가하거나 두 번째 근거를 누락했다.
- 실패한 두 건에 anchor ledger, 탈락 원인, rejected draft를 제공해 correction-only 재생성을 한 번씩 실행했지만 0/2였다. 모델은 다시 감정·가치 판단을 추가했고 한 근거를 누락했다.

결론: JSON schema는 근거 추출에는 유효하지만 현재 2.4B 모델의 대사 합성 품질을 보장하지 못한다. 이 경로를 production에 통합하거나 prompt를 더 누적하지 않는다. 검증을 느슨하게 하거나 고정 fallback 대사를 넣지 않으며, 다음 품질 분기는 legacy card 오염 경계 확인과 200건 pending S1의 독립 검수다.

### 카드 provenance와 source patch 동기화

- 현재 persisted `default` 카드는 공식 자동 생성 shape가 아니다. 여러 authored field가 채워져 있으므로 사용자 편집 카드로 취급하며 자동 초기화하거나 삭제하지 않는다.
- 정확한 v0.11.3 generated default만 locale별 전체 prompt fingerprint, ReLU/1.0.0, 모든 authored field empty, exact default widget 조건으로 마이그레이션한다. 기존에 기록된 재현 불가능한 길이/hash를 pinned `dbf8124` 원문에서 다시 계산한 값으로 교체했다.
- exact legacy ko/en migration, 한 글자 수정, authored field, widget 변경, UTF-16 FNV 경계를 포함한 card test 20개와 stage-ui typecheck가 통과했다.
- repository의 canonical AIRI source patch가 실제 temp source보다 15개 source path 뒤처져 있음을 발견했다. tracked 61개와 untracked source 16개, 총 77개 경로를 현재 source에서 다시 생성했고 `git apply --reverse --check`로 source와 exact match를 확인했다.
- core-agent, pipelines-audio, stage-ui, i18n, stage-tamagotchi, server, server-runtime, plugin-protocol 8개 package typecheck가 모두 통과했다.

### 최신 source build와 설치

- plugin-protocol, server-runtime, core-agent, pipelines-audio, i18n을 새로 build하고 Tamagotchi Electron main/preload/renderer를 fresh build했다.
- 기존 packaged runtime의 dependency/resources는 유지하고 새 `out`만 mirror한 뒤 28,085-entry `app.asar`를 생성했다. main과 renderer 진입점 및 card/voice-status/proactive/single-producer marker를 확인했다.
- 설치된 `app.asar` SHA-256은 `9AA26031877AD6B899F09CC00CCD06F869573F74F8FF1619DD580C84E531BA70`이다.
- 직전 설치본 SHA-256 `E3C73BC060DB2005014EECC9287435C47F8C32E161D1FF0F05B90C41B4129FCF`은 `.codex/artifacts`의 exact recovery backup과 일치한다.
- AIRI 앱은 사용자의 현재 창 focus를 빼앗지 않도록 자동 실행하지 않았다. persisted card/storage는 수정하지 않았다.

### 무포커스 백그라운드 실행 경계

- 공식 Tamagotchi main process에 `--background` 시작 모드를 추가했다. primary renderer와 tray/local runtime은 정상 부팅하지만 main BrowserWindow의 `ready-to-show`에서 창을 표시하지 않는다.
- 이미 실행 중인 AIRI에 `--background`가 두 번째 instance로 전달되면 기존 창을 표시하거나 focus하지 않는다. 일반 두 번째 실행은 기존 UI 복원 동작을 유지한다.
- workspace의 `start-airi-background.ps1`은 설치된 exact `AIRI.exe`와 sibling `resources/app.asar`를 검증하고, 기존 exact-path 프로세스가 있으면 중복 실행하지 않는다. 새 실행은 `--background`, `-WindowStyle Hidden`, exact working directory를 사용한다.
- 런처 성공 조건은 visible main window 없음과 passive local voice-status의 `stageMounted=true`다. 이 확인은 채팅, 모델, TTS, 마우스·키보드 입력을 전혀 발생시키지 않는다.
- background/startup 및 single-instance 집중 테스트 5개, stage-tamagotchi typecheck, workspace 런처 계약 테스트 5개, PowerShell AST parse가 통과했다.
- canonical source patch는 새 startup 경계를 포함한 82개 source path로 재생성했다. SHA-256은 `13177D2547EBDBCCC65541CEDD8F3B4DF197117DFA2212090A7C697C98C075C8`이며 pristine index 정방향과 현재 source 역방향 apply check가 모두 통과했다.
- source checkpoint push 뒤 Tamagotchi Electron main/preload/renderer build가 통과했다. 기존 packaged dependencies/resources에 fresh `out`을 mirror해 28,085-entry `app.asar`를 만들었고 main/renderer entry와 background, voice-status, proactive proof, per-event context lock, exact card fingerprint marker를 확인했다.
- 새 artifact 및 설치본 SHA-256은 `D3A623CEEDCEE3C3CFCCF508D6BD18C1C0EDD6F7FCC3CCC428109E60CF20074B`, 크기는 1,359,495,376 bytes다. 직전 설치본 `9AA26031877AD6B899F09CC00CCD06F869573F74F8FF1619DD580C84E531BA70`은 exact recovery backup으로 보존했다.
- `start-airi-background.ps1` 실기동에서 시작 전후 foreground process가 동일했고 visible AIRI window는 0개였다. local channel은 listener를 열었고 passive status는 `stageMounted=true`, voice input/provider configured, microphone permission granted, VAD active/listening, input live/enabled/unmuted를 확인했다. 캡처·transcription은 진행 중이 아니고 마지막 capture outcome도 none이었다.
- 같은 시점에 8880·8890·8892·9880·11434·11435 listener는 loopback에서 정상이고 11436은 OFF였다. STT는 large-v3-turbo/CUDA/int8_float16, TTS는 GPT-SoVITS v2ProPlus, memory/knowledge는 ready다. extraction, external search/chat approval, evaluation collection은 OFF이며 character evaluator는 local GPU/30m keep-alive로 ready다.

### 비영속 production quality probe

- 기존 `local-evaluation`은 frozen 평가 재현을 위해 personal memory/state뿐 아니라 production sampling 기본값과 grounding retry도 의도적으로 끈다. 따라서 이를 실제 대화 품질 판정에 재사용하면 안 된다.
- exact loopback 전용 `local-quality-probe` origin을 추가했다. personal memory assembly, character state/evaluator, repeat director, cloud search/chat, durable journal을 차단하지만 production local sampling, response mode, language/grounding retry는 유지한다. opaque trace만 사용하고 origin header는 upstream으로 전달하지 않는다.
- spoof 거부·상태/기억 비변경·sampling 유지·grounding retry eligibility·header stripping 집중 테스트와 proxy 전체 단위 테스트 186개가 통과했다.
- generated-default provenance를 사용한 합성 일상 장면 3건에서 journal scheduled/completed, character sessions, memory pending은 모두 불변이었다. 세 건 모두 최초 draft의 grounding 부족을 정확히 검출해 retry를 사용했지만 correction candidate는 0/3 통과였다.
- 현재 선택 로직은 correction 실패 시 grounding에 실패한 최초 완결 draft를 다시 공개한다. 실제 결과는 사건을 일반화하거나, 긍정 상황의 정서를 반대로 추정하거나, 입력에 없는 속성을 추가했다. 다음 품질 분기는 이 fail-open 동작을 제거하고 한 번의 correction call에서 검증 가능한 복수 후보를 생성·선택할 수 있는지 격리 실험한다.

### Grounding fail-closed 체크포인트

- 원본 `exaone-airi:2.4b`에 같은 세 합성 장면을 사용해 correction 1회당 JSON 후보 3개를 생성하는 격리 실험을 했다. schema parse는 3/3 성공했지만 9개 후보 중 기존 production verifier를 통과할 가능성이 있는 것은 2개뿐이었고, 그 후보에도 원문에 없는 동작이 섞였다. 더 엄격하게 원문 내용어 추가를 금지한 3회도 새 동사·속성·불완전 문장을 안정적으로 제거하지 못했다.
- 따라서 multi-candidate 생성을 production에 넣지 않았다. 모델 후보 수를 늘려 품질을 확률적으로 고르거나 verifier를 느슨하게 하는 방식은 채택하지 않는다.
- 실제 결함인 fail-open은 제거했다. 최초 draft가 grounding gate를 실패한 뒤 correction도 언어·내용 검증, timeout, UTF-8/NDJSON 구조 중 하나라도 실패하면 최초 draft를 복구하지 않는다. substantive SSE를 비운 채 정상 terminal만 보내며 journal, character state, evaluator에 아무 대사도 저장하지 않는다.
- correction 전용 문체 계약은 일반 잡담 계약과 분리했다. 서로 다른 사실 둘과 행동·결과 하나를 보존하고, 조사·어미 외에 사용자 원문에 없는 내용 명사·동사·형용사 및 새 감정·원인·속성·비유·조언·예측·질문을 추가하지 못하도록 제한했다.
- focused grounding 회귀 11개와 `test_ollama_proxy.py` 전체 187개가 통과했다. 최신 proxy를 재기동한 뒤 비영속 production probe 3건은 모두 correction 실패를 content-free로 종료했고, telemetry의 `grounding_quality_rejected=1`을 확인했다. journal scheduled/completed=0, character sessions=0, memory pending=986은 불변이며 evaluation/extraction/external search/chat은 계속 OFF다.
- 이 체크포인트는 잘못된 말을 TTS·로그·기억에 남기는 문제를 막지만, 3건 모두 무응답이므로 대화 품질의 최종 해결은 아니다. 다음 분기는 고정 fallback이나 추가 prompt 누적이 아니라, 검수된 S1 데이터와 더 신뢰할 수 있는 생성/검증 경계를 준비하는 것이다.

### S1 pending review 무결성

- 현재 pending S1은 정확히 200건, split 160/20/20, category 34/34/33/33/33/33이며 strict offline gate를 통과한다. 모든 레코드는 `pending`, reviewer/timestamp empty, `training_eligible=false`이고 실제 decision sidecar는 없다.
- 기존 reviewer CLI는 화면에 필요한 최소 필드만 읽어 strict pending gate를 운영자가 별도로 실행해야 했다. 이제 status·display·write 전에 동일한 `validate_pending_dataset`을 강제하며, 실패하면 sidecar를 열거나 쓰지 않는다.
- 기존 decision은 레코드 ID에만 묶여 있었다. `record_sha256` 필드를 추가해 prompt, answer, category, split, partition, review, provenance, eligibility를 포함한 전체 canonical pending record에 결정을 결합했다. 같은 ID의 내용이 한 글자라도 바뀌면 status, validation, replacement가 모두 fail-closed한다.
- reviewer identity는 추측하지 않고 입력받으며 pending 원본은 immutable, decision sidecar는 atomic write를 유지한다. 이 변경은 레코드를 승인하거나 production dataset으로 컴파일하지 않는다.
- reviewer/validator unittest 11개와 production verifier pytest 5개, py_compile, diff check가 통과했다. 실제 큐 status는 decision 0, remaining 200이고 status 확인으로 sidecar가 생성되지 않았다.
- production QLoRA gate에 필요한 canonical C0/S1 JSONL fixture, reviewed dataset compiler, independent reviewer provenance manifest, immutable gate report와 외부 custody/signature는 아직 없다. eval JSON을 production fixture라고 추측해 변환하거나 학습을 시작하지 않는다.

## 4. 최신 집중 검증

- `test_ollama_proxy -k grounding`: 11 passed.
- 최신 `test_ollama_proxy.py` 전체: 187 passed.
- S1 pending reviewer/validator unittest: 11 passed.
- production dataset verifier pytest: 5 passed.
- prompt/system contract: 25 passed.
- 추가 live-failure ledger/advice regression: 1 passed.
- STT quiet/timestamp validation: 42 passed.
- channel initialization store: 18 passed.
- core proactive runtime: 23 passed, 이후 provider history cap 포함 core runtime 25 passed.
- stage-ui와 stage-tamagotchi typecheck는 source checkpoint에서 통과했다.
- passive voice-status source/CLI tests 각각 4/4, 3/3 passed.
- Playwright browser contract는 Chromium executable이 없어 실행하지 못했다. 이를 설치한 것으로 간주하지 않는다.
- `ollama-proxy` 전체 회귀 436 passed. 이 과정에서 같은 `created_at`을 가진 평가 항목의 export 순서가 UUID에 따라 달라지는 문제를 발견해 `rowid` 삽입 순서로 고쳤다.
- eval runner 23 passed, latency monitor 16 passed, 공용 latency trace 3 passed, local no-focus API 8 passed.
- pending training gate 13 passed. 시드 큐는 200건 계약이며 여전히 전부 review pending/training ineligible이다.
- 수정·신규 PowerShell 7개 파일은 AST parse를 통과했다.
- AIRI source 8개 package typecheck와 exact legacy-card migration test 20개가 통과했다.

체크포인트 전체 회귀와 staged privacy/secret scan을 완료했으며, ASAR·로그·SQLite·runtime/eval 결과와 실제 발화 원문은 커밋에서 제외했다.

## 5. 현재 런타임 상태

체크포인트 작성 시 8880, 8890, 8892, 9880, 11434, 11435, 11436 listener가 모두 없었다. 이는 테스트 중 코드가 health fail을 반환한 상태가 아니라 프로세스가 외부에서 전체 종료된 상태다. 다음 실사용 전에 `start-airi-local-stack.ps1`로 기동하고 다음을 재확인한다.

- 8890: `large-v3-turbo`, CUDA, `int8_float16`.
- 9880/8880: GPT-SoVITS v2ProPlus backend/proxy.
- 11434/11435: local Ollama와 AIRI proxy, `num_gpu=999`, `keep_alive=30m`.
- 11436: listener 없음이 정상.
- memory/knowledge ready, extraction/search/cloud/evaluation OFF.

Push 이후 재기동 검사에서는 8880·8890·8892·9880·11434·11435가 loopback에서 정상이고 11436은 계속 OFF였다. STT는 `large-v3-turbo`/CUDA/`int8_float16`, memory·knowledge는 ready, Ollama는 `num_gpu=999`/`keep_alive=30m`, character evaluator는 같은 GPU/keep-alive 설정이다. extraction, external search/chat, evaluation collection은 OFF다.

## 6. 다음 작업 순서

1. 현재 default card와 request header 경로를 감사해 과거 ACT·선물 예시가 정확한 프로젝트 생성 템플릿일 때만 안전하게 마이그레이션한다. 사용자 작성 필드는 추측으로 지우지 않는다.
2. 200건 pending S1을 독립 검수하고, 승인 sidecar·reviewer provenance가 갖춰지기 전에는 production dataset이나 QLoRA 입력으로 승격하지 않는다.
3. 관련 unit test 후 무포커스 API로 최소 3개 서로 다른 일상 장면을 확인한다. 합격 기준은 첫 content 8초 이내, 한국어 한 문장, 상담/조언/복창/상태 요약/근거 없는 비유 없음, wire와 journal exact match다.
4. 사용자의 다음 자연 음성에서 quiet recovery와 first-word STT를 측정한다. 전용 발화를 반복 요구하지 않는다.
5. 논리 체크포인트 마지막에 전체 회귀를 한 번 수행하고 다음 commit/push를 만든다.

## 7. 커밋 경계와 개인정보

- raw session/request/round ID, 로컬 DB, 실제 사용자 발화 원문, local absolute path, auth token을 문서나 결과에 넣지 않는다.
- eval fixture와 pending training record는 synthetic이며 승인 여부를 명시한다. live result 디렉터리는 기본 ignore한다.
- GitHub push 전 staged diff와 secret scan을 다시 확인한다.
