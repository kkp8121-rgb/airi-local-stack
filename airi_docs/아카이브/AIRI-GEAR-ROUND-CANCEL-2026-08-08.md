# AIRI v0.11.3 Gear owner / round cancellation 결과 — 2026-08-08

상태: Gear owner 조사를 완료했고, 공식 v0.11.3 고정 소스에 round/STT/LLM/TTS
상관관계와 취소 변경을 구현·검증해 unified patch로 보존했다. 설치된 Electron
`app.asar`와 현재 실행 중인 AIRI에는 이 신규 patch를 적용하지 않았다.

## 1. Gear owner 결론

AIRI v0.11.3에는 `Gear`라는 semantic UI·상태 계약이 없다. 설치 `app.asar`의
renderer JS/HTML/JSON/CSS와 공식 v0.11.3 소스에서 exact `gear` owner, Pinia store,
localStorage key, 설정 label, request contract를 찾지 못했다. 부분 문자열 검색 결과는
라이브러리/WASM 노이즈뿐이다. 따라서 Gear를 character card라고 간주하거나 임의의 Gear
저장소를 만드는 근거가 없다.

사용자가 실제로 보는 LLM 설정은 **`의식` → `모델`**이며 선택 문구는
**`공급자에서 기본 모델 선택`**이다.

| 실제 owner | 책임 |
|---|---|
| `useConsciousnessStore` | 활성 LLM provider/model 선택 |
| `useProvidersStore` | provider instance와 자격 증명/설정 |
| `useAiriCardStore` | active card와 모듈 설정 snapshot 동기화 |
| chat orchestrator/session store | 대화, message round, transport 실행 |

consciousness 선택 localStorage key는 다음과 같다.

- `settings/consciousness/active-provider`
- `settings/consciousness/active-model`
- `settings/consciousness/active-custom-model`

선택 변경 watch는
`airiCardStore.updateActiveCardConsciousness({ provider, model })`로 active card의
`extensions.airi.modules.consciousness`에도 값을 복사한다. 카드 전환 watch는 그 값을
consciousness store로 되읽는다. 이는 active profile 설정 동기화이며
`Gear = character card`라는 뜻은 아니다.

실제 대화 request path는 다음과 같다.

`executeIngest → activeProvider/activeModel → providersStore.getProviderInstance →
chatOrchestrator.ingest → streamWithStageAdapters → llmStore.stream`

character card prompt는 별도로 초기 system session message에 반영된다. card 내용,
memory 내용, 반복 횟수로 provider나 대사를 선택하는 로직은 추가하지 않았다.

## 2. source patch

- 기준 tag/commit: `v0.11.3` /
  `dbf812488829a61cc2e95909e021b215704d066c`
- patch: `airi_docs/patches/AIRI-v0.11.3-round-cancel.patch`
- SHA-256: `8bd061184bb98b48fca1946dcaf1c8ae6707fb404541640f744a6a0b5aa9b26c`
- 범위: 32 files, 817 insertions, 60 deletions
- 상태: 공식 소스 복제본에 구현·검증, 설치본에는 미적용

구현된 상관관계는 다음과 같다.

`recorder-backed buffered STT roundId → chat runtime roundId → local/official LLM
header + AbortSignal → speech token/segment/intent → local/official REST TTS header
+ 같은 round의 취소·stale 차단`

round ID는 1–128자의 제한된 transport identifier이며 `turnId`, `intentId`,
`streamId`를 대체하지 않는다. official 및 exact loopback endpoint에만 전송하고,
임의 remote custom provider에는 보내지 않는다.

같은 session에서 사용자가 새 입력을 보내면 그 session의 active LLM만 abort한다.
background producer의 기존 FIFO는 유지한다. 취소된 응답은 assistant finalization,
completion hook, 성공/실패 telemetry로 처리하지 않는다. TTS는 fetch·decode·playback·
caption 각 경계에서 AbortSignal과 최신 round를 재검사한다.

local Ollama proxy의 true SSE와 AIRI의 기존 punctuation chunker가 결합되면 모델 완료
전에 첫 문장 TTS 요청을 시작할 수 있다. 한 문장 내부 REST audio byte streaming은
포함하지 않는다.

## 3. 검증 결과

- 변경 경계 집중 테스트: **169/169 통과**
- typecheck: core-agent, pipelines-audio, stage-ui, server, Web, Pocket,
  Tamagotchi 모두 통과
- production build: Web, Pocket, Tamagotchi 모두 통과
- `git diff --check`: exit 0
- patch 역적용 검증: `git apply --check --reverse` 통과

세부 테스트와 적용 명령은
`airi_docs/patches/AIRI-v0.11.3-round-cancel-source-replacement.md`에 기록했다.

## 4. 남은 live 경계

설치본에는 신규 source patch가 없으므로 실제 AIRI UI에서의 동일 round header 관찰,
active LLM/TTS 네트워크 취소, 첫 본문 음성 개선을 아직 운영 성공으로 주장하지 않는다.
적용은 clean v0.11.3 source build와 사용자 승인 뒤 진행한다.

장시간 streaming STT는 HTTP session 하나가 여러 chat message를 만들 수 있으므로
per-sentence protocol ID가 생기기 전까지 end-to-end explicit correlation 대상에서
제외한다. 또한 실제 음향 기반 full-duplex barge-in은 AEC 또는 신뢰 가능한 speech
trigger가 필요하며 이 patch의 범위가 아니다.
