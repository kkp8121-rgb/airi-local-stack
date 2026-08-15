# YouTube LIVE 실측 준비 자동화 — 2026-08-15

## 결과

공식 YouTube LIVE collector 실행 전에 필요했던 provenance SHA-256,
provider/channel/exporter/source-slot HMAC, authorization JSON, allowlist 항목의 수작업을
제거했다. `prepare_youtube_live_capture.py`는 운영자가 이미 확인한 권한 결정과 로컬
custody 파일을 strict ignored request로 받아 fresh per-capture bundle을 만든다.

이 도구는 방송을 검색하거나 YouTube에 연결하지 않고 API key·채팅을 읽지 않는다.
서면 권한의 발급자·진위·범위를 인증하거나 `authorized` 결정을 자동 생성하지도 않는다.
그 판단은 빈 체크박스로 시작하는 operator checklist와 실제 provenance 검수에 남는다.

## 입력과 출력

- request: `airi.youtube-live-capture-preparation-request.v1`
- 입력 파일: request, permission/provenance artifact, 32-byte 이상 local identity key
- 출력: `capture.authorization.json`, `provider-channel-allowlist.json`
- 출력 위치: 기존에 없어야 하는 ignored per-capture directory
- 비출력: API key, chat text, provider response, source/hash/HMAC report, shared allowlist

request/provenance/key는 resolved file identity가 서로 달라야 하며 hard-link alias도
거부한다. custody 경로는 `local-replay-intake/` 아래의 forward-slash 상대 경로만
허용한다. authorization/expiry/delete window는 준비 시각 기준 전체 30~120분을
덮어야 하고 `delete_by`는 30일을 넘을 수 없다. allowlist는 해당 캡처 하나만 담는다.

두 JSON은 sibling lock 아래 staging directory에 각각 fsync한 뒤 Windows-first
no-clobber `os.rename`으로 publish한다. rename 전 오류는 final bundle을 남기지 않으며,
rename이 성공한 뒤 directory fsync는 best-effort durability 확인으로만 취급한다.
다른 비협력 프로세스가 custody directory를 바꾸는 것은 보안 경계 밖이므로 실제
실행은 기존 계약대로 exclusive operator session에서 한다.

## 검증

- `python -m unittest discover -s ollama-proxy/eval/chat_replay -p 'test_prepare_youtube_live_capture.py' -v`
  — 10 PASS
- `python -m unittest discover -s ollama-proxy/eval/chat_replay -p 'test_*.py'`
  — 72 PASS
- `python -m py_compile ollama-proxy/eval/chat_replay/prepare_youtube_live_capture.py ollama-proxy/eval/chat_replay/test_prepare_youtube_live_capture.py`
  — PASS
- `.\test-current-checkpoint.ps1` — PASS

GitHub Actions는 기존 billing 차단이 계속되며 active Python 3.14에는 pytest가 없어
로컬 unittest와 checkpoint로 검증한다.

## 다음 실측

1. 운영자 소유 또는 명시 서면 승인된 현재 YouTube LIVE와 로컬 API key를 준비한다.
2. 권한·revocation을 다시 확인하고 opaque per-capture bundle을 생성한다.
3. collector를 30~120분 실행한 뒤 capture receipt와 함께 정규화한다.
4. 사람이 privacy 검수한 동일 capture를 Mi:dm epistemic OFF/ON으로 replay한다.
5. source별 최소 2국면과 결합 권한이 확보된 경우에만 3-source campaign을 집계한다.
