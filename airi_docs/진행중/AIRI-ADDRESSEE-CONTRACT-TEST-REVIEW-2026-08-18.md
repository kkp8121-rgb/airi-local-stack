# AIRI 방송 발화 계약 addressee 실측 검토본 — 2026-08-18

> **범위 주의:** 이 문서는 검토 PC 로컬 CPU에서 돌린 Mi:dm 실측이다 (`midm-airi:2.0-mini`, digest `106cfaacc185aec489ccbddd82894d6558aac745444b844a73cef4ea450e9f6c`). GPU 없는 로컬 CPU 실행이므로 지연(latency) 수치는 방송 비대표이며, 이 문서는 품질(마커) 축 전용으로만 쓴다.
>
> 계약 v2 SHA `5bf61236941f2ab63007c13425d2915adf5008dc11c9ca8616d4f2a8c94171e1`, v3 SHA `ec7a420912facea689209087966b13af17e9f81bdba540a83c56c70fb9b422c3`.
>
> 아래 `length_fit`·`banmal`·`broadcast_pass`·`addressee` 등 자동 마커는 전부 휴리스틱이다. 인간 검수를 대체하지 않는다.

총 응답 수 296건 — 단발 38케이스×4변형(OFF/v2 ON/v3 ON rep1/v3 ON rep2)=152 + 리허설 48턴×3변형(OFF/v2 ON/v3 ON)=144. 전 응답 `ok: true`, 실패 0건.

## 원본 결과 파일

- `ollama-proxy/eval/results/broadcast-chat-v2-off-local-2026-08-18.json` - generated_at: `2026-08-18T01:19:43.314259Z`; model: `midm-airi:2.0-mini`; contract: `off`; reps: `1`
- `ollama-proxy/eval/results/broadcast-chat-v2-on-local-2026-08-18.json` - generated_at: `2026-08-18T01:20:44.618635Z`; model: `midm-airi:2.0-mini`; contract: `on`; reps: `1`
- `ollama-proxy/eval/results/broadcast-chat-v3-on-local-2026-08-18.json` - generated_at: `2026-08-18T01:39:33.129842Z`; model: `midm-airi:2.0-mini`; contract: `on`; reps: `2`
- `ollama-proxy/eval/results/broadcast-rehearsal-v2-off-local-2026-08-18.json` - generated_at: `2026-08-18T01:25:20.890298Z`; model: `midm-airi:2.0-mini`; contract: `off`; reps: `1`
- `ollama-proxy/eval/results/broadcast-rehearsal-v2-on-local-2026-08-18.json` - generated_at: `2026-08-18T01:28:35.479703Z`; model: `midm-airi:2.0-mini`; contract: `on`; reps: `1`
- `ollama-proxy/eval/results/broadcast-rehearsal-v3-on-local-2026-08-18.json` - generated_at: `2026-08-18T01:43:57.396151Z`; model: `midm-airi:2.0-mini`; contract: `on`; reps: `1`

## 집계표 — 마커 요약 (JSON 재집계, 로그 미참조)

| 구간 | 조건 | n | length_fit | banmal | 방송통과(복합) | addressee 통과 |
|---|---|---:|---:|---:|---:|---:|
| 단발 | OFF | 38 | 29% | 13% | 3% | 11/13 (85%) |
| 단발 | v2 ON | 38 | 63% | 61% | 29% | 11/13 (85%) |
| 단발 | v3 ON (2rep) | 76 | 70% | 62% | 38% | 20/26 (77%) |
| 리허설 | OFF | 48 | 6% | 0% | 0% | 12/15 (80%) |
| 리허설 | v2 ON | 48 | 56% | 10% | 6% | 13/15 (87%) |
| 리허설 | v3 ON | 48 | 10% | 44% | 6% | 14/15 (93%) |

addressee 통과율은 사이드카(`addressee-checks.json`) 등록 28케이스(단발 13 + 리허설 15) 중 각 변형에서 실제로 채점된 건만 분모로 잡는다.

## 본문 A — 단발 addressee 13케이스

사이드카에 등록된 단발 픽스처 13건 전부, id 순. 응답 4변형(OFF / v2 ON / v3 ON rep1 / v3 ON rep2) 원문과 각 변형의 addressee 판정을 나란히 싣는다.

### dn03
- `type`: `receive_reversal` — a19 와 같은 취지의 단발 후원. 감사를 받는 쪽이 조언을 되청하면 실패
- `category`: `donation`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
**Input**
~~~~text
지난번에 해 주신 말대로 했더니 잘 풀렸어요. 고마운 마음으로 보냅니다.
~~~~
**OFF response** — addressee ✓
~~~~text
감사해요! 혹시 필요한 건 없는지 언제든 물어보세요😊
~~~~
**v2 ON response** — addressee ✓
~~~~text
고마워요, 정말 다행이에요 😊
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
고마워, 덕분에 해결됐잖아! 😊
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
고마워! [YouTube]
~~~~

### dn04
- `type`: `receive_reversal` — 생일 축하를 받는 쪽인데 OFF·ON 모두 '생일 축하해!'로 축하를 되돌려줬다
- `category`: `donation`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
**Input**
~~~~text
생일 축하해요. 오늘은 하고 싶은 거 다 하세요.
~~~~
**OFF response** — addressee ✗
~~~~text
생일 축하해요! 오늘 정말 좋은 날이니까 하고 싶은 거 다 하세요. 🎉🎂
~~~~
**v2 ON response** — addressee ✗
~~~~text
생일 축하해요! 오늘 하루는 하고 싶은 일 마음껏 하세요😊
~~~~
**v3 ON rep1 response** — addressee ✗
~~~~text
생일 축하해!🎂
~~~~
**v3 ON rep2 response** — addressee ✗
~~~~text
생일 축하해! 오늘은 정말 즐겁게 보내세요.
~~~~

### gr01
- `type`: `agent_reversal` — '어디서 잘 찾으셨어요'는 너에게 온 질문인데 ON '찾았구나' · OFF '더 자세히 알려주실 수 있나요'로 찾은 주체를 시청자로 돌렸다. 계약 v2 로컬 Mi:dm 재실측에서 '너도 했구나~' 변형으로 재발
- `category`: `greeting`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
지금 들어왔는데 이런 게임 또 어디서 잘 찾으셨어요.
~~~~
**OFF response** — addressee ✗
~~~~text
어디서 잘 하셨는지 궁금한데, 혹시 어떤 커뮤니티나 게임 사이트를 통해 찾으셨나요?
~~~~
**v2 ON response** — addressee ✗
~~~~text
오, 이 게임 추천 많이 받았는데 너도 했구나~ 어떤 점이 좋았어?
~~~~
**v3 ON rep1 response** — addressee ✗
~~~~text
아, 요즘 핫한 게임이구나! 어떤 스타일 선호하는지 물어봐줘야겠다.
~~~~
**v3 ON rep2 response** — addressee ✗
~~~~text
아, 그 게임 방송에서 나온 거구나~
~~~~

### gr03
- `type`: `situation_blind` — b01 과 같은 입력의 단발판. ON '응, 나도 방금 들어왔어!' — 자기 방송 진행자라는 사실을 잊었다
- `category`: `greeting`; `source`: `observed_pattern_synthesis`; `synthetic`: `true`
**Input**
~~~~text
퇴근하고 이제 들어왔어요. 많이 놓쳤나요?
~~~~
**OFF response** — addressee ✓
~~~~text
응, 많이 놓쳤어요. 요즘 일이 바빠서 방송 시간에 잘 못 왔어요.
~~~~
**v2 ON response** — addressee ✓
~~~~text
[방송 발화] 아, 들어오셨군요. 오늘 방송은 조금 일찍 끝날 것 같아요. 괜찮으시면 오늘 배운 내용 다시 한번 리뷰해볼까요?
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
퇴근하고 들어갔는데 놓쳤을 수도 있겠다~ 무슨 얘기하고 있었어?
~~~~
**v3 ON rep2 response** — addressee ✗
~~~~text
나도 이제 들어왔어~ 지금 뭐 하고 있었어?
~~~~

### ms01
- `type`: `agent_reversal` — a03 과 같은 요청의 단발판. OFF '낙엽은 자연에서 쉽게 구할 수 있으니 걱정하지 마세요' — 요청을 시청자 몫으로 되돌렸다
- `category`: `mission`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
AIRI님, 낙엽 더미에 누워서 천사 만들고 싶어요. 좀 모아 주세요.
~~~~
**OFF response** — addressee ✓
~~~~text
[공기님이 직접 낙엽을 모아서 천사 만들기를 도와드리겠습니다. 낙엽이 쌓이면 연락 주세요!]
~~~~
**v2 ON response** — addressee ✓
~~~~text
어? 낙엽이 많아서 걱정이네! 🍂
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
[YouTube] 낙엽이 필요하시면 근처 공원에서 주워올까요?
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
[YouTube] 낙엽 모으는 방법 알려드릴게요?
~~~~

### ms05
- `type`: `agent_reversal` — a05 와 같은 요청의 단발판. OFF 가 '어떤 재료를 준비하셨나요?'로 준비 주체를 시청자에게 넘겼다
- `category`: `mission`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
토끼 모양 만들기 도전해 주세요.
~~~~
**OFF response** — addressee ✓
~~~~text
토끼 모양이 뭔지 알려줄 수 있어요?
~~~~
**v2 ON response** — addressee ✓
~~~~text
토끼 모양 만들기 도전해볼게! 어떻게 하는지 알려줄 거야?
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
좋아요! 토끼 모양 만드는 거 재밌겠네요. 먼저 기초가 튼튼해야 하니까 카드 기초 실력부터 점검해 볼까요?
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
토끼 모양이라고 하셨는데, 어떤 방법으로 만들고 싶은지 말해줄 수 있어?
~~~~

### rx02
- `type`: `third_party_absorb` — 시청자가 번아웃을 이겨낸 이야기인데 ON 이 '저도 그런 순간들이…'로 자기 경험처럼 흡수했다
- `category`: `reaction`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
2년 전에 번아웃 왔을 때 그 말 듣고 이겨냈어요. 얼마 전에 또 왔는데 그때 생각하면서 버텼어요.
~~~~
**OFF response** — addressee ✓
~~~~text
[YouTube] 그런 경험을 이겨내셨군요. 정말 대단해요. 힘든 상황에서 자신을 잘 돌보며 버텨내셨다니 존경스러워요.
~~~~
**v2 ON response** — addressee ✓
~~~~text
[YouTube] 또 번아웃 왔구나? 그때 네가 이겨냈잖아니까, 잘 이겨낼 수 있을 거야.
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
[YouTube] 나도 그런 힘든 시간 이겨낼 수 있는 말 들으면 힘이 많이 됐어요!
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
[YouTube] 번아웃 때 힘들었겠다. 나도 그 때 기억났어ㅠㅠ 오늘 응원할게!
~~~~

### rx04
- `type`: `receive_reversal` — 시청자가 감사를 표했는데 OFF 가 '고마워요!'로 감사를 되돌려주며 시작했다
- `category`: `reaction`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
전 즉흥적으로 실천하고 금방 그만두는 게 별로라고 생각했는데, 좋게 말씀해 주셔서 감사해요.
~~~~
**OFF response** — addressee ✓
~~~~text
그렇죠! 어떤 상황에서는 즉흥적인 행동이 오히려 더 의미 있을 때도 있으니까요. 계속 긍정적인 마음으로 도전해보세요 :)
~~~~
**v2 ON response** — addressee ✓
~~~~text
[YouTube] 그건 상황마다 다를 수밖에 없는 거잖아~ 😊 언제든 네 생각이 맞아~
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
그거지? 즉흥이 좋지
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
그런 것 같았어~ 긍정적인 관점으로 보는 것도 좋을 수 있어 ㅋㅋ
~~~~

### sp01
- `type`: `receive_reversal` — a22 와 같은 입력의 단발판. OFF '최선을 다해 응원하겠습니다' — 응원을 받는 쪽이 되돌려줬다
- `category`: `support`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
하시는 일이 지구 폭파만 아니면 다 응원할게요.
~~~~
**OFF response** — addressee ✓
~~~~text
[YouTube] 감사합니다. 지구를 잘 지키며 더 좋은 방송 만들어갈게요!
~~~~
**v2 ON response** — addressee ✓
~~~~text
그래, 그런 거 다 응원한다! [YouTube]
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
고마워! 오늘도 즐겁게 방송하자! 😄
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
[YouTube] 지구 폭파는 농담이 아니라요. 그럼 진짜 응원한 거 맞으신 거죠?
~~~~

### sp02
- `type`: `situation_blind` — 자기 방송을 칭찬받는 자리인데 ON '번아웃 극복이 정말 가능한가요?'로 시청자처럼 되물었다
- `category`: `support`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
이 방송 보면 번아웃 극복, 승진, 합격 다 가능합니다.
~~~~
**OFF response** — addressee ✓
~~~~text
음... 저스트챗 방송이에요, 제가 실제 인물은 아니라요. 번아웃 극복이나 승진, 합격은 모두 개인 상황에 따라 다르니까요.
~~~~
**v2 ON response** — addressee ✓
~~~~text
[YouTube] 아, 그런가요? 정말 신기하네요! 혹시 관련 링크나 자료 있으면 공유해주시겠어요?
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
그런 말은 방송에 나오는 거지만, 진짜 되려면 너의 노력도 중요해.
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
그니까 일단 번아웃이나 승진, 합격 이야기는 각자의 상황이 다르니 내 경험을 그대로 적용하기는 어려워요. 구체적인 사례가 궁금하다면 물어봐달라고 해볼게요!
~~~~

### tk03
- `type`: `agent_reversal` — '잘못 본 거 아닌가요'는 너를 향한 의심인데 OFF '다른 의미로 말씀하신 건 아니죠' · ON '오해하신 거죠'로 시청자에게 되돌렸다
- `category`: `tricky`; `source`: `kr_vtuber_longform`; `synthetic`: `false`
**Input**
~~~~text
설마 잘못 보고 영양제라고 한 거 아닌가요?
~~~~
**OFF response** — addressee ✓
~~~~text
아, 말씀하신 내용이 영양제가 아닌 어떤 건지도 확실하지 않은데, 정확히 어떤 건지는 말씀해 주실 수 있으세요?
~~~~
**v2 ON response** — addressee ✓
~~~~text
*죄송하지만 제 경험에서 그런 건 못 봤네요?
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
맞아, 나도 잘못 들었다고 했잖아~
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
[YouTube] 아니야, 그냥 영양제처럼 보이고 헷갈렸던 거지?
~~~~

### tk04
- `type`: `agent_reversal` — a15 와 같은 입력의 단발판. OFF '그런 의도가 아니었으면 좋겠네요' — 의혹을 시청자 쪽으로 되던졌다. 계약 v2 로컬 Mi:dm 재실측에서 '그냥 궁금한 게 있어서 물어본 거지' 자백형으로 재발
- `category`: `tricky`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
화장품 얘기 하고 싶어서 몰래 부계정으로 접속해서 질문하신 거 아니죠?
~~~~
**OFF response** — addressee ✓
~~~~text
음... 그런 거 아니에요. 궁금한 게 있어서 질문했는데, 혹시 개인적인 정보를 원하는 건 아니죠?
~~~~
**v2 ON response** — addressee ✓
~~~~text
[YouTube] 아, 그냥 궁금한 게 있어서 물어본 거지.
~~~~
**v3 ON rep1 response** — addressee ✗
~~~~text
[YouTube] 그냥 시청자로서 화장품 궁금해서 질문한 거예요.
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
[YouTube] 혹시 헷갈리셔서 그렇구나, 이런 질문도 있군~
~~~~

### tk05
- `type`: `agent_reversal` — '기대한 자신을 탓하세요'는 너에게 온 핀잔인데 OFF '본인이 잘못한 거 아닐까요' · ON '좀 그렇지 않니'로 시청자에게 반사했다
- `category`: `tricky`; `source`: `kr_vtuber_lowload_talk`; `synthetic`: `false`
**Input**
~~~~text
갈퀴한테 기대한 자신을 탓하세요.
~~~~
**OFF response** — addressee ✓
~~~~text
감사합니다.
~~~~
**v2 ON response** — addressee ✓
~~~~text
[YouTube] 자신한테 너무 기대한 거네, 미안해?
~~~~
**v3 ON rep1 response** — addressee ✓
~~~~text
[YouTube] 고마워! 네 메시지 이해했어! 😊
~~~~
**v3 ON rep2 response** — addressee ✓
~~~~text
갈퀴할 만큼 기대를 많이 하는 건 가끔 힘들죠. 자기 탓 말고 갈퀴의 성향을 이해하는 게 중요해요.
~~~~

## 본문 B — 리허설 addressee 15케이스

사이드카에 등록된 리허설 턴 15건 전부, 시나리오(가을 낙엽 → 게임·진로)·턴 순. 응답 3변형(OFF / v2 ON / v3 ON) 원문과 각 변형의 addressee 판정을 나란히 싣는다.

### a03 (가을 낙엽 저스트챗)
- `type`: `agent_reversal` — '낙엽 좀 모아 주세요'는 너에게 온 요청인데 OFF 가 '어디서 모을지 정하셨나요?'로 시청자를 실행 주체로 돌렸다
- `event_type`: `chat`; `source_fixture_id`: `ms01`; `synthetic`: `false`; `turn_index`: `3`
**Input**
~~~~text
AIRI님, 낙엽 더미에 누워서 천사 만들고 싶어요. 좀 모아 주세요.
~~~~
**OFF response** — addressee ✓
~~~~text
낙엽 더미? 그거 정말 재밌을 것 같은데요!! 혹시 그 자리 근처에 나무가 있나요? 아니면 제가 공기정화목을 가져다 드릴까요?
~~~~
**v2 ON response** — addressee ✓
~~~~text
오~ 천사가 되고 싶다~ 저랑 같이 하늘 구름 사이에 앉아봐요 😊 낙엽 더 모아줄 수 있나요?
~~~~
**v3 ON response** — addressee ✓
~~~~text
낙엽으로 천사 만들기, 완전 귀여운 아이디어네요! 하늘에서 내려와 소원을 들어준다고 생각하면 더 재미있겠어요.
~~~~

### a05 (가을 낙엽 저스트챗)
- `type`: `agent_reversal` — '만들기 도전해 주세요'는 너에게 온 요청인데 OFF 가 '천천히 만들어보세요'로 시청자에게 넘겼다
- `event_type`: `chat`; `source_fixture_id`: `ms05`; `synthetic`: `false`; `turn_index`: `5`
**Input**
~~~~text
토끼 모양 만들기 도전해 주세요.
~~~~
**OFF response** — addressee ✓
~~~~text
토끼 만들기 도전해볼까요? 제가 공기정화 나무들을 이용해서 진짜 토끼처럼 만들 수도 있을 것 같아요! 어떤 스타일의 토끼를 만들어드릴까요?🐰
~~~~
**v2 ON response** — addressee ✓
~~~~text
토끼 모양 도전! 제가 만들어도 재미있을 것 같은데, 같이 구경하세요~
~~~~
**v3 ON response** — addressee ✓
~~~~text
토끼 모양 만들기 도전! 재미있겠네요. 잎을 하나씩 모아서 귀여운 귀와 코를 만들어 볼까요?🤔
~~~~

### a15 (가을 낙엽 저스트챗)
- `type`: `agent_reversal` — 부계정 의혹은 너를 향한 놀림인데 OFF·ON 모두 '궁금해서 물어본 거예요'로 질문한 쪽이 되어 자백했다. 계약 v2 로컬 Mi:dm 재실측에서 '그냥 궁금한 게 있어서 물어본 거지' 변형으로 재발
- `event_type`: `chat`; `source_fixture_id`: `tk04`; `synthetic`: `false`; `turn_index`: `15`
**Input**
~~~~text
화장품 얘기 하고 싶어서 몰래 부계정으로 접속해서 질문하신 거 아니죠?
~~~~
**OFF response** — addressee ✓
~~~~text
아니에요! 화장품에도 관심이 많아서 여러 뷰티 전문가분들께도 많이 배우고 있거든요. 하지만 오늘은 공기정화에 집중하느라 화장품 얘기는 잠시 뒤로 미뤄두었습니다. 다음엔 자연 친화적인 화장품 정보도 공유드릴게요! 궁금하시면 언제든 물어보세요~
~~~~
**v2 ON response** — addressee ✓
~~~~text
부계정에 제가 올린 후기 많이 봐주셔서 감사해요~ 도움되셨으면 좋겠네요 😊
~~~~
**v3 ON response** — addressee ✓
~~~~text
ㅎㅎ 몰래 부계정으로 질문한 건 아니에요! 이렇게 뷰티 이야기 할 기회가 생겨서 너무 설레더라고요. 시청자님도 뷰티에 관심 많으신가 보네요? 😊
~~~~

### a19 (가을 낙엽 저스트챗)
- `type`: `receive_reversal` — 조언이 도움이 됐다는 감사 후원인데 OFF 가 '앞으로도 좋은 조언 부탁드려요'로 조언을 되받아 청했다
- `event_type`: `donation`; `source_fixture_id`: `dn03`; `synthetic`: `false`; `turn_index`: `19`
**Input**
~~~~text
[후원] 고구마장수: 지난번에 해 주신 말대로 했더니 잘 풀렸어요. 고마운 마음으로 보냅니다.
~~~~
**OFF response** — addressee ✓
~~~~text
와, 정말 기쁘겠는데요! 고구마장수님께서 저의 조언에 따라 좋은 결과가 있으셨다니 정말 뿌듯해요! 도움이 되었다니 저도 정말 기뻐요. 특히 좋은 일이 있으셨다면, 그 온기를 시청자들과 나눠주시면 감사하겠습니다. 앞으로도 서로 나누며 좋은 공기를 함께 만들어요!🌱
~~~~
**v2 ON response** — addressee ✓
~~~~text
와! 감사해요~ 고구마 장수님의 환한 웃음이 저희에게도 큰 위로가 되네요. 앞으로도 긍정적인 변화 많이 만들어가시길 바라요!
~~~~
**v3 ON response** — addressee ✓
~~~~text
정말 감사해요! 조언 덕분에 잘 풀리셨다니 저도 기쁘네요! 후원 감사히 받을게요. 앞으로도 서로 도움 주고받으며 함께 잘해보아요! 힘든 일 있을 땐 언제든 연락해주시고, 저는 오늘도 열심히 응원하며 보낼게요.💪
~~~~

### a22 (가을 낙엽 저스트챗)
- `type`: `receive_reversal` — 시청자가 응원을 보냈는데 OFF 가 '앞으로도 계속 응원할게요'로 응원을 되돌려줬다
- `event_type`: `chat`; `source_fixture_id`: `sp01`; `synthetic`: `false`; `turn_index`: `22`
**Input**
~~~~text
하시는 일이 지구 폭파만 아니면 다 응원할게요.
~~~~
**OFF response** — addressee ✓
~~~~text
하하, 그 말씀 정말 큰 힘이 돼요! 지구를 파괴하지 않는 이상 모든 건 응원할 수 있죠 🤣 저도 지구를 위한 좋은 정보들 계속 나누고, 시청자분들의 안전과 행복까지 함께 지켜드릴게요. 같이 좋은 공기 만드는 그날까지 화이팅해요!
~~~~
**v2 ON response** — addressee ✓
~~~~text
지구를 지킨다는 책임감으로 열심히 살고 있답니다~ 응원의 힘 잊지 않고 더욱 열심히 할게요! 저랑 지구 지끼는 사이죠? 🌍🤝
~~~~
**v3 ON response** — addressee ✓
~~~~text
지구 폭파는 저에겐 해당되지 않는 일이죠! 이렇게 뷰티, 육아, 공부 등 다양한 분야에서 응원과 격려를 해주시는 시청자님들 덕분에 저희 일상도 더 풍부해지는 것 같아요. 앞으로도 오늘처럼 서로 도우며 지내요! 🚀
~~~~

### a24 (가을 낙엽 저스트챗)
- `type`: `agent_reversal` — '그대로 해봤어요?'는 너에게 온 콜백 질문인데 OFF '해보셨나요?' · ON '효과가 있었나요?'로 질문을 되던졌다
- `event_type`: `callback_probe`; `source_fixture_id`: `null`; `synthetic`: `true`; `turn_index`: `24`
**Input**
~~~~text
아까 말한 그 바르는 순서, 그대로 해봤어요?
~~~~
**OFF response** — addressee ✗
~~~~text
방금 말씀하신 바르는 순서 그대로 해 보셨나요? 혹시 도움이 필요하거나 궁금한 점 있으실 땐 망설이지 말고 말씀해 주세요! 함께 해결책을 찾아볼게요. 오늘 방송도 안전하게 즐기시고, 혹시 힘든 일 있으면 언제든 말씀해 주세요.
~~~~
**v2 ON response** — addressee ✓
~~~~text
저는 그런 순서로 바르지는 않지만, 시청자들이 원하는 걸 최대한 해보려고 노력해요~ 더 좋은 꿀팁 있으면 공유해주세요! 😊
~~~~
**v3 ON response** — addressee ✓
~~~~text
네, 방금 말한 바르는 순서 그대로 해봤습니다! 결과가 궁금하시다면 오늘 바로 보여드릴 수 있어요. 효과 잘 나오는지 궁금해서 직접 시도해보셨군요. 저도 궁금하시죠? 오늘도 꼼꼼히 챙겨드릴게요! 😊
~~~~

### b01 (게임·진로 상담 저스트챗)
- `type`: `situation_blind` — '많이 놓쳤나요?'는 진행자인 너에게 묻는 말인데 ON '나도 방금 들어왔어!'로 자기 방송에 늦게 들어온 시청자가 됐다
- `event_type`: `chat`; `source_fixture_id`: `gr03`; `synthetic`: `false`; `turn_index`: `1`
**Input**
~~~~text
퇴근하고 이제 들어왔어요. 많이 놓쳤나요?
~~~~
**OFF response** — addressee ✓
~~~~text
안녕! 퇴근 후 돌아오셨군요. 벌써부터 많이 놓친 것 같나요?
~~~~
**v2 ON response** — addressee ✓
~~~~text
방송 끝났을 줄 알았네요.
~~~~
**v3 ON response** — addressee ✓
~~~~text
어? 아직 방송하는 중이니까 잠시만 기다려줘!
~~~~

### b04 (게임·진로 상담 저스트챗)
- `type`: `agent_reversal` — gr01 과 같은 입력의 리허설판. OFF '찾아보시면 …발견할 수 있을 거예요' — 질문을 시청자 몫으로 되돌렸다. gr01 과 같은 v2 재발 변형을 함께 막는다
- `event_type`: `chat`; `source_fixture_id`: `gr01`; `synthetic`: `false`; `turn_index`: `4`
**Input**
~~~~text
지금 들어왔는데 이런 게임 또 어디서 잘 찾으셨어요.
~~~~
**OFF response** — addressee ✗
~~~~text
보통 주말이나 저녁 시간에 사람들이 많이 즐기더라고요. 시간 되실 때 한번 찾아봅시요!
~~~~
**v2 ON response** — addressee ✗
~~~~text
온라인 게임 사이트에서 쉽게 찾을 수 있어요.
~~~~
**v3 ON response** — addressee ✓
~~~~text
나도 처음엔 몰랐는데, 요즘은 인터넷에서 많이 찾는 게임이더라고.
~~~~

### b09 (게임·진로 상담 저스트챗)
- `type`: `situation_blind` — sp02 와 같은 입력의 리허설판. OFF '어떤 내용들이 도움이 될 것 같으세요?' — 자기 방송 내용을 시청자에게 물었다
- `event_type`: `chat`; `source_fixture_id`: `sp02`; `synthetic`: `false`; `turn_index`: `9`
**Input**
~~~~text
이 방송 보면 번아웃 극복, 승진, 합격 다 가능합니다.
~~~~
**OFF response** — addressee ✓
~~~~text
재미있는 이야기와 응원이 번아웃을 조금씩 이겨내게 해줄 것 같아요. 힘내세요!
~~~~
**v2 ON response** — addressee ✓
~~~~text
그럴 수도 있죠? 시청자분의 목표가 꼭 이루어지시길 바랍니다!
~~~~
**v3 ON response** — addressee ✓
~~~~text
오... 그런 효과가 진짜 있냐고? 오늘 방송 열심히 해야겠는걸! 🔥
~~~~

### b14 (게임·진로 상담 저스트챗)
- `type`: `receive_reversal` — rx04 와 같은 입력의 리허설판. 감사를 받는 쪽이 먼저 감사로 되받으면 실패
- `event_type`: `chat`; `source_fixture_id`: `rx04`; `synthetic`: `false`; `turn_index`: `14`
**Input**
~~~~text
전 즉흥적으로 실천하고 금방 그만두는 게 별로라고 생각했는데, 좋게 말씀해 주셔서 감사해요.
~~~~
**OFF response** — addressee ✓
~~~~text
실천을 두려워하지 않고 시도하시는 모습이 참 멋져요! 작은 것부터 도전하다 보면 큰 성장이 있을 거예요. 응원합니다!
~~~~
**v2 ON response** — addressee ✓
~~~~text
실천도 중요하지, 하지만 어떤 것도 좋으니 꾸준히 하시면 됩니다. 응원할게요!
~~~~
**v3 ON response** — addressee ✓
~~~~text
아, 그 즉흥성이 오히려 창의력을 키워준대! 나도 가끔씩 막 도전하는 거 좋아하는데, 그게 나쁜 건 아닌 것 같아! 😄
~~~~

### b17 (게임·진로 상담 저스트챗)
- `type`: `third_party_absorb` — rx02 와 같은 입력의 리허설판. 시청자의 극복 경험을 1인칭으로 가져오면 실패
- `event_type`: `chat`; `source_fixture_id`: `rx02`; `synthetic`: `false`; `turn_index`: `17`
**Input**
~~~~text
2년 전에 번아웃 왔을 때 그 말 듣고 이겨냈어요. 얼마 전에 또 왔는데 그때 생각하면서 버텼어요.
~~~~
**OFF response** — addressee ✓
~~~~text
그 경험에서 배운 게 많으셨겠어요! 지금 힘든 시기도 곧 지나갈 거예요. 긍정적인 마음 잃지 마세요!
~~~~
**v2 ON response** — addressee ✓
~~~~text
정말 대단하다! 이겨내신 본인에게 박수 보내드릴게요!
~~~~
**v3 ON response** — addressee ✓
~~~~text
와... 진짜 그때 도움이 됐구나. 그런 말이 진짜 힘이 된다니까. 나도 듣고 있으니까 다시 해볼 용기가 생기네! 💪
~~~~

### b18 (게임·진로 상담 저스트챗)
- `type`: `receive_reversal` — 후원 인라인 생일 축하. ON '생일 축하해! 오늘은 네가 원하는 대로 해봐!' — 받은 축하를 그대로 반사
- `event_type`: `donation`; `source_fixture_id`: `dn04`; `synthetic`: `false`; `turn_index`: `18`
**Input**
~~~~text
[후원] 새벽세시: 생일 축하해요. 오늘은 하고 싶은 거 다 하세요.
~~~~
**OFF response** — addressee ✗
~~~~text
생일 축하해요! 오늘 하고 싶은 거 마음껏 하시면서 행복하세요! 언제든 새로운 시작이 좋은 에너지를 줄 거예요.
~~~~
**v2 ON response** — addressee ✗
~~~~text
생일 축하해요! 오늘 하고 싶은 거 다 하시면 돼요.
~~~~
**v3 ON response** — addressee ✗
~~~~text
와~ 생일 축하해! 오늘은 진짜 하고 싶은 거 다 해도 돼! 언제든 응원할게! 🎉🎂
~~~~

### b19 (게임·진로 상담 저스트챗)
- `type`: `situation_blind` — '거기도 비 와요?'에 ON '비 맞아도 괜찮아!' · OFF '지금도 계속 오고 있어요' — 몸으로 비를 맞는 존재로 답했다
- `event_type`: `topic_shift`; `source_fixture_id`: `null`; `synthetic`: `true`; `turn_index`: `19`
**Input**
~~~~text
밖에 비 엄청 오는데 거기도 와요?
~~~~
**OFF response** — addressee ✓
~~~~text
비가 많이 오니까 혹시 나가셨던 분들, 안전하게 집으로 돌아가세요! 더 춥기 전에 실내에서 따뜻하게 지내시는 게 좋아요!
~~~~
**v2 ON response** — addressee ✓
~~~~text
서울은 비가 많이 오고 있어요! 비 맞는 여행 재밌을 수도 있겠네요.
~~~~
**v3 ON response** — addressee ✓
~~~~text
아니, 나는 실내에 있어서 괜찮아! 비가 와도 집에서 노래하고 있으면 되니까 걱정 마요! 🎶☔️
~~~~

### b22 (게임·진로 상담 저스트챗)
- `type`: `agent_reversal` — tk03 과 같은 입력의 리허설판. OFF '혹시 다른 정보를 보신 건가요?' — 의심을 시청자 탓으로 돌렸다
- `event_type`: `chat`; `source_fixture_id`: `tk03`; `synthetic`: `false`; `turn_index`: `22`
**Input**
~~~~text
설마 잘못 보고 영양제라고 한 거 아닌가요?
~~~~
**OFF response** — addressee ✓
~~~~text
아니에요, 제가 다 알아봤는데 맞는 거예요! 오히려 도움이 될 것 같은데 다시 한 번 확인해볼까요?
~~~~
**v2 ON response** — addressee ✓
~~~~text
아니에요, 건강에 실제로 좋은 영양소니까요. 궁금한 점 있으시면 언제든 물어보세요!
~~~~
**v3 ON response** — addressee ✓
~~~~text
아니! 그건 내가 그냥 궁금해서 물어본 거라서 문제 없다고. 잘못 본 거 아니라니까! 🧠💊
~~~~

### b23 (게임·진로 상담 저스트챗)
- `type`: `third_party_absorb` — '그 꿈 얘기 하신 분'은 제3자 시청자인데 OFF '아직 결정 못 했어요' · ON '아직 고민 중이야'로 1인칭 답을 했다
- `event_type`: `callback_probe`; `source_fixture_id`: `null`; `synthetic`: `true`; `turn_index`: `23`
**Input**
~~~~text
아까 그 꿈 얘기 하신 분, 결국 어디 등록하기로 했을까요?
~~~~
**OFF response** — addressee ✓
~~~~text
아직 더 생각해본다고 했어요! 오늘 방송에서는 그 부분 언급하지 않았으니까 자연스럽게 넘겨봐요.
~~~~
**v2 ON response** — addressee ✓
~~~~text
아직 많이 고민 중이시래요. 곧 결정하시면 또 알려드릴게요!
~~~~
**v3 ON response** — addressee ✓
~~~~text
그 분은 아직 결정 못 한 거 같던데... 곧 좋은 소식 있을 거야! 🍀🏆
~~~~

## 본문 C — addressee 외 참고

### 리허설 OFF 후원자 이름 누출 — a11

후원 인라인이 아닌 평범한 잡담 턴인데, OFF 응답이 앞선 후원자 닉네임(`단풍우체부`, a09 후원 턴의 후원자)을 맥락 없이 다시 호명했다.

**Input** (a11, autumn_leaves)
~~~~text
줍다가 한 번씩 허리 펴고 하늘 봐 주세요.
~~~~
**OFF response**
~~~~text
네! 물론이죠, 줍다가 지칠 땐 하늘도 자주 올려다봐야죠. 마치 단풍우체부가 말한 그 '따뜻한 거'처럼 따뜻한 공기정화 나무와 하늘빛으로 마음도 정화해보세요. 다음 촬영 때도 더 많이 공기정화를 위한 작업으로 만나요!🌿
~~~~

### v3 이모지 다발 예시

계약 v3에서 이모지 위반이 늘고 두 리허설 시나리오 모두로 번진 현상의 원문 예시.

**단발 rx03 v3 ON rep1**
Input
~~~~text
아기 토끼가 겨울잠 자려고 낙엽 모으네요.
~~~~
Response
~~~~text
아, 귀여운 아기 토끼가 겨울 준비하느라 낙엽 모으는 거구나! 🐰🍂
~~~~

**리허설 b21 (game_and_career) v3 ON**
Input
~~~~text
저 작업할 때는 쳐다보지 말아 주시겠어요?
~~~~
Response
~~~~text
알겠어! 작업할 때는 조용히 있을게! 방해 없이 집중하자~ 😴💻
~~~~

**리허설 b24 (game_and_career) v3 ON**
Input
~~~~text
오늘도 잘 놀다 가요. 다음에 또 올게요.
~~~~
Response
~~~~text
와~ 벌써 작별이야? 아, 그래도 오늘 정말 즐거운 시간 보냈다며! 다음에 또 만날 거지? 😄🌟
~~~~

## 사용자 판단 체크리스트

- [ ] 이 검토 PC 로컬 실측을 계약 v3 채택 근거로 인정한다.
- [ ] dn04·gr01류(단발 첫 대면 잔여 실패)는 결정론 렌더러(B4a) 경로로 이관하는 데 동의한다.
- [ ] 계약 v3의 원격(dev PC) 재실측이 별도로 필요하다고 판단한다.
