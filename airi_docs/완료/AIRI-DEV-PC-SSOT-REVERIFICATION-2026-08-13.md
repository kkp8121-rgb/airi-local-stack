# AIRI dev PC SSoT 재검증 (2026-08-13)

## 판정

`main` 기준 `c916f485565d29396e1580f16a4d72236bb724f5`에서 설치 AIRI의 모델
SSoT를 다시 검증했다. 이 base에는 승인된 `22a6add`가 포함되고 PR #8은 병합됐다.
병합 순간 PR 문맥 run `31671561496`은 memory-store를 완료 중이었으나 이후 13/13
green으로 종료됐다. 병합 `main` push run `31671652918`과 해당 branch의 최종 run
`31668787730`도 각각 13/13 green이다. 이번 문서 배치 CI는 이 문서 커밋 뒤의 별도
근거다. 코드·기본 digest pin·기존 테스트는 이미 일치하여 변경하지 않았다.

설치 `app.asar`는 1,356,257,019 bytes,
`1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`였다.
source SDK root는 `C:\Projects\airi-tts-resampler-staging-20260813b`다. 이 SDK의
commit/tree는 `bf173f2de870e3f779db02548d691c7b51bb290f` /
`ff71039caa507c5676c2cee31125374c5cc37d35`이고 clean이며, 설치 앱은 이 source
root로 `stageMounted=true`였다. 개인 서버 토큰은 기록하지 않았다.

내용 없는 구조화 증거는
`evidence/AIRI-DEV-PC-SSOT-REVERIFICATION-2026-08-13.json`에 고정했다. 파일은
5,533 bytes, SHA-256
`889501204046A7E01BBB6E0B138B16B34FC18481038243C58F74EAAE713607C8`이며 JSON
parse를 통과했다.

## 선행 정리와 경계

실행 전 죽은 parent와 정확한 Ollama 실행 파일을 확인한 뒤 orphan `llama-server` PID
5개를 제거했고 `/api/ps`는 0이었다. 이는 공개한 선행 정리일 뿐 제품 PASS 근거가
아니다. 외부 provider는 비활성화했고 raw content, token, session/id, audio는 보존하지
않았다.

## Mi:dm 기준 경로

- Mi:dm digest:
  `92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f`.
- STT OFF, extraction false, evaluation 및 character evaluator true, moderation OFF,
  `num_ctx=2048`, `num_gpu=999`로 기동했다. 런처는 warmup 200, Mi:dm pin,
  evaluator Mi:dm, TTS OK/reference found를 보고했다.
- 실제 설치 Electron server-channel sender는 chars 27, `completed=true`,
  `completed_ms=1079`, assistant chars 11을 기록했다. 이후 health는
  `normalized_requests=1`, `last_requested_model=exaone-airi:2.4b`, evaluator OK였다.
  `ollama ps`는 Mi:dm 단일 runner, 100% GPU, context 2048이었다. 로그에는
  `chat_model_digest` pinned verified와 `chat_model_ssot` normalized가 있었다.
- 승인된 임시 export의 provenance `model`/`model_version`은 모두 Mi:dm이었고,
  임시 record 삭제도 확인했다.

## EXAONE 롤백 경로

Mi:dm을 unload한 뒤 EXAONE을 unpinned로 기동해 관측했다. EXAONE digest는
`ec47936ec5439ea3c24bbdd069b3a7aeba5cd8100ab193367bd959fac679bde4`다. 런처는
warmup 200 및 evaluator EXAONE을 보고했고, Electron sender는 chars 30,
`completed=true`, `completed_ms=1103`, assistant chars 11이었다. health는 matching 2,
evaluator OK, `ollama ps`는 EXAONE 단일 100% GPU/context 2048이었다. provenance의
두 필드도 EXAONE이었고 임시 record를 삭제했다.

## 실패 폐쇄와 복원

Mi:dm digest 마지막 글자를 `...85e`로 바꾼 기동은 다음 content-free 오류로 차단됐다:
`Local chat model 'midm-airi:2.0-mini' does not match the expected artifact digest.`
이때 11435 false,
8880 false, runner 0, AIRI hidden process 7개는 유지됐다.

마지막으로 Mi:dm 정확한 pin+verified 상태로 복원했다. 단일 runner digest는 위 Mi:dm
값과 일치했고 VRAM은 1,869,464,206 bytes, context 2048이었다. evaluator/evaluation/
extraction/moderation은 OFF다. Python STT 8890과 Electron voice input을 모두 OFF로
복원했고 passive status에서 recording/transcribing 및 VAD active/listening/inputLive/
inputEnabled가 모두 false였다. Electron 설정 복원에 사용한 임시 CDP는 loopback에서만
열고 닫은 뒤 CDP 없이 재기동해 9223 false를 확인했다. TTS OK/reference found/cache
7/7, AIRI hidden process 7개 및 loopback 6121 true도 확인했다.

## 오프라인 회귀 검증

- CPython 3.12.13 `python -m unittest -v test_midm_model_configuration.py`:
  17/17 PASS.
- `./test-current-checkpoint.ps1`: PASS.
- 구조화 증거 JSON parse·고정 SHA 재검증, patch 변경 0, `git diff --check`:
  PASS.

## 후속 상태 결정 (2026-08-13)

사용자 결정으로 이 배치의 완료 조건은 **로컬 실기 배치 완료**이며, push/CI green은
더 이상 요구하지 않는다. 저장소는 계속 private이고 public visibility 변경도 하지 않는다.
아래 Actions 실행 사실은 역사 기록으로 그대로 보존한다.

## 원격 CI 차단 (역사 기록)

증거 커밋 `e694b4f651a57fa2a2b138c85910b5f5a664607b`의 push run
`31673311636`과 마이크 OFF 복원 커밋
`a42b5e9439c39bffda1abab7f61e37453032f0c4`의 push run `31673428754`는 각각
13개 job 모두 runner를 배정받기 전에 실패했다. 모든 job은 `runner_id=0`, steps 0이고
annotation은 최근 계정 결제 실패 또는 spending limit 증액이 필요하다는 동일한
GitHub Actions billing 오류다. 이는 코드나 테스트 assertion 실패가 아니다. 현 사용자
결정에서는 이 billing 차단을
해소하거나 workflow를 재실행할 필요가 없으며, push도 사용자가 요청할 때까지 하지
않는다(이 배치 시점 기준 — 이후 검토 인수를 위해 브랜치가 push됐다).

## 결론

설치 Electron 정규화, 단일 foreground runner, Mi:dm pin, EXAONE unpinned rollback,
evaluator·export provenance 및 불일치 digest fail-closed가 현 `main`에서 다시
성립한다. 이는 2026-08-12 증거를 대체하지 않고 그 후속 재검증이다. 실기 gate는
PASS이며, 후속 읽기 전용 점검에서도 설치 ASAR와 런타임 기본값은 변경하지 않는다.
