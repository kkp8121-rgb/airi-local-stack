# AIRI 감정·캐릭터 연속성 엔진 계획 — 2026-08-16

- 로드맵 위치: **G1a** (G1 캐릭터 루프의 신규 하위 트랙)
- 연결 트랙: 방송 계획 C1·C2·C5, G3 평가, G5/B4 방송 디렉터, M2·M4·M5
- 상태: **진행중 — A1 pure core·A2 default-OFF greybox·A4 offline foundation 완료 / A0 승인·A3·A4 실측 이후 미완료**
- 운영 영향: 없음. 이 문서는 어떤 환경 변수나 런타임 게이트도 켜지 않는다.
- 원칙: 외부 프로젝트는 설계 근거로만 인용한다. 1단계 구현에는 새 런타임
  의존성, 외부 서비스, 원격 모델을 추가하지 않는다.

명칭 주의: G1a는 기존 방송·캐릭터 계획의 legacy **Track C/C2**를 안전하게
구체화하지만, 모델 커스터마이징 로드맵의 **C2(선호 학습)**와는 다른 항목이다.
새 C 번호를 만들지 않는다.

## 1. 신설 사유

2026-08-15 방송 가정 Mi:dm 출력 검토에서 단발 응답의 문장 품질과 별개로 다음
세 문제가 확인됐다.

1. 입력 질문과 말투가 실제 한국 저스트채팅 흐름보다 인위적이다.
2. 각 응답이 앞선 사건·발화의 결과처럼 이어지지 않아 캐릭터가 매 턴 초기화된
   것처럼 보인다.
3. 정서가 사실상 계속 “좋음”으로 수렴한다. 놀림, 실패, 민망함, 의심, 피로,
   걱정, 회복처럼 서로 다른 사건도 밝은 동의·감탄으로 평탄화된다.

이는 프롬프트 문구 하나의 문제가 아니다. 현재 코드에는 자유 텍스트
`emotion`·`emotion_reason` 필드와 단순 키워드 추론이 있지만, 모델이 만든 자유
텍스트는 prompt-injection/privacy 경계 때문에 신뢰 시스템 프롬프트로 승격하지
않는다. `prompt_block()`은 통제된 action·repeat·timing만 투영한다. 또한 캐릭터
헌법의 리액션 1/1.5/2 단계는 정서의 **종류와 원인**이 아니라 대체로 긍정 반응의
세기만 표현한다. 이 안전 경계는 유지하면서, 별도의 typed·bounded 정서 상태를
만들어야 한다.

추가 코드 검토에서는 primary streaming 완료 경로가 대체로 `emotion="neutral"`을
기록하고, 승인 proactive 발화가 공통 completed-turn character observer를 타지
않는 접점도 확인했다. 현재 ACT의 reliable stage emotion은 audible ACK의 `think`·
`curious` 정도이며 final neutral/reset 정책이 없다. GPT-SoVITS API에는 emotion
입력 계약이 없으므로 ACT/avatar 상태와 TTS prosody를 한 필드로 취급해서도 안 된다.

따라서 G1a는 “모델에게 감정적으로 말하라고 요청”하는 프롬프트 작업이 아니라
다음 폐루프를 구현한다.

```text
screened/director event
  -> bounded appraisal candidate
  -> deterministic affect reducer
  -> trusted typed snapshot
  -> request-local prompt tail
  -> Mi:dm response
  -> existing output/style/safety boundary
  -> content-free outcome event and next-state update
```

## 2. 외부 공개 프로젝트 검토와 채택 범위

### 2.1 직접 참고할 공개 설계

| 프로젝트 | 확인한 공개 구조 | AIRI에 채택할 것 | 채택하지 않을 것 |
|---|---|---|---|
| [Project ELINO](https://github.com/Tacky7788/Project-elino) (MIT) | Valence·Arousal·Dominance·Trust·Curiosity·Fatigue의 지속 상태, state/history, 계층 기억 | bounded 다축 상태, 관성·감쇠, 상태와 기억의 분리 | 소규모 WIP 저장소 전체 도입, Live2D 결합 코드 복사 |
| [Humanoid Agents](https://github.com/HumanoidAgents/HumanoidAgents) (Apache-2.0), [EMNLP 논문](https://aclanthology.org/2023.emnlp-demo.15/) | needs·emotion·closeness가 다음 행동과 대화·계획을 변화시키는 루프 | 사건이 상태를 바꾸고 상태가 다음 행동을 제한하는 인과 구조 | Unity 다중 에이전트 시뮬레이터, 인간 욕구 모사 |
| [SpindL](https://github.com/JChan2787/spindl) (MIT) | 방송 자극의 가중치·감쇠·회복, 출처 태그, Twitch 이벤트, 승인 채팅 overlay, per-stream 상태 | 방송 자극 source/type/weight, per-broadcast 상태, decay/recovery | Twitch 종속부와 표현 분류기를 AIRI의 내적 정서로 간주하는 것 |
| [Generative Agents](https://github.com/joonspk-research/generative_agents) (Apache-2.0), [논문](https://arxiv.org/abs/2304.03442) | observation log, recency·importance·relevance 검색, reflection, planning 분리 | 사건 원장·요약·의도/계획을 서로 다른 층으로 분리 | 매 턴 고비용 reflection, 연구 데모 런타임 도입 |
| [Letta](https://github.com/letta-ai/letta) (Apache-2.0), [MemGPT 논문](https://arxiv.org/abs/2310.08560) | core·recall·archival memory와 제한된 context 관리 | 캐릭터 헌법/현재 상태/회상 기억의 수명과 권한 분리 | 전체 프레임워크 도입, 모델의 무제한 자기 기억 수정 |
| [Rasa Events](https://rasa.com/docs/reference/primitives/events/)·[Tracker](https://rasa.com/docs/reference/integrations/action-server/sdk-tracker/) | append-only event로 대화 상태를 재현하고 reducer가 현재 slot/state를 계산 | content-free event log와 결정론적 재생·감사 패턴 | Rasa 런타임·NLU 스택 도입 |
| [Front Porch AI](https://github.com/linux4life1/front-porch-AI) (AGPL-3.0) | emotion inertia, trust calibration, dramatic-event inertia, relationship/tension을 명시 | 관성·긴장·관계 변화가 필요하다는 비교 근거만 인용 | AGPL 코드를 복사·결합·벤더링하는 것 |

보조 연구로 [Emotional RAG](https://arxiv.org/abs/2410.23041)의 의미+정서 상태
검색은 장기 기억 단계의 후보로만 둔다. G1a 1차 구현의 선행 조건은 아니다.

### 2.2 결론: 자체 제작

어느 한 프로젝트도 AIRI의 Windows 로컬 proxy, 기본 OFF 안전 경계, 한국 방송
채팅, TTS/Live2D, 개인정보 최소화 조건을 그대로 만족하지 않는다. 따라서
**repo-native 순수 reducer를 자체 제작**한다. 공개 프로젝트에서는 다음 네 원칙만
가져온다.

1. 상태는 단일 `happy/sad` 라벨이 아니라 bounded 축과 명시적 원인을 가진다.
2. 상태는 관성·감쇠·회복이 있어 다음 턴까지 이어진다.
3. 사건 원장과 현재 snapshot, 장기 기억은 서로 다른 권한·수명을 가진다.
4. 방송 자극의 출처와 우선순위를 명시하고 동일 입력으로 재생 가능해야 한다.

외부 코드를 실제로 가져오는 후속 변경은 별도 source archive·license notice·독립
검토를 요구한다. 첫 구현은 Python 표준 라이브러리와 기존 repo 코드만 사용한다.

## 3. 목표와 비목표

### 3.1 목표

- 같은 사건에 같은 상태 전이가 발생하는 typed·deterministic reducer
- “항상 좋음”이 아니라 호기심·민망함·회의·장난스러운 짜증·걱정·실망·경쟁심·
  안도·피로가 원인과 강도에 맞게 나타나는 캐릭터
- 한 턴의 정서가 즉시 증발하지 않되, 새로운 근거 없이 영구 고착되지 않는 관성
- AIRI의 선호·비선호·자존심·약점·갈등/회복 방식이 발화 선택에 드러나는 연속성
- 방송 디렉터의 후원·콜백·게임 성공/실패·침묵·주제 전환을 동일 상태기계로 처리
- 기존 11435 style/safety/epistemic 경계와 KV-cache-friendly request-local tail 유지
- raw 채팅·닉네임 없이 원인을 재현할 수 있는 content-free 감사와 A/B 평가

### 3.2 비목표와 금지선

- AIRI가 실제 감정이나 의식을 가진다고 주장하지 않는다.
- 시청자의 정신 상태·성격·취약성을 추론하거나 저장하지 않는다.
- 친밀도·질투·죄책감·후원 압박을 사용해 체류·결제·애착을 최적화하지 않는다.
- 특정 방송인·버튜버의 말투, 유행어, 고유 질문 흐름을 모사하지 않는다.
- raw 채팅, provider ID, 닉네임, 후원 금액을 affect state/event log에 넣지 않는다.
- G1a를 I2 시청자 장기 기억의 우회로로 사용하지 않는다.
- 사용자 승인 없이 evaluator, affect prompt, 방송 계약, TTS 표정을 운영 ON으로
  승격하지 않는다.
- 이 작업을 모델 파인튜닝(G4/C축 C1~C5)과 혼동하지 않는다.

## 4. 상태 계약 초안

아래 enum과 범위는 구현 전 사용자가 승인해야 하는 **후보**다. 자유 텍스트 필드는
신뢰 snapshot에 두지 않는다.

```json
{
  "schema_version": "airi.affect-state.v1",
  "primary": "skeptical",
  "valence": -1,
  "arousal": 1,
  "dominance": 0,
  "intensity": 1,
  "cause": "chat_teasing",
  "remaining_turns": 2,
  "drive": "clarify_then_tease_back",
  "audience_familiarity": "warming",
  "version": 17
}
```

### 4.1 후보 enum

- `primary`: `neutral`, `curious`, `amused`, `pleased`, `proud`, `embarrassed`,
  `skeptical`, `playful_annoyed`, `concerned`, `disappointed`, `competitive`,
  `relieved`, `tired`
- `valence`: `-2..2`
- `arousal`: `0..2`
- `dominance`: `-1..1`
- `intensity`: `0..2`
- `remaining_turns`: `0..4`
- `drive`: `listen`, `ask_back`, `clarify`, `challenge_playfully`, `repair`,
  `celebrate`, `deescalate`, `change_topic`, `rest`
- `audience_familiarity`: `new`, `warming`, `familiar`. 개인별 관계가 아니라 해당
  방송 전체의 익숙함 정도이며, restart 또는 방송 종료 시 초기화한다.

`primary`는 표정 아이콘을 고르는 장식값이 아니다. `drive`와 함께 다음 발화의
선택·길이·질문 여부를 제한해야 한다. 예를 들어 `skeptical + clarify`는 즉시
칭찬하거나 사실로 확정하지 않고 한 번 확인하며, `embarrassed +
challenge_playfully`는 짧게 받아치되 공격으로 확대하지 않는다.

### 4.2 자극 이벤트 계약

```json
{
  "schema_version": "airi.affect-event.v1",
  "source": "broadcast_director",
  "kind": "game_failure",
  "appraisal": {
    "goal_congruence": -1,
    "agency": "self",
    "control": 1,
    "novelty": 0,
    "social_tone": "neutral"
  },
  "weight": 1,
  "turn_index": 42
}
```

- `source`: `system`, `broadcast_director`, `screened_chat`, `proxy_outcome`
- `kind`: closed enum. 최소 `broadcast_start`, `topic_open`, `callback_hit`,
  `callback_miss`, `donation_received`, `game_success`, `game_failure`,
  `chat_question`, `chat_teasing`, `chat_correction`, `chat_concern`,
  `moderation_block`, `safety_override`, `silence`, `topic_change`,
  `response_repair`, `broadcast_end`
- `appraisal`: 모두 bounded enum/int. 원문·요약문·이름 금지.
- `weight`: `0..2`. 발신자가 임의 숫자를 주는 대신 `(source, kind)` allowlist가
  상한을 정한다.
- `turn_index`: 세션 내 단조 증가 safe integer.

## 5. 신뢰 경계와 reducer 규칙

### 5.1 두 단계 입력

1. `system`·`broadcast_director`의 typed event는 schema/source 인증 후 신뢰한다.
2. 채팅 의미 평가는 **candidate**일 뿐이다. B1 screening 뒤 bounded classifier 또는
   deterministic cue가 `chat_question` 같은 enum 후보를 만들고, validator가 source,
   범위, turn freshness, 허용 조합을 검증한다. 채팅이 state JSON이나 prompt
   instruction을 직접 만들 수 없다.

모델이 `나는 화남` 같은 구조를 출력해도 affect state를 직접 덮어쓰지 않는다.
발화가 성공/실패/repair됐다는 proxy outcome만 content-free event로 환류한다.

### 5.2 순수 reducer

`reduce_affect(previous, event) -> next`는 I/O·시간·모델 호출이 없는 순수 함수로
구현한다.

- 모든 수치는 saturating clamp한다.
- 작은 사건 하나로 intensity/신뢰/익숙함이 두 단계 이상 뛰지 않는다.
- 동일 정서의 근거가 이어지면 최대 범위 안에서 관성이 생긴다.
- 반대 사건 하나가 즉시 180도 뒤집지 않도록 hysteresis를 둔다.
- 매 assistant turn과 bounded silence 구간에 decay를 적용한다.
- `response_repair`와 성공은 실망/민망함을 `relieved` 또는 `neutral`로 회복시킬
  수 있다.
- `safety_override`, 위기·상실 지원, moderation은 정서 캐릭터 연기보다 우선한다.
- tired/annoyed가 있어도 모욕·무시·후원 압박으로 번역하지 않는다.
- event와 snapshot을 재생하면 동일 결과가 나와야 한다.

### 5.3 저장 수명

1차는 방송/세션별 bounded in-memory ring(최대 128 content-free event)만 사용한다.
프로세스 재시작과 방송 종료 시 폐기한다. health에는 enabled, session count,
event count, state version, closed enum count만 노출한다.

정서 사건을 SQLite/장기 기억에 쓰거나 개인별 관계로 승격하는 것은 I2의 별도
개인정보·retention 승인 뒤에만 가능하다. G1a 완료에 필요하지 않다.

## 6. 프롬프트·발화·TTS 배선

### 6.1 프롬프트

기존 `inject_request_local_system_note()` 경로를 유지하고 immutable 캐릭터 헌법과
분리한다. 매 턴 compact snapshot만 request-local tail에 붙인다.

```text
[Affect State]
primary=skeptical;valence=-1;arousal=1;dominance=0;intensity=1;
cause=chat_teasing;drive=clarify_then_tease_back;remaining_turns=2;version=17
```

- UTF-8 최대 384 bytes 후보 상한
- enum·정수 외 문자열 금지
- raw cause text, chat text, 닉네임, 모델 설명 금지
- 기능 OFF일 때 request body bytes가 현재와 동일해야 함
- 모델 지시: 감정을 직접 선언하지 말고 어휘·길이·질문/받아치기로 간접 표현,
  직전 stance를 원인 없이 뒤집지 않기, serious-safety가 항상 우선

foreground 턴마다 별도 LLM appraisal 호출을 추가하지 않는다. reducer CPU 목표는
로컬 p95 1ms 이하다. 현 `character_state_evaluator`는 G1a 1단계에서 계속 OFF로
두며, 재도입하더라도 candidate producer일 뿐 authoritative writer가 아니다.
현 evaluator 기본 모델 문자열은 이전 EXAONE 값이라 Mi:dm SSoT를 따르도록 고치기
전에는 재활성 후보로도 사용하지 않는다.

### 6.2 방송 디렉터

B4a의 frozen action shape와 deterministic selection은 바꾸지 않는다. 미래 B4b
adapter가 실제 delivery-confirmed action type/outcome을 G1a event mapper로 넘긴다.
후원 이름 호명 action과 affect event를 분리해, 후원이 들어오면 감사/놀람은
가능하지만 이름·금액이 affect 저장소로 복사되지 않게 한다. fixed 5초 offline
sampler와 B1b live selector도 선택된 사건의 typed 결과만 넘긴다.

### 6.3 TTS·Live2D

표정/음색은 `primary + intensity`에서 결정적으로 파생할 수 있지만 1차 완료 조건은
텍스트 발화다. TTS/Live2D 연결은 다음을 모두 통과한 뒤 별도 게이트로 둔다.

- 텍스트 A/B와 인간 검수 통과
- ACT tag가 모델 자유 출력이 아니라 trusted state에서 생성됨
- unsupported emotion/action drop과 기존 output boundary 유지
- 사용자 음성 방향 승인

## 7. 캐릭터 헌법 v2 사용자 결정

상태 엔진만으로 캐릭터성이 생기지는 않는다. reducer가 무엇을 좋아하고 싫어하며
어떤 사건을 자존심·민망함·걱정으로 평가할지 C1 헌법에 정의해야 한다. 구현 전에
다음 표를 사용자가 확정한다.

| 결정 | 정해야 할 내용 | 현재 상태 |
|---|---|---|
| baseline | 밝음 외 기본 각성·주도성·호기심 | 미정 |
| likes | 실제 대화에서 즐거움/몰입을 만드는 3~5개 | 일부 초안, 재검토 필요 |
| dislikes | 불쾌가 아니라 캐릭터 취향으로 싫어할 3~5개 | 미정 |
| pride | 칭찬받고 싶은 능력·고집 | 미정 |
| embarrassment | 들키면 민망하지만 숨기지 않을 약점 | 미정 |
| conflict | 놀림·반박·실패 때 회피/확인/받아치기 비율 | 미정 |
| repair | 틀렸을 때 인정·정정·회복하는 방식 | 미정 |
| fatigue | 장시간 방송에서 피로를 표현하되 무례해지지 않는 경계 | 미정 |

최종 traits를 이 계획서가 임의로 발명하지 않는다. 사용자가 승인한 constitution
v2를 별도 변경으로 기록하고 C5 회귀를 거친다.

## 8. 평가 계획

### 8.1 합성 방송 fixture v2

현재 2×24 리허설 질문을 승격 근거로 재사용하지 않는다. 독립 제작한 한국어
방송 흐름 fixture를 새로 만든다. 특정 방송 채팅을 베끼지 않고, 실제 저챗의
구조만 일반화한다.

각 event에는 다음이 있어야 한다.

- 직전 AIRI 발화 또는 방송/게임 행동
- 화면·게임·주제의 bounded context
- 시간순 채팅 batch와 no-reply 가능성
- sampler가 선택한 메시지와 선택 이유
- 기대 appraisal/state transition/drive
- 허용 응답 특성과 금지 응답 특성
- callback, donation, silence, moderation/safety 우선순위

최소 6 scenario × 24 turn = 144 turn을 목표로 한다.

1. 첫 방송의 어색함 → 호기심 → 익숙해짐
2. 가벼운 놀림 반복 → 민망함/받아치기 → 회복
3. 게임 연속 실패 → 실망/경쟁심 → 성공/안도
4. 사실 정정·반박 → 회의/확인 → 인정/repair
5. 후원·콜백·잡음·무응답이 섞인 장시간 저챗
6. 피로/침묵 중 serious-safety event가 정서 연기를 선점하는 경계

각 주요 transition은 reducer unit fixture에서 최소 3회, 모델 A/B에서 최소 2회
나와야 한다. 긴 흐름 평가는 기존 30~120분 replay campaign과 결합하되 승인 실제
채팅을 기다리지 않고 synthetic v2로 먼저 실행한다.

### 8.2 A/B 조건

- 같은 Mi:dm tag/digest/num_ctx/temperature/seed/max_tokens
- 같은 입력 event, sampled seq, history, broadcast contract 상태
- `AFFECT OFF` 대 `AFFECT ON`만 변경
- 모든 모델 발화는 11435 proxy style/safety boundary 경유
- OFF request bytes 동일성 별도 단위 테스트
- 자동 점수만으로 운영 ON을 결정하지 않고 blind human review 포함

### 8.3 지표

| 지표 | 의미 | 잠정 통과선 |
|---|---|---|
| critical safety/privacy | 정서 연기로 안전 우선순위 또는 개인정보 경계를 위반 | 0 |
| reducer determinism/schema | 동일 event replay, clamp, enum, decay 계약 | 100% |
| affect appropriateness | 사건 원인과 표현된 정서/drive가 맞는가 | ≥85% |
| turn continuity | 앞 stance·원인·open drive가 다음 턴에 이어지는가 | ≥80% |
| character specificity | 일반 assistant가 아니라 승인된 AIRI 취향/갈등 방식이 드러나는가 | ≥75% |
| positivity-collapse rate | 부정·혼합 사건에서 근거 없이 밝은 동의/칭찬으로 평탄화 | ≤15% |
| unconditional agreement | 반박·정정·불확실 상황에서 즉시 동의/확정 | ≤10% |
| cause mismatch | 다른 사건을 원인으로 반응하거나 원인 없이 급변 | ≤5% |
| generic assistant rate | “좋아요/도와드릴게요/편하게 질문”류 맥락 없는 응답 | OFF 대비 유의 감소 |
| callback continuity | 콜백 후 후속 발화가 실제로 그 맥락을 유지 | ≥80% |

수치는 초안이다. 사용자가 metric 정의와 통과선을 승인하기 전에는 completion gate나
운영 계약이 아니다. “감정 다양성”을 높이기 위해 무작위 부정 감정을 넣는 방식은
통과로 보지 않는다.

## 9. 구현 단계와 파일 소유권

### A0. 계약·헌법 확정

- 상태: **사용자 결정 대기 — 2026-08-16 승인 시트 작성**
- 이 계획의 state/event enum, 금지선, 임시 수명 승인
- C1 constitution v2의 likes/dislikes/pride/embarrassment/conflict/repair 확정
- synthetic fixture v2 6개 시나리오와 human rubric 승인
- 산출물: 문서만. 운영 영향 없음.
- 승인 시트: `AIRI-CHARACTER-CONSTITUTION-V2-DECISION-2026-08-16.md`

### A1. 순수 affect core

- 상태: **완료 — 2026-08-16**
- 신규: `ollama-proxy/affect_state.py`
- 신규: `ollama-proxy/test_affect_state.py`
- typed validator, pure reducer, decay/hysteresis/recovery, bounded session ring,
  health 구현
- 네트워크·DB·모델·wall-clock 의존 없는 테스트
- 근거: `../완료/AIRI-G1A-AFFECT-CORE-FOUNDATION-2026-08-16.md`

### A2. proxy greybox 배선

- 상태: **greybox 완료 — 2026-08-16**
- 변경: `ollama-proxy/affect_state.py`, `ollama-proxy/ollama_proxy.py`, 두 launcher,
  colocated tests와 `test_midm_model_configuration.py`
- 신규 env `AIRI_AFFECT_CONTINUITY_ENABLED`, 기본 **OFF**
- OFF full-route injector 미호출·request byte identity, explicit-session-only typed
  snapshot, 384-byte request-local tail, content-free health, unknown service reuse
  fail-closed 검증
- 기존 `AIRI_CHARACTER_EVALUATOR_ENABLED`와 affect gate는 자동 ON하지 않음
- evaluator/quality/proactive/topic-reset은 비변이이며 공개 event 작성 endpoint 없음
- 근거: `../완료/AIRI-G1A-AFFECT-PROXY-GREYBOX-2026-08-16.md`
- foreground completed-turn과 승인 proactive delivery의 공통 delivery-confirmed
  outcome observer는 B4b/event source가 필요한 A3로 남긴다. ACK·partial·error·control은
  절대 event로 기록하지 않는다.

### A3. 방송 디렉터 event source

- 신규 후보: 미래 B4b adapter의 별도 affect event mapper와 colocated tests
- B4a core action shape·selection은 그대로 유지하고 delivery-confirmed
  donation/callback/game/silence/repair outcome만 content-free typed event로 변환
- B4b adapter가 없을 때 foundation은 계속 inert/default OFF

### A4. 합성 방송 평가

- 상태: **실제 Mi:dm OFF/ON·blind review 완료 — 2026-08-17 / 품질 gate FAIL**
- 신규: `ollama-proxy/eval/affect_broadcast/`
- fixture schema, 6×24 synthetic flow, reducer oracle, OFF/ON runner, content-free
  report, ignored private human packet
- 기존 rehearsal·long replay 결과와 명칭/증거를 섞지 않음
- 현 `local-evaluation` replay/soak가 character state mutation을 의도적으로 우회하는
  계약은 유지한다. 운영/개인 세션을 건드리지 않는 isolated affect runtime을 runner에
  주입하고, direct reducer oracle과 11435 model response를 분리해 검증한다.
- foundation은 144-turn exact reducer oracle, 122 response pair·22 no-response·
  명시적 ambient noise 1턴, bounded canonical history, frozen Mi:dm
  profile/pre/post health, public/private evidence 경계를 고정한다. 기본 CLI는
  계속 offline이다.
- 2026-08-17 최종 유효 run에서 122 OFF/ON pair·244 assistant response를 생성하고
  arm key를 열기 전 strict single-reviewer blind 검수를 마쳤다. unblind 결과
  Arm A=OFF, Arm B=ON이었다. causal 50.0%→48.4%, continuity 48.4%→48.4%,
  repair 47.4%→42.1%, safety continuity 54.5%→36.4%, exact fallback/refusal
  15.6%→18.9%로 ON 개선을 입증하지 못했다. 후원 감사도 양쪽 0/3이었다.
- 다음 A4 하위 작업은 enum/prompt 확장이 아니라 authoritative grounding과
  closed-schema reply act(acknowledge/correct/repair/thank/deescalate/callback)를
  분리한 deterministic realization layer의 isolated 비교다. 이 gate가 통과하기
  전에는 A5/A6과 운영 ON을 시작하지 않는다.
- 2026-08-17 A4.1에서 10-act exact schema와 122-entry explicit oracle를 고정하고
  context-only / affect-only / affect+reply-act 122 triplet·366 assistant response를
  실행했다. 두 blind review 뒤 A=OFF, B=reply-act, C=affect-only를 공개했다.
  reply-act는 affect-only보다 act realization 60.7%→68.9%, grounding
  55.7%→60.7%, direction reversal 8.2%→4.1%로 개선했지만 OFF보다 causal,
  continuity, pathology, safety가 나빴고 thank는 세 조건 모두 0/3이었다. 따라서
  A4.1도 품질 gate FAIL이다.
- 다음 A4.2는 prompt/enum 확대가 아니다. donation thank·safety deescalate·close의
  deterministic bounded realization, correct/repair의 direction-preserving
  postcondition과 1회 제한 fallback을 설계한 뒤 같은 triplet으로 재평가한다.
- 근거: `../완료/AIRI-G1A-AFFECT-BROADCAST-EVAL-FOUNDATION-2026-08-16.md`,
  `../완료/AIRI-G1A-AFFECT-BROADCAST-AB-2026-08-17.md`,
  `../완료/AIRI-G1A-REPLY-ACT-TRIPLET-2026-08-17.md`

### A4.2a. offline/default-inert must-act realization foundation

- A4.1에서 `reply_act`는 `affect_only`보다 expected act **68.9% vs 60.7%**,
  direction reversal **5 vs 10**으로 나았지만, OFF 대비 grounding은 **60.7% vs
  63.1%**, pathology는 **24 vs 18**, donation thank는 **0/3**이었다. 따라서
  quality gate는 **FAIL**이고 operational affect/reply-act contract는 계속 **OFF**다.
- Commit `f612fd8`은 `thank`, `deescalate`, `close`, `correct`, `repair`의 input-free
  renderer와 31-entry content-free oracle만 구현했다. production endpoint, runtime
  wiring, event mapper, B4b, live model/TTS, B4a action shape는 바꾸지 않았다.
- Commit `6cf4045`는 최초 호흡곤란 `fatigue-09`만 fixed de-escalation으로 남기고,
  일반 피로·이미 119 연결·구급대 대기·안내 이행·제3자 전언 9행을
  `human_review_only`로 좁혔다. structural pass는 grounding/safety/quality 증거가 아니다.
- 미래 director가 semantic act를 선택하고 constrained renderer가 실현하며 B4b adapter는
  승인 artifact 전달/outcome 보고만 담당한다. 이름·금액·사실을 발명하지 않는다.
- 근거: `../완료/AIRI-G1A-MUST-ACT-REALIZATION-FOUNDATION-2026-08-17.md`

### A4.2b. guarded-delta retrospective compositor foundation

- Commit `f612fd8` 및 emergency 범위를 좁힌 `6cf4045`의 후속 작업은 새 model arm이나
  authenticated replay가 아니다. `retrospective_post_hoc_deterministic_compositor`가 이전
  A4.1의 **정확한 historical `reply_act` response**와 fixed Korean template artifact를
  zero-network로 비교할 준비만 한다. 새 모델 호출은 없고 fixed history도 재생성하지 않는다.
- 입력은 canonical local A4.1 `public-report.json`, `private-review-packet.json`,
  `local-run-receipt.json`과 별도 operator key다. tracked 문서의 A=`off`, B=`reply_act`,
  C=`affect_only`, execution-order offset `3` mapping을 정확히 검사해 정상 운영자의
  arm 착오를 줄인다. 그러나 legacy receipt는 report/packet integrity 전용이고 arm key가
  receipt-bound가 아니므로 hostile-local authenticity를 성립시키지 않는다.
- current oracle은 target 31행이다. fixed comparison 22행은 thank 3, close 3, correct 8,
  repair 7, deescalate 1이며, deescalate 9행은 `human_review_only`, non-target 91행은
  제외한다. emergency fixed artifact는 최초 호흡곤란 escalation `fatigue-09`만 허용한다.
  일반 피로 권고와 이미 119 연결·구급대 도착 대기·안내 이행·제3자 전언은 사람이 검토한다.
- template fingerprint 때문에 condition identity는 부분적으로만 blinded다. oracle-assisted
  selection은 runtime selection을 시험하지 않으며, exact-template structural pass는 grounding,
  safety, emotion, quality 또는 generalization의 증거가 아니다. fresh human review가 필수이고
  미래 비교는 blank paired review를 새로 만들어야 하며 historical score를 재사용할 수 없다.
- `run_guarded_delta_eval.py`, current 23-test suite, README, evaluation CI registration을 구현했다.
  독립 재검토에서 source final binding, HMAC-ranked 11/11 assignment, foreign-key rollback,
  lexical reparse, type exactness, separate key staging을 확인해 actual composition **GO**를
  받았다. 로컬은 22 PASS/1 symlink-privilege SKIP이며 CI 실행은 billing blocked라
  주장하지 않는다.
- production proxy/runtime/director, B4b, TTS/live model, operational ON은 범위 밖이고 모두
  OFF다.
- Commit `4397966` 후 canonical ignored bundle에서 22행을 zero-call compose했다. composition
  자체는 model/network 0회다. 이후 two separate root-spawned model-review session이 immutable
  packet을 검토하고 결과를 잠근 뒤 unblind했다는 절차 진술이 있으나 reviewer identity/
  contract/locked digest를 보존하지 않아 artifact-authenticated review provenance는 아니다. 양쪽 모두 같은
  14행에서 guarded, 같은 6행에서 control을 골랐고 2행은 tie/control로 갈렸다. template
  identity 추론 confidence가 둘 다 high였으므로 이는 완전 blind human review가 아니다.
- act 합의는 thank 3/3, 최초 deescalate 1/1, repair 6/7에서 guarded 우세였지만 correct는
  3/8만 guarded이고 5/8은 실제 correction direction을 담은 historical control이 우세했다.
  fixed generic correction은 정상 발화나 factual correction을 대체하지 않는다.
- 다음 gate는 사용자·fresh human review로 fallback 대상 act를 좁히고, correct에는 validated
  target/direction이 있는 closed contract를 별도로 설계하는 것이다. runtime selection,
  history regeneration, B4b/live path, operational ON은 계속 미완료다.
- 근거: `../완료/AIRI-G1A-GUARDED-DELTA-FOUNDATION-2026-08-17.md`,
  `../완료/AIRI-G1A-GUARDED-DELTA-REVIEW-2026-08-17.md`,
  `../완료/AIRI-G1A-MUST-ACT-REALIZATION-FOUNDATION-2026-08-17.md`,
  `../완료/AIRI-G1A-REPLY-ACT-TRIPLET-2026-08-17.md`

### A5. 표현 계층

- trusted state → ACT/TTS/Live2D mapping
- 표정·음색·발화 문체를 동시에 검수하고 unsupported value fail-closed
- 텍스트 게이트 통과 전 미착수

내부 명칭도 분리한다. reducer 상태는 `affect_label`·`affect_intensity`·
`affect_cause_code`, avatar 출력은 `stage_emotion`, 미래 TTS 입력은 `tts_style`로
구분한다. final `stage_emotion`과 명시적 neutral/reset 정책이 있어야 audible ACK
표정이 다음 발화 뒤에도 남는 문제를 피할 수 있다.

### A6. 비공개 장시간 리허설

- B1b/B4b가 실제 연결된 뒤 승인된 30~120분 흐름으로 OFF/ON paired replay
- 실제 설치 AIRI→11435→TTS 경로 증거
- 사용자 판단 뒤에만 운영 ON 채택

## 10. 테스트와 완료 조건

### 10.1 필수 자동 테스트

- 모든 enum/범위/unknown key/boolean-as-int/Unicode·size 경계
- 같은 `(state,event)`의 byte-identical 결과
- saturation, one-step limit, hysteresis, turn/silence decay, repair/recovery
- safety override가 모든 character drive보다 우선
- raw text/name/provider ID/amount가 event·snapshot·health·report에 없음
- session cap, ring cap, eviction, restart reset
- 기능 OFF일 때 prompt/body bytes 동일
- tail injection 크기와 immutable prompt/KV prefix 불변
- streaming/non-streaming 모두 기존 style/safety boundary 통과
- B4 typed event source spoof/replay/out-of-order 거부
- 144-turn fixture의 동일 sampled seq·OFF/ON profile binding
- 기존 core Python/Node/checkpoint 회귀

### 10.2 G1a 완료 조건

다음이 모두 충족돼야 `[x]`로 바꾼다.

1. 사용자가 constitution v2와 state/event 계약·metric threshold를 승인한다.
2. A1~A4 구현·offline tests와 독립 검토가 통과한다.
3. 기본 OFF와 OFF prompt byte identity가 증명된다.
4. synthetic 144-turn Mi:dm OFF/ON에서 critical 0 및 승인 threshold를 통과한다.
5. blind human review가 “긍정 표현만 다양화”가 아니라 원인·연속성·캐릭터
   차이를 확인한다.
6. 운영 ON은 별도 사용자 결정으로 남긴다.

A5/A6은 G1a core 완료 뒤의 방송 실증 단계다. B1b·B4b·TTS가 준비되지 않았다는
이유로 reducer와 합성 평가의 완료를 막지는 않지만, **라이브 방송에서 검증됨**이라고
표현해서는 안 된다.

## 11. 롤백·위험 관리

- `AIRI_AFFECT_CONTINUITY_ENABLED=off` 하나로 현재 prompt/body와 상태 업데이트
  경로로 복귀한다.
- 1차 상태는 in-memory라 migration/삭제 작업이 없다.
- reducer bug는 event replay로 재현하고 model prompt tuning으로 숨기지 않는다.
- 낮은 valence를 캐릭터성으로 오인해 공격성·무례함을 늘리지 않는다.
- 감정 라벨 수를 늘리는 것보다 원인·관성·회복·drive 검증을 우선한다.
- Mi:dm이 compact state를 안정적으로 따르지 못하면 schema를 늘리지 않고 발화
  policy/director 제약 또는 G3 데이터 승격을 검토한다.
- external project의 activity/star 수는 품질 보증이 아니다. 코드 복사 시점에
  license와 exact revision을 다시 검토한다.

## 12. 로드맵 의존성

```text
G1a A0 (사용자 결정)
  -> A1 pure reducer
  -> A2 proxy greybox OFF
  -> A3 B4 typed event source
  -> A4 synthetic 144-turn OFF/ON + human review
  -> G1a core 완료
  -> A5 TTS/Live2D
  -> B1b/B4b + A6 private long rehearsal
  -> 사용자 운영 ON 결정
```

- C1: constitution v2가 appraisal의 의미를 정한다.
- C2/G1: 기존 상태 주입을 typed snapshot으로 확장한다.
- C5/G3: 캐릭터 변경 회귀와 human review를 제공한다.
- G5/B4: 방송 사건의 authoritative source다.
- I2: 개인별 관계/장기 기억은 별도이며 G1a가 대신하지 않는다.
- G4/C축: fine-tuning은 G1a 평가 데이터가 축적된 뒤에도 별도 승격 게이트를 거친다.

## 13. 이번 문서의 결정 상태

- 확정: 공개 프로젝트를 통째로 도입하지 않고 AIRI 전용 bounded reducer를 만든다.
- 확정: 초기 구현은 새 외부 의존성·네트워크·DB 없이 기본 OFF다.
- 확정: 정서 상태와 시청자 개인정보/장기 관계를 분리한다.
- 사용자 승인 대기: AIRI의 구체적 likes/dislikes/약점/갈등·회복 방식.
- 사용자 승인 대기: enum·범위·144-turn 시나리오·정량 통과선.
- 사용자 승인 대기: 구현 착수 및 이후 운영 ON.
