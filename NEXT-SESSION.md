# AIRI 다음 세션 안내

현재 진입점은 `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`와 `airi_docs/진행중/AIRI-DEV-PC-HANDOFF-2026-08-12.md`다. 과거 2026-08-07의 EXAONE/STT-on 절차는 사용하지 않는다.

## 운영 기본값

- Chat model: Mi:dm (`midm-airi:2.0-mini`) digest pin 유지
- `num_ctx=2048`
- 방송 기본 프로파일: chat/text 입력, STT/마이크 OFF
- 기억 추출 OFF (통과한 extractor가 없음)
- output moderation 기본 OFF

STT와 실제 마이크(AEC, barge-in, 20+20)는 사용자가 명시적으로 “마이크 테스트 시작”을 요청할 때만 `-Stt on`으로 재개한다. 현행 일본어 참조 음성은 유지하며, T-05 한국어 후보 126번은 예비 후보다. 정식 팬덤명은 유보하고 “시청자들”을 쓴다.

## 현재 작업 상태

production-context v2 gate는 구현·측정을 완료했지만 **FAIL**이다. 7개 필드 중 6개는 12/12이고 두 continuity color는 v1보다 개선됐으나, `dialogue_marker`가 0/12로 memory marker `silver-fern`을 결정적으로 복사한다. 따라서 prompt tuning을 계속하거나 품질 PASS라고 주장하지 않는다. 기본 2048·추출 OFF·STT OFF를 유지하며, 설치 extraction을 재실행하지 않았다.

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
- Kanana 공개·수익 방송 라이선스: 법률 검토 또는 Kakao 서면 확인
