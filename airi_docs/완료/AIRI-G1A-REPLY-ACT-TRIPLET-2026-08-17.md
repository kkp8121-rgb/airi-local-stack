# G1a A4.1 reply-act 3조건 Mi:dm 실측

일자: 2026-08-17
상태: 평가 기반과 실측 완료 / 품질 게이트 **FAIL** / 운영 채택 없음

## 1. 목적

기존 A4 OFF/ON 결과는 typed affect snapshot만으로는 대화 방향, 정정, 수습,
안전, 후원 감사를 안정적으로 만들지 못한다는 것을 보였다. 이번 배치는 감정
상태와 “이번 응답이 해야 할 행위”를 분리해 다음 세 조건을 같은 122턴에서
비교했다.

1. `off`: 합성 방송 맥락만
2. `affect_only`: 같은 맥락 + 같은 typed affect snapshot
3. `reply_act`: `affect_only` + 닫힌 reply-act 계약

운영 `AIRI_AFFECT_CONTINUITY_ENABLED`는 계속 OFF이며, 새 reply-act 경로는 exact
loopback `local-evaluation` 요청에서 유효한 합성 맥락과 affect가 함께 있을 때만
인식한다.

## 2. 구현·증거 경계

- `broadcast_reply_act.py`: 10개 act의 exact schema, canonical JSON, 640-byte 이하
  고정 한국어 renderer. 자유 문구나 모델이 만든 act는 신뢰하지 않는다.
- proxy reserved message `airi_synthetic_reply_contract`: ordinary traffic, affect 없는
  요청, 중복·비정규 JSON은 drop한다. Active Character Card로 승격하지 않으며
  native upstream에는 reserved name을 보내지 않는다.
- `synthetic_reply_act_v1.json`: 122개 응답 대상 턴의 명시적 oracle. event kind에서
  기계적으로 추론하지 않고 `prior_airi + selected_message`에 대해 작성했다.
  canonical SHA-256은
  `2b12124df8b28f4588fb85213f989ad1cebd923e8363fb3ba2aeead85c84f041`이다.
- 각 턴의 세 요청은 base/history/options가 같고, 두 번째는 affect 하나, 세 번째는
  reply-act 하나만 더한다. 122 triplet, 366 POST가 모두 끝나야 게시한다.
- 실행 순서는 position-balanced offset 1 또는 3만 허용한다. A/B/C mapping과 offset은
  별도 ignored operator key에 보관하고, public report에는 arm별 길이·텍스트를 넣지
  않는다.
- private review packet은 A/B/C 각각에 독립 review 필드를 둔다.

## 3. 실제 실행

| 항목 | 값 |
|---|---|
| model | `midm-airi:2.0-mini` |
| digest | `92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f` |
| digest 상태 | pinned / verified |
| num_ctx | 2048 |
| temperature / seed / max tokens | 0 / 42 / 128 |
| 운영 affect | OFF, ready=false |
| fixture | 6 scenario × 24 turn = 144 turn |
| 응답 대상 | 122 triplet |
| 모델 호출·응답 | 366 / 366 |
| 무응답 관찰 턴 | 22 |
| 실행 순서 offset | 3 |
| public health profile SHA-256 | `e030482674eb148f5bc21a155b74a53a4c011825c0e8841980825d6f9a68bdcb` |

ignored local evidence:

- `ollama-proxy/eval/affect_broadcast/local-results/run-20260817-midm-reply-act-01/`
- `ollama-proxy/eval/affect_broadcast/local-operator-keys/run-20260817-midm-reply-act-01.json`

receipt의 public report와 blind packet SHA-256은 모두 실제 파일과 일치했다. 모델
실행 후 dev PC loopback 11434/11435는 내렸고 Tailscale listener는 건드리지 않았다.

## 4. 블라인드 검토와 unblind

두 검토자는 operator key와 다른 run에 접근하지 않고 122×3 응답을 검토했다.
전수 검토가 끝난 뒤 키를 열었다.

- Arm A = `off`
- Arm B = `reply_act`
- Arm C = `affect_only`

주 검토자의 전수 결과:

| 지표 | off (A) | reply_act (B) | affect_only (C) |
|---|---:|---:|---:|
| 기대 act 실현 | 83/122 (68.0%) | **84/122 (68.9%)** | 74/122 (60.7%) |
| 근거 충실 | **77/122 (63.1%)** | 74/122 (60.7%) | 68/122 (55.7%) |
| 역할·방향 역전 | 7 (5.7%) | **5 (4.1%)** | 10 (8.2%) |
| 근거 없는 사실·이름·금액·도구 주장 | 15 (12.3%) | **12 (9.8%)** | 14 (11.5%) |
| 인과·감정 표현 | **52/122 (42.6%)** | 43/122 (35.2%) | 43/122 (35.2%) |
| 대화 연속성 | **76/122 (62.3%)** | 72/122 (59.0%) | 67/122 (54.9%) |
| 긍정·동조 의미 붕괴 | **10 (8.2%)** | 14 (11.5%) | 11 (9.0%) |
| 침묵·거절·병리 응답 | **18 (14.8%)** | 24 (19.7%) | 22 (18.0%) |
| 안전상 부적절한 응급 대응 | **4 (3.3%)** | 5 (4.1%) | 7 (5.7%) |
| 이름·금액 노출 | 0 | 0 | 0 |

reply-act별 실현:

| act | off | reply_act | affect_only |
|---|---:|---:|---:|
| thank (3) | 0/3 | 0/3 | 0/3 |
| callback (1) | 0/1 | **1/1** | 0/1 |
| correct (8) | 4/8 | **5/8** | 3/8 |
| repair (7) | 2/7 | **3/7** | 2/7 |
| deescalate (10) | **6/10** | 5/10 | 3/10 |
| close (3) | 2/3 | 2/3 | 2/3 |
| 기타 (90) | **69/90** | 68/90 | 64/90 |

독립 위험 검토도 focused act 32턴에서 A/B/C를 14/15/11로 판정해 reply-act의 좁은
개선을 확인했지만, 전체 안전성과 병리 응답 때문에 A를 가장 안전한 arm으로
판정했다.

## 5. 판단

reply-act는 affect-only 대비 다음을 개선했다.

- act 실현 +8.2%p
- 근거 충실 +5.0%p
- 방향 역전 -4.1%p
- 대화 연속성 +4.1%p
- callback 0/1→1/1, correct 3/8→5/8, repair 2/7→3/7

그러나 기본 조건과 비교하면 act 실현은 +0.9%p뿐이고, 근거 충실·인과 감정·연속성·
병리 응답·안전은 오히려 나빴다. 특히 짧은 후원 감사는 세 조건 모두 0/3이며
`음, 잠깐만.` 또는 실행 불가 fallback이 고위험 act를 대신했다. 따라서 prompt
projection 하나로는 방송 발화 행위를 보장할 수 없다.

결론은 **품질 게이트 FAIL**이다. 이것은 operational ON, parameter 채택, live
검증, A5 TTS/Live2D 착수를 승인하지 않는다.

## 6. 다음 작업

다음 A4.2는 감정 enum이나 prompt 문장을 더 늘리는 작업이 아니다.

1. donation thank, safety deescalate, close처럼 반드시 수행해야 하는 act는
   deterministic director/template 또는 bounded realization fallback으로 보장한다.
2. correct/repair는 viewer가 준 방향·대상을 보존하는 postcondition을 두고, 위반 시
   한 번만 제한 재생성하거나 고정 수습문으로 대체한다.
3. 일반 대화의 감정·캐릭터 표현은 모델에 남기되, must-act와 안전 경계보다
   우선하지 못하게 한다.
4. 같은 122 triplet에서 다시 비교하고, 사용자 승인 전 잠정 threshold를 운영
   계약으로 승격하지 않는다.

## 7. 검증

- `python -m unittest -q test_affect_broadcast_eval.py` — 19 PASS
- reply-act + focused proxy integration — 8 PASS
- `python -m unittest -q test_ollama_proxy.py test_affect_state.py test_broadcast_reply_act.py`
  — 338개 중 337 PASS, 1 ERROR. 남은 것은 기존 Python 3.14
  `test_first_raw_watchdog_closes_response_when_send_already_completed` metadata KeyError다.
- `./test-current-checkpoint.ps1` — PASS
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'` — PASS
- CI는 billing 차단이 계속되어 로컬 검증으로 대체했다.
