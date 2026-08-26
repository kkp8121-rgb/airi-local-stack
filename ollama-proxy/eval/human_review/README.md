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
재현한다. 이 디렉터리의 테스트 파일 3개는 `.github/workflows/remediation-checkpoint.yml` 의
`ollama-proxy-evaluations` 샤드에 등록돼 있다(새 테스트 파일을 추가하면 같은 샤드에 넣어야 CI 에서 돈다).

## 4. 공개 채팅 리플레이 가져오기

`import_public_chat.py` 는 공개 라이브 방송의 채팅 리플레이(Chzzk VOD, yt-dlp YouTube 라이브 채팅)를
저장소 밖 원본 파일에서 읽어 가명화된 시청자 메시지 JSONL 로 바꾼다. 표준 라이브러리만 쓰고, 다른
eval 모듈을 import 하지 않는다.

```powershell
python ollama-proxy\eval\human_review\import_public_chat.py chzzk-fetch --video-no 123456 --output D:\airi-public-chat\raw-chzzk.json

python ollama-proxy\eval\human_review\import_public_chat.py normalize --format chzzk --input D:\airi-public-chat\raw-chzzk.json --output D:\airi-public-chat\chzzk.jsonl --hmac-key-file D:\airi-public-chat\hmac.key

python ollama-proxy\eval\human_review\import_public_chat.py normalize --format youtube --input D:\airi-public-chat\raw-youtube.jsonl --output D:\airi-public-chat\youtube.jsonl --hmac-key-file D:\airi-public-chat\hmac.key --video-id <영상 id>
```

`chzzk-fetch` 는 Chzzk VOD 채팅 API 를 `nextPlayerMessageTime` 커서로 페이지네이션해 원본 JSON 을
그대로 저장한다. `normalize` 는 원본(Chzzk/YouTube)을 정제해 닉네임, 원본 유저 id, 채널 id 를 절대
남기지 않고 `author` 필드에 HMAC-SHA256 가명(키는 `--hmac-key-file` 에 없으면 새로 만들고, 있으면
그대로 재사용해 같은 사람은 항상 같은 가명이 되게 한다)만 남긴다. `--video-id` 는 원본에 영상 id 가
없는 YouTube 형식에서 필수다. 원본 캡처와 출력, HMAC 키는 실제 대화와 같은 이유로 저장소 트리 밖에
두는 것이 기본이며, 저장소 안 경로는 `--allow-repo-path` 를 줘야만 쓴다.

### 가명 닉네임 표기 (`--nickname-style`)

`normalize` 는 `--nickname-style {hash,korean}` 로 `author` 표기를 고른다. 기본값 `hash` 는 지금까지와
같은 `v` + 16진수 8자리(`v36d8e423`)다. `korean` 은 **같은 HMAC 다이제스트에서** 2음절 한국어 단어
두 개와 2자리 접미사를 뽑아 `솔잎토끼19` 같은 8자 이하 가명을 만든다.

```powershell
python ollama-proxy\eval\human_review\import_public_chat.py normalize --format chzzk --input D:\airi-public-chat\raw-chzzk.json --output D:\airi-public-chat\chzzk.jsonl --hmac-key-file D:\airi-public-chat\hmac.key --nickname-style korean
```

`korean` 은 **평가자 가독성만을 위한 것**이다. 원본 닉네임에서 오는 값은 하나도 없고(단어는 고정 풀,
선택은 전부 다이제스트), 같은 키·같은 사람이면 실행을 몇 번 반복해도 같은 가명이 나온다는 점도
`hash` 와 같다. 다만 표기 공간이 좁아(단어 44개 × 44개 × 접미사 100) 시청자가 수백 명이면 서로 다른
사람이 같은 가명을 받을 확률이 `hash` 보다 눈에 띄게 높다. 가명 하나가 곧 한 사람이어야 하는 분석
(재생 로스터, 발언 이력)에는 기본값 `hash` 를 쓴다.
