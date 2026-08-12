# AIRI 로컬 스택 구현 검토 — 코드 실측 감사 (2026-08-07)

- 대상: `airi-local-stack` 저장소 (커밋 36건, 2026-08-05 ~ 08-07, 자체 코드 약 3,500라인 + 서드파티 스냅샷 3종)
- 방법: 병렬 코드 감사 5종(LLM 프록시 / STT / TTS / 설치본 패치 / 계측·문서) + 테스트 4종 실제 실행(27/27 통과) + 핵심 결함 주장 원본 코드 재검증
- 기준 문서: `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md` v2.1, `AIRI-CODE-AUDIT-2026-08-06.md`
- 감사 실행 환경: 별도 PC(원본 계획 문서 보관 PC). 개발 PC 로컬 자산(.venv, 모델, 설치본 패치 상태)은 이 감사에서 직접 확인 불가한 항목을 "확인 필요"로 명시함.

---

## 1. 총평

**설계 방향과 문서 규율은 상급, 실행 계층에 사용자 체감을 직접 막는 결함이 집중.**

- 큰 결정들(GPT-SoVITS v2ProPlus 채택, MOSS RTF 4.687 게이트 탈락, Chatterbox 비활성화, STT CUDA 이전, 선반응 캐시)은 전부 실측 근거를 갖추고 옳게 내려졌다. 문서가 "합성 STT라 완료 아님" 같은 유보를 스스로 명시하는 정직성도 상급.
- 그러나 **서버는 스트리밍하는데 클라이언트가 받지 않고**(TTS 이득 미실현), **STT 필터가 정상 발화를 소리 없이 폐기하는 사각지대**가 있으며(마이크 5회 검증 실패의 유력 원인), **한국어 정규식 처리 3종이 실사용 발화를 훼손**한다("응원할게→원할게"). 이 3가지가 현재 체감 8초와 신뢰성 문제의 본체다.
- 계획 대비: Phase 1 조건부 달성 / Phase 2 미착수 / Phase 3 GPU화 완료·스트리밍 미착수 / Phase 5 진입 조건 충족했으나 미진입 / Phase 6 착수 안 함(오히려 AEC 상시 off로 역행) / 트랙 M(기억 계층) 0% — 구현된 것은 "후보 A + 검색 전용 클라우드 사이드카"이며 후보 D가 아니다.

---

## 2. 계획(v2.1) 대비 진척 매핑

| 계획 항목 | 상태 | 근거 요약 |
|---|---|---|
| Phase 0 계측 | ✅ 대부분 | latency_trace(bounded queue·fail-open·타입 화이트리스트) + monitor + playback 패치. 단 STT 계측이 body read 이후 시작이라 업로드 구간 누락 계상 |
| Phase 1 TTS 교체 | ✅ 조건부 | v2ProPlus streaming_mode=2 실동작, min_chunk 스윕(8/16/24) 근거 보유. 백엔드 첫 청크 P50 374ms. 단 §6 앵커 기준으로는 미달(락+클라이언트 버퍼링) |
| Phase 2 취소 경로 | ❌ 0/3 | /stop 미노출, 세대 비교 없음, GeneratorExit는 계측만. lock 대기 최대 4.2초의 직접 원인 |
| Phase 3 STT | ⚠️ 절반 | CUDA/float16 이전 완료(warm 291ms). 스트리밍 STT 미착수. VAD 튜닝은 계획(600→400 단계)보다 공격적인 450/100ms 일괄 적용 |
| Phase 5 청크 재생 | ❌ 미진입 | 진입 조건(첫 오디오 P50>800ms) 실측 충족. HANDOFF에 AudioWorklet 설계만 존재 |
| Phase 6 half-duplex/barge-in | ❌ + 역행 | 해당 패치 없음. audio-constraints 패치가 AEC 상시 off → Phase 6 1안(재생 구간 한정 AEC)을 선제 차단 |
| 트랙 M 기억 계층 | ❌ 0% | SQLite/임베딩/워터마크 코드 0건(전체 grep). last-10 슬라이스뿐 |
| M+ ④ 반사 응답 | ⚠️ 변형 | 체감 목표는 달성(캐시 WAV 1.4ms). 수단은 계획이 폐기 대상으로 명시한 "고정 대기 멘트"(맥락 리액션 아님) |
| M0 ③ CLI 경유 금지 | ❌ 위반 | 검색이 codex CLI subprocess 경유(실측 11.6~21.3초). 계획서가 TTFT 근거로 금지한 방식 |
| §12 외부 전송 게이트 | ❌ 위반 | 후보 D 게이트 미통과 상태에서 검색 의도 발화 원문 최대 500자가 OpenAI로 전송 + 의도 오탐 다수("리서치 결과 알려줘"도 검색 판정) |

---

## 3. 사용자 체감을 막는 구조 병목 3건

### ① TTS: 서버는 스트리밍하는데 클라이언트가 받지 않는다
- `gpt-sovits/openai_compatible_proxy.py:152` 전역 `TTS_LOCK`을 스트림 전 구간 보유 → 문장 N+1 첫 바이트가 문장 N **전체 생성 완료**를 대기. 실사용 5턴 계측 lock 대기 평균 **2,334ms**(최대 4,209ms) — 최대 단일 병목.
- AIRI 클라이언트는 `AudioBufferSourceNode` 단발 재생(완성 WAV 디코딩 후 재생) → 프록시가 첫 청크를 아무리 빨리 흘려도 TTFA = 총 생성시간.
- 취소 부재(Phase 2)와 결합: 끼어들어도 진행 중 합성이 GPU·락을 끝까지 점유.
- **해소 경로 = Phase 2(/stop 노출 + 세대 비교) + Phase 5(media_type=raw + AudioWorklet). 이 둘 없이 락 제거만 하면 오디오 중첩(웅얼거림)이 재발한다** — 락은 재생 측 순서 보장 부재의 대증요법이었음.

### ② STT: 필터 사각지대가 정상 발화를 소리 없이 폐기
- `stt/openai_stt_server.py:52-61`: quiet 판정(rms<0.01 AND peak<0.08)과 VAD fallback 자격(rms≥0.015 OR peak≥0.15) 사이 **dead band** — 이 구간의 청크는 whisper 내부 VAD가 세그먼트를 지우면 구제 없이 빈 문자열 + HTTP 200. 프로젝트 자체 관측 표본(1.159s/rms 0.00889/peak 0.0932)이 정확히 이 구간.
- fallback 최소 길이 0.6초 → "응"·"아니" 같은 짧은 대답 원천 배제.
- `:325-327` min() 집계: 한 세그먼트만 저신뢰여도 **전체 전사 폐기**.
- 클라이언트 패치가 빈 전사를 침묵 처리 + 빈 전사가 `accepted=true`로 집계 + 거부 시 진단 필드 소거(`:404-405`) → **오폐기의 관측 가능성 0**. "실제 마이크 5회 연속 검증" 미통과의 가장 유력한 잔여 원인.

### ③ 한국어 텍스트 처리: 어절 경계 없는 정규식·치환 3종이 발화를 훼손
- `ollama-proxy/ollama_proxy.py:74-77` `[!,.?\s]*`(0개 허용) → "그래도→도", "응원할게→원할게" (모든 로컬 본답변 경유. 재검증 완료)
- `:163-167` 불용어 `해`·`좀` 무경계 제거 → "해리포터 검색→리포터", "좀비→비" (훼손된 검색어가 외부 전송됨)
- `stt/openai_stt_server.py:91-102` 검색 단어 1개면 문장 전역 치환 → "음료인 것 같은데 검색해줘→음유잉여 것 같은데…"
- 공통 성질: **로그에 안 남고 사용자 귀에만 들리는 손상.** 수정 비용은 셋 다 낮다(경계 조건 1~2줄).

---

## 4. 결함 목록 (CRITICAL·HIGH 전체, MEDIUM 요약)

### CRITICAL

| # | 위치 | 내용 |
|---|---|---|
| C1 | `gpt-sovits/openai_compatible_proxy.py:234-238, 154-156` | **에러 전파 파손**: 백엔드 접속 전에 StreamingResponse(200) 반환, 상태 검사는 제너레이터 내부 → 백엔드 400/예외가 "HTTP 200 + 0바이트"로 둔갑. 반복돼 온 "200인데 무음" 증상의 구조적 원인. `tts.end`도 최소 바이트 검사 없음 |
| C2 | `gpt-sovits/openai_compatible_proxy.py:31-34` | 참조 음성 기본값이 구 경로 `C:\Projects\airi\chatterbox\...` 하드코딩. **실제 기동 체인(start-local-stack.ps1)은 `GPT_SOVITS_REFERENCE_AUDIO`를 설정하지 않음**(설정하는 스크립트는 8891 포트용 별도 파일). C1과 결합 시 전 요청 무음이 되어도 /health는 ok |
| C3 | 설치본 패치 상태 | 감사 PC의 `app.asar`(1.13GB)는 표적 7종 전부 stock, 백업 0개 = **완전 미패치**. 개발 PC 설치본의 패치 적용 여부는 이 감사에서 확인 불가(확인 필요) — **acceptance 측정 전 표적 문자열 존재 여부로 패치 상태를 반드시 검증할 것.** 미패치 상태 측정치는 폐기 대상 |

### HIGH — LLM 프록시 (`ollama-proxy/ollama_proxy.py`)

| # | 위치 | 내용 |
|---|---|---|
| P1 | `:74-77` | strip_leading_reaction 접두사 절단 (§3-③). `[!,.?\s]+`로 수정 |
| P2 | `:163-167` | 검색어 불용어 무경계 제거 (§3-③) |
| P3 | `:42, 546-570` | 검색 실패 시 로컬 EXAONE 폴백 없음 — "찾아볼게" 후 최대 75초 침묵 → 사과 한 줄 |
| P4 | `:363` | `httpx.AsyncClient(timeout=None)` — Ollama 정지 시 SSE 영구 대기, 턴 종료 불가 |
| P5 | `:30-36, 447` | 무인증 catch-all + `allow_origins=["*"]` — 임의 웹페이지가 `/api/delete`로 모델 삭제, codex 프로세스 무제한 스폰 가능(CSRF). 오리진·경로 화이트리스트 필요 |

### HIGH — STT (`stt/openai_stt_server.py`)

| # | 위치 | 내용 |
|---|---|---|
| S1 | `:52-61, 211-224, 305-306` | dead band + fallback 최소 0.6초 (§3-②) |
| S2 | `:325-327` | min() 집계 전체 폐기 (§3-②). 세그먼트별 필터로 전환 |
| S3 | `:91-102` | search_aliases 문장 전역 오보정 (§3-③) |
| S4 | `start-local-stt.ps1:18,31` | CUDA 기동이 gitignore된 `external/GPT-SoVITS/.venv`의 torch DLL에 하드 의존 — fresh clone에서 CUDA STT 기동 불가 |

### HIGH — TTS (`gpt-sovits/`)

| # | 위치 | 내용 |
|---|---|---|
| T1 | `openai_compatible_proxy.py:42,152-154` | 전역 락 직렬화 (§3-①). README "동시 요청 동작" 주장과 정면 배치 |
| T2 | `:224-233` | 캐시 히트는 락 우회 → 이전 턴 오디오 꼬리와 "응!" 중첩 가능(§12 "TTS 겹침 0건" 충돌) |
| T3 | `start-local-stack.ps1:7-9` 외 4파일 | `external/GPT-SoVITS/.venv` 경로 참조 — 현재 레포 레이아웃에 부재. README "한 줄 시작" 재현 불가. 문서 3종의 경로 표기도 3갈래로 상이 |
| T4 | `api_v2.py`(스냅샷) | /stop 미노출 = Phase 2 미이행. TTS.stop()은 존재하나 HTTP 노출 없음 |
| T5 | `benchmark-suite.py:21-58` | "gate suite"가 단정문·exit code 없는 print 스크립트 + 프록시 미경유(9880 직접) + HANDOFF가 무음 원인으로 특정한 prompt_lang=ko 조합으로 측정. **지연 회귀 자동 게이트 부재** |

### HIGH — 설치본 패치

| # | 위치 | 내용 |
|---|---|---|
| A1 | `patch-airi-reaction-latency.ps1:116-123` | transcript flush 1200→**100ms**는 문장 병합 완전 무력화 — 다음 조각 도착(최소 ~750ms) 전 무조건 flush → 문장 중간 500ms 휴지 시 턴 분할. 600~800ms로 복원 권장. (400ms로 바꾸는 transcript-latency.ps1는 중복이며 순서 위반 시 hard fail — 폐기 권장) |
| A2 | `patch-airi-voice-input-segmentation.ps1:116-118` | 900ms 타이머 제거는 진단 자체는 정확하나(아래 §6), VAD 프레임 공급 중단(장치 전환·워클릿 크래시) 시 **음성 입력 영구 잠금** — stock의 자가 복구 안전망을 대체 없이 제거. "VAD 소유 세그먼트 한정 상한 타임아웃(예: minSilence×2)" 형태로 재작성 권장 |
| A3 | 패치 체계 전반 | 백업 = 실행 시마다 1.05GiB 전체 사본(6종 = 6.3GiB, 각기 다른 시점) + 복원 스크립트 부재 + 멱등성 1종 결여(native-media-recorder 재실행 시 실패) + 치환 여유 playback 1바이트/recorder 52바이트. **다음 변경은 물리적으로 in-place 표현 불가 → 소스 빌드 전환 손익분기 도과** |
| A4 | `patch-airi-reaction-latency.ps1` 중 speech_pad 360→120 | **no-op 실측** — 해당 값은 소비되지 않는 이벤트 경로에만 사용. 문서의 지연 개선 주장에서 삭제할 것 |

### MEDIUM (요약 — 상세는 각 파일 감사분)

- **프록시**: 검색 의도 부분일치 오탐("리서치"·"research" 포함 잡담이 외부 전송, §12 위반 확대) / 클라우드 결과에 반말 정규화 미적용(페르소나 붕괴, codex 존댓말 응답 실측) / options(num_ctx·num_gpu)가 OpenAI 경로에서 무시 추정 — /health 표시값은 실효 아님 / 취소 시 업스트림 커넥션 누수 / ack 후 11~75초 SSE 무전송(heartbeat 없음) / codex 프롬프트 인젝션→read-only라도 로컬 파일 낭독·검색 경유 유출 경로 / stream:false·/api/chat 경로는 기능 전체 미적용
- **STT**: 1.5초 경계 비단조(느린 발화가 거부) / max_new_tokens=64 무통보 절단 / 거부 시 진단 소거 / 빈 전사 accepted 집계 / 워밍업이 VAD 경로 미포함(cold +379ms, 회수 가능) / cuDNN 사전점검 누락 / CORS 와일드카드 / OOM 저하 경로 부재 / hotwords에 context 값 상시 주입 / 완성 문장 initial_prompt(환각 유발 패턴) / 강제 종료 시 %TEMP% 음성 잔존 / 로그 무회전
- **TTS**: startup 워밍업이 포트 바인딩 차단(콜드 시 런처 30초 타임아웃 오진) / /health가 참조 부재·캐시 전멸을 ok로 보고, verify 스크립트도 미게이트 / pcm 요청에 WAV 반환 / ACK 문구가 두 파일에 하드코딩된 암묵 계약(변경 시 캐시 100% 미스, 어떤 테스트도 실패 안 함) / 입력 길이 무제한 + 180초 락 점유 / 벤치가 라이브 세션의 단일 슬롯 ref 캐시 축출 가능
- **패치·문서**: AGC off가 저 RMS(0.003~0.019)와 상호작용해 whisper VAD 0-segment(5중 4)의 기여 요인 가능성(A/B 미측정) / 'volume' 소유 세그먼트는 여전히 900ms 절단 / STT 디바이스 표기 stale 문서 3종(CPU INT8 — 그중 하나는 자칭 "기준 문서") / 계획서 스냅샷의 8700G 3곳은 STALE(원본이 최신, 5600X가 맞음) / 대시보드 synthetic 필터는 producer 없는 죽은 코드 / 합성 STT 주입 재현 스크립트 미커밋

LOW급 다수(양 프록시 도달 불가 코드, content-encoding, RIFF data=0 헤더, 포트 기본값 불일치 등)는 생략 — 필요 시 세부 감사분 참조.

---

## 5. 보안·프라이버시 판정

- **프라이버시 기본값: PASS.** 로그 redaction 기본 ON·디버그 오디오 기본 OFF를 코드·기동 스크립트·테스트가 일관 강제. 계측 meta의 int/float/bool 화이트리스트는 텍스트 유출을 구조적으로 차단하는 좋은 설계. 잔여: %TEMP% 잔존(강제 종료 시)·과거 로그 미소거·argparse 경로 미테스트.
- **셸 인젝션: 없음.** codex를 node 직접 실행 + 인자 배열 + stdin 프롬프트로 호출.
- **실질 위험 2건**: ① 두 서버 모두 무인증 + CORS `*` (프록시는 catch-all이라 모델 삭제·구독 소진까지 가능) ② §12 외부 전송 게이트 위반(오탐 포함 발화 원문 전송). 후보 D 게이트 논의 전에 이 둘을 먼저 정리해야 한다.

---

## 6. 잘된 점 (유지·계승할 것)

1. **선반응 구현이 정석**: create_task로 느린 작업 선기동 → ack 1청크 선발행. ack 경로 무블로킹. AIRI marker-parser 5글자 보류를 ACT 토큰으로 flush시킨 해법 + 테스트에 의도 기록.
2. **900ms 절단 진단이 정확**: 원본 0.11.3 `voice-input-session.ts:499-515`에서 볼륨 폴백(900ms)이 VAD(1200ms)를 항상 선점하는 결함 **실재 확인**. 업스트림 테스트도 이 경로 미커버(`volumeFallback: enabled false`만) — **moeru-ai/airi 이슈/PR 기여 가치 있음.**
3. **패치 스크립트 공학 품질**: 경로 화이트리스트·매칭 개수 검증·동일 길이 치환(asar 오프셋 보존)·쓰기 후 재검증. 1GB 아카이브에 올바른 접근.
4. **한국어 g2p 우회 타당**: python-mecab-ko 휠 + eunjeon shim + 실합성 검증. 소스 빌드 회피 최소 우회의 모범. (단 런처에 검사 미배선 — 수동 실행 의존)
5. **문서 정직성**: "합성 STT라 완료 아님"·"5회 검증 대기" 유보가 README까지 일관. 27개 테스트 주장은 실행 재검증 결과 정확히 일치.
6. **테스트가 실측 표본 기반**: STT 필터 테스트 케이스가 실제 관측 RMS/logprob에서 유도됨.

---

## 7. 권고 우선순위 (다음 세션 착수 순서)

1. **[반나절] 한국어 텍스트 손상 3종 수정** (P1·P2·S3) — 비용 최소·체감 최대. 오답 재현 케이스를 테스트로 추가.
2. **[반나절] C1+C2**: 백엔드 첫 응답 확인 후 StreamingResponse 반환(실패 시 502), REFERENCE_AUDIO 존재 검사 startup 추가 + /health degraded + 기동 체인에 env 설정. "무음인데 전부 통과" 조합 제거.
3. **[반나절] STT 오폐기 관측 가능화 + dead band 해소** (S1·S2 + 거부 시 진단 로깅 + 빈 전사 accepted=false) — **마이크 5회 acceptance 재도전은 이것과 C3(패치 상태 검증) 이후에.**
4. **[1일] 검색 경로 정비**: 폴백(P3) + 타임아웃 계층화 + 의도 판정 경계 강화(오탐=외부 전송) + SSE heartbeat. 여유가 되면 codex CLI → Responses API(web_search) 전환 검토(M0 ③ 재정렬).
5. **[1일] 보안 기본선**: 두 서버 CORS 오리진 화이트리스트 + 프록시 허용 경로 화이트리스트 + upstream 타임아웃(P4·P5).
6. **[판단] 소스 빌드 전환 착수** — 패치 6종 누적으로 손익분기 도과(A3). Phase 5(청크 재생)·Phase 6(AEC 동적 토글)은 길이 증가 변경이라 in-place 패치로 불가. 전환 시 VAD·flush 값은 패치가 아니라 `useVoiceInputSession` 옵션 한 줄이 된다. flush 100ms→600~800ms 복원(A1)과 VAD 잠금 안전망(A2)도 이때 함께.
7. **[전환 후] Phase 2+5**: /stop 노출 + 세대 비교 + media_type=raw + AudioWorklet 재생 → 락 제거. lock 대기 2.3초 회수의 유일한 경로.
8. **[백로그] 트랙 M(기억 계층)은 미착수 상태 그대로** — 위 안정화가 끝난 뒤 M0 게이트부터. 现 구성은 "후보 A + 검색 사이드카"임을 문서에 명시해 후보 D 진척으로 오독되지 않게 할 것.

## 8. 계획서(v2.1) 측 반영 사항

- §3 기준선 정정: "1.2초 상수는 VAD 무음 판정뿐" → 실제로는 `flushDelayMs 1200`(index.vue:264)이 별도 존재(2곳).
- Phase 3에 "AIRI VAD ↔ whisper 내부 VAD 이중 게이팅" 항목 추가 — 0-segment(5중 4)의 직접 원인. 클라이언트가 VAD 분할한 청크에는 `vad_filter=False` 기본 검토.
- Phase 0-1 소스 빌드 전환의 우선순위 상향(§7-6 근거).
- §6 앵커 주의: 서버 내부 측정치(STT 291ms, TTS 374ms)는 앵커 구간(vad_speech_end→stt_final, llm_first_clause→audio_play_start)과 다름 — 게이트 판정에 혼용 금지.
- M+ ④ 반사 응답: 현 구현은 고정 멘트 캐시. "맥락 리액션 300ms" 승격은 미달성 상태로 유지.
