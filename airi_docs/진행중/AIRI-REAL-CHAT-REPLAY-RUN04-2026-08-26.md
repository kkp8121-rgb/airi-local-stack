# AIRI 실제 채팅 재생 run 04 결과 (2026-08-26)

> 첫 실제 시청자 채팅 재생. 입력은 공개 치지직 저스트 채팅 VOD 1편의 채팅 리플레이를 HMAC 가명화한
> 것이며(원본·표시명은 저장소 밖), 출력은 운영 구성(stock Mi:dm 2.0 Mini Q4 + 결정론 계층 + handle
> guard + 브리핑 + live broadcast + memory ON)이 만든 응답이다. **사람 채점은 아직 없다.** 아래 점수는
> Claude의 1차 참고 채점(rater `claude-preliminary`)이며 계약상 채택 게이트가 아니다.
> 산출물 root: `D:\AIRI-Models\airi-human-eval\20260826-replay-04\`(저장소 밖) — `report.json`,
> `packet.md`, `review.jsonl`, `rating-sheet.html`, `ratings-claude-preliminary.json`,
> `summary-claude-preliminary.{json,md}`, `health-before/after.json`, `runner.exit-code.txt`(0 아님:
> packet 렌더러 KeyError로 exit 1이었고 report는 완성; 렌더러 수정 뒤 packet 재생성 — 아래 §4).

## 1. 실행 receipt

| 항목 | 값 |
|---|---|
| 입력 | `chzzk-12901656.jsonl` 가명화 6,127행 중 앞 1,500건(스트림 시작 후 약 24분), `--max-turns 100` |
| 픽업 | 99턴 응답 + 입력 스크리닝 차단 1턴(profanity) = 100 픽업; kind: donation 35 · question 56 · reaction 8 |
| 프록시 health | deterministic_utterance_layer true, handle_grounding_guard true, broadcast_contract true, num_ctx 4096, memory enabled, chat_model `midm-airi:2.0-mini` digest `92a9ba2e…485f` pinned·verified |
| 채점기 자동 지표 | service_error 0, fallback 1/99, polite_violation 0, invented_handle 0, topic_anchored 51.5%, chars p50 10 / p95 93 |
| 실패 이력 | run 01 러너 인터프리터(httpx 없음) / run 02·03 실제 채팅의 스크리닝 차단을 러너가 치명 처리 → `f408eb7`로 재생 모드에서만 `screened` 기록·계속 |
| 종료 | 스택 stop, owned listener 0 |

## 2. Claude 1차 참고 채점 (99턴, 5축 1~5)

| 축 | 평균 | 중앙값 |
|---|---:|---:|
| 방송다움 | 1.89 | 2 |
| 맥락 유지 | 1.85 | 2 |
| 반응 적절성 | 1.99 | 2 |
| 말투 규칙 | 4.03 | 4 |
| 사실성 | 3.99 | 4 |

플래그: `silence_or_filler` 44.4%, `critical_failure` 3.0%(후원 본문의 성희롱성 문장을 축자 인용한 3턴),
`invented_name` 0, `polite_violation` 0. 5축 모두 ≥4인 턴 2.0%.

## 3. 패턴 (실제 방송에서 그대로 나타날 것)

1. **"고마워." 붕괴(23턴, 전부 모델 출력)**: 후원 35턴의 thank 렌더러+P5 echo가 history 8턴을
   감사 문장으로 채우자, 이후 질문에 모델이 "고마워."만 답한다. 되먹임 사본(Task 13)이 이름은 지우지만
   감사 문형은 그대로 남기는 것이 원인.
2. **P5 후원 echo의 축자 인용**: 후원 본문과 공유 토큰이 없으면 본문을 40자까지 인용해 "이렇게 보내 줘서
   진짜 고마워!"를 붙인다. 실제 후원 본문에는 원 방송 맥락·농담·성희롱이 섞여 있어 그대로 읽는 것이
   부적절하며, 35턴 중 대부분이 같은 문형이라 형식적이다.
3. **따라 말하기**: 짧은 반응("둥하", "롤체?", "얼엑?")에 시청자 말을 되풀이하거나 되묻기만 한다.
4. **원 방송 맥락 의존**: 시청자 메시지의 상당수가 원래 스트리머(둥그레)의 상황을 전제한다. AIRI에게는
   맥락이 없어 무난한 대꾸 이상이 나오기 어렵다 — 이 축은 데이터 한계이며 채점 시 코멘트로 분리한다.
5. 잘 된 턴(약 15턴): 짧은 질문에 반말로 직접 답하거나 받아치는 경우(예: 명치/스트레칭/일정 취소 반응).

## 4. 이번 run에서 고친 것 / 남은 것

- 고침: 재생 모드 스크리닝 차단 처리(`f408eb7`), packet 렌더러 `screened` 항목.
- 남은 결정(사용자): (a) 사람 최종 채점 — `rating-sheet.html`을 열어 채점 후 JSON 내보내기 → `summarize_ratings.py`;
  (b) 다음 개선 후보 — 후보 1: thank 렌더러/P5 echo의 되먹임을 history에서 제거하거나 echo를 인용 대신 요약형으로
  바꾸기(결정론 계층), 후보 2: 후원 본문 인용 전 출력 모더레이션 적용, 후보 3: 짧은 반응 턴의 되묻기 억제.
  파인튜닝은 여전히 대상이 아니다.
