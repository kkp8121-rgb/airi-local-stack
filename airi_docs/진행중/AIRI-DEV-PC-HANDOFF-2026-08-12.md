# dev PC(codex) 인수인계 — 검토 PC 선행 작업 배치 (2026-08-12)

검토 PC(무GPU 검증 환경)에서 로드맵 중 오프라인으로 가능한 작업을 선행했다.
이 문서는 그 결과와, **dev PC에서만 가능한 잔여 검증·후속 작업**의 전체
목록이다. 착수 전 이 문서와 아래 근거 문서를 정독하라.

- historical base: `aef5300`(STT OFF 방송 프로필; 기반 배치
  `7dc4e76` 문서, `932eae6` 코드). 이는 현행 branch tip이 아니다.
- 현재 branch는 `0db431c`의 continuity hardening 이후 production-context v2
  source-binding batch까지 포함한다. exact tip은 `git log -1`로 확인한다.
- 오프라인 historical 검증: **`aef5300`의 CI `python-core-tests` matrix 41개 추적 경로**
  **829 passed / 1 skipped / 706 subtests**
  (기준 733/1/504), `test-patch-manifest.ps1` PASS, 소스·문서
  `git diff --check` 클린(생성된 runtime patch 내부 source whitespace 제외)
- 계획 근거: `진행예정/AIRI-BROADCAST-CHARACTER-PLAN-2026-08-12.md` (M1
  착수분), `진행중/AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md` (게이트)

---

## 1. 검토 PC에서 완료된 것 (요약)

| 트랙 | 내용 | 상태 |
|---|---|---|
| 모델 SSoT | `resolve_chat_model()` 단일화, Electron 정규화, foreground 단일 runner, 롤백·eval provenance, digest pin | **dev PC 실기 PASS**, Mi:dm 실측 digest 기본 pin 반영 (`완료/AIRI-DEV-PC-SSOT-VERIFICATION-2026-08-12.md`) |
| 장문 모델 A/B | `num_ctx=2048`의 card·초기 화자·최신 부정 정정·tail memory 합성 비교 | **실측 완료, 양 모델 FAIL**. EXAONE exact 3/12, Mi:dm 0/12; Mi:dm 20 filler쌍에서 token 포화 (`완료/AIRI-LONG-CONTEXT-MEMORY-CARD-AB-2026-08-12.md`) |
| I1 기억 추출 | 게이트 리포트 자동 해석 → 검증 PASS 때만 추출 ON(fail-closed), 게이트 프로파일 strict/balanced | Mi:dm·Qwen3.5·Granite 4.0·Kanana smoke 및 Gemma full 모두 FAIL, 추출 off 유지 (`완료/AIRI-NEW-EXTRACTION-CANDIDATE-GATE-2026-08-12.md`, `완료/AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md`) |
| MEM-04 | SQLite WAL + busy_timeout=5000ms (당초 500ms → 저하된 CI runner에서 락 실패 재발해 sqlite3 기본 예산 복원) | 완료, 활성화 후 락 경합 실측만 남음 |
| B3 모더레이션 | 한국어 금칙어 사전·SSE 문장 게이트·캐릭터 폴백 대사(C3) | **3종 배선·신규 3층 source test/typecheck/build·설치본 "필터당함" 배지 실기 완료** (`완료/AIRI-B3-ELECTRON-MODERATION-VERIFICATION-2026-08-12.md`) |
| C1 헌법 | 캐릭터 헌법 초안 (`진행예정/AIRI-CHARACTER-CONSTITUTION-DRAFT-2026-08-12.md`) | 관계·인사·클로징 반영. 정식 팬덤명 유보·일반 호칭 “시청자들” 확정. T-05 126번 예비 후보 보존·현행 음성 유지. 인간 검수 대기 |
| 문서 | TECH-SPECS 현행화, 색인 갱신 | 완료 |
| STT/마이크 | 기본 방송 프로파일을 chat/text + STT OFF로 고정, 런처 OFF 경로 실기 확인 | **완료** (`완료/AIRI-STT-OFF-BROADCAST-PROFILE-2026-08-12.md`); 실제 mic/AEC/barge-in은 사용자 재개 요청까지 보류 |

## 2. dev PC 필수 작업 — SSoT 실기 검증

**2026-08-12 완료.** 아래 1~4를 실제 설치 Electron 턴으로 검증했다. Mi:dm은
stale EXAONE tag 1회를 정규화했고 GPU runner는 단일이었다. EXAONE 롤백은
warmup·evaluator·provenance가 모두 일치했다. Mi:dm digest
`92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f`는
일치 pin 통과·고의 불일치 기동 차단 후 운영 런처 기본값으로 고정했다.
상세 증거는 `완료/AIRI-DEV-PC-SSOT-VERIFICATION-2026-08-12.md`에 있다.

1. 스택 기동 후 실제 Electron→11435 턴에서 `/health`의
   `chat_model.normalized_requests > 0`과 `last_requested_model`(Electron이
   보내는 tag)을 확인한다.
2. `ollama ps`로 foreground runner가 Mi:dm 단일인지 확인한다.
3. 롤백 경로: `-ChatModel exaone-airi:2.4b`로 기동 시 warmup·정규화·
   evaluator·provenance 전 경로가 exaone으로 일치하는지 확인한다.
4. digest pin 발효: `ollama-proxy.out.log`의 `chat_model_digest` 이벤트에서
   실측 digest를 복사해 `AIRI_CHAT_MODEL_DIGEST`(또는 런처
   `-ChatModelDigest`)로 재기동 → 통과 확인, 고의 불일치 값 → 기동 차단
   확인. 이후 운영 기동 스크립트에 pin을 고정한다.
5. 주의: `local-proactive` 마커는 SSoT 면제가 아니다(의도적).
   `eval/run_airi_proactive_soak.py --model X` 등 마커 없는 러너로 모델
   A/B가 필요하면 프록시를 `AIRI_CHAT_MODEL=<대상>`으로 기동하거나
   `AIRI_CHAT_MODEL_ENFORCE=0`을 쓴다. 문서 §재현자료의 4개 커맨드는 영향
   없다.

## 3. dev PC 필수 작업 — I1 게이트 리포트 생산

**Mi:dm 및 신규 로컬 후보 측정 완료, 모두 FAIL.** Mi:dm의 11436 격리 CPU
balanced 7 fixtures 결과는 기존과 같고,
`qwen3.5:4b-q4_K_M`은 `persistent_trait` smoke에서 recall 0/unexpected 1/alias
0으로 25,696.794 ms에 fail-fast FAIL했다. `gemma3:4b`는 같은 smoke는 PASS했지만
full 7-row balanced에서 recall 0.5, unexpected 5, op/alias 0.5714285714,
connectivity 0.8571428571, coverage 0.7142857143으로 FAIL했고 독립 verifier도
거부했다. 마지막 공식 후보 `granite4:3b`도 smoke에서 schema/connectivity/coverage는
통과했지만 recall 0/alias 0으로 20,067.440 ms에 fail-fast FAIL했다. 상세 증적은
`완료/AIRI-NEW-EXTRACTION-CANDIDATE-GATE-2026-08-12.md`다.
2026-08-13에는 Kanana 공식 commit
`6a5d7889964c4c590299d16e309eabab1f73f8a9`의 BF16 shard를 직접 검증하고,
llama.cpp `b10375`로 Q4_K_M을 생성했다. Ollama tag
`kanana-airi-extraction:3b-q4_k_m` digest
`4a1d0b3322b50ffe5b16990129ab14f46abe1835e9b871e2b42a5ed144f65b9a`의
`persistent_trait` smoke도 schema/connectivity는 통과했지만 recall 0,
coverage 0, unexpected 1, op/alias 0, total 24,715.938 ms로 fail-fast FAIL했다.
full은 생략했다. 상세는
`완료/AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md`다.
Mi:dm은 11436 격리 CPU 서버의 balanced 7 fixtures에서
구조 schema는 1.0이었지만 critical recall 0.2619, Stage B coverage 0.4286,
op alias accuracy 0.1429로 불합격했다. total latency P50/P95는
20.19/34.16초였고 독립 verifier도 거부했다. 실패 리포트는 운영 추출을
활성화하지 않으며 다음 후보 선정이 필요하다. 상세는
`완료/AIRI-MIDM-EXTRACTION-GATE-MEASUREMENT-2026-08-12.md` 참조.

추출 자동 ON은 **게이트 리포트가 존재하고 검증을 통과할 때만** 발효된다.
현재 모든 candidate report가 FAIL이며, `/health`도 `extraction_enabled=false`,
`extraction_ready=false`, external extraction=false다. 다음 통과 후보 선정·재측정이
필요하다. Kanana 공식 원본 기반 자체 변환 provenance와 로컬 smoke는 완료했지만
품질 FAIL이다. 공개·수익 방송의 Kanana Open License §4.1/4.2 분류는 법률 검토
또는 Kakao 서면 확인 전 미승인이고, §2.2·§3.1 준수도 별도다. 표시·Notice만으로
충분하다고 해석하지 않는다. 제3자 Q8_0 tag는 load·측정하지 않았고 운영 근거로
쓰지 않는다.

```powershell
# 11436 격리 Ollama 서버 필요 (기존 절차)
python ollama-proxy\benchmark_memory_track.py --mode extraction `
  --model <후보 tag> --model-digest <sha256> `
  --gate-profile balanced `
  --report ollama-proxy\runtime\extraction-gate-report.json
```

- 통과 후: 스택 재기동만으로 자동 ON (`extraction_enabled=true` 확인).
- 함께 실측할 것: Stage A/B 실제 지연(공유 httpx read=120s 대비 — CPU
  2B·60메시지 배치가 초과하면 전용 타임아웃 분리 필요), 활성 상태
  SQLite 락 경합(MEM-04 재평가), 실제 대화→다음 세션 콜백 스모크
  (`eval/proxy_memory_smoke.py` 확장).
- **MEM-04 잔여 경계:** WAL·busy_timeout 코드는 완료됐지만 통과 extractor가
  없어 `extraction_enabled=true`의 실제 Stage B commit과 foreground
  append/retrieve를 겹치는 락 경합 실측은 아직 닫을 수 없다. 합성 store-level
  시험은 조기 위험 자료일 뿐 이 활성화 후 실측을 대체하지 않는다.

## 4. dev PC 필수 작업 — B3 배선 3종

1. **TTS 캐시 프리로드 (오디오 공백 금지의 실제 성립 조건)**:
   모더레이션 폴백 대사 5종(`ollama-proxy/moderation_terms_ko.json`의
   `blocked_dialogue`)은 검토 PC 시점 GPT-SoVITS 프리로드 캐시에 없어
   cold synthesis였다. `gpt-sovits/openai_compatible_proxy.py`의
   `IMMEDIATE_RESPONSE_TEXTS`와 동일한 mirror 계약으로 추가하라 —
   프록시 데이터 파일과 문자열이 1자라도 다르면 조용히 캐시 미스가 난다.
   — **완료:** literal mirror 테스트와 실기 cache readiness 7/7 통과.
2. **런처 env 배선**: `AIRI_OUTPUT_MODERATION`(on|off), 선택적
   `AIRI_OUTPUT_MODERATION_TERMS`(사전 경로)를 두 런처
   (`start-airi-local-stack.ps1` → `start-local-ollama-proxy.ps1`)에 전달한다.
   검토 PC 시점에는 동시 편집 충돌을 피하려고 의도적으로 남긴 배선 갭이었다.
   — **완료:** 기본 off, on/off 검증, 절대 사전 경로, 기존 proxy 재사용
   불일치 fail-closed, health 요약까지 배선.
3. **Electron "필터당함" 표시**: SSE 청크의 최상위 `airi_moderation:
   {blocked, category, rule, replaced}` 필드를 읽어 화면 표시(C3 결함의
   콘텐츠화). **완료:** 3층 source test/typecheck/build과 설치 Electron의
   실제 차단 턴에서 보이는 배지를 확인했다. 상세:
   `완료/AIRI-B3-ELECTRON-MODERATION-VERIFICATION-2026-08-12.md`.

추가 판단 항목: 사전 큐레이션 확대(리허설 트랜스크립트 기반 — JSON 작업),
반복 문자 패딩 우회(오차단 위험으로 의도적 미구현 — 실제 관측 시 옵션
추가), 비스트리밍 경로 2곳(`to_openai_sse`·native non-stream)은 TTS 경로가
아니라 미게이트(다른 클라이언트를 붙일 경우 재검토).

## 5. 기존 실기 게이트 (이월)

- **B0 선행 실측:** B0-2 완료 — 3단계 VRAM 6,084/6,131/6,289MiB,
  델타 +47/+158MiB(+205MiB), 최소 여유 1,736MiB, 실제 NVENC H.264 1080p60.
  B0-3 완료 — 설치 Electron 실제 턴 중 x264 1080p30 veryfast CPU 평균
  44.8%, 최대 70%, 최소 headroom 30%, 정상 5,346 frames
  (`완료/AIRI-B0-RESOURCE-MEASUREMENT-2026-08-12.md`). B0-1만 자격증명·
  외부 YouTube 실측 대기.
- **설치 Electron matched 모델 A/B 완료:** 같은 ASAR·TTS warm 상태에서
  Mi:dm→EXAONE→Mi:dm→EXAONE 교차 블록, 모델별 n=10. first substantive
  render P50/P95는 Mi:dm 1,501.5/2,597.2ms, EXAONE
  1,752.5/3,233.0ms였다
  (`완료/AIRI-INSTALLED-MODEL-RENDER-AB-2026-08-12.md`).
- **장문 context·memory·card A/B 완료:** raw Ollama, `num_ctx=2048`,
  4압력×3회에서 EXAONE exact 3/12, Mi:dm 0/12로 양 모델 FAIL. Mi:dm은 같은
  무압력 입력도 1,139 token(EXAONE 756)을 사용했고 card·부정을 0/12 보존했다.
  최신 정정·tail memory는 양 모델 12/12였다
  (`완료/AIRI-LONG-CONTEXT-MEMORY-CARD-AB-2026-08-12.md`).
- 실제 마이크 20+20, barge-in 200~500ms, speaker AEC, STT-06 마이크 품질은
  사용자 요청으로 추후 보류한다. 사용자가 “마이크 테스트 시작”을 요청하면
  현재 확인된 `마이크(USB Audio Device)`로 재개한다.
- **인간 검수 100건 수집** — eval provenance가 해소됐으므로 이제 수집한
  평가 데이터를 승격 근거로 쓸 수 있다 (이전에는 모델 오표기 위험으로
  불가).

## 6. 알려진 잔여 리스크 (수정 보류 — 근거 포함)

- `character_state_evaluator.py:77,110`의 exaone 기본값: 런처가
  `AIRI_CHARACTER_EVALUATOR_MODEL`을 항상 설정해 운영상 커버. SSoT 함수
  역참조는 순환 import라 보류.
- eval 러너 CLI `--model` 기본값들(run_airi_baseline 등): A/B는 항상 명시
  지정이므로 실해 없음.
- health 스키마 변경: `immediate_ack`가 `silent`→`audible`(사용자 턴
  기준), `chat_model`·`output_moderation` 섹션 신설. 외부 소비자는 레포
  내 0건 확인됨 — 별도 대시보드가 있으면 확인.
- generic proxy launcher의 digest pin은 명시값이 없으면 관측 모드다. root
  운영 런처는 Mi:dm 실측 digest를 기본값으로 고정해 fail-closed가 성립한다.
  EXAONE 롤백은 승인 digest를 별도로 주지 않으면 unpinned 관측 모드다.

## 7. 로드맵 현황판 갱신 의무 (신규 규칙)

`airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`가 전 축(G·C·지연·M)의 살아있는
현황판이다. **dev PC에서도 매 작업 배치 커밋마다 이 문서의 상태·갱신
로그를 갱신하라.** 갱신 없는 배치는 완결로 보지 않는다. 위 §2~§4를
수행하면 최소 G2(게이트 리포트)·M1(B0)·M3(B3 배선) 행이 바뀐다.

## 8. 사용자 결정 결과 (2026-08-12 처리)

방송 계획 §4의 4건 처리됨: ① 관계 축 — AI 단독형 + 메타 서사("사장님")
확정 ② 방송 중 클라우드 LLM — 조건부(즉시 승인 아님, dev PC 실측 2종 후
재결정) ③ 캐릭터 **방향 결정** — 이름 AIRI·호칭 "사장님"·시그니처
인사·클로징은 확정. 헌법 자체의 최종 승인은 인간 검수 대기다. 팬덤명
“아이리스”는 공개 충돌 FAIL로 철회했고, 정식 팬덤명 없이 일반
호칭 “시청자들”을 쓰다가 방송에서 자연스러운 호칭이 쌓인 뒤 재검토한다
(`완료/AIRI-FANDOM-NAME-COLLISION-CHECK-2026-08-12.md`). T-05는 126번을
한국어 예비 후보로 보존하되 낭독조·감정 부족 때문에 운영 승격하지 않고
현행 일본어 참조 음성을 유지한다
(`완료/AIRI-T05-KOREAN-SPEAKER-CANDIDATES-2026-08-12.md`) ④ 첫 방송 목표 시점 — 조건 기반
확정(M3 → 비공개 리허설 → 데뷔, 날짜 고정 없음). 헌법 초안 §5(관계
규정)·§6(인사·클로징·시청자 호칭)이 이 결과를 반영했다
(`진행예정/AIRI-CHARACTER-CONSTITUTION-DRAFT-2026-08-12.md`). 모더레이션
폴백 대사 5종은 B3 실기까지 완료했으며, 향후 문구 재승인은 선택적 조정이다.

## 9. dev PC 신규 작업 상태 (2026-08-12 사용자 결정 반영)

1. **cloud_chat_provider 스트리밍 지연 실측** (결정 2의 전제) —
   `ollama-proxy/benchmark_cloud_chat_latency.py` 하네스와 테스트는 완료.
   live TTFT/지연 P50은 `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY`와 외부
   승인 부재로 보류(`진행중/AIRI-CLOUD-CHAT-LATENCY-MEASUREMENT-2026-08-12.md`).
   codex 구독 경로(비스트리밍)는 TTFT 8~15s로 이미 부적합 확정됐으므로,
   이 실측은 스트리밍 경로 단독 대상이다. 결과가 결정 2(방송 중 클라우드
   LLM)의 재결정 근거가 된다.
2. **T-05 한국어 화자 후보 합성 샘플** — 라이선스 확인된 3개 후보 생성과
   사용자 1차 청취 완료. 126번을 예비 후보로 선택했지만 낭독조·감정 부족
   때문에 운영 승격은 보류하고 현행 일본어 참조 교차클로닝을 유지한다.
   감정이 드러나는 대화체 조건으로 다시 A/B할 때 126번을 우선 사용한다.
3. **장문 context·memory·card 비교** — 합성 전용 하네스·CI test와 모델별
   4압력×3회 실측 완료. 양 모델 FAIL이므로 측정 항목은 닫되 품질 위험은
   인간 검수와 문맥 예산/표현 개선 후 회귀 대상으로 유지한다.

   **2026-08-13 후속:** root `-NumCtx`/비공백 `AIRI_NUM_CTX`를 strict
   512..32768(기본 2048) SSoT로 모든 child·verify-only·warmup·재사용 health에
   배선했다. invalid env는 서비스 작업 전 거부, live 2048 재사용에 4096 요청은
   fail-closed 거부다. `/health.prompt_budget`은 prompt 원문 없이 terminal-sampled
   숫자 telemetry만 제공한다. Mi:dm raw 4096은 초기 사용자 절단을 해소했지만
   exact/card/부정 0/12이므로 품질 FAIL, default는 2048 유지다. GPU 최소 여유
   543 MiB도 clean B0 proof가 아니다. malformed/fractional health `num_ctx`도
   정확히 거부된다. current Python 3.12 41-path matrix는 833 passed / 1 skipped /
   708 subtests / 7 warnings (64.98s) PASS이며, proxy full은 286 passed / 377
   subtests / 5 warnings (2.23s), API shard는 323 passed / 569 subtests다.
   historical 829는 base `aef5300`만의 수치다. 상세:
   `완료/AIRI-CONTEXT-WINDOW-SSOT-AND-4096-TRIAGE-2026-08-13.md`.

4. **production context·continuity gate (2026-08-13, v2)** — 실제 proxy 경로의 budget/card/정정 표현과 고정 0/8/20/48 압력×3회 측정은 완료했다. generic structured-output 계약으로 spoken style 충돌을 제거하고 source-oriented fields·답 canary가 없는 질문·swapped/reordered anti-overfit test를 추가했다. 7개 필드 중 6개는 12/12이고 두 continuity color 필드는 v1의 11/12에서 개선됐으나, `dialogue_marker` 0/12가 memory marker `silver-fern`을 결정적으로 복사해 semantic/gate/authoritative 전체는 FAIL이다. dialogue-vs-memory는 모델 한계로 결론냈으므로 prompt tuning을 계속하지 않는다. raw capacity A/B를 대체하지 않으며 default 2048, extraction OFF를 유지한다. v2 전체 CI-equivalent Python 3.12.13 matrix는 858 passed / 1 skipped / 7 warnings / 708 subtests (45.04s) PASS다. 상세: `완료/AIRI-PRODUCTION-CONTEXT-CONTINUITY-GATE-2026-08-13.md`.

5. **STT/실제 마이크** — 기본 방송은 chat/text 입력 + STT OFF이며 Electron
   마이크 토글도 OFF다. 기본 런처는 `-Stt off`; 명시적인 `-Stt on` 또는
   `AIRI_STT=on`만 opt-in이다. 사용자가 STT/마이크 개발 재개를 요청하면
   `-Stt on`으로 시작해 실제 mic 20+20, AEC, barge-in 시험을 수행한다.
   TTS 참조 음성 관련 경고는 이 결정과 별개다.
