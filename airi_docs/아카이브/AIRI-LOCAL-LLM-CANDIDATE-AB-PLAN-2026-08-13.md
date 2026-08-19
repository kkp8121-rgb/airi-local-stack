# AIRI 로컬 LLM 전 후보 동일 조건 A/B 계획 — 2026-08-13

## 상태와 우선순위

- 상태: **즉시 착수하는 최우선 G3/C0 평가 배치**
- 목적: 명확한 허용 라이선스 후보와 사용자가 평가 예외로 승인한 Motif를 포함한
  모든 로컬 LLM 후보를 Mi:dm과 같은 AIRI 대화·캐릭터·문맥·안전·지연
  경로에서 비교한다.
- 운영 기본값은 결과가 나올 때까지 `midm-airi:2.0-mini`로 유지한다.
- extraction smoke 성공/실패는 foreground chat 품질 판정으로 재사용하지 않는다.
- 공식 공개 저장소의 metadata와 평가에 필요한 model weight를 로컬로 받는 것은
  이 배치 범위다. 외부 inference API, prompt/output 업로드와 telemetry는 허용하지
  않는다. 후보는 한 번에 하나씩 준비해 디스크·VRAM provenance를 분리한다.

## 후보 집합

| 역할 | 정확한 공식 저장소 | 라이선스 취급 | 상태 |
|---|---|---|---|
| 기준선 | `K-intelligence/Midm-2.0-Mini-Instruct` | MIT | 같은 환경에서 재측정 |
| 후보 | `Motif-Technologies/Motif-2.6b-v1.1-LC` | 사용자 승인 조건부 후보; MIT 표시와 Motif License 이력 충돌 기록 | 전 항목 평가 |
| 후보 | `mistralai/Ministral-3-3B-Instruct-2512-BF16` | Apache-2.0 | 전 항목 평가 |
| 후보 | `Qwen/Qwen3-4B` | Apache-2.0 | 전 항목 평가 |
| 후보 | `microsoft/Phi-4-mini-instruct` | MIT | 전 항목 평가 |
| 후보 | `ibm-granite/granite-3.3-2b-instruct` | Apache-2.0 | 전 항목 평가 |

EXAONE은 NC이므로 신규 공개·수익 방송 후보에서 제외한다. Kanana,
HyperCLOVA X SEED, Gemma, LFM 등 별도·제한적 라이선스 후보도 이번 배치에서
제외한다. 과거 결과는 비교 이력으로 보존하지만 신규 승격 점수에는 넣지 않는다.

## 모델별 사용 계약을 먼저 고정한다

모델마다 사용법이 다르므로 하나의 tokenizer/template/옵션을 억지로 공통 적용하지
않는다. 각 후보는 실행 전에 다음 **model usage manifest**를 작성하고 source URL,
exact revision과 파일 SHA-256으로 고정한다.

1. 공식 model card와 공식 저장소가 요구하는 최소 library/version
2. `trust_remote_code` 필요 여부와 실행되는 Python 파일/import 표면
3. tokenizer 및 공식 chat template, system role 지원·처리 방식
4. thinking/reasoning 모드의 존재와 정확한 on/off 방법
5. EOS/pad/stop token과 generation prompt 처리
6. 공식 권장 temperature/top-p/top-k/min-p/repetition 설정
7. native context 한도와 AIRI 유효 `num_ctx=2048`의 차이
8. dtype, attention implementation, device map 및 KV-cache 조건
9. 공식/검증 가능한 quantization과 8 GB GPU 실행 방식
10. Ollama/llama.cpp 지원 여부; custom architecture이면 변환 성공을 추정하지 않음
11. 모델/토크나이저/template/config/quant artifact의 digest와 provenance
12. 라이선스·Notice·표시 의무와 공개 방송 사용 경계

확인되지 않은 항목은 `unknown`으로 남기며 다른 모델의 관례로 채우지 않는다.
mutable `main`과 tag-only provenance는 금지한다. Motif의
`trust_remote_code=True`는 고정 revision의 코드 감사를 통과한 뒤 격리 환경에서만
허용한다.

## 공식 사용법 기준표

아래는 계획 작성 시점의 공식 model card/config에서 확인된 출발점이다. 실제
실행에서는 반드시 pinned revision의 파일을 다시 읽어 값과 hash를 고정한다.

| 모델 | 공식 사용법에서 확인된 차이 | AIRI 평가 적용 |
|---|---|---|
| Mi:dm 2.0 Mini | 표준 Transformers `AutoTokenizer`/`AutoModelForCausalLM`과 `apply_chat_template(..., add_generation_prompt=True)`. 별도 thinking/custom-code 요구는 공식 카드에서 확인되지 않음. `generation_config.json`은 sampling on, temperature 0.8, top-k 20, top-p 0.75 | 현재 Ollama Q4 경로를 기준선으로 재측정하고 native lane에서는 pinned generation config도 별도 실행 |
| Motif 2.6B v1.1-LC | model/tokenizer 모두 `trust_remote_code=True`; 공식 예제는 eager attention이며 FlashAttention 2도 언급. config는 16K/BF16 custom architecture | remote Python을 먼저 감사. mutable main 실행 금지. 안전한 quant/engine 경로가 증명되지 않으면 UNRUNNABLE |
| Ministral 3 3B Instruct 2512 BF16 | 공식 target은 language model 약 3.4B와 vision encoder 약 0.4B를 포함하고 current Transformers 지원을 요구. 별도 reasoning family와 혼동 금지. 공식 문서는 BF16 16GB, quantized는 8GB 미만 가능성을 명시 | text-only chat template/system prompt를 pinned target에서 확인. FP8 sibling의 loader·옵션을 BF16 target에 그대로 복사하지 않음 |
| Qwen3 4B | Transformers 4.51 이상. `enable_thinking=True/False`를 chat template에서 제어하며 기본은 thinking. reasoning parser가 backend별로 다름 | 실시간 AIRI lane은 공식 `enable_thinking=False`; thinking lane은 별도 품질 row. thinking text를 대화 history에 재삽입하지 않음 |
| Phi-4-mini-instruct | 공식 카드 예제는 model/tokenizer `trust_remote_code=True`; Phi는 Transformers 4.49 통합도 명시. system/user/assistant 경계와 `<|end|>`를 사용하는 공식 template. 공식 예제 중 temperature 0.0/max tokens 500 | pinned revision에서 integrated path와 remote-code path 중 정확한 지원 경로를 선택·기록. BF16 약 7.69GB는 runtime/KV 여유가 없어 8GB에서 quantized path 필요 |
| Granite 3.3 2B Instruct | 표준 Transformers chat template. `thinking=True/False`가 있고 thinking 출력은 구조화 태그를 사용. 공식 예제는 BF16 CUDA, seed 42, max-new-tokens 8192 | 실시간 AIRI lane은 `thinking=False`; thinking lane 별도. `num_ctx=2048`와 bounded output을 명시해 128K native context를 곧바로 할당하지 않음 |

공식 출처:

- <https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct>
- <https://huggingface.co/Motif-Technologies/Motif-2.6b-v1.1-LC>
- <https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-BF16>
- <https://huggingface.co/Qwen/Qwen3-4B>
- <https://huggingface.co/microsoft/Phi-4-mini-instruct>
- <https://huggingface.co/ibm-granite/granite-3.3-2b-instruct>

revision은 benchmark 시작 시 official Hugging Face model-info가 반환한 full commit
SHA로 고정하고, `snapshot_download(..., revision=<full SHA>)`와 동일 provenance를
사용한다. 웹 화면에 보이는 짧은 commit이나 moving `main`은 pin으로 쓰지 않는다.

## 두 개의 평가 프로파일

### A. 공식-native 프로파일

각 모델의 공식 chat template와 권장 추론 옵션을 그대로 사용한다. 모델 고유의
thinking mode가 있다면 실시간 방송에 적합한 공식 non-thinking 경로와 품질 확인용
thinking 경로를 혼동하지 않고 별도 row로 기록한다. 이 프로파일은 “그 모델을
제대로 사용했을 때”의 품질을 확인한다.

### B. AIRI-common 프로파일

의미상 동일한 AIRI system prompt와 fixture를 사용하되 직렬화는 각 모델의 공식
chat template로 한다. raw deterministic 비교는 기존 Mi:dm 계약과 같은
`num_ctx=2048`, temperature 0, seed 42, case당 3회다. proxy 비교는 현재 production
sampling(`temperature=0.45`, `top_p=0.9`, `repeat_penalty=1.05`)과 동일하게 한다.
모델이 지원하지 않는 옵션을 조용히 무시하거나 다른 의미로 매핑하지 말고 manifest와
report에 `unsupported`를 기록한다.

두 프로파일 결과를 섞어 하나의 숫자로 만들지 않는다. tokenizer별 prompt token
수도 언어 길이처럼 직접 비교하지 않는다.

## candidate × profile × stage 실행표

| 단계 | 공식-native profile | AIRI-common profile |
|---|---|---|
| P0 provenance/security | artifact당 1회, 두 profile이 공유 | artifact당 1회, 두 profile이 공유 |
| P1 8 GB 적합성 | native backend/권장 dtype 또는 공식 quant 경로 | AIRI에서 실제 채택 가능한 quant/engine 경로 |
| P2 raw 16-case×3 | 공식 template·공식 권장 sampling | 공식 template·temperature 0·seed 42·`num_ctx=2048` |
| P3 context 4압력×3 | raw native context gate | raw common + production-context gate |
| P4 persona 20-case | direct native generation | direct common deterministic generation |
| P5 proxy 120-turn | 실행하지 않음. proxy는 production profile이므로 native로 오표기 금지 | 현재 production sampling과 AIRI SSoT 후보 override로 실행 |
| P6 한국어 인간 검수 | native 응답 20턴/model | AIRI proxy 응답 20턴/model |
| P7 Electron/TTS n=10 | 실행하지 않음. full-stack은 AIRI production profile | 비유해 고정 subset으로 전 후보 실행 |

Qwen3·Granite의 공식 non-thinking을 native foreground 기본 row로 사용한다.
thinking mode는 모델당 별도의 보조 품질 row이며 P5/P7 latency 결과와 합치지 않는다.
Motif·Phi의 remote-code loader와 integrated/converted AIRI engine도 서로 다른
artifact/profile로 기록한다. 따라서 “official-native도 P5/P7을 실행했다”거나
“AIRI-common 결과가 모델 공식 권장 설정이다”라고 주장하지 않는다.

## 전 후보 공통 실행 단계

1. **P0 provenance/license/security:** exact revision, usage manifest, remote-code
   감사, artifact hash를 고정한다.
2. **P1 8 GB 적합성:** 후보 하나만 로드해 정적 weight·KV와 실제 VRAM을 측정한다.
   RTX 3060 Ti 8 GB에 맞지 않거나 안전한 4-bit 경로가 없으면 `UNRUNNABLE`로
   기록하고 억지 변환하지 않는다.
3. **P2 raw 16-case:** 위 profile matrix에 따라 16 case × 3회. common은
   `run_airi_baseline.py` 계약을 사용한다. gate, TTFT,
   completion, tok/s, 출력 길이와 실패 유형을 기록한다.
4. **P3 문맥:** native는 raw context, common은 raw context와 production-context를
   각각 0/8/20/48 × 3으로 실행해 active card, continuity, memory, dialogue
   binding을 측정한다.
5. **P4 persona/safety:** 두 profile에서 20-case ko/en/ja/zh corpus를 실행한다.
   marker contract와
   의미 안전/정답 품질을 동일시하지 않고, 원응답 인간 검토를 별도 보존한다.
6. **P5 AIRI proxy:** public synthetic 6 case × 10회 × A→B/B→A 순서로
   모델당 120 turn을 측정한다. test-origin으로 memory/journal을 변경하지 않는다.
7. **P6 한국어 방송 대화:** native와 common 각각에서 인사, 일상 잡담, 채팅
   답변, 후원 감사, 모호한 질문,
   컨셉 침범, 욕설·성적·괴롭힘 입력을 포함한 동일 시나리오를 모델당 최소 20턴
   생성하고 익명·교차 순서로 사람이 자연스러움/캐릭터성/충실성/안전을 평가한다.
8. **P7 full-stack 후보 실기:** P0~P6에서 실행 가능성이 확인된 모든 후보를
   한 번에 하나씩 exact digest로 고정해 설치 ASAR 변경 없이 local proxy→현재
   Electron→GPT-SoVITS→Windows render를 모델당 n=10 교차 블록으로 측정한다.
   이 단계의 음성 출력은 고정된 비유해 한국어 대화 subset만 사용하고, jailbreak·
   욕설·성적 case의 raw 모델 출력은 TTS하지 않는다. 출력 믹스 진입과 사람이
   들은 품질을 구분한다. 종료 후 Mi:dm 기본값과 서비스 상태를 복원한다.

P0/P1에서 멈춘 모델도 후보 누락이 아니라 명시적 `BLOCKED` 또는 `UNRUNNABLE`
결과다. 나머지 후보는 한 모델의 실패 때문에 중단하지 않고 끝까지 같은 단계를
수행한다.

## 판정과 산출물

- 모델별 report에는 exact source/tag/digest, engine, template/config hash,
  usage profile, prompt 옵션, runtime version, VRAM, latency, gate 결과와 실패 원인을
  포함한다.
- 최종 표는 Mi:dm 대비 품질·캐릭터·문맥·안전·지연·VRAM을 축별로 보여 준다.
  개발사 benchmark와 AIRI 실측은 별도 열이다.
- 자동 gate 하나만으로 우승자를 정하지 않는다. 최소 P6 인간 검수와 P7 full-stack
  근거가 있어야 운영 승격을 제안한다.
- 승격 전 `midm-airi`를 덮어쓰지 않고 별도 tag/digest를 사용한다. 운영 SSoT 변경은
  최종 보고와 사용자 재승인 후 별도 배치다.
- 모델 weight, 개인 대화, raw audio, credentials와 runtime DB는 커밋하지 않는다.
  공개 합성 fixture, content-free report, provenance와 요약 문서만 추적한다.

## 실행 갱신 — 2026-08-14

- [x] P0 exact revision, license/NOTICE, artifact hash, remote-code 정적 감사
- [x] P1 common 5개 및 native Mi:dm/Granite 8 GB bounded fit 실측
- [x] P2 common 5개×16×3, native 2개×16×3
- [x] P3 common raw+production, native Mi:dm/Granite 0/8/20/48×3
- [x] P4 common 5개, native 2개 20-case
- [x] P5 common 5개 120-turn
- [x] P6 common 5개×20턴, native 2개×20턴, 익명 packet 생성
- [x] P7 common 5개 Electron→GPT-SoVITS→Windows render n=10
- [x] Qwen/Granite thinking 보조 row 분리
- [x] 모호성·근거·불확실성·무조건 동의를 다루는 12-scene 방송 지능 리허설
- [~] 인간 검수: packet/key는 생성 완료, rubric 입력은 검토 PC 대기
- [x] Motif: P0 정적 감사 뒤 license file 부재·remote code·8 GB quant 부재로
  P1–P7 `UNRUNNABLE`; 다른 후보 평가는 계속 완료

상세 수치와 잠정 운영 결정은
`airi_docs/진행중/AIRI-LOCAL-LLM-CANDIDATE-AB-RESULT-2026-08-14.md`를 본다.
