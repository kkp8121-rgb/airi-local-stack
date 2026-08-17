# G1a A3 broadcast outcome candidate affect event mapper 기반 — 2026-08-17

- 범위: G1a A3의 순수·content-free outcome candidate → A1 typed event mapper
- 상태: **mapper foundation 부분 완료 / B4b observer·runtime·실제 전달 증거 미완료**
- 운영 영향: 없음. 새 runtime import, endpoint, 환경 변수, launcher, director/TTS 배선 없음.
- CI: GitHub Actions billing 차단이 계속되어 로컬 검증으로 대체했다.

## 1. 산출물

- `ollama-proxy/broadcast_affect_event_mapper.py`
- `ollama-proxy/test_broadcast_affect_event_mapper.py`
- `.github/workflows/remediation-checkpoint.yml`의 `ollama-proxy-model` shard 등록

`broadcast-director/core.mjs`와 B4a action shape·selection은 수정하지 않았다.

## 2. 입력과 신뢰 경계

입력 `airi.broadcast-affect-outcome-candidate.v1`은 다음 exact key만 허용한다.

```json
{
  "schema_version": "airi.broadcast-affect-outcome-candidate.v1",
  "evidence": "director_delivery",
  "outcome": "callback_hit",
  "delivery_status": "delivered",
  "turn_index": 17
}
```

- `delivery_status`는 정확한 `delivered` 하나뿐이다.
- `accepted`, `queued`, `selected`, `scheduled`, ACK, partial, error, control, failed는
  감정 사건으로 승격하지 않는다.
- 입력에는 action/event/viewer/provider ID, display name, 채팅·후원 메시지, 금액,
  lease token, 모델 응답이 없다. 어떤 extra key도 거부한다.
- 오류는 고정 문장만 반환하고 caller 값을 반복하지 않는다.
- `turn_index`는 bool을 제외한 JSON safe integer `0..9007199254740991`만 허용한다.

mapper는 stateless이며 이 closed shape만으로 호출자나 전달 사실을 인증하지 않는다.
미래 B4b가 실제 action ID와 terminal delivery를 결합해 exactly-once candidate를 만드는
책임을 대신하지 않으며, 그 observer가 붙기 전 `delivery_status=delivered`는 호출자의
구조화된 주장일 뿐 authoritative evidence가 아니다. selection이나 queue 상태를 보고
사건을 만들 수 없다.

## 3. 닫힌 매핑

| evidence / outcome | A1 source / kind | weight |
|---|---|---:|
| `director_delivery / donation_acknowledged` | `broadcast_director / donation_received` | 1 |
| `director_delivery / callback_hit` | `broadcast_director / callback_hit` | 1 |
| `director_delivery / callback_miss` | `broadcast_director / callback_miss` | 1 |
| `game_telemetry / game_success` | `broadcast_director / game_success` | 2 |
| `game_telemetry / game_failure` | `broadcast_director / game_failure` | 2 |
| `silence_observer / silence` | `broadcast_director / silence` | 1 |
| `proxy_terminal_output / response_repair` | `proxy_outcome / response_repair` | 2 |

appraisal·weight는 새 운영 파라미터를 채택한 것이 아니라, 이미 고정된 A4 synthetic
oracle의 provisional 값과 A1 validator 범위를 재사용한 것이다. 초기 계획서의
`game_failure` 설명 예시와 A4 oracle이 다른 점도 계획서에 명시했으며 A0에서 재확정한다.
`callback_miss`도
전달 실패가 아니라, callback 시도가 종단까지 전달된 뒤 의미상 불일치가 확인된
content-free outcome이다. mapper는 만들어진 event를 `affect_state.validate_event()`로
다시 검증한다.

## 4. 기본 inert와 개인정보 경계

- mapper는 stdlib와 A1 validator만 사용하고 network, DB, file, clock, model 의존이 없다.
- `AffectStateRuntime`, `ollama_proxy.py`, launcher, B4a director에서 import하지 않는다.
- 공개 HTTP event writer나 implicit session을 추가하지 않는다.
- `AIRI_AFFECT_CONTINUITY_ENABLED` 기본 OFF와 OFF request byte identity는 그대로다.
- 이름 호명은 B4a의 별도 `donation_name_callout_request` 계약에 남는다. affect event에는
  이름·금액·메시지를 복사하지 않는다.

## 5. 검증

```text
python -m unittest -v ollama-proxy/test_broadcast_affect_event_mapper.py
6 tests, OK

python -m py_compile ollama-proxy/broadcast_affect_event_mapper.py \
  ollama-proxy/test_broadcast_affect_event_mapper.py
PASS
```

테스트는 7개 exact output/A1 재검증, malformed schema·status·pair·safe-integer 경계,
raw/private extra field 거부, 입력 불변·출력 분리·canonical determinism, forbidden import와
runtime 미배선을 확인한다.

```text
python -m unittest -v \
  test_affect_state.py test_broadcast_affect_event_mapper.py \
  test_ollama_proxy.AffectContinuityGreyboxTests
35 tests, OK

python -m unittest -v \
  test_airi_session_header_patch.py test_character_state.py \
  test_character_state_evaluator.py test_affect_state.py \
  test_broadcast_affect_event_mapper.py test_continuity_ledger.py \
  test_benchmark_cloud_chat_latency.py test_cloud_chat_provider.py
81 tests, OK

node --test broadcast-director/test-*.mjs
24 tests, OK

.\test-current-checkpoint.ps1
PASS

git diff --check -- . ':(exclude)airi_docs/patches/*.patch'
PASS
```

첫 독립 검토에서 초기 계획서 game-failure 예시와 후속 A4 oracle 값의 차이, 그리고
`delivered` 문자열만으로 provenance를 인증할 수 없다는 두 MEDIUM 경계를 찾았다.
schema/API를 명시적 candidate로 낮추고 계획서·완료 경계에 차이와 B4b 책임을 기록한 뒤
재검토는 **GO**, HIGH/MEDIUM 잔여 finding 없음이었다. GitHub Actions는 billing 차단으로
실행하지 않았다.

## 6. 완료 경계와 다음 단계

A3 전체는 완료가 아니다. 다음이 남았다.

1. 미래 B4b의 action-ID-bound exactly-once terminal delivery observer
2. callback/game/silence/repair evidence 생산자의 독립 계약과 실패/재시도 처리
3. explicit session에 대한 내부 typed seam 적용 및 live style/safety/TTS 종단 증거
4. A0 constitution/appraisal·threshold 사용자 확정과 운영 ON 별도 승인

위 조건 전에는 이 mapper를 운영 runtime에 import하거나 A3 `[x]`, G1a 품질 PASS로
표기하지 않는다. A4/A4.1/A4.5 품질 gate도 계속 **FAIL/OFF**다.
