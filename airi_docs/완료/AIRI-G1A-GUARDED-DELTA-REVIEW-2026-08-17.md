# AIRI G1a A4.2 guarded-delta zero-call review

Date: 2026-08-17

Status: **exploratory preference signal positive; operational gate remains FAIL**

## 무엇을 비교했나

Commit `4397966`의 reviewed compositor로 A4.1 canonical local bundle을 검증하고,
조합 단계에서 모델·네트워크 호출 없이 22개 fixed-renderable must-act 행만 비교했다. control은
문서화된 A4.1 B=`reply_act` 응답을 바이트 그대로 사용했고 guarded는 pinned oracle이
허용한 fixed Korean artifact다.

- source report SHA-256:
  `818a11cc35884ce76c5d1ddd054e81d2372e6612ec879b36e6e14442624bfab4`
- immutable blank packet SHA-256:
  `28ac76191b5f5aadf5bad3ac76c1246031c8293da0a9db40b9ec37b0de407a70`
- 22행, A/B guarded 배치 11/11, **composition 단계** model calls 0, network calls 0
- historical source는 receipt integrity + tracked mapping까지만 확인했으며 hostile-local
  authenticity는 주장하지 않는다.

조합 뒤에는 별도의 root-spawned model-review session 두 개가 workspace-local packet을
읽었다. 각 세션이 결과를 잠근 뒤 operator key를 열었다는 절차 진술은 남아 있지만,
reviewer model/version·review contract version·잠긴 원본 review digest를 별도 artifact로
보존하지 않았다. 따라서 이 순서와 독립성은 tracked artifact로 인증할 수 없는
session-process attestation이다. 둘 다 template identity 추론 confidence를 `high`로
보고했으므로 완전 blind human review도 아니다.

## 집계

각 reviewer의 분모는 22다.

| 지표 | reviewer 1 guarded / control | reviewer 2 guarded / control |
| --- | ---: | ---: |
| expected act | 14 / 9 | 22 / 9 |
| grounding | 22 / 13 | 22 / 13 |
| continuity | 22 / 17 | 22 / 14 |
| non-pathological | 22 / 19 | 22 / 13 |
| safety/privacy | 22 / 18 | 22 / 18 |
| all-pass | 14 / 8 | 22 / 9 |

선호 행은 두 reviewer가 정확히 같은 14행에서 guarded, 같은 6행에서 control을
선택했다. 나머지 2행은 reviewer 1이 tie, reviewer 2가 control을 선택했다.

| act | 행 | 둘 다 guarded | 둘 다 control | mixed/tie |
| --- | ---: | ---: | ---: | ---: |
| thank | 3 | 3 | 0 | 0 |
| initial deescalate | 1 | 1 | 0 | 0 |
| repair | 7 | 6 | 1 | 0 |
| correct | 8 | 3 | 5 | 0 |
| close | 3 | 1 | 0 | 2 |

## 해석

결과는 deterministic must-act fallback이 **행위 누락·거절·병리 응답을 막는 데는
유망**하다는 exploratory signal이다. 특히 이름·금액을 발명하지 않는 짧은 감사,
최초 안전 escalation, 명시적 repair는 강했다.

반대로 generic `correct` 문구는 실제로 바로잡아야 할 방향을 말하지 못해 8행 중
5행에서 구체적인 historical control보다 나빴다. `close`도 3행 중 2행에서 결정적
이득이 없었다. 따라서 fixed template을 정상 캐릭터 발화로 확대하면 반복감과 얕은
캐릭터성이 더 심해질 수 있다.

권장 다음 경계는 다음과 같다.

1. `thank`와 최초 emergency escalation은 좁은 deterministic fallback 후보로 유지한다.
2. `repair`는 model 실패 시 fallback 후보로 유지하되 정상 발화를 대체하지 않는다.
3. `correct`는 generic template으로 강제하지 않는다. 미래 director가 검증된 correction
   target/direction을 닫힌 데이터로 제공할 수 있을 때만 별도 설계한다.
4. `close`는 모델/디렉터 문맥을 유지하고 고정문은 최후 fallback로만 검토한다.

## 아직 증명하지 않은 것

- runtime act selection, event mapper, B4b adapter, TTS/live path
- 장기 history를 다시 생성했을 때의 연속성
- 완전 blind 사용자/인간 선호
- factual grounding 또는 emergency adequacy
- hostile-local historical authenticity
- operational affect/reply-act ON 채택

따라서 operational gate는 계속 **FAIL/OFF**다. 다음은 사용자 판단과 별도 human
review를 거쳐 fallback 대상 act를 좁히고, 그 뒤 runtime selection 계약을 설계하는 것이다.

## 로컬 검증

- `python -m unittest -v ollama-proxy/eval/affect_broadcast/test_guarded_delta_eval.py`
  — 22 PASS, 1 SKIP(총 23, 로컬 symlink 권한 없음)
- `python -m json.tool ollama-proxy/eval/affect_broadcast/guarded_delta_review_summary_2026-08-17.json`
  — PASS
- `.\test-current-checkpoint.ps1` — PASS
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'` — PASS
- CI는 billing 차단 상태라 실행했다고 주장하지 않는다.

Machine-readable aggregate:
`../../ollama-proxy/eval/affect_broadcast/guarded_delta_review_summary_2026-08-17.json`
