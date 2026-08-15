# YouTube LIVE 채팅 승인형 수집 기반 — 2026-08-15

## 결과

장시간 채팅 replay의 실제 입력을 만들 수 있도록, 현재 진행 중인 YouTube LIVE
방송을 공식 API로만 읽어 `airi.authorized-provider-export.v1` safe envelope로
최소화하는 collector를 구현했다. 이 배치는 합성 provider 응답으로 계약을
검증했으며 실제 시청자 채팅, 채널 ID, API key, 권한 문서는 수집하거나 저장소에
기록하지 않았다.

파일:

- `ollama-proxy/eval/chat_replay/collect_youtube_live_export.py`
- `ollama-proxy/eval/chat_replay/test_collect_youtube_live_export.py`
- `ollama-proxy/eval/chat_replay/youtube-live-capture-authorization.schema.json`
- `ollama-proxy/eval/chat_replay/authorized-live-capture-receipt.schema.json`

## 고정 계약

- 입력은 현재 LIVE 방송 하나와 그 방송을 특정하는 로컬 승인 문서다. 종료된 VOD
  chat replay, player scraping, 비공식 endpoint, CHZZK/SOOP raw callback은 받지 않는다.
- 승인 근거는 `creator_or_platform_written_permission` 또는
  `operator_owned_broadcast`만 허용하고, permission artifact의 실제 SHA-256과
  provider/channel/exporter/source slot HMAC을 확인한다.
- 승인·만료·삭제 시각은 요청한 30~120분 전체를 덮어야 하고, YouTube API-key
  데이터의 `delete_by`는 시작 후 30일을 넘지 못한다.
- `videos.list`에서 exact video/channel과 `activeLiveChatId`를 확인한 뒤
  `liveChatMessages.list`의 page token과 polling interval을 따른다. 시작 전 history는
  제외한다.
- 저장 필드는 event timestamp/type/text뿐이다. author details, provider message ID,
  display name/profile, donation wording/amount, page token, API key, raw provider error는
  저장하지 않는다. 후원·system event는 본문 없는 의미만 보존한다.
- transport는 HTTPS official origin, no proxy, no redirect로 고정했다. 전체 구간 중
  revocation/expiry/abort/live end/unsafe Unicode/time regression/event·byte·batch 상한
  위반은 fail-closed다. wall clock과 monotonic 시작점을 setup 전에 함께 고정하며,
  승인 구간 종료 timestamp 이후 event는 safe envelope에 넣지 않는다.
- safe envelope·derived consent v2·content-free receipt를 모두 stage한 뒤 교체하고
  일반적인 쓰기 실패는 rollback한다. 세 독립 파일 교체는 전원 차단까지 전역
  atomic할 수 없으므로 collector 전용 `airi.youtube-live-api-minimized.v1` source
  schema는 downstream normalizer가 capture receipt를 필수로 받아 exact export와
  canonical consent를 함께 HMAC 검증한다. receipt 누락·불일치·변조 bundle은 읽지 않는다.

## 검증

- `python -m unittest -v ollama-proxy/eval/chat_replay/test_collect_youtube_live_export.py`
  — 9 PASS
- `python -m unittest discover -s ollama-proxy/eval/chat_replay -p 'test_*.py' -v`
  — 62 PASS
- `.\test-current-checkpoint.ps1` — PASS (offline synthetic contract)
- 실측 네트워크 요청: 없음

GitHub Actions는 기존 billing 차단이 계속되어 로컬 회귀로 대체한다.

## 남은 실측

1. 권한 있는 YouTube LIVE 방송과 로컬 API key/permission artifact를 준비한다.
2. 서로 다른 익명 source 3개에서 최소 2개 국면씩 연속 30~120분·300~20,000 event를
   수집하고 사람이 privacy 검수한다. 플랫폼/권한상 세 source 결합이 허용되지 않으면
   먼저 source별 진단으로 분리한다.
3. 동일한 exact capture를 Mi:dm epistemic gate OFF/ON으로 replay하고 private human
   review와 content-free campaign aggregate를 만든다.
4. 운영 gate ON 채택은 결과 뒤 사용자 확인을 거치며 자동 승격하지 않는다.

공식 근거:

- https://developers.google.com/youtube/v3/live/streaming-live-chat
- https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list
- https://developers.google.com/youtube/v3/docs/videos/list
- https://developers.google.com/youtube/terms/developer-policies
