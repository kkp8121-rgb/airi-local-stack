# human_review — 실제 대화 사람 평가 도구

2026-08-26 결정에 따라 채택 게이트는 **합성 픽스처가 아니라 실제 대화**(비공개 테스트 방송 또는
로컬 스택과의 직접 대화)에 대한 사람 평가다. 이 디렉터리는 그 루프에 필요한 최소 오프라인 도구
3종만 담는다. 표준 라이브러리만 쓰고, 다른 eval 모듈을 import 하지 않는다.

## 1. 대화 내보내기

프록시 메모리 DB의 `conversation_message` 를 **읽기 전용**(`file:...?mode=ro`)으로 열어 turn 단위
user/assistant 쌍을 JSONL 로 뽑는다. 한쪽이 없는 turn 은 건너뛴다.

```powershell
python ollama-proxy\eval\human_review\export_session_dialogue.py --db <memory.sqlite3> --list
python ollama-proxy\eval\human_review\export_session_dialogue.py --db <memory.sqlite3> --session <id> --output D:\airi-human-review\turns.jsonl
python ollama-proxy\eval\human_review\export_session_dialogue.py --db <memory.sqlite3> --all-sessions --since-turn 10 --limit-turns 40 --output D:\airi-human-review\turns.jsonl
```

메모리 DB 기본 경로는 `ollama-proxy\runtime\airi-memory.sqlite3` 이다
(`start-airi-local-stack.ps1` / `ollama-proxy\start-local-ollama-proxy.ps1` 의 `-MemoryDbPath` 가
비어 있을 때의 값이며, 프록시에는 `AIRI_MEMORY_DB` 로 전달된다). 캠페인·T3 실행은 각 run 디렉터리의
`runtime\memory.sqlite3` 를 쓴다.

실제 대화는 Git 에 남기지 않는다. 그래서 출력 경로가 저장소 트리 안이면 기본적으로 거부하고,
`--allow-repo-path` 를 줘야만 쓴다. stdout 에는 개수만 찍고 대화 내용은 찍지 않는다.

## 2. 평가지 만들기

JSONL 을 외부 자산 없는 단일 HTML 평가지로 만든다. 대화 텍스트는 전부 `textContent` 로만 넣고,
JSON 은 `<`, `>`, `&` 를 이스케이프해 스크립트 블록을 조기 종료할 수 없게 한다.

```powershell
python ollama-proxy\eval\human_review\build_rating_sheet.py --input D:\airi-human-review\turns.jsonl --output D:\airi-human-review\sheet.html --rater 이름
```

평가 축은 1~5 정수로 **방송다움 / 맥락 유지 / 반응 적절성 / 말투 규칙 / 사실성**, 플래그는
`critical_failure`, `silence_or_filler`, `invented_name`, `polite_violation`(존댓말 종결 정규식으로
미리 체크되는 정보성 힌트, 평가자가 고칠 수 있음) 과 자유 코멘트다. 기준 설명은 평가지 상단에
같이 들어가므로 별도 문서가 필요 없다. 채점 상태는 브라우저 메모리에만 있고, `JSON 내보내기` /
`JSON 불러오기` 로 저장하고 이어서 한다. 진행 카운터와 `미평가만 보기` 필터가 있다.

## 3. 집계

평가자별 JSON 을 검증하고 내용 없는 요약을 만든다. 스키마 위반이거나 평가 turn 이 0이면 exit 1.

```powershell
python ollama-proxy\eval\human_review\summarize_ratings.py --ratings r1.json --ratings r2.json --output summary.json --markdown summary.md
```

축별 평균/중앙값/최소, 전 축 4점 이상 비율, 플래그 비율, 같은 turn 을 2명 이상이 평가했을 때의
축별 평균 절대차와 플래그 불일치율, turn/세션 개수를 담는다. 대화 텍스트와 코멘트 원문은 요약에
절대 들어가지 않는다(코멘트는 개수만 센다).

## 테스트와 CI

```powershell
python -m pytest -q ollama-proxy\eval\human_review
```

`test_human_review_tools.py` 는 오프라인·결정적이며 임시 SQLite 로 `airi_memory.py` 의 DDL 을 그대로
재현한다. **이 테스트 파일은 `.github/workflows/remediation-checkpoint.yml` 의 Python 샤드 매트릭스에
아직 추가되지 않았다.** 샤드 목록에 추가해야 CI 에서 실제로 돈다(추가는 supervisor 가 한다).
