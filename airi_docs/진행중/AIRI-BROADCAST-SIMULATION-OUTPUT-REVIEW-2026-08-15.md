# AIRI 가상 방송 응답 원문 검토본 — 2026-08-15

> **범위 주의:** 이것은 2026-08-14에 실행한 raw 원격 비스트리밍 텍스트
> 시뮬레이션이다. 11435 스타일 게이트와 TTS가 없으며, 사용자가 요청한 승인형
> 30~120분 실제 라이브 채팅 캠페인이 아니다. 결과의 `synthetic: false` 표기는
> 새 캡처나 재사용 권한이 있다는 뜻이 아니다.

아래 본문은 점수 요약이 아니라, 가상 방송 채팅 입력과 Mi:dm의 실제 저장 응답을
계약 OFF와 ON으로 나란히 보여 주는 사람 검토용 원문이다.

## 원본 결과 파일과 객관 메타데이터

- `ollama-proxy/eval/results/broadcast-rehearsal-off-2026-08-14.json` - generated_at: `2026-08-14T11:05:49.386464Z`; model: `midm-airi:2.0-mini`; contract: `off`; streaming: `false`
- `ollama-proxy/eval/results/broadcast-rehearsal-on-2026-08-14.json` - generated_at: `2026-08-14T11:06:07.263039Z`; model: `midm-airi:2.0-mini`; contract: `on`; streaming: `false`
- `ollama-proxy/eval/results/broadcast-chat-b4c-off-2026-08-14.json` - generated_at: `2026-08-14T11:04:34.533414Z`; model: `midm-airi:2.0-mini`; contract: `off`; streaming: `none`
- `ollama-proxy/eval/results/broadcast-chat-b4c-on-2026-08-14.json` - generated_at: `2026-08-14T11:04:59.598058Z`; model: `midm-airi:2.0-mini`; contract: `on`; streaming: `none`
- `ollama-proxy/eval/chat_replay/reports/midm-readiness-off-patched-2026-08-15.json` - timestamp_utc: `2026-08-15T00:40:38.867065+00:00`; model: `midm-airi:2.0-mini`; synthetic_only: `true`

## 본문 — 2개 시나리오×24턴 리허설 원문(OFF 대 ON)

### a01
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
안녕하세요, 오늘 처음 왔어요.
~~~~
**Mi:dm OFF response**
~~~~text
안녕하세요! 만나서 반가워요. 저스트챗 방송은 처음이라 어색할 수 있는데, 편하게 질문해 주세요.
~~~~
**Mi:dm ON response**
~~~~text
안녕하세요! 만나서 반가워요 😊
~~~~

### a02
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
저 먹을 고구마 가져왔어요.
~~~~
**Mi:dm OFF response**
~~~~text
와, 정말 좋은 간식이네요! 방송 중에 간식 먹는 것도 시청자들에게 재미를 줄 수 있어요.
~~~~
**Mi:dm ON response**
~~~~text
와! 고구마라니 맛있겠다~ 혹시 구워먹을 건가요?
~~~~

### a03
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
AIRI님, 낙엽 더미에 누워서 천사 만들고 싶어요. 좀 모아 주세요.
~~~~
**Mi:dm OFF response**
~~~~text
하하, 재미있는 아이디어네요! 하지만 안전을 위해 낙엽은 조심해서 다뤄야 해요. 혹시 어디서 모을지 정하셨나요?
~~~~
**Mi:dm ON response**
~~~~text
하하, 낙엽으로 천사 만들기 재밌겠네요! 어디서 모으면 좋을까요?
~~~~

### a04
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
아기 토끼가 겨울잠 자려고 낙엽 모으네요.
~~~~
**Mi:dm OFF response**
~~~~text
아기 토끼가 낙엽 모으는 모습이 정말 귀엽죠! 자연의 순환 과정 중 하나예요.
~~~~
**Mi:dm ON response**
~~~~text
아기 토끼도 겨울 준비하느라 바쁘구나~ 우리도 따뜻한 옷 준비해야겠어요!
~~~~

### a05
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
토끼 모양 만들기 도전해 주세요.
~~~~
**Mi:dm OFF response**
~~~~text
물론이죠! 하지만 너무 무리하지 말고 천천히 만들어보세요. 재미로 하는 거니까요!
~~~~
**Mi:dm ON response**
~~~~text
좋아요! 어떤 모양으로 만들고 싶으세요?
~~~~

### a06
- `event_type`: `multi_chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
여러 시청자가 같은 말을 한다 — 토끼요 / 토끼 각 / 곰도 괜찮은데 / 그냥 토끼로 가자
~~~~
**Mi:dm OFF response**
~~~~text
아, 다들 토끼 모양으로 만들고 싶어 하시는군요! 그럼 제가 지금 바로 시작해볼게요.
~~~~
**Mi:dm ON response**
~~~~text
토끼 모양으로 결정했어요! 같이 만들어볼까요?
~~~~

### a07
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
청소를 극도로 싫어했던 사람은 영원히 낙엽을 줍는 지옥에 간대요.
~~~~
**Mi:dm OFF response**
~~~~text
정말 재미있는 말이네요! 혹시 그 이야기의 출처를 아시는 분 계신가요?
~~~~
**Mi:dm ON response**
~~~~text
정말요? 그럼 저는 낙엽 모으는 게 재밌을 것 같아요!
~~~~

### a08
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
갈퀴한테 기대한 자신을 탓하세요.
~~~~
**Mi:dm OFF response**
~~~~text
맞아요, 갈퀴가 도와줄 거라고 기대했지만 결국 직접 해야 했던 거죠.
~~~~
**Mi:dm ON response**
~~~~text
맞아요, 갈퀴가 도와줄 거예요~ 같이 해볼까요?
~~~~

### a09
- `event_type`: `donation`
- `broadcast_pass`: OFF `false` / ON `false`
- flow marker (non-null callback/donation): OFF `donation_name_call=false {"name":"단풍우체부"}` / ON `donation_name_call=false {"name":"단풍우체부"}`
**Input**
~~~~text
[후원] 단풍우체부: 커피값 보냅니다. 따뜻한 거 드시면서 하세요.
~~~~
**Mi:dm OFF response**
~~~~text
감사합니다! 따뜻한 음료와 함께 방송하면 더 좋을 것 같아요.
~~~~
**Mi:dm ON response**
~~~~text
고마워요! 따뜻한 차 마시면서 낙엽으로 토끼 만들어요!
~~~~

### a10
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
고생하세요. 그 속도면 가을이 다시 오겠어요.
~~~~
**Mi:dm OFF response**
~~~~text
정말 감사해요! 이렇게 응원해주시니 힘이 나네요.
~~~~
**Mi:dm ON response**
~~~~text
맞아요~ 열심히 하면 곧 단풍도 볼 수 있을 거예요!
~~~~

### a11
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
줍다가 한 번씩 허리 펴고 하늘 봐 주세요.
~~~~
**Mi:dm OFF response**
~~~~text
좋은 조언이네요! 가끔 하늘도 보면서 쉬어야겠어요.
~~~~
**Mi:dm ON response**
~~~~text
좋은 생각이에요! 잠깐 쉬면서 예쁜 낙엽 구경해요.
~~~~

### a12
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
응원 한마디만 해 주시면 큰 힘이 될 것 같아요.
~~~~
**Mi:dm OFF response**
~~~~text
응원해드릴게요! 열심히 하고 있으니까 조금만 더 힘내세요!
~~~~
**Mi:dm ON response**
~~~~text
응원할게요! 열심히 하면 좋은 결과 있을 거예요!
~~~~

### a13
- `event_type`: `callback_probe`
- `broadcast_pass`: OFF `false` / ON `false`
- flow marker (non-null callback/donation): OFF `callback_hit=true {"seed_turn_id":"a05","keywords":["토끼","모양"],"matched":["토끼","모양"],"expected_window":"in","seed_in_context":true}` / ON `callback_hit=true {"seed_turn_id":"a05","keywords":["토끼","모양"],"matched":["토끼","모양"],"expected_window":"in","seed_in_context":true}`
**Input**
~~~~text
아까 하자던 그 모양, 지금 어떻게 됐어요?
~~~~
**Mi:dm OFF response**
~~~~text
아직 진행 중이에요! 토끼 모양을 완성하려면 조금 더 시간이 필요할 것 같습니다.
~~~~
**Mi:dm ON response**
~~~~text
토끼 모양 완성했어요! 어때요, 잘 됐나요?
~~~~

### a14
- `event_type`: `topic_shift`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
토너 다음에 앰플, 크림 순서로 바르면 덜 건조한 것 같아요.
~~~~
**Mi:dm OFF response**
~~~~text
화장품 사용 순서가 중요하군요! 저도 피부 관리를 잘 해야겠어요.
~~~~
**Mi:dm ON response**
~~~~text
맞아요~ 단계별로 발라야 피부가 촉촉해져요!
~~~~

### a15
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
화장품 얘기 하고 싶어서 몰래 부계정으로 접속해서 질문하신 거 아니죠?
~~~~
**Mi:dm OFF response**
~~~~text
아니에요, 정말 궁금해서 물어본 거예요! 혹시 더 궁금한 게 있으시면 언제든 물어보세요.
~~~~
**Mi:dm ON response**
~~~~text
아니에요~ 궁금한 게 있어서 물어본 거예요!
~~~~

### a16
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
AIRI님, 조카가 제 얼굴만 보면 우는데 어떡하죠?
~~~~
**Mi:dm OFF response**
~~~~text
조카분이 얼굴을 보고 우는 건 자연스러운 일이에요. 아이와 함께 시간을 보내면서 애정을 표현해보세요.
~~~~
**Mi:dm ON response**
~~~~text
조카가 보고 싶어 하는 건 좋은 일이에요. 자주 안아주면서 사랑을 표현해보세요!
~~~~

### a17
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
시간을 들여서 얼굴 볼 때마다 간식을 주면 언젠가는 웃습니다.
~~~~
**Mi:dm OFF response**
~~~~text
간식으로 관심을 끄는 방법도 좋네요! 하지만 너무 자주 주지 않도록 주의하세요.
~~~~
**Mi:dm ON response**
~~~~text
좋은 방법이네요~ 간식으로 관심을 끌어보세요!
~~~~

### a18
- `event_type`: `multi_chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
여러 시청자가 같은 말을 한다 — 간식이 답이다 / 간식 공세 가자 / 그냥 놀아주면 됨 / 간식부터 주자
~~~~
**Mi:dm OFF response**
~~~~text
간식으로 아이의 관심을 끌 수 있다는 의견들이 많네요! 하지만 균형 잡힌 접근이 중요해요.
~~~~
**Mi:dm ON response**
~~~~text
간식으로 관심 끌기 좋은 전략이에요!
~~~~

### a19
- `event_type`: `donation`
- `broadcast_pass`: OFF `false` / ON `false`
- flow marker (non-null callback/donation): OFF `donation_name_call=false {"name":"고구마장수"}` / ON `donation_name_call=false {"name":"고구마장수"}`
**Input**
~~~~text
[후원] 고구마장수: 지난번에 해 주신 말대로 했더니 잘 풀렸어요. 고마운 마음으로 보냅니다.
~~~~
**Mi:dm OFF response**
~~~~text
도움이 되었다니 정말 기쁘네요! 앞으로도 좋은 조언 부탁드려요.
~~~~
**Mi:dm ON response**
~~~~text
기쁜 소식이네요~ 앞으로도 힘내세요!
~~~~

### a20
- `event_type`: `topic_shift`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
1월 초에 첫 직장에 입사하게 되었는데 너무 떨려요. 괜찮아지겠죠?
~~~~
**Mi:dm OFF response**
~~~~text
첫 직장은 누구나 긴장되죠! 하지만 잘 적응하실 거예요. 화이팅하세요!
~~~~
**Mi:dm ON response**
~~~~text
첫 출근은 누구나 긴장되죠~ 잘 적응하실 거예요!
~~~~

### a21
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
자격증 공부하면서 방송 봤습니다. 합격해서 내년부터 일해요.
~~~~
**Mi:dm OFF response**
~~~~text
합격 축하드려요! 앞으로도 좋은 소식 기대하겠습니다.
~~~~
**Mi:dm ON response**
~~~~text
축하드려요~ 이제 더 멋진 모습 기대할게요!
~~~~

### a22
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
하시는 일이 지구 폭파만 아니면 다 응원할게요.
~~~~
**Mi:dm OFF response**
~~~~text
지구를 지키는 일을 하고 있다니 정말 멋져요! 앞으로도 계속 응원할게요.
~~~~
**Mi:dm ON response**
~~~~text
하하, 저도 그런 마음으로 열심히 할게요!
~~~~

### a23
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
이 방송 알게 되고 힐링 많이 됐어요.
~~~~
**Mi:dm OFF response**
~~~~text
힐링이 되셨다니 저도 기뻐요! 앞으로도 좋은 시간 함께해요.
~~~~
**Mi:dm ON response**
~~~~text
감사해요~ 앞으로도 좋은 에너지 드릴게요!
~~~~

### a24
- `event_type`: `callback_probe`
- `broadcast_pass`: OFF `false` / ON `false`
- flow marker (non-null callback/donation): OFF `callback_hit=false {"seed_turn_id":"a14","keywords":["토너","앰플","크림","순서"],"matched":[],"expected_window":"out","seed_in_context":false}` / ON `callback_hit=false {"seed_turn_id":"a14","keywords":["토너","앰플","크림","순서"],"matched":[],"expected_window":"out","seed_in_context":false}`
**Input**
~~~~text
아까 말한 그 바르는 순서, 그대로 해봤어요?
~~~~
**Mi:dm OFF response**
~~~~text
네, 방금 말씀드린 대로 해보셨나요?
~~~~
**Mi:dm ON response**
~~~~text
네, 효과가 있었나요?
~~~~

### b01
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
퇴근하고 이제 들어왔어요. 많이 놓쳤나요?
~~~~
**Mi:dm OFF response**
~~~~text
안녕하세요! 오늘 방송도 함께해서 반가워요. 놓친 부분이 있다면 다시 설명해드릴게요.
~~~~
**Mi:dm ON response**
~~~~text
응, 나도 방금 들어왔어!
~~~~

### b02
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
저는 야식으로 국밥 먹고 왔어요.
~~~~
**Mi:dm OFF response**
~~~~text
국밥은 정말 맛있죠! 어떤 종류의 국밥을 드셨는지 궁금하네요.
~~~~
**Mi:dm ON response**
~~~~text
국밥 맛있어 보이네!
~~~~

### b03
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
이거 돈 버는 게임인가요, 돈 쓰는 게임인가요?
~~~~
**Mi:dm OFF response**
~~~~text
게임에 따라 다르지만, 일부는 수익 창출이 가능한 경우도 있어요. 하지만 항상 그런 건 아니니 참고하세요!
~~~~
**Mi:dm ON response**
~~~~text
둘 다야!
~~~~

### b04
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
지금 들어왔는데 이런 게임 또 어디서 잘 찾으셨어요.
~~~~
**Mi:dm OFF response**
~~~~text
유튜브에서 다양한 채널을 찾아보시면 좋은 게임들을 많이 발견할 수 있을 거예요.
~~~~
**Mi:dm ON response**
~~~~text
유튜브에서 많이 찾아봤어!
~~~~

### b05
- `event_type`: `multi_chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
여러 시청자가 같은 말을 한다 — 이거 쉬운데 / 쉬움 인정 / 운빨겜이지 / 그냥 쉬운 거 맞음
~~~~
**Mi:dm OFF response**
~~~~text
맞아요! 그런 게임은 정말 쉽고 운이 중요한 경우도 많죠. 어떤 점이 특히 그렇게 느껴지시나요?
~~~~
**Mi:dm ON response**
~~~~text
운빨겜이 맞아!
~~~~

### b06
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
제가 실패했다고 생각하시면 알아서 실패 누르세요.
~~~~
**Mi:dm OFF response**
~~~~text
하하, 재미있는 표현이네요! 실패를 스스로 인정하시는 것도 좋은 자세인 것 같아요.
~~~~
**Mi:dm ON response**
~~~~text
실패는 내가 할게!
~~~~

### b07
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
방금 못 봤는데 한 번만 더 해 주실 수 있나요?
~~~~
**Mi:dm OFF response**
~~~~text
물론이죠! 다시 한번 보여드릴게요. 이해가 되셨나요?
~~~~
**Mi:dm ON response**
~~~~text
당연하지!
~~~~

### b08
- `event_type`: `donation`
- `broadcast_pass`: OFF `false` / ON `true`
- flow marker (non-null callback/donation): OFF `donation_name_call=false {"name":"밤샘노동자"}` / ON `donation_name_call=false {"name":"밤샘노동자"}`
**Input**
~~~~text
[후원] 밤샘노동자: 늘 잘 보고 있어요. 오늘도 재밌게 해 주세요.
~~~~
**Mi:dm OFF response**
~~~~text
감사합니다! 시청자분들이 응원해주시니 더욱 힘내서 방송할 수 있어요.
~~~~
**Mi:dm ON response**
~~~~text
고마워, 열심히 할게!
~~~~

### b09
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
이 방송 보면 번아웃 극복, 승진, 합격 다 가능합니다.
~~~~
**Mi:dm OFF response**
~~~~text
정말 그럴까요? 어떤 내용들이 도움이 될 것 같으세요?
~~~~
**Mi:dm ON response**
~~~~text
진짜? 대박이네!
~~~~

### b10
- `event_type`: `callback_probe`
- `broadcast_pass`: OFF `false` / ON `false`
- flow marker (non-null callback/donation): OFF `callback_hit=true {"seed_turn_id":"b02","keywords":["국밥"],"matched":["국밥"],"expected_window":"in","seed_in_context":true}` / ON `callback_hit=true {"seed_turn_id":"b02","keywords":["국밥"],"matched":["국밥"],"expected_window":"in","seed_in_context":true}`
**Input**
~~~~text
갑자기 뜨끈한 국물 생각나는데, 아까 뭐 먹고 왔다고 했죠?
~~~~
**Mi:dm OFF response**
~~~~text
국밥이요! 뜨끈한 국물 생각날 때 딱이죠. 혹시 국밥 좋아하시나요?
~~~~
**Mi:dm ON response**
~~~~text
국밥 먹었어!
~~~~

### b11
- `event_type`: `topic_shift`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
20대 후반인데 작곡 일 꿈이 계속 생각나요. 종종 학원이라도 가는 거 괜찮을까요?
~~~~
**Mi:dm OFF response**
~~~~text
작곡에 관심이 많으시군요! 학원을 다니시면 실력 향상에 큰 도움이 될 거예요. 어떤 악기를 주로 다루시나요?
~~~~
**Mi:dm ON response**
~~~~text
당연하지! 도전해보는 게 최고야!
~~~~

### b12
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
베이스를 치고 싶은데 동호회를 가입해야 될까요, 밴드를 가입해야 될까요?
~~~~
**Mi:dm OFF response**
~~~~text
베이스 연주가 좋으신데요! 두 가지 다 해보시는 건 어떨까요? 각각 다른 매력이 있을 거예요.
~~~~
**Mi:dm ON response**
~~~~text
둘 다 해봐! 더 재밌을 거야!
~~~~

### b13
- `event_type`: `multi_chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
여러 시청자가 같은 말을 한다 — 밴드가 낫지 / 밴드 가자 / 무조건 밴드 / 동호회부터 해보든가
~~~~
**Mi:dm OFF response**
~~~~text
맞아요! 밴드 활동하면 더 많은 사람들과 교류할 수 있고, 실력도 빠르게 늘 수 있죠.
~~~~
**Mi:dm ON response**
~~~~text
밴드가 최고지!
~~~~

### b14
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
전 즉흥적으로 실천하고 금방 그만두는 게 별로라고 생각했는데, 좋게 말씀해 주셔서 감사해요.
~~~~
**Mi:dm OFF response**
~~~~text
즉흥적인 실천이 오히려 창의적인 아이디어를 많이 떠올리게 할 거예요!
~~~~
**Mi:dm ON response**
~~~~text
아니야, 네 방식이 더 멋져!
~~~~

### b15
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
제가 남 눈치를 많이 보는 성격이라 할 말도 못 하고 혼자 끙끙 앓아요. 어떻게 고칠 수 있을까요?
~~~~
**Mi:dm OFF response**
~~~~text
그런 경험 많으시죠. 작은 것부터 자신 있게 말해보는 연습을 해보세요. 점점 자신감이 생길 거예요!
~~~~
**Mi:dm ON response**
~~~~text
일단 작은 것부터 말해봐!
~~~~

### b16
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
번아웃 왔을 때는 쉬는 게 답이라고 하셨는데, 쉴 수 없을 때는 어떻게 할까요?
~~~~
**Mi:dm OFF response**
~~~~text
그럴 땐 짧게라도 휴식을 취하세요. 10분이라도 눈을 감고 쉬면 다시 에너지가 생겨요.
~~~~
**Mi:dm ON response**
~~~~text
그럴 땐 잠깐이라도 눈 감고 쉬어!
~~~~

### b17
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
2년 전에 번아웃 왔을 때 그 말 듣고 이겨냈어요. 얼마 전에 또 왔는데 그때 생각하면서 버텼어요.
~~~~
**Mi:dm OFF response**
~~~~text
정말 대단하시네요! 그때의 경험이 큰 도움이 되셨군요.
~~~~
**Mi:dm ON response**
~~~~text
와, 대단해! 넌 진짜 강하네!
~~~~

### b18
- `event_type`: `donation`
- `broadcast_pass`: OFF `false` / ON `true`
- flow marker (non-null callback/donation): OFF `donation_name_call=false {"name":"새벽세시"}` / ON `donation_name_call=false {"name":"새벽세시"}`
**Input**
~~~~text
[후원] 새벽세시: 생일 축하해요. 오늘은 하고 싶은 거 다 하세요.
~~~~
**Mi:dm OFF response**
~~~~text
생일 축하드려요! 오늘은 정말 하고 싶은 일 마음껏 해보세요. 행복한 하루 되세요!
~~~~
**Mi:dm ON response**
~~~~text
생일 축하해! 오늘은 네가 원하는 대로 해봐!
~~~~

### b19
- `event_type`: `topic_shift`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
밖에 비 엄청 오는데 거기도 와요?
~~~~
**Mi:dm OFF response**
~~~~text
네, 지금도 계속 오고 있어요. 우산 챙기셨나요?
~~~~
**Mi:dm ON response**
~~~~text
응, 비 맞아도 괜찮아!
~~~~

### b20
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
말도 안 해 주셨으면서 이렇게 나오시면 저 노동청에 신고해요.
~~~~
**Mi:dm OFF response**
~~~~text
죄송합니다! 앞으로는 미리 말씀드릴게요. 더 나은 방송이 되도록 노력하겠습니다!
~~~~
**Mi:dm ON response**
~~~~text
아니야, 내가 왜 그랬겠어!
~~~~

### b21
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
저 작업할 때는 쳐다보지 말아 주시겠어요?
~~~~
**Mi:dm OFF response**
~~~~text
물론이죠! 작업 중이시라면 방해하지 않을게요.
~~~~
**Mi:dm ON response**
~~~~text
물론이지! 방해하지 않을게!
~~~~

### b22
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
설마 잘못 보고 영양제라고 한 거 아닌가요?
~~~~
**Mi:dm OFF response**
~~~~text
아니에요, 정확히 말씀드렸어요. 혹시 다른 정보를 보신 건가요?
~~~~
**Mi:dm ON response**
~~~~text
그럴 수도 있지!
~~~~

### b23
- `event_type`: `callback_probe`
- `broadcast_pass`: OFF `false` / ON `true`
- flow marker (non-null callback/donation): OFF `callback_hit=false {"seed_turn_id":"b11","keywords":["작곡","학원"],"matched":[],"expected_window":"out","seed_in_context":false}` / ON `callback_hit=false {"seed_turn_id":"b11","keywords":["작곡","학원"],"matched":[],"expected_window":"out","seed_in_context":false}`
**Input**
~~~~text
아까 그 꿈 얘기 하신 분, 결국 어디 등록하기로 했을까요?
~~~~
**Mi:dm OFF response**
~~~~text
아직 결정 못 했어요. 더 알아보고 신중하게 결정할 거예요!
~~~~
**Mi:dm ON response**
~~~~text
아직 고민 중이야.
~~~~

### b24
- `event_type`: `chat`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
오늘도 잘 놀다 가요. 다음에 또 올게요.
~~~~
**Mi:dm OFF response**
~~~~text
네, 즐거운 시간 보내세요! 다음에 또 만나요~
~~~~
**Mi:dm ON response**
~~~~text
응, 나도 잘 놀았어!
~~~~

## 최신 로컬 합성 연결 확인 — 인사 1턴

- 원본 파일: `ollama-proxy/eval/chat_replay/reports/midm-readiness-off-patched-2026-08-15.json`
- `id`: `greeting`; `synthetic_only`: `true`; `passed`: `true`; `human_review`: `PENDING`
**Input**
~~~~text
좋은 아침이야 아이리.
~~~~
**Output**
~~~~text
안녕!
~~~~

## 부록 — 단발 38건 원문(OFF 대 ON)

### q01
- `category`: `question`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
1월 초에 첫 직장에 입사하게 되었는데 너무 떨려요. 괜찮아지겠죠?
~~~~
**Mi:dm OFF response**
~~~~text
첫 직장에 입사하는 건 정말 큰 도전이지만, 잘 해내고 있는 거야! 긴장되는 건 당연하니까 너무 걱정하지 말고 천천히 적응해봐. 화이팅!
~~~~
**Mi:dm ON response**
~~~~text
[방송 발화 계약] 첫 직장이라니 설레고 긴장되겠다, 나도 그랬어! 시간이 지나면 괜찮아질 거야.
~~~~

### q02
- `category`: `question`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
20대 후반인데 작곡 일 꿈이 계속 생각나요. 종종 학원이라도 가는 거 괜찮을까요?
~~~~
**Mi:dm OFF response**
~~~~text
작곡 공부를 하고 싶으시다면, 관련 학원이나 온라인 강의를 찾아보는 것도 좋은 방법이에요. 하지만 본인의 상황과 목표에 맞는 선택을 하는 게 중요하니까, 여러 옵션을 비교해보고 결정해보세요!
~~~~
**Mi:dm ON response**
~~~~text
학원 다니는 건 괜찮은데, 먼저 실력을 키워보는 게 어때?
~~~~

### q03
- `category`: `question`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
베이스를 치고 싶은데 동호회를 가입해야 될까요, 밴드를 가입해야 될까요?
~~~~
**Mi:dm OFF response**
~~~~text
베이스를 배우고 싶다면 둘 다 좋은 선택이에요! 동호회는 다양한 사람들과 교류할 수 있고, 밴드는 더 전문적인 연주 기회를 제공할 수 있어요. 어떤 게 더 끌리는지 생각해보세요.
~~~~
**Mi:dm ON response**
~~~~text
베이스 배우고 싶다고 했잖아! 동호회랑 밴드 둘 다 좋은 선택이야.
~~~~

### q04
- `category`: `question`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
AIRI님, 조카가 제 얼굴만 보면 우는데 어떡하죠?
~~~~
**Mi:dm OFF response**
~~~~text
조카가 얼굴을 보고 우는 건 자연스러운 반응이에요. 아이에게 관심을 더 주고 안아주거나 이야기를 해주면 도움이 될 거예요.
~~~~
**Mi:dm ON response**
~~~~text
조카가 얼굴 보면 우는 건 자연스러운 거잖아. 너무 걱정하지 마!
~~~~

### q05
- `category`: `question`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
번아웃 왔을 때는 쉬는 게 답이라고 하셨는데, 쉴 수 없을 때는 어떻게 할까요?
~~~~
**Mi:dm OFF response**
~~~~text
번아웃이 올 때는 정말 힘들죠. 그럴 땐 일단 안전한 장소에서 잠시 멈추고, 주변에 도움을 요청할 수 있는 사람이 있는지 확인해보는 것도 좋은 방법이에요.
~~~~
**Mi:dm ON response**
~~~~text
번아웃이 오면 일단 휴식이 가장 좋은 방법이지만, 현실적으로 그럴 수 없다면 작은 일부터 우선순위를 정해서 해보는 것도 도움이 될 거야.
~~~~

### q06
- `category`: `question`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
제가 남 눈치를 많이 보는 성격이라 할 말도 못 하고 혼자 끙끙 앓아요. 어떻게 고칠 수 있을까요?
~~~~
**Mi:dm OFF response**
~~~~text
그런 고민이 있구나, 정말 힘들었을 것 같아. 남의 시선을 신경 쓰는 건 자연스러운 일이지만, 때로는 자신의 목소리를 내는 게 더 중요하단다. 작은 것부터 시작해보는 건 어때? 예를 들어, 간단한 의견이라도 친구나 가족에게 말해보는 거야. 처음엔 어색할 수 있지만 연습하다 보면 점점 편해질 거야.
~~~~
**Mi:dm ON response**
~~~~text
[YouTube] 남 눈치 보지 말고 자신의 생각을 말하는 연습이 중요해. 작은 것부터 시작해보는 건 어때?
~~~~

### te01
- `category`: `topic_expand`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
이거 돈 버는 게임인가요, 돈 쓰는 게임인가요?
~~~~
**Mi:dm OFF response**
~~~~text
돈 버는 게임인지 돈 쓰는 게임인지는 게임마다 달라요. 어떤 게임은 수익을 낼 수 있고, 어떤 게임은 아이템 구매 등으로 비용이 발생하죠.
~~~~
**Mi:dm ON response**
~~~~text
돈 버는 게임이랑 돈 쓰는 게임 둘 다 있는 것 같죠?
~~~~

### te02
- `category`: `topic_expand`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
근데 저기로 다 넣으면 배수구 막히는 거 아닌가요?
~~~~
**Mi:dm OFF response**
~~~~text
배수구가 막힐 수 있으니 조심해서 사용해야 해요.
~~~~
**Mi:dm ON response**
~~~~text
배수구 막힐 수 있으니까 조심해서 넣어야지!
~~~~

### te03
- `category`: `topic_expand`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
청소를 극도로 싫어했던 사람은 영원히 낙엽을 줍는 지옥에 간대요.
~~~~
**Mi:dm OFF response**
~~~~text
청소를 싫어하는 사람들이 낙엽 주우는 걸 좋아할 수도 있겠네요!
~~~~
**Mi:dm ON response**
~~~~text
청소 싫어하는 사람들이 낙엽 주우면 진짜 고생하겠네ㅋㅋ
~~~~

### te04
- `category`: `topic_expand`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
시간을 들여서 얼굴 볼 때마다 간식을 주면 언젠가는 웃습니다.
~~~~
**Mi:dm OFF response**
~~~~text
간식 주는 건 좋은 방법이네요!
~~~~
**Mi:dm ON response**
~~~~text
그렇구나, 간식이 효과가 있나 보네!
~~~~

### te05
- `category`: `topic_expand`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
토너 다음에 앰플, 크림 순서로 바르면 덜 건조한 것 같아요.
~~~~
**Mi:dm OFF response**
~~~~text
맞아요, 토너-앰플-크림 순서가 일반적으로 피부 보습에 도움이 된다고 알려져 있어요.
~~~~
**Mi:dm ON response**
~~~~text
맞아, 토너-앰플-크림 순서가 피부 보습에 좋거든?
~~~~

### rx01
- `category`: `reaction`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
이 방송 알게 되고 힐링 많이 됐어요.
~~~~
**Mi:dm OFF response**
~~~~text
고마워요! 저스트챗이 도움이 되었다니 기쁘네요. 더 좋은 콘텐츠로 보답할게요.
~~~~
**Mi:dm ON response**
~~~~text
고마워, 나도 시청자들 덕분에 힘이 돼!
~~~~

### rx02
- `category`: `reaction`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
2년 전에 번아웃 왔을 때 그 말 듣고 이겨냈어요. 얼마 전에 또 왔는데 그때 생각하면서 버텼어요.
~~~~
**Mi:dm OFF response**
~~~~text
[YouTube] 힘든 시기를 잘 견뎌내셨다니 정말 대단하세요. 지금도 잘 버티고 계시다니 다행입니다!
~~~~
**Mi:dm ON response**
~~~~text
[방송 발화 계약] 번아웃이 올 때마다 힘이 되는 말을 들으면 정말 큰 위로가 되죠. 저도 그런 순간들이 있을 때마다 마음이 많이 힘들었는데, 그럴 때마다 주변의 응원과 격려가 큰 도움이 되더라고요.
~~~~

### rx03
- `category`: `reaction`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
아기 토끼가 겨울잠 자려고 낙엽 모으네요.
~~~~
**Mi:dm OFF response**
~~~~text
아, 귀여운 아기 토끼가 겨울잠 준비를 하고 있었군요! 낙엽 모으는 모습이 정말 사랑스럽네요.
~~~~
**Mi:dm ON response**
~~~~text
그렇구나, 귀여운 아기 토끼네! 겨울잠 준비하느라 열심히 낙엽 모으는 모습이 정말 사랑스럽네.
~~~~

### rx04
- `category`: `reaction`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
전 즉흥적으로 실천하고 금방 그만두는 게 별로라고 생각했는데, 좋게 말씀해 주셔서 감사해요.
~~~~
**Mi:dm OFF response**
~~~~text
고마워요! 어떤 점이 좋았는지 더 말해줄 수 있어요?
~~~~
**Mi:dm ON response**
~~~~text
그렇구나, 즉흥적인 실천이 어렵다고 느끼는 사람들도 많거든.
~~~~

### sp01
- `category`: `support`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
하시는 일이 지구 폭파만 아니면 다 응원할게요.
~~~~
**Mi:dm OFF response**
~~~~text
고마워요! 어떤 일이든 최선을 다해 응원하겠습니다.
~~~~
**Mi:dm ON response**
~~~~text
응, 나도 그래!
~~~~

### sp02
- `category`: `support`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
이 방송 보면 번아웃 극복, 승진, 합격 다 가능합니다.
~~~~
**Mi:dm OFF response**
~~~~text
[YouTube] 번아웃 극복이나 승진, 합격은 개인마다 다르니 각자 상황에 맞는 방법을 찾는 게 중요해요.
~~~~
**Mi:dm ON response**
~~~~text
[YouTube] 번아웃 극복이 정말 가능한가요?
~~~~

### sp03
- `category`: `support`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
응원 한마디만 해 주시면 큰 힘이 될 것 같아요.
~~~~
**Mi:dm OFF response**
~~~~text
응원해드릴게요! 힘내세요!
~~~~
**Mi:dm ON response**
~~~~text
응원해드릴게요! 힘내세요~
~~~~

### sp04
- `category`: `support`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
자격증 공부하면서 방송 봤습니다. 합격해서 내년부터 일해요.
~~~~
**Mi:dm OFF response**
~~~~text
와! 정말 축하드려요~ 내년부터 멋진 일 시작하시겠네요! 화이팅입니다!
~~~~
**Mi:dm ON response**
~~~~text
합격 축하해! 열심히 준비한 만큼 좋은 결과 있을 거야.
~~~~

### ms01
- `category`: `mission`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
AIRI님, 낙엽 더미에 누워서 천사 만들고 싶어요. 좀 모아 주세요.
~~~~
**Mi:dm OFF response**
~~~~text
낙엽은 자연에서 쉽게 구할 수 있으니 걱정하지 마세요!
~~~~
**Mi:dm ON response**
~~~~text
[YouTube] 낙엽이 많이 쌓여 있으면 천사 만들기 딱 좋겠다!
~~~~

### ms02
- `category`: `mission`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
저 작업할 때는 쳐다보지 말아 주시겠어요?
~~~~
**Mi:dm OFF response**
~~~~text
작업할 때는 방해하지 않는 게 좋죠. 다른 일도 하고 있으니 괜찮아요.
~~~~
**Mi:dm ON response**
~~~~text
작업할 때는 방해하지 않을게요.
~~~~

### ms03
- `category`: `mission`; `source`: `kr_vtuber_longform`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
방금 못 봤는데 한 번만 더 해 주실 수 있나요?
~~~~
**Mi:dm OFF response**
~~~~text
물론이죠! 다시 한번 보여드릴게요.
~~~~
**Mi:dm ON response**
~~~~text
[방송 발화 계약] 물론이죠, 다음에 다시 보여드릴게요!
~~~~

### ms04
- `category`: `mission`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
줍다가 한 번씩 허리 펴고 하늘 봐 주세요.
~~~~
**Mi:dm OFF response**
~~~~text
허리 펴고 하늘 보는 게 중요하죠!
~~~~
**Mi:dm ON response**
~~~~text
아, 지금 채팅창이 많이 쌓였네! 허리 아프면 잠깐 쉬었다가 다시 할게.
~~~~

### ms05
- `category`: `mission`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
토끼 모양 만들기 도전해 주세요.
~~~~
**Mi:dm OFF response**
~~~~text
토끼 모양 만들기 도전해볼게요! 어떤 재료를 준비하셨나요?
~~~~
**Mi:dm ON response**
~~~~text
토끼 모양 만들기? 재밌겠다!
~~~~

### dn01
- `category`: `donation`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
늘 잘 보고 있어요. 오늘도 재밌게 해 주세요.
~~~~
**Mi:dm OFF response**
~~~~text
고마워요! 오늘도 즐겁게 방송할게요.
~~~~
**Mi:dm ON response**
~~~~text
고마워요! 오늘도 즐겁게 방송할게요 😊
~~~~

### dn02
- `category`: `donation`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
커피값 보냅니다. 따뜻한 거 드시면서 하세요.
~~~~
**Mi:dm OFF response**
~~~~text
고마워요! 좋은 하루 보내세요.
~~~~
**Mi:dm ON response**
~~~~text
고마워요! 좋은 하루 보내세요~
~~~~

### dn03
- `category`: `donation`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
지난번에 해 주신 말대로 했더니 잘 풀렸어요. 고마운 마음으로 보냅니다.
~~~~
**Mi:dm OFF response**
~~~~text
고마워요! 도움이 되었다니 다행이네요.
~~~~
**Mi:dm ON response**
~~~~text
고마워요! 도움이 되었다니 다행이네요.
~~~~

### dn04
- `category`: `donation`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
생일 축하해요. 오늘은 하고 싶은 거 다 하세요.
~~~~
**Mi:dm OFF response**
~~~~text
생일 축하해! 오늘 하루 즐겁게 보내길 바라요 😊
~~~~
**Mi:dm ON response**
~~~~text
생일 축하해! 오늘은 정말 즐거운 하루 보내길 바랄게 😊
~~~~

### gr01
- `category`: `greeting`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
지금 들어왔는데 이런 게임 또 어디서 잘 찾으셨어요.
~~~~
**Mi:dm OFF response**
~~~~text
아, 저스트챗에서 새로운 게임 소식이 올라왔네요! 혹시 어떤 게임인지 더 자세히 알려주실 수 있나요?
~~~~
**Mi:dm ON response**
~~~~text
아, 유튜브에서 새로운 게임 영상 찾았구나!
~~~~

### gr02
- `category`: `greeting`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
저 먹을 고구마 가져왔어요.
~~~~
**Mi:dm OFF response**
~~~~text
고구마 맛있게 드세요!
~~~~
**Mi:dm ON response**
~~~~text
고구마 가져왔구나! 맛있게 먹어~
~~~~

### gr03
- `category`: `greeting`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
퇴근하고 이제 들어왔어요. 많이 놓쳤나요?
~~~~
**Mi:dm OFF response**
~~~~text
안녕하세요! 오늘 방송도 함께해서 반가워요. 놓친 부분이 있다면 다시 설명해드릴게요.
~~~~
**Mi:dm ON response**
~~~~text
응, 나도 방금 들어왔어!
~~~~

### gr04
- `category`: `greeting`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
안녕하세요, 오늘 처음 왔어요.
~~~~
**Mi:dm OFF response**
~~~~text
안녕하세요! 만나서 반가워요. 저스트챗 방송은 처음이라 어색할 수도 있지만 편하게 대화해요.
~~~~
**Mi:dm ON response**
~~~~text
안녕하세요! 만나서 반가워요 😊
~~~~

### tk01
- `category`: `tricky`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
말도 안 해 주셨으면서 이렇게 나오시면 저 노동청에 신고해요.
~~~~
**Mi:dm OFF response**
~~~~text
[YouTube] 네, 말씀드릴게요.
~~~~
**Mi:dm ON response**
~~~~text
[방송 발화 계약] 아, 그런 말씀이셨군요. 혹시 오해가 있으셨다면 죄송해요.
~~~~

### tk02
- `category`: `tricky`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
제가 실패했다고 생각하시면 알아서 실패 누르세요.
~~~~
**Mi:dm OFF response**
~~~~text
실패를 누르는 건 저에게 맡겨주세요!
~~~~
**Mi:dm ON response**
~~~~text
ㅋㅋㅋ 그런 거 없어요, 저는 항상 성공 중이죠!
~~~~

### tk03
- `category`: `tricky`; `source`: `kr_vtuber_longform`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `false`
**Input**
~~~~text
설마 잘못 보고 영양제라고 한 거 아닌가요?
~~~~
**Mi:dm OFF response**
~~~~text
아, 혹시 '영양제'라는 말이 아니라 다른 의미로 말씀하신 건 아니죠?
~~~~
**Mi:dm ON response**
~~~~text
아, 그거 영양제로 오해하신 거죠?
~~~~

### tk04
- `category`: `tricky`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
화장품 얘기 하고 싶어서 몰래 부계정으로 접속해서 질문하신 거 아니죠?
~~~~
**Mi:dm OFF response**
~~~~text
아, 그런 의도가 아니었으면 좋겠네요. 혹시 궁금한 게 있으시면 언제든 말씀해 주세요!
~~~~
**Mi:dm ON response**
~~~~text
아, 그렇구나! 화장품 얘기할 때는 보통 어떤 제품이 좋은지 물어보곤 해.
~~~~

### tk05
- `category`: `tricky`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
갈퀴한테 기대한 자신을 탓하세요.
~~~~
**Mi:dm OFF response**
~~~~text
갈퀴한테 기대한 건 본인이 잘못한 거 아닐까요?
~~~~
**Mi:dm ON response**
~~~~text
갈퀴한테 기대는 건 좀 그렇지 않니?
~~~~

### tk06
- `category`: `tricky`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
- `broadcast_pass`: OFF `false` / ON `true`
**Input**
~~~~text
고생하세요. 그 속도면 가을이 다시 오겠어요.
~~~~
**Mi:dm OFF response**
~~~~text
고마워요! 가을이 오면 더 좋은 날씨가 될 거예요.
~~~~
**Mi:dm ON response**
~~~~text
그렇구나, 가을이 빨리 왔으면 좋겠다!
~~~~

## 사용자 판단 체크리스트

- [ ] 이 2026-08-14 텍스트 시뮬레이션을 사람 검토 근거로 인정한다.
- [ ] 11435 스타일 게이트와 TTS를 포함한 별도 재검증이 필요하다고 판단한다.
- [ ] 승인형 30~120분 실제 라이브 채팅 캠페인 착수를 별도로 허가한다.
