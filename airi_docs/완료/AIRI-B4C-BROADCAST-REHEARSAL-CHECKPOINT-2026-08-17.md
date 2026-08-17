# B4c 멀티턴 방송 리허설 로컬 체크포인트

날짜: 2026-08-17
상태: **오프라인 합성 흐름 회귀 편입 완료**
운영 상태: **B4c 전체는 부분 완료, 계약 기본 OFF 유지**

## 1. 이번 배치의 결론

기존 B4c 멀티턴 리허설을 CI 목록에만 두지 않고
`test-current-checkpoint.ps1`의 필수 로컬 회귀로 편입했다. 고정 fixture는
semantic JSON SHA-256
`aeb2bc2e8f74f6bd54a13eaf338ad48c288875b888b10ced430302fe906d96c8`로
핀하며, 순서가 고정된 `autumn_leaves`와 `game_and_career` 두 시나리오가
각각 정확히 24턴이어야 한다.

이 PASS가 뜻하는 것은 다음뿐이다.

- 합성 2시나리오 × 24턴의 순서·히스토리 cap·콜백 창 안/밖·여론 집계·후원
  호명 범위·이름 누출·주제 전환·존댓말 drift 계산 계약이 변하지 않았다.
- 주입형 오프라인 transport에서 48/48턴이 처리되고, 시나리오마다 콜백
  `in=1/out=1`, 현재 후원자 호명과 과거 후원자 이름 비누출이 확인된다.
- B4c 계약 OFF의 시스템 프롬프트 바이트가 기존 A/B 러너와 동일하다.
- Windows CP949 콘솔에서도 테스트 출력 때문에 거짓 실패하지 않으며,
  unittest가 최소 37개 실행됐는지 PowerShell이 확인한다.

## 2. content-free 체크포인트 증거 계약

`run_broadcast_rehearsal.py`에
`airi.broadcast-rehearsal-checkpoint-evidence.v1` projection/validator를
추가했다. 전체 실행 리포트를 redaction하지 않고 닫힌 필드만 새 객체로
투영한다. 다음은 남기지 않는다.

- 시스템 프롬프트·방송 frame·사용자 입력·모델 응답·오류 본문
- 파일 경로·endpoint·token/TLS 정보·후원자 이름

허용되는 것은 고정 fixture와 프롬프트의 SHA-256, 닫힌 config, 시나리오별
카운트·비율·분산뿐이다. 증거 validator는 다음을 fail-closed로 강제한다.

- `dry-midm`, 128 tokens, history 8, non-stream dry-run, exact full fixture
- ordered 2×24, 각 24/24 성공·실패 0, 전체 48/48 성공·실패 0
- finite rate, `hits <= denominator`, 반올림 산술, 시나리오→overall 합계
- 프롬프트 hash 재계산과 계약 OFF/ON별 contract block hash
- `synthetic_only=true`, network/model/proxy/B1b/TTS 모두 `false`

초기 독립 검토에서 빈 summaries, 음수 count, NaN rate, 위조 hash와 임의 model
문자열이 통과하는 차단점을 발견했다. 위 계약과 hostile regression을 추가한
뒤 동일 변형은 모두 `ValueError`로 거부됐고 최종 독립 재검토는 GO였다.

## 3. 검증

- `python -m unittest -v ollama-proxy\eval\broadcast_chat\test_run_broadcast_rehearsal.py`
  - **37/37 PASS**
- `python -m py_compile ollama-proxy\eval\broadcast_chat\run_broadcast_rehearsal.py ollama-proxy\eval\broadcast_chat\test_run_broadcast_rehearsal.py`
  - PASS
- `.\test-current-checkpoint.ps1`
  - PASS
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`
  - PASS

GitHub Actions는 billing 차단 상태이므로 이번 배치는 위 로컬 검증을 대체
증거로 사용했다.

## 4. 증명하지 않은 것

이 배치는 네트워크·Ollama·Mi:dm·11435 proxy를 호출하지 않았고 AIRI 앱,
B1b screened event 주입, B4a/B4b 라이브 어댑터, 스타일 게이트 public wire,
TTS, OBS, 실제 채팅, 장시간 실방송을 실행하지 않았다. 따라서 다음은 계속
미완료다.

- 첫 토큰 스트리밍과 원격 서버 `max_tokens` 정확 경계
- B1b→11435 스타일 게이트→public wire/TTS 동일 turn 실증
- B4b 어댑터와 승인된 비공개 30~120분 리허설
- 운영 `AIRI_BROADCAST_CONTRACT=on` 채택

운영 계약 ON과 파라미터 확정은 사용자 확인 전 자동 승격하지 않는다.
