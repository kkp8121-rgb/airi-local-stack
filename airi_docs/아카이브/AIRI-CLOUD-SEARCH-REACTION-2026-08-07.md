# AIRI 2초 선반응 + 구독형 클라우드 검색 — 2026-08-07

## 목표와 현재 판정

목표는 `발화 종료 → AIRI 첫 음성`을 2초 안으로 줄이고, 명시적 검색 요청은 로그인된 구독형 클라우드 AI가 실제 웹 검색하도록 만드는 것이다.

구현과 설치 AIRI 내부의 실제 오디오 재생 검증은 완료했다. 자동 검증에서는 텍스트 입력 앞에 합성 STT 시각을 넣었으므로, 실제 마이크·발화 종료 판정을 포함한 사용자 5회 측정은 여전히 필요하다. 따라서 전체 목표를 완료로 판정하지 않는다.

## 적용된 경로

```text
발화 종료
  → AIRI VAD 450ms
  → faster-whisper small CUDA/float16
  → 고유명사 사전 보정
  → transcript flush 400ms
  → Ollama proxy가 즉시 SSE 선반응
      ├─ 일반 대화: "응!" + 로컬 EXAONE 답변
      └─ 검색 요청: "응! 바로 찾아볼게." + Codex 구독 웹 검색
  → 고정 선반응은 GPT-SoVITS 메모리 WAV 캐시로 즉시 재생
  → 검색 결과는 같은 assistant stream에 이어서 TTS
```

검색은 AIRI의 비활성 Tavily 도구나 로컬 EXAONE function calling에 의존하지 않는다. `codex login status`가 `Logged in using ChatGPT`인 Codex CLI를 `--search exec --ephemeral --sandbox read-only`로 호출한다. 별도 검색 API 키를 저장하지 않는다.

## 핵심 변경

- `ollama-proxy/ollama_proxy.py`
  - `검색/서칭/찾아봐` 의도를 결정적으로 판별
  - 첫 SSE를 upstream LLM 또는 검색 완료 전에 즉시 반환
  - 짧은 ACK 뒤에 무해한 ACT 경계 토큰을 붙여 AIRI의 5글자 marker-parser 보류를 즉시 해제
  - Codex CLI 구독 세션으로 live web search 실행
  - 검색 성공/실패를 같은 assistant turn에 이어 반환
  - 검색 로그에는 원문 대신 query 글자 수와 시간만 기록
  - AIRI의 `[날짜 시간]` 표시 접두사를 검색어에서 제거
  - 문장 첫 검색어가 잘렸지만 `웹에서 검색해줘`가 남은 경우 최근 명시적 검색어를 복구
- `stt/openai_stt_server.py`
  - CPU INT8에서 RTX 3060 Ti CUDA/float16으로 이동
  - startup CUDA warmup
  - `stt/proper_nouns.json` 기반 hotword와 관측 alias 보정
  - `웹서팅`을 `웹서칭`으로 보정
  - AIRI VAD를 통과한 비정숙 청크를 Whisper 내부 VAD가 전부 제거하면 `vad_filter=false`로 한 번 즉시 재시도
- `patch-airi-reaction-latency.ps1`
  - VAD silence `1200 → 450ms`
  - 문장 첫 단어 보존용 speech pre-roll `360 → 600ms`
  - transcript flush `1200 → 400ms`
  - 설치 `app.asar` 원본 백업 후 동일 길이 바이너리 패치
- `gpt-sovits/openai_compatible_proxy.py`
  - `응!`, `바로 찾아볼게.`를 startup에 합성해 메모리에 보관
  - cache hit은 TTS generation lock을 거치지 않고 완성 WAV를 즉시 반환
  - backend 준비 후 proxy를 시작하도록 startup 순서 보정
- `patch-airi-playback-latency.ps1` + `latency-monitor/`
  - 실제 Web Audio `source.start(0)` 순간을 `playback:start`로 전송
  - 대시보드의 큰 숫자를 VAD 450ms 포함 `발화 종료 → 실제 재생 시작`으로 표시
  - 최근 실제 마이크 5회의 최신값·P50·P95와 `5/5 모두 2초 이내` 판정을 자동 표시
  - 각 turn에 고유명사 보정 횟수와 클라우드 검색 실행 여부를 표시
  - 문장 시작 누락 때문에 직전 검색어를 복구했는지도 표시
  - 원문·음성·대사는 보내지 않고 intent 식별자와 시각만 메모리에 기록

## 실측

2026-08-07 현재 PC에서 같은 프로세스가 실제 포트를 열고 있는 상태로 측정했다.

| 항목 | 결과 |
|---|---:|
| STT HTTP 첫 실요청 | 670.3ms |
| STT HTTP warm 요청 | 291.3ms |
| 일반 대화 첫 SSE | 90.4ms |
| 검색 요청 첫 SSE | 99.9ms |
| `응!` 캐시 TTS 전체 HTTP | 5.5ms |
| `바로 찾아볼게.` 캐시 TTS | startup cache ready |
| 설치 AIRI 일반대화: 합성 입력 종료 → 실제 재생 | 744ms |
| 설치 AIRI 검색: 합성 입력 종료 → 실제 재생 | 1,184ms |
| 설치 AIRI 검색: LLM 시작 → 실제 재생 | 123ms |
| 설치 AIRI 검색: 첫 ACK TTS | 1.4ms, cache hit |
| `음유잉여` Codex 검색 최종 답변 | 11.6~21.3초 |

실제 마이크 검색 선반응은 적용 중간 검증에서 `1.460s`, `1.620s`, `1.850s`,
`1.552s`, `1.500s`로 모두 2초 이하였다. 다만 마지막 두 번 중 첫 턴에서 문장
첫 고유명사가 한 번 누락되어 speech pre-roll과 최근 검색어 복구를 추가했으며,
수정 후 실제 마이크 표본은 다시 수집한다.

최종 검색 검증에서는 `음유잉여`를 이터널 리턴의 이바 장인 선수·스트리머 닉네임이며 선수명은 `UmU`라고 찾아냈고, 이터널 리턴 공식 사이트·닥지지·이스포츠 위키를 교차 확인했다고 반환했다.

설치 AIRI 자동 검증은 프록시 첫 조각이 marker parser, 문장 분리기, TTS, `AudioBufferSource.start(0)`까지 실제로 통과했음을 확인한다. 검색은 백그라운드에서 21.3초 계속됐지만 선반응은 합성 입력 종료 기준 1.184초에 재생됐다. 다만 이 합성 입력은 실제 STT가 아니므로, 물리적 첫 재생 2초 달성은 사용자 마이크 5회 데이터로 확정한다.

## 고유명사 처리

현재 `proper_nouns.json`에는 다음 항목이 있다.

- canonical: `음유잉여`
- observed aliases: `음류인경`, `윤류린 여`, `음유 인여`, `음유잉어`
- search-only alias: `음료인` — 일반 문장의 “음료인 것 같아”를 오보정하지 않도록 검색 의도가 있을 때만 적용
- search-only context hint: `이터널 리턴`, `UmU`

맥락 힌트는 검색 프롬프트에서 반드시 웹으로 재검증하도록 표시한다. 사전에 있다고 사실로 확정하지 않는다.

## 시작·검증

```powershell
.\start-airi-local-stack.ps1

Invoke-RestMethod http://127.0.0.1:8890/health
Invoke-RestMethod http://127.0.0.1:11435/health
Invoke-RestMethod http://127.0.0.1:8880/health
```

기대 상태:

- STT: `device=cuda`, `compute_type=float16`, `proper_nouns=1`
- LLM proxy: `cloud_search=codex-subscription`, `immediate_ack=true`
- TTS: `immediate_response_cache.ready=2`

새 PC 또는 AIRI 재설치 후에는 AIRI를 종료하고 설치본 패치를 다시 적용한다.

```powershell
.\patch-airi-native-media-recorder.ps1
.\patch-airi-audio-constraints.ps1
.\patch-airi-voice-input-segmentation.ps1
.\patch-airi-reaction-latency.ps1
.\patch-airi-playback-latency.ps1
```

## 남은 acceptance test

1. AIRI에서 `음유잉여를 웹에서 검색해줘`를 자연스럽게 말한다.
2. 발화 종료부터 `응!` 첫 소리까지 시간을 5회 잰다.
3. transcript가 `음유잉여`로 표시되는지 확인한다.
4. 약 10~20초 뒤 같은 assistant 답변으로 검색 결과가 이어지는지 확인한다.
5. 최근 5회 모두 2.0초 이하인지 확인하고, P50·P95·최악값과 문장 중간 절단·누락 여부를 기록한다.

450ms VAD는 빠른 대신 말 중간의 짧은 쉼을 발화 종료로 오판할 수 있다. 5회 테스트에서 절단이 보이면 600ms로 되돌려 정확도와 지연을 다시 비교한다.

첫 사용자 검증에서는 5개 음성 청크 중 4개가 충분한 RMS·peak를 가졌는데도 Whisper 내부 VAD에서 segment 0개가 됐다. AIRI가 이미 발화를 VAD로 잘라 보내므로, 위 fallback을 적용하고 기존 실패 표본은 재검증 대상에서 제외했다.

계측 수치는 monitor 프로세스 메모리에만 남는다. 테스트 중 monitor를 재시작하면 표본이 사라지므로, 다른 PC에서 장기 검증할 때는 원문·오디오 없이 숫자 이벤트만 영속화하는 후속 작업이 권장된다.
