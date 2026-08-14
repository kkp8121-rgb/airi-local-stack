# AIRI B4a 방송 디렉터 기반 — 2026-08-13

## 판정

B4a `broadcast-director/`의 오프라인·결정론적 기반 코어와 README·집중
테스트를 추가했다. 기본값은 **OFF/inert**이며, Node 내장 모듈만 사용한다. 이
코어는 I/O, 타이머·시계, 환경변수, 로그, 네트워크, 파일, 영속성을 사용하지
않는다. 시간은 호출자가 제공하는 단조 `nowMs`만 입력으로 받는다.

집중 테스트는 **17 PASS**, 독립 최종 검토도 **PASS**다. 이는 시뮬레이션
계약의 증거일 뿐 실제 2시간 비공개 방송, 무오디오 공백, YouTube 채팅
지연·쿼터·OAuth, 런타임 어댑터, AIRI sender/TTS/OBS, 외부 killswitch 연동,
실제 모더레이션을 입증하지 않는다. 설치된 ASAR 변경도 없다.

## 구현 계약

- 2시간은 20분 블록 6개다. 각 블록은 0~30초 오프닝, 30초~15분 전개,
  15~20분 마무리로 나뉜다. 첫 블록 시그니처 여부는 boolean만 다루며,
  마지막 블록은 Q&A·감사·다음 방송 예고·완료를 포함한다.
- 질문은 하나씩만 내며 닫힌 질문:열린 질문은 3:2다. 정확히 12초를 기다리고,
  해당 시점에 채팅이 있으면 자문자답을 억제한다. 침묵 사다리는 설정된 임계값마다
  What→How→Why 나레이션, 승인 토픽 lease, 양자택일 질문 순서이며 기본 임계값은
  잠정 60초다.
- B1의 screened event는 정확히 하류로 전달하되 우선순위 분류는 별도다. 허용된
  채팅은 모두 bounded queue로 수용하며, 우선순위는 질문 > 토픽 확장 > 진심
  > 응원 > 긍정, 같은 우선순위는 FIFO다. backpressure는 명시하고 조용한 drop은
  없다. `viewerKey`·통계 상태는 emit하지 않고 원시 provider ID도 없다.
- 후원은 즉시 `donation_name_callout_request`를 내며 검증된 `displayName`을
  정확히 한 번 호명하는 것이 future adapter의 MUST 계약이다. 이름이 없거나
  안전하지 않으면 event 전체를 거부하고 이름을 추측하지 않는다. 금액은 다루지
  않으며, 읽기는 one-shot seam 또는 클로징에 이연하고 리액션 요청은 분리한다.
- 승인 토픽은 내용이 아닌 opaque lease seam만 다룬다. 활성 토큰은 유일하며
  ABA 안전, delivered terminal status와 teardown release 계약을 가진다.
- pause/resume, kill/close, inflight 1건 재생, frozen output, 내용 없는 통계,
  bounded live queue·recent LRU, strict shape·Unicode 검증을 제공한다.

## 경계와 다음 단계

압축 deterministic rehearsal은 **simulation only**다. B4a는 G5/B4 구현 기반의
부분 완료이며 M4, B5 또는 실제 방송 구현 완료가 아니다. 다음 작업은 외부
자격증명·B1b가 계속 막힌 상태를 유지한 채 B4b 런타임 어댑터와 승인된 비공개
리허설을 별도 권한·실측으로 진행하는 것이다. STT는 OFF/deferred를 유지한다.

2026-08-14 후속에서 위 이름 호명 action을 명시하고 집중 suite 24/24 PASS를
확인했다. 실제 모델/TTS가 이름을 한 번 호명하는 증거는 B4b adapter 이후의
비공개 리허설 게이트다
(`완료/AIRI-B4C-DEV-PC-FOLLOWUP-2026-08-14.md`).
