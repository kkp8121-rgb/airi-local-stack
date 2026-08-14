# 승인 실제 채팅 replay 분석 기반 후속 — 2026-08-15

상태: **오프라인 기반 완료 / 실제 세 채널 캡처·Mi:dm OFF/ON 실측 미완료**

## 이번 배치 결과

- `airi.authorized-provider-export.v1` strict safe envelope만 받는 offline
  normalizer를 추가했다. CHZZK/SOOP raw callback, YouTube resource, VOD/비공식
  historical payload는 받지 않는다.
- consent v2와 channel allowlist를 local-key HMAC-SHA256으로 provider, channel,
  exporter, provenance hash, 익명 source slot에 결합한다. 단순 channel/exporter
  SHA fingerprint는 report/receipt에 남기지 않는다.
- donation event는 event kind만 유지하고 본문·호명·금액·통화는 고정
  `[후원 이벤트]`로 폐기한다. header channel/exporter ID도 text redaction 대상이다.
- normalized JSONL, derived consent, content-free receipt를 ignored directory에
  파일별 atomic replace로 쓴다. replay CLI는 exact normalized bytes, slot/phase,
  provider binding과 event count의 receipt HMAC을 다시 검증하므로 receipt가 없거나
  일부 output만 남은 bundle은 모델 호출 전에 실패한다.
- report v2는 redaction 전 source-text repeat, rolling half-open 5초 window,
  inter-arrival p50/p95/max·rate, burst, duplicate/noise/eligible rate, bounded lexical
  signal과 adjacent signal pair, proxy fallback outcome을 원문 없이 집계한다.
- 일반 response fingerprint는 plain SHA가 아니라 domain-separated local-key HMAC을
  사용한다.
- ignored private review packet은 응답한 event뿐 아니라 skipped repeat/noise도 모두
  포함한다. 사람은 bounded expected-action/grounded/context/tone/privacy/epistemic
  label만 채우고, scorer는 source structural hash를 재검증한 뒤 confusion matrix,
  quality rate와 critical failure count만 일반 report에 남긴다.

## 의미 경계

- lexical signal은 질문부호·웃음 반복·정정 표지·강조 등의 표면 proxy다. 장난,
  감정, 화제 전환 또는 특정 방송인 스타일의 의미 판정이 아니다.
- selector precision/recall은 현재 offline replay harness의 `noise/repeat skip`을
  평가한다. B1b/B4a live priority 또는 AIRI의 실제 선택 성능 증거가 아니다.
- local HMAC/sidecar는 운영자가 제시한 파일과 channel scope의 일관성을 검증한다.
  permission 발급자를 인증하지 않으므로 모델 실행 전 사람이 서면 권한을 확인해야 한다.
- epistemic gate와 `AIRI_BROADCAST_CONTRACT`의 기본값은 바꾸지 않았다. runner는
  기대 ON/OFF 상태를 health에서 검증할 뿐 운영 설정을 변경하지 않는다.

## 로컬 검증

- chat replay/normalizer/human scorer focused: **23/23 PASS**
- epistemic-confidence focused: **11/11 PASS**
- `test-current-checkpoint.ps1`: **PASS**
- Python compile 및 `git diff --check`: **PASS**

현재 dev PC에는 pytest가 없어 CI evaluations shard와 동일 명령을 재현하지 못했다.
Python 3.14 `unittest`로 전체 eval 파일을 한 process에 묶는 비동일 시도는 기존
`test_airi_native_baseline` pinned-fixture 검사 1건이 실패했다. 이 배치가 수정한
chat replay 3파일은 package/cwd 두 호출 방식 모두 23/23 PASS다. 원격 Actions는
기존 billing 차단 때문에 실행 결과를 코드 검증으로 사용할 수 없다.

## 남은 실제 작업

1. 탬탬버린·아카네 리제·아이네 각각에 대해 방송인/플랫폼 서면 권한과 공식
   exporter 또는 사용자가 권리를 가진 broadcast export를 확보한다.
2. 채널별 서로 다른 국면을 최소 2개씩 safe envelope로 만들고, 자동 redaction 뒤
   사람이 privacy 검수한다.
3. 같은 normalized sequence를 Mi:dm의 epistemic gate OFF/ON에 각각 재생하여 private
   human review와 content-free score를 만든다.
4. critical epistemic/privacy failure 0을 확인한 뒤에만 운영 ON 여부를 사용자에게
   제안한다. 실제 문장·닉네임·채널명·고유 밈은 git 또는 학습 데이터에 넣지 않는다.
5. B1b 준비 후 `screened event -> 11435 proxy -> style gate -> public wire/TTS`에서
   같은 평가를 종단 재검증한다.
