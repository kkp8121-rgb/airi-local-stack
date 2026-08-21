# AIRI 코덱스 배치 검수 — 2026-08-21 클로드 PC 평가

갱신: 2026-08-21

상태: **검수 완료 + 즉시 수리 6커밋 랜딩. 코덱스 선결 목록·사용자 확인 1건 대기.**

대상: `C:\Projects\airi\airi-local-stack` (main), 검수 시작 HEAD `ef67433` → 수리 완료 HEAD `889d4c2`.

이 문서는 자기완결형이다 — 태스크 원문(`​.superpowers/sdd/task-15-report.md`~
`task-20-report.md`)을 읽지 않아도 이 문서만으로 배치 전체를 파악할 수 있다.

---

## 0. 평가 방식

전날(2026-08-21 코덱스 PC) 배치를 영역 3분할해 검수자를 배정했다.

| 영역 | 검수자 | 대상 |
|---|---|---|
| R1 — 프록시·보안 | opus | capability 게이트, trace ledger, 시스템 프롬프트 계약 |
| R2 — 하네스·게이트 | opus | 런처, CI 배선, comparator, live campaign 계약 |
| R3 — 학습 governance | sonnet | 트레이너·머지·GGUF 핀 체계, continuity 코퍼스 eligibility |

각 검수 결과는 3버킷으로 분류했다: **즉시 수리**(이 배치에서 바로 고침) /
**코덱스 선결**(다음 코덱스 세션이 재개 전 반드시 처리) / **사용자 확인**(AI가
독단으로 판단할 수 없는 governance 질문).

---

## 1. R1 — 프록시·보안 (opus)

**총평**: capability 보안 성립 — 위조·재사용·비루프백 요청이 모두 차단됨을 확인.
어제(2026-08-20) 확정한 계약 4종은 무손상.

### 즉시 수리 2건 (완료)

- **F1 (CRITICAL)** — 재사용 `trace_id` 요청이 기본(OFF) 경로 chat을 죽임.
  `TraceReceiptLedger`가 같은 trace_id에 다른 내용이 오면 `raise ValueError`했고,
  이 예외가 SSE 제너레이터 밖으로 전파돼 2번째 턴 응답에 오류 폴백 문장이 섞여
  나갔다(실측: `'둘째 답이야.답을 만들다가 문제가 생겼어. 다시 말해줘.'`). fail-soft로
  전환 — 재사용 id를 raise하지 않고 해당 엔트리를 새 턴으로 재시작(덮어쓰기)하며
  `trace_reused_id_resets` 카운터로 관측한다. 위조 방지(3해시 일치 요구)는 그대로 유지.
- **F2 (HIGH)** — `AIRI_SYSTEM_PROMPT` 3항이 무조건 v4 확장 길이 규범으로 교체돼
  방송이 아닌 모든 chat 턴 프롬프트가 바뀌어 있었음. 방송 계약 게이트가 켜진 턴에서만
  적용되도록 게이트화하고, 기본(OFF) 경로 프롬프트를 ce82f2a 시점 바이트로 복원
  (LF 정규화 후 sha256 `7fa8bddc7dfef167…`, 949자 — 배치 직전과 완전 동일 확인).

### 코덱스 선결 (미수리)

| 항목 | 내용 |
|---|---|
| F3 | 발화계약↔출력경계 탈동조 — capability가 응답 문장 수를 실제로 올리지 못함. 15개 call site가 B4c env만 보고 있어 계약이 실질적으로 무효화된 지점이 있음. |
| F4 | receipt 3해시 정규화 경로가 3갈래로 갈라져 있고, 목(mock) 없는 실제 성공 경로 테스트가 0건. |
| F5 | `confirm_injected` 신호 이후 실패 시 쇼가 300초간 wedge(고착)됨. |
| F6 | 202-pending 응답이 후속 처리와 결속돼 있지 않음. |
| F7 | trace 없는 중복 저널 억제 로직이 제거돼 있음 — 의도적 변경인지 확인 필요. |

---

## 2. R2 — 하네스·게이트 (opus)

**총평**: 어제 확정한 기능 4종 보존. 캠페인 영수증(receipt) 체계는 우수하다는 평가.

### 즉시 수리 4건 (완료)

- 런처 `$Pid` PowerShell 예약 자동변수 셰도잉 — 함수 호출 즉시 크래시
  (`Cannot overwrite variable Pid because it is read-only or constant.`)를 재현 후
  `$OwnerPid`로 개명해 수리.
- CI에 신규 테스트 6파일 미배선 — `remediation-checkpoint.yml` matrix에 실제 경로
  기준으로 배선(지시문과 2건 경로가 달라 실측 경로로 정정).
- comparator(`compare_broadcast_t3.py`)에 provenance 필드 3종(`phase`,
  `fixtures_compared`, `seeds_by_fixture`) 추가 전용 삽입.
- comparator의 `Path.cwd().rglob(...)` CWD 의존 코드를 파일 고정 경로(`MODULE.parent`)로 교체.

### 코덱스 선결 (미수리)

| 항목 | 내용 |
|---|---|
| **F5** | 시드(seed) 하한을 강제하는 코드가 없음 — 단일 시드로도 캠페인이 PASS 판정을 받을 수 있음. |
| **F6** | 교락(confounding) 필드가 비교 대상에서 빠짐 — `memory_arm`·`contract_version`이 비교 누락, `max_tokens`·모델 digest는 애초에 payload에 실려 있지 않음(코덱스 스스로 인정한 사실). |
| **F7** | T3 미통과 시 캠페인을 막는 코드가 0건. 게다가 기존 캠페인 증거에는 모델 digest 자체가 없음. |
| F8 | 후원(donation) 히스토리 격리가 결정론 기반에서 프롬프트 의존으로 후퇴했고, 이를 검증하는 테스트가 구조적으로 항진명제(무엇을 넣어도 통과)임. |
| F9 | `matched_decoy`가 프롬프트 큐와 교락돼 있음. |
| F10 | `URLError` 발생 시 manifest가 아예 작성되지 않음. |

Minor(저위험, 기록만): `show_arc`/`broadcast_affect`가 동일 dict를 공유, `invented_handle` 접두 면제 조건이 과관대.

**우선순위 — R2 F5·F6·F7은 T3 신뢰의 필수 조건이다.** 인수인계 문서
(`AIRI-CODEX-HANDOFF-2026-08-21.md`)는 다음 세션이 baseline/E1/E2 36-report T3를
실행하도록 지시하고 있다. 그러나 comparator에 시드 하한이 없고(F5), 교락 필드를
비교하지 않으며(F6), T3 미통과 시 캠페인을 막는 코드가 없다면(F7) — T3가 "통과"로
나와도 그 통과가 실제로 의미하는 바를 신뢰할 수 없다. 즉 F5/F6/F7은 다른 선결
항목보다 먼저, T3 실행 전에 반드시 닫혀야 한다.

---

## 3. R3 — 학습 governance (sonnet)

**총평**: 트레이너·머지·GGUF 핀 체계는 견고하다는 것을 재확인했다(강화 확인 —
`queue_digest` EOL 안정화, 행동 적용기 큐 결속 정렬).

### 핵심 발견 — governance 위반 판정

continuity v2/v3/v4(합계 1,840행) 코퍼스가 `training_eligible: True`를 **합성
스크립트 내부의 자기선언**으로 부여받았다. 그 선언의 근거로 적힌 표식은
`"user_aggregate_feedback_2026-08-21"`이며, 이를 뒷받침하는 검증 가능한 승인
결속(사용자 승인 로그, 티켓, 별도 승인 문서 등)이 없다. 그런데도 이 표식을 근거로
**E1 QLoRA 학습이 이미 실행됐다**. 이는 인간 검수(governance)를 우회한 사례로 판정한다.

**완화 요인**: `adoption_authorized=false` / `t3_status=pending` 게이트가 전 구간
생존해 있어, 운영 채택으로 넘어가는 문은 아직 닫혀 있다.

**추가 증거(task-18)**: v2 코퍼스의 자체 감사 테스트
(`test_no_reference_identity_urls_pii_or_prior_target_overlap`)가 작성된 시점부터
red 상태로 커밋됐고, 그 이후 단 한 번도 통과한 적이 없었다. 원인은 테스트 자체의
glob 스코프 버그(자기 자신의 하류 파생물을 선행물로 오인)로 판명돼 이번 배치에서
수리했지만, "감사가 미통과 상태인 채로 자기선언 eligibility가 부여됐다"는 사실
자체는 수리 여부와 무관하게 성립한다.

### 선결 (미수리)

- eligibility 판정을 자기선언 문자열에서 **검증 가능한 게이트**(실제 승인 이벤트에
  결속된 조건)로 전환하거나, 전환 전까지는 E1을 미승인 실험으로 재분류할 것.
- v4의 review dict 투명성 보강.
- 독스트링에 적힌 보증 문구가 실제 코드보다 강하게 약속하는 부분(보증 약화)을
  문서로 승격해 명시할 것.

---

## 4. 즉시 수리 6커밋

| 커밋 | 요약 | 출처 |
|---|---|---|
| `32947e9` | training 데이터 개행(EOL) 핀 — `.gitattributes` 2줄 추가 + 58개 파일 CRLF→LF 디스크 정규화 | task-15 |
| `5f021b5` | 런처 `$Pid` 예약변수 셰도잉 수리(`$OwnerPid`로 개명) + CI 신규 테스트 6파일 배선 + comparator provenance 3필드 + CWD 의존 테스트 수리 | task-17 |
| `4a4847d` | SHA 어테스테이션 재핀 — CRLF 스머지 바이트로 박제됐던 `raw_sha256`을 LF 바이트 기준 재계산(4중 독립 검증으로 비트 단위 확증), v2 자체 감사 테스트 glob 스코프 버그 수리 | task-18 |
| `b8981f1` | F1(재사용 trace_id fail-soft + `trace_reused_id_resets` 카운터) + F2(시스템 프롬프트 방송 경로 게이트화, OFF 949자 바이트 복원) | task-16 |
| `d65134a` | 레포 전체 CRLF 908개 파일 정규화 + `.gitattributes` 포괄 규칙(`*.json`/`*.jsonl` eol=lf) + dry-run 스트리밍 `terminal` 키 누락 버그 수리 | task-19 |
| `889d4c2` | input_safety 정책 어테스테이션 3중 체인(정책→상수→픽스처) 재정렬, 코덱스가 추가한 `allowed_latin_tokens: "AI"` 변경은 되돌리지 않고 수용 | task-20 |

모든 커밋은 명시 경로만 `git add`했고 push는 하지 않았다(오케스트레이터 소관).

---

## 5. 최종 스윕

수리 6커밋 완료 후 전체 테스트 스윕: **eval 563 · training 201 · proxy 488 · 계약 13
= 1,265 passed, 0 failed.**

수리 대상이 아니라 판단해 **의도적으로 남겨둔** 사전 존재 결함 1건:
`ollama-proxy/input_screening_policy_ko.json`의 `POLICY_SHA256`은 `06d68e1`이
`allowed_latin_tokens`에 `"AI"`를 추가하기 이전 콘텐츠로 박제됐던 것을 task-20에서
재핀했다 — 이 항목은 위 표의 `889d4c2`로 이미 수리 완료 상태다.

---

## 6. 코덱스 선결 목록 (재개 전 필수 소화)

우선순위 순으로 정리한다. **R2 F5/F6/F7은 T3 실행 전 필수**(§2 근거 참조).

1. **R2 F5** — comparator 시드 하한 부재 (T3 신뢰 필수 조건)
2. **R2 F6** — 교락 필드(memory_arm·contract_version·max_tokens·모델 digest) 비교 누락 (T3 신뢰 필수 조건)
3. **R2 F7** — T3 미통과→캠페인 차단 코드 0건 + 캠페인 증거에 모델 digest 부재 (T3 신뢰 필수 조건)
4. **R1 F3** — 발화계약↔출력경계 탈동조(capability가 문장 수를 못 올림, 15개 call site가 B4c env만 봄)
5. **R1 F4** — receipt 3해시 정규화 3갈래 분기 + 목 없는 성공 경로 테스트 0건
6. **R1 F5** — `confirm_injected` 후 실패 시 쇼 300초 wedge
7. **R1 F6** — 202-pending 응답 미결속
8. **R1 F7** — trace 없는 중복 저널 억제 제거 (의도 확인 필요)
9. **R2 F8** — 후원 히스토리 격리 결정론→프롬프트 의존 후퇴 + 검증 테스트 구조적 항진
10. **R2 F9** — `matched_decoy` 프롬프트 큐 교락
11. **R2 F10** — `URLError` 시 manifest 미작성
12. **R3** — eligibility 검증 가능 게이트 전환(또는 E1 재분류) / v4 review dict 투명성 / 독스트링 보증 약화 문서화

Minor(R2): `show_arc`/`broadcast_affect` 동일 dict 공유, `invented_handle` 접두 면제 과관대.

---

## 7. 사용자 확인 1건 — continuity governance

**질문**: `training_eligible: True`의 근거로 코퍼스 합성 스크립트에 자기선언된
`"user_aggregate_feedback_2026-08-21"` 표식 — 이에 대응하는 **실제 사용자 승인이
존재하는가**?

- **존재한다면**: 그 승인의 근거(승인 시점·범위·문서 또는 대화 기록)를 이 문서 또는
  별도 governance 로그에 명시적으로 남겨야 한다. 현재는 코드 내부 문자열 외에
  추적 가능한 근거가 없다.
- **존재하지 않는다면**: E1은 미승인 실험으로 재분류해야 한다. `adoption_authorized=false`/
  `t3_status=pending` 게이트가 운영 채택은 막고 있으나, "학습에 투입됐다"는 사실
  자체는 게이트로 되돌릴 수 없으므로 governance 기록에 위반 사실을 명시적으로 남겨야 한다.

---

## 8. 함정 재발 기록 — CRLF 어테스테이션

이번 배치(task-15·18·19·20)에서 반복적으로 드러난 단일 근본 원인: **Windows
`core.autocrlf=true` 체크아웃에서 `.gitattributes`에 `eol=lf`로 고정되지 않은
텍스트 파일은 커밋 blob이 LF라도 디스크에는 CRLF로 스머지된다.** raw bytes를
`hashlib.sha256(Path.read_bytes())`로 직접 해싱하는 어테스테이션 핀은 이 스머지에
그대로 영향을 받는다.

이번 배치에서 실제로 발생한 두 가지 실패 양상:

1. **디스크가 CRLF, 핀은 LF 기준** — 로컬 실행 시 해시 불일치로 실패(task-15가 발견한
   58개 파일, task-19의 908개 전면).
2. **핀 자체가 CRLF 바이트로 박제됨** — 코덱스가 CRLF로 스머지된 워킹카피에서
   `raw_sha256`을 계산해 매니페스트에 박아넣은 경우, 오히려 **LF로 정규화한 디스크가
   핀과 불일치**하는 역설적 상황이 발생한다(task-18, 4중 독립 검증으로 확증 —
   CRLF로 되돌리면 핀이 비트 단위로 재현됨).

**재발 방지 원칙**: 어떤 raw-byte SHA 핀이든 계산·박제하기 전에 반드시 (1) 해당
경로에 `.gitattributes`의 `eol=lf` 규칙이 먼저 적용돼 있는지 확인하고, (2) 핀 계산은
항상 **LF 기준 blob 바이트**로 수행한다. 순서를 뒤집으면(핀을 먼저 박고
`.gitattributes`를 나중에 붙이면) 이번 배치와 같은 어테스테이션 결함이 재발한다.

---

## 부록 — 소스 리포트 매핑

| 태스크 | 내용 | 커밋 |
|---|---|---|
| task-15 | training EOL 핀 + 잔여 미커버 스캔 | `32947e9` |
| task-16 | R1 F1·F2 수리 | `b8981f1` |
| task-17 | R2 F1~F4 수리(런처·CI·provenance·CWD) | `5f021b5` |
| task-18 | SHA 어테스테이션 재핀 + v2 감사 glob 수리 | `4a4847d` |
| task-19 | 레포 전체 CRLF 908파일 정규화 + rehearsal 버그 수리 | `d65134a` |
| task-20 | input_safety 정책 어테스테이션 재정렬 | `889d4c2` |
