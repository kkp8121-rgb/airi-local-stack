# AIRI Claude 인계 — VOD storyline 반응 품질 자가 테스트 (2026-08-28)

이 문서가 다른 PC Claude의 단일 진입점입니다. 먼저 `git pull --ff-only origin main`을 실행한 뒤
`AGENTS.md` → `AIRI-WORKING-STATE.md` 전체 → 이 문서 →
`AIRI-EVAL-INPUT-CONTEXT-AUDIT-2026-08-27.md` → `AIRI-ROADMAP-STATUS.md` →
`NEXT-SESSION.md` 순으로 읽으십시오. 문서와 기계 상태가 다르면 실행하지 말고 관측값으로 문서를
먼저 정정하십시오.

VOD storyline 구현·테스트·현행 문서 배치 commit은
`b5abd7843b2198861ca885d565c831c9deb548ef`입니다. 이 문서의 최종 인계 receipt는 바로 다음
문서 전용 commit에 들어갑니다.

## 1. 현재 결론

- 구조 테스트 하네스는 작동합니다: 고정 8막, 장면당 4개 시청자 입력, 총 32턴, 장면 순서,
  금지 방송 시그니처, 빈 응답/서비스 오류, 사건·callback·next-hook·감정, 반복·고중복,
  원방송 경험 도용, 무관 지식을 회차별 외부 report로 남깁니다.
- 품질 통과는 아직 **0/3회**입니다. 자동 구조 게이트가 참인 회차도 수동 transcript 검토에서
  의료 조언, 질문 종결, 내부 연출어, AIRI의 원방송 경험 도용 때문에 무효화됐습니다.
- 최신 유효 완주 회차는 **run-78**입니다. 32/32·8/8·1536 slot 후보·금지 시그니처 0·오류 0,
  repeat/high-overlap/source-marker/irrelevant-marker 0이지만 자동 emotion variation 실패 및 수동
  품질 실패입니다. report SHA256은
  `8b6c5b397bcfb2d79ea9eb123b1fc74bf55a10b88f4ce7939e15ad5b6e2f7304`입니다.
- run-79는 명령에서 `--rewrite-passes 1 --rewrite-format slotwise`를 누락한 잘못된 실행입니다.
  비교·품질 회차로 사용하지 마십시오.
- run-80은 정확한 slotwise 명령으로 시작했지만 사용자가 인계로 전환해 19/32에서 중단했습니다.
  runner는 terminal에서만 report/HTML을 쓰므로 완성 산출물이 없습니다. 이어서 실행하지 말고 새
  외부 디렉터리에서 turn 1부터 다시 실행하십시오.

“리제 급”은 특정 인물 문장 복제가 아니라 다음 관측 특성입니다: 시청자 발화를 구체적으로 받아치기,
이전 복선 회수, 매 턴 줄거리 전진, 감정 변화, 반복 억제, 원방송 경험 비도용, 시청자 입력의 사적
약속어 제거. 3회 연속 전체 시나리오 수동 품질 통과 전에는 달성했다고 선언하지 마십시오.

## 2. 저장소 작업물

- `ollama-proxy/eval/broadcast_sim/vod_storyline_20260827.json`: 저장된 31.64분 STT에서 만든
  고정 8막·32턴 줄거리와 장면별 시청자 입력입니다.
- `ollama-proxy/eval/broadcast_sim/run_vod_storyline.py`: 정제, 전송, slotwise 후보 생성·선택,
  report/HTML, 구조 지표를 담당합니다. 응답 원문과 report는 `--report`, `--review-html`로 지정한
  저장소 밖 경로에만 씁니다.
- `ollama-proxy/eval/broadcast_sim/test_vod_storyline.py`: 장면 순서, 약속어 변형 제거, slot cue,
  source/staging validator 계약입니다.
- `ollama-proxy/ollama_proxy.py`·`test_ollama_proxy.py`: 명시적 `local-evaluation` origin만 방송
  응답 계약과 synthetic grounding 허용을 사용합니다. 운영 live capability를 켜지 않습니다.
- `ollama-proxy/eval/broadcast_chat/run_broadcast_chat_ab.py`: 평가 transport의 선택적 structured
  `format` 전달입니다.

현재 working code에는 run-79 뒤 시작한 **미검증 단일 변경**이 남아 있습니다.
`build_turn_system()`의 건강·약·술 지시를 실제 상담이 아닌 허구 방송 사건/감정으로 한정해,
의료 조언과 AIRI 자기 경험으로 흐르는 충돌을 줄이는 `fictional-health-story-boundary`입니다.
run-80이 중단됐으므로 이 변경의 전체 32턴 결과는 아직 없습니다. 먼저 이 변경만 검증하십시오.

### 이 PC의 게시 전 검증

- `py_compile`: storyline runner, broadcast transport, proxy, proxy test 통과
- 오프라인 storyline 계약 **8/8**, `ollama_proxy` unittest **411/411**,
  broadcast rehearsal **85/85**, broadcast_sim **105/105** 통과
- roadmap dashboard·work-continuity 계약과 `git diff --check` 통과
- 종합 `test-current-checkpoint.ps1`은 work-continuity·dashboard·training durability까지 통과한 뒤
  기존 CI 매트릭스 불일치로 실패했습니다. 기준 HEAD `53befcb`에 이미 추적된
  `ollama-proxy/test_broadcast_examples.py`, `ollama-proxy/test_opener_resample.py`가 기준 HEAD의
  workflow 목록에 없는 문제입니다. 이번 VOD 변경의 통과로 오인하거나 인계 중 숨기지 마십시오.

## 3. 자산과 DB 경계

필요한 Git 자산은 저장소 안에 있습니다.

- 지식 배치 144건: `ollama-proxy/eval/knowledge_batches/` — 재생성 금지
- VOD 채팅 5,243행·STT 500세그먼트·응답쌍 57행:
  `ollama-proxy/eval/vod_capture_2026-08-27/`
- 고정 회수 질의 6종: `ollama-proxy/eval/knowledge_probe_queries.txt`

SQLite runtime DB, 채점 결과, 회차 report/HTML, 대화 export, 오디오, HMAC 키, 가명화 전 원본은
Git에 없습니다. 현재 Codex PC의 authoritative DB는 `documents=153, chunks=296`, probe 6/6입니다.
다른 PC에서는 **153을 미리 가정하지 마십시오**. 기존 DB count를 먼저 읽고, 저장소 배치 세 개를
runtime 내부 절대경로에서 game→meme→culture 순으로 적재하며 각 inserted/updated/duplicate를
기록하십시오. 최종 count가 Codex PC와 다르면 원인을 규명하기 전에는 같은 조건의 비교 회차로
간주하지 마십시오. 어느 경우든 고정 probe 6/6과 `/health`의 DB count 일치가 선행 조건입니다.

## 4. 재개 명령

오프라인 계약부터 확인하십시오.

```powershell
python -m py_compile ollama-proxy/eval/broadcast_sim/run_vod_storyline.py
python -m pytest -q `
  ollama-proxy/eval/broadcast_sim/test_vod_storyline.py `
  ollama-proxy/test_ollama_proxy.py
git diff --check -- . ':(exclude)airi_docs/patches/*.patch'
```

스택은 memory ON·knowledge ON으로 띄우고, 적재한 DB 경로와 `/health` count를 대조하십시오.
현재 변경의 첫 유효 실행은 아래 명령 형태를 사용하되, 외부 run 번호는 기존과 겹치지 않게 새로
정하십시오. `--rewrite-passes 1 --rewrite-format slotwise`를 빼면 run-79처럼 무효입니다.

```powershell
python ollama-proxy/eval/broadcast_sim/run_vod_storyline.py `
  --base-url http://127.0.0.1:11435/v1 `
  --model midm-airi:2.0-mini `
  --turn-origin local-evaluation `
  --per-scene-turns 4 `
  --history-turns 8 `
  --max-tokens 220 `
  --rewrite-passes 1 `
  --rewrite-format slotwise `
  --tuning-cause response-format `
  --tuning-change fictional-health-story-boundary `
  --report <저장소-밖-새-root>\vod-storyline-report.json `
  --review-html <저장소-밖-새-root>\vod-storyline-review.html
```

자동 `quality_pass`만으로 통과 처리하지 마십시오. 32개 최종 응답을 모두 읽고 다음을 확인하십시오.

1. 각 턴이 시청자 입력을 구체적으로 받는가
2. 새 사건을 말하고 이전 단서와 다음 고리를 연결하는가
3. 장면별 감정 변화가 실제 대사로 드러나는가
4. 같은 문장·정보·감탄사를 반복하지 않는가
5. 내부 카드·슬롯·다음 회차 홍보·의료 조언이 노출되지 않는가
6. AIRI가 원방송인의 꿈·병원·약·외출·추격 경험을 자기 경험으로 말하지 않는가
7. 무관한 지식과 금지 방송 시그니처가 0인가

실패하면 원인을 `줄거리 상태 전달 / 다음 사건 유도 / 응답 형식 / 감정 연출 / 반복 억제` 중
하나로만 선택해 최소 수정하고, 전체 32턴을 새 외부 root에서 다시 실행하십시오. 실패 회차와 원인은
WORKING-STATE에 intent/receipt로 남기되 transcript 본문은 Git에 넣지 마십시오.

## 5. 보존할 금지선

- M7 `3축 ≥ 3.0` 절대 채택 게이트와 S3 `[x]`를 사용하지 않습니다.
- pickup_priority, 점수제 가중치 57쌍 피팅, replay 재실행, S5를 하지 않습니다.
- GPU 학습·파인튜닝은 2026-09-09까지 금지입니다.
- `adoption_authorized=false`, 운영 flag OFF, 현행 모델 태그를 유지합니다.
- 지식 배치를 재생성하지 않습니다.
- 실제 대화 원문·채점·report·HTML·SQLite·오디오·키를 Git에 넣지 않습니다.
- commit/push는 다음 PC에서도 매번 별도 사용자 승인을 받습니다.

## 6. Claude에 제출할 Goal

```text
/goal resume

목표:
저장소의 고정 VOD 8막·32턴 storyline과 정상 지식 DB를 사용해 AIRI 반응 품질을 전체 시나리오로
검증하고, 수동 transcript 검토까지 포함한 품질 통과를 3회 연속 확보한다.

첫 행동:
AGENTS.md → WORKING-STATE 전체 → AIRI-CLAUDE-HANDOFF-2026-08-28-VOD-STORYLINE.md →
context audit → ROADMAP-STATUS → NEXT-SESSION을 읽고 Git/PID/listener/DB/health를 read-only로
대조한다. DB count가 Codex PC의 153/296과 다르면 원인을 규명하고 probe 6/6·health 일치 전에는
실행하지 않는다.

실행:
run-79와 run-80은 근거로 쓰지 않는다. 현재 미검증 fictional-health-story-boundary 변경 하나만
정확한 slotwise 옵션으로 새 외부 root에서 turn 1부터 검증한다. 매 회차 자동 지표와 32턴 수동
검토를 분리하고, 실패 원인 하나만 최소 수정한 뒤 전체 시나리오를 다시 실행한다.

완료 조건:
모든 장면에서 구체적 시청자 반응·이전 맥락 회수·다음 사건 연결·감정 변화가 확인되고, 반복·무관
지식·금지 약속어·원방송 경험 도용·내부 연출어가 0인 회차를 3회 연속 확보한다. 구조 통과와 품질
통과를 분리해 보고한다.

금지:
3.0 절대 채택 게이트, S3 채택 근거, pickup/replay/S5, 점수 가중치 피팅, GPU/파인튜닝, 운영
활성화, 모델 태그 변경, 저장소 내 원문/report/채점/DB 보관, 승인 없는 commit/push.
```
