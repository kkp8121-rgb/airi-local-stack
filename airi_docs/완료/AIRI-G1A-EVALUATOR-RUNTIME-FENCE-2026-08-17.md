# G1a evaluator-only runtime import fence — 2026-08-17

- 범위: A4.2~A4.6 평가 전용 artifact의 production literal import/reference 금지
- 상태: **오프라인 정적 fence 완료 / 품질·운영 gate는 FAIL/OFF**
- 운영 영향: 없음. production code, prompt, wording, endpoint, flag, launcher 동작을 바꾸지 않는다.
- CI: GitHub Actions billing 차단이 계속되어 로컬 checkpoint 검증으로 대체했다.

## 1. 배경

`must_act_realization.py`와 `correction_target_realization.py`의 고정 한국어 문장은
합성 평가용 미승인 proposal이다. A4.5 결과도 target 3/8 대 control 2/8이라 prompt만의
안정적 개선을 입증하지 못했고, fixed 8/8은 self-conformance일 뿐이다. 기존 focused test는
주로 `ollama_proxy.py` 한 파일만 직접 확인해 다른 runtime helper나 launcher·patch를 통한
accidental wiring을 local checkpoint에서 막지 못했다.

## 2. 구현

- `test-affect-evaluator-runtime-fence.mjs`
  - Node built-in만 쓰는 deterministic source scanner와 11개 self-test
  - repository root 아래 first-party source를 재귀적으로 scan하고 runtime patch도 별도 scan
  - repo-relative path와 forbidden token만 보고하고 source text는 반복하지 않음
- `test-current-checkpoint.ps1`
  - 위 exact test를 `node --test`로 실행
  - nonzero exit를 거부하고 최소 11개 reported test를 요구해 no-test green을 방지

금지하는 evaluator-only literal family는 다음과 같다.

- `must_act_realization`, `must_act_realization_v1.json`
- `run_guarded_delta_eval`
- `correction_target`, `correction_target_v1.json`
- `run_correction_target_ab_eval`, `run_affect_broadcast_eval`
- `correction_target_realization`, `correction_target_realization_v1.json`
- `run_correction_realization_postcondition_eval`
- `correction_prepublication_policy`, `correction_prepublication_policy_v1.json`
- `run_correction_prepublication_eval`

intentional `broadcast_correction_target.py`는 A4.4의 exact local-evaluation transport seam이며
위 renderer/postcondition module과 다른 닫힌 production module이므로 허용한다.

## 3. scan 경계

scan 대상은 repository root 아래의 first-party Python/JavaScript/TypeScript/Vue/PowerShell,
JSON/YAML/TOML 설정과 CMD/BAT launcher, `airi_docs/patches/*.patch`다. 새 first-party
component와 하위 runtime directory도
기본적으로 재귀 탐색한다. 다음은 의도적으로 제외한다.

- `test-*`/`test_*`, 일반 docs, `ollama-proxy/eval`, training/testdata/bench 결과
- `.venv`, `node_modules`, model, debug recording, log/runtime DB
- ignored local results/operator keys/private replay/reports
- upstream third-party snapshot

따라서 이 검사는 개인·generated/runtime data를 읽지 않고, production artifact에 미승인
평가 모듈의 literal 이름이 들어오는지만 확인한다.

## 4. 검증 범위

fixture는 다음을 고정한다.

1. direct import와 helper를 통한 indirect literal import 검출
2. A4.3/A4.4 base/oracle/runner와 A4.6 prepublication policy/runner reference 검출
3. 단순 quoted literal 결합 Python/JavaScript/PowerShell reference 검출
4. root launcher와 runtime patch reference 검출
5. 새 first-party component와 중첩 runtime source 자동 발견
6. 대소문자 변형 검출과 codepoint 기준 stable relative-path 결과
7. tests/docs/eval/private/generated/third-party reference 제외
8. intentional `broadcast_correction_target` 허용
9. missing/invalid/symlink root와 included symlink fail-closed
10. 현재 production scan 위반 0

이 fence는 literal static reference 검사다. 단순 quoted literal 결합은 정규화해 검출하지만,
임의 난독화·코드 생성·hostile same-account 파일 교체 또는 런타임 동적 로더의 보안 증명은
아니다. 그런 방식은 이 repository의 승인된 workflow가 아니며 별도 code review와 runtime
provenance가 필요하다.

## 5. 로컬 검증

```text
node --test test-affect-evaluator-runtime-fence.mjs
11 tests: 9 PASS, 2 SKIP (현재 Windows 환경의 symlink 생성 권한 없음), 0 FAIL

.\test-current-checkpoint.ps1
PASS

git diff --check -- . ':(exclude)airi_docs/patches/*.patch'
PASS
```

독립 재검토는 **GO — HIGH/MEDIUM 잔여 없음**이었다. relative/qualified/multiple/from-member
Python import 우회가 모두 회귀에서 검출되고, intentional `broadcast_correction_target` seam과
일반 `correction_target` 지역 변수는 오탐 없이 허용됨을 확인했다. LOW 한계로 import 형태의
주석을 보수적으로 잡을 수 있고 임의 난독화·동적 코드를 증명하지 않는다는 점은 유지한다.

## 6. 완료 경계

이번 배치는 A4.2~A4.6 evaluator artifact의 accidental literal wiring을 방지할 뿐이다.
다음을 완료하거나 승인하지 않는다.

- 승인 표현 정책의 fresh model·human review
- fixed fallback 또는 constrained retry의 운영 전략 채택
- proxy prepublication postcondition/runtime selector
- A3 B4b authoritative observer, live model/TTS/installed AIRI 증거
- `AIRI_AFFECT_CONTINUITY_ENABLED` 또는 다른 운영 gate ON

따라서 A4.6 evaluator 결과를 운영 배선으로 승격하는 일은 계속 fresh evaluation·human
review와 별도 사용자 결정 뒤에 남는다.
