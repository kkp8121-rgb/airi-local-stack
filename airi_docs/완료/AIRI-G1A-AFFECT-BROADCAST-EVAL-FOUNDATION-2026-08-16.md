# G1a A4 합성 방송 감정 평가 기반 — 2026-08-16

- 범위: G1a A4의 `synthetic fixture + reducer oracle + paired transport contract`
- 상태: **offline foundation 완료 / A4 Mi:dm A/B·blind human review는 미완료**
- 운영 영향: 없음. `AIRI_AFFECT_CONTINUITY_ENABLED` 기본 OFF 유지

## 1. 이번 배치가 만든 것

- `ollama-proxy/eval/affect_broadcast/synthetic_affect_broadcast_v1.json`
  - 독립 작성한 한국어 방송 흐름 6개 × 24턴 = 144턴
  - AIRI 직전 발화, 화면·게임·화제 상태, 선택 채팅 또는 무응답, typed event,
    reducer expected state, 허용/금지 표현 trait를 분리
  - 첫 방송 적응, 그림 퀴즈 놀림·수습, 게임 연속 실패·성공, 화면 근거 정정,
    콜백·익명 후원·소음/무응답, 피로·침묵·serious-safety 우선순위를 포함
- `ollama-proxy/eval/affect_broadcast/run_affect_broadcast_eval.py`
  - exact scenario/event/no-response manifest와 fixture SHA-256 pin
  - A1 reducer를 직접 replay하는 exact oracle
  - 최대 8개 고정 canonical history를 쓰는 122개 응답 대상 OFF/ON pair
  - OFF/ON의 유일한 차이를 384-byte typed affect note로 제한
  - literal 11435 `/api/chat`와 `local-evaluation`만 허용하는 injected transport 계약
  - Mi:dm tag/digest, `num_ctx=2048`, temperature 0, seed 42,
    max tokens 128, history 8, 운영 affect OFF를 pre/post health로 고정
  - HTTP/JSON/빈 응답/non-assistant 응답/불완전 pair/profile drift·위조 health
    hash fail-closed
  - content-free public report와 분리된 blind private packet/arm key builder
- `ollama-proxy/eval/affect_broadcast/test_affect_broadcast_eval.py`
  - 구조·한국어·역할 분리·인과 milestone·multi-turn pair·health·private/public
    경계를 offline fake transport로 검증
- `airi_docs/진행예정/AIRI-CHARACTER-CONSTITUTION-V2-DECISION-2026-08-16.md`
  - 확정 이월과 likes/dislikes/pride/embarrassment/conflict/repair/fatigue 미정
    선택지를 분리한 A0 사용자 승인 시트

## 2. 숫자와 자동 판정 경계

| 항목 | 결과 |
|---|---:|
| synthetic scenario | 6 |
| 총 turn | 144 |
| model-response 대상 pair | 122 |
| 명시적 no-response turn | 22 |
| 명시적 ambient-noise turn | 1 |
| reducer oracle | 144/144 exact |
| serious safety override event | 7 |
| response repair event | 15 |
| 실제 Mi:dm response | **0 — 실행하지 않음** |
| blind human review | **미실행** |

fixture의 AIRI 발화, 화면 상태, 선택 채팅은 서로 다른 역할이며 전역 중복을
거부한다. 숫자 접미사만 바꾼 template, mojibake, replacement/control/bidi 문자,
비canonical scenario·event·topic·no-response 순서도 fail-closed다.

자동 판정은 reducer state/cause/drive와 OFF/ON 입력 대칭, transport 무결성까지만
다룬다. 응답의 인과 표현, 긍정 평탄화, 수습 품질, 대화 연속성, 캐릭터성은
사람 평가 대상이다. 특히 A0 미승인 상태에서는 `character_specificity`를
`unscored_constitution_unapproved`로 고정한다.

## 3. 격리·보안 경계

- 기본 CLI는 네트워크를 사용하지 않는다. `--execute`만으로도 실제 호출하지 않고
  명시적으로 주입된 loopback transport를 요구한다.
- runner는 운영 affect runtime, event seam, 환경 변수, 서비스 설정을 변경하지 않는다.
- production request-local copier는 전체 proxy app을 import하지 않고 해당 순수 함수
  AST와 고정 message-name 상수만 로드한다.
- 운영 affect gate가 ON이거나 ready면 실행 계약이 실패한다. A/B의 ON은 runner의
  isolated expected state note일 뿐 운영 승격이 아니다.
- public report에는 fixture text, event/state payload, 모델 응답, session ID가 없다.
  private review packet과 arm key는 pure builder이며 파일을 쓰지 않는다.

## 4. 검증

```powershell
python -m unittest -v ollama-proxy/eval/affect_broadcast/test_affect_broadcast_eval.py
python -m py_compile `
  ollama-proxy/eval/affect_broadcast/run_affect_broadcast_eval.py `
  ollama-proxy/eval/affect_broadcast/test_affect_broadcast_eval.py
python ollama-proxy/eval/affect_broadcast/run_affect_broadcast_eval.py
git diff --check -- . ':(exclude)airi_docs/patches/*.patch'
```

- focused unittest: **10/10 PASS**
- py_compile: PASS
- offline CLI content-free report: PASS
- diff-check: PASS
- `.github/workflows/remediation-checkpoint.yml`의 `ollama-proxy-evaluations` shard에
  신규 테스트를 등록했다.
- GitHub Actions는 기존 billing 차단 때문에 실행하지 않았다. 로컬 검증으로
  대체하며 자동 승격 근거로 사용하지 않는다.
- 독립 최종 리뷰는 HIGH/MEDIUM 잔여 finding 없이 **A4 offline foundation**
  범위의 commit 가능 판정을 냈다.

## 5. 명확한 미완료

1. A0 승인 시트의 7개 성격 항목과 metric threshold 사용자 확정
2. 실제 설치 Mi:dm/11435에서 122쌍 OFF/ON 응답 생성
3. arm key를 분리한 blind human review와 승인 threshold 판정
4. A3 B4b delivery-confirmed typed event source
5. A5 TTS/Live2D 표현 및 A6 승인 30~120분 설치 리허설
6. 운영 `AIRI_AFFECT_CONTINUITY_ENABLED=on` 사용자 결정

따라서 이 기록은 **A4 offline foundation**의 근거이지 A4 전체 완료, G1a 완료,
라이브 방송 검증, Mi:dm 품질 PASS, 운영 ON 채택 근거가 아니다.
