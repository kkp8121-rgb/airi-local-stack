# AIRI G1a A4.5 correction realization postcondition 결과

Date: 2026-08-17

Status: **zero-network retrospective complete; lexical target 3/8 vs control 2/8; fixed proposals 8/8 self-conformance only; quality/operational gate FAIL/OFF**

## 결론부터

A4.4에서 correction target을 prompt에 넣은 것만으로는 정정 내용을 안정적으로 말하게
만들지 못했다. 엄격한 닫힌 cue 검사는 target arm **3/8**, control **2/8**을 통과시켰다.
target-only 2행, control-only 1행, 양쪽 통과 1행, 양쪽 실패 4행이다. 즉 target prompt의
순증가는 1행에 불과하고 절반은 두 조건 모두 핵심 정정 형태를 만들지 못했다.

고정 제안문 8개는 동일한 구조 검사에서 8/8을 통과한다. 이는 문장을 검사 규칙에 맞춰
작성했기 때문에 예상되는 **self-conformance**이며, 자연스러움·캐릭터성·사실성·사람 선호·
운영 채택의 증거가 아니다. 따라서 이번 단계에서도 어떤 문구도 runtime에 배선하지 않는다.

## 무엇을 검사했나

입력은 A4.4 protocol v2의 exact synthetic 8-pair packet이다.

- source run: `a44-midm-8row-20260817-02`
- source packet SHA-256:
  `3d899ecf05d55a975267646fd7dba667b6329d729ae1ab508d57d85acc56d71b`
- A4.5 run: `a45-retrospective-20260817-06`
- 새 proxy POST: 0
- 새 model call: 0

검사는 target별 요구 cue, 긍정형 현재 판단, 기존 오답 cue 부재, direction 형태를 확인한다.
질문·인용·메타 발화·부정·가정형은 보수적으로 실패시킨다. 숫자 21은 `21`, `스물하나`,
`이십일`만 허용하고 다른 숫자와 함께 나오면 실패한다. 결과에는 응답 원문이 없고 boolean과
failure bitmask만 남는다.

이 판정은 의도적으로 좁은 lexical/structural evidence다. 문장의 진실, 실제 화면 grounding,
부정문을 포함한 자연스러운 정정의 의미, 방송 재미를 판정하지 않는다. 이 때문에 사람에게는
올바른 문장도 보수적으로 실패할 수 있다.

## 8행 결과

원문 응답은 `AIRI-G1A-CORRECTION-TARGET-AB-RESULTS-2026-08-17.md`에 있다.

| # | target | control | target-aware | 고정 제안문 |
|---:|---|---:|---:|---:|
| 1 | 토끼 귀 | FAIL | PASS | PASS |
| 2 | 촛불 심지 | PASS | FAIL | PASS |
| 3 | 오른쪽 문 위 출구 표시 | FAIL | PASS | PASS |
| 4 | 나침반 문양 | FAIL | FAIL | PASS |
| 5 | 회색 바늘 | FAIL | FAIL | PASS |
| 6 | 문 번호 21 | FAIL | FAIL | PASS |
| 7 | 원본 창도 21 | FAIL | FAIL | PASS |
| 8 | 깃털 같은 문양 | PASS | PASS | PASS |

이 집계는 A4.4 model reviewer 선호표를 재사용하지 않는다. exact recorded response에 새로 고정한
lexical rule만 적용했다. A4.4 receipt가 operator key 자체를 bind하지 않으므로 arm 귀속은
honest-local integrity 범위이며 hostile-local authenticity는 성립하지 않는다.

## 사용자 검토용 고정 제안문

아래 문장은 모델 응답이 아니라 **평가 전용·미승인 proposal**이다. 정상 발화를 대체하는
상시 템플릿이 아니라, exact correction target이 있고 공개 가능한 모델 문장이 실패했을 때의
최후 후보로만 검토한다.

| # | 상태 의도 | 제안문 |
|---:|---|---|
| 1 | 첫 오답의 짧은 민망함 | `아, 토끼 귀로 보이네. 내가 제대로 낚였어.` |
| 2 | 반복 확신 뒤 차분한 인정 | `음, 촛불 심지로 보이네. 이번 건 네 말이 맞아.` |
| 3 | 좌우 오판 인정 | `잠깐, 출구 표시는 오른쪽 문 위에 있네. 내가 반대로 봤어.` |
| 4 | 문양 해석 교체 | `그러네. 아래 문양은 나침반 모양으로 보여.` |
| 5 | 색 오판과 다음 행동 | `응, 바늘은 회색으로 보여. 색부터 다시 볼게.` |
| 6 | 숫자 읽기 수정 | `맞아, 문 번호는 스물하나로 보여.` |
| 7 | 기존 교정 확인 | `응, 원본 창도 스물하나네.` |
| 8 | 확신을 낮춘 닮음 판단 | `응, 깃털처럼 보여. 그쪽 해석이 더 자연스럽네.` |

이전 사용자 검토 시트의 긴 “정상 발화 목표”와 달리, 위 문장들은 failure-only 후보라 짧다.
1번은 민망함, 2·3·5번은 자기수정, 8번은 확신 하향을 드러내지만 캐릭터 깊이를 충분히
증명하지 않는다.

## 사용자 판단 항목

- [ ] 1번의 `내가 제대로 낚였어`가 AIRI다운 민망함/장난기로 들린다.
- [ ] 2번의 `네 말이 맞아`가 지나친 순응이 아니라 반복 오답 뒤의 적절한 인정이다.
- [ ] 5번의 `색부터 다시 볼게`처럼 짧은 회복 행동을 fallback에 허용한다.
- [ ] 6·7번은 너무 평평하므로 감정 원인이나 자기수정을 한 절 더 넣어야 한다.
- [ ] 8번의 hedged resemblance가 호기심을 살리면서 과도한 확정을 피한다.
- [ ] 고정 문장은 exact target + prepublication failure에서만 1회 사용하며 평상시 캐릭터
  말투로 재사용하지 않는다.

체크 전에는 문구 승인, fallback 전략 선택, retry 정책, 운영 ON을 뜻하지 않는다.

## 다음 단계

다음 A4.6을 진행하려면 먼저 사용자가 위 wording 방향을 판단해야 한다. 그 뒤에도 바로
runtime에 넣지 않는다. proxy non-stream 경로에는 이미 숨은 bounded retry/fallback이 있으므로,
추가 A/B는 upstream attempt 수와 prepublication postcondition outcome을 관찰할 수 있는
평가 전용 seam을 먼저 만들어야 한다. 비교 후보는 다음 둘이다.

1. target-specific postcondition 실패 시 단 한 번의 constrained retry
2. 사람이 승인한 fixed failure fallback

두 전략 모두 exact authoritative target source, 최대 upstream attempt 수, public yield 이전 판정,
사람 자연스러움 검토를 통과해야 한다. A3/B4b/live/TTS는 계속 범위 밖이고 운영 gate는 OFF다.

## 검증

- A4.5 focused offline tests: 22 PASS / 1 symlink-privilege SKIP
- full `affect_broadcast` unittest discovery: 98 PASS / 2 platform-privilege SKIP
- A4.5 source/report/receipt/key exact validation: PASS
- actual zero-call retrospective: target 3/8, control 2/8, fallback proposal 8/8
- public report SHA-256:
  `b185cd3b9c786d617200a1b1f8193a94c91ac551b583fe1b50ad4e2785bce8c7`
- private detail SHA-256:
  `18965911204137382467cf382468bc90be1a6fcd14e517a916dbe16aff714b52`
- local receipt SHA-256:
  `e04d9bc4dbc8f8e0f5889109776d1e75c08afe0b7927037927233dbfa6066fae`
- `test-current-checkpoint.ps1`: PASS
- `python -m py_compile` 및 `git diff --check`: PASS
- 독립 semantic/integrity 재검토: 범위 내 GO, HIGH/MEDIUM 잔여 0
- GitHub Actions: billing 차단으로 미실행; 로컬 검증으로 대체
