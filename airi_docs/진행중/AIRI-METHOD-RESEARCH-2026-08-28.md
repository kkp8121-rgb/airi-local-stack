# 대안 기법 리서치 — 소형 모델 인캐릭터 대사 생성 (2026-08-28)

> 사용자 Goal("few-shot 같은 다른 방법을 GitHub·HuggingFace·논문에서 광범위 서칭")의 결과.
> 웹 리서치 subagent 2축(학술 논문 / GitHub·HF 실전)을 병렬 수행해 종합했다. 링크가 근거이며
> 로컬 실측은 아직 없다 — 채택·실행은 별도 사용자 결정. 한계 실증 문서
> `AIRI-VOD-STORYLINE-CEILING-EVIDENCE-2026-08-28.md` §6의 선택지를 이 결과로 구체화한다.

## 0. 두 축이 독립적으로 수렴한 결론 3가지

1. **Ollama가 고급 제어 3종을 전부 막고 있다** — GBNF 문법 강제(ollama/ollama#6237,
   #11911), `logit_bias`(#2415, 미구현), control vector(#8110, PR #8148 미머지). 같은 GGUF를
   `llama-server`(llama.cpp)로 서빙하면 셋 다 네이티브로 열린다. 지금까지의 40회 실험이
   "프롬프트+후처리 검증기"에 갇혀 있던 데에는 서빙 계층 제약도 있었다.
2. **우리가 소진한 best-of-N+자체검증기 트랙은 논문으로도 반증돼 있다** —
   13B 이하 모델은 약한 verifier로 자기 교정 불가(arXiv 2404.17140), intrinsic
   self-correction 실패(2310.01798), 롤플레이는 reward-ambiguous라 verifier 순위 자체가
   신뢰 불가(2508.09074). 트랙 중단 결정과 정합.
3. **문법 완전 강제도 함정이다** — 7~9B에서 grammar 강제 시 정확도 74→33% 급락
   (2605.02363), 포맷 제약이 성능 저하(2408.02442). 검증된 대안은 **CRANE 패턴**(2502.09061,
   Qwen2.5-1.5B에서 실증): 자유 서술 구간은 무제약으로 두고 최종 출력 한 줄만 격리·검증.

## 1. 학술 축 — 적용 가능성 순

| 판정 | 기법 | 핵심 근거 | 2.3B 적용 |
|---|---|---|---|
| 가능 | CRANE식 자유서술+구분자 격리 | arXiv 2502.09061 (1.5B 실증, +10%p) | Ollama 그대로 소프트 구현 가능 — "자유롭게 생각 → 마지막 줄만 대사" |
| 가능 | few-shot은 "지시문+정제 예시 1~2개" | 2402.09954 (페르소나 대화: prompt+demo 결합 최고; demo 단독은 k≥7만 유효), 2303.08119 (많을수록 저하), 2409.15790 (SLM 5-shot 평균 +2.1% — 기대치 낮게) | 미시도·저비용. 단독 해결책 아님, 결합 보조 |
| 시사점 | "롤플레이" 대신 "스토리 캐릭터" 프레이밍 | 2608.07852 (SAE, 4B 포함): 롤플레이 페르소나는 어시스턴트 핵심 위에 누적이라 잔재가 남고, 스토리 캐릭터는 어시스턴트 핵심을 결여 | 프롬프트 재구성으로 즉시 반영 가능 |
| 조건부 | grammar 강제는 종결부 등 최소 지점만 | 2605.02363, 2408.02442 | CRANE과 결합 시만 |
| 조건부 | 파인튜닝 재시도 시 Learnability Gap 교정 | 2502.12143 (Qwen2.5-3B: 큰 teacher의 길고 복잡한 출력은 역효과, 작은 teacher·짧은 예시·Mix Distillation이 유효) — **과거 6라운드 전패의 유력한 사후 설명** | 2026-09-09 이후·별도 승인 |
| 조건부/불가 | persona vector·activation steering | 2507.21509·2601.10387·2605.21006 전부 7B~70B 검증, 소형 미검증 명시. llama.cpp는 지원(PR #5970)·Ollama는 미노출 | 인프라 전환+캘리브레이션 리스크 |
| 불가 | best-of-N 확장·self-refine 강화 | §0-2의 반증 3편 | 트랙 재개 비권장 |

## 2. 실전 축 — GitHub·HuggingFace

- **제약 생성 라이브러리**(outlines 등·guidance 21.7k★·lm-format-enforcer 2.0k★): 전부
  llama-cpp-python/llama-server 레벨 접근 필요 — Ollama HTTP API로는 불가. 그리고 전부
  형식만 강제, "인캐릭터 화법"이라는 의미는 강제 불가.
- **한국어 롤플레이 소형 모델 생태계는 거의 비어 있다.** 최근접:
  `ramyun/adelie-qwen-roleplay-v2-gguf`(Qwen2.5-7B, 한/영, q4_k_m 4.4GB, CPU 구동 명시).
  동급(2.1B) 비교 후보 `kakaocorp/kanana-nano-2.1b`. Mi:dm 베이스의 커뮤니티 RP 튜닝은
  검색 결과 없음. **데이터셋** `huggingface-KREW/korean-role-playing`(GPT-4o 생성 한국어
  페르소나 대화)은 파인튜닝 없이 few-shot 예시 소스로 즉시 사용 가능.
- **커뮤니티 검증 프롬프트 기법**(SillyTavern 23k★·RisuAI 문서): character card +
  `{{char}}`/`{{user}}` 예시 대화 블록, Author's Note **depth injection**(생성 직전 깊이에
  짧은 리마인더 재주입 — depth가 낮을수록 강함), anti-impersonation stop string. 전부
  Ollama 그대로 오늘 시험 가능.
- **logit_bias**: llama-server `/completion`은 `[[token_id, bias]]`·`false`=완전 차단
  지원. 어구("좋을 것 같아")는 활용형별 토큰 열거 필요.
- **control vector**: vgel/repeng(756★)이 GGUF 벡터 내보내기 지원, llama.cpp 네이티브
  적용. 참조 구현이 7B 기준이라 2.3B는 강도·레이어 재캘리브레이션 필요.

## 3. 종합 권고 경로 (실행은 전부 사용자 결정)

| 단계 | 내용 | 비용 | 금지 저촉 |
|---|---|---|---|
| **A. 단기 콤보 1회차** | 평가 러너의 슬롯 cue를 ①스토리 캐릭터 프레이밍(SAE 근거) ②지시문+정제 예시 1~2개(KREW 데이터셋·storyline 어투로 저작) ③CRANE식 "자유 서술→구분자 뒤 최종 대사 한 줄" 구조로 재구성 — 근거 있는 추론 시점 레버 3개를 한 형식 변경으로 결합 | 1회차 ~90분 | 없음 (response-format 단일 원인) |
| **B. llama-server 평가 병행** | 같은 GGUF를 llama-server로 병행 기동(운영 Ollama 경로 불변), 어시스턴트 문형 logit_bias 차단 + 종결부 최소 GBNF — 평가 전용 A/B | 반나절~1일 | 운영 기본값 불변이면 없음 (평가 인프라 추가는 사전 고지) |
| **C. S5 모델 축 판정** | 같은 하네스로 qwen3:8b/4b·adelie-7B(RP 튜닝)·kanana-nano-2.1b(동급) — "모델 천장 vs 과제 설계" 판정 | 회차당 수 시간(CPU) | **S5 해제 필요** |
| **D. 교정 파인튜닝** | Learnability Gap 반영: 작은 teacher·짧은 예시·Mix Distillation, 이번 결함 목록=평가셋 | GPU 필요 | **2026-09-09까지 금지** |

권고(포지, 결정 아님): **A → 실패 시 C(해제 승인 하) → C 결과로 B 또는 D 분기.**
A가 실패해도 "추론 시점에서 근거 있는 방법을 전부 소진했다"는 판정이 완결되고, C가
천장/설계 문제를 가른다. B는 C에서 소형 모델이 근접했을 때 마지막 밀어붙임으로 가장 값지다.
