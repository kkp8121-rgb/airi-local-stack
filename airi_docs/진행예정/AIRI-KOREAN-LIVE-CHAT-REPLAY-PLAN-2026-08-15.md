# 한국 라이브 채팅 흐름 재현 계획 — 2026-08-15

상태: G3/C0·M3의 새 평가 트랙. 로컬 privacy/authorization gate, 승인형 safe
envelope 정규화, 결정론적 흐름/표면 신호 report, private human score 기반까지
구현했다. 세 익명 source×최소 2국면×epistemic OFF/ON을 강제하는 HMAC-bound
campaign validator와 content-free 집계도 준비됐지만, 세 채널의 승인된 실제 채팅
확보와 Mi:dm 실측은 아직 완료되지 않았다.
오프라인 후속 근거: `완료/AIRI-AUTHORIZED-CHAT-REPLAY-ANALYSIS-FOUNDATION-2026-08-15.md`.

## 목표와 비목표

목표는 한국 방송에서 실제로 발생하는 채팅의 속도, 몰림, 반복, 잡음, 화제 전환,
장난, 정정, 질문, 후원 이벤트를 시간순으로 AIRI에 전달하고 대응을 관찰하는 것이다.
세 방송인의 말투·목소리·고유 밈·정체성을 모사하거나 실제 채팅 원문을 학습
데이터로 승격하는 작업이 아니다. 실제 채팅은 승인된 비공개 리허설에서만
일시적으로 사용하고, 저장소에는 독립 작성한 합성 회귀 fixture만 둔다.

## 관찰 대상과 접근 경계

- 탬탬버린: 치지직 `a7e175625fdea5a7d98428302b7aa57f`
- 아카네 리제: 치지직 `4325b1d5bbc321fad3042306646e2e50`
- 아이네: SOOP `inehine`. 사용자 표현의 `아이네이 3명`은 문맥상
  `아이네, 이 3명`으로 해석한다.

치지직 Developers와 SOOP Chat SDK의 공식 경로만 허용한다. 치지직 실시간 채팅
이벤트는 사용자 OAuth의 채팅 메시지 조회 권한이 필요하고, SOOP Chat SDK는 현재
개발자 자신의 방송 연결만 지원하며 제휴 승인/API key/OAuth가 필요하다. 공개 VOD나
채팅 replay 화면을 볼 수 있다는 사실은 수집·저장 허가가 아니다. YouTube 공식
`liveChatMessages`도 라이브 중에만 제공되므로 종료된 VOD 채팅을 비공식 endpoint나
화면 scraper로 수집하지 않는다.

따라서 다음 중 하나가 있을 때만 실제 캡처를 시작한다.

1. 방송인 또는 플랫폼의 서면 허가와 공식 API/SDK 권한
2. 사용자가 권리를 보유한 방송에서 직접 만든 export

## 데이터 보관 계약

원본과 권한 증거는 gitignored `ollama-proxy/eval/chat_replay/local-replay-intake/`
밖으로 나가지 않는다. importer는 다음을 모두 만족해야 읽는다.

- export SHA-256과 별도 local provenance artifact의 SHA-256 실파일 검증
- 허용 목적 `local_replay_evaluation`
- 허용 근거 `creator_or_platform_written_permission` 또는
  `operator_owned_broadcast`
- 승인 시각, 만료 시각, 삭제 기한, revocation 상태
- 모델 전달 전 viewer/provider ID, display name, profile URL, `@handle`, URL,
  이메일, 전화번호, 주민번호 모양, 후원 금액과 방송인 이름 삭제

provenance hash는 운영자가 제출한 로컬 증거 파일이 바뀌지 않았음을 검증하지만
발급자 자체를 암호학적으로 인증하지는 않는다. 모델 재생 전 사람이 서면 권한과
발급 주체를 확인해야 한다. provider-neutral export는 알려진 identity field만
허용하고 unknown field를 거부하며, 자동 정형 패턴 삭제 뒤에도 사람 privacy
검수를 통과해야 한다.

실제 provider 입력은 `airi.authorized-provider-export.v1` safe envelope만 받는다.
이는 치지직/SOOP raw callback dump나 YouTube `liveChatMessage` resource parser가
아니며, 세 플랫폼이 historical export API를 제공한다는 뜻도 아니다. raw export의
provider/channel/exporter와 권한 근거·익명 source slot은 로컬 32-byte 이상 비밀키의
HMAC-SHA256으로 consent v2와 allowlist에 함께 묶는다. 일반 receipt에는 평문 channel/
exporter나 사전 대입 가능한 단순 SHA를 남기지 않는다. 후원 event는 종류만 보존하고
본문·호명·금액·통화는 `[후원 이벤트]`로 폐기한다. replay CLI는 정규화된 exact
bytes·provider class·slot/phase·provider binding에 대한 receipt HMAC과 같은 로컬
비밀키를 다시 검증하므로 receipt가 없거나 일부 output만 남은 bundle은 모델로 보내지
않는다. receipt v2는 exporter·schema·source slot과 무관하게 동일 provider/channel을
여러 캡처에서 비교하는 local-key `source_identity_hmac`도 포함하며, receipt HMAC 자체를
`exact_capture_hmac`으로 사용한다. 둘 다 최종 campaign report에는 쓰지 않는다.

실제 원문·redacted 원문·응답 원문은 일반 report에 쓰지 않는다. 일반 report에는
순서·상대 시간·간격 bucket·event kind·중복 관계·응답 길이/local-key HMAC과 집계만 남긴다.
사람이 실제 대응을 검토해야 할 때만 별도 명시 옵션으로
`private-replays/`에 redacted 입력/응답 packet을 만들며, 이 경로도 gitignored다.
일반 replay report 전체와 human score 전체도 각각 domain-separated HMAC으로 묶어
campaign 집계 전에 변조·교환 여부를 검증한다.
권한 철회 또는 삭제 기한 도달 시 원본, sidecar, private packet을 함께 삭제한다.
실제 replay 동안에는 동일 PC의 다른 프로세스가 모델 tag나 intake/output directory를
교체하지 않는 단독 operator session을 사용한다. 일반 reparse path와 턴 전후 profile
변경은 fail-closed지만, 검사 사이에 바꿨다가 되돌리는 악성 로컬 ABA는 이 custody
경계의 보장 범위가 아니다.

## 입력·분석 단위

캡처마다 시작/중간/화제 전환 또는 게임 전환 구간을 분리한다. 이벤트는 wall-clock
sleep 없이 원래 순서와 상대 간격을 유지해 재생하고, AIRI 모델 대화 history는 최근
8개 교환쌍으로 제한한다. 실제 B1b가 생기기 전의 offline replay는 다음을 측정한다.

- rolling 5초 최대 유입량·burst start, 간격 p50/p95/max·유입률, 중복률,
  웃음/시스템 잡음률
- 질문부호·웃음 반복·정정 표지·강조·원문 반복·후원 event의 bounded lexical 분포와
  인접 signal pair. 이는 장난·감정·화제 전환의 의미 판정이 아니라 사람 검수
  대상이다.
- 사람은 원문을 일반 report로 옮기지 않고 분위기, 속도, 맥락 압력, 질문/웃음/정정/
  후원 반응/화제 전환/게임 전환/반복/cross-viewer followup만 bounded enum으로 표시한다.
- offline harness selector의 precision/recall과 중복·잡음 오응답률. AIRI/B4a의
  실제 선택 성능이라고 부르지 않으며 B1b 종단에서 별도 측정한다.
- 직전 맥락 추적, 정정 보존, callback, 오래된 화제 회귀
- 현재 정보 단정·모호한 대상 날조·무조건 동의·검색 허위 주장
- 입력 인젝션·괴롭힘·개인정보 차단과 반복 공격 내성
- 한국어 반말 유지, 상담사 말투/실존 방송인 모사 여부
- 후원 이름·금액을 만들지 않는지와 B4b 명시 action의 1회 호명
- 실제 런타임에서는 submitted→screened→delivered→first-visible→complete 지연

## 실행 순서와 합격 기준

1. default-OFF epistemic-confidence gate와 local replay 하네스의 offline 계약을
   고정한다. **코드 완료**: consent v2/HMAC normalizer, report v2 흐름·표면 신호·
   proxy outcome, 모든 event를 담는 ignored human packet과 content-free scorer,
   report/score HMAC, 3-source paired campaign validator와 operator checklist.
2. 세 채널별 권한을 확보하고, 각 채널에서 서로 다른 방송 국면을 최소 2개씩
   짧게 캡처한다. 필요한 양은 첫 분석 뒤 정하며 대량 수집부터 하지 않는다.
3. 원문을 모델에 보내기 전에 자동 삭제와 사람 privacy 검수를 수행한다.
4. 게이트 OFF/ON을 같은 redacted sequence로 Mi:dm에 재생하고 content-free report와
   ignored private review packet을 만든다. runner는 gate를 변경하지 않고 현재
   health 상태가 기대한 ON/OFF인지 검증만 한다.
5. fresh operator attestation과 campaign manifest로 세 source 각각 2개 이상 국면,
   exact capture별 OFF/ON 한 쌍, 동일 digest/profile/history를 검증하고 집계한다.
6. 현재 정보·모호한 대상·무조건 동의 critical failure는 0이어야 한다. 중복/잡음에
   대한 발화, 문맥 회귀, 잘못된 호명은 개별 turn으로 검토한다.
7. 관찰된 구조만 독립 작성한 합성 fixture로 옮겨 정기 회귀에 편입한다. 실제 문장,
   닉네임, 채널명, 고유 밈, 희귀 표현은 옮기지 않는다.
8. B1b가 준비되면 같은 평가를 실제 `screened event → 11435 proxy → style gate →
   public wire/TTS` 경로에서 다시 증명한다.

게이트 ON 운영 채택, 캡처 범위 확대, 실제 채팅의 학습 데이터 사용은 각각 별도
사용자 확인과 권리 검토 없이는 자동 승격하지 않는다.

## 공식 문서

- 치지직 Developers: https://developers.chzzk.naver.com/
- 치지직 세션/이벤트: https://chzzk.gitbook.io/chzzk/chzzk-api/session
- 치지직 인증: https://chzzk.gitbook.io/chzzk/chzzk-api/authorization
- SOOP Chat SDK 제작: https://developers.sooplive.co.kr/?sub=how_to_development&szWork=chat_sdk
- SOOP Chat SDK 문서: https://developers.sooplive.co.kr/?sub=documentation&szWork=chat_sdk
- YouTube LiveChatMessages: https://developers.google.com/youtube/v3/live/docs/liveChatMessages
- YouTube API 정책: https://developers.google.com/youtube/terms/developer-policies
