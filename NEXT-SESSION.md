# AIRI 다음 세션 안내

현재 진입점은 `airi_docs/진행중/AIRI-NEXT-SESSION-HANDOFF-2026-08-13.md`,
`airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`,
`airi_docs/진행중/AIRI-REVIEW-PC-HANDOFF-2026-08-13.md`다. 과거
2026-08-07의 EXAONE/STT-on 절차는 사용하지 않는다.

## 운영 기본값

- Chat model: Mi:dm (`midm-airi:2.0-mini`) digest pin 유지
- `num_ctx=2048`
- 방송 기본 프로파일: chat/text 입력, STT/마이크 OFF
- 기억 추출 OFF (통과한 extractor가 없음)
- output moderation 기본 OFF

STT와 실제 마이크(AEC, barge-in, 20+20)는 사용자가 명시적으로 “마이크 테스트 시작”을 요청할 때만 `-Stt on`으로 재개한다. 현행 일본어 참조 음성은 유지하며, T-05 한국어 후보 126번은 예비 후보다. 정식 팬덤명은 유보하고 “시청자들”을 쓴다.

## 현재 작업 상태

최우선 신규 배치는 명확한 허용 라이선스 후보와 사용자 승인 평가 예외 Motif를
포함한 Mi:dm, Motif 2.6B v1.1-LC, Ministral 3 3B, Qwen3 4B,
Phi-4-mini 3.8B, Granite 3.3 2B의 동일 AIRI A/B다.
모델마다 공식 chat template·system role·thinking·sampling·EOS·context·
quantization이 다르므로 exact revision의 사용법 manifest를 먼저 만들고,
공식-native profile과 AIRI-common profile을 모두 측정한다. Motif의 원격 Python을
실행하는 `trust_remote_code=True`를 mutable `main`에 사용하지 않는다. 운영 모델
교체는 아니며 Mi:dm을 기준선으로 유지한다. EXAONE은 NC 라이선스 때문에
공개·수익 방송 승격 후보에서 제외한다. 상세 SSoT는
`airi_docs/진행예정/AIRI-LOCAL-LLM-CANDIDATE-AB-PLAN-2026-08-13.md`다.

production-context v2 gate는 구현·측정을 완료했지만 **FAIL**이다. 7개 필드 중 6개는 12/12이고 두 continuity color는 v1보다 개선됐으나, `dialogue_marker`가 0/12로 memory marker `silver-fern`을 결정적으로 복사한다. 따라서 prompt tuning을 계속하거나 품질 PASS라고 주장하지 않는다. 기본 2048·추출 OFF·STT OFF를 유지하며, 설치 extraction을 재실행하지 않았다.

로컬 LLM P0–P7 A/B 실측은 2026-08-14 완료했다. foreground 운영 모델은
Mi:dm exact digest를 유지하며, Phi-4 Mini와 Ministral은 인간 검수 challenger다.
Qwen3는 확신도/문맥 자동 규칙 8/12와 production-context 12/12였지만 실제 첫
render P50 약 9.15초, 120-turn 80/120, 빈 응답 때문에 foreground 승격 대상이
아니다. Motif는 pinned license file 부재, remote code, 8 GB safe quant 부재로
UNRUNNABLE이다. 검토 PC는 모델명을 열기 전에 P6와 intelligence의 두 익명 packet을
채우고, 그 뒤 별도 key로 매핑한다. 상세:
`airi_docs/진행중/AIRI-LOCAL-LLM-CANDIDATE-AB-RESULT-2026-08-14.md`.

모든 후보가 모호한 고유명사·현재 정보 불확실성·무조건 동의를 완전히 처리하지
못했으므로 음란/비속어 moderation과 별도의 epistemic-confidence gate가 다음
구현 우선순위다. 외부 검색은 여전히 OFF이며 검색하지 않았는데 검색했다고 말하면
안 된다.

현재 exact tip과 원격 동기화·CI 상태는 `git status`, `git log -1`, PR checks로 확인한다. v2 전체 CI-equivalent Python 3.12.13 matrix는 858 passed / 1 skipped / 708 subtests다. historical test count는 해당 historical base에만 적용한다.

Source-built ASAR deployment safety tooling has synthetic >1 MiB PASS coverage,
and its full validator passed the installed ASAR read-only at SHA-256
`1B68AE...B0`, but the installed AIRI remains unchanged.
[GitHub issue #2](https://github.com/kkp8121-rgb/airi-local-stack/issues/2) is
the authorization and tracking gate for an installed-ASAR operation. Until
then, do not stop or write the installed app and do not claim installation
completion or runtime TTS duration/pitch verification. See
`airi_docs/완료/AIRI-SOURCE-ASAR-DEPLOY-SAFETY-2026-08-13.md`.

## 외부/인간 입력이 필요한 항목

- cloud streaming latency 재측정: 제공자 자격증명과 외부 사용 승인
- 인간 검수 100건
- STT/실제 마이크 재개: 사용자 명시 요청
- 제한 라이선스 모델 재도입: 사용자가 후보군에 다시 넣을 때만 별도 법률 검토
