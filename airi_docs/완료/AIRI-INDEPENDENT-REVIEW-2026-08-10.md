# AIRI 주말 작업 독립 검토 — 2026-08-10

- **대상 브랜치**: `fix/code-audit-remediation-2026-08-07` (HEAD `05bbafe`)
- **검토 범위**: `1d8a720..HEAD` — 127커밋 / 176파일 / **+58,407 −405**
- **검토 주체**: Claude(Opus 5) 오케스트레이터 + 병렬 감사 에이전트 14 + 목표 추출 에이전트 6 (누적 2.1M 토큰, 도구 호출 798회)
- **검토 성격**: **읽기 전용 감사**. 이 문서 2종 작성 외에 소스·설치본·서비스·AIRI 아카이브를 일절 변경하지 않았습니다. 실제 마이크 입력, 모델 호출, 네트워크 수집을 수행하지 않았습니다.
- **이 문서의 위치**: 코덱스 세션 산출물에 대한 **외부 검토 기록**입니다. 브랜치 계약을 정의하지 않으며, 기존 핸드오프 문서를 대체하지 않습니다.
- **데이터 부록**: `AIRI-INDEPENDENT-REVIEW-DATA-2026-08-10.md` (신설 목표 150건 전수 · MED/LOW 발견 61건 전문 · 축별 총평)

---

## 0. 요약

주말 작업은 **작업량 최상위, 개별 코드 품질 상급, 검증 체계 자기기만, 방향은 절반**입니다.

사용자가 승인한 신규 로드맵(EXAONE 성장 전략 G0~G6, 모델 커스터마이징 C0~C5)에 비추면 거버넌스·평가·정직성 작업은 **정당한 실행**이며, 이를 "범위 이탈"로 볼 수 없습니다. 이 검토의 초기 채점은 그 로드맵을 읽지 못한 상태에서 산출돼 틀렸고, §3.3에서 정정합니다.

그러나 두 가지는 어떤 목표 문서로도 방어되지 않습니다.

1. **1순위인 응답 지연이 개선이 아니라 후퇴했습니다.** 선반응 발화가 제거돼 체감 첫 반응 수단이 사라졌고(`ALIGN-02`, CRITICAL), 그라운딩 재시도가 직렬 2차 LLM 왕복 최대 +5초를 매 턴 추가하며(`ALIGN-03`, CRITICAL), 직전 감사가 최대 단일 병목으로 지목한 TTS 전역 락은 `gpt-sovits/` 디렉터리 **127커밋 0변경**으로 방치됐습니다.
2. **스스로 만든 CI 게이트가 Python 테스트 전량을 제외했습니다.** 그 결과 실패 2건이 도입 커밋 `a7412af`부터 **126커밋 동안 방치**됐고, 커밋된 패치 7종 중 3종이 적용 불가 상태로 남았는데 적용성 검사는 CI에서 한 번도 실행된 적이 없습니다.

두 번째가 더 무겁습니다. 코드 결함은 고치면 되지만 **결함을 못 보게 만드는 게이트**는 이후 모든 작업의 신뢰도를 오염시키며, 특히 G3(평가·데이터 플라이휠)를 목표로 선언한 프로젝트에서는 목표 자체와 모순됩니다.

---

## 1. 실측 검증 결과

검토 착수 시점에 브랜치를 pull하고, 문서가 지정한 게이트와 그 밖의 스위트를 모두 실행했습니다.

| 검증 | 명령 | 결과 |
|---|---|---|
| 작업 트리 | `git status --short` | clean |
| whitespace | `git diff-tree --check --no-commit-id -r HEAD -- . ':(exclude)airi_docs/patches/*.patch'` | PASS (exit 0) |
| 오프라인 체크포인트 | `.\test-current-checkpoint.ps1` | **PASS** |
| sender 계약 | `node --test test-send-airi-local-text.mjs` | **26/26 PASS** |
| **Python 스위트** | `cd ollama-proxy; python -m pytest -q` | **2 failed / 593 passed / 1 skipped** (330 subtests 별도 통과, 40.7초) |

문서가 "minimum reproducible checkpoint"로 제시한 3개 명령은 전부 통과합니다. **통과하지 않는 것은 그 3개에 포함되지 않은 스위트뿐입니다.**

### 1.1 실패 2건은 도입 시점부터 실패했습니다

두 실패 모두 커밋 `a7412af`(주말 두 번째 커밋, "feat: checkpoint local memory voice and broadcast runtime")에서 도입됐습니다. 해당 커밋을 분리 워크트리(`git worktree add --detach`)로 체크아웃해 재현한 결과 **그 시점부터 이미 실패**했습니다.

회귀가 아니라 **실패하는 테스트가 커밋된 것**이며, 이후 126커밋 동안 스위트가 재실행되지 않았습니다.

**실패 ①** `test_knowledge_store.py::KnowledgeStoreTests::test_approved_manifest_uses_review_date_not_claimed_source_publication`

```
FileNotFoundError: [Errno 2] No such file or directory:
  'C:\Projects\airi-local-stack\ollama-proxy\runtime\approved-knowledge-2026-08-09.json'
```

해당 경로는 `.gitignore:50`의 `ollama-proxy/runtime/`으로 제외돼 있습니다. 테스트와 그 `.gitignore` 줄이 **동일 커밋 `a7412af`에서 함께 들어왔습니다**. 따라서 클린 체크아웃에서 영구 실패이며, 승인 지식 시드 9건은 재생성 수단조차 없습니다 — 승인 근거 문서(`AIRI-APPROVED-KNOWLEDGE-2026-08-09.md`, 총 29줄)는 출처 URL 표와 검토 원칙만 담고 본문·`answer_summary`·콘텐츠 SHA-256을 포함하지 않으며, 해당 JSON을 만드는 스크립트가 레포에 없습니다. (부록 B `DOC-07`·`MEM-07`)

**실패 ②** `test_ollama_proxy.py::MemoryProxyIntegrationTests::test_first_raw_watchdog_bounds_a_stream_that_never_starts`

```
self.assertTrue(chat.response.closed)
AssertionError: False is not true
```

이것은 테스트 하네스 결함이 아니라 **실제 프로덕션 결함**입니다. 아래에서 계측으로 확정했습니다.

### 1.2 워치독 누수의 근본 원인 (직접 계측 확정)

읽기 전용 계측(`emit_latency_event` 가로채기 + `chat.requests` 관찰)으로 실행 경로를 특정했습니다.

| 관찰 | 값 | 해석 |
|---|---|---|
| `len(chat.requests)` | **1** | 업스트림 `send()`가 실제로 실행되어 응답 객체를 반환함 |
| 방출된 meta | `upstream_response_headers_timeout: 1` | 그럼에도 워치독은 **헤더 타임아웃**으로 판정 |
| `chat.response.closed` | **False** | 손에 쥔 응답을 **닫지 않고 버림** |
| 공개 출력 | `"답이 늦어져서 잠깐 멈췄어."` | 사용자에게는 정상적인 폴백이 나감 |

같은 파일 `ollama-proxy/ollama_proxy.py:4054`에 이 문제를 위한 헬퍼가 **이미 존재**하며, 독스트링이 정확히 이 상황을 기술합니다.

> *"Cancel an upstream request and close whatever response it still lands. Cancelling alone leaks the connection: httpx may already have returned an open streaming response that nobody will read."*

그런데 `ollama_proxy.py:5318`의 헤더 대기 분기만 이 헬퍼를 호출하지 않고 `asyncio.wait_for`의 내부 취소에 의존합니다. `:5320-5322`의 주석은 다음과 같이 주장합니다.

> *"wait_for cancels and awaits the in-flight send task, so a stalled header acquisition cannot continue consuming the local Ollama connection after the public terminal."*

**송신이 성공한 경우에는 거짓입니다.** 취소가 도달하기 전에 태스크가 완료되면 열린 스트리밍 응답이 회수되지 않은 채 버려집니다. 프로덕션 기본값(`AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=8`)에서는 발생 창이 좁지만, 부하 상황에서 커넥션 고갈로 이어질 수 있는 실재 누수입니다.

**최소 수정**: `except asyncio.TimeoutError:` 블록 진입 직후 `discard_upstream_task(send_task)` 호출 1줄.

부수적으로, 이 테스트가 패치하는 타임아웃 0.01초는 Windows/Python 3.12의 `time.monotonic()` 해상도(15.625ms)와 asyncio 이벤트 루프의 `_clock_resolution` 보정 때문에 **첫 루프 이터레이션에서 무조건 만료**됩니다. 즉 테스트는 결정론적으로 헤더 타임아웃 분기를 타며, 그 분기의 정리 누락을 정확히 겨냥합니다. (부록 B `LAT-01`·`LAT-02`)

### 1.3 CI가 이 실패를 구조적으로 못 보게 돼 있습니다

`.github/workflows/remediation-checkpoint.yml`이 실행하는 것은 두 가지뿐입니다.

1. `git diff --check` / `git diff-tree --check` 기반 committed whitespace 검사 (패치 아티팩트 제외)
2. `.\test-current-checkpoint.ps1`

그리고 `test-current-checkpoint.ps1:7-13`이 호출하는 것은 다음 넷입니다.

- `test-patch-manifest.ps1` — 패치 아티팩트 3종의 크기·SHA-256 대조
- `test-patch-entrypoints.ps1` — 자식 스크립트의 가드 문자열 존재 확인
- `test-patch-applicability.ps1` — **인자 없으면 SKIP(inert)**
- `node --test test-send-airi-local-text.mjs` — 26건

**Python 호출 지점이 0건입니다.** `AIRI-FINAL-HANDOFF-2026-08-10.md:60-69`의 "verification at handoff" 3줄, `:159-160`의 다음 세션 copy/paste 지시도 동일하게 `pytest`를 배제합니다. 레포 전체 자동화에서 pytest를 실행하는 곳은 무관 프로젝트인 `Qwen3-TTS-Openai-Fastapi/.github/workflows/regression-tests.yml`뿐입니다.

감사에서 제시된 CI 도입 장애물 3가지는 **실측으로 모두 반증**됐습니다.

| 주장된 장애물 | 실측 결과 |
|---|---|
| `sentence-transformers`(torch) 무게 | torch·sentence_transformers·h2가 **미설치 상태에서 659건 통과** (지연 임포트 + 테스트 fake) |
| Windows 러너 시간 | 레포 루트 단일 명령으로 662건이 **약 34초** (현 timeout 10분) |
| `runtime/` 미커밋 | 실패 2건 중 **1건에만** 해당. fixture 이관 또는 `.gitignore` 예외로 해소 |

### 1.4 패치 적용성이 한 번도 검증되지 않았습니다

`test-patch-applicability.ps1`은 `-BaseCheckout` 인자가 없으면 SKIP이므로 **CI에서 단 한 번도 실행된 적이 없습니다**. 감사에서 기준 checkout(`C:/Projects/airi/external/airi`, HEAD `dbf8124`)에 읽기 전용 `git apply --check`를 실제로 돌린 결과:

- **커밋된 패치 7종 중 3종이 적용 불가**
  - 2종 — 한글 문자열이 `?`로 파괴된 mojibake 상태
  - 1종 — `@@` 헤더에 라인 번호가 없는 비정상 diff
- 매니페스트가 핀한 것은 **3종뿐**이고, 깨진 3종은 전부 **핀되지 않은 4종**에 포함됩니다

즉 "체크포인트 PASS"가 주는 신뢰는 실제 검증량 대비 명백히 과대평가입니다. (부록 B `GATE-01`·`MANIFEST-01`·`PATCH-01`·`GATE-02`)

### 1.5 직전 감사(2026-08-07) 지적사항 처리 현황

`AIRI-LOCAL-STACK-REVIEW-2026-08-07.md`가 지목한 CRITICAL·HIGH를 현재 코드에서 하나씩 확인했습니다.

| 직전 지적 | 현재 상태 | 근거 |
|---|---|---|
| 한국어 정규식 손상 3종 ("응원할게→원할게") | **해소** | `ollama_proxy.py:1653-1666` — `QUERY_FILLER_RE`·`LEADING_REACTION_RE`가 어절 경계를 요구하고 주석에 사례 명시 |
| TTS 에러 전파 파손 (200 빈 응답) | **해소** | `gpt-sovits/openai_compatible_proxy.py:376-405` — 백엔드 200 확인 후에만 `StreamingResponse` 반환, 실패 시 502 |
| STT dead band 무음 폐기 | **해소** | `stt/openai_stt_server.py:106` `VAD_FALLBACK_MIN_DURATION_SECONDS = 0.3`(기존 0.6), `:731-746` 세그먼트별 필터로 전환(`min()` 전체 폐기 제거). 커밋 `b234abe` |
| **TTS 전역 락** (평균 2.3초 대기) | **미해소** | `gpt-sovits/openai_compatible_proxy.py:55` `TTS_LOCK = threading.Lock()` 그대로. **`gpt-sovits/` 127커밋 0변경** |
| **클라이언트 완성 버퍼링** (스트리밍 이득 소멸) | **미해소** | 소스 패치 `:4185-4189`가 `!res \|\| res.byteLength === 0` 검사 후 `decodeAudioData(res)` — 완성 ArrayBuffer 전제 |
| **half-duplex 억제 / AEC 상시 off** | **미해소·역행 고착** | 소스 패치 `:578-579`·`:688`에 `!isVoiceInputSuppressed()` 유지, `:4539-4551`이 `echoCancellation`·`noiseSuppression`을 `false`로 하드코딩하고 신규 테스트가 이를 **계약으로 고정** |

한국어 정규식과 TTS 에러 전파는 기준선 `1d8a720` **이전** 커밋의 성과이며, 이번 주말 델타의 기여가 아닙니다.

### 1.6 실측 지연 vs 계획서 목표

`AIRI-LATENCY-ACCEPTANCE-2026-08-09.md`의 실측치를 계획서 §6 예산과 대조했습니다.

| 구간 | 실측 | 1차 목표 | 최종 목표 | 판정 |
|---|---:|---:|---:|---|
| STT 확정 | 996.5ms | 1,200ms | 300~500ms | 1차 통과 / 최종 2~3배 초과 |
| LLM 첫 구절 (프록시 first content) | 427.3ms | 600ms | 300~500ms | **통과** |
| TTS 첫 오디오 (**warm**) | 613.3ms | 800ms | 350~750ms | **통과** |
| TTS 첫 오디오 (**cold**) | **6,897.5ms** | 800ms | 350~750ms | **8.6배 초과** |
| warm 경로 합(발화 종료 감지 제외) | **≈2,037ms** | 3,000ms | 1,200~2,000ms | 최종 목표 경계 |

두 가지가 드러납니다.

1. **warm 경로는 이미 최종 목표 경계에 있습니다.** 남은 레버는 TTS 청크 재생(약 −580ms)과 STT beam 되돌림(약 −700ms)입니다.
2. **진짜 병목은 TTS cold start 6.9초**입니다. 이는 계획서 어느 Phase에도 명시 항목이 없으며, 주말 작업에서도 다뤄지지 않았습니다.

단, 같은 문서가 스스로 밝히듯 이 측정의 STT 입력은 실제 마이크가 아니라 저장된 WAV이며, 재생 시각을 증명하지 않습니다. 실제 음성 턴의 자체 실측은 훨씬 나쁩니다 — `AIRI-TRACK-M-HANDOFF-2026-08-08.md` 기준 **본답변 재생 시작이 STT 시작 +8,968ms**(후속 3턴 7.721 / 7.522 / 11.767초)였습니다.

---

## 2. 브랜치 구조 — 사다리가 적층이 아니라 분기했습니다

| 비교 | ahead | behind |
|---|---:|---:|
| `fix/code-audit-remediation` vs `feat/llm-backend-modes` | 127 | 1 |
| `fix/code-audit-remediation` vs `feat/memory-layer` | 127 | 2 |
| `fix/code-audit-remediation` vs `main` | 132 | 0 |
| `feat/llm-backend-modes` vs `feat/memory-layer` | 0 | 1 |

주말 127커밋이 ①번 브랜치에만 쌓이면서 ②③이 고립됐습니다.

**`feat/memory-layer`에만 존재하고 주말 브랜치에 없는 파일 (11종)**

```
ollama-proxy/llm_backends.py          ollama-proxy/memory_layer.py
ollama-proxy/llm_modes.json           ollama-proxy/memory_store.py
ollama-proxy/bench-llm-modes.py       ollama-proxy/memory_retrieve.py
ollama-proxy/test_llm_backends.py     ollama-proxy/memory_embed.py
ollama-proxy/test_memory_layer.py     ollama-proxy/memory_extract.py
ollama-proxy/persona_prompt.txt
```

두 가지 결과가 나왔습니다.

1. **주말 브랜치에 `AIRI_LLM_MODE` 참조가 0건**입니다(`git grep` 실측). 직전 벤치에서 저지연 수단으로 확인됐던 클라우드 스트리밍 백엔드 전환(`local` / `cloud` / `cloud_anthropic` / `open` / `hybrid`)이 이 브랜치에는 존재하지 않습니다. 주말 브랜치의 `cloud_chat_provider.py`(206줄)는 `a7412af`에서 신설된 별개 경로이며, 기본값은 `provider='local'`·`allow_external=False`입니다.
2. **기억 구현이 두 갈래로 분기**했습니다. 주말 브랜치의 `airi_memory.py`(1,810줄)·`memory_runtime.py`·`knowledge_store.py` 계열과 `feat/memory-layer`의 `memory_layer.py`·`memory_store.py`·`memory_retrieve.py` 계열이 독립 구현이며, 어느 쪽도 병합되지 않았습니다.

**판단이 필요한 지점**: 어느 기억 구현을 채택할지, `AIRI_LLM_MODE`를 재도입할지. 두 브랜치를 이대로 두면 다음 세션이 어느 쪽을 기준으로 작업할지 알 수 없습니다.

---

## 3. 주말에 신설된 목표 — 149건

주말에 새로 추가된 문서 43종에서 목표·수용 기준·게이트를 전수 추출했습니다(부록 A). 계획서 v2.1 baseline에 없던 **신규 149건**이며, 유형 분포는 다음과 같습니다.

| 유형 | 건수 | 비중 |
|---|---:|---:|
| 금지사항 | 51 | 34% |
| 게이트 | 47 | 32% |
| 정량목표 | 24 | 16% |
| 완료기준 | 16 | 11% |
| 정성목표 | 12 | 8% |

**금지사항 + 게이트 = 98건(66%)**. 만들 것보다 막을 것이 훨씬 많이 늘었습니다. 이는 그 자체로 나쁜 신호는 아니며 — 온라인 무검수 자기학습 금지, 도구 거짓말 금지처럼 정당한 안전 경계가 다수입니다 — 다만 **각 게이트가 지연 예산에 얼마를 더하는지 계산된 곳이 없습니다.**

### 3.1 최상위 목표가 재정의됐습니다

`AIRI-EXAONE-GROWTH-STRATEGY-2026-08-07.md`(결정일 2026-08-07, 상태: **사용자 승인 방향**)가 목표를 다시 정의합니다.

> 즉 목표는 단일 LLM의 벤치마크 점수가 아니라 **지속적인 캐릭터 경험**이다. (`:30`)

계획서 §1의 핵심 지표는 **둘 다 지연**이었습니다(마지막 음절→첫 음절, 끼어들기→중단). 새 정의의 8개 체감 항목 중 지연은 **첫 1개**뿐이고, 나머지 7개는 맥락 반응 · 세션 간 기억 · 말투 장기 안정성 · 감정 관계 상태 · 자발 발화와 침묵 · **도구 정직성** · 평가 데이터 축적입니다.

### 3.2 신규 트랙 2개

**G0~G6 — 성장 로드맵** (`AIRI-EXAONE-GROWTH-STRATEGY-2026-08-07.md` §6)

| 단계 | 목표 |
|---|---|
| G0 | 작업 트리 재조정 — 진행 중 변경 보호, 실제 상태 확정, **회귀 시험 결과 기록** |
| G1 | 캐릭터 루프 — 화제·관심도·감정·관계 단계·반복 의도·침묵 시간 상태화 |
| G2 | 장기 기억 — 재시작 후 회상, 세션 간 격리, 잡음 미기억, fail-soft, 트랙 M 지연 예산 준수 |
| G3 | 평가·데이터 플라이휠 — 좋음/나쁨/수정 태그, 선호 쌍, 오류 태그 7종, 고정 시나리오·회귀 세트 |
| G4 | 성격 파인튜닝 — HF 원본 가중치 LoRA/QLoRA SFT → DPO 검토 → GGUF 배포. 배포 게이트 5개 |
| G5 | 자발 행동·방송 디렉터 — 쿨다운·중복 억제·끼어들기 우선권 |
| G6 | 화면·게임·채팅 에이전트 |

**C0~C5 — 모델 커스터마이징** (`AIRI-EXAONE-MODEL-CUSTOMIZATION-PLAN-2026-08-07.md` §6)

C0 기준선·평가세트 고정 → C1 성격 SFT LoRA → C2 선호 학습 → C3 선택적 제어 토큰 → C4 구조 프루닝 연구 → C5 Ollama 배포. 평가 지표는 품질 8 / 성능 7 / 운영성 5로 §8에 정의돼 있습니다.

**설계 원칙 4조** (§5): 정체성 > 기반 모델 / 기억과 학습 분리 / **온라인 무검수 자기학습 금지** / 게임 능력 별도 모듈.

### 3.3 이 검토가 스스로 정정하는 부분

초기 채점에서 다음을 "우선순위 밖 작업"으로 감점했습니다. **이 판단은 틀렸습니다.**

| 초기 감점 항목 | 실제 대응 목표 |
|---|---|
| 토픽 보드·자율 발화 스택 8,401줄 | **G5** 자발 행동·방송 디렉터 |
| `training/` 스타일 데이터셋 승인 파이프라인 | **G3** 평가·데이터 플라이휠 + G4 준비 |
| Wikimedia 다단계 human-in-the-loop 승인 게이트 | **§5.3** "수집→선별→수정→평가→오프라인 학습→회귀시험→버전 배포" 절차 그 자체 |
| `character_state.py` / `character_state_evaluator.py` | **G1** 캐릭터 루프 |
| 그라운딩 fail-closed 도입 | **§2** "실제로 하지 않은 행동을 했다고 주장하지 않는다" |

**원인은 문서 색인입니다.** `AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`는 Current를 4개 문서(FINAL-HANDOFF · SERVER-CHANNEL-PLAYBACK · 패치 매니페스트 · sanitizer 패치)로 한정하고 나머지 전부를 *"historical working material"*로 규정합니다. **사용자가 승인한 G0~G6 전략과 C0~C5 계획, 그리고 대화 스타일 목표 9조가 그 "나머지"에 들어 있습니다.** 인덱스가 지시한 대로 읽으면 승인된 로드맵을 보지 못합니다. 다음 검토자도 같은 실수를 반복합니다.

추가로 다음 3건도 감사의 지적을 완화해야 합니다.

- **`GOV-02`(고정 문장 반복)** — 결함이 아니라 **명시된 설계**입니다. `AIRI-LOCAL-TOPIC-BOARD-DESIGN-2026-08-09.md`가 *"모델이 토픽 대사를 새로 생성하지 않으며"*라고 못박습니다. 다만 그 설계 선택이 "빠르게 받아치는 체감"과 다른 성격이라는 지적 자체는 유효합니다.
- **`ALIGN-08`의 "계측 없이 결정됐다"** — 부정확합니다. `AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:19`가 실제 오인식 발생을 사유로 기록하고 지연 비용도 함께 남겼습니다. 남는 지적은 "A/B 정확도 개선폭이 수치로 없다"에 한정됩니다.
- **그라운딩 도입 동기** — 기록돼 있습니다. `AIRI-VTUBER-STYLE-REVIEW-2026-08-09.md:28` *"도구를 실행하지 않은 상황에서 파일 삭제를 완료했다고 말한 사례"*.

**단, 구현 결함은 그대로 유효합니다.** 그라운딩의 방향은 승인된 목표에 부합하나, 수락 게이트가 앵무새 응답만 통과시키고(`GRND-02`) 최종 실패 시 완전 침묵하며 그 턴이 저널에서도 사라지는 것은(`GRND-01`) 별개의 CRITICAL입니다.

### 3.4 자연스러움이 측정 가능한 목표가 됐습니다

주말 문서가 처음으로 "자연스러움"에 검사 가능한 정의를 부여했습니다.

**스타일 계약 9조** (`AIRI-VTUBER-JUST-CHATTING-REFERENCE-2026-08-08.md:61-77`) — 한 박자 대화 / 직접 반응·관찰·가벼운 놀림으로 시작 / 한국어 1~2문장·질문 최대 1개 / 뜻밖의 디테일을 콜백으로 / 감정 요약·상담식 질문 연쇄 금지 / 진지할 땐 농담 강요 금지 / 낯선 고유명사를 자신 있게 바꾸지 말 것 / 캐릭터 카드보다 안전·도구 진실이 상위 / 이력은 콜백용이지 낭독용이 아님

**기준선 실측** — 두 스위트가 있습니다.
- `AIRI-VTUBER-STYLE-REVIEW-2026-08-09.md`: v0.1 12케이스 중 **2 PASS / 10 FAIL**
- `ollama-proxy/eval/README.md`: v0.3 16케이스 중 **7 PASS, aggregate gate FAIL** (temperature=0, seed=42, num_ctx=2048, **num_gpu=0**)

그리고 못 박은 규칙이 둘 있습니다 — *"프롬프트를 더 길게 쌓거나 특정 문구 예외를 추가해 점수를 맞추지 않는다"*, *"자동 PASS는 결코 최종 PASS가 아니다"*(전 케이스 사람 검토 필수).

이는 G3의 실질적 착수이며 이 검토가 인정하는 강점입니다. 다만 `num_gpu=0`(CPU 전용) 기준선의 TTFT 수치(ko_greeting 5.849초)는 계획서 "LLM 첫구절 P50 500ms"와 **직접 비교할 수 없습니다**.

---

## 4. 목표 체계의 충돌 — 결정이 필요합니다

신규 목표와 계획서 v2.1이 정면 충돌하는 지점이 6곳입니다.

| # | 충돌 | 내용 |
|---|---|---|
| 1 | **수용 기준이 4~5배 느슨해짐** | `AIRI-WORK-CHECKPOINT-2026-08-10.md:173` — 합격 기준 **"첫 content 8초 이내"**. 계획서 §12 필수는 종단 P50 ≤2초 / P95 ≤3초, 권장 첫 반응 P50 ≤1.5초. **8초 기준을 통과해도 1차 목표 3.0초조차 만족하지 못합니다** |
| 2 | **평가 기준선이 CPU** | 스타일 baseline이 `num_gpu=0`. 보고된 TTFT는 지연 게이트 근거로 쓸 수 없는 값이며, README도 *"C0에는 아직 T0 first-audio 측정이 포함되지 않는다"*고 명시 |
| 3 | **두 제약이 서로를 조임** | 현 단계 LoRA/QLoRA 금지 → 스타일은 프롬프트로만 달성 / 동시에 "PASS 수를 높이려 프롬프트를 길게 쌓지 말 것". 출구가 좁습니다 |
| 4 | **문서 간 합격선 불일치** | 레퍼런스는 "한국어 1~2문장", 스타일 프로브(`eval/airi_style_probe_v0.1.md:15`)는 "**한 문장만**" |
| 5 | **지식 검색 지연 예산 부재** | 기억 DB와 지식 DB가 **물리적으로 분리**돼 한 발화에 검색 2회. 계획서는 기억검색 P50 ≤150ms만 규정하고 **지식검색 임계값 미선언** |
| 6 | **새 앵커 신설** | playback-start(`source.start(0)` 성공 후)라는 앵커가 추가됐고, end-to-end 기록에 "4단계 explicit 상관 100%"를 선결 조건으로 요구. 계획서 §6의 5구간 앵커와 정렬되지 않았습니다 |

### 결정 필요 (사용자 판단 사항)

이 충돌은 감사로 해소할 수 없습니다. **목표 서열이 바뀌었는지 여부가 사용자 결정**이기 때문입니다.

- **(A) 저지연이 여전히 1순위** → "첫 content 8초" 수용 기준을 폐기하고 계획서 §6·§12를 SSoT로 복원. 보완 순서는 §5를 따릅니다.
- **(B) 캐릭터 경험이 1순위로 이동** → 계획서 §6·§12를 신규 목표에 맞춰 **정식 개정**하고, G1~G3 완성을 우선하며 지연은 "8초 내" 유지.

어느 쪽이든 **한 곳에만 기록되어야 합니다.** 현재는 두 기준이 서로 다른 문서에 공존하며, 어느 쪽도 상대를 폐기하지 않았습니다. 이 상태에서는 "완료"를 판정할 수 없습니다.

---

## 5. 보완 착수 순서 (저지연이 1순위인 경우)

| 순위 | 항목 | 근거 | 작업량 | 기대 효과 |
|---|---|---|---|---|
| 1 | **선반응 발화 복원** — `ollama_proxy.py:1587-1588`을 기준선 형태(짧은 발화 + ACT 봉투)로 되돌리고 `:5158-5163`의 빈 delta를 `LOCAL_IMMEDIATE_ACK`로 교체. GPT-SoVITS `IMMEDIATE_RESPONSE_TEXTS`와 문자열 일치를 테스트로 고정 | `ALIGN-02` CRITICAL | S | 체감 첫 반응 ~1.2초 회복 |
| 2 | **그라운딩 침묵 → 폴백 대사** — `ollama_proxy.py:5840`에 최종 무응답 가드 추가, `schedule_completed_turn` 호출을 발화 채택에서 분리. 킬 스위치 플래그 신설 | `GRND-01` CRITICAL | M | 무응답 제거 + 기억 손실 차단 + A/B 가능 |
| 3 | **CI에 `pytest` 추가** + 실패 2건 수정 (`discard_upstream_task` 호출 1줄 / 승인 매니페스트 fixture 이관) | `DOC-01`·`LAT-01`·`DOC-07` | S | 게이트의 거짓 신호 제거 (34초 비용) |
| 4 | **그라운딩 수락 게이트 완화** — 전체표면일치를 수락 조건에서 **fast-accept 조건으로 강등**, 사실 왜곡 신호만 거절 | `GRND-02` CRITICAL | M | 앵무새 탈출, 재시도 발생률 급감(→ 지연 −5초) |
| 5 | **패치 적용성 게이트 활성화** — 깨진 패치 3종 정리 + 매니페스트에 7종 전량 핀 + CI에서 `-BaseCheckout` 지정 | `GATE-01`·`MANIFEST-01`·`PATCH-01` | M | 패치 신뢰 회복 |
| 6 | **TTS cold start 6.9초 대응** — 기동 시 워밍 또는 상주 전략 | `AIRI-LATENCY-ACCEPTANCE` 실측 | M | 첫 턴 −6초 |
| 7 | **STT 트레이드오프 재측정** — large-v3-turbo/beam3 vs small/beam1의 한국어 WER·P50을 표준 문장 7종으로 1회 측정 후 판단. 두 진입점의 기본값 불일치(`small` vs `large-v3-turbo`)도 정렬 | `ALIGN-08` | S | 최대 −700ms |
| 8 | **Phase 5 진입**(TTS 청크 재생) — 소스 빌드 전환이 끝나 진입 조건 성립 | `ALIGN-05` | L | warm 턴 −580ms, cold 턴은 더 큼 |
| 9 | **브랜치 통합 결정** — 기억 구현 2갈래 중 채택본 확정, `AIRI_LLM_MODE` 재도입 여부 판단 | §2 | M | 다음 세션 기준선 확정 |
| 10 | **문서 색인 정정** — 승인된 G0~G6·C0~C5와 스타일 계약을 Current로 승격 | §3.3 | S | 다음 검토자의 반복 실수 차단 |

MED·LOW 61건은 부록 B에 있으며, 위 10건과 독립적으로 처리 가능합니다. 다만 그중 39건은 반증 시도를 거치지 않았으므로 착수 전 개별 확인이 필요합니다.

---

## 6. 채점 — 그리고 이 채점의 한계

목표 집합이 불완전한 상태에서 산출한 초기 점수(33/100)는 **폐기합니다**. 아래는 신규 목표 149건을 반영한 재채점입니다.

### 6.1 먼저 한계를 밝힙니다

- 항목별 0~10 점수에 **사전 고정된 루브릭이 없습니다**. 다른 세션에서 같은 근거로 재채점하면 ±1점 흔들립니다.
- MED·LOW 39건은 **반증 시도를 거치지 않았습니다**. 이들이 과장이라면 항목 5·6이 각 1점 오를 수 있습니다.
- 가중치 비율은 사용자가 표명한 우선순위 *순서*에서 왔으나 **숫자 자체는 검토자가 배분**했습니다.
- 평가 대상은 `1d8a720..HEAD` **델타뿐**입니다. 프로젝트의 절대 성숙도도, 투입 노력도, 코드 미학도 채점 대상이 아닙니다.

### 6.2 채점표

| 항목 | 가중 | 점수 | 요지 |
|---|---:|---:|---|
| 1순위 — 응답 지연 | 25% | **3**/10 | **후퇴**. 선반응 제거(CRITICAL) · 그라운딩 재시도 +5초(CRITICAL) · TTS 락 방치 · Phase 5·6 미착수 · STT 지연 3배. 단 round-cancel 패치(Phase 2 배선 완료)와 소스 빌드 전환(Phase 0)은 실질 진척 |
| 2순위 — 로컬 기억·RAG | 15% | **6**/10 | **유일한 실질 진척**. KURE-v1 CUDA query P50 31.679ms(목표 ≤80ms PASS), 검색 internal P50/P95 47/63ms(게이트 ≤150ms PASS), fail-soft 구현·계측. 감점: O(N) 파이썬 코사인이 2,000행에서 154ms로 기본 타임아웃 초과(정리 코드 0줄), 기본 기동 구성에서 Stage A/B 추출기 OFF, 승인 지식 클린 배포 시 0건, SQLite에 WAL·busy_timeout 미설정 |
| 대전제 — 대화 자연스러움 | 15% | **3**/10 | 방향은 승인된 목표에 부합하나 **구현이 파손**. 앵무새 게이트(CRITICAL) · 완전 침묵(CRITICAL) · 재시도 구조적 실패. 자체 평가 7/16 PASS·gate FAIL. 단 스타일 계약 문서화와 "점수 맞추기 금지" 규율은 강점 |
| 신규 트랙 이행 (G/C) | 10% | **6**/10 | G1(캐릭터 상태)·G3(평가 플라이휠)·G5(자발 발화) 기반이 실코드로 존재. C0 평가 세트 고정도 착수. 감점: **G0 완료 조건인 "회귀 시험 결과 기록"이 미이행**(실패 2건 미기록) |
| 코드 정확성·견고성 | 12% | **6**/10 | 593 통과 / 2 실패. 스키마 불변식·임베딩 차원 혼합 차단·프라이버시 경계·untrusted 입력 처리는 우수. 감점: 커넥션 누수, 죽은 모듈 ~2,900줄, `ollama_proxy.py` 6,258줄 단일 파일 |
| 검증 체계 신뢰성 | 13% | **2**/10 | CI가 Python 662건 제외 → 실패 2건 126커밋 방치. applicability 게이트 미실행 → 패치 3종 적용 불가 미검출. 장애물 3가지 실측 반증. **G3를 목표로 선언한 프로젝트에서 가장 무거운 위반** |
| 브랜치·릴리스 위생 | 5% | **3**/10 | 사다리 분기, 기억 구현 중복, `AIRI_LLM_MODE` 유실 |
| 문서·인수인계 실효성 | 5% | **4**/10 | 서술 정직성·과대주장 억제·프라이버시 경계는 우수. 그러나 인덱스가 승인된 로드맵을 Historical로 분류해 이 검토자가 실제로 오판했습니다 |

### 6.3 종합 — **42 / 100**

가중 합계: `3×0.25 + 6×0.15 + 3×0.15 + 6×0.10 + 6×0.12 + 2×0.13 + 3×0.05 + 4×0.05 = 4.21` → **42점**

두 개의 분리된 지표로 읽는 편이 더 유용합니다.

| 지표 | 점수 | 의미 |
|---|---:|---|
| **장인정신 (craft)** | 7.5/10 | 방어 설계(mutex·pristine 해시·atomic replace)·프라이버시 경계·자기 한계 명시는 상급 |
| **목표 정렬 (outcome)** | 4/10 | 신규 목표를 반영해도 1순위 후퇴와 검증 체계 결함은 어느 문서로도 방어되지 않음 |

**초기 33점 → 42점**으로 올린 이유는 승인된 신규 로드맵을 반영해 "범위 규율" 감점(2/10, 가중 8%)을 철회하고 "신규 트랙 이행"(6/10, 가중 10%)을 신설했기 때문입니다. **지연과 검증 체계 점수는 유지**했습니다.

민감도: 8항목 완전 균등 가중이면 41점, 사용자 우선순위 극단(지연 50·기억 20·자연스러움 20·나머지 10)이면 35점, 엔지니어링 품질만 보면 44점. **총점은 가중치에 거의 흔들리지 않습니다** — 점수를 결정한 것은 항목값입니다.

---

## 7. 검토 방법 (재현용)

```powershell
# 브랜치 확보
git fetch --all --prune
git checkout fix/code-audit-remediation-2026-08-07
git merge --ff-only origin/fix/code-audit-remediation-2026-08-07

# 실측 게이트 — 앞 3줄은 현행 문서가 지정한 것, 마지막 2줄은 지정에 없는 것
git status --short
git diff-tree --check --no-commit-id -r HEAD -- . ':(exclude)airi_docs/patches/*.patch'
.\test-current-checkpoint.ps1
node --test test-send-airi-local-text.mjs
cd ollama-proxy; python -m pytest -q          # ← 현행 게이트·CI 어디에도 없음

# 실패 재현이 도입 시점부터인지 확인
git worktree add --detach <tmp> a7412af
cd <tmp>\ollama-proxy; python -m pytest -q "test_ollama_proxy.py::MemoryProxyIntegrationTests::test_first_raw_watchdog_bounds_a_stream_that_never_starts"
```

**감사 구성**: 7축(정렬도 · 지연/스트리밍/취소 · 기억 계층 · 그라운딩/자연스러움 · 토픽 거버넌스 · 패치/CI · 문서 정합성) 병렬 → CRITICAL·HIGH 전건에 대해 축별 적대적 검증관이 **반증을 시도**. 검증관은 "불확실하면 REFUTED가 아니라 DOWNGRADE"를 택하도록 지시받았습니다.

**목표 추출**: 주말 신규 문서 43종을 6클러스터로 분할해 병렬 정독. 각 항목에 계획서 baseline 대비 `is_new` 판정과 충돌 여부를 요구했습니다.

**증거 규칙**: 모든 발견과 목표에 레포 상대경로 `file:line` 근거를 요구했고, 근거가 코드와 불일치한 1건은 결과에서 제외했습니다. 등급 조정 25건은 검증관이 정정한 등급을 적용했습니다.


---

## 8. CRITICAL · HIGH 발견 상세 (20건)

7축 병렬 감사 후 CRITICAL·HIGH 전건을 적대적 검증관이 반증 시도했습니다. 검증 판정은 `CONFIRMED`(반증 실패) / `DOWNGRADE`(실재하나 영향 과장) / `UPGRADE`(영향 과소평가) 이며, `REFUTED` 1건은 이 목록에서 제외했습니다.

| 등급 | 축 | ID | 발견 | 검증 | 작업량 |
|---|---|---|---|---|---|
| CRITICAL | ALIGN | [`ALIGN-02`](#align-02) | 선반응(spoken pre-response) 제거 — 체감 첫 반응 보장 수단 소멸, TTS ACK 캐시가 dead code화 | CONFIRMED | S |
| CRITICAL | ALIGN | [`ALIGN-03`](#align-03) | grounding 재시도 = 2× 전체 LLM 왕복, 실패 시 AIRI 무응답 — 대전제(자연스러운 대화) 침해 | CONFIRMED | M |
| CRITICAL | DOCS | [`DOC-01`](#doc-01) | FINAL-HANDOFF의 검증 게이트가 Python 593건을 구조적으로 배제 — 2건 영구 실패 은폐 | CONFIRMED | S |
| CRITICAL | GRND | [`GRND-01`](#grnd-01) | 그라운딩 최종 실패 시 폴백 대사 없이 완전 침묵 — 저널 기록도 소실 | CONFIRMED | M |
| CRITICAL | GRND | [`GRND-02`](#grnd-02) | 재시도 수락 게이트가 '표면 토큰 완전 일치'를 요구 — 앵무새 응답만 통과 가능 | CONFIRMED | M |
| HIGH | ALIGN | [`ALIGN-01`](#align-01) | 로컬 LLM 경로가 스트리밍하지 않음 — 전체 답변 버퍼링 후 단일 SSE delta | DOWNGRADE | M |
| HIGH | ALIGN | [`ALIGN-05`](#align-05) | Phase 5(TTS 청크 재생) 미진입 — 서버 스트리밍 이득이 클라이언트에서 계속 소멸 | CONFIRMED | L |
| HIGH | ALIGN | [`ALIGN-06`](#align-06) | Phase 6(half-duplex 해체·barge-in) 미착수 + AEC 상시 off 역행이 소스 레벨로 고착 | CONFIRMED | L |
| HIGH | ALIGN | [`ALIGN-07`](#align-07) | 기회비용: 08-10 하루 125커밋에 지연 0줄·기억 4줄, 거버넌스·패치 재생성 21,347줄 | CONFIRMED | S |
| HIGH | ALIGN | [`ALIGN-08`](#align-08) | STT 모델·beam 상향으로 지연 3배 회귀 — 정확도와 지연 트레이드오프가 계측 없이 결정됨 | CONFIRMED | S |
| HIGH | DOCS | [`DOC-02`](#doc-02) | "브랜치는 source/patch 작업뿐"이라는 오기술이 트랙 M 전체(+29,547줄)를 감사 범위 밖으로 밀어냄 | DOWNGRADE | S |
| HIGH | DOCS | [`DOC-07`](#doc-07) | 승인 근거 문서가 가리키는 산출물이 gitignore로 레포에 부재 — 재현 불가 + 테스트 영구 실패 | CONFIRMED | M |
| HIGH | GOV | [`GOV-02`](#gov-02) | 자동 발화가 LLM 생성이 아니라 사람이 쓴 고정 문장 6개의 무한 반복 — 자연스러움 대전제 위배 | CONFIRMED | M |
| HIGH | GRND | [`GRND-03`](#grnd-03) | 1차 프롬프트와 재시도 검증기가 상호 모순 — 재시도가 구조적으로 거의 항상 실패 | CONFIRMED | S |
| HIGH | INFRA | [`CI-01`](#ci-01) | Python 662건이 CI에 전혀 없음 — 제시된 3대 장애물(torch 무게·runtime 미커밋·Windows 러너 시간)은 실측으로 모두 반증됨 | CONFIRMED | S |
| HIGH | INFRA | [`BACKUP-01`](#backup-01) | 자식 패치 스크립트의 pristine 백업은 비원자적·무검증 Copy-Item — 중단되면 undo 경로가 영구히 잠김 | CONFIRMED | M |
| HIGH | LAT | [`LAT-01`](#lat-01) | 첫-토큰 워치독 타임아웃 브랜치가 이미 열린 업스트림 스트림을 닫지 않음 (실패 테스트의 실제 코드 갭) | CONFIRMED | S |
| HIGH | MEM | [`MEM-01`](#mem-01) | 검색이 활성 기억 전량을 O(N) 파이썬 코사인으로 스캔 — 실측 2,000행에서 기본 타임아웃 초과, 기억이 무성으로 소실 | DOWNGRADE | M |
| HIGH | MEM | [`MEM-03`](#mem-03) | 추출 OFF/불가 시 저널이 무한 누적 → 매 턴 최대 4096 메시지 창을 파이썬으로 재토큰화 | CONFIRMED | M |
| HIGH | MEM | [`MEM-07`](#mem-07) | 승인 지식 코퍼스 9건이 .gitignore된 runtime/ 에만 존재 — 클린 배포에서 지식 0건이며 재생성 수단 없음 | CONFIRMED | S |

### ALIGN-02 — 선반응(spoken pre-response) 제거 — 체감 첫 반응 보장 수단 소멸, TTS ACK 캐시가 dead code화

**등급** CRITICAL · **축** ALIGN(목표 정렬도) · **검증** CONFIRMED · **작업량** S

**근거**

기준선(1d8a720)의 ollama_proxy.py:130-137은 `LOCAL_IMMEDIATE_ACK = '<|ACT {"emotion":"think"}|> 응! …'`, `SEARCH_IMMEDIATE_ACK = '<|ACT …|> 응! 바로 찾아볼게. …'`였습니다. 커밋 a7412af가 이를 ollama-proxy/ollama_proxy.py:1587-1588 `LOCAL_IMMEDIATE_ACK = '<|ACT {"emotion":"think","silent":true}|>'` / `SEARCH_IMMEDIATE_ACK = '<|ACT {"emotion":"curious","silent":true}|>'`로 바꾸고, 실제 전송 지점도 빈 문자열로 교체했습니다(a7412af diff: `- SEARCH_IMMEDIATE_ACK` → `+ ""`). 현재 두 상수는 ollama_proxy.py 본문 어디에서도 참조되지 않고 test_ollama_proxy.py:1958·2086-2087(부재 단언)에서만 등장합니다. 한편 gpt-sovits/openai_compatible_proxy.py:58 `IMMEDIATE_RESPONSE_TEXTS = ("응!", "바로 찾아볼게.")`와 :148-163 warm_immediate_response_cache는 그대로 남아 기동 시 이 두 문구를 미리 합성합니다.

**영향**

이전 감사가 '정석'으로 평가하고 계획서 M+ ④가 요구한 '체감 첫 반응 1초 미만' 메커니즘이 통째로 사라졌습니다. 자체 실측에서 ACK 재생은 STT 시작 +1,211ms였는데(TRACK-M-HANDOFF), 이제 그 다리가 없어 사용자는 본답변 재생(+8,968ms)까지 무음을 듣습니다. GPT-SoVITS 쪽 캐시 워밍은 아무도 요청하지 않는 WAV를 계속 만드는 순수 낭비가 됐습니다.

**수정안**

제거 사유가 문서에 없으므로 먼저 근거를 확인하고, 없다면 ollama_proxy.py:1587-1588을 기준선 형태(짧은 발화 문구 + ACT 봉투)로 되돌리고 5158-5163의 빈 delta를 `LOCAL_IMMEDIATE_ACK`로 복원합니다. 캐시 문구와 프록시 문구가 어긋나면 캐시 미스가 나므로 IMMEDIATE_RESPONSE_TEXTS와 문자열 일치를 테스트로 고정하십시오.

**검증관 판정**

반증 실패 — 모든 인용이 코드와 일치합니다. 기준선 `git show 1d8a720:ollama-proxy/ollama_proxy.py` 129-136행에 `LOCAL_IMMEDIATE_ACK = '<|ACT {"emotion":"think"}|> 응! ...'`, `SEARCH_IMMEDIATE_ACK = '... 응! 바로 찾아볼게. ...'`가 실제로 존재했고, 현재 ollama_proxy.py:1587-1588은 발화 텍스트가 제거된 silent ACT 토큰만 남습니다. 두 상수의 전 레포 참조는 정의부 2곳과 test_ollama_proxy.py:1958·2086-2087(부재 단언)뿐이며 런타임 참조 0건입니다(pycache 제외 grep 실측). a7412af diff에서 전송 지점이 `- LOCAL_IMMEDIATE_ACK,` → `+ ""`로 바뀐 것도 확인했습니다 — 즉 오디오뿐 아니라 ACT 감정 큐조차 전송되지 않습니다(ollama_proxy.py:5158-5163이 빈 문자열). 한편 gpt-sovits/openai_compatible_proxy.py:58 `IMMEDIATE_RESPONSE_TEXTS = ("응!", "바로 찾아볼게.")`와 :148-162 warm_immediate_response_cache, :165-178 기동 워밍 스레드가 그대로 살아 있고, 캐시 조회는 :120-127 `cached_wav_for_request`가 `text not in IMMEDIATE_RESPONSE_TEXTS`면 None을 반환하므로 정확히 이 두 문구에만 적중합니다. 그런데 `grep -rn '응!'` 결과 이 두 문구를 요청하는 코드는 레포 전체에 0건 — 순수 dead 워밍이 맞습니다. 제거 사유를 airi_docs 전체에서 grep했으나(`grep -rn silent airi_docs/*.md`) 근거 문서가 없어 의도적 트레이드오프라는 방어도 성립하지 않습니다. 1순위(체감 지연)를 직접 파괴하므로 CRITICAL 유지.

### ALIGN-03 — grounding 재시도 = 2× 전체 LLM 왕복, 실패 시 AIRI 무응답 — 대전제(자연스러운 대화) 침해

**등급** CRITICAL · **축** ALIGN(목표 정렬도) · **검증** CONFIRMED · **작업량** M

**근거**

ollama-proxy/ollama_proxy.py:2633-2665 `needs_grounding_retry`는 평범한 한국어 평서문 턴에서 후보 답변이 ①사용자 원문과의 토큰 겹침 부족 ②비유 ③일반적 되받기 ④조언 ⑤단독 감탄사 ⑥인칭 지시어 포함 ⑦**사용자 원문에 없는 감정 표현**이면 재시도를 요구합니다. 재시도는 ollama_proxy.py:5540→5588-5595에서 첫 스트림을 aclose 후 `client.send(...)`로 두 번째 전체 생성을 수행합니다. 두 번째도 실패하면 ollama_proxy.py:5840 `if dialogue:` 가드로 아무것도 방출되지 않습니다. 이 침묵이 테스트로 고정돼 있습니다 — ollama-proxy/test_ollama_proxy.py:2471("철수가 나한텐 책을 건네줬어." → `assertEqual(openai_sse_content(response.text), "")`), :2500("니가 수건 접었어." 등 3종 → 빈 응답), :2524("점심 먹었어" → 빈 응답, `assertEqual(len(chat.requests), 2)`로 2회 호출 확인). 대체 경로인 ollama_proxy.py:2538-2591 `grounded_observation_fallback`은 사용자 문장 어미만 바꿔 되돌려주는 앵무새 응답("…헐거워졌어." → "…헐거워졌구나!")입니다.

**영향**

버튜버 대화에서 가장 흔한 턴 유형(사용자 평서문 → AIRI 감정 리액션)이 정확히 재시도 트리거입니다(2660행: 사용자가 감정어를 안 썼는데 AIRI가 감정어를 쓰면 재시도). 결과는 ①지연 2배 ②그마저 실패 시 완전 침묵 ③성공해도 앵무새 복창. 1순위(지연)와 대전제(자연스러움)를 동시에 파괴하며, 방송 중 무응답은 사용자가 명시한 '버튜버로서' 요건에 치명적입니다.

**수정안**

최소 변경: 2660행의 감정 조건(`_GROUNDING_EMOTION_RE.search(candidate) and not …user_text`)과 2658행 `_GROUNDING_BARE_INTERJECTION_RE`를 재시도 트리거에서 제외해 감정 리액션을 정상 응답으로 인정하고, ollama_proxy.py:5840에 최종 무응답 가드를 추가해 dialogue가 비면 캐릭터 톤의 짧은 폴백 1문장을 반드시 발화하도록 합니다. 침묵을 정상으로 고정한 test_ollama_proxy.py:2471·2500·2524는 기대값을 함께 갱신해야 합니다.

**검증관 판정**

반증 실패 — 인용 전부 일치합니다. ollama_proxy.py:2633-2665 `needs_grounding_retry`가 겹침 부족·비유·generic echo·조언·단독 감탄사·인칭 지시어·감정어 비대칭(2660행 `_GROUNDING_EMOTION_RE.search(candidate) and not ...search(user_text)`)에서 True를 반환하는 것을 직접 확인했습니다. 게이트인 ollama_proxy.py:2610-2630 `ordinary_korean_grounding_turn`은 질문·명령·지식조회·심각 문맥만 제외하므로 남는 집합은 정확히 '평범한 한국어 평서문'입니다. 재시도 경로도 실측 일치 — ollama_proxy.py:5551-5595에서 첫 스트림을 `await upstream_response.aclose()` 후 `client.send(...)`로 두 번째 전체 생성을 수행하며 예산은 ollama_proxy.py:1631 `CORRECTIVE_RETRY_TIMEOUT_SECONDS = 5.0`으로 최대 +5초입니다. 침묵 고정도 사실 — test_ollama_proxy.py:2471, :2500-2501, :2524가 각각 `assertEqual(openai_sse_content(response.text), "")`이고 :2528 `assertEqual(len(chat.requests), 2)`로 2회 호출을 명시합니다. 대체 경로도 앵무새가 맞습니다: ollama_proxy.py:2568-2584가 어미만 '~구나!'로 바꾸거나(2571-2577) 마침표만 '!'로 치환하며(2582-2583), airi_docs/AIRI-EXACT-SURFACE-FALLBACK-CHECKPOINT-2026-08-10.md:52-57이 스스로 'This is a liveness safeguard, not a naturalness solution'이라고 인정합니다. 게다가 인칭 지시어가 있으면 ollama_proxy.py:2562-2563에서 폴백조차 ""를 반환해 완전 침묵이 남습니다. 방송 중 무응답 + 지연 2배로 1순위와 대전제를 동시에 침해 — CRITICAL 유지.

### DOC-01 — FINAL-HANDOFF의 검증 게이트가 Python 593건을 구조적으로 배제 — 2건 영구 실패 은폐

**등급** CRITICAL · **축** DOCS(문서 정합성) · **검증** CONFIRMED · **작업량** S

**근거**

airi_docs/AIRI-FINAL-HANDOFF-2026-08-10.md:60-69 이 "minimum reproducible checkpoint"로 제시하는 것은 `git status --short` / `git diff-tree --check` / `.\test-current-checkpoint.ps1` 3줄뿐입니다. test-current-checkpoint.ps1:7-13 은 test-patch-manifest.ps1 + test-patch-entrypoints.ps1 + (inert) test-patch-applicability.ps1 + `node --test test-send-airi-local-text.mjs` 만 실행합니다. .github/workflows/remediation-checkpoint.yml:68-70 도 동일 스크립트만 호출합니다. 같은 문서가 다음 세션에 배포하는 copy/paste 지시(:159-160)도 "git status/log, git diff-tree --check, .\test-current-checkpoint.ps1, node --test"만 나열하고 pytest를 넣지 않습니다. 실측: `python -m pytest test_knowledge_store.py -k approved_manifest` → `FAILED ... FileNotFoundError: ollama-proxy\runtime\approved-knowledge-2026-08-09.json` (1 failed, 12 deselected). airi_docs 51개 문서 전체에서 실패한 테스트를 기록한 문장은 0건입니다(fail 계열 매칭은 전부 fail-closed/fail-soft 설계 서술 또는 model draft 실패).

**영향**

다음 세션은 문서가 지정한 게이트를 그대로 실행하면 PASS를 받고 "검증 완료"로 판단합니다. 실패 중인 2건은 기억·지식(우선순위 2) 영역이므로, 사용자가 가장 지키고 싶은 트랙의 회귀가 게이트를 통과한 채 누적됩니다. 126커밋 동안 아무도 눈치채지 못한 것이 이 구조의 결과입니다.

**수정안**

AIRI-FINAL-HANDOFF-2026-08-10.md:65-69 코드블록에 `cd ollama-proxy; python -m pytest -q` 1줄을 추가하고, 그 아래에 현재 실측치(2 failed / 593 passed / 1 skipped)와 두 실패의 원인·상태를 명시합니다. test-current-checkpoint.ps1 에도 동일 단계를 추가하되, 실패 2건을 먼저 고치거나 xfail로 명시 표기한 뒤 게이트에 넣습니다(현 상태로 추가하면 게이트가 상시 RED).

**검증관 판정**

반증 시도 실패 — 인용 근거가 코드와 전부 일치합니다. test-current-checkpoint.ps1:7-13 은 test-patch-manifest.ps1 / test-patch-entrypoints.ps1 / (inert) test-patch-applicability.ps1 / `node --test test-send-airi-local-text.mjs` 4개만 실행하고 Python 호출이 없습니다. .github/workflows/remediation-checkpoint.yml:69-70 도 동일 스크립트만 호출하며, 레포 전체 자동화에서 pytest/unittest를 실행하는 곳은 무관 프로젝트인 Qwen3-TTS-Openai-Fastapi/.github/workflows/regression-tests.yml:32,38 뿐입니다(ollama-proxy 대상 아님). AIRI-FINAL-HANDOFF-2026-08-10.md:62-69 의 'minimum reproducible checkpoint' 3줄, :159-160 의 다음 세션 지시 모두 pytest 부재를 확인했습니다. 다만 영향 서술 1점은 부정확합니다 — 실패 2건 중 test_ollama_proxy.py:3448-3459 `test_first_raw_watchdog_bounds_a_stream_that_never_starts` 의 실패 단언은 `chat.response.closed`(ollama-proxy/test_ollama_proxy.py:3459)로, 기억·지식이 아니라 LLM 스트리밍 watchdog 경로(=우선순위 1 지연/자원 누수) 문제입니다. 즉 영향은 '기억 트랙 한정'이 아니라 우선순위 1까지 걸쳐 있어 CRITICAL 유지가 타당합니다.

### GRND-01 — 그라운딩 최종 실패 시 폴백 대사 없이 완전 침묵 — 저널 기록도 소실

**등급** CRITICAL · **축** GRND(그라운딩·자연스러움) · **검증** CONFIRMED · **작업량** M

**근거**

ollama-proxy/ollama_proxy.py:5741-5759, 5776-5787 — 재시도/초안이 모두 게이트를 못 넘으면 `boundary = IncrementalAiriOutputBoundary(...)` 새 빈 객체로 교체 + `boundary.closed_early = True`, `grounding_selected = GROUNDING_SELECTED_CONTENT_FREE`. 결과적으로 5816 `dialogue = enforce_tool_truth(..., boundary.output.strip())` 가 빈 문자열이 되고 5840 `if dialogue:` 가 False → SSE delta가 한 건도 나가지 않음. 추가로 5852 `if dialogue and not proactive_turn:` 때문에 `schedule_completed_turn`이 호출되지 않고, 3727 `if not user_text or not assistant_text: return` 로 사용자 발화조차 저널에 남지 않음. 문서 실측: airi_docs/AIRI-GROUNDING-DIAGNOSTICS-CHECKPOINT-2026-08-10.md:45-46 "one turn selected content-free refusal, emitted no assistant text, and correctly produced no TTS/playback" (3턴 중 1턴). 커밋 7982138 diff에서 기존 `boundary = initial_boundary`(초안이라도 말함)가 침묵으로 교체됨.

**영향**

사용자가 말을 걸었는데 버튜버가 아무 반응도 하지 않습니다. 오류 표시도, "음..." 같은 청취 신호도 없어 사용자는 시스템 고장으로 인식합니다. 동시에 그 턴 전체가 기억에서 사라져 트랙 M(기억·지능 보존)에도 직접적인 손실이 발생합니다.

**수정안**

content-free 경로에서 (a) 사용자 원문에 의존하지 않는 안전한 비단정 리액션 1종(예: 짧은 되묻기 또는 청취 신호)을 최소 폴백으로 발화하고, (b) 발화 채택과 저널 기록을 분리해 최소한 사용자 turn은 항상 저널에 남기도록 `schedule_completed_turn` 호출 조건을 `dialogue` 종속에서 분리하세요.

**검증관 판정**

반증 시도했으나 실패했습니다. 인용 라인 전부 실측 일치: ollama_proxy.py:5741-5759(strict/safe 모두 실패 시 boundary를 빈 IncrementalAiriOutputBoundary로 교체 + closed_early=True), 5776-5787(동일 패턴), 5816 dialogue=enforce_tool_truth(...,"")→빈 문자열, 5840 `if dialogue:` False → SSE delta 0건, 5852 `if dialogue and not proactive_turn:` → schedule_completed_turn 미호출, 3725 `if not user_text or not assistant_text: return` → 사용자 발화까지 저널 소실. 반증 후보 1: 5817-5834에 grounded_observation_fallback(2538-2591) 결정론 폴백이 존재해 완전 침묵이 아닌 경우가 있습니다(발견 서술이 이 부분을 누락). 그러나 이 폴백은 (a) grounding_quality_rejected·retry_terminal·not timed_out·not invalid·not language_blocked 를 모두 만족해야 하고, (b) 2550-2585에서 질문·명령·인칭 표현·60자 초과·미지원 어미를 전부 ""로 반환합니다. 반증 후보 2: 폴백이 나중에 추가돼 문제가 이미 해결됐는가 → git log 실측 결과 폴백 도입 커밋 909e0c7 이후 3커밋 뒤에 작성된 문서 83c9c0c(airi_docs/AIRI-GROUNDING-DIAGNOSTICS-CHECKPOINT-2026-08-10.md:44-45, 49-51)가 여전히 "one turn selected content-free refusal, emitted no assistant text", "현재 결정론 관측 폴백이 다시 쓰지 못하는 어미"라고 자인합니다. 즉 폴백 적용 이후에도 3턴 중 1턴 침묵이 실측됐습니다. 반증 후보 3: 클라이언트 측 복구 → send-airi-local-text.mjs 테스트(test-send-airi-local-text.mjs:34, 220)는 빈 completion을 정상 상태로 취급할 뿐 대체 발화가 없습니다. 추가로 5798-5805(empty_dialogue_retry 실패 경로)는 grounding_quality_rejected가 False라 5817의 폴백 조건에도 걸리지 않아 폴백 없는 순수 침묵입니다. CRITICAL 유지.

### GRND-02 — 재시도 수락 게이트가 '표면 토큰 완전 일치'를 요구 — 앵무새 응답만 통과 가능

**등급** CRITICAL · **축** GRND(그라운딩·자연스러움) · **검증** CONFIRMED · **작업량** M

**근거**

ollama-proxy/ollama_proxy.py:1976-1984 `grounding_candidate_matches_full_surface` 는 `grounding_surface_sequence(user_text) == candidate_sequence` 즉 사용자 문장의 모든 표면 토큰(문장부호 포함)이 후보와 동일할 것을 요구합니다. 이 술어가 수락 경로 전부에 걸려 있습니다 — 2258(strict retry), 2321(safe fallback), 2469(rejection flag). 실측 probe(읽기 전용, python -c로 모듈 함수 직접 호출): 사용자 "고양이가 소파를 다 긁어놨어." 에 대해 자연스러운 반응 "고양이가 아주 신났나 보네."/"발톱 좀 깎아줘야겠다." 는 needs_retry=True·safe_fallback=False 로 전량 폐기되고, 통과한 유일한 후보는 "고양이가 소파를 다 긁어놨구나!"(full_surface=True) 였습니다. 테스트가 이 동작을 정답으로 고정: ollama-proxy/test_ollama_proxy.py:2287-2322 는 모델이 낸 "정말 다행이다!"를 버리고 "수건을 반듯하게 접어뒀구나!"(사용자 원문 복창)를 expected로 단언합니다. 문서 자인: airi_docs/AIRI-EXACT-SURFACE-FALLBACK-CHECKPOINT-2026-08-10.md:39-41 "input length: 18 characters; assistant length: 18 characters", airi_docs/AIRI-GROUNDING-NATURALNESS-EXPERIMENT-2026-08-10.md:69-71 "allows ending/prosody changes, not a genuinely new reaction".

**영향**

버튜버가 사용자 말을 그대로 되풀이하는 앵무새가 됩니다. 자체 VTuber 레퍼런스(airi_docs/AIRI-VTUBER-JUST-CHATTING-REFERENCE-2026-08-08.md:70-73 "Start with one direct reaction, observation, or light tease", "Turn a surprising user detail into a callback or playful hook")가 요구하는 리액션·놀림·콜백이 구조적으로 불가능합니다. 잡담(just chatting)이 제품의 본체인데 그 본체가 죽습니다.

**수정안**

전체표면일치를 '수락 조건'에서 '무검증 즉시 통과(fast-accept) 조건'으로 강등하고, 그 외 후보는 (1) 사실 왜곡 신호(미지원 감정·비유·조언·인칭 뒤집힘·polarity 변화)만 거절하는 완화 게이트로 판정하세요. 즉 `grounding_candidate_is_safe_fallback`에서 2321 라인의 full-surface 조건을 제거하고, 이미 존재하는 semantic_marker/personal_deixis/emotion/simile 검사만 남기는 것이 최소 변경입니다.

**검증관 판정**

핵심 주장은 실측 일치합니다. ollama_proxy.py:1976-1984 grounding_candidate_matches_full_surface는 grounding_surface_sequence(user_text)==candidate_sequence 를 요구하고, 1923-1973을 읽어보면 이 시퀀스는 최종 용언 어미만 <COP>/<SS>/마커로 정규화하고 나머지 단어·문장부호를 전부 보존합니다 → 어미·억양 변화만 허용. 2258(grounding_retry_is_factual_improvement), 2321(grounding_candidate_is_safe_fallback), 2469(reject mask) 모두 실측 확인. 테스트 인용도 정확합니다 — test_ollama_proxy.py:2287-2321은 모델 출력 "정말 다행이다!"를 버리고 expected="수건을 반듯하게 접어뒀구나!"(사용자 원문 복창)를 단언하며 GROUNDING_SELECTED_DETERMINISTIC까지 고정합니다. 프로젝트 자체 문서가 자인: airi_docs/AIRI-GROUNDING-NATURALNESS-EXPERIMENT-2026-08-10.md:70-71 "intentionally allows ending/prosody changes, not a genuinely new reaction". 반증 시도에서 찾은 유일한 부정확성은 "이 술어가 수락 경로 전부에 걸려 있다"는 표현입니다 — 5554의 재시도 진입 조건이 False면(초안이 1차 게이트 통과) 초안이 full_surface 검사 없이 그대로 나갑니다. 그러나 그 1차 게이트(2648-2665)도 ①앵커 토큰 2개 이상 중복(2069-2072), ②사용자 원문의 행동 앵커 포함, ③원문에 없는 감정어 금지, ④인칭 표현 금지를 요구하므로, 놀림·콜백 같은 새 리액션은 1차 게이트에서 탈락→재시도→full_surface 앵무새로 귀결됩니다. 결론 불변, CRITICAL 유지.

### ALIGN-01 — 로컬 LLM 경로가 스트리밍하지 않음 — 전체 답변 버퍼링 후 단일 SSE delta

**등급** HIGH · **축** ALIGN(목표 정렬도) · **검증** DOWNGRADE · **작업량** M

**근거**

ollama-proxy/ollama_proxy.py:5489 `clean = boundary.feed(content)` — 루프 안에서 계산만 하고 어디에도 yield하지 않습니다(변수 clean은 이 지점 이후 재사용되지 않음). 실제 발화 전송은 루프가 완전히 끝난 뒤 ollama_proxy.py:5840-5843 `if dialogue: yield openai_sse_delta(completion_id, model, dialogue)` 단 한 번입니다. 첫 delta는 ollama_proxy.py:5158-5163에서 빈 문자열(`""`, include_role=True)로 나가므로 클라이언트가 받는 실질 텍스트는 생성 완료 시점에 한꺼번에 도착합니다. 자체 실측: airi_docs/AIRI-TRACK-M-HANDOFF-2026-08-08.md "LLM substantive content는 STT 시작 +6,049 ms에 준비됐고 … substantive playback은 +8,968 ms에 시작했다".

**영향**

AIRI가 이미 갖고 있는 tts-chunker의 '첫 구절 조기 방출'(계획서 §7 [기존] 자산)이 구조적으로 무력화됩니다. 첫 TTS 요청 자체가 LLM 전체 생성 완료 이후에야 시작되므로 계획서 §6의 `llm_first_clause` 구간이 사실상 존재하지 않고, 종단 목표 <2s가 산술적으로 달성 불가능합니다. 뉴로사마급 체감의 핵심 메커니즘이 프록시 한 곳에서 소멸합니다.

**수정안**

5489행의 `clean`을 즉시 방출하도록 변경: `if clean: emitted_substantive = True; yield openai_sse_delta(completion_id, model, clean)`. 단, grounding 재시도(ALIGN-03)가 사후 전체 문장을 요구하므로 둘은 함께 결정해야 합니다 — 최소 변경안은 `needs_grounding_retry` 대상이 아닌 턴(질문·명령·지식·proactive)만 먼저 증분 방출로 전환하고, grounding 대상 턴만 현행 버퍼링을 유지하는 것입니다.

**검증관 판정**

구조적 사실은 반증 실패 — 확인됨. ollama_proxy.py:5489·5525의 `clean = boundary.feed(content)`는 대입 후 재사용되지 않고(같은 함수 내 grep 결과 5489/5525/5812만 존재, 어느 것도 yield 인자로 쓰이지 않음), 로컬 경로의 실질 텍스트 delta는 ollama_proxy.py:5841-5843 `if dialogue: yield openai_sse_delta(...)` 한 번뿐입니다. 첫 delta는 ollama_proxy.py:5158-5163에서 빈 문자열입니다. 반면 클라우드 경로 ollama_proxy.py:5084-5092는 정상적으로 증분 yield를 하므로 '로컬만 버퍼링'이라는 구분도 맞습니다. 기본 설정(cloud_chat_provider.py:38-40 provider='local', allow_external=False)에서 로컬 경로가 실제 사용되는 것도 확인했습니다. 다만 **영향은 과장**입니다: ollama_proxy.py:3377-3379 `response_sentence_limit`는 안전·사별 문맥을 제외한 모든 턴에서 1을 반환하고, ollama_proxy.py:2585 부근 REQUEST_LOCAL_STYLE_CONTRACT가 '10~45자 한 문장'을 강제합니다. 즉 버퍼링 대상은 한 문장 10~45자이며, 조기 방출할 '첫 구절'이 사실상 하나뿐입니다. 레포 내 실측 airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:11-12은 'proxy stream first content 427.3ms / stream total 605.1ms'로, 그 턴에서 스트리밍으로 절약 가능한 최대치는 약 180ms입니다. 따라서 '<2s가 산술적으로 달성 불가능'·'핵심 메커니즘 소멸'은 성립하지 않습니다. 또한 ollama_proxy.py:5540-5546의 grounding/language 재시도 게이트가 boundary.output 전체를 요구하므로 버퍼링은 우발적 누락이 아니라 현 설계의 필연적 귀결입니다(스트리밍 도입 시 재시도 설계 자체를 바꿔야 함). 실재하는 결함이나 CRITICAL이 아니라 HIGH.

### ALIGN-05 — Phase 5(TTS 청크 재생) 미진입 — 서버 스트리밍 이득이 클라이언트에서 계속 소멸

**등급** HIGH · **축** ALIGN(목표 정렬도) · **검증** CONFIRMED · **작업량** L

**근거**

주말에 생성된 소스 패치 airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch(84파일)를 `grep -in "audioworklet|media_type.*raw|chunkStream"` 하면 매치 0건입니다. 해당 패치는 packages/pipelines-audio/src/speech-pipeline.ts와 packages/stage-ui/src/components/scenes/Stage.vue를 수정하지만 재생 계약은 완성 버퍼 방식 그대로입니다. 한편 gpt-sovits/openai_compatible_proxy.py의 백엔드 페이로드는 `"streaming_mode": STREAMING_MODE, "media_type": "wav"`로 서버는 계속 스트리밍합니다.

**영향**

계획서 §10 진입 조건('TTS 첫 오디오 P50 > 800ms')을 이전 감사가 실측으로 충족시켰는데도 진입하지 않았습니다. 서버가 374ms에 첫 청크를 흘려도 클라이언트가 완성 WAV를 기다리므로 TTFA = 총 생성시간이며, 자체 실측에서 두 번째 TTS가 +6,194ms 시작 → +8,907ms 종료(2.7초)로 그 손실이 그대로 드러납니다.

**수정안**

소스 빌드로 전환이 끝난 지금이 진입 시점입니다. 최소 슬라이스: 프록시 요청에 `media_type=raw`를 허용하고 speech-pipeline의 `tts()` 반환을 AsyncIterable<Uint8Array>로 확장한 뒤, Stage.vue의 playFunction만 청크 큐잉 재생으로 교체(립싱크는 실시간 그래프라 구조상 호환).

**검증관 판정**

반증 실패 — 오히려 더 강한 근거를 찾았습니다. `grep -icE 'audioworklet|media_type.*raw|chunkStream' airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch` 결과 0건이 맞고, 같은 패치의 재생 계약은 airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch:4189 `const audioBuffer = await audioContext.decodeAudioData(res)` + :4185 `!res || res.byteLength === 0` 검사로 **완성 ArrayBuffer 전제**임이 명시적으로 확인됩니다(:4070 createBufferSource, :4950 arrayBuffer). 패치가 packages/pipelines-audio/src/speech-pipeline.ts(:3429-3432)와 packages/stage-ui/src/components/scenes/Stage.vue(:4011-4014)를 건드리면서도 재생 계약은 바꾸지 않았습니다. 서버는 계속 스트리밍합니다 — gpt-sovits/openai_compatible_proxy.py:40 `STREAMING_MODE = int(os.environ.get(..., "2"))`, :114 `"streaming_mode": STREAMING_MODE`, :118 `"media_type": "wav"`. 손실 규모도 레포 내 실측으로 뒷받침됩니다 — airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:14-15 'warm first byte 613.3ms / warm total 1192.9ms'이므로 warm 턴에서만 약 580ms, cold 턴(:13 6897.5ms)에서는 훨씬 큽니다. 1문장 응답 체제에서는 LLM 스트리밍(ALIGN-01)보다 이쪽이 남은 최대 레버입니다. HIGH 유지.

### ALIGN-06 — Phase 6(half-duplex 해체·barge-in) 미착수 + AEC 상시 off 역행이 소스 레벨로 고착

**등급** HIGH · **축** ALIGN(목표 정렬도) · **검증** CONFIRMED · **작업량** L

**근거**

AIRI-v0.11.3-local-runtime-source.patch:577-579 `canStartSegment: () => enabled.value && !isVoiceInputSuppressed()` — 억제 게이트가 그대로 유지되고, :688에도 `&& !isVoiceInputSuppressed()`가 남아 있습니다. 같은 패치 :4513-4551은 `echoCancellation: false`, `noiseSuppression: false`를 하드코딩으로 확정합니다(기존 `true`를 `false`로 치환하는 diff 3쌍).

**영향**

계획서 §7 '끼어들기 경로'와 Phase 6의 전제(재생 중 마이크 유지)가 미착수 상태이며, 이전 감사가 '역행'이라 지적한 AEC 상시 off가 app.asar 임시 패치에서 소스 코드로 승격돼 Phase 6의 1안(재생 구간 한정 AEC 재활성화)이 더 굳게 막혔습니다. 계획서의 2대 핵심 지표 중 하나인 '끼어든 시점 → 음성 정지 시간'은 여전히 측정조차 불가합니다.

**수정안**

소스 빌드 전환이 끝났으므로 audio-device의 constraints를 하드코딩 대신 재생 상태 기반 동적 토글로 바꾸는 것이 이제 1줄 수준입니다. 그 다음 voice-input-suppression 해체 실험 → 자기 트리거(self-interrupt) 발생률 계측 순서로 진행하십시오.

**검증관 판정**

반증 실패 — 다만 인용 라인 한 곳은 정정이 필요합니다. airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch:577은 삭제 라인(`-`)이고, 억제 게이트가 유지된다는 근거는 신규 라인 :578-579 `+ canStartSegment: () => { const allowed = enabled.value && !isVoiceInputSuppressed()`와 :688 `+ && !isVoiceInputSuppressed()`입니다. 즉 패치는 텔레메트리(noteLocalVoiceCapture)만 덧붙였을 뿐 half-duplex 억제 조건 자체는 그대로이며 주장 자체는 성립합니다. AEC 고착은 인용 그대로 확인 — 같은 패치 :4539-4543, :4547-4551이 `echoCancellation: true/noiseSuppression: true`를 `false`로 치환하고, :4505-4525의 신규 테스트가 'disables browser audio processing whether a microphone is selected or not'로 이 동작을 **계약으로 고정**합니다(autoGainControl까지 false). 임시 asar 패치가 아니라 소스 diff + 테스트로 승격된 것이 맞고, 그만큼 Phase 6 1안(재생 구간 한정 AEC 재활성화)이 더 막혔습니다. 끼어들기 지표 측정 불가도 사실 — 재생 중 마이크 유지 경로가 존재하지 않습니다. HIGH 유지.

### ALIGN-07 — 기회비용: 08-10 하루 125커밋에 지연 0줄·기억 4줄, 거버넌스·패치 재생성 21,347줄

**등급** HIGH · **축** ALIGN(목표 정렬도) · **검증** CONFIRMED · **작업량** S

**근거**

`git log --format='%ad' --date=format:'%m-%d %H:%M' 1d8a720..HEAD` 기준 127커밋 중 125건이 08-10 01:48~16:55(약 15시간)에 집중됩니다. `git diff --numstat a7412af..HEAD` 분류 결과: 패치 blob 재생성 14,828줄 / 거버넌스(topic·wikimedia·knowledge·training) 6,519줄 / 문서 1,807줄 / 프록시+테스트 2,324줄 / sender 테스트 도구 705줄 / 패치·CI 툴링 589줄 / **memory 4줄 / stt·latency 0줄**. 커밋 단위로도 문서 전용 43건 + 패치·CI 전용 47건 = 90/127(70.9%)이 런타임 코드를 전혀 건드리지 않았습니다. 산출물은 airi_docs/AIRI-FINAL-HANDOFF-2026-08-10.md가 스스로 요약하듯 'correlation/cancellation/playback-start 증명 + 패치 매니페스트 해시 + 오프라인 CI'입니다.

**영향**

사용자가 1·2순위로 못박은 두 축에 08-10 하루가 사실상 0 기여했습니다. 토픽 승인 워크플로·위키미디어 수집·인간 검토 게이트는 계획서 어느 Phase에도 없는 신규 축이고, 패치 아티팩트 해시 관리는 소스 빌드로 전환한 뒤에는 존속 가치가 급감하는 작업입니다. 지연은 후퇴(ALIGN-01·02·03·08)했고 기억은 08-08 이후 정지했습니다.

**수정안**

다음 세션은 착수 전에 '이 변경이 T0→첫 음절 P50을 몇 ms 줄이는가'를 커밋 메시지에 적도록 규칙화하고, 거버넌스·패치 매니페스트 계열은 계획서 Phase에 매핑되지 않는 한 백로그로 내리십시오. 우선순위는 ALIGN-02(S) → ALIGN-01(M) → ALIGN-03(M) → ALIGN-04(L) 순입니다.

**검증관 판정**

반증 실패 — 오히려 주장보다 수치가 더 극단적입니다. `git log --format='%ad' --date=format:'%m-%d' 1d8a720..HEAD | sort | uniq -c` 결과 08-07 1건 + 08-10 126건으로 집중 사실이 확인됩니다(127커밋). 파일별 변경량도 일치 — `git diff --numstat a7412af..HEAD` 상위가 airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch 14,778줄, 그 다음이 test_ollama_proxy.py 1,326 / ollama_proxy.py 998 / wikimedia_topic_source.py 838 등 토픽·위키미디어·training 거버넌스 축입니다. 저는 더 엄격한 기준으로 재측정했는데, 런타임 코어(ollama-proxy/ollama_proxy.py·stt/·gpt-sovits/)를 건드린 커밋은 **127건 중 9건**뿐이었고(118건 미접촉, 주장의 90/127보다 큼), 그 9건의 제목도 a7d2895 'avoid silent grounded completions', 4e8a19e 'preserve facts in grounded replies', 7982138 'fail closed on ungrounded dialogue' 등 전부 grounding 계열로 지연 항목이 없습니다. `git diff --numstat a7412af..HEAD -- stt/`는 빈 출력이고, memory/knowledge/rag 이름을 가진 파일 변경은 test_memory_e2e.py 3+1줄이 전부입니다(gpt-sovits/도 전 구간 0). 사용자가 못박은 1·2순위에 08-10 하루가 사실상 0 기여했다는 판단은 실측으로 뒷받침됩니다. HIGH 유지.

### ALIGN-08 — STT 모델·beam 상향으로 지연 3배 회귀 — 정확도와 지연 트레이드오프가 계측 없이 결정됨

**등급** HIGH · **축** ALIGN(목표 정렬도) · **검증** CONFIRMED · **작업량** S

**근거**

start-airi-local-stack.ps1:2 `[string]$SttModel = 'mobiuslabsgmbh/faster-whisper-large-v3-turbo'` — 기준선 스크립트에는 이 파라미터 자체가 없었고 stt/start-local-stt.ps1:2의 기본값은 여전히 `'small'`입니다(커밋 a7412af가 도입, `git log -S "large-v3-turbo"`로 확인). stt/openai_stt_server.py:107 `BEAM_SIZE = 3`(기준선 1, b234abe→a7412af). 결과는 airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md "STT 8890 /v1/audio/transcriptions: 약 996.5ms"이며 같은 문서가 "짧은 의미 변경 오인식이 확인된 뒤 STT 기본 beam을 1에서 3으로 올렸다"고 사유를 기록합니다. 이전 감사 실측은 small/CUDA warm 291ms였습니다.

**영향**

계획서 §6 1차 목표 STT 1,200ms는 겨우 통과하지만 최종 목표 300~500ms에서 2~3배 이탈합니다. 종단 예산에서 약 700ms를 정확도와 맞바꾼 셈인데, A/B 정확도 개선폭이 수치로 남아 있지 않아 트레이드오프가 검증되지 않았습니다(문서도 "실제 마이크 재검증은 새 입력이 필요하다"고 유보).

**수정안**

large-v3-turbo/beam3 vs small/beam1의 한국어 WER과 P50 지연을 표준 문장 7종(계획서 §9)으로 한 번 측정해 표로 남기고, 개선폭이 작으면 beam을 1로 되돌리십시오(1줄). 모델 기본값이 두 스크립트에서 어긋나 있는 것(`small` vs `large-v3-turbo`)도 함께 정렬해야 합니다.

**검증관 판정**

반증 실패 — 라인 번호 하나만 드리프트가 있습니다. BEAM_SIZE는 stt/openai_stt_server.py:107이 아니라 **:115** `BEAM_SIZE = 3`이며 :116 `RECOVERY_BEAM_SIZE = 3`, 사용처는 :289-290, :561입니다. 기준선은 `git show 1d8a720:stt/openai_stt_server.py`의 101행 `BEAM_SIZE = 1`이 맞아 1→3 상향이 확인됩니다. 모델도 확인 — start-airi-local-stack.ps1:2 `$SttModel = 'mobiuslabsgmbh/faster-whisper-large-v3-turbo'`가 :187-188 `-Model $SttModel -ComputeType $SttComputeType`로 실제 전달되고, 기준선에는 param 블록 자체가 없었으며(첫 줄이 `$ErrorActionPreference = 'Stop'`) stt/start-local-stt.ps1:2는 여전히 `$Model = 'small'`이라 두 진입점이 갈라져 있습니다. 실측·사유 인용도 그대로입니다 — airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:9 'STT 8890 약 996.5ms', :19 'beam을 1에서 3으로 올렸다 … 실제 마이크 재검증은 새 입력이 필요하다'. 같은 문서 :5가 입력이 실제 마이크가 아닌 저장 WAV임을 명시하므로 정확도 개선폭이 수치로 없다는 지적도 정당합니다. 종단 2초 예산에서 STT가 단일 최대 항목(996.5ms)이 된 상태 — HIGH 유지.

### DOC-02 — "브랜치는 source/patch 작업뿐"이라는 오기술이 트랙 M 전체(+29,547줄)를 감사 범위 밖으로 밀어냄

**등급** HIGH · **축** DOCS(문서 정합성) · **검증** DOWNGRADE · **작업량** S

**근거**

airi_docs/AIRI-FINAL-HANDOFF-2026-08-10.md:9-11 "The branch is source and patch work only." / :150 "Audit only the current source patch and sender/bridge protocol." / :161. AIRI-SERVER-CHANNEL-PLAYBACK-CHECKPOINT-2026-08-10.md:86-87, :110 도 동일하게 "only the current source patch and sender/bridge protocol"로 범위를 못박습니다. 실측: `git diff --stat 1d8a720..HEAD -- ollama-proxy` → 95 files changed, 29547 insertions(+), 254 deletions(-) (airi_memory.py, knowledge_store.py, knowledge_ingest.py, memory_runtime.py, wikimedia_topic_source.py 838줄 등). Current 3문서에서 memory/rag/knowledge/topic 단어가 등장하는 9곳은 전부 금지 문구입니다(FINAL-HANDOFF:10,131,161 / INDEX:50 / PLAYBACK:72,98,120,143) — 설명이 아니라 "만들지 마라"뿐입니다.

**영향**

사용자 우선순위 2(로컬 RAG+DB 기억)의 코드 전량이 다음 감사자에게 "이 브랜치에 없는 것"으로 전달됩니다. 그 결과 DOC-01의 실패 2건도, 기억 파이프라인의 정합성도 검토 대상이 되지 않습니다.

**수정안**

FINAL-HANDOFF:9-11을 "이 브랜치는 (a) v0.11.3 source/patch, (b) ollama-proxy 로컬 기억·지식·토픽 런타임 두 축을 포함한다. 생산 topic board·리뷰 결정·raw discovery·개인 마이크 데이터는 포함하지 않는다"로 정정하고, :150/:159-164의 audit scope에 ollama-proxy 축과 pytest를 추가합니다.

**검증관 판정**

사실 근거는 실측 일치하나 '오기술' 프레이밍이 과장돼 HIGH가 적정합니다. 반증 1: AIRI-FINAL-HANDOFF-2026-08-10.md:9-11 의 'source and patch work only'는 바로 뒤 종속절에서 'It does not contain a production topic board, review decisions, raw discovery data, model output, or personal microphone content'로 한정됩니다 — 즉 '런타임 데이터·산출물이 없다'는 뜻이고, ollama-proxy Python 자체도 source이므로 '트랙 M 코드가 브랜치에 없다'는 허위 진술로 읽기는 어렵습니다. 반증 2: INDEX:50 도 동일한 데이터 경계 문장 뒤에 'Do not create governed topic boards...'가 붙습니다. 확인된 실재: `git diff --stat 1d8a720..HEAD -- ollama-proxy` = 95 files / +29,547 / -254(wikimedia_topic_source.py 838줄 등)인데, FINAL-HANDOFF:150 'Audit only the current source patch and sender/bridge protocol'과 :159-161, PLAYBACK:86-87·:110 이 다음 감사 범위를 patch+sender로 명시 축소하고, Current 3문서의 memory/rag/knowledge/topic 언급 9곳(FINAL-HANDOFF:10,131,161 / INDEX:50 / PLAYBACK:35 제외 72,98,120,143)이 사실상 전부 금지·경계 문구인 점은 그대로 확인했습니다. 감사 범위 배제는 실재하지만 의도된 범위 지정이며 데이터 손실·보안이 아니므로 HIGH.

### DOC-07 — 승인 근거 문서가 가리키는 산출물이 gitignore로 레포에 부재 — 재현 불가 + 테스트 영구 실패

**등급** HIGH · **축** DOCS(문서 정합성) · **검증** CONFIRMED · **작업량** M

**근거**

airi_docs/AIRI-APPROVED-KNOWLEDGE-2026-08-09.md:3 "이 문서는 `ollama-proxy/runtime/approved-knowledge-2026-08-09.json`에 포함한 공개 일반 지식의 승인 근거다", AIRI-APPROVED-TOPICS-2026-08-09.md:3 도 `ollama-proxy/runtime/approved-topics-2026-08-09.json`을 동일하게 참조합니다. 실측: `ls ollama-proxy/runtime/` → "No such file or directory". .gitignore:50 `ollama-proxy/runtime/`. 이 .gitignore 줄과 그 파일을 읽는 테스트(ollama-proxy/test_knowledge_store.py:194 `Path(__file__).parent / "runtime" / "approved-knowledge-2026-08-09.json"`)가 동일 커밋 a7412af에서 함께 들어왔습니다(`git show a7412af -- .gitignore`).

**영향**

우선순위 2의 시드 지식(9개 출처 수기 검수분)이 클린 체크아웃에서 복원 불가능하며, 검수 근거 문서만 남고 검수 대상은 사라진 상태입니다. 동시에 이것이 DOC-01 실패 2건 중 1건의 직접 원인입니다.

**수정안**

승인 매니페스트 2종을 `ollama-proxy/fixtures/`(추적 대상)로 옮겨 커밋하고 테스트를 fixture 기반으로 바꾸거나, `.gitignore:50`에 예외(`!ollama-proxy/runtime/approved-*.json`)를 추가합니다. 개인정보 없는 공개 출처 요약이므로 커밋 가능 여부만 재확인하면 됩니다.

**검증관 판정**

반증 시도 실패 — 모든 근거가 실측과 일치하고, 추가로 재현 불가성이 더 강하게 확인됩니다. .gitignore:50 `ollama-proxy/runtime/`, `ls ollama-proxy/runtime` → No such file or directory, ollama-proxy/test_knowledge_store.py:193-194 가 `Path(__file__).parent / "runtime" / "approved-knowledge-2026-08-09.json"` 를 읽고 :195 에서 9건을 단언합니다. 도입 커밋 동일성도 확인 — `git log --diff-filter=A -- ollama-proxy/test_knowledge_store.py` = a7412af, `git show a7412af -- .gitignore` 에 `+ollama-proxy/runtime/` 추가가 포함됩니다. 복원 가능성 반증도 실패했습니다: 승인 근거 문서 airi_docs/AIRI-APPROVED-KNOWLEDGE-2026-08-09.md 는 총 29줄로 출처 URL 표(:16-24)와 검토 원칙만 담고 승인 본문·answer_summary·콘텐츠 SHA-256을 포함하지 않으며, 해당 JSON을 생성하는 스크립트는 레포에 없습니다(`grep -rl approved-knowledge-2026-08-09` = test_knowledge_store.py 단 1건). 따라서 클린 체크아웃에서 시드 9건은 복원 불가이며 테스트는 영구 실패합니다.

### GOV-02 — 자동 발화가 LLM 생성이 아니라 사람이 쓴 고정 문장 6개의 무한 반복 — 자연스러움 대전제 위배

**등급** HIGH · **축** GOV(토픽 거버넌스) · **검증** CONFIRMED · **작업량** M

**근거**

proactive 경로는 업스트림 모델을 호출하지 않고 승인된 문장을 그대로 뱉고 종료한다 — ollama-proxy/ollama_proxy.py:5202-5207 `yield openai_sse_delta(completion_id, model, approved_proactive)` → `yield openai_sse_finish(...)` → 5219 `return`. 그 문장은 사람이 직접 타이핑한다 — ollama-proxy/curate_raw_topics.py:242-252 프롬프트 `"Pending id: ", "Korean title: ", "Summary: ", "Broadcast line: ", "Expires at: "`. 문장 제약은 12~60자, 물음표 금지, 존댓말 어미 금지, 요약에 없는 숫자 금지 — ollama-proxy/topic_board.py:123-141 (`MAX_BROADCAST_LINE_CHARS = 60`, topic_board.py:27). 반복 회피 버퍼는 `deque(maxlen=8)`(ollama_proxy.py:203 `TOPIC_RECENT_LIMIT = 8`, 477)인데 실제 운영 보드는 6건뿐이다(airi_docs/AIRI-APPROVED-TOPICS-2026-08-09.md 표 6행: nasa-eclipse-2026-08-12 … fao-sofi-2026-healthy-diet). 6 < 8이므로 ollama_proxy.py:518 `topic = next((item for item in available if item.id not in self._recent), None)`가 항상 None이 되고, 522-526의 "가장 오래 전에 내보낸 것 재사용" 분기로 떨어져 동일 6문장을 영구 라운드로빈한다.

**영향**

뉴로사마 벤치마크에서 자율 발화는 캐릭터의 핵심입니다. 현재 구현은 NASA 일식·UNCTAD 무역보고서 등 6개 고정 문장을 무한 반복하는 자동응답기이며, 시청자가 즉시 알아챌 수준의 부자연스러움입니다. "코드가 존재한다"가 "버튜버가 말한다"가 아닌 대표 사례입니다.

**수정안**

승인 보드를 발화 원문(verbatim)이 아니라 **근거(grounding)** 로만 쓰도록 되돌리세요. 즉 ollama_proxy.py:5202의 조기 반환을 제거하고, `render_topic_context()`(topic_board.py:202-214)로 이미 만들어 둔 시스템 프롬프트 블록을 붙인 채 로컬 모델을 정상 호출한 뒤, 출력에 대해서만 기존 grounding 검증(요약에 없는 숫자/고유명사 금지)을 사후 적용하는 구조로 바꾸는 것이 최소 변경입니다. 검증 실패 시에만 승인 문장으로 폴백하세요.

**검증관 판정**

반증 시도 4건이 모두 실패했습니다. 코드가 주장대로입니다.

① 'LLM 생성 아님' 확인 — ollama_proxy.py:5187 `approved_proactive = topic_board_runtime.approved_dialogue(selected_topic_id)` → 5202-5206 `yield openai_sse_delta(..., approved_proactive)` → `yield openai_sse_finish(...)` → 5219 `return`. 업스트림 호출 전에 return합니다. 비스트리밍/native 경로도 동일 — ollama_proxy.py:6080-6113의 `direct_native = {..., "content": approved_proactive}` 즉시 반환. `approved_dialogue`는 ollama_proxy.py:568-590에서 리스에 저장된 `broadcast_line` 원문을 그대로 돌려줍니다(575 `topic_id, line = lease`, 590 `return line`). prepare()가 만든 render_topic_context 프롬프트(ollama_proxy.py:551)는 두 경로 모두 모델에 전달되지 않고 버려집니다 — 즉 '실은 LLM이 생성한다'는 반증은 성립하지 않습니다.

② '사람이 타이핑한다' 확인 — curate_raw_topics.py:241-249의 프롬프트 루프 `for prompt in ("Pending id: ", "Korean title: ", "Summary: ", "Broadcast line: ", "Expires at: ")` 실재. 제약도 topic_board.py:27 `MAX_BROADCAST_LINE_CHARS = 60`, 127-134(12자 미만·`?` 포함·존댓말 어미 HONORIFIC_ENDING_RE 거부) 일치.

③ '순환 반복' 확인 — ollama_proxy.py:203 `TOPIC_RECENT_LIMIT = 8`, 477 `deque(maxlen=TOPIC_RECENT_LIMIT)`, 518 미사용 항목 선택 → None이면 522-527 `self._recent` 순서대로 가장 오래된 것 재사용. 승인 항목은 airi_docs/AIRI-APPROVED-TOPICS-2026-08-09.md 표 6행. (근거 문장 중 '6<8이므로 518이 항상 None'은 부정확 — 초기 6회는 정상 선택되고 7회차부터 None이 됩니다. 결론인 '동일 6문장 영구 라운드로빈'은 그대로 성립하므로 판정에 영향 없음.)

④ '죽은 경로 아니냐' 반증 실패 — is_local_proactive_turn(ollama_proxy.py:721-731)이 요구하는 `x-airi-turn-origin: local-proactive` 헤더를 AIRI 클라이언트가 실제로 보냅니다: airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch:1185 `headers: { 'x-airi-turn-origin': 'local-proactive' }`, 1207-1227 `commitBroadcastDelivered` 브로드캐스트 루프.

보강 사실: TOPIC_BOARD_PATH 기본값은 빈 문자열(ollama_proxy.py:202)이라 옵트인 전 기본 구성에서는 6문장 반복조차 아니라 selected_topic_id=None → 빈 문자열 종료(5177-5185, 6019-6076)로 자율 발화가 완전 무음입니다. 자연스러움 대전제 위배라는 영향 주장은 오히려 강화됩니다. HIGH 유지.

### GRND-03 — 1차 프롬프트와 재시도 검증기가 상호 모순 — 재시도가 구조적으로 거의 항상 실패

**등급** HIGH · **축** GRND(그라운딩·자연스러움) · **검증** CONFIRMED · **작업량** S

**근거**

ollama-proxy/ollama_proxy.py:2668-2675 `REQUEST_LOCAL_STYLE_CONTRACT`(1차 프롬프트, 3384 `inject_response_mode`로 주입)는 "짧은 놀림·판정·선호 중 하나로 끝내"를 요구합니다. 놀림·판정은 필연적으로 원문에 없는 내용어를 도입하므로 2258의 전체표면일치를 통과할 수 없습니다. 재시도 프롬프트도 자기모순입니다 — 2680 "조사와 어미 외에는 사용자 원문에 없는 내용 명사·동사·형용사를 추가하지 마" 와 2682 "감탄사나 상태 요약만으로 끝내지 마"가 동시에 걸려 있어, 허용된 유일한 출력 형태(상태 요약)를 프롬프트가 금지합니다. 실측 결과: airi_docs/AIRI-GROUNDING-NATURALNESS-EXPERIMENT-2026-08-10.md:20 "previous prompt: strict accepted 0/6", :34 "strict-selected requests: 9/30"; airi_docs/AIRI-GROUNDING-DIAGNOSTICS-CHECKPOINT-2026-08-10.md:45 "all three used one corrective grounding attempt"(3/3).

**영향**

재시도가 성공할 수 없는 구조라 거의 모든 턴이 2차 LLM 호출 비용을 내고도 앵무새 폴백 아니면 침묵으로 끝납니다. 지연은 2배가 되는데 품질 이득은 실측 0~30%입니다.

**수정안**

프롬프트와 검증기를 하나의 계약으로 정렬하세요. 최소 변경은 `GROUNDING_CORRECTION_STYLE_CONTRACT`(2677-2683)에서 2682의 "감탄사나 상태 요약만으로 끝내지 마"를 제거해 모순을 없애는 것이고, 근본 해결은 GRND-02와 함께 검증기를 완화해 1차 프롬프트가 요구하는 놀림·판정을 실제로 수락 가능하게 만드는 것입니다.

**검증관 판정**

인용 전부 실측 일치. ollama_proxy.py:2668-2675 REQUEST_LOCAL_STYLE_CONTRACT는 "짧은 놀림·판정·선호 중 하나로 끝내" + "감탄사와 명사 복창, 상태 요약 ... 으로 끝내지 마"를 요구하는데, 2258의 full_surface 게이트는 정확히 그 '상태 요약'만 통과시킵니다. 재시도 프롬프트 2677-2683도 2680("조사와 어미 외에 원문에 없는 내용 명사·동사·형용사 추가 금지")과 2682("감탄사나 상태 요약만으로 끝내지 마")가 동시에 걸려 허용 가능한 유일 형태를 스스로 금지합니다. 반증 시도: 1차 프롬프트가 실제로 로컬 잡담 경로에 주입되는지 확인 → 3382-3387 inject_response_mode가 REQUEST_LOCAL_STYLE_CONTRACT를 결합하고, 호출부 3551·3572·3574가 prepare_memory_body 내부(일반 잡담 경로)이므로 5227의 일반 분기에도 확실히 주입됩니다(5221의 nonmutating 분기 한정이 아님). 실측 근거도 유효: NATURALNESS-EXPERIMENT:20 previous prompt strict accepted 0/6, :34 9/30. 다만 "거의 항상 실패"는 9/30(30%)와 GROUNDING_SELECTED_RETRY_STRICT 테스트 존재를 감안하면 상한이 존재합니다 — 그래도 실패가 지배적이라는 결론은 유지되므로 HIGH 유지.

### CI-01 — Python 662건이 CI에 전혀 없음 — 제시된 3대 장애물(torch 무게·runtime 미커밋·Windows 러너 시간)은 실측으로 모두 반증됨

**등급** HIGH · **축** INFRA(패치·CI) · **검증** CONFIRMED · **작업량** S

**근거**

.github/workflows/remediation-checkpoint.yml:69-71 의 유일한 테스트 스텝은 `.\test-current-checkpoint.ps1`이며, test-current-checkpoint.ps1:7-13 은 매니페스트/엔트리포인트/적용성(SKIP) + node sender만 실행합니다. 실측 반증: (a) 의존성 — `python -c "import torch/sentence_transformers/h2"`가 전부 ModuleNotFoundError인 환경에서 `python -m pytest`(cwd=ollama-proxy) 결과 `2 failed, 593 passed, 1 skipped, 330 subtests`. sentence_transformers는 memory_runtime.py:159, benchmark_memory_track.py:460 처럼 함수 내부 지연 임포트뿐이고 test_memory_benchmark.py:387-398이 가짜 모듈을 주입합니다 → torch 불필요. (b) 시간 — 레포 루트에서 `python -m pytest ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt` 실행 시 `2 failed, 659 passed, 1 skipped, 365 subtests passed in 34.34s` (총 662건, 34초). 현 job timeout 10분 대비 충분합니다. (c) runtime/ 미커밋 — .gitignore:47 `ollama-proxy/runtime/` 로 인해 실패하는 것은 662건 중 1건(test_knowledge_store.py:195)뿐이고 나머지 661건은 무관합니다.

**영향**

지연 경로의 핵심인 ollama_proxy(워치독·스트리밍·취소)를 덮는 662건이 자동 검증되지 않아, 실패 2건이 a7412af(기준선 1d8a720..HEAD 중 126번째 = 두 번째로 오래된 커밋) 이후 125커밋 동안 무경고로 남았습니다. 선반응·본답변 지연 회귀가 발생해도 머지가 차단되지 않습니다.

**수정안**

remediation-checkpoint.yml에 job 1개 추가: `runs-on: windows-latest` + `actions/setup-python@<sha>`(3.12) + `pip install fastapi==0.141.1 httpx==0.28.1 uvicorn==0.52.1 pytest` (requirements.txt 전체가 아니라 이 4개만 — sentence-transformers 설치 금지) + `python -m pytest ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt`. 선행 조건으로 CI-02의 실패 2건을 먼저 정리해야 red가 되지 않습니다.

**검증관 판정**

근거·실측 모두 재현됨. (1) 워크플로의 유일한 테스트 스텝은 .github/workflows/remediation-checkpoint.yml:69-71 `.\test-current-checkpoint.ps1`이고, test-current-checkpoint.ps1:7-13은 매니페스트·엔트리포인트·적용성(무인자 → SKIP)과 node sender만 호출합니다. Python 호출 지점 0건. (2) 의존성 반증 재현 — 이 머신에서 torch·sentence_transformers·h2 모두 ModuleNotFoundError인 상태로 `python -m pytest ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt` 실행 → 658 passed / 1 skipped / 365 subtests / 34.03s (총 662건). job timeout 10분(remediation-checkpoint.yml:18) 대비 충분. (3) runtime 미커밋 반증 재현 — .gitignore:47 `ollama-proxy/runtime/`이고 해당 디렉터리는 워킹트리에 아예 존재하지 않으나(ls 실패), 영향받는 것은 test_knowledge_store.py:194-195 1건뿐. (4) 방치 기간도 확인 — `git log -S`로 두 실패 테스트 모두 a7412af에서 도입, `git log 1d8a720..HEAD`는 127커밋이며 a7412af는 뒤에서 두 번째(=126번째). 보강 사실 1건: 전체 스위트 동시 실행 시 test_collect_topic_candidates.py::test_concurrent_distinct_raw_merges_are_serialized가 추가로 실패(단독 실행 3/3 통과 → 부하 의존 flaky)하므로, CI 도입 시 실패는 2건이 아니라 3건입니다. 이는 발견을 약화시키지 않고 오히려 '자동 검증 부재로 flaky까지 무경고 방치'를 뒷받침합니다.

### BACKUP-01 — 자식 패치 스크립트의 pristine 백업은 비원자적·무검증 Copy-Item — 중단되면 undo 경로가 영구히 잠김

**등급** HIGH · **축** INFRA(패치·CI) · **검증** CONFIRMED · **작업량** M

**근거**

오케스트레이터는 임시 파일 스테이징 + SHA-256 검증 + File.Move로 백업을 만듭니다(apply-airi-patches.ps1:278-304). 그러나 자식 5종은 목적지에 직접 복사할 뿐이고 해시 검증도 없습니다 — patch-airi-audio-constraints.ps1:185, patch-airi-native-media-recorder.ps1:217, patch-airi-playback-latency.ps1:173, patch-airi-reaction-latency.ps1:239, patch-airi-voice-input-segmentation.ps1:240 이 모두 `Copy-Item -LiteralPath $resolvedAsar -Destination $pristineBackupPath` 한 줄입니다. 이 경로는 실제로 도달 가능합니다: 아카이브가 fully stock이 아니고 -Force가 주어지면 오케스트레이터는 백업 생성을 건너뛰고(apply:306-308), 이후 각 자식은 자기 마커만 stock이면 백업을 만듭니다(patch-airi-playback-latency.ps1:169-181). 잘못된 백업은 이후 apply-airi-patches.ps1:267-269와 restore-airi-original.ps1:117-119의 핀 해시 게이트에서 무조건 throw됩니다.

**영향**

1.05 GiB 복사 중 Ctrl-C·디스크 부족·전원 차단이 나면 잘린 `app.asar.backup-pristine`이 최종 경로에 남습니다. 그 시점부터 apply도 restore도 해시 불일치로 거부하고, 아카이브는 이미 stock이 아니라 새 백업도 만들 수 없습니다 → AIRI 재설치 외에 복구 수단이 없습니다. -Force + 부분 패치 상태에서는 '이름만 pristine'인 비-pristine 백업이 만들어져 같은 잠금에 빠집니다.

**수정안**

자식 5종의 백업 블록을 오케스트레이터와 동일한 3단계(임시 GUID 파일 → Get-FileHash 검증 → [System.IO.File]::Move)로 통일하거나, 더 단순하게 자식에서 백업 생성 로직을 제거하고 '백업은 오케스트레이터만 만든다'로 계약을 일원화하십시오(자식은 백업 부재 시 -Force 없이는 throw). 후자가 코드가 5곳 줄어 더 낫습니다.

**검증관 판정**

인용 라인 전부 일치하며, 도달 경로는 발견이 제시한 것보다 오히려 더 넓습니다. 확인: 오케스트레이터는 임시 파일 스테이징 → Get-Sha256 검증 → [System.IO.File]::Move 순서로 백업을 만들고 finally에서 임시 파일을 정리합니다(apply-airi-patches.ps1:272-304). 반면 자식 5종은 검증 없는 단일 Copy-Item입니다 — patch-airi-audio-constraints.ps1:185, patch-airi-native-media-recorder.ps1:217, patch-airi-playback-latency.ps1:173, patch-airi-reaction-latency.ps1:239, patch-airi-voice-input-segmentation.ps1:240. 자식 스크립트 전체에 Get-Sha256·knownPristineAsarSha256 참조가 0건임을 grep으로 확인했습니다(해시 검증 부재). 백업 생성 조건은 자기 마커 존재 여부뿐이라(patch-airi-playback-latency.ps1:169-172 `Test-MarkersPresent @($oldBlock)`) 다른 패치가 이미 적용된 아카이브도 'pristine'으로 명명해 복사합니다. 도달성 보강 — -Force 경로(apply-airi-patches.ps1:306-308)뿐 아니라 인수인계 문서가 자식 스크립트 개별 실행을 직접 안내합니다(airi_docs/AIRI-HANDOFF-2026-08-07.md:99-103, airi_docs/AIRI-CLOUD-SEARCH-REACTION-2026-08-07.md:118-121). 잠금 효과도 확인 — 백업 파일이 존재하면 해시 불일치 시 무조건 throw이고 이 throw는 -Force 분기보다 앞에 있어 우회 불가입니다(apply-airi-patches.ps1:266-269), restore도 동일하게 거부합니다(restore-airi-original.ps1:116-118). 결과적으로 1.05 GiB 복사 중단 시 잘린 .backup-pristine이 최종 경로에 남고, apply는 차단·restore는 거부되며 아카이브는 이미 stock이 아니라 새 pristine 백업도 만들 수 없습니다. 유일한 완화는 손상 백업을 수동 삭제 후 -Force로 진행하는 것이나 이는 원본 복구를 포기하는 선택이며, 원본 회복 수단은 AIRI 0.11.3 재설치뿐입니다. 재설치로 회복은 가능하므로 CRITICAL은 아니고 HIGH가 적정합니다.

### LAT-01 — 첫-토큰 워치독 타임아웃 브랜치가 이미 열린 업스트림 스트림을 닫지 않음 (실패 테스트의 실제 코드 갭)

**등급** HIGH · **축** LAT(지연·스트리밍·취소) · **검증** CONFIRMED · **작업량** S

**근거**

ollama-proxy/ollama_proxy.py:5302-5346 — `send_task = asyncio.create_task(client.send(..., stream=True))` 이후 `except asyncio.TimeoutError:` 블록(5319~5346)은 텔레메트리·fallback 대사만 내보내고 `return`합니다. 같은 제너레이터의 다른 핸들러는 반드시 정리합니다: `except asyncio.CancelledError:`(5956-5958)와 `except Exception:`(5968-5971) 모두 `if upstream_response is None and send_task is not None: discard_upstream_task(send_task)`를 호출합니다. `discard_upstream_task`(4054-4071) docstring 자체가 "Cancelling alone leaks the connection: httpx may already have returned an open streaming response that nobody will read"라고 명시합니다. 5320-5322 주석은 "wait_for cancels and awaits the in-flight send task"라고 주장하지만, (a) 5316-5317의 `if remaining <= 0: raise asyncio.TimeoutError` 경로는 wait_for를 아예 거치지 않고 task를 그대로 버리며, (b) wait_for 자체도 task가 같은 틱에 성공 완료하면 결과를 폐기합니다. 미세 재현(Python 3.12.10 / ProactorEventLoop): `asyncio.wait_for(create_task(instant()), 0.01)` → `TIMEOUT; task.done=True cancelled=False result='RESPONSE-OPENED'`. 실제 프록시 구동 결과도 동일 — `chat.response.closed == False`, end meta `upstream_response_headers_timeout: 1`, 총 소요 2.6ms(8초 예산 대비). 마지막 `finally:`(6003-6005)는 `upstream_response`가 None이므로 아무것도 닫지 않습니다. httpx 클라이언트는 기본 풀 한계(max_connections=100)에 `pool=5.0` 타임아웃(ollama-proxy/ollama_proxy.py:191)으로 생성되므로, 누수된 스트림은 풀 고갈 → PoolTimeout으로 이어집니다.

**영향**

워치독이 발생할 때마다 로컬 Ollama 커넥션이 반환되지 않아, 반복 시 풀 고갈로 이후 모든 턴이 최대 5초 PoolTimeout을 맞습니다(지연 1순위 직접 파괴). 프로덕션 기본 8초 예산에서는 발생 창이 좁지만(헤더가 데드라인과 같은 루프 틱에 도착하는 경우), 워치독의 정리 계약이 126커밋 동안 검증되지 않은 상태로 방치되었습니다.

**수정안**

`except asyncio.TimeoutError:` 블록 진입 직후(5319 바로 아래)에 `discard_upstream_task(send_task)`를 추가합니다. 더 확실하게 하려면 fallback을 yield하기 전에 `send_task.cancel()` 후 `with contextlib.suppress(BaseException): opened = await send_task` / `if opened is not None: await opened.aclose()`로 await 기반 정리를 쓰면 테스트도 결정론적으로 통과합니다. 5320-5322의 사실과 다른 주석도 함께 정정하십시오.

**검증관 판정**

반증 실패 — 코드와 실측 모두 주장과 일치합니다. ollama_proxy.py:5314-5358의 `except asyncio.TimeoutError:` 블록은 텔레메트리·fallback 대사만 내보내고 5358에서 `return`하며, `discard_upstream_task` 호출이 없습니다. 같은 제너레이터의 형제 핸들러는 모두 정리합니다(5956-5958 CancelledError, 5970-5971 Exception). `discard_upstream_task`(4054-4071) docstring이 바로 이 상황("httpx may already have returned an open streaming response that nobody will read")을 명시하므로 계약 위반이 명확합니다. finally(6003-6005)는 `upstream_response is None`이라 no-op입니다. 실측 재현(읽기 전용, in-process TestClient): end meta = {"upstream_response_headers_timeout":1,"raw_progress_timeout_ms":2.6}, `chat.response.closed == False` — send()가 즉시 반환하는 fake인데도 헤더 단계 워치독이 발동해 이미 열린 응답이 미회수 상태로 남았습니다. 실패 테스트 test_ollama_proxy.py:3459가 정확히 이 갭을 잡고 있으며 3회 반복 실행 모두 동일 실패(결정론적)입니다. 다만 영향 서술은 일부 과장입니다 — 정상적으로 헤더가 stall하는 대다수 경우엔 wait_for가 send를 취소해 열린 응답 자체가 없으므로 "워치독 발생할 때마다 누수"는 아니고, 헤더가 데드라인과 같은 루프 틱에 도착하는 레이스에서만 누수됩니다. 풀 고갈(기본 max_connections=100, 3945에서 limits 미지정)에는 100회 레이스가 필요해 현실성이 낮습니다. 그럼에도 자기 계약을 어기는 명백한 버그이고 126커밋 동안 실패 테스트로 방치되었으므로 HIGH 유지합니다.

### MEM-01 — 검색이 활성 기억 전량을 O(N) 파이썬 코사인으로 스캔 — 실측 2,000행에서 기본 타임아웃 초과, 기억이 무성으로 소실

**등급** HIGH · **축** MEM(기억 계층) · **검증** DOWNGRADE · **작업량** M

**근거**

ollama-proxy/airi_memory.py:1669-1671 이 `active_rows(session_id,'entity'|'fact'|'relation')`로 세션 활성 행 전량을 로드하고, :1697-1699 `score()`가 행마다 `cosine(qvec, unpack_vector(r['vector']))`를 호출합니다. cosine(:183-188)은 매 호출마다 두 벡터의 노름을 재계산하는 순수 파이썬 루프입니다(실측: dim 1024에서 호출당 180.4µs). 예산은 ollama-proxy/memory_runtime.py:129 `retrieve_timeout_ms=150`이며, 초과 시 :397-399가 예외를 삼키고 빈 `RetrievalResult()`를 반환합니다.
합성 DB 실측(dim 1024, 엔티티/팩트/릴레이션 + fact_subject 링크 포함, 콜드 경로):
  rows 300 → 32.4ms / rows 1000 → 88.1ms / rows 2000 → 154.3ms / rows 3000 → 215.4ms
즉 활성 행 약 2,000개부터 매 턴 타임아웃이며, 레포 전체에 `DELETE FROM memory`·VACUUM·prune·retention 코드가 0건(airi_memory.py, memory_runtime.py 전수 grep 결과 없음)이라 행 수는 단조 증가만 합니다.

**영향**

기억이 조용히 사라집니다. 사용자에게는 '아이리가 갑자기 기억을 못 한다'로 나타나고, 대화 자연스러움 대전제가 무너집니다. 동시에 타임아웃 직전 구간(100~150ms)은 매 턴 TTFT에 그대로 가산돼 <2s 목표를 잠식합니다.

**수정안**

(1) 후보 선별을 SQL로 내리기: `active_rows`에 kind별 `ORDER BY turn_range_end DESC LIMIT N`(예: 엔티티 200, 팩트 400)을 적용해 파이썬으로 넘어오는 행 수를 상수로 고정. (2) 벡터 연산을 numpy 단일 행렬곱으로 교체하고 노름을 저장 시점에 정규화해 재계산 제거. (3) 타임아웃 발생을 health()에 `retrieval_timeouts` 카운터로 노출해 무성 소실을 관측 가능하게 만들기.

**검증관 판정**

메커니즘은 인용대로 실재합니다. airi_memory.py:1669-1671이 active_rows()로 세션 활성 행 전량을 로드하고, :1697-1699 score()가 행마다 cosine(:183-188, 매 호출 노름 재계산)을 호출하며, :1732/1745/1753/1759/1765/1774에서 relation·onehop·traits·moments·scene 정렬이 score/cosine을 추가로 반복 호출합니다. 예산 memory_runtime.py:129 retrieve_timeout_ms=150, 초과 시 :397-399가 예외를 삼키고 빈 RetrievalResult 반환도 사실입니다. prune/retention 부재도 확인(전수 grep에서 DELETE FROM memory·VACUUM 0건, session_turn_tail만 airi_memory.py:445-446에서 60턴 트림). 그러나 '실측 2,000행'이 현실 구성에서 도달 불가라는 반증이 있습니다 — 실제 운영 DB 수치는 airi_docs/AIRI-TRACK-M-HANDOFF-2026-08-08.md:416-417에서 memory rows=252 / snapshots=45, 즉 세션당 활성 행 약 6개입니다. 근거: 대화→memory 행 승격의 유일한 경로가 apply_operations(추출)인데 MEM-02대로 추출이 OFF이고, 기본 캐논 번들 airi-canon.json은 entities 2 / facts 3 / relations 1뿐입니다(실측). 따라서 '기억이 조용히 소실'은 현재 배포에서 발생하지 않으며, 추출을 켠 뒤에야 발현하는 잠재 확장성 결함입니다. CRITICAL이 아니라 HIGH가 타당합니다.

### MEM-03 — 추출 OFF/불가 시 저널이 무한 누적 → 매 턴 최대 4096 메시지 창을 파이썬으로 재토큰화

**등급** HIGH · **축** MEM(기억 계층) · **검증** CONFIRMED · **작업량** M

**근거**

ollama-proxy/airi_memory.py:27 `JOURNAL_RECALL_WINDOW_MESSAGES = 4096`. :933-978 `journal_recall`은 미추출 메시지 최신 4096건을 창으로 잡고(:945), 완성 페어의 본문을 전부 읽어 :975 `self._journal_tokens(searchable)`로 파이썬 정규식 토큰화합니다. 게이트는 :1624-1627 `has_unextracted_complete_turns`가 True이기만 하면 열리므로, 추출이 멈춘 세션에서는 항상 열립니다. memory_runtime.py:455-458이 이 호출을 150ms 예산 안에 포함시킵니다.
실측: 600자 페어 2,048건 토큰화 = 82.2ms (DB 본문 읽기 시간 제외).

**영향**

MEM-02(기본 추출 OFF)와 결합하면 이 창은 반드시 가득 찹니다. 대화가 길어질수록 매 턴 80ms+가 고정 가산되고, MEM-01의 코사인 비용과 합쳐져 150ms 예산을 확실히 넘겨 기억+저널이 동시에 소실됩니다.

**수정안**

창 크기를 메시지 수가 아니라 '최근 N턴 + 총 문자 예산'으로 재정의(예: 최근 200메시지 또는 60KB)하고, 토큰 매칭을 파이썬 재토큰화 대신 conversation_message에 대한 FTS5 인덱스로 옮기십시오. 최소 완화책으로 `JOURNAL_RECALL_WINDOW_MESSAGES`를 256 수준으로 낮추는 것만으로도 즉시 효과가 있습니다.

**검증관 판정**

반증 실패, 오히려 실데이터가 주장을 강화합니다. airi_memory.py:27 JOURNAL_RECALL_WINDOW_MESSAGES=4096, :941-957 SQL이 extracted=0 최신 4096건을 창으로 잡고, :970-975가 완성 페어 본문을 파이썬 정규식으로 재토큰화(_journal_tokens, :915-931)합니다. 게이트는 :1624-1627 has_unextracted_complete_turns가 True이기만 하면 열리고(:883-897 LIMIT 1), 호출은 :1634/:1685/:1780에서 발생해 memory_runtime.py:390-394의 150ms wait_for 안에 포함됩니다. 창 포화가 가설이 아니라 현재 상태입니다 — airi_docs/AIRI-TRACK-M-HANDOFF-2026-08-08.md:415-416 'messages=37,666, pending total=37,666'(전량 미추출)이므로 창은 매 턴 가득 찹니다. 같은 문서 :393-395가 996 pending messages에서 15.032ms를 실측했고, 이를 4096 messages로 외삽하면 60~80ms대로 제출된 82.2ms와 정합합니다(DB 본문 읽기 최대 약 2.4MB는 별도). 다만 제목의 '무한 누적'은 부정확합니다 — 창은 4096으로 상한이 있고 페어당 JOURNAL_RECALL_MAX_PAIR_CHARS=1200(:28) 필터가 SQL(:952)에 있습니다. 상한이 있는 고정 비용이라는 점만 정정하면 HIGH 유지가 타당합니다.

### MEM-07 — 승인 지식 코퍼스 9건이 .gitignore된 runtime/ 에만 존재 — 클린 배포에서 지식 0건이며 재생성 수단 없음

**등급** HIGH · **축** MEM(기억 계층) · **검증** CONFIRMED · **작업량** S

**근거**

.gitignore에 `ollama-proxy/runtime/` 항목이 있어 해당 디렉터리 전체가 버전관리 제외입니다. 실측: `test -d C:/Projects/airi-local-stack/ollama-proxy/runtime` → NO (개발 머신에도 현재 존재하지 않음). test_knowledge_store.py:194가 `Path(__file__).parent / 'runtime' / 'approved-knowledge-2026-08-09.json'`을 읽어 9건을 단언하므로 이 테스트는 클린 체크아웃에서 영구 실패합니다. 근거 문서 airi_docs/AIRI-APPROVED-KNOWLEDGE-2026-08-09.md:3은 해당 JSON을 참조만 하고, 문서 본문에는 출처 URL 표만 있을 뿐 실제 레코드(content, content_sha256, answer_summary)가 없어 재생성이 불가능합니다. 유일한 적재 경로인 knowledge_ingest.py도 입력 파일을 인자로 요구하며 레포에 시드 파일이 없습니다(approved-topics.example.json은 토픽용, 80바이트).
동일 계열 전수조사 결과: 프로덕션 코드의 runtime/ 의존은 evaluation_store.py:53,69의 상대경로 기본값뿐이며, 메모리/지식 DB 경로는 모두 `Path(__file__).resolve().parent`(memory_runtime.py:74,124 / ollama_proxy.py:4001) 기준 절대경로 + mkdir이라 파일 부재로 기동이 깨지지는 않습니다.

**영향**

단순 테스트 결함이 아니라 배포 결함입니다. 새 머신에 클론하면 approved-knowledge가 0건이라 `approved_knowledge_dialogue` 즉답 경로(ollama_proxy.py:5255)가 절대 발동하지 않고, 지식 질문이 전부 소형 모델 생성으로 떨어져 환각·지연이 함께 늘어납니다.

**수정안**

승인 레코드 9건을 `ollama-proxy/seeds/approved-knowledge-2026-08-09.json`처럼 추적되는 경로에 커밋하고, 테스트와 기동 스크립트가 그 경로를 읽도록 바꾸십시오(runtime/ 은 파생 산출물 전용). 원본이 소실됐다면 문서의 출처 표를 근거로 레코드를 재작성하고 해시를 재산출해야 합니다.

**검증관 판정**

모든 하위 주장을 실측 확인했습니다. git check-ignore -v 결과 '.gitignore:50:ollama-proxy/runtime/'가 해당 JSON을 제외하고, ollama-proxy/runtime 디렉터리는 현재 존재하지 않습니다(ls: No such file or directory). test_knowledge_store.py:194가 Path(__file__).parent/'runtime'/'approved-knowledge-2026-08-09.json'을 읽고 :196에서 records 9건을 단언하므로 클린 체크아웃 영구 실패가 맞습니다. 재생성 불가도 확인 — airi_docs/AIRI-APPROVED-KNOWLEDGE-2026-08-09.md는 총 29라인이며 :3이 JSON을 참조만 하고 본문에는 출처 URL 표(9행)와 검토 원칙만 있어 content·content_sha256·answer_summary 원본이 없습니다. 유일 적재 경로 knowledge_ingest.py:29-30은 --input을 required로 요구하고, git ls-files ollama-proxy 결과 시드 후보는 approved-topics.example.json(80바이트, 토픽용)뿐입니다. 따라서 클린 배포에서 지식 0건 → ollama_proxy.py:5255 approved_knowledge_dialogue 즉답 경로가 발동 불가라는 결론도 성립합니다. 프로덕션 코드의 runtime/ 상대경로 의존이 evaluation_store.py:53,69뿐이고 메모리/지식 DB 경로는 절대경로+mkdir이라는 부가 조사도 grep으로 일치 확인했습니다. HIGH 유지.

---

## 9. 관련 문서

- `AIRI-INDEPENDENT-REVIEW-DATA-2026-08-10.md` — 이 검토의 데이터 부록: 신설 목표 150건 전수(원문 인용 포함), MED·LOW 발견 61건 전문, 축별 총평과 확인된 강점

- `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md`(v2.1) — 계획서 baseline (§1 목표 · §6 지연 예산 · §8 Phase · §10 게이트 · §12 완료 기준)

- `AIRI-EXAONE-GROWTH-STRATEGY-2026-08-07.md` — 사용자 승인 방향, G0~G6 로드맵

- `AIRI-EXAONE-MODEL-CUSTOMIZATION-PLAN-2026-08-07.md` — C0~C5 게이트와 평가 지표

- `AIRI-LOCAL-STACK-REVIEW-2026-08-07.md` — 직전 감사 (이 검토의 비교 기준선)
