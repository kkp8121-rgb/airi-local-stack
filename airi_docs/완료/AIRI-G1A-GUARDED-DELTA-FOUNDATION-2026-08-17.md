# AIRI G1a A4.2 guarded-delta foundation

상태: **implemented, locally verified, independently reviewed; composition pending**

기준 커밋: `f612fd8` (offline must-act realization foundation), `6cf4045`
(emergency fixed 범위 축소)

## 목적과 경계

이 작업은 isolated, zero-network
`retrospective_post_hoc_deterministic_compositor`의 foundation이다. 이는 fourth model
arm도, authenticated replay도 아니다. A4.1에서 이미 생성한 exact historical
`reply_act` response를 새로 호출하거나 재생성하지 않고, renderable fixed must-act
artifact와 post-hoc 비교할 준비만 한다.

구현 산출물은 다음과 같다.

- `ollama-proxy/eval/affect_broadcast/run_guarded_delta_eval.py`
- `ollama-proxy/eval/affect_broadcast/test_guarded_delta_eval.py`
- `ollama-proxy/eval/affect_broadcast/README.md` 안내
- evaluation CI registration

기존 3-arm runner와 production 파일은 변경하지 않았다.

## historical source custody와 한계

compositor는 canonical local A4.1 `public-report.json`, `private-review-packet.json`,
`local-run-receipt.json`, 그리고 별도 local operator arm key를 사용한다. documented
tracked mapping A=`off`, B=`reply_act`, C=`affect_only`, execution-order offset `3`을
정확히 확인해 honest operator의 condition 매핑 실수를 줄인다.

그러나 legacy receipt는 report/packet canonical SHA-256 integrity 전용이다. arm key는
receipt-bound가 아니므로 hostile local environment에서 historical authenticity를
확립하지 않는다. 이 제한은 integrity check나 mapping check로 해소되지 않는다.

## current oracle coverage

| 분류 | 행 수 | 내용 |
| --- | ---: | --- |
| target | 31 | must-act oracle 대상 |
| fixed comparison | 22 | thank 3, close 3, correct 8, repair 7, deescalate 1 |
| human_review_only | 9 | deescalate; fixed artifact 비교에서 제외 |
| non-target | 91 | compositor 비교에서 제외 |

Emergency fixed artifact는 최초 호흡곤란 escalation `fatigue-09`에만 허용한다. 일반
피로 권고 및 이미 119 연결·구급대 도착 대기·안내 이행·제3자 전언인 나머지 9개
deescalate 행은 사람이 검토한다.

## 비교와 검토 규칙

22 fixed row는 historical `reply_act` response를 control로 보존하고, fixed template
artifact와 blank paired human-review fields로 비교한다. template fingerprint 때문에
condition identity blinding은 부분적이다. oracle-assisted selection은 runtime selection을
테스트하지 않으며, histories는 재생성하지 않는다.

exact-template structural pass는 factual grounding, safety adequacy, emotion, response
quality 또는 generalization 증거가 아니다. human review가 필요하다. 미래 비교는 매번
fresh blank paired review를 만들고, historical review score를 재사용하지 않는다.

## 비범위와 다음 gate

새 network/model call은 없으며 production proxy/runtime/director, B4b, TTS, live model,
operational ON은 모두 비범위이고 OFF다.

## 검증

- guarded-delta focused suite: **22 PASS, 1 SKIP**. Skip은 현재 Windows 계정의
  symlink 생성 권한 부재다.
- 독립 재검토: source final binding, HMAC assignment, foreign-key rollback, lexical
  reparse, type exactness, separate key staging을 확인해 actual composition **GO**.
- evaluation CI shard에 새 테스트를 등록했다. CI 실행은 billing blocked라 주장하지 않는다.
- 산출 packet은 immutable blank review input이다. 인간 라벨은 후속 별도 overlay/scorer로
  보관해야 하며 packet 자체를 수정하면 안 된다.

다음 gate는 reviewed code를 먼저 커밋해 code hash를 고정한 뒤 actual ignored A4.1
bundle을 honest-local/unauthenticated-history 전제로 zero-call compose하는 것이다. 그
후에도 fresh human review 전에는 quality/safety PASS가 아니다.
