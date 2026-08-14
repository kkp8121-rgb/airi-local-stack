# AIRI 검토 PC 인수인계 — 2026-08-13

## 검토 대상

- 저장소: `kkp8121-rgb/airi-local-stack`
- 브랜치: `chore/dev-pc-live-gates-2026-08-13`
- 기준 main: `c916f485565d29396e1580f16a4d72236bb724f5`
- 검토 범위: `origin/main..origin/chore/dev-pc-live-gates-2026-08-13`
- 이 문서 커밋으로 tip은 전진하므로 고정값 대신 `git log -1`로 확인한다.

브랜치는 main의 직계 후손이며 rebase가 필요하지 않다. 패치 디렉터리는 변경하지
않았다. 검토 PC는 먼저 `git fetch --prune origin` 후 위 범위를 검토한다.

## 이번 브랜치에서 완료한 것

1. 설치 Electron의 Mi:dm SSoT를 실기로 재검증했다. digest pin, 단일 runner,
   EXAONE rollback, evaluator provenance, digest 불일치 fail-closed, STT/Electron
   microphone OFF를 확인했다.
2. YouTube `streamList` 쿼터 측정을 위한 transport-neutral·content-free 오프라인
   코어를 구현했다. 실제 OAuth/gRPC/live polling/AIRI 전달은 포함하지 않는다.
3. 신규 공개 라이선스 추출 후보 3종을 11436 CPU 단일 fixture로 선별했다.
   Ministral 3 3B, Phi-4-mini 3.8B, Granite 3.3 2B 모두 FAIL하여 full gate는
   실행하지 않았고 extraction은 OFF다. 결과 JSON은 추적한다.
4. 실패 모델과 재생성 가능한 임시 산출물을 정리해 C: 여유 공간을 약
   12.41 GiB에서 58.99 GiB로 늘렸다. source, patches, evidence, runtime DB/log,
   설치 AIRI 및 운영 서비스는 보존했다.

## 로드맵 판정

실제 송출·비공개 리허설만 제외해도 전체 완료가 아니다. 남은 비송출 작업은
다음과 같다.

- 통과 extraction 후보의 full balanced gate와 extraction ON 후 MEM-04 활성
  Stage-B commit↔foreground 락 경합 실측
- 캐릭터 evaluator 재활성, 인간 검수 100건, 헌법 최종 승인
- 장문 dialogue 품질 FAIL 해소, 스타일 승격 및 G4/C1~C5 커스터마이징
- I2 시청자 기억의 launcher/proxy/AIRI runtime 연결
- B1b live adapter/AIRI ingress, B4 director의 AIRI/TTS/moderation/kill-switch 연결
- TTS resampler ASAR 설치 후 duration/pitch/text→render 검증
- cloud live TTFT, OBS B2, 실제 마이크/AEC/barge-in 및 I3 운영 승인

retrieval/store executor lifecycle과 ASAR preflight 결정론화는 검토 PC 커밋
`22a6add` 및 main `c916f48`로 완료됐다. 다만 SQLite native store 호출은 협력
취소 지점이 없어 shutdown drain이 순수 대기이고, 장기 `SQLITE_BUSY`에서는
deadline 뒤 tracked worker가 남을 수 있다는 알려진 한계를 유지한다.

## 실제 설치 AIRI 시험의 정확한 범위

현재 설치 `app.asar`는 1,356,257,019 B,
SHA-256 `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`이며
7개 AIRI 프로세스가 실행 중인 상태를 2026-08-13 재확인했다.

| 행동 | 증거 수준 | 결론 |
|---|---|---|
| text→LLM→GPT-SoVITS→Windows render | 현재 설치본 실제 20턴 | Mi:dm render P50/P95 1,501.5/2,597.2 ms. 출력 믹스 진입 증거이며 사람이 들은 음향 품질 증명은 아님 |
| 대화 자연스러움 | 과거 설치 경로 3장면 인간 판정 | 3/3 스타일 FAIL. 현재 ASAR 자연스러움 합격 증거 없음 |
| 자연스러운 대화 간격 | 미검증 | 발화 종료→다음 반응, drain/lip-sync 간격 acceptance 없음 |
| 채팅·도네이션·director | 오프라인 합성 event/state-machine 시험 | 실제 YouTube 채팅·실제 후원·AIRI/TTS runtime 연결 없음 |
| 탈옥·컨셉 침범 | direct-model의 제한된 hostile-card fixture | 현재 설치 Electron 대상 종합 red-team 없음 |
| 욕설·음란성 반응 | dictionary/unit 및 generic match-all 배선 실기 | category별 실제 UI/TTS 반응 없음; current moderation OFF |

B1/B4는 default OFF이며 live adapter가 없다. malicious metadata·BIDI·잘못된 ID는
강하게 거부하지만, 자연어 prompt injection·욕설·성적 발언·일반 괴롭힘을 판별하는
입력 screener 구현은 없다. output moderation은 생성 후 문장 교체이며 현재 OFF다.
따라서 이 브랜치를 실제 방송 안전 완료로 승인하면 안 된다.

## 검토 우선순위

1. `c916f48..HEAD`의 변경 범위와 roadmap/evidence 정합성을 확인한다.
2. streamList 코어가 network/OAuth/raw content를 보존하지 않고 bounded
   cancellation·cleanup·manual quota snapshot 계약을 지키는지 검토한다.
3. 신규 extraction smoke가 단일 fixture fail-fast FAIL임을 유지하고 운영
   report로 승격되지 않았는지 확인한다.
4. 설치본 실기와 offline simulation의 주장이 섞이지 않았는지 확인한다.
5. 다음 구현 제안 시 input semantic screener, persona-jailbreak corpus,
   category별 installed UI/TTS 시험을 별도 gate로 정의한다.

## 검증 및 CI 상태

## B3-c/B3-d current handoff (2026-08-13)

B3-c is a default-OFF deterministic local input prefilter plus local B1
downstream spine, independently reviewed PASS. It blocks
`persona_takeover`/`profanity`/`sexual_explicit`/`targeted_harassment`/`privacy`
before upstream, including historical unsafe user entries; has bounded
normalization/obfuscation and PII patterns, protocol variants, proactive
exemption, exact loopback, and fail-closed launch health/policy digest. The
model sees `[YouTube] ${text}` only; public `displayName` is separate viewer
observation. No YouTube/OAuth/provider adapter is implemented. It is not
multilingual semantic screening: ja/zh and unvalidated Latin fail closed as
`unsupported_language`, Korean permits only 14 exact benign product/acronym
tokens, and novel euphemisms/other languages remain human/model-gate work.
Output moderation remains OFF.

Focused B3-c evidence: Python input+launcher+eval 43 passed (later input-only
19), chat-ingress 47, sender 32, combined Node latest 79. The final local
Actions substitute is Python 3.12 full suite 911 passed/1 skipped/863 subtests/
7 warnings in 53.13 s plus checkpoint/manifest/source-ASAR contracts PASS;
launcher parsers and diff checks PASS. The fresh loopback probe
`airi_docs/evidence/AIRI-B3C-INPUT-SCREENING-LIVE-PROBE-2026-08-13.json` records
unchanged installed ASAR 1,356,257,019 B SHA `1b68ae...b88b0`, seven AIRI
processes, source screening ON/ready policy SHA `67739c...b9d7a`, five category
blocks and benign Korean allow repeated twice (12/2/10), with output moderation
OFF, extraction OFF, and STT listener absent. It proves loopback policy only.
The fresh installed UI/TTS recheck did not reach model/TTS after cleanup removed
sender SDK `@moeru/std`; ASAR was untouched. Do not treat earlier TTS evidence
as current-policy proof; B3-e is pending installed badge + TTS rehearsal.

B3-d's content-free direct local Ollama 20-case exact ko/en/ja/zh marker corpus
is recorded in `ollama-proxy/eval/results/airi-persona-jailbreak-marker-midm-2026-08-13.json`
(14,395 B; SHA-256 `9308b0c1527eaf42b58496bd3c36520feabeaa38c70623139981357cb65509c8`;
Mi:dm `92a9...485f`). Structural 20/20 PASS, standalone marker 5/20 PASS, so
overall FAIL; P50/P95/max 211.371/809.552/928.064 ms. It makes no semantic
safety, proxy, Electron, UI, or TTS claim. Installed red-team remains pending.

- 로컬 `test-current-checkpoint.ps1`: PASS
- streamList focused: 20/20 PASS
- all chat-ingress: 47/47 PASS
- push Actions run `31683115216`: 13 jobs 모두 failure지만 `runner_id=0`,
  steps 0, 로그 없음. 코드 실행 전 runner 할당 단계 실패이며 기존 계정
  payment/spending 제한과 같은 형태다. green으로 오인하지 말고, 코드 failure로도
  오인하지 않는다.

## 핵심 문서

- `airi_docs/진행중/AIRI-DEV-PC-HANDOFF-2026-08-12.md` — memory review 지시는
  superseded 이력으로 표시됐으며 나머지 dev-PC 운영 상태를 참조한다.
- `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`
- `airi_docs/완료/AIRI-DEV-PC-SSOT-REVERIFICATION-2026-08-13.md`
- `airi_docs/완료/AIRI-B0-1-STREAMLIST-QUOTA-MEASUREMENT-CORE-2026-08-13.md`
- `airi_docs/완료/AIRI-NEW-LOCAL-EXTRACTION-CANDIDATE-SMOKES-2026-08-13.md`
- `airi_docs/완료/AIRI-LOCAL-TEMP-AND-FAILED-MODEL-CLEANUP-2026-08-13.md`
- `airi_docs/완료/AIRI-MEMORY-RETRIEVAL-SHUTDOWN-DRAIN-2026-08-13.md`

검토 결과는 PASS/REQUEST CHANGES와 함께 blocker, exact file/line, 재현 명령,
실제 완료 범위를 남긴다. 외부 호출, 실제 채팅·후원, ASAR 설치, 마이크 테스트는
별도 사용자 승인 없이 실행하지 않는다.

## 로컬 LLM A/B 검토 추가 — 2026-08-14

개발 PC가 여섯 후보 P0과 실행 가능한 다섯 후보 P1–P7을 완료했다. 결과 SSoT는
`AIRI-LOCAL-LLM-CANDIDATE-AB-RESULT-2026-08-14.md`다. 운영 기본값은 Mi:dm을
유지한다. 모델 승격 commit이나 installed ASAR 교체는 하지 않았다.

검토 PC 순서:

1. `ollama-proxy/eval/results/local-llm-ab-p6-human-review-packet-2026-08-14.json`
   의 rubric을 모델명 없이 채운다.
2. `ollama-proxy/eval/results/local-llm-ab-intelligence-human-review-packet-2026-08-14.json`
   의 도움됨/확신도/근거/간결성 rubric을 모델명 없이 채운다.
3. 두 packet을 저장한 뒤에만 각각의 `review-key`를 열어 sample을 모델에 매핑한다.
4. 자동 gate 하나로 winner를 정하지 말고 P2 구조, P3 문맥, P5 120-turn, P7
   render tail, native/common 경계를 함께 본다.
5. 인간 점수가 Mi:dm 대비 명확한 차이를 보이지 않으면 Mi:dm을 유지한다.

특별 검토 항목은 문맥 없는 `정범`, history의 `정범=방송 고양이`, 무조건 동의,
확인할 수 없는 현재 patch/server 질문이다. 이 항목은 음란·비속어 moderation이
아니라 epistemic-confidence gate 요구다. 외부 검색은 이 배치에서 실행하지 않았다.

Motif는 누락이 아니다. pinned custom Python은 실행하지 않고 정적 감사했으며,
pinned repository의 license file 부재와 8 GB safe quant 부재로 P1–P7
UNRUNNABLE이다. `local-llm-ab-motif-unavailable-2026-08-14.json`을 확인한다.

`ollama-proxy/eval/results/`는 의도적으로 gitignored다. 검토 PC에는 결과 디렉터리를
별도 전송하고 result SSoT의 packet/key bytes와 SHA-256을 대조한다. generated
output을 `git add -f`로 commit하지 않는다.
