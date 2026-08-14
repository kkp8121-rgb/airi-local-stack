# AIRI 장시간 채팅 replay 최대 경계 및 실행 상한 — 2026-08-15

상태: **오프라인 실행 경계 완료, 승인 실제 채팅 campaign 미완료**

## 이번 배치에서 고정한 것

- strict 승인 provider envelope 20,000 event를 정확히 120분 시간축으로 만들고,
  normalizer → derived consent → importer → fixed 5초 sampler → bounded responder
  callback 전체 경로를 실제 회귀 테스트로 통과시켰다. 일반 report는 64 KiB보다
  작으며 원문·응답문·채널 식별자를 보존하지 않는다.
- 후원 본문이 모두 `[후원 이벤트]`로 폐기되는 privacy 계약 때문에 서로 다른 후원
  event가 전역 exact-repeat로 합쳐지던 결함을 수정했다. 후원 callout은 각 event를
  별도·eligible로 유지하고, 일반 채팅 exact-repeat와 system noise 억제는 유지한다.
- 모델 opt-in은 첫 health 요청 전에 300~20,000 event, 연속 30~120분,
  sampler 선택 1~1,441건을 검사한다. campaign 증거는 기본값 1,441 call과
  7,200초 실행 상한만 허용하며 runner가 gate 상태나 운영 파라미터를 바꾸지는 않는다.
- loopback transport는 환경·Windows HTTP proxy를 사용하지 않고 redirect를 거부하며
  health/model body를 각각 64 KiB로 제한한다.
  남은 실행시간을 각 작업 timeout에 반영하고 body chunk마다 monotonic deadline을
  재확인한다. 이는 협조적인 로컬 peer에 대한 전체 상한이며, 임의 peer를 프로세스
  수준에서 강제 중단하는 hard cancellation 계약은 아니다.
- assistant response는 1~4,000자, complete-pair history는 6,000자, 직렬화 request는
  12 KiB로 제한한다. private packet은 96 MiB를 넘으면 atomic replace 전에 거부하며
  scorer도 같은 상한을 사용한다. private packet 검증/저장 실패 뒤 일반 report만
  남는 순서를 제거했다.
- campaign의 frozen runtime profile은 정수와 bool을 JSON 타입까지 정확히 검사한다.
  `0 == false`, `8 == 8.0` 같은 Python 비교 호환값은 증거로 받지 않는다.

## 외부 자료 조사 결론

- LiveChatBench는 약 3천만 SOOP 한국어 raw chat, 약 150만 synthetic pair,
  1,000개 한영 benchmark를 기술하지만 논문/OpenReview에는 공개 예정이라고만 적혀
  있다. 2026-08-15 현재 공식 GitHub, Hugging Face, Zenodo, OSF artifact와 재사용
  라이선스를 확인하지 못했다.
  https://openreview.net/forum?id=3DgbiMKhM0
- SIGDIAL 2024 자료는 28개 replay, 20,514개 5초 batch, 평균 11.91 chat/batch의
  장시간 selection 설계를 제공하지만 원문은 일본어이고 공개 dataset artifact를
  확인하지 못했다. 현재 sampler의 구조 참고 근거일 뿐 한국어 실제 campaign 입력이
  아니다. https://aclanthology.org/2024.sigdial-1.16/
- YouTube의 종료 live chat replay UI는 공개 시청 표면이지 공식 과거 로그 export가
  아니다. 공식 API는 종료된 chat을 `liveChatEnded`로 거부한다. 따라서 공개 VOD의
  동적 화면을 비공식 scraping해 부족한 corpus를 채우지 않는다.
  https://support.google.com/youtube/answer/9826490?hl=en
  https://developers.google.com/youtube/v3/live/docs/errors

## 검증

- `python -m unittest discover -s ollama-proxy/eval/chat_replay -p 'test_*.py' -v`
  — 52 passed
- `python -m py_compile` — 변경 Python 모듈 통과
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'` — 통과
- `.\test-current-checkpoint.ps1` — PASS

GitHub Actions는 billing 차단이 계속되어 실행 결과가 없으며 위 로컬 검증으로
대체했다.

## 남은 완료 조건

코드 최대 경계는 준비됐지만 목표 campaign은 아직 실행되지 않았다. 권한이 확인된
세 익명 source에서 각각 서로 다른 두 국면 이상을 30~120분·300~20,000 event로
준비하고, privacy 사람 검수 후 동일 exact capture를 Mi:dm gate OFF/ON으로 재생해야
한다. 이어서 private human review와 content-free paired aggregate의 critical failure
0을 확인한다. gate ON 운영 채택은 별도 사용자 확인 전 자동 승격하지 않는다.
