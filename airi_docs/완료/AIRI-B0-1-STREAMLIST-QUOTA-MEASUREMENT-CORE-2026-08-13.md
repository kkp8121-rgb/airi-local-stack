# AIRI B0-1 streamList quota measurement core — 2026-08-13

## 판정

**오프라인 측정 코어는 완료, 라이브 B0-1 쿼터 판정은 NOT COMPLETE다.**

`chat-ingress/streamlist-quota.mjs`는 주입형 transport만 받는 content-free
측정 코어다. 실제 YouTube 연결, API key/OAuth, ChatIngress/AIRI 호출, provider
내용·ID 영속화는 하지 않는다. 이것은 B1b live adapter도 아니다.

## 구현 경계

- 정확한 shape만 받아 기간·메시지·응답·연결 수를 각각 bounded 한다.
- batch가 메시지 상한을 넘겨도 실제 관측 메시지 수를 보존한다.
- caller가 주입한 단조 시간으로 모든 timing을 기록한다.
- `nextPageToken`은 재연결 resume에만 쓰는 transient 값이며 결과에 남기지 않는다.
- deadline 및 caller abort를 지원하고, 열린 transport는 best-effort로 정리한다.
- 측정 결과는 content-free count/timing/connection 정보뿐이다. quota snapshot은
  수동으로 입력한 숫자 before/after만 기록한다.

검증은 focused 15 PASS, chat-ingress 전체 32 PASS, full checkpoint PASS,
독립 최종 검토 PASS다. 이 테스트 파일은 기존 checkpoint glob에 이미 CI 등록되어
있으므로 workflow 변경은 하지 않았다.

## 공식 API 사실과 해석 금지선

공식 `streamList` 문서는 TLS gRPC endpoint `youtube.googleapis.com:443`를
설명하고, request에 `liveChatId`와 `part`가 필요하다고 한다. 연결이 끊기면 마지막
`nextPageToken`을 다음 request의 `pageToken`으로 넘겨 resume할 수 있다.

- [LiveChatMessages.streamList 공식 문서](https://developers.google.com/youtube/v3/live/docs/liveChatMessages/streamList)
- [YouTube Data API Quota Calculator 공식 문서](https://developers.google.com/youtube/v3/determine_quota_cost)

Quota Calculator는 모든 request가 최소 1 quota point를 소비하며 Live Streaming
API도 quota를 소비한다고 명시한다. 그러나 이 페이지는 `streamList`의 연결당,
response당, 시간당 정확한 과금량을 열거하지 않는다. 따라서 이 문서나 코어의 수치로
그 비용을 추론하거나, polling `list`의 비용을 streamList에 전용하면 안 된다.

## 라이브 완료 전제

라이브 B0-1은 다음 명시적 승인 전까지 **NOT COMPLETE**다.

1. YouTube API key/OAuth, quota 및 Google Cloud project 사용 승인
2. 승인된 격리 test broadcast
3. Cloud Console의 수동 before/after quota snapshot으로 idle, message, reconnect를
   각각 측정

그 전까지 B1b, 실제 AIRI 주입, provider content/ID 저장, 설치 ASAR 또는 방송 런타임
변경은 범위 밖이며 STT/mic은 OFF/deferred를 유지한다.
