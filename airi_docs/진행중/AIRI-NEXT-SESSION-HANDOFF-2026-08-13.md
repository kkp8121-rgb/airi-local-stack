# AIRI 다음 세션 인수인계 — 2026-08-13

## 1. 시작점

- 작업 저장소: 이 문서를 포함하는 저장소의 root
- 작업 브랜치: `chore/dev-pc-live-gates-2026-08-13`
- 작성 직전 HEAD: `6ef04a05e4c82133a7e83c679428c28024926cf3`
  (`feat: add local input safety gates`)
- 작성 직전에는 위 브랜치와 origin이 일치했다. 최초 배치에서는 push를 보류했고,
  2026-08-14 후속 요청에서 결과·대화 문서의 commit과 push를 승인받았다.
- 시작 즉시 `git status --short --branch`, `git log -3 --oneline --decorate`,
  `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`로 실제 상태를
  다시 확인한다. 기존 변경을 reset/revert하지 않는다.

현재 운영 기준은 Mi:dm `midm-airi:2.0-mini`, `num_ctx=2048`, STT/마이크 OFF,
기억 추출 OFF, output moderation OFF다. 설치 ASAR 교체·외부 API·실제 마이크는
별도 사용자 승인 없이는 실행하지 않는다.

## 2. 직전 안전 게이트 상태

- B3-c 로컬 입력 screener와 B1 local downstream spine은 기본 OFF로 구현됐고
  독립 검토 PASS다. 입력은 모델·기억·상태에 들어가기 전에 차단되며, 일본어·
  중국어 및 검증되지 않은 라틴 표현은 현재 fail-closed다. 다국어 의미 안전을
  완성했다는 뜻은 아니다.
- B3-d의 direct local Ollama 20-case ko/en/ja/zh marker corpus는 구조 20/20
  PASS지만 standalone marker 5/20 PASS로 전체 FAIL이다. 이 수치는 정답 품질이나
  의미 안전 점수가 아니라 exact marker 계약 점수다.
- B3-e category별 설치 UI badge·TTS fallback 실기는 아직 완료되지 않았다.
- 실제 YouTube/OAuth 채팅, 실제 후원, 방송 director runtime 연결, 실제 송출,
  자연스러운 대화 간격과 종합 jailbreak rehearsal은 모두 미완료다.
- 최신 정확한 근거는 `진행중/AIRI-REVIEW-PC-HANDOFF-2026-08-13.md`,
  `완료/AIRI-B3C-INPUT-SCREENING-AND-LOCAL-CHAT-SPINE-2026-08-13.md`,
  `완료/AIRI-B3D-PERSONA-JAILBREAK-MARKER-CORPUS-2026-08-13.md`를 사용한다.

## 3. 사용자 결정 — LLM 후보와 라이선스

### 3.1 후보 정책

- Mi:dm 2.0 Mini는 MIT이며 현재 운영 기준선으로 유지한다.
- EXAONE은 NC 라이선스 때문에 공개·수익 방송의 신규 승격 후보에서 제외한다.
  기존 태그·과거 A/B 자료는 이력/호환 확인용으로만 보존하고 공개 방송 모델로
  선택하지 않는다. 임의 삭제나 launcher rollback 재설계는 별도 작업이다.
- Apache-2.0/MIT가 명확한 비교 후보는 Ministral 3 3B, Qwen3 4B,
  Phi-4-mini 3.8B, Granite 3.3 2B다. 기존 extraction smoke 실패는 기억 추출
  계약의 실패이며 foreground chat 후보를 자동 탈락시키는 증거가 아니다.
- Kanana, HyperCLOVA X SEED, Gemma, LFM 계열 등 별도·제한적 라이선스 후보는
  공개 방송 승격 후보에서 보수적으로 제외한다.

### 3.2 Motif 결정

사용자는 `Motif-Technologies/Motif-2.6b-v1.1-LC`를 라이선스 불명확성 때문에
제외하지 말고 **정식 실측 평가 후보로 승격**하도록 결정했다. 이는 즉시 Mi:dm을
교체하거나 공개 방송 사용이 승인됐다는 뜻이 아니다.

확인된 라이선스 상태는 다음과 같다.

- v1.1-LC 모델 카드 메타데이터는 `license: mit`라고 표시하면서 동시에
  `license_name: motif-license`, `license_link: LICENSE`를 선언한다.
- v1.1-LC 저장소의 현재 파일 트리에는 LICENSE가 없고, 커밋 이력에는 Motif
  License Agreement를 추가했다가 삭제한 기록이 있다.
- 기반 모델 `Motif-2.6B`의 현재 LICENSE는 별도 Motif License Agreement다.
  상업 사용 자체를 금지하지 않지만, 제품/서비스 공개 시 라이선스 사본,
  Notice, 눈에 띄는 `Built with Motif` 표시, AUP 준수와 7억 MAU 예외를 둔다.
- 따라서 이것을 단순한 MIT 법률 확정으로 문서화하지 않는다. 사용자가 이
  회색영역을 인지하고 평가 후보 승격을 승인했으며, 권리자 이의 제기나 적용
  조건 불일치가 확인되면 사용을 중단하고 재평가한다. 이는 법률 면책 주장이 아니다.

공식 확인 링크:

- <https://huggingface.co/Motif-Technologies/Motif-2.6b-v1.1-LC>
- <https://huggingface.co/Motif-Technologies/Motif-2.6B/blob/main/LICENSE>
- <https://huggingface.co/Motif-Technologies/Motif-2.6b-v1.1-LC/commit/56a7745193185621e5f23ea62e8ddb98d8ca5970>

Motif가 실제 방송 모델로 채택될 때는 채널 소개와 해당 방송 설명란에 최소 다음
문구를 표시한다.

> AIRI는 Motif-2.6B v1.1-LC를 사용합니다. Built with Motif.

모델 또는 모델 포함 배포물을 재배포하면 적용 라이선스 원문과 Notice도 함께
제공한다. 평가 단계의 로컬 비공개 실행과 공개 배포/서비스 표시 의무를 혼동하지
않는다.

## 4. 전 후보 모델별 사용법·보안 게이트

다음 세션의 최우선 작업은 Motif 한 모델만 보는 것이 아니라, 명확한 허용
라이선스 후보와 사용자 승인 평가 전용 조건부 Motif 예외를 포함한 **모든 후보**를
Mi:dm과 동일한 AIRI 평가 경로에서 비교하는 것이다. 상세 계약은
`진행예정/AIRI-LOCAL-LLM-CANDIDATE-AB-PLAN-2026-08-13.md`가 SSoT다.

모델마다 공식 사용법이 다르므로 공통 tokenizer/template를 강제하지 않는다.
각 모델의 공식 chat template, system-role 처리, thinking on/off, stop/EOS,
sampling 권장값, context, dtype/attention, quantization과 engine 지원을 exact
revision으로 먼저 고정한다. 공식-native profile과 AIRI-common profile을 모두
실행하고 결과를 섞지 않는다.

특히 Motif 모델 카드 예제의 `trust_remote_code=True`는 Hugging Face 저장소의
Python 구현을 로컬 프로세스에서 실행한다는 뜻이다. mutable `main`을 그대로
신뢰해 실행하지 않는다.

1. 정확한 commit revision을 고정하고 `modeling_motif.py`,
   `configuration_motif.py`, tokenizer/config 및 import 경계를 먼저 읽기 전용으로
   검토한다.
2. 다운로드 파일 목록·크기·SHA-256과 라이선스/README 메타데이터를 evidence로
   남긴다. 인증정보·개인 경로·모델 weight 자체는 커밋하지 않는다.
3. 고정 revision을 명시해 로드하며, 격리된 로컬 환경에서만 실행한다. 외부
   telemetry·remote inference·임의 shell/network 동작이 없는지 확인한다.
4. 원본 저장소는 약 10.4 GB F32이므로 RTX 3060 Ti 8 GB에 `.cuda()`로 그대로
   올리는 절차를 사용하지 않는다. 4-bit 경로의 정확성·지원 여부와 CPU/GPU
   offload를 먼저 검증한다.
5. Ollama/llama.cpp가 Motif custom architecture를 지원한다고 추정하지 않는다.
   변환 가능성은 별도 prove-or-stop 게이트로 판단하며 기존 `midm-airi` 태그를
   덮어쓰지 않는다.

## 5. 다음 세션의 실행 순서

1. 이 문서와 roadmap, review-PC handoff를 읽고 현재 diff·서비스·디스크 상태를
   확인한다. 직전 B3-c/d 작업을 재조사하거나 되돌리지 않는다.
2. Mi:dm, Motif 2.6B v1.1-LC, Ministral 3 3B, Qwen3 4B,
   Phi-4-mini 3.8B, Granite 3.3 2B 각각의 공식 사용법 manifest를 먼저 완성한다.
   chat template·thinking·sampling·EOS·context·quantization을 다른 모델에서
   복사하지 않는다.
3. 각 후보의 exact revision, 라이선스, remote-code/import 표면, 8 GB 실행
   경로를 다운로드·실행 전에 고정한다. P0/P1 불합격은 명시적 BLOCKED/
   UNRUNNABLE로 남기되 다른 후보 평가는 계속한다.
4. 모든 실행 가능한 후보에 공식-native와 AIRI-common 두 프로파일을 적용한다.
   native는 raw 16-case×3, raw context 4압력×3, persona 20-case, 한국어
   응답 인간 검수를 수행한다. common은 같은 direct gate에 더해 production-
   context, proxy 120-turn, AIRI proxy 인간 검수와 full-stack n=10까지 수행한다.
   thinking 보조 row는 proxy/full-stack 지연과 섞지 않는다.
5. 설치 ASAR를 바꾸지 않고 후보를 한 번에 하나만 exact digest로 로드하며,
   모델별 종료 후 서비스/VRAM을 정리하고 최종적으로 Mi:dm 기본값을 복원한다.
   실제 공개 방송, 외부 API, 마이크 시험은 별도 승인 대상이다.
6. 어떤 FAIL도 숨기지 않고 실기·direct model·합성/unit 증거 층위를 구분해
   roadmap과 완료/진행중 문서를 갱신한다.

## 6. 금지 및 보존 규칙

- `airi_docs/patches/` 이동·수정 금지.
- 캐릭터 확정값 AIRI·“사장님”·아이리스·확정 인사/클로징 임의 변경 금지.
- 현행 일본어 참조 음성과 T-05 126 예비 후보 결정을 변경하지 않는다.
- 실제 채팅·후원·외부 API·ASAR 설치·마이크는 별도 승인 전 실행하지 않는다.
- 새 테스트 파일은 CI matrix/checkpoint에 등록한다.
- 커밋 배치마다 `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`와 갱신 로그를
  업데이트하고 trailing whitespace를 금지한다.
- 사용자가 현재 요청에서 push를 지시하지 않았으므로 임의 push하지 않는다.

## 7. 실행 완료 인수 — 2026-08-14

위 §5의 P0–P7 실행은 완료됐다. 최신 결과 SSoT는
`AIRI-LOCAL-LLM-CANDIDATE-AB-RESULT-2026-08-14.md`다. 운영 foreground는
Mi:dm exact digest를 유지하고, Phi-4 Mini와 Ministral을 익명 인간 검수
challenger로 넘긴다. Qwen3는 문맥/확신도 자동 항목에서 가장 높았지만 실제 방송
지연과 빈 응답 때문에 foreground 승격하지 않는다. Motif는 P0 정적 감사 뒤
P1–P7 UNRUNNABLE이다.

검토 PC는 P6 20-turn packet과 intelligence 12-scene packet을 먼저 blind review한
뒤 별도 key를 연다. 사람 점수는 아직 공란이다. 후속 구현 우선순위는 음란·비속어
moderation과 분리된 epistemic-confidence gate다. 외부 검색은 OFF이며, 모호한
고유명사는 확인하고 확인 불가능한 현재 정보는 보류해야 한다.
