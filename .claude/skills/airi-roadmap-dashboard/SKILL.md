---
name: airi-roadmap-dashboard
description: AIRI 저장소의 현재 로드맵 진행, 체크리스트 상태, 장시간 작업 heartbeat와 사용자용 완료율을 실제 프로세스·산출물 증거로 대조해 갱신할 때 사용합니다. AIRI와 무관한 일반 체크리스트나 단순 코드 구현에는 사용하지 않습니다.
---

# AIRI 로드맵 대시보드

현재 진행 설명, 로드맵 체크리스트 갱신, M 단계 의미, matrix/campaign heartbeat 또는 전체
완료율을 묻는 요청에 사용합니다.

갱신 전에 저장소 루트의 `AGENTS.md`,
`../../../airi_docs/진행중/AIRI-WORKING-STATE.md` 전체, 그 문서가 가리키는 현재 handoff,
`../../../airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`, `../../../NEXT-SESSION.md`를 읽습니다.
그다음 [공통 대시보드 계약](../../../airi_docs/진행중/AIRI-ROADMAP-DASHBOARD-CONTRACT.md)을
반드시 전체 읽고 따릅니다.

문서 기록보다 실제 PID·command line·listener·고유 산출물 집합·receipt·HEAD/status를 우선
대조합니다. 불일치는 실행 전에 관측 사실로 바로잡습니다.

이 스킬은 mutation, 장시간 실행, process 재시작, commit 또는 push 권한을 자동으로 부여하지
않습니다. 현재 요청과 저장소 권한 계약이 허용한 범위에서만 행동합니다.
