# 장시간 실제 채팅 replay sampler 기반 — 2026-08-15

상태: **오프라인 장시간 실행 계약 완료 / 승인 실제 장시간 캡처·Mi:dm OFF/ON
실측 미완료**

## 사용자 범위 고정

평가 대상은 방송인의 음성이나 말투 모사가 아니라 장시간 방송 다시보기 또는
스트림에 시간순으로 나타나는 시청자 채팅과 AIRI 대응이다. 세 개 공개 예문은
연결 smoke일 뿐이며 완료 근거로 세지 않는다. 실제 campaign은 익명 source 3개,
source마다 서로 다른 국면 2개 이상, 캡처마다 연속 30~120분·300~20,000 event,
동일 capture의 epistemic OFF/ON 한 쌍을 요구한다.

## 구현 계약

1. `offline_fixed_5s_response_sampler_v1`은 방송 시작 기준 half-open 5초 창마다
   eligible event를 최대 1개만 고른다. 질문·후원을 우선하고 제한된 정정·강조·
   웃음·최근 선택 chat lexical signal만 사용한다. threshold 미달 창은 no-reply다.
2. 선택되지 않은 event도 report 구조, 흐름, 반복, 잡음, private review packet에
   모두 남는다. 실제 model history와 response HMAC에는 선택된 event만 들어간다.
3. report v3의 `response_sampling`은 선택 원문/seq 없이 batch·candidate·no-reply·
   eligible·selected 수와 bounded reason count만 기록한다.
4. private scorer는 packet의 모든 event로 sampler를 다시 실행해 summary와 실제
   delivered/response seq가 정확히 같은지 확인한다. 서명만 다시 만든 허위 summary,
   한 5초 창의 복수 응답, 임의 outcome은 거부한다.
5. campaign validator는 OFF/ON이 같은 event seq를 골랐는지, report/score/run HMAC,
   exact capture, Mi:dm digest/profile/history, flow 파생 비율, 30~120분·300~20,000
   경계를 모두 fail-closed 검증한다. 운영 gate 채택은 계속 자동 승격하지 않는다.

이 sampler는 장시간 offline harness를 실행하기 위한 임시 선택 정책이다. 실제 B1b
live selector 또는 B4a 의미 선택 성능으로 부르지 않는다.

## 외부 근거와 smoke 경계

- SIGDIAL 2024 연구는 28개 replay, 20,514개 5초 batch, 평균 11.91 chats/batch에서
  한 응답 후보 또는 no-reply를 고르는 장시간 문제를 다뤘다.
  https://aclanthology.org/2024.sigdial-1.16/
- LiveChatBench 논문은 허가 아래 수집한 실제 한국 SOOP chat을 기술한다. 공개된
  예문 3개로 Mi:dm OFF/ON 연결만 확인했으며 gate block은 0이었다. 이는 한국 채팅
  slang/근거 없는 일반 동의 응답을 드러낸 smoke이지 장시간 실측이 아니다.
  https://arxiv.org/abs/2601.02641
- YouTube의 공개 chat replay UI는 종료된 chat의 공식 API export와 다르다.
  https://support.google.com/youtube/answer/9826490?hl=en
  https://developers.google.com/youtube/v3/live/docs/errors

## 검증

- `python -m unittest discover -s ollama-proxy/eval/chat_replay -p 'test_*.py'`
  — **42/42 PASS**
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'` — **PASS**
- 핵심 회귀: 4,999/5,000ms 경계, 창당 최대 1개, neutral no-reply, 구조-only와
  model-run 구분, OFF/ON 선택 seq 동일, 29:59/30:00·120:00/120:00.001,
  299/300 event 경계, sampler 재계산, HMAC/flow 변조 거부.

## 남은 실제 작업

1. 권한이 확인된 한국 장시간 저챗 source 3개의 safe envelope를 확보한다.
2. 각 source의 연속 30~120분 국면 2개 이상을 정규화하고 사람 privacy 검수한다.
3. 같은 exact capture를 frozen Mi:dm profile에서 epistemic OFF/ON으로 재생한다.
4. 모든 selected response를 사람이 검토하고 content-free paired report를 집계한다.
5. 실제 B1b가 준비되면 `screened event → 11435 proxy → style gate → public wire/TTS`
   종단에서 다시 검증한다.
