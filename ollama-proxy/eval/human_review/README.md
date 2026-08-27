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

## 3.5 보정 채점 — 사람 노력을 30% 로 줄이기

99턴 전수 채점은 오래 걸린다. `calibrate_ratings.py` 는 AI 채점을 사람 부분 채점으로 눈금 보정해
전수 채점에 준하는 추정치를 만든다.

**AI 채점 단독은 게이트에 쓸 수 없다.** 2026-08-27 실측: 사람 채점 198턴을 앵커로 준 채점자 2종
(codex/claude, 페르소나 "치지직 실시간 스트리밍 시청자")이 사람 3.0976 회차를 각각 1.98/2.11 로 매겨
**PASS 를 FAIL 로 뒤집었다**. 무캘리브레이션 예비 채점은 더 나빠서 회차마다 편향 부호가 뒤집히고
(+0.15/−0.31) filler 오차 21pp 에 치명 실패를 놓쳤다(3/7, 0/1). filler 를 결정론 규칙으로 재현하려는
시도도 최선 규칙이 평균 오차 15.4pp 로 실패했다.

쓸 수 있는 이유는 따로 있다. 두 AI 채점자는 **서로 0.09~0.13 안에서 일치**했다(턴 단위 ±1 이내
88.9~96.0%). 즉 오차는 무작위가 아니라 앵커 평균 쪽으로 수축하는 **체계적 편향**이고, 그건 사람
표본으로 교정된다. 사람 k턴만 쓰는 것 대비 p95 오차가 15~48% 줄었고, 층화 추출이 무작위보다 6~22%
더 좋았다.

```powershell
# 1) 사람이 채점할 30턴을 AI 점수 구간을 가로지르게 층화 선정 (난수 없음 — 재현 가능)
python ollama-proxy\eval\human_review\calibrate_ratings.py select --ai ai-a.json ai-b.json `
    --input review.jsonl --output subset.jsonl --k 30
# 2) 그 30턴만 담긴 평가지를 만들어 사람이 채점한다
python ollama-proxy\eval\human_review\build_rating_sheet.py --input subset.jsonl --output partial.html
# 3) 사람 부분 채점 + AI 채점 → 보정 전수 채점 + 불확실성
python ollama-proxy\eval\human_review\calibrate_ratings.py merge --ai ai-a.json ai-b.json `
    --human human-partial.json --output calibrated.json --markdown calibrated.md
```

출력 JSON 은 `summarize_ratings.py` 가 그대로 받는 정수 스키마이고, 소수점 추정치와 95% 구간은
`calibration` 블록에 따로 남는다. **구간이 기준선(3축 3.0)을 가로지르면 확정하지 않고 전수 채점한다.**
`merge` 리포트는 계약 §4 돌파 정의 **5개 기준을 전부** 낸다 — 3축 ≥3.0, critical 0, filler ≤25%,
말투 ≥3.5, 사실성 ≥기준선(run 04 확정 2.75). 앞의 세 개만 보면 통과 판정이 잘못 나온다.

실측 검증(사람 30턴, 실데이터 end-to-end):

| 회차 | 보정 추정 (95% 구간) | 사람 전수 참값 | 판정 |
| --- | --- | --- | --- |
| 07-s3-r2 | 3.2860 [3.096, 3.476] | 3.0976 | PASS — 일치 |
| 07-s2-r2 | 2.1389 [1.969, 2.309] | 2.2290 | FAIL — 일치 |

한계 두 가지를 알고 써야 한다. **filler 추정 오차는 최대 19pp** 라 어떤 회차의 filler 가 25% 근처면
그 기준만은 전수 채점해야 한다. **critical 은 보정 대상이 아니다** — 합집합으로 모으므로 과잉 검출이
나오고(실측 사람 0건에 AI 1건), 사람이 그 후보 턴만 직접 확인해야 한다. 놓치는 것보다 안전한 방향을
택한 결과다.

기준선 자체의 한계도 기록해 둔다. 99턴 3축 합성의 표준오차는 0.08~0.10 이라, **3.0976 같은 값은
전수 채점을 해도 3.0 과 통계적으로 구별되지 않는다**(+1.10σ, 95% 구간이 3.0 을 가로지름). 다른
회차는 −7.6σ~−14.5σ 로 확고했다.

### 아직 없는 것 (쓰기 전에 알아야 함)

- **AI 채점을 생성하는 도구가 레포에 없다.** 위 실측의 AI 채점은 에이전트가 앵커 팩을 읽고 손으로
  JSON 을 쓴 애드혹 절차였다. 프롬프트·앵커 팩·모델을 SHA 로 못 박는 `rate_dialogue.py` 가 없으면
  **회차 간 비교가 성립하지 않는다.** 그때까지 이 경로는 1회성 실측이지 정식 게이트가 아니다.
  실측에 쓴 채점 JSON 은 계약 §1 대로 저장소 밖 회차 디렉터리에 `ratings-*-calibrated.json` /
  `ratings-ensemble.json` / `calibrated-30turn.json` 으로 보존했다.
- **계약 §6 개정과 사용자 승인이 선행 조건이다.** 계약은 사람 채점을 유일한 채택 게이트로 두고,
  채점 결과를 본 뒤 판정 규칙을 바꾸는 것을 금지한다(변경은 다음 라운드부터). 보정 경로를 정식
  게이트로 인정하려면 **채점을 시작하기 전에** 개정·승인돼야 한다.
- **앵커 누출 금지.** 앵커로 쓴 회차를 검증 대상으로 다시 쓰면 수치가 무의미해진다. 현재는 코드로
  막혀 있지 않으니 사람이 지켜야 한다.
- **채점자에게 AI 점수를 먼저 보여주지 않는다.** 앵커링 편향으로 검증 자체가 오염된다. `select` 가
  만드는 부분 평가지에는 AI 점수가 들어가지 않는다.

## 5. 스트리머 응답 정답지 (`pair_streamer_response.py`)

공개 VOD 의 **채팅 + 스트리머 발화**로 "실제 스트리머가 무엇에 반응했는가" 를 만든다. 쓰임은 셋이다 —
픽업 정책의 정답지, 흔들리지 않는 채점 기준점, 맥락 주입용 트랜스크립트. 상세와 실측은
`진행중/AIRI-EVAL-INPUT-CONTEXT-AUDIT-2026-08-27.md` §4-3·§8.

```powershell
# 오디오 (yt-dlp 는 chzzk:video 가 KeyError('sourceURL') 로 깨져 있어 이 경로를 쓴다)
python ollama-proxy\eval\human_review\import_public_chat.py chzzk-audio --video-no <no> --output <밖>\audio.m4a
ffmpeg -i <밖>\audio.m4a -vn -ac 1 -ar 16000 -c:a pcm_s16le <밖>\audio.wav
python stt\transcribe_vod.py --input <밖>\audio.wav --output <밖>\transcript.jsonl
# 정답지
python ollama-proxy\eval\human_review\pair_streamer_response.py `
    --chat <밖>\chat.jsonl --transcript <밖>\transcript.jsonl --output <밖>\pairs.jsonl
```

**시간만으로 짝지으면 안 된다** — 채팅이 초당 3건인데 스트리머는 극히 일부만 읽는다. 스트리머가
채팅을 읽을 때 그 채팅의 고유 어휘를 그대로 쓰는 것을 신호로 쓴다. 그리고 **방향을 반드시 가른다**:
시청자가 스트리머 말을 따라한 경우가 훨씬 흔하므로, 채팅 직전 발화에 이미 나온 어휘는 응답 근거가
될 수 없다. 조사·어미로 분절이 갈리는 것(`충실한편` vs `충실한`)까지 접두 매칭으로 잡는다 — 실측에서
이 필터를 촘촘히 한 것만으로 후보 70 → 57건, 에코 제외 123 → 364건이 됐다.

`transcribe_vod.py` 는 모델·beam 을 `stt/openai_stt_server.py` 와 같은 값으로 핀한다(테스트로 고정).
회차마다 다른 설정으로 받아쓰면 트랜스크립트끼리 비교가 성립하지 않는다. GPU 없이 돌며 실측은
32분 오디오에 654초(2.94배속)였다. 대기화면 구간에서 VAD 가 통째로 뭉개는 일이 있어(실측 296초)
30초 초과 세그먼트는 짝짓기에서 제외한다.

산출물은 전부 **저장소 밖**이다. 오디오는 계약 §1 문구에 없는 입력이므로 **로컬 평가 한정**이며,
학습 정답으로는 쓰지 않는다.

## 테스트와 CI

```powershell
python -m pytest -q ollama-proxy\eval\human_review
```

`test_human_review_tools.py` 는 오프라인·결정적이며 임시 SQLite 로 `airi_memory.py` 의 DDL 을 그대로
재현한다. 이 디렉터리의 테스트 파일 5개는 `.github/workflows/remediation-checkpoint.yml` 의
`ollama-proxy-evaluations` 샤드에 등록돼 있다(새 테스트 파일을 추가하면 같은 샤드에 넣어야 CI 에서 돈다).
`stt/` 는 디렉터리 단위 샤드라 새 파일이 자동으로 포함된다.

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
