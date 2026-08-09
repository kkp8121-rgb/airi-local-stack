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

## 4. 최신 집중 검증

- `test_ollama_proxy -k grounding`: 9 passed.
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
