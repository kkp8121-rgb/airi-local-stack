# G1a A2 affect proxy greybox 완료 — 2026-08-16

- 범위: G1a A2 `default-OFF proxy greybox + health/launcher contract`
- 상태: **A2 greybox 완료 / G1a 전체와 운영 ON은 미완료**
- 운영 영향: 기본값 OFF. 운영 환경이나 현 요청 prompt를 자동으로 바꾸지 않는다.
- CI: GitHub Actions billing 차단이 계속되어 로컬 검증으로 대체했다.

## 1. 산출물

- `ollama-proxy/affect_state.py`: 384 UTF-8 bytes 이하 typed snapshot projection
- `ollama-proxy/ollama_proxy.py`: opt-in runtime, typed event seam, request-local injection,
  content-free health
- `ollama-proxy/test_affect_state.py`, `ollama-proxy/test_ollama_proxy.py`
- `ollama-proxy/start-local-ollama-proxy.ps1`, `start-airi-local-stack.ps1`
- `test_midm_model_configuration.py`

## 2. 기본 OFF와 수명주기

- 환경 변수는 `AIRI_AFFECT_CONTINUITY_ENABLED`이며 launcher 기본값은 `off`다.
- launcher는 `on|off`만 받고 child env로 명시적으로 전달한다. 자동 승격은 없다.
- proxy 직접 실행에서는 정확한 소문자 `on`만 enabled로 해석하고 나머지는 OFF다.
- OFF full route는 affect injector를 호출하지 않는다. helper 단위에서도 원래 bytes
  객체를 그대로 반환하고 session을 만들지 않는다.
- ON startup은 매 lifespan마다 빈 `AffectStateRuntime`을 새로 만든다. 생성 실패 시
  과거 runtime을 재사용하지 않고 startup을 중단한다. shutdown은 runtime을 폐기한다.

## 3. 신뢰·세션·prompt 경계

- 공개 HTTP event 작성 endpoint는 없다. 내부 `apply_affect_continuity_event()`는
  A1 exact typed event와 명시적 session ID만 받고, raw text에서 event를 추론·보정하지
  않는다.
- header가 없는 요청에 `implicit-local-session`을 만들지 않는다. snapshot이 이미
  존재하는 정확한 session만 다음 정상 foreground 요청에 투영된다.
- `local-evaluation`, `local-quality-probe`, proactive, topic-reset, sessionless 요청은
  주입·상태 변경을 하지 않는다.
- affect sub-block은 closed enum/int snapshot과 고정 지시만 담는다. 최장 valid
  snapshot 실측은 348 UTF-8 bytes로 384-byte 상한 안이다.
- 고정 지시는 감정명을 직접 말하지 않고 어휘·길이·질문·받아치기에 간접 반영하며
  기존 safety 규칙이 우선하도록 한다.
- `affect_continuity` health에는 enabled/ready, mode/schema, prompt cap과 count만
  있고 session ID, primary/cause/drive, event, 사용자·모델 text는 없다.

## 4. launcher/reuse fail-closed

- 기존 11435를 재사용할 때 `affect_continuity.enabled`와 `ready`가 JSON Boolean인지,
  mode/schema/prompt cap이 정확히 `typed-snapshot-v1`/`airi.affect-state.v1`/384인지
  확인한다.
- 요청값과 enabled가 다르거나, ON을 요청했는데 ready가 false면 재사용을 거부한다.
- root stack도 live health를 같은 방식으로 검증하고 최종 요약에 enabled/ready를
  노출한다.
- 이 계약은 기능을 ON으로 채택한다는 뜻이 아니다. 사용자가 `-AffectContinuity on`을
  명시해야 한다.

## 5. 로컬 검증

```text
python -m unittest -v test_affect_state.py
21 tests, OK

python -m unittest -v test_ollama_proxy.AffectContinuityGreyboxTests
8 tests, OK

python -m unittest -v \
  test_airi_session_header_patch.py test_character_state.py \
  test_character_state_evaluator.py test_affect_state.py \
  test_continuity_ledger.py test_benchmark_cloud_chat_latency.py \
  test_cloud_chat_provider.py
75 tests, OK

python test_midm_model_configuration.py
20 tests, OK
```

- 두 PowerShell launcher는 `[scriptblock]::Create()` parse PASS.
- 변경 Python은 `py_compile` PASS.
- affect 파일을 tracked candidate로 포함한 `test-current-checkpoint.ps1` 전체 PASS.
- API shard와 같은 6개 파일을 `unittest`로 실행하면 393개 중 392개가 PASS했다.
  남은 1건은 이 변경 전부터 Python 3.14 로컬에서 재현된
  `test_first_raw_watchdog_closes_response_when_send_already_completed`의 기존 timing
  metadata 오류다. affect 변경 경로와 별개이며 CI 기준 Python 3.12 확인은 billing
  차단 해소 뒤 필요하다.
- 독립 A2 재검토에서 기존 11435 계약 식별자 미검증과 health/request readiness
  불일치 2건이 발견됐다. mode/schema/cap exact 검증과 단일 lock 아래 runtime
  폐기로 수정했으며 최종 재검토는 HIGH/MEDIUM 잔여 finding 없이 clean이었다.
- active Python에는 `pytest`가 없어 pytest 명령은 실행하지 못했다.

## 6. 완료 경계와 다음 작업

이 배치는 typed 상태가 있는 경우의 안전한 전달 경로를 증명한다. 다음은 증명하지
않는다.

- 채팅 문장에서 의미를 추론하는 appraisal classifier
- B4b delivery-confirmed donation/callback/game/silence event mapper
- proactive와 foreground의 실제 공통 affect outcome observer
- Mi:dm OFF/ON 발화 품질·캐릭터성 개선
- TTS/Live2D 표현, 설치 AIRI 또는 장시간 방송 검증

따라서 운영 gate는 계속 OFF다. 다음 구현은 A3 event source가 아니라, 먼저 A0
constitution v2의 취향·자존심·민망함·갈등/회복 방식을 사용자와 확정하거나 A4의
독립 합성 fixture/oracle을 준비하는 것이다. B4b가 없는 상태에서 free text를 임의로
event로 승격하지 않는다.
