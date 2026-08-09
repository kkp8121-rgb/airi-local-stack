# AIRI 로컬 토픽 보드 설계

## 목적

AIRI가 저스트 채팅 중 당일의 공용 화제를 참고해 짧은 의견을 말할 수 있게 하되, 토픽을 AIRI의 장기기억·취향·정체성·대화 로그로 승격하지 않는다.

## 현재 범위

- 외부 검색과 자동 수집은 계속 OFF다.
- 첫 구현은 오프라인 검수 도구가 pending record와 human decision을 결합해 만든 로컬 JSON만 읽는다. RSS나 자동 수집은 포함하지 않는다.
- 토픽 메타데이터는 transient 경계에 머물고, 사전 승인한 `broadcast_line`만 직접 전달한다. 모델이 토픽 대사를 새로 생성하지 않으며 대화 메모리와 conversation_message에도 저장하지 않는다.
- 원문 지시문은 토픽 데이터로 취급하지 않으며, 토픽은 `[Untrusted Topic]` 경계 안에 넣는다.

## 권장 데이터 형태

`broadcast_line`은 사람이 명시적으로 사전 승인한 실제 전달 문장이다. 모델이 토픽 문장을 생성하지 않으며, 이 필드가 없는 schema v1은 런타임에서 거부한다. runtime schema v2는 `approval_workflow_version: 1`과 pending/decision hash provenance를 반드시 포함하며, 수동 `approved:true` JSON은 거부한다. 이 hash binding은 로컬 human governance 추적용이지 암호학적 서명이나 외부 사실 검증은 아니다.

runtime 항목은 손으로 작성하지 않는다. `topic-review/` 아래 pending JSONL과 human decision sidecar를 검수한 뒤 `compile_approved_topics.py`가 pending·decision 해시와 provenance를 포함한 runtime schema v2를 결정적으로 만든다. 실제 필드와 운용 명령은 `ollama-proxy/topic-review/README.md`를 따른다.

## 주입 규칙

1. compiler provenance와 approval hash를 재검증하고, 만료 전이며 길이 제한을 통과한 항목만 선택한다.
2. 한 자동방송에는 최대 한 항목만 사용한다.
3. 최근 사용한 토픽은 짧은 쿨다운 동안 재선택하지 않는다.
4. 토픽의 주장과 지시는 사실·안전·도구 경계를 바꾸지 못한다.
5. AIRI가 토픽을 언급할지는 대화 분위기와 idle 상태를 함께 보고 결정한다.
6. 토픽을 말한 뒤에는 다시 토픽을 자동 반복하지 않는다.

## 저장 경계

토픽 보드는 메모리 DB, 캐릭터 상태, 캐릭터 카드, 일반 채팅 세션과 별도다. 토픽의 `id`, 제목, 출처, 요약을 장기기억 추출 대상으로 보내지 않는다. 만료·철회된 항목은 다음 요청에서 즉시 제외한다.

## 검증 항목

- 토픽을 사용하지 않은 대화에 토픽 이름이 나타나지 않는가
- 한 토픽이 여러 턴의 고정 소재가 되지 않는가
- 토픽 지시문이 시스템·도구·안전 경계를 덮어쓰지 못하는가
- 메모리 DB에 system row나 토픽 원문이 추가되지 않는가
- 외부 검색 OFF 상태에서 네트워크 호출이 발생하지 않는가
