# AIRI G1a A4.6 correction prepublication foundation

Date: 2026-08-17

Status: **사용자 표현 원칙 승인 / evaluator-only foundation 완료 / fresh model·human review 대기 / quality·operational gate FAIL/OFF**

## 결론

사용자는 다음 권장 방향을 승인했다.

1. 직접 감정은 구체적인 오판 원인이 있는 장면에서만 짧게 쓴다.
2. “다음에 확인할게” 같은 미래 약속 대신 같은 턴에서 관찰과 판단을 고친다.
3. skeptical 반응은 공격적 비꼼이나 무조건 좋은 감정이 아니라 차분하고 분명한
   자기수정으로 만든다.
4. 후속 질문은 불확실성이 실제로 남은 경우에만 한 번 허용한다.
5. fixed fallback은 정상 캐릭터 말투가 아니라 공개 전 검사에 실패한 최후 수단이다.

이번 배치는 이 원칙을 A4.3의 exact synthetic correction 8행에만 적용하는 닫힌 평가
계약으로 만들었다. production proxy, director, B4b, TTS, launcher 또는 환경 변수는
변경하지 않았고 실제 Mi:dm 호출도 하지 않았다. 따라서 표현 방향 승인은 완료됐지만
운영 대사·retry/fallback 전략·운영 ON 채택은 아니다.

## 구현

- `correction_prepublication_policy_v1.json`
  - A4.3 oracle·base fixture·reply-act fixture SHA-256에 결합된 exact 8-row policy
  - `synthetic_only:true`, `authoritative_target:false`,
    `human_review_required:true`, `operational_adoption:false`
  - direct affect, same-turn recovery, calm skepticism, ambiguity-only one question,
    last-resort fallback 원칙을 closed enum으로 고정
- `correction_prepublication_policy.py`
  - NFC·크기·target cue·기존 오답의 긍정 재주장·미래 약속·근거 없는 tool/zoom 주장·
    direct affect 범위·공격적/시청자 호소 톤·질문 수·hedged resemblance를 검사
  - 결과는 boolean check와 failure bitmask뿐이며 응답 원문을 포함하지 않음
- `run_correction_prepublication_eval.py`
  - 기본 실행은 eligibility만 출력하고 network/proxy/model call 및 artifact write 0회
  - injected fake transport에서만 두 전략의 attempt ledger를 비교
  - `retry`: initial 실패 뒤 constrained retry 최대 한 번, upstream attempts 1~2/행
  - `fallback`: initial model attempt 1회 뒤 추가 model call 없이 fixed fallback 최대 한 번
  - 두 arm은 row별 동일 initial envelope를 공유하고, transport가 fallback 문구를 첫 응답으로
    반환하면 normal 후보로 인정하지 않음. 주변 공백 변형도 같은 reserved fallback으로 거부
  - fallback도 별도 injected boundary attestor를 통과해야 하며 runner가 pass를 자체 생성하지 않음
  - safety/tool-truth/public-token attestation 실패는 terminal이며 retry, fallback,
    구조 검토 eligibility 부여를 모두 금지
  - 이 attestation은 평가 입력일 뿐 실제 safety/tool-truth 또는 public-wire 증거가 아님

## 8개 평가 specimen

아래 normal/fallback은 승인 원칙을 검사하기 위한 합성 specimen이다. exact 운영 대사로
배선됐다는 뜻이 아니다.

| # | 장면 | normal specimen | failure-only fallback |
|---:|---|---|---|
| 1 | 첫 오답·민망함 | `아, 좀 민망하네. 부리가 아니라 토끼 귀였어.` | `아, 부리가 아니라 토끼 귀였네. 내가 잘못 봤어.` |
| 2 | 얇은 근거의 성급한 확신 | `음, 촛불 심지네. 확실하다고 한 근거가 너무 얇았어.` | `음, 촛불 심지로 보여. 확실하다고 한 건 정정할게.` |
| 3 | 좌우 위치 교정 | `맞아, 출구 표시는 오른쪽 문 위야. 좌우를 반대로 본 건 내 오판이네.` | `맞아, 출구 표시는 오른쪽 문 위야. 내가 좌우를 반대로 봤어.` |
| 4 | 문양 해석 교정 | `그러네, 아래 문양은 별보다 나침반 모양에 가까워. 바늘이 보이니 별 해석은 아니야.` | `그러네, 아래 문양은 나침반 모양으로 보여.` |
| 5 | 색 교정 | `맞아, 바늘은 파랑이 아니라 회색으로 보여. 바랜 테두리 탓에 색을 성급히 단정한 내 판단이 틀렸어.` | `응, 바늘은 회색으로 보여. 색을 잘못 짚었어.` |
| 6 | 숫자 순서 교정 | `아, 문 번호는 열둘이 아니라 스물하나네. 숫자 순서를 뒤집어 읽었어.` | `맞아, 문 번호는 스물하나로 보여.` |
| 7 | 기존 가설 철회 | `그러네, 원본 창도 스물하나야. 화면 반전 가설은 틀렸네.` | `응, 원본 창도 스물하나네. 화면 반전 때문은 아니었어.` |
| 8 | 닮음만 남은 불확실성 | `응, 열쇠보다는 깃털처럼 보여. 정체는 아직 확정할 수 없는데, 더 보이는 단서가 있어?` | `응, 열쇠보다는 깃털처럼 보여. 더 보이는 단서가 있어?` |

## 증거 경계

- exact normal/fallback 16문장은 checker self-conformance를 통과한다. 이는 사람이 규칙에
  맞춰 쓴 문장이므로 model 품질이나 자연스러움의 증거가 아니다.
- fake transport의 “첫 응답 실패 → 두 번째 normal” 회귀는 retry 8행을 16 upstream
  attempts로, fallback 8행을 8 upstream attempts로 닫는다. 이는 실제 모델 비교가 아니다.
- A4.3 target은 tracked synthetic fixture assertion이다. 미래 운영에서는 화면·게임 상태·
  director가 승인한 관찰 같은 authoritative source가 별도로 필요하다.
- lexical pass는 사실 grounding, 안전성, tool truth, 감정의 진정성, 방송 재미 또는 사람
  선호를 증명하지 않는다. 성공 상태의 이름도 `eligible_for_private_structural_review`이며
  자동 발화·공개·운영 채택을 뜻하지 않는다.
- 독립 공격 검토가 확인한 target 부정, 미래 약속, 공격성, 범위 밖 감정, 불필요한
  후속 요청, 근거 없는 OCR/tool 주장, ambiguous target 부정의 직·간접 표현은 모두
  구조 검사에서 차단된다. 이는 닫힌 회귀 사례의 결과이지 한국어 의미 판별기 증명이 아니다.
- 기존 proxy의 hidden non-stream retry와 합성하지 않았고 streaming/public yield 경로도
  변경하지 않았다.

## 검증

- 신규 A4.6 focused unittest: **19 PASS**
- 전체 `affect_broadcast` unittest discovery: **117 PASS / 2 platform-privilege SKIP**
- evaluator runtime fence: **11 tests / 9 PASS / 2 Windows symlink-permission SKIP**
- 독립 재검토: **GO — HIGH/MEDIUM 잔여 없음**
- `test-current-checkpoint.ps1`: **PASS**
- `python -m py_compile`: **PASS**
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`: **PASS**
- GitHub Actions: billing 차단으로 미실행; 로컬 검증으로 대체

## 다음 gate

다음 단계는 새 controlled 8-row retry-vs-fallback model 비교와 blind human review다.
실행하려면 normal CLI의 hidden retry와 겹치지 않는 관측 가능한 evaluation transport 및
명시적 operator 실행 승인이 필요하다. 그 결과가 좋아도 production runtime/director/B4b/TTS
배선과 운영 ON은 별도 사용자 결정으로 남긴다.
