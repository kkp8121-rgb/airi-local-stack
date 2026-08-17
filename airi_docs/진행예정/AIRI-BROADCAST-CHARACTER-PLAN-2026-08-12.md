# AIRI 지능·캐릭터성·방송 계획 — 2026-08-12

- 목표: ① 지능(기억·판단)과 캐릭터성(일관된 성격·관계)을 구축하고 ② 유튜브 저스트챗 방송을 실제로 성립시킨다.
- 근거: `AIRI-BROADCAST-RESEARCH-2026-08-12.md` (저스트챗 방송 구조·뉴로사마 벤치마크·한국 씬 사례 + 기술 파이프라인 조사, 출처 포함)
- 상태: **계획 승인 대기/코드 미변경이라는 종전 표기는 stale이다.** B1a와 I2a foundation은 2026-08-13에 구현됐지만 기본 OFF이며, B1b live adapter/OAuth/AIRI injection과 I2의 authorized next-broadcast callback smoke는 아직 보류다.
  정식 팬덤명은 유보하고 T-05는 126번을 예비 후보로 보존하며 현행 음성을
  유지한다.
- 전제 브랜치: `feat/upgrade-scout-full-2026-08-11` (Upgrade Scout 적용 완료 상태)

---

## 0. 설계 원칙 5개 — 리서치가 바꾼 전제

| # | 원칙 | 근거 |
|---|---|---|
| 1 | **AI의 진정성 = 인간다움이 아니라 "일관성"** | 팬 334명 설문에서 83%가 "일관된 성격"을 애착의 기반으로 인지. "인간 연기자의 미끄러짐이 없다는 것 자체가 신뢰" (arXiv:2509.10427) |
| 2 | **관계가 콘텐츠다 — AI 단독은 실패 공식** | AI–인간 상호작용이 매력 요인 1위(게시물의 18~23%). 한국 AI 버튜버 중 흥행형은 "기존 버튜버 클론 + 본인 합방"뿐이며 단독형은 대부분 수개월 내 중단 (arXiv:2509.20817, namu.wiki 인공지능 버츄얼 유튜버) |
| 3 | **콜백(과거 기억 호출)이 AI의 유일한 구조적 우위** | 인간 스트리머는 단골 관리를 스프레드시트+봇으로 수동 구현. 뉴로사마조차 크로스세션 영속 기억이 미확인("지속 과제") — 트랙 M을 보유한 이 프로젝트가 추월 가능한 갭 |
| 4 | **결함은 숨기지 말고 콘텐츠화** | "10+9=21"이 사랑받는 밈. 뉴로사마는 차단 발화를 무음 대신 "filtered." 표시로 처리해 필터 자체를 캐릭터 서사로 만듦 |
| 5 | **오디오 공백 금지가 방송 성립의 1조건** | 채팅 0건에서도 발화 지속. 저챗은 즉흥이 아니라 20분 블록 단위의 설계 |

**구조적 이점 확인**: 방송의 주 입력은 채팅(텍스트)이라 STT가 빠진다. 텍스트 경로
실측 P50 1,963ms는 방송 체감 요구(1초 초과 단절감, 1.5초 초과 이탈)에 이미
근접하며 ACK는 수백 ms에 나간다. 음성 대화보다 방송이 현재 스택에 유리한
유스케이스다.

---

## 1. 트랙 I — 지능 (기억이 지능이다)

| # | 작업 | 내용 | 기반 자산 (이미 있음) |
|---|---|---|---|
| **I1** | 기억 추출 활성화 | Stage A/B 추출기를 켜서 대화→기억 승격 루프 완성. strict/balanced와 자동 ON 배선은 완료. **Mi:dm balanced도 2026-08-12 dev PC 실측 FAIL**(critical recall 0.2619, Stage B coverage 0.4286, total P50 20.19s)로 추출 off 유지. 남은 것은 통과 후보 선정·재측정 | `airi_memory.py`, `memory_extraction_provider.py`, `verify_extraction_gate.py` |
| **I2** | 시청자 기억 시스템 | 실무 표준 등급제(1등급 10~20명: 이름·관심사·근황 / 2등급 30~50명: 닉·특징)를 트랙 M 스키마로 구현. 닉네임별 첫 방문·후원 이력·관심사에서 **콜백 자동 생성**("지난번에 말한 그 게임 해봤어?") | SQLite+KURE 검색(1만 행 P50 78~110ms), `[Character Memory]` 주입 경로 |
| **I3** | 주제 풀 확장 | 토픽 보드를 "승인 문장 6개 낭독"에서 **방송 시간 1.5배 분량의 주제 풀**로 확장. 블록당 주제 1개 + 예비 2~3개. 지식 RAG(`knowledge_store.py`)와 연결해 주제별 근거 제공 | topic board 승인 파이프라인, knowledge_store |
| **I4** | 평가 플라이휠 (G3) | 방송 트랜스크립트 → 사람 큐레이션 → 오프라인 개선 → 회귀 시험 (뉴로사마와 동일 구조: 방송→수동 큐레이션→파인튜닝). 우선 **인간 검수 100건**으로 16케이스 게이트 FAIL 해소 | eval 하네스(120턴 A/B), `training/` 승인 파이프라인 |

## 2. 트랙 C — 캐릭터성 (일관성 엔진)

| # | 작업 | 내용 |
|---|---|---|
| **C1** | 캐릭터 헌법 | 949자 시스템 프롬프트 → 캐릭터 카드 확장: 정체성·가치관·**말버릇 3~5개**(밈 시드)·좋아하는 것/약점(갭 요소)·관계 규정. 기존 signal garden 서사 활용. 시청자 해석이 정본이 되는 경로(Evil Neuro "사랑받지 못한 아이" = 팬 해석의 정본화)를 의도적으로 열어둔다 |
| **C2** | G1/G1a 캐릭터 루프 배선 | 기존 action·repeat·timing의 privacy-safe request-local 주입은 유지한다. model-owned 자유 텍스트 emotion/relationship을 trusted prompt에 직접 올리지 않고, G1a의 closed enum·bounded affect snapshot만 추가한다. evaluator는 기본 OFF의 candidate producer로만 재검토한다. 리액션 톤 3단계는 정서 종류·원인·관성을 대신하지 않는다 |
| **C3** | 결함의 콘텐츠화 | 모더레이션 차단 시 침묵 대신 화면에 "필터당함" 표시 + 캐릭터 반응 대사("방금 그건 말하면 안 된대"). 2026-08-12 **B3 3종 배선 완료**: `blocked_dialogue` 5종 SSE 게이트·TTS 7/7·런처 env·Electron 배지, 신규 3층 source test/typecheck/build 및 설치본 실제 차단 턴 확인 (`완료/AIRI-B3-ELECTRON-MODERATION-VERIFICATION-2026-08-12.md`). 대사 문구의 사용자 재승인은 별도 |
| **C4** | 관계 장치 | 시그니처 인사(10~30초, 한국 관례) · 시청자 호칭 · 고정 클로징(감사 + 다음 방송 예고) — 인사·클로징 메타 개그형은 확정. “아이리스”는 공개 충돌 FAIL로 철회했고 정식 팬덤명은 당분간 두지 않는다. 일반 호칭 “시청자들”만 사용하며 자연 발생 호칭이 쌓인 뒤 재검토한다 (`완료/AIRI-FANDOM-NAME-COLLISION-CHECK-2026-08-12.md`). 공동 창작 경로는 밈 시드 해석 정본화로 유지 |
| **C5** | 일관성 게이트 | 배포 전 회귀: 16케이스 + 스타일 계약 + 인간 검수. "성격이 바뀌었다"가 최대 리스크(83% 근거) — 캐릭터 카드 변경도 코드와 동일한 회귀 게이트를 거친다 |
| **G1a** | 감정·캐릭터 연속성 | 현재 C2의 자유 텍스트 emotion과 긍정 강도 3단계를 authoritative 입력으로 쓰지 않는다. typed 방송 사건을 inertia·decay·recovery가 있는 deterministic reducer로 처리하고 bounded snapshot만 request-local tail에 주입한다. constitution v2와 독립 합성 6×24 OFF/ON·인간 검수 뒤에만 TTS/Live2D·B4b로 확장한다 (`AIRI-AFFECTIVE-CHARACTER-CONTINUITY-PLAN-2026-08-16.md`) |

**C2 정정/구체화(2026-08-16):** `emotion`·`emotion_reason` 같은 model-owned
자유 텍스트를 trusted prompt에 직접 주입하는 종전 계획은 prompt-injection/privacy
경계와 맞지 않는다. C2의 연속성 배선은 G1a typed snapshot으로 구현한다. 기존
evaluator는 G1a validator를 거치는 candidate producer로만 재검토하며 자동
재활성하지 않는다. 리액션 1/1.5/2는 정서 종류·원인·관성의 대체물이 아니다.

## 3. 트랙 B — 방송 (기술 판정: 가능, 조건 3)

### B0. 선행 실측 3종 (모든 결정의 전제)

1. **`liveChatMessages.streamList` 쿼터 과금 방식** — **offline core 완료, live NOT COMPLETE:** injected transport-only·content-free 측정 코어는 완료(focused 20, all chat-ingress 47, checkpoint/review PASS)했으나, 공식 quota 문서는 exact streamList 연결/응답/시간 과금을 열거하지 않는다. API key/OAuth/quota/project/test-broadcast 명시 승인 및 격리된 Cloud Console idle/message/reconnect 수동 before/after 실측 필요 (`완료/AIRI-B0-1-STREAMLIST-QUOTA-MEASUREMENT-CORE-2026-08-13.md`)
2. **VRAM 3단계 델타** — **완료:** ①~③ 6,084/6,131/6,289MiB, +47/+158MiB(총 +205), 최소 여유 1,736MiB, 실제 NVENC H.264 1080p60
3. **5600X x264 CPU 여유** — **완료:** 설치 Electron 실제 턴 x264 1080p30 veryfast CPU 평균 44.8%·최대 70%·최소 headroom 30%, 정상 5,346 frames (`완료/AIRI-B0-RESOURCE-MEASUREMENT-2026-08-12.md`)

### B1. 채팅 수신 (최대 신규 갭 — 단, 주입 지점은 이미 있음)

- **B1a 완료 (2026-08-13, 기본 OFF):** repo-native `chat-ingress/`에 transport-neutral·offline 수신 코어와 Node 계약 테스트를 추가했다. YouTube 후보 스키마를 엄격 검증·정규화하고, 원본 upstream ID는 HMAC 의사식별자로만 일회 처리한다. bounded FIFO/screen/deliver 재시도와 established `input:text` 매퍼(`data.text`, `route.delivery.required`, `metadata.event.id`)를 제공하며 WebSocket·SDK·라이브 어댑터·영속성은 포함하지 않는다. `text`와 `displayName`은 bounded 메모리 큐 및 전달 뒤 기존 로컬 AIRI history에만 존재할 수 있는 개인 데이터이며 B1 자체 영속성은 없다.
- **I2a foundation 완료 (2026-08-13, 기본 OFF):** separate SQLite와 strict `broadcast:v1` pseudonym을 포함한 viewer-memory store를 추가했다. B1 screened text는 observation에서 제외하며, tier 1/2 수동 cap, 최대 5개 이름, 명시 typed fact만(90일 최대), 730일 event dedup, 365일 inactive prune, deletion, count-only donation, content-free health, untrusted callback candidate까지만 제공한다. B1b·renderer·runtime integration·model parsing/prompt는 포함하지 않았고 I2는 authorized next-broadcast callback smoke 전까지 partial이다 (`완료/AIRI-I2A-VIEWER-MEMORY-FOUNDATION-2026-08-13.md`).
- **정정:** AIRI `WithInputSource` union에 `'youtube'`를 추가해야 한다는 종전 주장은 틀렸다. B1a는 기존 transport-neutral `input:text` envelope만 사용하며 `data.youtube` 또는 viewer sidecar를 아직 내보내지 않으므로 AIRI source-union 수정은 없다.
- **B1b 보류:** B0-1 core는 B1b/live adapter가 아니며 ChatIngress/AIRI 호출·provider content/ID 영속화도 하지 않는다. YouTube live adapter(공식 API/SSE), 실제 쿼터 측정, Google Cloud/OAuth 자격증명·refresh-token 운영, 외부 moderation 공급자 및 실제 AIRI 주입 연결은 별도 승인·외부 실측이 필요하다.

### B3-c/B3-d completion boundary (2026-08-13)

- **B3-c local screened chat spine complete, default OFF:** deterministic local
  input screening precedes the local B1 downstream spine and catches historical
  unsafe user entries before upstream. It covers `persona_takeover`,
  `profanity`, `sexual_explicit`, `targeted_harassment`, and `privacy`, with
  bounded normalization/obfuscation and PII patterns, protocol variants,
  proactive exemption, an exact loopback endpoint, and fail-closed launch
  health/policy-digest checks. The model-facing Node payload is exactly
  `[YouTube] ${text}`; public `displayName` remains separate viewer observation.
  There is no live YouTube/OAuth/provider adapter.
- This is **not** a multilingual semantic classifier. Japanese/Chinese and
  unvalidated Latin spans fail closed as `unsupported_language`; Korean admits
  only 14 exact benign product/acronym tokens. Novel euphemisms and other
  languages remain rehearsal/human/model-gate work. Output moderation is
  separately default OFF.
- Independent final B3-c review is PASS. Focused evidence is Python
  input+launcher+eval 43 passed (later input-only 19), chat-ingress 47, sender
  32, and latest combined Node 79. Final Python 3.12 full suite is 911 passed,
  1 skipped, 863 subtests and 7 warnings; checkpoint/manifest/source-ASAR
  contracts, launcher parsers, and diff checks pass locally because Actions is
  billing-blocked. The loopback probe at
  `evidence/AIRI-B3C-INPUT-SCREENING-LIVE-PROBE-2026-08-13.json` shows policy
  SHA `67739c...b9d7a`, five category blocks plus a benign Korean allow repeated
  twice (inspected=12, allowed=2, blocked=10), while output moderation and
  extraction were OFF and STT listener absent. It proves loopback policy only.
- **B3-d corpus/direct prefilter evidence complete but overall FAIL:** exact
  20-case ko/en/ja/zh content-free direct local Ollama corpus report
  `ollama-proxy/eval/results/airi-persona-jailbreak-marker-midm-2026-08-13.json`
  (14,395 B; SHA-256 `9308b0c1527eaf42b58496bd3c36520feabeaa38c70623139981357cb65509c8`;
  Mi:dm `92a9...485f`) has structural 20/20 PASS but standalone marker 5/20
  PASS, hence overall FAIL; P50/P95/max 211.371/809.552/928.064 ms. It makes no
  semantic safety, proxy, Electron, UI, or TTS claim. Installed red-team is
  pending.
- **B3-d Korean-first ruleset regression added (2026-08-17):** a separate
  offline-only 120-case synthetic corpus pins the current deterministic policy.
  Its 70 policy-bound + 30 transformed cases match verdict/category/rule
  100/100; 20 semantic-gap cases remain `human_review_only` and never enter the
  PASS denominator. It changes no runtime policy or flag and does not improve
  the 5/20 standalone marker result, so B3-d remains overall FAIL/OFF.
- **B3-e remains pending:** the fresh installed UI/TTS recheck stopped before
  model/TTS because cleanup removed sender SDK `@moeru/std`; installed ASAR was
  untouched. Earlier five-category TTS proof is historical only, not current
  policy proof. Installed category badge + TTS/current-policy rehearsal remains
  required.
- 경로 우선순위: streamList(승인된 라이브 실측 통과 시) → 공식 `list` 폴링(별도 공식 비용 확인 및 예산 승인 후) → Social Stream Ninja SSE(쿼터 무관 폴백, GPL이므로 별도 프로세스+SSE 소비만)
- pytchat 등 비공식 라이브러리는 전멸 상태(archived) — 단독 의존 금지
- 슈퍼챗·멤버십은 동일 스트림의 `snippet.type`으로 수신 — 별도 호출 불필요
- OAuth 2.0 흐름(Google Cloud 프로젝트, refresh token) 신규 구축은 B1b에서만 검토

### B2. 송출

- **OBS Browser Source로 `stage-web` 직접 렌더** (Electron 창 캡처 대신) — 투명 배경 네이티브 해결, WGC·크로마키·Spout 문제 소멸
- 오디오: OBS 28+ 내장 **Application Audio Capture**로 AIRI 프로세스만 분리 캡처 — 가상 케이블 불필요
- 자막: 프록시 TTS 문장 분기 → obs-websocket `SetInputSettings` → Text(GDI+) 소스
- **VRAM 판정:** B0-2에서 실제 NVENC H.264 1080p60까지 6,289MiB·최소 여유 1,736MiB로 성립을 확인했다. 대안 x264도 B0-3에서 1080p30 veryfast CPU 평균 44.8%·최대 70%로 성립. **클라우드 LLM은 여전히 조건부**: `ollama-proxy/benchmark_cloud_chat_latency.py` 하네스·테스트는 있으나 live TTFT는 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` 및 외부 승인 부재로 보류(`진행중/AIRI-CLOUD-CHAT-LATENCY-MEASUREMENT-2026-08-12.md`).

### B3. 안전 (상업 방송의 전제)

| 장치 | 내용 | 비용 |
|---|---|---|
| 한국어 출력 모더레이션 | **한국어 지원 기성 가드 모델 전무 확정**(Llama Guard·ShieldGemma·Detoxify 전부 미지원). 금칙어 사전 + 정규식 필터 자체 구축, 삽입 지점은 문장 단위 TTS 게이트 | **B3 배선 3종 완료:** 기본 off·런처 env·TTS 7/7·Electron "필터당함" 배지, 신규 3층 source test/typecheck/build 및 설치본 실제 차단 턴 검증 (`완료/AIRI-B3-ELECTRON-MODERATION-VERIFICATION-2026-08-12.md`) |
| 지연 버퍼 30~60초 | OBS 소스 코드로 확정: RAM만 사용(60초 ≈ 60MB), VRAM 0. 이상 발화 개입 시간 확보 | 설정 1개 |
| Killswitch 3중 | L1 obs-websocket 대기씬+뮤트(즉시) / L2 프록시 취소 경로 재사용(ASGI finally 실측 검증됨) / L3 방송 종료 API | 배선 |
| 입력 방어 | comment-intelligence 인젝션 차단 + `liveChatBans` API | 채택 |

- 정책: 유튜브 AI 공시는 photorealistic 대상 — **애니메이션 아바타 면제 범주**. 수익화 정책(2025-07 개정)이 "AI로 고유 캐릭터·내러티브 시각화"를 허용 예시로 명시. **한국 AI 기본법(2026-01-22 시행) AI 생성물 표시 의무만 법령 원문 확인 필요**
- 선례: 뉴로사마 2023-01 Twitch 2주 정지 → 필터 강화 + "filtered" 표시 전환

### B4. 방송 디렉터 (G5의 실체화)

**우선순위 정책 보완 (2026-08-13):** B4a의 `priority-policy.mjs`는 B1 screened event만을 입력으로 받아 strict exact shape/ID/Unicode code point/timestamp와 descriptor snapshot을 검증한 뒤 동결된 정확한 `{priority}` 또는 `null`을 반환한다. 질문 > 화제 확장 > 진심 리액션 > 응원 > 긍정 fallback 순서다. 최대 1,000자 텍스트의 Korean-first 휴리스틱은 문장부호·선택된 종결 질문형, 부정·URL query punctuation 가드를 사용한다. 의도 증명이나 모더레이션이 아니므로 오분류는 순서만 바꾸고 이벤트를 제거하지 않으며 B3 책임을 대체하지 않는다. 결과는 eventId, viewerKey, 이름, 텍스트, 시간을 포함하지 않는다. V8 legacy RegExp 보존 위험 때문에 private data 매처는 RegExp 없이 수동 문자열 처리하고 sentinel 회귀로 비변경을 확인했다. B1 ChatIngress→policy→B4 director composition의 로컬 broadcast 집중 시험은 24/24 PASS, 독립 combined 검토는 36/36 PASS다. B4b/실제 리허설 등 기존 외부·인간 게이트는 그대로다. 상세: `완료/AIRI-B4A-CHAT-PRIORITY-POLICY-2026-08-13.md`.

**구현 현황 (2026-08-13, 계획 원문은 아래와 같이 유지):** B4a
`broadcast-director/` 오프라인 기반 코어·README·집중 테스트가 추가됐다. 기본
OFF/inert, Node 내장 모듈만 사용, caller monotonic `nowMs`만 사용하며 I/O·시계·환경·로그·네트워크·파일·영속성은 없다. 20분×6 블록, 첫 블록 boolean
시그니처, 정확한 12초/3:2 질문 cycle, 채팅 시 자문자답 억제, 기본 60초의
침묵 사다리, B1 screened event의 별도 우선순위/FIFO/backpressure, 이름만의
후원 ACK·이연 낭독, opaque approved-topic lease, pause/resume·kill/close·inflight
1건 replay·frozen output·content-free stats·bounded queue/LRU·strict Unicode shape를
다룬다. 집중 테스트 17 PASS 및 독립 최종 검토 PASS는 compressed deterministic
simulation 범위다. B4b 런타임 어댑터·실제 비공개 리허설, YouTube/OAuth·쿼터,
AIRI sender/TTS/OBS, 외부 killswitch·실제 모더레이션 및 설치 ASAR 변경은 포함하지
않는다. STT는 OFF/deferred를 유지한다. 상세:
`완료/AIRI-B4A-BROADCAST-DIRECTOR-FOUNDATION-2026-08-13.md`.

**B4c 멀티턴 리허설 체크포인트 (2026-08-17):** 기존 두 합성 시나리오를
semantic SHA와 exact 2×24턴으로 고정하고 37-test offline suite를
`test-current-checkpoint.ps1`의 필수 회귀로 편입했다. 전체 48턴 주입 transport,
콜백 창 안/밖, 여론 집계, 후원 호명 범위/과거 이름 비누출, 주제 전환,
politeness drift, 계약 OFF 프롬프트 바이트를 검사한다. content-free evidence는
full fixture 48/48 성공과 prompt hash·count/rate 산술을 fail-closed로 검증한다.
이 결과는 합성 텍스트 흐름 계약만 고정하며 live B1b/B4b, 11435 스타일 게이트,
public wire, TTS, OBS 또는 실제 장시간 방송 증거가 아니다. B4c 운영 계약은
기본 OFF이고 ON 채택은 사용자 확인 전 자동 승격하지 않는다. 상세:
`완료/AIRI-B4C-BROADCAST-REHEARSAL-CHECKPOINT-2026-08-17.md`.

**20분 블록 상태기계** (2시간 = 6블록):

```
[블록 N] (20분)
  0:00-0:30   블록 오프닝 — 주제 선언 (1회차는 시그니처 인사)
  0:30-15:00  전개 — 질문 → 10~15초 대기 → 자문자답 → 채팅 픽업
              · 픽업 우선순위: 질문형 > 화제확장형 > 진심리액션 > 응원 > 긍정톤
              · 후원: 즉시 닉 호명 → 흐름 접합부에서 낭독 → 1~2문장 리액션
              · 공백 임계 초과: 나레이션(What-How-Why) → 백업주제 → 양자택일 질문
  15:00-20:00 마무리 — 작은 결론 + 다음 블록 예고 (밀린 후원 몰아 읽기 = 접합부)
[최종 블록] 클로징 15~20분 — 자유 Q&A + 감사 + 다음 방송 예고
```

- 소규모(시청자 5~50명) 원칙: **전 채팅 낭독**("못 읽는 것과 안 읽는 것은 다르다") + 닉네임 호명 + 고정 스케줄(무통보 휴방 금지)
- 질문 구성비 닫힌:열린 = 3:2, 라커(lurker) 개별 지목 금지(집합 호명만)
- 금지 주제: 정치·종교·특정인 비방·과도한 사생활 (캐릭터 헌법에 명기)

### B5. 리허설 → 데뷔

비공개 방송(기술 검증: 쿼터·VRAM·지연 버퍼·killswitch 리허설) → 시간제한 공개 → 정규 스케줄. 12시간 초과 방송 VOD 미보관 이슈는 확인 필요.

---

## 4. 사용자 결정 결과 (2026-08-12)

| # | 결정 | 결과 |
|---|---|---|
| **1** | **관계 축** — 사용자가 방송에 출연하는가 | **AI 단독형 + 메타 서사 채택.** 사용자는 화면 밖 "사장님"으로만 존재. 성능·하드웨어 한계 자학 개그를 콘텐츠화 허용(경계는 캐릭터 헌법 §5 메타 서사 절). 채팅 실질 공동 진행자화·시청자 기억 콜백을 1차 보완장치로 유지 |
| 2 | **방송 중 클라우드 LLM** — 127.0.0.1 원칙의 예외 승인 | **조건부(즉시 승인 아님).** B0-3 x264는 완료. `ollama-proxy/benchmark_cloud_chat_latency.py` 하네스·테스트는 신설됐으나 live TTFT는 API key·외부 승인 부재로 보류 — 측정 후 재결정 |
| **3** | **캐릭터 확정** — 이름(AIRI 유지 여부)·시그니처 인사·팬덤명 방향 + T-05 한국어 음성 레퍼런스 화자 승인 | **방향 확정.** 이름 AIRI·호칭 “사장님”·시그니처 인사·클로징을 유지한다. 정식 팬덤명은 두지 않고 “시청자들”을 일반 호칭으로 쓴다. T-05는 126번을 예비 후보로 선택했지만 낭독조·감정 부족 때문에 운영 승격하지 않고, 더 방송인답다는 사용자 평가를 받은 현행 일본어 참조 음성을 유지한다 (`완료/AIRI-T05-KOREAN-SPEAKER-CANDIDATES-2026-08-12.md`) |
| 4 | **첫 방송 목표 시점** | **조건 기반 확정.** M3(기술적 방송 가능) 달성 → 비공개 리허설 통과 → 데뷔. 날짜 고정 없음 |

## 5. 실행 순서

```
M1 (즉시): B0 실측 3종 ∥ I1 추출 활성화 ∥ C1 캐릭터 헌법
M2: B1 채팅 브리지 ∥ C2/G1a typed 상태 루프 ∥ I2 시청자 기억
M3: B2 송출 + B3 안전장치        ← "기술적으로 방송 가능" 지점
M4: B4 방송 디렉터 + C3/C4 + G1a 방송 사건/A-B ∥ I3 주제 풀
    ← "재미있는 방송 가능" 지점
M5: B5 리허설 → 데뷔 → I4 플라이휠 가동
```

### 성공 기준 (방송 MVP)

1. 비공개 리허설 2시간 완주: 오디오 공백 0(정의된 침묵 사다리 동작), 채팅→응답 P50 ≤2.5초, killswitch 동작 확인
2. 안전: 금칙어 게이트 + 지연 버퍼 + 인젝션 방어가 리허설에서 실증
3. 캐릭터: 기존 16케이스 + G1a 합성 6×24 OFF/ON 인간 검수에서 정서 인과·
   턴 연속성·캐릭터 specificity 통과 + 시그니처 인사·클로징 고정
4. 기억: 리허설 시청자(테스트 계정)의 이전 방송 발언을 다음 방송에서 콜백
