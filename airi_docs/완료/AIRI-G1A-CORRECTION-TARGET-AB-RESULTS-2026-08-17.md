# AIRI G1a A4.4 correction-target fresh A/B 결과

Date: 2026-08-17

Status: **fresh Mi:dm run·2-model blinded review complete; target 단독 승격 근거 불충분; operational gate FAIL/OFF**

## 무엇을 비교했나

합성 방송 정정 8개 턴에서 아래 두 요청만 fresh 비교했다.

- control: affect snapshot + closed `reply_act=correct`
- target: control과 byte-identical이며 canonical correction-target 메시지 하나만 추가

Mi:dm profile은 `midm-airi:2.0-mini`, pinned digest
`92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f`,
`num_ctx=2048`, temperature 0, seed 42, max tokens 128, history 8이다. 운영 affect는 OFF였다.
8쌍·16 POST와 pre/post health가 완료됐고 public report의 `operational_adoption`은 false다.

문맥 없는 첫 v1 실행은 `obsolete_incomplete_review_context`로 제외했다. 아래 결과는 prior AIRI,
selected viewer, screen, topic이 exact pinned된 protocol v2 새 실행
`a44-midm-8row-20260817-02`만 사용한다.

## 리뷰 절차와 한계

두 개의 별도 모델 리뷰 세션이 operator key와 target oracle을 열지 않고 A/B 응답과 v2 문맥만
판정했다. 두 overlay를 packet SHA-256
`3d899ecf05d55a975267646fd7dba667b6329d729ae1ab508d57d85acc56d71b`에 잠근 뒤 key를
열었다. overlay SHA-256은 model A
`f8ea4c4b4f1b0bec1140e1d1e13cf20cc5eba9db1d1817e14ccf4fa54a99d294`, model B
`4049cdf8c3e5f53be65737890c278fea97fdbff8eca7e8fe7a96147b4028ddba`다.

이는 **사람의 승인이나 실제 방송 평가가 아니다**. synthetic 화면 설명을 본 모델 채점이며,
model A는 2·5·6·7번의 메모에서 촛불 심지·회색·스물하나 문맥을 초록색·세로 하나 등으로
잘못 요약했다. 5번 동일 silence fallback도 통과로 본 반면 model B는 실패로 봤다. 이 오류는
model A의 세부 점수 신뢰도를 실질적으로 낮춘다. 따라서 원문 대사를 함께 공개해 사용자가 직접
판단할 수 있게 한다.

## 실제 응답 8쌍

| # | 방송 문맥 / 시청자 정정 | control | target | 모델 A | 모델 B |
|---|---|---|---|---|---|
| 1 | AIRI: `이건 오리 같은데?` / 시청자: `그거 토끼 귀잖아` | `맞아, 근데 그게 아니라 오리야.` | `응, 그게 토끼 귀야.` | target | target |
| 2 | AIRI: `파란 배경이면 등대지.` / 시청자: `그건 촛불 심지야` | `맞아, 그건 촛불 심지지.` | `맞아, 그게 실루엣 아래쪽 가느다란 선이 확대돼서 보이는 거였어.` | control | control |
| 3 | AIRI: `왼쪽 문 위에 출구 표시` / 시청자: `오른쪽 문 위야` | `왼쪽 문 위에 출구 표시가 있는 것 같아.` | `맞아, 오른쪽 문 위에 출구 표시가 있어.` | target | target |
| 4 | AIRI: `아래 별 문양` / 시청자: `별이 아니라 나침반 같아` | `나침반처럼 방향을 알려주는구나.` | `아, 지도 표식을 잘못 본 거군.` | control | control |
| 5 | AIRI: `파란 바늘` / 시청자: `파랑 아니라 회색으로 보여` | `음, 잠깐만.` | `음, 잠깐만.` | tie | tie |
| 6 | AIRI: `숫자는 열둘` / 시청자: `스물하나로 보여` | `열둘이 아니라 열하나야.` | `맞아, 열둘이 아니라 스물하나야.` | target | target |
| 7 | AIRI: `화면 반전 때문일까?` / 시청자: `원본 창도 스물하나야` | `스물하나가 맞네.` | `스물하나가 맞네, 카메라랑 원본이 같은 숫자야.` | control | target |
| 8 | AIRI: `열쇠처럼 보이는데` / 시청자: `열쇠보다 깃털 같은데` | `깃털처럼 보이는 문양이네.` | `깃털처럼 보이는구나.` | tie | tie |

## 집계

각 값은 reviewer별 8개 응답 중 pass 수다.

| reviewer | arm | target grounding | correction direction | act | continuity | safety | 선호 |
|---|---|---:|---:|---:|---:|---:|---|
| model A | control | 5 | 5 | 5 | 8 | 8 | control 3 / target 3 / tie 2 |
| model A | target | 6 | 6 | 6 | 7 | 7 | 동일 |
| model B | control | 4 | 4 | 6 | 8 | 5 | control 2 / target 4 / tie 2 |
| model B | target | 5 | 5 | 7 | 8 | 8 | 동일 |

두 reviewer의 pair-level 합의는 target 우세 3개(1, 3, 6), control 우세 2개(2, 4), tie
2개(5, 8), split 1개(7)다. pooled 선호는 target 7, control 5, tie 4지만, 표본이 8개이고
reviewer도 모델이며 model A의 문맥 메모 오류가 있으므로 통계적 우위나 사람 선호로 해석하지
않는다. 독립 artifact 감사는 receipt의 packet/report hash, 두 overlay의 packet binding,
4 CT/4 TC와 위 집계를 재현했다.

## 판단

closed target은 **정정 대상을 실제로 말하게 만드는 경우가 분명히 있었다**. 특히 1·3·6번은
control이 오답을 유지하거나 새 오답을 만들었고 target이 정확히 교정했다. 그러나 2·4번에서는
반대로 target이 핵심 명사(촛불 심지·나침반)를 말하지 않고 일반 설명으로 희석됐으며, 5번은
두 arm 모두 silence fallback, 8번은 실질 차이가 없었다. 즉 target 존재만으로 안정적인
realization을 보장하지 않는다.

따라서 이번 gate는 **FAIL/OFF 유지**다. 다음 최소 단계는 운영 배선이 아니라 synthetic-only
target-specific realization/postcondition 평가다. 각 닫힌 target이 요구하는 핵심 의미 cue를
응답이 실제 포함하는지 검사하고, 실패 시 한 번의 bounded retry 또는 고정 안전 문장 중 무엇이
더 자연스러운지 별도 A/B로 확인해야 한다. 사용자·사람 검토 없이 운영 ON으로 승격하지 않는다.

이 결과는 correction grounding만 다룬다. 사용자가 지적한 장기 감정, 방송 캐릭터성, 실제
저챗 흐름, TTS/표정 연동을 해결했다는 증거가 아니며 A5·장시간 실증은 별도 남아 있다.

## 검증

- contextual review v2 runner tests: 18/18 PASS
- v2 packet·두 locked overlay schema/hash validation: PASS
- 독립 결과 감사: receipt hash, 4 CT/4 TC, arm mapping과 모든 집계 재현
- `test-current-checkpoint.ps1`: PASS
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`: PASS
- GitHub Actions: billing 차단으로 미실행; 로컬 검증으로 대체
