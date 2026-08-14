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

로컬 LLM 후보 동일 AIRI A/B는 완료됐고 사용자가 Mi:dm Q4를 최종 운영 모델로
확정했다. Motif, Ministral, Qwen3, Phi-4-mini, Granite와 과거 EXAONE/Kanana/
Gemma의 로컬 weight·평가 snapshot은 2026-08-14 정리했다. exact revision,
모델별 사용법, 대화, 실측과 실패 판단은 지우지 않고 문서·manifest·ignored 결과로
보존했다. 후보를 다시 실행하려면 기존 weight를 찾지 말고 pinned manifest로
재다운로드한다. 통합·복구 경계는
`airi_docs/완료/AIRI-LOCAL-ASSET-CONSOLIDATION-2026-08-14.md`를 따른다.

production-context v2 gate는 구현·측정을 완료했지만 **FAIL**이다. 7개 필드 중 6개는 12/12이고 두 continuity color는 v1보다 개선됐으나, `dialogue_marker`가 0/12로 memory marker `silver-fern`을 결정적으로 복사한다. 따라서 prompt tuning을 계속하거나 품질 PASS라고 주장하지 않는다. 기본 2048·추출 OFF·STT OFF를 유지하며, 설치 extraction을 재실행하지 않았다.

Mi:dm–Motif native 비교는 2026-08-14 clean rerun으로 갱신했다. 기존 Motif 비교는
단일 EOS 방법론 오류와 이전 대화 유래 fixture 우려로 결론에서 제외하되 역사 기록은
보존한다. 새 일반 합성 방송 16건은 메시지 해시 64/64 일치, `hf_card` 1회와
`broadcast_equal` 3회 profile로 TTFT/총 시간/tok/s를 기록했다. equal-profile에서 Mi:dm은
TTFT P50/P95 `0.156/0.157s`, 총 시간 `2.657/8.391s`, `13.973 tok/s`; Motif는
`0.203/0.219s`, `12.493/24.516s`, `5.227 tok/s`다. 품질은 인간 검수 대기다.
Mi:dm exact digest를 운영 기준으로 유지하고 Motif는 배포 차단을 유지한다. 상세:
`airi_docs/진행중/AIRI-MIDM-MOTIF-NATIVE-BROADCAST-RERUN-2026-08-14.md`.
로컬 전체 검증 결과는 위 상세 문서의 `로컬 검증과 종료 상태`를 기준으로 확인한다.

B4c 검토 PC 배치의 dev PC 후속도 2026-08-14에 인수했다. 원격 A/B용 11439
gateway는 `archived_not_deployed`이고 현재 내려가 있으며, 보존 소스의 정확 계약은
비스트리밍·`max_tokens=1..128`이다. B4 방송 모델 경로는 canonical source patch의
exact `11435/v1` 계약을 checkpoint에 고정했으나 B1b 실제 주입 종단 실증은 남아
있다. B4a 후원 action은 `donation_name_callout_request`로 명시했으며 실제 이름
1회 호명은 B4b adapter 리허설 완료 조건이다. `AIRI_BROADCAST_CONTRACT` 기본 OFF와
사용자 확인 전 운영 ON 금지를 유지한다. 상세:
`airi_docs/완료/AIRI-B4C-DEV-PC-FOLLOWUP-2026-08-14.md`.

모든 후보가 실패한 모호한 고유명사·현재 정보 불확실성·무조건 동의에 대해
음란/비속어 moderation과 별도의 epistemic-confidence greybox를 2026-08-15
구현했다. env 기본 OFF이며 현재/live 상태 무근거 단정, 무조건 동의, 문맥 없는
지시어·짧은 미확립 대상을 모델 호출 전에 한국어 fallback으로 처리한다. 아직
승인 실제 채팅 Mi:dm OFF/ON 비교와 운영 ON 채택을 하지 않았으므로 완료/PASS로
승격하지 않는다. 외부 검색은 여전히 OFF이며 검색하지 않았는데 검색했다고 말하면
안 된다.

한국 방송의 실제 변수도 G3/B3-f 평가축에 추가했다. 탬탬버린·아카네 리제·아이네의
실제 채팅은 공개 화면을 무단 scraping하지 않고 방송인/플랫폼 서면 권한 또는
사용자가 권리를 보유한 export가 있을 때만 사용한다. local replay 기반은 권한·
삭제기한 sidecar, 명시 identity/정형 PII 패턴/후원 금액 pre-model 삭제,
시간순·중복·잡음 보존,
content-free report와 ignored private review packet까지 구현됐다. 다음 실작업은
세 채널 권한 확보 → 짧은 구간 캡처 → privacy 사람 검수 → 동일 sequence의
epistemic gate OFF/ON Mi:dm replay다. 상세:
`airi_docs/진행예정/AIRI-KOREAN-LIVE-CHAT-REPLAY-PLAN-2026-08-15.md`.

현재 exact tip과 원격 동기화·CI 상태는 `git status`, `git log -1`, PR checks로 확인한다. 2026-08-14 자산 통합 checkpoint는 PASS이고 Python 3.12 core suite는 `1061 passed, 2 skipped, 916 subtests passed`다. historical test count는 해당 historical base에만 적용한다.

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
- 탬탬버린·아카네 리제·아이네 실제 채팅: 방송인/플랫폼 공식 권한 또는
  사용자가 권리를 보유한 export
- STT/실제 마이크 재개: 사용자 명시 요청
- 제한 라이선스 모델 재도입: 사용자가 후보군에 다시 넣을 때만 별도 법률 검토
