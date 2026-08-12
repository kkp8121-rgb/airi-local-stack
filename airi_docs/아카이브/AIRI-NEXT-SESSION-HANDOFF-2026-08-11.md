# AIRI 다음 세션 인수인계 — 2026-08-11

## 현재 상태

- 브랜치: `fix/code-audit-remediation-2026-08-07`
- 구현 기준 커밋: `a6fa19c` (`ci: gate core Python regression suite`)
- 구현 기준 원격 CI: PASS
- 로컬·원격 브랜치: 동기화 상태에서 이 문서를 작성했다.
- 선택지 A인 재현성·검증 안정화는 완료했다.
- 선택지 B인 대화 자연스러움·grounding 정책과 C인 2초 지연·retry 정책은 의도적으로 연기했다.

문서 작성 중 원격에 `feat/grounding-latency-2026-08-11` 브랜치가 추가된 것을 확인했다. 이 브랜치는 안정화 기준 `a6fa19c` 이후 7개 커밋을 가지며, 관측 당시 tip은 `2033abb`였다. grounding·무응답 방지·watchdog·patch 검증·Python CI 변경이 함께 들어 있으나 현재 안정화 브랜치에는 병합되지 않았고, 이 인수인계 세션에서 내용의 정당성을 검증하지도 않았다.

상세한 변경 및 검증 근거는 `airi_docs/AIRI-STABILITY-CHECKPOINT-2026-08-10.md`에 있다.

## 완료된 작업

1. 전체 핵심 Python 범위를 클린 Python 3.12 기준으로 실행할 수 있게 했다.
2. ignored `runtime/` 파일을 읽던 지식 테스트를 tracked `testdata/` fixture로 옮겼다.
3. Windows 시계 해상도 때문에 다른 분기를 검사하던 first-raw watchdog 테스트를 결정적으로 수정했다.
4. GitHub Actions에 별도 `python-core-tests` job을 추가했다.
5. 최종 로컬 결과는 `661 passed, 1 skipped, 365 subtests passed`였다.
6. 기존 오프라인 체크포인트와 Node sender 26건도 통과했다.

## 반드시 유지할 경계

- 테스트용 승인 지식 fixture는 운영 지식 DB를 자동 생성하거나 활성화하지 않는다.
- 모델, Ollama, STT, TTS, 마이크, 운영 서비스 및 운영 DB를 검증 목적으로 호출하지 않는다.
- 독립 검토 문서의 경로·개인정보 정리는 사용자가 무시하도록 결정했으므로 다시 시작하지 않는다.
- B와 C를 한 번에 구현하지 않는다. 독립 검증이 끝난 후 사용자가 다음 우선순위를 다시 선택한다.
- 새 원격 feature 브랜치를 자동 merge, rebase 또는 cherry-pick하지 않는다. 먼저 `a6fa19c..2033abb`를 읽기 전용으로 감사한다.
- 과거 patch artifact 전체를 현재 지원 patch로 취급하지 않는다. 현재 매니페스트가 지원 범위의 기준이다.

## 다음 세션의 첫 작업

다음 세션은 코드를 고치기 전에 안정화 기준과 새 feature 브랜치를 읽기 전용으로 확인한다.

```powershell
git pull --ff-only origin fix/code-audit-remediation-2026-08-07
git fetch origin
git status --short --branch
git log -5 --oneline
git diff 9997145..HEAD --stat
git log --oneline a6fa19c..origin/feat/grounding-latency-2026-08-11
git diff --stat a6fa19c..origin/feat/grounding-latency-2026-08-11
.\test-current-checkpoint.ps1
python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt
```

Python 명령은 필요한 패키지가 설치된 클린 Python 3.12 환경에서 실행한다. 운영 서비스나 모델을 기동해 테스트를 보충하지 않는다.

검토 결과는 다음 세 가지를 분리해서 보고한다.

1. 테스트 fixture 재현성
2. CI가 클린 Windows runner에서 실제로 실행되는지
3. 운영 지식 배포·활성화 정책이 아직 별도 과제라는 사실

그다음 feature 브랜치를 별도 clean worktree 또는 별도 clone에서 검증한다. 안정화 브랜치 위에 checkout·merge하지 않는다. HIGH 또는 MED 문제가 없더라도 수정 커밋을 만들지 말고 merge 가능 여부만 보고한다.

## 다른 세션에 전달할 채팅

```text
airi-local-stack 저장소의 fix/code-audit-remediation-2026-08-07 브랜치를 인수인계받아 주세요.

먼저 다음을 실행하세요.
git pull --ff-only origin fix/code-audit-remediation-2026-08-07
git fetch origin
git status --short --branch
git log -5 --oneline

그다음 아래 두 문서를 순서대로 읽으세요.
1. airi_docs/AIRI-NEXT-SESSION-HANDOFF-2026-08-11.md
2. airi_docs/AIRI-STABILITY-CHECKPOINT-2026-08-10.md

이번 턴은 읽기 전용 독립 검증입니다. 구현 설명을 그대로 믿지 말고 안정화 기준 9997145..HEAD를 먼저 확인하세요.

원격에 feat/grounding-latency-2026-08-11 브랜치가 있으며 관측 당시 tip은 2033abb입니다. 이 브랜치는 아직 안정화 브랜치에 병합되지 않았습니다. 자동 merge/rebase/cherry-pick하지 말고 a6fa19c..origin/feat/grounding-latency-2026-08-11의 7개 커밋과 전체 diff를 별도 clean worktree 또는 별도 clone에서 감사하세요.

검증 항목:
- .\test-current-checkpoint.ps1
- 클린 Python 3.12 환경에서:
  python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt
- test_knowledge_store.py가 ignored runtime/ 파일 없이 tracked testdata fixture만으로 통과하는지
- first-raw watchdog 테스트가 response-header timeout이 아니라 raw-body timeout 경로를 검증하는지
- GitHub Actions의 python-core-tests job이 클린 Windows runner에서 필요한 의존성과 위 테스트 범위를 실제로 실행하는지
- 새 fixture와 인수인계 변경에 비밀키, 개인 대화, 세션 ID, 로컬 절대 경로가 추가되지 않았는지 privacy-safe하게 확인
- feature 브랜치의 grounding/무응답 방지 변경이 새로운 사실 날조, 화자 역전, 질문의 단정문 변환, wire와 journal 불일치 또는 추가 침묵을 만들지 않는지
- feature 브랜치의 watchdog 정리가 응답 선택·타임아웃·연결 종료 순서를 바꾸거나 중복 close를 만들지 않는지
- feature 브랜치가 B와 C를 한 변경에 섞은 이유와 실제 지연·자연스러움 acceptance 근거가 충분한지
- feature 브랜치의 patch manifest 및 CI 변경이 현재 지원 범위만 검증하고, cold-cache에서도 10분 job 상한 안에 끝나는지

제약:
- 모델, Ollama, STT, TTS, 마이크, 운영 서비스, 운영 DB를 호출하거나 변경하지 마세요.
- B(자연스러움/grounding)와 C(2초 지연/retry)를 새로 구현하지 마세요. 이미 존재하는 feature 브랜치를 감사만 하세요.
- 독립 검토 문서의 경로·개인정보 정리와 과거 patch artifact 정리는 하지 마세요.
- HIGH/MED만 우선 보고하고, 문제가 없으면 불필요한 수정·문서·테스트 커밋을 만들지 마세요.
- 테스트 재현성과 운영 지식 자동 배포는 별개라는 점을 분명히 구분하세요.

최종 보고에는 안정화 HEAD, feature tip, 각 worktree 상태, 실행한 검증, 결과, 남은 HIGH/MED, 그리고 feature 브랜치를 merge해도 되는지 여부만 간결하게 적어 주세요.
```
