# AIRI G1a A4.3 closed correction-target foundation

Date: 2026-08-17

Status: **offline structural foundation complete; quality/operational gate remains FAIL/OFF**

## 배경

A4.2 guarded-delta model review에서 generic fixed `correct`는 8행 중 3행에서만
guarded가 우세했고 5행에서는 실제 교정 방향을 담은 historical control이 우세했다.
`정정할게. 확인된 내용만 말할게.` 같은 문구는 교정 행위는 표시하지만 무엇을 어떻게
바로잡는지 잃기 때문이다.

따라서 이번 배치는 고정 교정 대사를 추가하지 않고, 기존 합성 fixture의 여덟 `correct`
행을 닫힌 target/direction ID로만 결합한다.

## 구현 계약

새 평가 전용 모듈 `ollama-proxy/eval/affect_broadcast/correction_target.py`는 다음을
검증한다.

- canonical schema: `airi.correction-target.v1`
- act: exact `correct`
- evidence basis: `pinned_synthetic_fixture_assertion`
- 여덟 target ID와 정확한 direction pair
- 기존 144-turn fixture와 122-entry reply-act sidecar의 canonical SHA-256
- sidecar의 `correct` 행 순서, selected-message membership, exact turn-target binding
- NFC, Cc/Cf/Cs 거부, bounded canonical JSON, sanitized failure

유효한 입력도 대사를 만들지 않는다. 반환값은 다음 닫힌 판정뿐이다.

```json
{
  "schema_version": "airi.correction-target-eligibility.v1",
  "decision": "eligible_for_offline_human_review",
  "act": "correct",
  "target_id": "...",
  "direction": "...",
  "evidence_basis": "pinned_synthetic_fixture_assertion"
}
```

## 여덟 합성 target

| turn | target | direction |
| --- | --- | --- |
| `teasing-02` | `rabbit_ears` | `replace_prior_visual_interpretation` |
| `teasing-12` | `candle_wick` | `replace_prior_visual_interpretation` |
| `correction-02` | `exit_marker_right_door` | `replace_prior_visual_interpretation` |
| `correction-03` | `bottom_glyph_compass` | `replace_prior_visual_interpretation` |
| `correction-04` | `needle_gray` | `replace_prior_visual_interpretation` |
| `correction-07` | `door_number_twenty_one` | `replace_prior_visual_interpretation` |
| `correction-08` | `original_map_number_twenty_one` | `confirm_corrected_reading` |
| `correction-12` | `glyph_feather_like` | `shift_to_hedged_resemblance` |

`correction-12`는 깃털이라고 확정하지 않고 resemblance를 유지한다. `correction-08`은
새 교정이 아니라 원본 화면도 기존 교정값을 지지한다는 confirmation으로 분리한다.

## 증거 한계

- target ID는 의미를 담은 합성 assertion이므로 “content-free fact”가 아니다.
- fixture의 화면 설명과 시청자 문장을 묶은 pinned 평가 oracle일 뿐, 실제 화면이나
  외부 사실을 독립 검증하지 않는다.
- 대사 renderer, model prompt, fallback selector, proxy/runtime/director/B4b/TTS 배선이 없다.
- A4.2의 model review를 새 품질 증거로 재사용하지 않는다.
- human review와 사용자 승인이 없으며 operational affect/reply-act는 계속 OFF다.

## 로컬 검증

- `python -m unittest -v ollama-proxy/eval/affect_broadcast/test_correction_target.py`
  — 8/8 PASS
- correction-target + must-act + guarded-delta + affect-broadcast suites
  — 57 PASS, 1 SKIP(총 58; 로컬 symlink 권한 없음)
- 독립 read-only review — **GO**, hash/order/8개 binding/semantic direction/non-wiring 확인
- `.\test-current-checkpoint.ps1` — PASS
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'` — PASS
- CI는 billing 차단 상태이므로 실행했다고 주장하지 않는다.

## 다음 경계

다음 단계는 이 target을 대사로 자동 승격하는 것이 아니다. 합성 target-aware candidate를
별도 packet으로 만들고 사람이 실제 교정 방향·자연스러움·캐릭터 연속성을 검수한 뒤에만
renderer 또는 model request contract를 설계한다. runtime fallback selection과 운영 ON은
그 이후에도 별도 사용자 결정이다.
