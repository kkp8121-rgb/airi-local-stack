# AIRI G1a A4.4 correction-target fresh A/B foundation

Date: 2026-08-17

Status: **implementation and offline review complete; fresh Mi:dm run and human review pending; operational gate FAIL/OFF**

## 목적

A4.2에서 고정 generic `correct`는 실제 교정 방향을 자주 잃었다. A4.3은 여덟 개 합성
`correct` 턴을 닫힌 target/direction에 결합했지만, 구조적 eligibility만 증명했다. A4.4는
그 target을 Mi:dm이 실제 대사에 반영하는지 새 응답으로 비교하기 위한 최소 실험 경계를
추가한다.

비교 조건은 다음 두 개뿐이다.

- control: 기존 affect snapshot + closed `reply_act=correct`
- target: control과 byte-identical인 요청에 closed correction-target 메시지 하나만 추가

대상은 pinned oracle의 정확한 8행이며, 실행 시 8쌍·16 POST만 만든다. 과거 A4.1 응답,
A4.2 선호 점수, 결정 시트의 사람이 쓴 예시 대사는 입력이나 판정에 사용하지 않는다.

## 합성 평가 전용 proxy seam

`ollama-proxy/broadcast_correction_target.py`는 정확한 8개 `(target_id, direction)` pair만
canonical JSON으로 수용하고, 각 pair를 고정 한국어 근거 문장으로 렌더한다. free text,
시청자 이름, 후원 금액, event ID, 외부 사실은 입력 필드에 없다.

proxy는 아래 조건을 모두 만족할 때만 이 메시지를 upstream에 보존한다.

1. 요청이 loopback peer의 exact `x-airi-turn-origin: local-evaluation`이다.
2. 기존 closed synthetic context와 affect snapshot이 유효하다.
3. 정확히 하나의 canonical reply-act가 있고 act가 `correct`다.
4. 정확히 하나의 canonical correction-target이 있다.

공백·ZWSP·NBSP·대소문자·key casing으로 reserved name을 흉내 낸 메시지, duplicate,
extra key, malformed candidate는 target 기능 전체를 no-op으로 만들며 raw candidate도 active
character card로 투영하지 않는다. ordinary/remote traffic에는 target이 주입되지 않는다.

## fresh blinded runner

`run_correction_target_ab_eval.py`의 기본 실행은 pinned cohort와 request delta만 검증하고
network와 파일 쓰기를 하지 않는다. `--execute`는 literal
`http://127.0.0.1:11435/api/chat`만 허용하고, proxy-disabled/no-redirect bounded transport와
frozen Mi:dm profile을 pre/post health로 확인한다.

- 8 control + 8 target = 16 model calls
- pair order는 정확히 CT 4개 / TC 4개이며 CSPRNG로 섞는다.
- row 실행 순서와 A/B label도 별도로 섞고 mapping은 ignored operator key에만 둔다.
- blinded packet에는 두 응답과 빈 검토 rubric만 있고 target ID/direction/arm mapping/seed가 없다.
- unblind 전에는 exact packet SHA-256에 결합된 완전한 locked review overlay가 필요하다.
- public report는 count, pinned source hash, profile/health hash와 normal CLI transport contract만
  기록하고 응답·target·mapping·선호 점수를 기록하지 않는다.

결과/키 저장은 Windows honest-local CLI용 ignored custody다. receipt는 report/packet integrity만
주장하며 same-account hostile-local race, path substitution/ABA, external transport authenticity는
명시적으로 범위 밖이다.

## 검증과 검토

- shared correction-target unit tests: PASS
- proxy synthetic-target focused tests: PASS
- A4.4 runner tests: 16/16 PASS
- full proxy suite: 311/312 PASS; 1건은 기존 Python 3.14 raw-watchdog metadata
  `upstream_response_headers_timeout` KeyError이며 변경 경로의 synthetic-target tests는 PASS
- `py_compile`: PASS
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`: PASS
- proxy seam 독립 공격 검토: name/key/Unicode variant raw-leak 두 차례 수정 후 **GO**
- runner 독립 검토: packet/execution/custody 결합 수정 후 Windows honest-local CLI 범위 **GO**
- CI: billing 차단으로 미실행; 새 unit tests는 기존 API/evaluations shard에 등록

## 아직 완료가 아닌 것

현재 로컬 11435와 Ollama가 내려가 있어 이 foundation 배치에서는 Mi:dm 16회 실측을 아직
수행하지 않았다. 따라서 target-aware가 실제로 더 자연스럽거나 정확하다는 결과는 없다.
다음은 reviewed foundation을 커밋한 뒤 stack을 올리고 새 run name으로 16회를 실행하고,
key를 열기 전에 packet-bound review를 끝내는 것이다.

이 seam은 합성 평가 전용이다. production event mapper, director/B4a/B4b, renderer fallback,
TTS/Live2D, operational affect/reply-act ON은 모두 변경하지 않았고 자동 승격하지 않는다.
