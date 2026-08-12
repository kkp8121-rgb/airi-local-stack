# dev PC(codex) 인수인계 — 검토 PC 선행 작업 배치 (2026-08-12)

검토 PC(무GPU 검증 환경)에서 로드맵 중 오프라인으로 가능한 작업을 선행했다.
이 문서는 그 결과와, **dev PC에서만 가능한 잔여 검증·후속 작업**의 전체
목록이다. 착수 전 이 문서와 아래 근거 문서를 정독하라.

- 완료 커밋: `7dc4e76`(문서), `932eae6`(코드) — 기반 `294c4e6`
- 오프라인 검증: 전체 스위트 **809 passed / 1 skipped / 706 subtests**
  (기준 733/1/504), `test-patch-manifest.ps1` PASS, `git diff --check` 클린
- 계획 근거: `진행예정/AIRI-BROADCAST-CHARACTER-PLAN-2026-08-12.md` (M1
  착수분), `진행중/AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md` (게이트)

---

## 1. 검토 PC에서 완료된 것 (요약)

| 트랙 | 내용 | 상태 |
|---|---|---|
| 모델 SSoT | `resolve_chat_model()` 단일화(프록시 내 EXAONE 문자열 0건), foreground model 정규화, eval provenance, digest pin(opt-in), ACK metadata 교정 | 코드 완료, **실기 검증 대기** |
| I1 기억 추출 | 게이트 리포트 자동 해석 → 추출 자동 ON 배선(fail-open), 게이트 프로파일 strict/balanced | 코드 완료, **게이트 리포트 생산 대기** |
| MEM-04 | SQLite WAL + busy_timeout=5000ms (당초 500ms → 저하된 CI runner에서 락 실패 재발해 sqlite3 기본 예산 복원) | 완료, 활성화 후 락 경합 실측만 남음 |
| B3 모더레이션 | 한국어 금칙어 사전(113항목+개인정보 패턴 7)·우회 표기 8형 전수 차단·SSE 문장 게이트·캐릭터 폴백 대사(C3) | 코드 완료(기본 off), **배선·프리로드 대기** |
| C1 헌법 | 캐릭터 헌법 초안 (`진행예정/AIRI-CHARACTER-CONSTITUTION-DRAFT-2026-08-12.md`) | 초안 — 사용자 결정 1·3 대기 |
| 문서 | TECH-SPECS 현행화, 색인 갱신 | 완료 |

## 2. dev PC 필수 작업 — SSoT 실기 검증

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

추출 자동 ON은 **게이트 리포트가 존재하고 검증을 통과할 때만** 발효된다.
현재 리포트는 없으며, 완화(balanced)로도 기존 후보(EXAONE 2.4B, Qwen3
4B/8B)는 전부 불합격이다. **Mi:dm 2.0-mini는 추출기 후보로 미측정.**

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

## 4. dev PC 필수 작업 — B3 배선 3종

1. **TTS 캐시 프리로드 (오디오 공백 금지의 실제 성립 조건)**:
   모더레이션 폴백 대사 5종(`ollama-proxy/moderation_terms_ko.json`의
   `blocked_dialogue`)은 GPT-SoVITS 프리로드 캐시에 없어 현재 cold
   synthesis다. `gpt-sovits/openai_compatible_proxy.py`의
   `IMMEDIATE_RESPONSE_TEXTS`와 동일한 mirror 계약으로 추가하라 —
   프록시 데이터 파일과 문자열이 1자라도 다르면 조용히 캐시 미스가 난다.
2. **런처 env 배선**: `AIRI_OUTPUT_MODERATION`(on|off), 선택적
   `AIRI_OUTPUT_MODERATION_TERMS`(사전 경로)를 두 런처
   (`start-airi-local-stack.ps1` → `start-local-ollama-proxy.ps1`)에 전달
   (현재 두 런처 모두 참조 0건 — 검토 PC에서 동시 편집 충돌을 피하려고
   의도적으로 남긴 유일한 배선 갭).
3. **Electron "필터당함" 표시**: SSE 청크의 최상위 `airi_moderation:
   {blocked, category, rule, replaced}` 필드를 읽어 화면 표시(C3 결함의
   콘텐츠화). 클라이언트 패치 계약(3층) 안에서 진행.

추가 판단 항목: 사전 큐레이션 확대(리허설 트랜스크립트 기반 — JSON 작업),
반복 문자 패딩 우회(오차단 위험으로 의도적 미구현 — 실제 관측 시 옵션
추가), 비스트리밍 경로 2곳(`to_openai_sse`·native non-stream)은 TTS 경로가
아니라 미게이트(다른 클라이언트를 붙일 경우 재검토).

## 5. 기존 실기 게이트 (이월 — 변동 없음)

- **B0 선행 실측 3종** (방송 계획의 모든 결정의 전제):
  `liveChatMessages.streamList` 쿼터 과금 실측 / VRAM 3단계 델타
  (①STT+LLM+TTS ②+OBS ③+NVENC) / 5600X x264 CPU 여유.
- Mi:dm installed-app first-audible, 실제 마이크 20+20, barge-in
  200~500ms, speaker AEC, STT-06 마이크 품질.
- 같은 Electron build·TTS warm 상태에서 모델 순서 교차 matched
  text→render A/B (모델 교체의 체감 지연 확정용).
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
- digest pin은 opt-in이 기본: 미설정 시 관측·기록만 한다. 완전한
  fail-closed는 §2-4의 pin 고정 후 성립.

## 7. 로드맵 현황판 갱신 의무 (신규 규칙)

`airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`가 전 축(G·C·지연·M)의 살아있는
현황판이다. **dev PC에서도 매 작업 배치 커밋마다 이 문서의 상태·갱신
로그를 갱신하라.** 갱신 없는 배치는 완결로 보지 않는다. 위 §2~§4를
수행하면 최소 G2(게이트 리포트)·M1(B0)·M3(B3 배선) 행이 바뀐다.

## 8. 사용자 결정 결과 (2026-08-12 처리)

방송 계획 §4의 4건 처리됨: ① 관계 축 — AI 단독형 + 메타 서사("사장님")
확정 ② 방송 중 클라우드 LLM — 조건부(즉시 승인 아님, dev PC 실측 2종 후
재결정) ③ 캐릭터 확정 — 이름 AIRI·호칭 "사장님" 확정, 시그니처 인사·
팬덤명은 포지 후보 제안 → 사용자 확정 대기, T-05 음성 화자는 dev PC
샘플 생성 → 사용자 청취 검토 대기 ④ 첫 방송 목표 시점 — 조건 기반
확정(M3 → 비공개 리허설 → 데뷔, 날짜 고정 없음). 헌법 초안 §5(관계
규정)·§6(인사·팬덤명)이 이 결과를 반영했다
(`진행예정/AIRI-CHARACTER-CONSTITUTION-DRAFT-2026-08-12.md`). 모더레이션
폴백 대사 문구 확정은 여전히 결정 3의 잔여 항목(인사·팬덤명 선택)에
걸려 있다.

## 9. dev PC 신규 작업 2건 (2026-08-12 사용자 결정 반영)

1. **cloud_chat_provider 스트리밍 지연 실측** (결정 2의 전제) —
   `cloud_chat_provider.py` 스트리밍 경로의 TTFT/지연 P50을 실측한다.
   codex 구독 경로(비스트리밍)는 TTFT 8~15s로 이미 부적합 확정됐으므로,
   이 실측은 스트리밍 경로 단독 대상이다. 결과가 결정 2(방송 중 클라우드
   LLM)의 재결정 근거가 된다.
2. **T-05 한국어 화자 후보 합성 샘플 생성** (결정 3의 잔여 항목) — 공개
   라이선스 화자만 사용해 후보 화자 합성 샘플을 생성한다. 사용자 청취
   검토 1회 후 어울리는 후보가 없으면 현행(일본어 참조 교차클로닝)을
   유지한다.
