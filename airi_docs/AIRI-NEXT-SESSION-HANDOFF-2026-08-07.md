# AIRI 다음 세션 인수인계 — 2026-08-07 23:12 KST

## 1. 다음 세션의 시작 원칙

- 작업 루트는 저장소 루트(`<repo>`)다.
- 현재 작업 트리는 의도적으로 미커밋 상태다. 기존 변경을 reset/revert/checkout 하지 말고
  먼저 `git status`, `git diff`, 실행 서비스 상태를 확인한다.
- 이 프로젝트의 최종 목표는 검색 봇이 아니라 Neuro-sama처럼 방송하며 사람다운 반응을
  보이는 캐릭터다. 검색은 STT·도구 호출·대화 연속성을 검증하는 테스트 수단일 뿐이다.
- 고정 문구나 단순 횟수 if문으로 성격을 만들지 않는다. 안전 경계는 코드로 지키되,
  대화 행동은 가능한 한 최근 맥락과 모델 판단으로 결정한다.
- 음성 원문과 전사문은 기본 로그에 남기지 않는다. 현재 로그는 길이·신뢰도·지연 같은
  메타데이터만 기록한다.

## 2. Git 상태

- 브랜치: `fix/code-audit-remediation-2026-08-07`
- 마지막 커밋: `b234abe fix: preserve leading speech and recover failed transcripts`
- 아래 작업은 아직 커밋·푸시하지 않았다.

수정 파일:

- `airi_docs/AIRI-FIX-HANDOFF-2026-08-07.md`
- `ollama-proxy/ollama_proxy.py`
- `ollama-proxy/start-local-ollama-proxy.ps1`
- `ollama-proxy/test_ollama_proxy.py`
- `start-airi-local-stack.ps1`
- `stt/openai_stt_server.py`
- `stt/proper_nouns.json`
- `stt/start-local-stt.ps1`
- `stt/test_transcription_filter.py`

새 파일/디렉터리:

- `.codex/config.toml`: 이 저장소에서 불필요한 `unityMCP`, `node_repl`만 비활성화하는
  repo-local 설정이다. 아직 untracked이므로 커밋 여부를 사용자 의도와 함께 확인한다.
- 이 인수인계 문서.

현재 diff 규모는 이 문서를 만들기 전 기준 9개 파일, 약 `+1161/-16`이다. 변경량이 크므로
다음 세션은 커밋 전에 반드시 diff를 기능별로 검토한다.

## 3. 현재 실행 상태

2026-08-07 23:12 KST 기준 다음 포트가 모두 listen 중이다.

| 포트 | 서비스 | 상태 |
|---:|---|---|
| 8880 | TTS | listen |
| 8890 | faster-whisper STT | listen |
| 8892 | latency monitor | listen |
| 9880 | TTS | listen |
| 11434 | Ollama | listen |
| 11435 | AIRI Ollama compatibility proxy | listen |

STT health:

```json
{"status":"ok","model":"mobiuslabsgmbh/faster-whisper-large-v3-turbo","model_id":"whisper-1","device":"cuda","compute_type":"int8_float16","cpu_threads":8,"proper_nouns":1}
```

Proxy health:

```json
{"status":"ok","upstream":"http://127.0.0.1:11434","tools_stripped":true,"cloud_search":"codex-subscription","immediate_ack":true,"system_prompt_overridden":true,"num_ctx":2048,"num_gpu":0}
```

## 4. STT 변경과 실측

현재 루트 기동 기본값은 다음과 같다.

- STT: `mobiuslabsgmbh/faster-whisper-large-v3-turbo`
- device: CUDA
- compute type: `int8_float16`
- CPU threads: 8
- Ollama: `num_gpu=0`

VRAM이 작은 다른 PC에서는 다음 저메모리 프로필을 명시할 수 있다.

```powershell
.\start-airi-local-stack.ps1 -SttModel small -SttComputeType float16 -OllamaNumGpu 12
```

구현된 STT 보정:

- 작은 음성은 목표 RMS 0.04, 최대 4배로 자동 증폭한다.
- RMS와 peak가 모두 조용할 때만 증폭/재시도를 포기한다.
- 검색 맥락에서만 `유행렬`을 `음유잉여`로 교정한다. 일반 대화에는 적용하지 않는다.
- 원문 전사 로그는 계속 비활성화한다.
- 관측된 방송 자막 환각 `자막 제공 및 광고를 포함하고 있습니다.`와 띄어쓰기·문장부호
  변형, `...포함합니다` 변형을 `known_whisper_hallucination`으로 차단한다.
- 이 환각 사유는 retry 대상이 아니므로 recovery decode에서 되살아나지 않는다.
- 문구를 인용하는 더 긴 정상 문장은 exact normalized match가 아니므로 차단하지 않는다.

자막 환각의 근거:

- 저장소 전체에 해당 고정 문구는 없었다.
- 실제 문구는 마침표 포함 22자이며, STT 로그에도 `text_chars=22`가 두 번 기록됐다.
- 두 건 모두 약 2.879초, 낮은 RMS/peak, 첫 판정 `low_log_probability`, VAD fallback 뒤
  잘못 accepted된 동일 패턴이었다.

검증:

- `stt/test_transcription_filter.py`: 36개 전부 통과.
- `py_compile stt/openai_stt_server.py` 통과.
- STT 서버를 위 large-v3-turbo 설정으로 재기동했고 health OK다.
- 아직 실제 마이크에서 같은 환각이 다시 발생하는 물리 테스트는 하지 않았다. 다음 실제
  발생 시 응답이 빈 전사로 끝나고 로그 사유가 `known_whisper_hallucination`인지 확인한다.

## 5. 반복 대화 디렉터

처음 구현했던 `세 번째 같은 요청 => 고정 문구로 되묻기`는 폐기했다. 현재 구조는 다음과
같다.

- 요청의 `messages`에서만 연속 반복 의도를 계산한다. 전역 캐시가 없어 창·세션 간 누출이
  없다.
- 두 번째부터 `repeat_candidate`가 되지만, count 자체는 최종 행동을 강제하지 않는다.
- 로컬 EXAONE이 `normal`, `answer_again`, `ask_reason`, `wait`를 고른다.
- 사용자가 `다시 검색해`라고 명시했을 때만 `search_again`이 허용 행동에 포함된다.
- 모델은 결정 전에 `다시 답할 가치`와 `반복 이유를 물을 가치`를 low/medium/high로
  비교하도록 프롬프트되어 있다.
- 관찰값에는 완료된 유사 답변 수와 직전 답의 짧은 excerpt가 들어간다.
- 반복 후보에서도 캐시된 첫 `응!`은 디렉터 판단 전에 즉시 스트리밍한다.
- 실행하지 않은 검색을 `다시 찾아봤다`고 주장하면 직전 실제 답으로 되돌린다.
- 존댓말이 섞이는 자주 관측된 표현은 반말로 후처리한다.

실제 사용자 테스트 로그:

- 첫 요청: repeat count 1, 일반 처리.
- 두 번째: repeat count 2, 디렉터 `normal`, 약 1712ms.
- 세 번째: repeat count 3, 디렉터 `ask_reason`, 약 2624ms.
- 사용자는 “딱 3번째에 반응하네”라고 확인했다.

이 결과가 하드코딩인지 반증하기 위해 같은 실제 EXAONE에 다른 맥락을 넣어 확인했다.

- count 2 + 이미 충분한 답: `answer_again`.
- count 3 + 앞선 두 답이 모두 미완료 내용: `normal`.
- count 3 + 사용자가 명시적으로 다시 설명 요청: `normal`로 기존 답변 경로 실행.

따라서 count 3 강제 분기는 아니다. 다만 2.4B 모델과 temperature 0 조합이라 같은 맥락은
매번 비슷한 시점에 수렴할 가능성이 높다. 이를 단순 랜덤으로 흔들지 말고, 후속 memory와
관심도·감정·대화 목표 같은 내부 상태가 생긴 뒤 자연스러운 변동을 주는 편이 프로젝트
목표에 맞다.

검증:

- `ollama-proxy/test_ollama_proxy.py`: 43개 전부 통과.
- 실제 EXAONE 통합 fixture에서 세 번째 `음유잉여를 웹에서 검색해`가 `ask_reason`을
  선택했고 외부 검색 호출은 0회였다.
- 첫 SSE `응!`은 별도 라이브 요청에서 약 30ms, 디렉터 본 판단은 대략 1.7~3.7초다.
- 검색 본문을 Codex subscription으로 수행하는 경로는 여전히 약 27초가 걸릴 수 있으며
  별도 병목이다.

## 6. 다음 세션에서 먼저 할 일

1. 이 문서와 `AIRI-FIX-HANDOFF-2026-08-07.md`를 끝까지 읽는다.
2. `git status --short`, `git diff --check`, 기능별 diff를 확인한다. 사용자 변경을 되돌리지
   않는다.
3. 8890/11435 health와 8880/8892/9880/11434 포트 상태를 확인한다.
4. 사용자가 다음 물리 테스트를 하면 STT·proxy 로그를 같은 시간축으로 확인한다.
   - 자막 환각 재발 시 `known_whisper_hallucination`으로 차단되는가.
   - 자연 발화 `오늘 날씨 어때`와 `음유잉여를 웹에서 검색해`가 정확히 전사되는가.
   - 반복 질문에서 count뿐 아니라 director action과 실제 대사가 자연스러운가.
5. 테스트 진단 후 latency monitor를 재기동해 다음 사용자 측정과 진단 샘플을 분리한다.
6. 현재 변경을 커밋/푸시하기 전에 `.codex/config.toml` 포함 여부와 큰 diff를 검토한다.
   사용자의 명시적 요청 없이 reset하거나 다른 변경을 추가로 넓히지 않는다.
7. 이후 큰 기능 우선순위는 장기 기억/RAG 자체보다, 짧은 대화 상태·관심도·감정·행동
   목표를 character loop에 연결해 방송 캐릭터의 연속성을 만드는 것이다.

## 7. 점검 명령

```powershell
git status --short
git diff --check

Invoke-RestMethod http://127.0.0.1:8890/health
Invoke-RestMethod http://127.0.0.1:11435/health

Get-Content -Encoding UTF8 stt\stt-server.out.log -Tail 80
Get-Content -Encoding UTF8 ollama-proxy\ollama-proxy.out.log -Tail 80

& .\chatterbox\.venv\Scripts\python.exe -m unittest discover -s ollama-proxy -p 'test_ollama_proxy.py'
& .\stt\.venv\Scripts\python.exe -m unittest discover -s stt -p 'test_transcription_filter.py'
```

STT만 현재 프로필로 재기동:

```powershell
& .\stt\stop-local-stt.ps1
& .\stt\start-local-stt.ps1 `
  -Model 'mobiuslabsgmbh/faster-whisper-large-v3-turbo' `
  -Device cuda `
  -ComputeType int8_float16 `
  -CpuThreads 8
```

## 8. 다음 세션에 보낼 첫 메시지

아래 내용을 새 세션의 첫 메시지로 그대로 사용한다.

> 저장소 루트(`<repo>`)에서 AIRI 작업을 이어서 진행해줘. 먼저
> `airi_docs/AIRI-NEXT-SESSION-HANDOFF-2026-08-07.md`와
> `airi_docs/AIRI-FIX-HANDOFF-2026-08-07.md`를 끝까지 읽고, 현재 브랜치의
> `git status`와 diff를 확인해. 작업 트리는 의도적으로 미커밋 상태이므로 기존 변경을
> reset/revert하지 마. 그런 다음 8890·11435 health와 8880·8892·9880·11434 포트를
> 확인해. 직전 작업은 Whisper의 “자막 제공 및 광고를 포함하고 있습니다.” 환각을
> `known_whisper_hallucination`으로 차단하고 STT를 large-v3-turbo/CUDA/int8_float16로
> 재기동한 상태야. 우선 인수인계 내용과 현재 실행 상태가 일치하는지 검증하고, 내가
> 다음 음성 테스트를 하면 STT 전사·반복 count·dialogue director action·첫 음성 지연을
> 같은 시간축으로 분석해줘. 이 프로젝트는 검색 봇이 아니라 Neuro-sama처럼 방송 가능한
> 사람다운 캐릭터가 목표이므로 검색 전용 고정 규칙이나 횟수 if문으로 확장하지 마.
> 커밋이나 푸시는 먼저 상태와 검증 결과를 보고한 뒤 내 지시에 따라 진행해.
