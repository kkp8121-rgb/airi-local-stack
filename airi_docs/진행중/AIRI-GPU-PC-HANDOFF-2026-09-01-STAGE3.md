# AIRI GPU PC 인계 — M8 Stage 3 (Mi:dm 교정 파인튜닝) (2026-09-01)

이 문서가 GPU PC의 **단일 진입점**입니다. 먼저 `git pull --ff-only origin main`을 실행한 뒤
`AGENTS.md` → `AIRI-WORKING-STATE.md` 전체 → 이 문서 →
`AIRI-VOD-STORYLINE-CEILING-EVIDENCE-2026-08-28.md` →
`AIRI-METHOD-RESEARCH-2026-08-28.md` → `AIRI-ROADMAP-STATUS.md`(M8 절) →
`NEXT-SESSION.md` 순으로 읽으십시오. 문서와 기계 상태가 다르면 실행하지 말고 관측값으로
문서를 먼저 정정하십시오.

> ⚠️ **이 인계 시점에 검토 PC의 작업물은 아직 push되지 않았습니다.** 아래 §7의 미커밋 목록을
> 먼저 확인하고, 사용자 승인된 push가 끝난 뒤에 pull하십시오. push 전에 GPU PC에서
> 작업을 시작하면 코드가 갈라집니다.

## 1. 왜 GPU PC로 넘어왔는가 (한 줄)

추론 시점(Stage 1)과 서빙 계층(Stage 2)의 **모든 레버를 소진했고 품질 통과는 0/3**이다.
남은 단계는 학습뿐인데 검토 PC에는 **CUDA 장치가 없어 물리적으로 실행 불가**다.

## 2. 확정된 사실 (추측 아님 — 전부 실측)

### 2-1. 닫힌 것

| 결함 | 조치 | 결과 |
|---|---|---|
| beat 원문 낭독 | 14자 연속 일치 거부 (임계값은 run-81 분포로 결정) | 10/96 → **0/96** |
| 세계관 붕괴("촬영 특수효과") | 이야기 밖 화법 거부 | 1 → **0** |
| 질문 종결 `?` | 서빙 계층 토큰 차단 534개 | 11턴 → **0턴** (구조적) |

### 2-2. 어떤 레버로도 닫히지 않은 것

암묵 자기 경험(~8턴) · 조언 프레이밍(2~4턴) · 역할 전도(시청자를 주인공으로) ·
beat 모순 · 같은 내용 3문장 반복 · 파손 출력.

### 2-3. 폐기된 접근 (재시도 금지 — 근거 있음)

- **CRANE 단일 콜 다문장**: 형식 시연을 줘도 구분자 출력 3/64. 이 모델은 한 콜에 다문장
  구조를 못 낸다 (run-84·85·86).
- **depth injection / 지시문 추가**: 순악화. 지시가 늘수록 예시를 더 베낌 (run-90).
- **검증기 적층**: 논문으로도 반증(arXiv 2404.17140 · 2310.01798 · 2508.09074 —
  ≤13B는 약한 verifier로 자기교정 불가, 롤플레이는 reward-ambiguous).
- **토큰 차단으로 의미 통제**: 문자를 막아도 행위는 생존. `?` 차단 후 의문문이
  종결부 없는 run-on과 말줄임(0→3턴)으로 변형됨 (run-92).

### 2-4. 자동 채점기를 믿지 말 것 (중요)

`slot_candidate_score`·`cue_term_matches`가 **beat 텍스트와의 어휘 일치**로 채점하므로,
모델이 beat를 복창하면 만점이 나온다. 과거 `quality_pass=true` 회차
(48·53~56·60~62·76)는 전부 이 부풀림 위의 값이다. **자동 지표는 바닥 지표
(32/32·8/8·시그니처 0·오류 0·반복 0)로만 유효하고, 판정은 32턴 수동 7항목이다.**

## 3. Stage 3 — GPU PC가 할 일

### 3-1. 처방 (근거: arXiv 2502.12143, Qwen2.5-3B에서 실증)

과거 합성 데이터 파인튜닝 6라운드 전패의 유력한 원인은 **Small Model Learnability Gap**이다
— 3B 이하는 큰 teacher의 길고 복잡한 출력으로 학습하면 오히려 나빠진다. 따라서:

- **teacher를 키우지 말 것.** 작은 teacher 또는 짧은 출력이 더 잘 전이된다.
- **Mix Distillation**: 긴/짧은 예시를 1:4, 또는 대/소 teacher 출력을 1:1로 혼합.
- **베이스는 Mi:dm 유지** — 사용자 지시로 모델 교체는 최후순위다(한국어 능력).

### 3-2. 학습 데이터의 출처는 이미 있다

이번 M8의 **결함 목록 자체가 평가셋**이다. run-89(최선)와 run-92(서빙 통제)의 32턴
transcript에 각 턴의 결함 범주가 분류돼 있다. 교정 데이터는 "이 턴에서 무엇이 잘못됐고
어떤 한 문장이 옳았는가"로 만들면 된다 — 합성 시나리오를 새로 지어내지 말 것.

### 3-3. 저장소에 있는 학습 스캐폴드

`ollama-proxy/training/` — `train_airi_behavior_lora.py`, `train_airi_style_qlora.py`,
`merge_airi_behavior_lora.py`, `package_airi_gguf.py`, `durable_training_runner.py`,
`behavior_training_checkpoint.py`. 스캐폴드는 **권한이 아니다**: 트레이너가 데이터 SHA·
manifest·closed report를 재검증하고 원격 모델·네트워크 경로·불안전 CUDA를 거부한다.
전원 종료 대비는 `pause-airi-safely.ps1`(`SAFE_TO_POWER_OFF` 출력 전 전원 차단 금지).

## 4. 평가 환경 재현 (검토 PC와 동일 조건 만들기)

### 4-1. 지식 DB

저장소 배치 3종을 **runtime 내부 절대경로로 복사한 뒤** game→meme→culture 순 적재.

```powershell
python ollama-proxy\knowledge_batch.py lint --input <runtime>\kb-*.jsonl --runtime-dir <runtime>
python ollama-proxy\knowledge_ingest.py --runtime-dir <runtime> --input <runtime>\kb-game-001.jsonl --apply
# meme, culture 순서대로 반복
python ollama-proxy\knowledge_batch.py probe --queries ollama-proxy\eval\knowledge_probe_queries.txt --min-hit-rate 0.9
```

- 상대경로를 주면 `runtime_path()`가 CWD 기준으로 풀어 `KnowledgeInputError`로 거부된다.
- 검토 PC 최종값 **documents=144, chunks=287**, probe **6/6**. (Codex PC는 153/296 —
  그 PC에만 있던 기존 문서 9건 차이이며 probe는 144건 배치만으로 6/6이다.)
- **DB count를 미리 가정하지 말고 실측하고, `/health`와 대조한 뒤에만 회차를 시작할 것.**

### 4-2. 스택 기동 함정 두 가지 (검토 PC에서 실제로 겪음)

1. **PowerShell 5.1 필수.** 런처의 affect 계약이 `prompt_cap_bytes`를 `[int]`로 요구하는데
   pwsh 7은 JSON 384를 `Int64`로 파싱해 거짓 실패한다. `powershell.exe`로 실행할 것.
2. **첫 토큰 마감 8초는 CPU에서 콜을 폴백으로 대체한다.** GPU PC는 빠르므로 기본값으로도
   될 수 있으나, 폴백 문구(`답이 늦어져서 잠깐 멈췄어.`)가 draft에 반복되면 이 증상이다.
   `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS`(유효 1~30)를 올려 확인할 것.
   검토 PC는 30으로 운용했다.

### 4-3. 모델 digest 핀

런처는 `midm-airi:2.0-mini`의 digest를 하드코딩 핀
(`92a9ba2e…485f`)과 대조해 fail-closed한다. 검토 PC의 태그는 `106cfaac…9f6c`로 달랐는데,
**가중치는 동일**했다 — 신형 Ollama(0.32.14)가 manifest에 layer별 `from` 필드를 추가해
manifest 해시만 바뀐 것이다(가중치 layer `sha256:31beb9a8…55c3`는 핀된 소스 GGUF와
byte-identical, template 277B·params 155B도 Modelfile과 동일).
GPU PC에서 같은 불일치가 나면 **핀·Modelfile·태그를 바꾸지 말고** 위 3요소를 대조해
동일성을 확인한 뒤 런처의 `-ChatModelDigest`로 그 PC의 실측값을 명시하십시오.

## 5. 재사용 자산 — 다시 만들지 말 것

| 자산 | 경로 | 용도 |
|---|---|---|
| 고정 8막·32턴 시나리오 | `ollama-proxy/eval/broadcast_sim/vod_storyline_20260827.json` | 학습 전후 비교의 고정 입력 |
| 평가 러너 | `ollama-proxy/eval/broadcast_sim/run_vod_storyline.py` | 최선 구성 = run-89 형태(프레이밍 ON, 슬롯 예시 2종, depth reminder 빈 문자열) |
| llama-server shim | `ollama-proxy/eval/llama_server_shim.py` (+18 오프라인 테스트) | 프록시 **무변경**으로 `logit_bias`·`grammar` 사용. Ollama 자리(11434)에 두고 llama-server(11500)로 중계 |
| 지식 배치 144건 | `ollama-proxy/eval/knowledge_batches/` | **재생성 금지** (두 PC 코퍼스 분기 방지) |
| 고정 probe 6종 | `ollama-proxy/eval/knowledge_probe_queries.txt` | 지식 준비 확인 |

**llama-server는 새로 설치할 필요가 없다** — Ollama가 번들한
`%LOCALAPPDATA%\Programs\Ollama\lib\ollama\llama-server.exe`가 `--logit-bias`·`--grammar`·
`--grammar-file`·`--json-schema`를 지원한다. 다만 Ollama API에는 `logit_bias`가 없고,
프록시는 Ollama 전용 `/api/chat`을 쓰므로 shim이 필요하다.

토큰 차단 집합이 필요하면 GGUF 메타데이터 `tokenizer.ggml.tokens`(131,392개)를 덤프해
**GPT-2 byte-to-unicode 역변환으로 디코딩한 뒤** 표면형을 매칭하십시오. 표준 표면형만
열거하면 실패합니다 — 앞선 공백이 붙은 병합 토큰이 다른 ID입니다
(` 좋습니다`=6623, `안녕하세요`=7602). 시/셨 어간(`꾸셨`)은 검토 PC 집합에서 빠져 있었으니
보완하십시오.

## 6. 판정 프로토콜 (바꾸지 말 것)

1. **자동 = 바닥 지표만 필수**: 32/32 · 8/8 장면 순서 · 금지 시그니처 0 · 빈응답/오류 0 ·
   반복 0 · 고중복 0. `quality_pass`는 판정자가 아니다(§2-4).
2. **판정 = 32턴 수동 7항목**: ①구체적 시청자 반응 ②새 사건+복선 회수 ③감정이 대사로
   ④반복 0 ⑤내부 연출어·조언 0 ⑥원방송 경험 도용 0 ⑦무관 지식·시그니처 0.
3. **통과 시 같은 구성 재현 2회** → 3연속으로 확정(비결정성 대비, run-13 전례).
4. 한 회차 한 레버. 결함 범주가 줄면 조합 누적, 불변·악화면 그 레버 폐기.

## 7. 미커밋 상태 (GPU PC 착수 전 반드시 해소)

검토 PC local `5f4bd8e` = origin/main. **아래 12개가 아직 커밋되지 않았습니다.**

수정 8: `NEXT-SESSION.md`, `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`,
`airi_docs/로드맵/AIRI-ROADMAP-{STATUS,LOG}.md`,
`airi_docs/진행중/AIRI-{WORKING-STATE,CLAUDE-HANDOFF-2026-08-28-VOD-STORYLINE}.md`,
`ollama-proxy/eval/broadcast_sim/run_vod_storyline.py`, 같은 디렉터리 `test_vod_storyline.py`

신규 4: `airi_docs/진행중/AIRI-{METHOD-RESEARCH,VOD-STORYLINE-CEILING-EVIDENCE}-2026-08-28.md`,
`ollama-proxy/eval/llama_server_shim.py`, `ollama-proxy/eval/test_llama_server_shim.py`
(+ 이 문서)

검증 상태: storyline+proxy 계약 통과, broadcast_sim/rehearsal 759 passed/1 skipped,
shim 18 passed, `git diff --check` clean, 대시보드·work-continuity 계약 PASS.
**CI 미등록 1건**: `test_llama_server_shim.py`를 sharded root에 두었으므로 CI에서 돌리려면
`.github/workflows/remediation-checkpoint.yml` 매트릭스에 추가해야 한다(평가 전용이라
등록하지 않는 선택도 가능 — 판단 필요).
기준 HEAD부터 있던 별건 결함: `ollama-proxy/test_broadcast_examples.py`와
`test_opener_resample.py`가 tracked인데 어느 workflow에도 없다.

## 8. 금지선 (유지)

3.0 절대 채택 게이트 · S3 채택 근거 · pickup/replay 트랙 · 점수 가중치 피팅 ·
운영 활성화(`adoption_authorized=false`) · **운영 모델 태그 변경** ·
지식 배치 재생성 · 원문/report/채점/SQLite/오디오/HMAC 키의 Git 반입 ·
**승인 없는 commit/push**(매 건 별도 승인) · Stage 순서 위반(모델 교체는 최후순위).

## 9. GPU PC에 제출할 Goal

```text
/goal resume

목표:
M8 Stage 3 — Mi:dm 베이스를 유지한 채 교정 파인튜닝으로, 추론·서빙 레버로 닫히지 않은
결함(암묵 자기 경험·조언 프레이밍·역할 전도·beat 모순·반복)을 줄이고, 고정 VOD 8막 32턴에서
수동 7항목 통과를 재현 포함 3회 연속 확보한다.

첫 행동:
AGENTS.md → WORKING-STATE 전체 → AIRI-GPU-PC-HANDOFF-2026-09-01-STAGE3.md →
한계 실증·대안 기법 리서치 문서 → ROADMAP-STATUS(M8) → NEXT-SESSION을 읽고
Git/PID/listener/DB/health/CUDA를 read-only로 대조한다. 지식 DB는 실측 후 probe 6/6과
/health 일치를 확인하기 전에는 회차를 시작하지 않는다.

실행:
Small Model Learnability Gap 처방(작은 teacher·짧은 예시·Mix Distillation)으로 교정 데이터를
만들되, 새 합성 시나리오를 지어내지 말고 run-89·run-92의 32턴 결함 분류를 근거로 만든다.
학습 전후를 같은 고정 시나리오로 비교하고, 자동 지표는 바닥 지표로만 쓰고 판정은 32턴 수동
검토로 한다. 한 회차 한 변수.

금지:
§8 금지선 전부. 특히 운영 모델 태그 변경과 승인 없는 push.
```
