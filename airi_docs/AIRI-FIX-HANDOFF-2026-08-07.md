# AIRI 로컬 스택 감사 반영 수정 — 인수인계 (2026-08-07)

> **수신자**: 개발 PC(Ryzen 5 5600X / RTX 3060 Ti 8GB / Windows 11)에서 이 스택을 이어받는 에이전트.
> **작성자**: 계획 문서 보관 PC의 감사·수정 세션. 브랜치 `fix/code-audit-remediation-2026-08-07`에 이 문서와 함께 수정 전체가 커밋되어 있다.
> **전제 문서**: 결함의 근거·실측치는 `AIRI-LOCAL-STACK-REVIEW-2026-08-07.md`(코드 감사 보고서, 같은 폴더)에 있다. 이 문서는 "무엇을 왜 어떻게 고쳤고, 너는 무엇을 해야 하는가"만 다룬다.

---

## 0. 프로젝트 방향 (사용자 재확인, 2026-08-07)

1. **최우선 목표 = 응답 지연 최소화** — 뉴로사마처럼 준실시간 응답. 모든 트레이드오프는 이 기준으로 판단한다.
2. **장기 기억·지능 보존 = 로컬 RAG + DB(기억 계층)** — 지연을 줄이는 과정에서 기억과 지능이 희생되지 않도록 벡터 RAG + 관계 1-hop DB가 담당한다. 설계는 `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md` 트랙 M과 `AIRI-MEMORY-TECH-REFERENCE.md`에 완비되어 있으나 **구현은 아직 0%다.** 이번 수정은 지연 파이프라인 안정화까지이고, 트랙 M이 다음 큰 마일스톤이다.

## 1. 이번 브랜치에서 바뀐 것 (요약)

감사에서 CRITICAL 3·HIGH 18·MEDIUM 다수가 확인됐고, 이 브랜치는 그중 **코드로 즉시 고칠 수 있는 전부**를 수정했다. 영역별 상세는 §3~§6, 남긴 것은 §7.

| 영역 | 핵심 수정 | 지연 관점 효과 |
|---|---|---|
| ollama-proxy | 한국어 절단·검색어 훼손 수정, 검색 폴백+타임아웃+heartbeat, 경로·Origin 화이트리스트 | 발화 품질 회복(재질문 루프 제거), 75초 침묵 시나리오 제거 |
| stt | 필터 dead band 해소, 세그먼트별 신뢰도 필터, 오보정 경계 검사, VAD 경로 워밍업, CUDA 경로 견고화 | 무음 폐기로 인한 턴 소실 제거, cold +379ms 회수 |
| gpt-sovits | 에러 전파 수복(200 무음 근절), 참조 음성 경로 수복, **GeneratorExit→백엔드 절단 = 실효 취소**, 백그라운드 워밍업, 게이트 실질화 | 끼어들기 시 락·GPU 조기 해제(락 대기 평균 2.3s의 주요 회수 수단) |
| 설치본 패치 | 볼륨 폴백 900ms → **분기 제거 대신 2700ms 연장**(영구 잠금 위험 제거), flush 100→400ms(문장 병합 복원), no-op 패치 제거, pristine 단일 백업 + 일괄 적용/복원 스크립트 | 절단 버그 해소 유지 + 안전망 보존, 백업 6.3GB→1.05GB |
| 문서 | STT CUDA 전환 반영(스펙 SSoT 동기화), stale 문서 상단 경고, 계획서 스냅샷 갱신(8700G→5600X 정정판), 감사 보고서 반입 | — |

## 2. 네가 개발 PC에서 해야 할 일 (순서대로)

1. **브랜치 체크아웃**: `git fetch && git checkout fix/code-audit-remediation-2026-08-07`.
2. **테스트 재실행**: 4개 테스트 파일 전부 (`ollama-proxy\test_ollama_proxy.py`, `stt\test_transcription_filter.py`, `gpt-sovits\test_openai_compatible_proxy.py`, `latency-monitor\test_monitor_server.py`). 이 PC에서는 전부 통과했다(§8) — 그쪽 venv에서도 통과해야 한다.
3. **설치본 패치 상태 확정**: 감사 결과 이 PC의 app.asar는 완전 미패치 stock이었다. 그쪽 설치본도 **가정하지 말고** `apply-airi-patches.ps1`을 실행해 최종 검증 표로 확정하라. 구버전 패치(vad 분기 제거형)가 적용돼 있으면 `restore-airi-original.ps1`로 pristine 복원 후 재적용.
   - 주의: 이번 패치 세트는 구성이 바뀌었다 — voice-input-segmentation은 분기 제거가 아니라 타이머 연장(900→2700ms), reaction-latency의 speech padding 항목은 no-op으로 판명되어 제거, flush는 400ms, transcript-latency는 deprecated(빈 스텁).
4. **스택 기동**: `start-airi-local-stack.ps1`. GPT-SoVITS 클론 위치가 다르면 `GPT_SOVITS_ROOT` env로 지정(후보 자동 탐색 있음). 참조 음성은 저장소 상대 경로가 기본이 됐고 `/health`의 `reference_audio_found`로 확인 가능.
5. **마이크 5회 acceptance 재도전**: 이제야 전제가 갖춰졌다 — (a) 패치 상태 확정됨 (b) 무음 폐기가 관측 가능해짐(빈 전사 accepted=false + 거부 사유 로깅) (c) 200 무음 증상 근절. 실패하면 이번에는 로그에 거부 사유·신뢰도가 남는다.
6. **결과 기록**: acceptance 결과와 구간별 수치를 HANDOFF 관례대로 기록. 합성 STT 시각 수치는 acceptance에 쓰지 말 것(감사 보고서 §계측 참조).

## 3. ollama-proxy 수정 내역 (`ollama_proxy.py`, 테스트 7→26개)

| # | 위치 | 수정 | 왜 |
|---|---|---|---|
| F1 | `:164-168` | `LEADING_REACTION_RE`를 `(?:[!,.?~…\s]+|$)`(구분자 1+ 또는 문장 끝)로, 대안 순서 `응응\|응` 최장 우선 | `[!,.?\s]*` 0개 허용이 "그래도→도", "응원할게→원할게" 절단. 절단 4종 불변·정상 제거 4종 유지 테스트 고정 |
| F2 | `:170-176, 257-271` | 검색어 불용어를 룩어라운드 `(?:(?<=\s)\|^)…(?=\s\|$)`로 어절 전체 일치 시만 제거. 빈 쿼리는 검색 분기 대신 로컬 일반 분기로 라우팅 | 맨몸 `해`·`좀`이 "해리포터→리포터", "좀비→비" 훼손. 훼손된 검색어가 외부 전송되던 문제 동시 해소 |
| F3 | `:36-38, 489-536, 676-768` | codex 타임아웃 75→30초, 실패·타임아웃 시 로컬 EXAONE 폴백("검색이 안 돼서 아는 만큼만 말할게. …"), ack 후 5초 간격 SSE 주석 heartbeat | "찾아볼게" 후 최대 75초 침묵→사과 시나리오 제거. 라이브 실측: ack 276ms, heartbeat 정상 |
| F4 | `:42-44, 479, 864-876` | `httpx.Timeout(connect=5, read=120, write=30, pool=5)` + 타임아웃 시 전용 문구 청크 + `[DONE]` 정상 종료 | `timeout=None`이라 Ollama 정지 시 SSE 영구 대기·턴 미종료 |
| F5 | `:46-115` | CORS `*` 제거 → `AIRI_PROXY_ALLOW_ORIGINS` 접두사 allowlist(기본 `app://.,file://,http://localhost,http://127.0.0.1`), Origin 불일치 403 미들웨어, 경로 화이트리스트(9개 + `/v1/` 접두사, `..` 차단) | 임의 웹페이지가 `/api/delete`로 모델 삭제·codex 스폰 가능하던 CSRF 표면 제거. 라이브 실측: evil origin/`/api/delete` 403, preflight 정상 |
| F6 | `:139-156` | 검색 의도: 명사 앞 룩비하인드 + 명령형 어미 또는 단독 어절일 때만 매칭 | "리서치 자료 정리해줘"·"검색엔진 이야기해줘" 오탐 → 원문 500자 외부 전송되던 문제. 오탐 4종 False·정상 5종 True 고정 |
| F7 | `:209-244, 273-286` | 클라우드 검색 결과에도 `normalize_dialogue`(반말화·장식 제거) 적용. 문장 예산만 3문장 유지(출처명 보존) | codex가 존댓말로 답하는 실측 → 검색 답변만 페르소나 붕괴하던 문제 |
| F8 | `:489-506, 834-847` | 취소 시 `discard_upstream_task()` — cancel 후 done-callback으로 열린 응답 `aclose()` 보장 | 끼어들기 잦은 워크로드에서 httpx 커넥션 풀 점진 고갈 |
| F9 | `:277-286, 817, 939` | `message_content()` 헬퍼로 `content: null` → `""` (스트림·논스트림 양쪽) | AIRI가 "None"이라고 발화하던 결함 |
| F10 | `:388-390` | `asyncio.TimeoutError` 명시 포함 | Python 3.10 이하에서 codex 타임아웃 미포착 → 프로세스 잔존 |
| F12 | `start-local-ollama-proxy.ps1:6-38` | python 후보 체인: env `AIRI_STACK_PYTHON` → repo `.venv` → chatterbox `.venv` → PATH(경고) | `chatterbox\.venv` 하드 의존 — fresh clone에서 무조건 throw였음 |

보류: 도달 불가 코드는 주석만 표시(삭제는 별도 승인), `extract_search_query`의 조사 절단(`을/를/은/는/이/가$`)은 기존 동작 유지 — "장미가" 단일 어절 검색어 끝음절 절단 잠재 위험 있음(후속 과제), `~습니다` 일반 활용형은 반말 변환표 밖(별건).

## 4. stt 수정 내역 (`openai_stt_server.py` 외, 테스트 12→28개)

| # | 위치 | 수정 | 왜 |
|---|---|---|---|
| F1 | `:82-89, 366-387, 457-462` | quiet 판정과 fallback 자격을 단일 함수 `is_quiet_audio()`로 통합(자격 = not quiet AND duration≥0.3, 종전 0.6) — dead band 구조적 재발 불가. 정의 일치를 검증하는 lock 테스트 포함 | 두 임계 사이 청크(감사 표본 3종 전부)가 구제 없이 빈 200으로 폐기 → 턴 소실. "응"·"아니" 단답도 원천 배제였음 |
| F2 | `:478-508, 579-591` | 저신뢰 필터를 min() 전체 폐기 → 세그먼트별 제외(전부 저신뢰일 때만 전체 거부). 재조립 시 고유명사 보정 재적용. 제외 수 `low_confidence_segments` 로깅 | 한 세그먼트(-1.24) 때문에 고신뢰(-0.31) 문장까지 통째로 버려짐 |
| F3 | `:130-244` | 고유명사 치환에 어절 경계 검사(앞뒤 한글이면 불일치) + search_aliases는 검색 키워드 2어절 이내만 치환 | "음료인지→음유잉여지" 문장 전역 오보정. 오보정 3종 불변·정상 보정 유지 테스트 고정 |
| F4 | `:588-600, 640-648` | 거부 시에도 세그먼트 수·min avg_logprob·max no_speech_prob 보존 로깅 + latency 메타에 `rejected_reason` | 거부된 케이스에서만 진단 근거가 소거돼 임계 튜닝 불가였음 |
| F5 | `:583-586` | 빈 전사 → `accepted=false`, `reason="empty_transcription"` (HTTP 계약 불변) | 무음 폐기가 수용률 지표에서 은폐 → 5회 acceptance 판정 왜곡 |
| F6 | `:455-474` | 글자수 상한을 `max(18, 14×duration)` 연속 함수로 통합(사유 문자열 호환 유지) | 1.49s/19자 거부·1.51s/24자 통과의 비단조 역전. 1.3~1.7초 구간이 소폭 엄격해지는 트레이드오프는 의도됨 |
| F7 | `:253-284` | 워밍업에 vad_filter=True 패스 추가(+실제 hotwords) — False 패스도 유지(무음 워밍업 오디오라 True만으로는 encoder 미기동) | 첫 실요청에서 Silero ONNX 초기화 +379ms 실측 → 기동 시점으로 이동 |
| F8 | `:33-68` | Origin allowlist(env `AIRI_STT_ALLOW_ORIGINS`) + 403 미들웨어. `localhost.evil.example` 우회 차단(호스트 경계 고정), 빈 allowlist는 fail-closed | CORS `*` + 무인증 |
| F9 | `requirements.txt` | `av`, `numpy` 직접 의존 명시 | 전이 의존으로만 유입 — faster-whisper 변경 시 조용히 파손 |
| F10 | `:92-94` | initial_prompt를 완성 문장 → 어휘 나열형("한국어 일상 대화. 아이리, AIRI.") | 완성 문장 프롬프트는 애매한 오디오에서 그대로 되뱉는 환각 패턴 |
| F11 | `start-local-stt.ps1` | python·CUDA DLL 후보 체인(env 오버라이드 포함), cublas+cuDNN 9 동시 검사, cpu 지정 시 int8 자동 전환 | gitignore된 타 프로젝트 venv 하드 의존 → fresh clone에서 CUDA 기동 불가였음 |
| F12 | `record-direct-microphone-test.ps1` | 출력 디렉토리 자동 생성, dshow 장치 파라미터화 | fresh clone 실패·타 PC 이식 불가 |

알려진 트레이드오프(의도된 판단): ① F3의 어절 경계 검사로 **조사 결합형은 미보정**된다("음유잉어를 검색해줘" 형태) — 오보정(틀린 발화 출력)보다 미보정(원문 유지)이 안전하다는 판단. 완화하려면 `is_word_boundary_match`의 후행 검사 한 곳만 조정하면 된다. ② F1로 fallback 재전사 빈도가 늘어 무음 다발 구간 GPU 점유 소폭 증가 가능 — latency-monitor로 관측할 것. ③ F2 파생: 세그먼트 일부 제외 시 응답 `text`와 `segments` 배열이 불일치(계약 유지 우선, 후속 판단 항목).

## 5. gpt-sovits·런처 수정 내역 (`openai_compatible_proxy.py` 외, 테스트 3→21개 + 뮤테이션·라이브 검증)

| # | 위치 | 수정 | 왜 |
|---|---|---|---|
| F1 | `:183-231, 333-410` | 락·백엔드 접속을 핸들러로 이동 — 상태 확인 후 비200이면 **502 JSON**, 200일 때만 스트리밍 시작. 무음 본문(≤44바이트)은 error 기록, 중도 절단은 명시적 RuntimeError | 백엔드 실패가 "200 + 0바이트"로 둔갑하던 구조적 원인("200인데 무음" 반복 증상). **주의: 락 취득(핸들러 스레드)과 해제(스트리밍 스레드)가 다른 스레드 — TTS_LOCK은 owner-bound가 아닌 순수 Lock이어야 하며 release는 idempotent 가드 필수(주석 참조)** |
| F11 | `:301-321` | **실효 취소**: 클라이언트 절단 시 백엔드 스트림 close + 락 해제를 `_EngineStreamingResponse.__call__`의 finally에서 수행. 실측: 백엔드 "3/20 청크에서 생성 중단", 다음 문장 대기 0초 | 끼어들기 시 진행 중 합성이 GPU·락을 끝까지 점유(락 대기 평균 2.3s의 주요 원인). **제너레이터 finally 방식은 동작하지 않음** — Starlette는 절단된 body iterator를 닫지 않고 방치(라이브로 재현: 다음 요청 60초 타임아웃). ASGI `__call__`만이 모든 경로에서 결정론적 해제 지점. keep-alive 커넥션 폐기는 의도된 트레이드오프(docstring) |
| F2 | `:33-34, 74-99, 163-180` + ps1 | 참조 음성 기본값을 저장소 상대 경로로, startup 존재 검사 + `/health`에 `reference_audio_found` 노출·미발견 시 `degraded`, 기동 체인에서 env 설정, verify 스크립트가 ok·참조·캐시 3종 게이트 | 구 PC 절대경로 하드코딩 + 기동 체인 env 미설정 → 완전 무음 스택이 모든 헬스체크를 통과하던 조합 |
| F3 | ps1 3종 + `benchmark-moss-onnx.py` | GPT-SoVITS 루트 후보 체인(env `GPT_SOVITS_ROOT` → repo/external → 부모/external → `C:\Projects\airi\external\GPT-SoVITS`). 클론 판정(api_v2.py)과 venv 판정을 분리해 각각 다른 안내 | fresh clone에서 "한 줄 시작" 재현 불가였음. 클론은 있는데 venv만 없는 경우의 오진 방지 |
| F4 | `:163-180` + ps1 | 워밍업을 데몬 스레드로(포트 바인딩 실측 0.58초), `/health`에 `warming` 단계 | 동기 워밍업(최대 2×180초)이 바인딩을 막아 런처 30초 대기가 오진 |
| F5/F7/F8 | `:44, 50, 416` 외 | response_format은 wav만(그 외 400), 입력 300자 상한(env 조정 가능), 백엔드 타임아웃 180→60초, 포트 기본값 8891→8880 통일 | pcm 헤더 노이즈 위험 / 긴 입력 1건이 180초 락 점유 / stop 스크립트가 8891 프록시를 못 죽이던 불일치 |
| F6 | `test_openai_compatible_proxy.py` | ACK 계약 테스트 — ollama_proxy.py를 ast 파싱해 ACK 문구와 TTS 캐시 문구의 집합 일치 검증 | 두 파일의 하드코딩 암묵 계약 — 문구 변경 시 캐시 100% 미스인데 어떤 테스트도 못 잡았음 |
| F9 | `benchmark-suite.py` | 기본 프록시(8880) 경유, 직접 모드도 `build_backend_payload()` 재사용으로 프로덕션과 바이트 동일, `--gate-first-ms`/`--gate-min-bytes` + FAIL 시 exit 1 | "gate suite"가 게이트가 아니었음(단정·exit code 없음, 무음 유발 프롬프트 조합으로 측정) |
| F10 | 루트 런처 2종 | 존재하지 않는 health 키 참조 수정, 기능 비대칭 주석화 | VoiceReference가 항상 공백으로 출력돼 참조 부재를 가림 |

검증: 뮤테이션 테스트(상태검사 스킵·락 미해제·plain StreamingResponse 되돌리기 → 전부 테스트 FAILED 확인) + 라이브 uvicorn 통합(모의 백엔드: 502 전파, 취소 후 즉시 다음 문장, 캐시 히트 16~26ms). **F11 테스트는 `asyncio.run()`을 쓰면 안 됨** — 종료 시 asyncgen 정리가 버그를 은폐한다(테스트 주석 참조). 보류: 전역 락 자체는 유지(§7), `tts.cancelled` 전용 phase는 latency-monitor의 PHASES 화이트리스트 확장이 선행돼야 해서 현재는 `error`+`client_cancelled=1` 메타로 관측.

## 6. 설치본 패치 수정 내역 (ps1 6종 + 신규 2종, 합성 설치본 10개 시나리오 검증)

| 스크립트 | 수정 | 왜 |
|---|---|---|
| `patch-airi-voice-input-segmentation.ps1` | **접근 교체**: "vad" 분기 제거 → `var DEFAULT_VOLUME_FALLBACK_STOP_DELAY_MS = 900;`의 `= 900`→`=2700` 동일 길이 치환. 구버전 패치 마커 감지 시 restore 안내 후 중단(-Force 우회) | 분기 제거는 VAD 정지(장치 전환·워클릿 크래시) 시 녹음 종료 주체가 사라져 **음성 입력 영구 잠금**. 타이머 연장은 VAD 정상 시 450ms가 항상 선행(선점 절단 소멸) + VAD 사망 시 2700ms 안전망 보존. 표적은 stock asar 실측 1건(870,122,206, 미실행 TS 사본과 구분) |
| `patch-airi-reaction-latency.ps1` | VAD 1200→450 유지 / speech_pad 360→120 **제거**(no-op 판정 — 소비되지 않는 이벤트 경로) / flush 표적 **400ms**(old 후보 1200·400·100 인식) | flush 100ms는 다음 STT 조각 도착(~750ms)보다 무조건 먼저 flush → 문장 병합 완전 무력화. 700ms+는 매 턴 과지불. 400ms가 균형점 |
| `patch-airi-audio-constraints.ps1` | **[계획 외 HIGH 발견] 원래부터 동작 불가였음** — here-string이 파일 개행(CRLF)을 표적에 포함해 LF 번들과 영원히 불일치(stock 실측: CRLF 형태 0건, LF 형태 2건). 명시 이스케이프 단일행 문자열로 교체 | "문서는 적용했다는데 설치본은 stock"이던 모순의 부분 원인. 개발 PC에서도 이 스크립트는 실패했을 것 |
| `patch-airi-transcript-latency.ps1` | deprecation 스텁(구 파라미터 수용, 안내 출력 후 exit 0) | reaction-latency에 통합. 순서 위반 시 hard fail 유발하던 중복 제거. 기존 문서의 호출 절차도 무해하게 통과 |
| `patch-airi-native-media-recorder.ps1` | 멱등성 추가: 치환본 고유 문자열(`audioBitsPerSecond:128e3`, stock 0건 실측) 감지 시 exit 0. 검사를 백업 블록보다 앞에 배치 | 유일하게 재실행 시 실패하던 스크립트. 이미 패치된 asar를 pristine으로 오인 백업하는 것도 방지 |
| 6종 공통 | 단일 `app.asar.backup-pristine` 규약(부재+stock일 때만 1회 생성, 비-stock이면 중단), AIRI 프로세스 실행 검사, 설치본 검증을 경로 하드코딩 → `airi.exe`+`resources` 구조 검사로 | 실행 시마다 1.05GiB 사본 6개(6.3GiB)·시점 불일치 백업·롤백 불능 문제 해소. `-InstallDir` 지원 |
| `apply-airi-patches.ps1` **(신규)** | 일괄 적용 오케스트레이터: 프로세스 검사 → 전 표적 단일 패스 스캔 → pristine 백업 → 5종 순차 적용 → 최종 재스캔 8행 PASS/FAIL 표, 실패 시 exit 1 | **acceptance 측정 전 패치 상태 확정은 반드시 이 스크립트의 최종 표로** |
| `restore-airi-original.ps1` **(신규)** | pristine 복원(SHA-256 검증, 동일하면 no-op) | 복원 경로가 아예 없었음 |

검증: 8종 전부 PowerShell AST 파싱 오류 0건. 실제 asar는 읽기 전용 스캔만(쓰기 0회) — 합성 설치본으로 최초 적용/멱등 재실행/복원/구버전 감지/비-stock 중단/실행 중 차단 10개 시나리오 전부 통과. stock asar 표적 실측표는 워커 검증 로그 기준이며 오프셋까지 스크립트 주석에 반영돼 있다.

## 7. 의도적으로 고치지 않은 것 (오해 금지)

| 항목 | 이유 |
|---|---|
| TTS 전역 락(문장 직렬화) 자체 | 락 제거는 클라이언트 청크 재생(Phase 5)과 서버 취소(Phase 2) 없이 하면 오디오 중첩(웅얼거림)이 재발한다. 이번엔 "끊긴 스트림의 백엔드 전파"(실효 취소)까지만. 락 해체는 Phase 2+5와 함께. |
| AIRI 클라이언트 완성 버퍼링 | app.asar in-place 패치로는 코드 증가 변경이 불가(치환 여유 1~52바이트). **소스 빌드 전환이 선행 조건** — 감사 보고서 §7-6. |
| 기억 계층(트랙 M) | 미착수 상태 그대로. 현 구성은 "후보 A + 검색 사이드카"이며 후보 D가 아니다. 파이프라인 안정화(§2의 5) 통과 후 트랙 M0 게이트부터 시작하라. |
| codex CLI 검색 경로 자체 | 폴백·타임아웃·heartbeat로 보강했지만 CLI 경유(실측 11.6~21.3초)라는 구조는 그대로다. 계획서 M0 ③ 기준 재평가(Responses API + web_search 직접 호출) 후보로 남긴다. |
| 프록시 dead code (`to_openai_sse` 등) | 도달 불가 확인됐으나 외과적 변경 원칙상 삭제 보류(주석만 표시). |

## 8. 이 PC에서의 검증 증거 (2026-08-07, 커밋 직전 실행)

| 스위트 | 수정 전 | 수정 후 | 결과 |
|---|---|---|---|
| `ollama-proxy\test_ollama_proxy.py` | 7 | 26 | OK (0.24s) |
| `stt\test_transcription_filter.py` | 12 | 28 | OK |
| `gpt-sovits\test_openai_compatible_proxy.py` | 3 | 21 | OK (0.25s) |
| `latency-monitor\test_monitor_server.py` | 5 | 5 | OK (무수정 회귀 확인) |
| **합계** | **27** | **80** | **전부 통과** |

테스트 외 검증: ① 프록시·STT — 라이브 uvicorn으로 SSE 플러시(ack 276ms)·heartbeat·403 게이트·CORS preflight 실측 ② TTS — 뮤테이션 3종(버그 되돌리기 → 테스트 FAILED 확인) + 라이브 통합(502 전파, 취소 후 다음 문장 대기 0초, 캐시 히트 16~26ms, 포트 바인딩 0.58초) ③ 패치 — 합성 설치본 10개 시나리오(최초 적용 8/8 PASS·멱등 재실행·복원·구버전 감지·비-stock 중단·실행 중 차단) + 실제 stock asar 읽기 전용 표적 스캔(쓰기 0회) ④ ps1 전체 — PowerShell 5.1 AST 파싱 오류 0건.

**미검증(개발 PC에서 해야 함)**: 실제 GPT-SoVITS·Ollama·faster-whisper를 붙인 end-to-end(이 PC에는 venv·모델·참조 WAV가 없음 — gitignore 정책), 실제 마이크 5회 acceptance, F7 워밍업 절감(+379ms 회수) 실측, CUDA 후보 체인의 실동작.

## 9. 다음 로드맵 (지연 목표 기준 우선순위)

1. **소스 빌드 전환** (Phase 0-1) — 패치 6종 누적으로 in-place 패치는 물리 한계 도달. 전환 시 VAD·flush 값은 `useVoiceInputSession` 옵션 한 줄이 된다.
2. **Phase 2+5**: GPT-SoVITS `/stop` 노출 + 세대 비교 + `media_type=raw` + AudioWorklet 청크 재생 → 전역 락 해체. 락 대기 평균 2.3s 회수의 본체.
3. **트랙 M**: M0 게이트(클라우드 TTFT·임베딩 벤치) → M1 프록시 확장 → M2 기억 파이프라인(SQLite 벡터+관계 1-hop, 워터마크 절삭, Stage A/B 추출 — `AIRI-MEMORY-TECH-REFERENCE.md`에 프롬프트·스키마·상수 전부 있음).
4. 업스트림 기여: 볼륨 폴백 900ms 선점 결함은 moeru-ai/airi v0.11.3에 실재 확인 — 이슈/PR 가치 있음(재현 테스트: `voice-input-session.test.ts`에 `volumeFallback: { enabled: true }` 케이스 추가).
