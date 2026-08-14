# AIRI B4c dev PC 후속 검토 — 2026-08-14

## 판정

검토 PC 배치 `a84d6ed`와 직전 dev PC 자산 통합 배치를 최신 `main`
`b4a9f32`에서 함께 검토했다. 원격 실측용 11439 gateway는 최종 런타임이
아니라 `archived_not_deployed` 연구 증거이며, 현재 11437/11439 listener와
Tailscale Serve 규칙은 없다. 보존본은 hash-pinned 증거이므로 수정하지 않았다.

이번 후속의 결론은 다음과 같다.

1. 당시 gateway의 정확한 소스 계약은 **비스트리밍, `max_tokens=1..128`**이다.
2. B4 방송 모델 생성은 **exact loopback proxy `11435/v1`만** 허용해야 한다.
   현재 source patch의 정적 계약은 이를 만족하지만 B1b 실제 주입 종단 실증은
   아직 남아 있다.
3. B4a 후원 이벤트는 허용형 프롬프트가 아니라 명시적인 이름 호명 action을
   낸다. 실제 발화 강제는 이 action을 소비할 B4b adapter의 완료 조건이다.

`AIRI_BROADCAST_CONTRACT`는 계속 기본 OFF다. 파라미터 확정과 운영 ON 채택은
이번 배치에서 하지 않았으며 반드시 사용자 확인을 경유한다.

## 1. 원격 gateway 스트리밍·출력 상한

보존 소스
`airi_docs/evidence/source-archives/remote-model-test-rehearsal-20260814/ollama-proxy__eval__run_airi_remote_model_test_gateway.py`
는 다음을 명시한다.

- `stream`이 `false`가 아니면 `400 streaming is not supported`
- `max_tokens`는 정수 `1 <= value <= 128`
- 허용된 값은 Ollama `num_predict`로 전달하고 backend도 `stream:false`

따라서 원격 A/B에서 관측한 “128 허용·160 거부”의 미확정 구간
`128~159`는 소스 검토로 해소됐다. **당시 gateway의 정확 상한은 128**이다.
이는 폐기된 배포의 소스 계약이지 현재 살아 있는 원격 서비스의 실측 주장은
아니다.

결정 2의 “첫 토큰부터 점진 재생”을 다시 추진할 때는 retired 평가 gateway를
그대로 되살리는 대신 운영 후보 endpoint에서 다음을 새로 증명한다.

- 명시 승인된 endpoint·credential로 `stream:true`가 실제 SSE delta를 점진 전송
- 첫 delta TTFT와 완료 시간을 분리 기록하고 abort/연결 종료를 전파
- 그 배포의 output-token 상한을 별도 capability probe로 확인
- 실측값은 설정을 자동 변경하지 않고 사용자 채택 판단 자료로만 보존

## 2. proxy 스타일 게이트 방송 경로

canonical AIRI source patch
`airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch`는 proactive 방송
생성 provider를 loopback `11435`의 `/v1` 경로로 제한한다. 같은 patch의 시험은
raw Ollama `11434`, 잘못된 `/api` 경로, 원격 HTTPS provider를 거부한다. 이번
배치는 이 의미 marker를 `test-patch-manifest.ps1`에 추가해 byte/hash pin과 함께
checkpoint에서 보호한다.

proxy의 모델 출력 경계는 `normalize_korean_register` 치환 후 미해결 존댓말
문장을 drop하는 fail-closed 계약이다. 다만 현재 `local-proactive`의 승인 토픽
분기는 사전 검토된 `broadcast_line`을 직접 반환하므로, 11435 ingress를 지난다는
사실만으로 **B4c 모델 계약과 스타일 게이트가 실제 방송 모델 출력에 적용됐다고
주장할 수 없다**. 이 분기를 재설계하는 것은 이번 배선 확인 범위가 아니다.

B1b 실제 AIRI 주입 시 아래를 한 묶음으로 확인해야 로드맵의 라이브 항목을
완료 처리할 수 있다.

- screened B1 이벤트가 AIRI의 실제 모델 생성 요청을 만든다.
- 활성 chat provider base URL이 exact `http://127.0.0.1:11435/v1`이다.
- `11434`, retired `11439`, 임의 원격 provider로 바꾸면 fail-closed한다.
- proxy가 생성한 응답에서 치환 가능한 존댓말은 반말로 바뀌고 미해결 문장은
  public wire/TTS 전에 drop된다.
- 최종 텍스트와 TTS 재생까지 같은 turn 증거로 연결한다.
- 계약 ON 실증은 사용자가 ON 채택을 승인한 경우에만 추가한다.

## 3. B4a 후원 호명

멀티턴 결과의 후원 호명 `0/2`는 B4c 문구가 이름 사용을 허용만 하고 의무화하지
않은 결과다. B4a core의 즉시 action을 `donation_name_callout_request`로
명시해 future adapter가 검증된 `displayName`을 정확히 한 번 호명해야 하는 계약으로
좁혔다. 이 action에는 후원 메시지·금액·`viewerKey`를 싣지 않는다.

이름이 없거나 빈 문자열, 제어문자·bidi·비정상 Unicode, 길이 상한 위반이면
event 전체를 `invalid_event`로 거부한다. 이름을 추측·대체·임의 정제해 발화하지
않는다. 메시지 낭독과 reaction은 기존 deferred action으로 분리한다.

이 변경은 B4a 오프라인 계약의 명확화다. B4b adapter가 action을 실제 모델/TTS
지시로 소비하고 비공개 리허설에서 이름 1회 호명을 증명하기 전에는 운영 완료로
표시하지 않는다.

## 보존한 운영 경계

- 설치 ASAR와 canonical patch bytes는 변경하지 않았다.
- STT/마이크, 기억 추출, output moderation은 기존 OFF 경계를 유지한다.
- 외부 credential·모델 endpoint·Tailscale 규칙을 사용하거나 생성하지 않았다.
- CI billing 차단을 우회하거나 성공으로 해석하지 않는다. 로컬 검증만 근거로 쓴다.

## 로컬 검증

- `node --test broadcast-director/test-*.mjs`: **24/24 PASS**
- `stt/.venv/Scripts/python.exe ollama-proxy/test_broadcast_contract.py -q`:
  **21/21 PASS**
- `PYTHONUTF8=1 stt/.venv/Scripts/python.exe
  ollama-proxy/eval/broadcast_chat/test_run_broadcast_rehearsal.py -q`:
  **34/34 PASS**
- `test-current-checkpoint.ps1`: **PASS**
  (patch/source archive/entrypoint, synthetic ASAR, sender 32, chat-ingress 47,
  broadcast-director 24, latency dashboard 5; patch applicability는 명시적
  `-BaseCheckout`이 없어 기존 계약대로 inert SKIP)
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`: **PASS**

직전 자산 정리에서 Python 3.12 audit venv가 제거됐고 시스템 3.12에는
`pytest`/runtime dependency가 없어 Python core 전체 suite는 재구성하지 않았다.
이번 배치는 Python 코드를 변경하지 않았으며, 관련 55개 unittest는 남아 있는
서비스 venv(Python 3.11)에서 통과했다. CI는 billing 차단이 지속되므로 위 로컬
검증을 이번 커밋의 근거로 사용한다.
