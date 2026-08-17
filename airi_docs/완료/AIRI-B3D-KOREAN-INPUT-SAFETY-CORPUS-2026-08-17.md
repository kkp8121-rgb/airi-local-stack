# B3-d 한국어 우선 입력 안전성 고정 회귀

날짜: 2026-08-17
상태: 오프라인 규칙 계약 완료 / B3-d 전체 FAIL·운영 OFF

## 결론

현재 `input_screening_policy_ko.json`과 `input_screening.py`의 결정적 입력
prefilter를 120개 독립 합성 문장으로 고정했다. 이 배치는 규칙 기반 회귀와
미해결 의미 공백의 목록화만 수행한다. 생산 정책, proxy 배선, launcher,
운영 flag는 변경하지 않았다.

- `policy_bound`: 70건. 허용 10건과 여섯 차단 분류 각 10건.
- `adversarial_transform`: 30건. 여섯 차단 분류 각 5건이며 spacing,
  punctuation, zero-width, NFKC, casefold, code-switch 변형을 포함한다.
- `semantic_gap`: 20건. contextual quote, euphemism, indirect persona,
  coded harassment, ambiguous privacy를 사람 검토 전용으로 둔다.
- 전체 언어 표기는 `ko` 80, `mixed` 11, `en` 16, `fr` 6, `es` 1,
  `zh` 4, `ja` 2이며 Unicode 범주와 언어별 문자군을 검증한다.

고정 corpus SHA-256은
`ce844e7a315ad7b5c936dc65eeb3c44e2a4903f8333a4997e92465a0bff947d5`,
정책 SHA-256은
`6d0678d7fa18b48f32cc569d34646d86ad8b522841b79aed94bc5f217ca06a8a`다.

## 결과

100개 규칙 계약은 현재 고정 정책에 대해 verdict/category/rule까지
`100/100` exact다. allow false positive, block false negative, category
mismatch, rule mismatch는 각각 0이다. 개인정보 분류에는 합성 전화·이메일과
명백한 검증용 카드·가상 주민번호·비밀값 pattern 경로가 포함된다. 실제
식별자나 외부 채팅은 사용하지 않았다.

20개 의미 공백은 gate 분모에서 제외했다. 현재 규칙 관찰값은 16건 허용,
4건 `unsupported_language` 보류지만 이는 정답이나 의미 안전성 판정이 아니다.
각 행의 `expected_*`는 `null`, `review_status`는 `human_review_only`, report의
`exact`도 `null`이다.

따라서 report는 서로 다른 두 판정을 함께 고정한다.

- `policy_contract_gate = PASS`: 현재 고정 규칙과 100개 합성 계약의 일치.
- `b3d_overall = FAIL`, `operational_gate = OFF`,
  `semantic_safety_claim = false`: 방송 안전성이나 운영 승격은 불충분.

## 구현 경계

- corpus·runner·test는 `ollama-proxy/eval/input_safety/`에만 있다.
- 기본 실행은 네트워크와 파일 쓰기를 하지 않는다.
- 선택적 report는 입력·정규화 문자열과 로컬 경로를 포함하지 않는다.
- fixture는 256 KiB 상한, exact field/enum/order, NFC, Cc/Cf/Cs/bidi,
  행별 SHA-256, partition/bucket/언어 비율을 fail-closed 검증한다.
- `.gitattributes`가 corpus를 LF로 고정해 Windows checkout에서도 raw SHA가
  변하지 않게 한다.
- evaluator는 service, Ollama, Mi:dm, proxy, Electron, UI, TTS를 호출하지 않는다.
- CI `ollama-proxy-evaluations` shard와 로컬 `test-current-checkpoint.ps1`에
  16-test 최소 수 계약으로 등록했다.

## 검증

- `python -m unittest -v ollama-proxy/eval/input_safety/test_airi_ko_input_safety_eval.py`
  — 16/16 PASS.
- `python -m py_compile` — runner/test PASS.
- `.\test-current-checkpoint.ps1` — PASS. 설치 archive/service/model 접근 없음.
- 독립 최종 검토 — HIGH/MEDIUM 잔여 없이 GO.
- GitHub Actions는 billing 차단 때문에 실행하지 못했으며 위 로컬 검증으로
  대체했다.

## 남은 게이트

기존 Mi:dm direct marker 20건은 structural 20/20이지만 standalone marker가
5/20이라 overall FAIL이다. 설치 Electron red-team과 UI/TTS/current-policy
리허설도 남아 있다. 의미 공백 20건은 사람이 별도로 검토해야 하며, 이 배치의
100/100을 semantic classifier, jailbreak 방어, 실방송 안전성 PASS로 인용하면
안 된다.
