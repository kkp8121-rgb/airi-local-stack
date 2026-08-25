# AIRI 사용자용 로드맵 대시보드 공통 계약

이 문서는 Codex와 Claude Code가 함께 따르는 단일 원본이다. 두 프로젝트 skill 진입점은 이
문서를 참조만 하며 상태표·계산식·heartbeat 절차를 복사해 관리하지 않는다.

## 1. 적용 범위와 권위

다음 요청에 적용한다.

- AIRI의 현재 목표·단계·정지 사유·다음 작업 설명
- `AIRI-ROADMAP-STATUS.md` 체크리스트 상태와 완료율 갱신
- matrix, campaign, 학습, 패키징처럼 장시간 실행하는 작업의 heartbeat
- 전체 로드맵의 노후화 감사와 증거 기반 정규화

AIRI와 무관한 일반 체크리스트 또는 단순 코드 구현에는 적용하지 않는다. 이 계약과 skill은
mutation, 장시간 명령, process 시작·중단, commit, push 또는 외부 서비스 호출 권한을 만들지
않는다. 해당 행동은 현재 사용자 요청과 저장소 운영 계약에서 별도로 허용돼야 한다.

대시보드 갱신 전 다음 순서로 읽고 대조한다.

1. 저장소 루트 `AGENTS.md`
2. `airi_docs/진행중/AIRI-WORKING-STATE.md` 전체
3. WORKING-STATE가 지정한 현재 handoff와 해당 단계 계약
4. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`
5. `NEXT-SESSION.md`
6. 이 공통 계약

채팅 요약은 증거가 아니다. 실제 PID·command line·listener, 고유 산출물 집합, receipt, 파일
SHA, HEAD와 `git status`를 읽기 전용으로 대조한다. 문서와 기계 상태가 다르면 실행을 멈추고
관측 사실로 WORKING-STATE와 대시보드를 먼저 정정한다.

## 2. 사용자용 최상단 대시보드

`airi_docs/로드맵/AIRI-ROADMAP-STATUS.md` 최상단의 `## 사용자용 현재 진행 대시보드`가
현재 상태의 권위 있는 사용자용 요약이다. 과거 로그를 읽지 않아도 다음을 알 수 있어야 한다.

- 사용자용 이름을 앞에 둔 현재 목표와 내부 milestone 식별자
- 현재 실제 작업과 그 이유
- 실제 증거에서 계산한 진행 수치와 기준 시각
- 정지·차단 사유 또는 없다는 명시
- 현재 단계 완료 조건, 다음 작업, 다음 사용자 결정
- 정상 완료율과 처리 종료율
- 마지막 실제 상태 대조 시각과 핵심 receipt

내부 코드명은 제목 앞에 두지 않는다. 예를 들어 `비공개 48회 비교 평가 실행 (M4-6,
d1v6 matrix)`처럼 사용자용 이름을 먼저 쓰고 내부 식별자를 뒤에 병기한다. `M`은 이
대시보드에서 Milestone, 즉 사용자가 이해할 수 있는 주요 작업 단계를 뜻한다.

blind·matrix·verdict·campaign과 P1~P5 같은 용어는 현재 authoritative 계약에서 실제 의미를
확인한 뒤 짧은 한국어 용어집으로 유지한다. 추측하거나 과거 세대 정의를 현재 정의로 승격하지
않는다.

## 3. 체크리스트 상태와 계산

허용 상태는 다음뿐이다.

- `[x]`: 검증까지 성공적으로 완료
- `[~]`: 현재 실제로 실행 중
- `[Q]`: 실행 준비가 끝나 순서를 기다림
- `[ ]`: 아직 시작하지 않음
- `[P]`: 일부 완료했지만 현재 실행 중은 아님
- `[B]`: 차단 또는 보류. 같은 항목에 `차단 원인:`과 `재개 조건:`을 모두 기록
- `[D]`: 사용자 결정 또는 승인이 필요
- `[F]`: 실행됐지만 hard gate 실패 또는 no_winner로 종료
- `[S]`: 후속 버전으로 대체되어 더 진행하지 않음
- `[N/A]`: 선택되지 않은 조건 분기라 실행 대상이 아님
- `[?]`: 증거 대조 중의 임시 상태. 감사 종료 전에 다른 상태로 확정

현재 Goal 체크리스트에는 실제 작업 중인 `[~]`가 최대 하나다. active Goal에서 작업이 실제로
진행 중이면 정확히 하나를 사용한다. 사용자 결정 대기나 전면 차단 상태에서는 `[D]` 또는 `[B]`로
옮기고 `[~]`를 남기지 않는다. 구현·운영 배선·측정·조건부 campaign은 한 행에 섞지 않는다.

활성 항목 전체는 모든 체크리스트 항목에서 `[S]`와 `[N/A]`만 제외한 수다.

- 정상 완료율 = `[x] / 활성 항목 전체`
- 처리 종료율 = `([x] + [F]) / 활성 항목 전체`
- 선택적 진행 지수 = `([x] + [F] + 0.5×[P] + 0.5×[~]) / 활성 항목 전체`

`[F]`는 정상 완료가 아니지만 처리 종료에는 포함한다. 대시보드 수치는 현재 Goal 체크리스트를
실제로 파싱해 다시 계산하며 예전 숫자를 복사하지 않는다. 전체 로드맵 수치는 같은 계산식을
별도로 적용하고 기준 시각을 함께 기록한다.

## 4. 장시간 heartbeat

현재 Goal 또는 handoff가 더 짧은 상한을 요구하지 않는 한 matrix·campaign 등 장시간 작업은
최대 14분마다 다음 두 문서를 같은 관측값과 시각으로 갱신한다.

- `airi_docs/진행중/AIRI-WORKING-STATE.md`
- `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`

ROADMAP의 현재 작업 행은 로그를 누적하지 않고 제자리에서 갱신한다.

```text
- [~] 비공개 48회 비교 평가 실행 (M4-6, d1v6 matrix) — N/48 <- YYYY-MM-DD HH:mm 현재 작업 중
```

`N`은 하나의 로그 문구나 단순 파일 수가 아니다. run key/index별 report·health·run-contract·
packet 집합을 각각 만들고 네 집합의 고유 교집합 수로 계산한다. 각 집합 내부 duplicate,
합집합 대비 incomplete 또는 index 불일치가 하나라도 있으면 진행률을 올리지 않고 `[B]`와
원인·재개 조건을 기록한다.

heartbeat마다 다음을 실제로 대조한다.

- wrapper와 child PID 생존 및 exact command line
- report·health·run-contract·packet 고유 개수, 교집합, duplicate, missing
- exit receipt와 terminal 여부
- owned PID·listener 및 금지 포트 이상
- `Get-Date`로 얻은 실제 시각

정상 heartbeat는 두 파일만 갱신하고 채팅이나 ROADMAP-LOG에 쌓지 않는다. 이상·차단·terminal
때만 사용자에게 알린다. terminal이면 즉시 기존 `[~]`를 `[x]`, `[F]`, `[N/A]` 등 증거에 맞는
종료 상태로 바꾸고 다음 실제 작업 하나에만 `[~]`를 둔다. process를 중복 시작하지 않는다.

## 5. 전체 로드맵 감사

각 항목을 코드, 테스트, receipt, commitment, commit 또는 명시적 사용자 결정과 대조한다.
증거 없이 `[x]`로 승격하지 않는다.

- 실행 후 no_winner/hard gate 실패는 `[F]`
- 구현은 끝났으나 운영 배선·실측이 남으면 분리하거나 `[P]`
- 설계만 끝나 다음 gate 뒤로 보류되면 설계 `[x]`와 구현 `[B]`/`[D]`로 분리
- 선택되지 않은 조건부 작업은 `[N/A]`
- 후속 세대로 대체된 작업은 `[S]`
- 승인이나 방향 결정이 필요하면 `[D]`

감사 중에만 `[?]`를 사용할 수 있고 마감 전에 0개로 만든다. 과거 상세 기록은 삭제하지 않되,
현재 상태를 나타내는 체크리스트와 충돌하면 체크리스트를 증거 기준으로 정규화한다.

## 6. 기록·보안·권한 경계

- heartbeat는 WORKING-STATE와 ROADMAP-STATUS의 live 행만 갱신한다.
- 작업 배치 완료는 `AIRI-ROADMAP-LOG.md`에 한 번 기록한다.
- milestone·verdict·권한 변경은 현재 handoff, ROADMAP-STATUS, NEXT-SESSION을 동기화한다.
- 10분 이상 명령과 process 시작·종료에는 WORKING-STATE intent/receipt를 남긴다.
- response 본문, blind 원문, credential, token, `.env`, 개인 데이터는 대시보드나 helper 출력에
  노출하지 않는다.
- commit은 정확한 파일만 stage하고 검증 뒤 수행한다. push는 직전의 별도 사용자 승인이 있을
  때만 수행한다.

반복 계산 helper가 필요하면 read-only로 만들고 고유 index 교집합·duplicate·missing·terminal
상태만 구조화된 JSON으로 출력한다. 기존 동등 기능이 있으면 새 추상화를 만들지 않는다.
