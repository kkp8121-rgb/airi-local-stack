# G1a A1 감정 상태 코어 기반 완료 — 2026-08-16

- 범위: G1a A1 `typed affect state·event + deterministic reducer`
- 상태: **A1 foundation 완료 / G1a 전체는 진행중**
- 운영 영향: 없음. proxy import·prompt 주입·환경 변수·방송/TTS 배선 없음.
- CI: GitHub Actions billing 차단이 계속되어 로컬 검증으로 대체했다.

후속 참고: 이 문서의 미배선 경계는 A1 배치 당시 범위다. 같은 날 A2 default-OFF
proxy greybox가 후속 구현됐으며 현재 상태는
`AIRI-G1A-AFFECT-PROXY-GREYBOX-2026-08-16.md`를 함께 본다.

## 1. 산출물

- `ollama-proxy/affect_state.py`
- `ollama-proxy/test_affect_state.py`
- `.github/workflows/remediation-checkpoint.yml`의 `ollama-proxy-model` shard 등록

## 2. 구현 계약

### strict typed schema

- state `airi.affect-state.v1`
- event `airi.affect-event.v1`
- closed source/kind/appraisal/primary/drive/familiarity enum
- JSON safe integer, exact key set, bool-as-int 거부
- `(source, kind)` allowlist와 kind별 보수적 weight 상한
- validation error는 raw 값·unknown key·session ID를 반복하지 않는다.

### 순수 reducer

- model/network/DB/wall-clock 의존 없음
- 동일 `(state,event)`의 결정적 결과와 입력 불변
- valence/arousal/dominance/intensity/remaining-turn이 호출당 최대 한 단계만 이동
- turn/silence 중립 수렴, saturation, inertia/hysteresis, repair/recovery
- safety/moderation의 `concerned/deescalate` 우선순위와 다음 ordinary event lock
- 강한 반복 근거는 valence ±2/arousal 2/intensity 2에 도달하고 약한 근거는 1에
  제한
- `embarrassed`, `disappointed`를 포함한 13개 primary가 valid event sequence에서
  모두 도달 가능
- `broadcast_end`는 최종 snapshot을 반환한 뒤 해당 runtime session·event ring·
  audience familiarity를 폐기

### bounded runtime

- 기본 256, 최대 4,096 session LRU
- session별 event ring 기본/최대 128
- NFC·길이·Unicode control/format/surrogate를 검사하는 strict session ID
- 단조 증가 turn index, invalid/out-of-order write의 LRU 무영향
- copy-safe snapshot, LRU-neutral read, explicit reset
- session/content/ID가 없는 count-only health

## 3. 검증

### focused 및 인접 회귀

```text
python -m unittest -v test_affect_state.py
20 tests, OK

python -m unittest -v \
  test_airi_session_header_patch.py \
  test_character_state.py test_character_state_evaluator.py \
  test_affect_state.py test_continuity_ledger.py \
  test_benchmark_cloud_chat_latency.py test_cloud_chat_provider.py
74 tests, OK
```

활성 Python은 3.14.3이며 `pytest`가 설치돼 있지 않아 `python -m pytest`는 실행하지
못했다. CI 기준 Python 3.12 실행은 billing 차단 해소 후 확인한다.

### 속성 검사

- root 고정 seed `20260816`, valid state/event 50,000개:
  determinism, input immutability, output schema, 모든 수치 한 단계, familiarity 한
  단계, safe version saturation — PASS
- 독립 reviewer boundary/property sweep 39,852 transition:
  saturation, safety precedence, extrema reachability 포함 — PASS

### 정적/등록 검증

- `python -m py_compile affect_state.py test_affect_state.py` — PASS
- tracked 후보에 새 test를 포함해 workflow matrix와 대조 — 72 proxy tests,
  candidate contract PASS
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'` — PASS
- 독립 최종 검토 — remaining blocker 없음

## 4. 완료 경계

이 배치는 다음을 **증명하지 않는다**.

- `AIRI_AFFECT_CONTINUITY_ENABLED` 또는 다른 운영 env의 구현·ON
- `character_state.py`/`ollama_proxy.py` prompt 주입
- 채팅 의미 appraisal 또는 B4 event adapter
- Mi:dm OFF/ON 발화 품질 개선
- TTS prosody, Live2D/ACT stage emotion
- 설치 AIRI·B1b/B4b·실제 방송 검증

A0의 constitution v2 세부 취향·갈등/회복 방식과 정량 통과선은 여전히 사용자
확정 대상이다. A1의 표와 enum은 A2/A4 전까지 변경 통제되는 provisional contract로
취급한다.

## 5. 다음 단계

1. A2 기본 OFF proxy greybox와 OFF request byte identity
2. content-free health·reuse fail-closed 계약
3. A0 constitution v2 사용자 확정
4. A3 미래 B4b delivery-confirmed event mapper
