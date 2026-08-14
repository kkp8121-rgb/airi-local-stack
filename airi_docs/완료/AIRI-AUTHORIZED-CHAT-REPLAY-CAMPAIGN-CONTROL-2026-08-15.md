# 승인 실제 채팅 3-source campaign control 기반 — 2026-08-15

상태: **오프라인 control plane 완료 / 실제 세 채널 캡처·Mi:dm OFF/ON 실측 미완료**

## 이번 배치가 닫은 간극

기존 단일-capture replay는 exact normalized bytes를 확인했지만, 서로 다른 캡처가
같은 승인 채널인지, human score가 어느 모델 응답 run을 검토했는지, 세 채널×복수
국면×OFF/ON 전체가 빠짐없이 끝났는지를 campaign 수준에서 증명하지 못했다.

이번 배치는 다음 local-only 증거 체인을 추가했다.

1. normalization receipt v2의 `source_identity_hmac`은 provider/channel만 local
   key로 묶어 exporter·schema·anonymous slot이 달라도 같은 source임을 검출한다.
2. receipt의 `normalization_hmac_sha256`은 exact normalized bytes·phase·provider
   binding·event count를 묶으며 replay에서는 `exact_capture_hmac`으로 사용한다.
3. Mi:dm replay report 전체와 각 response는 domain-separated local-key HMAC으로
   묶인다. private scorer는 response 원문을 seq/length/outcome/HMAC과 대조한다.
4. human score 전체도 별도 HMAC으로 묶어 campaign 집계 전 변조·run 교환을
   fail-closed한다.
5. 이벤트 순서별 `respond|ignore` source label도 별도 HMAC으로 묶어 OFF/ON에서
   label 분포만 같고 대상 turn이 바뀌는 경우를 거부한다.
6. 사람 source observation은 free text 없이 분위기, 속도, 맥락 압력, 제한된
   dominant pattern enum만 허용한다. 응답 평가는 grounded/context/tone/privacy와
   current-fact/reference/agreement calibration을 분리한다.

## Campaign 계약

`aggregate_replay_campaign.py`는 ignored local manifest와 report만 읽고 다음을
모두 요구한다.

- 서로 다른 HMAC identity를 가진 `channel_a`, `channel_b`, `channel_c` 정확히 3개
- source마다 `opening|middle|topic_transition|game_transition` 중 2개 이상 국면
- exact capture마다 epistemic OFF 1회와 ON 1회
- 모든 run의 Mi:dm tag/digest pinned 상태, `num_ctx=2048`, temperature 0,
  seed 42, `max_tokens=128`, history 8 일치
- replay report와 human score의 source/run/profile/HMAC 일치
- 모든 model response의 bounded human review 완료
- permission scope, privacy review, retention/revocation, exclusive session을 확인한
  24시간 이하 fresh operator attestation

aggregate는 source capture의 유입량, noise/repeat, timing bucket, rolling burst,
surface signal과 사람 atmosphere/pace/context/pattern을 한 번만 합산한다. OFF/ON은
response outcome, selector, quality pass rate, explicit critical failure와 paired delta를
따로 낸다.

최종 aggregate에는 provider/source identity, capture/pair/run ID, file path, digest,
hash/HMAC, response row, 입력·응답 text가 없다. `campaign_critical_gate`가 pass여도
`automatic_adoption=false`, `user_confirmation_required=true`가 고정이다.

## 보안·해석 경계

- local HMAC은 운영자 custody 안의 accidental swap/tamper 방지다. 서면 권한
  발급자나 플랫폼 권한을 암호학적으로 인증하지 않는다.
- bounded 사람 label은 해당 capture의 관찰 결과이지 방송인 성격·고유 스타일의
  학습 허가나 모사 근거가 아니다.
- selector 수치는 offline harness의 noise/repeat 전달 정책이다. B1b/B4a live
  priority 또는 설치 Electron/TTS 종단 성능 증거가 아니다.
- 실제 target mapping은 보호된 local allowlist/permission record에만 두며 git이나
  campaign aggregate에 쓰지 않는다.

## 로컬 검증

- chat replay/normalizer/private scorer/campaign focused: **34/34 PASS**
- Python compile: PASS
- `git diff --check`: PASS
- `test-current-checkpoint.ps1`: PASS

원격 Actions는 repository billing 차단이 지속되어 실행하지 못한다. evaluation
shard에 campaign test를 등록하고 local verification으로 대체하며 커밋 메시지에도
제약을 남긴다.

## 남은 실제 작업

1. 탬탬버린·아카네 리제·아이네 각각의 서면 권한과 공식/권리 보유 export를
   확보한다. 공개 VOD/chat을 scraping하지 않는다.
2. source별 서로 다른 국면 2개 이상을 safe envelope로 정규화하고 사람이 privacy
   검수한다.
3. fresh attestation 아래 같은 exact capture를 Mi:dm epistemic OFF/ON으로 재생한다.
4. 사람이 bounded source observation과 모든 response review를 완성하고 campaign을
   집계한다.
5. privacy/current-fact/reference/agreement critical failure 0을 확인한 뒤에만 운영
   ON 여부를 사용자에게 제안한다.
6. B1b 준비 후 `screened event -> 11435 proxy -> style gate -> public wire/TTS`에서
   같은 capture를 종단 재검증한다.
