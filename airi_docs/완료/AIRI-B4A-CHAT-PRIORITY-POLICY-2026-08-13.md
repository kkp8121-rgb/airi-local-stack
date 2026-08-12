# AIRI B4a 채팅 우선순위 정책 완료 기록 — 2026-08-13

## 완료 범위

`broadcast-director/priority-policy.mjs`에 B1 screened event를 위한 순수·무상태·결정론적 우선순위 정책을 추가했다. 유효한 입력은 고정된 정확한 `{priority}`만 반환하고, 부적합 입력은 `null`을 반환한다. 우선순위는 질문, 화제 확장, 진심 리액션, 응원, 긍정 fallback 순서다.

정확한 B1 shape/ID/Unicode code point/timestamp를 엄격히 검증하고 descriptor snapshot을 적용한다. 유효한 텍스트의 최대 길이는 1,000자다. 이 모듈은 상태, I/O, 환경변수, 네트워크, 로그, 영속성 및 외부 의존성을 사용하지 않는다.

## 개인정보 및 분류 경계

결과에는 eventId, viewerKey, 이름, 텍스트, 시간이 포함되지 않는다. 사적 데이터에 대해 V8 legacy `RegExp.input`/`lastMatch`가 보존될 수 있다는 점검 결과에 따라, 매처는 수동 문자열 처리만 사용하며 RegExp를 사용하지 않는다. sentinel 회귀 시험은 해당 전역 상태가 변하지 않음을 확인한다.

한국어 우선의 보수적 휴리스틱으로 문장부호와 선택된 종결 질문형을 보며, 부정 표현 및 URL의 query punctuation은 가드한다. 이는 사람의 의도를 증명하는 분류기가 아니다. 오분류는 처리 순서만 바꾸며 이벤트를 버리거나 모더레이션하지 않는다. B3는 계속 모더레이션 책임을 가진다.

## 검증 및 미포함 범위

B1 ChatIngress → policy → B4 director composition을 정확한 경계로 시험했다. 로컬 broadcast 집중 시험은 **24/24 PASS**, 독립 combined ingress/policy/director 검토는 **36/36 PASS**였다. 두 수치는 서로 다른 시험 범위이므로 합산하거나 동일시하지 않는다. checkpoint는 policy 시험을 자동 발견한다. 변경은 JavaScript뿐이므로 전체 Python 재실행은 하지 않았다.

B4a/G5/M4는 여전히 partial이다. 런타임/live adapter, OAuth·quota·YouTube, AIRI sender/TTS/OBS, 비공개 2시간 리허설, 설치 ASAR은 추가·검증되지 않았고 STT는 OFF/deferred다. 외부·인간 승인 게이트도 남아 있다. 현 오프라인 범위를 점검한 결과, production-consumed 자율 오프라인 배치 중 바로 이어서 수행할 항목은 식별되지 않았으며, 다음 진행은 게이트된 B1b/B4b 또는 인간 주제·헌법 검토다. 이는 영구적 부재 주장이 아니라 현 시점의 감사 결론이다.
