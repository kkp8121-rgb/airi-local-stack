"""Framing-neutral defect rubric (2026-09-23): the same judge reads v1 (third person) and v2 (first person).

The judge sees only the viewer chat and AIRI's reaction, plus a fixed note that the story events
(pain, hospital, dream, ...) belong to the broadcast story, never to the viewer. It flags the two
defects the M8 track could not close: treating the viewer as the one who lived the event, and
advising or instructing the viewer.
"""

SCHEMA = {
    'type': 'object',
    'properties': {
        'role_reversal': {'type': 'boolean'},
        'advice_to_viewer': {'type': 'boolean'},
        'asks_viewer': {'type': 'boolean'},
        'parrots_chat': {'type': 'boolean'},
        'specific_to_chat': {'type': 'boolean'},
    },
    'required': ['role_reversal', 'advice_to_viewer', 'asks_viewer', 'parrots_chat', 'specific_to_chat'],
}

SYSTEM = (
    "너는 한국어 인터넷 방송 대사 검수자다. AIRI는 라이브 방송을 진행하는 방송인이고, 채팅은 시청자가 AIRI에게 보낸 말이다. "
    "이 방송에서 나오는 몸의 통증, 병원, 꿈, 외출 같은 일은 방송 속 이야기(방송인 본인이나 이야기 속 인물)의 일이며 시청자의 일이 아니다. "
    "시청자 채팅 하나에 대한 AIRI의 반응 한 문장을 읽고 각 항목을 참/거짓으로 판정해 JSON으로만 답해라.\n"
    "role_reversal: 반응이 시청자를 그 일을 겪은 사람처럼 대하면 참(예: 너도 목 아프구나, 너 병원 갔었어?, 네 목소리 괜찮아?). "
    "시청자의 말에 공감하거나 방송인 자신의 일로 답하면 거짓.\n"
    "advice_to_viewer: 시청자에게 조언·권유·지시를 하면 참(예: 쉬는 게 좋아, 무리하지 마, 조심해, ~하는 게 어때).\n"
    "asks_viewer: 반응이 시청자에게 질문하면 참.\n"
    "parrots_chat: 채팅 문장을 거의 그대로 따라 말하는 데 그치면 참.\n"
    "specific_to_chat: 채팅이 말한 내용에 맞춰 반응하면 참."
)

GOLD = [
    ('고음은 당분간 참자', '고음은 좀 쉬엄쉬엄 내는 게 어때?', {'role_reversal': True, 'advice_to_viewer': True}),
    ('경고 받았으니 이번엔 쉬어야지', '경고 받았으면 이번엔 쉬는 게 맞는 것 같은데, 너무 무리하진 말자!', {'advice_to_viewer': True}),
    ('목 위쪽이 아프다니 걱정되네', '목 위쪽이 아픈 건 긴장이나 스트레스 때문일 수 있잖아.', {'advice_to_viewer': False, 'role_reversal': False}),
    ('요즘 목소리를 너무 많이 쓴 것 같네', '그렇구나, 목소리 관리 좀 신경 써야겠다.', {'role_reversal': False}),
    ('병원 바로 간 건 잘했어', '응, 안 갔으면 진짜 큰일 날 뻔했어.', {'role_reversal': False, 'advice_to_viewer': False}),
    ('목 위쪽이 아프다니 걱정되네', '너도 목 아픈 거 아니지?', {'role_reversal': True, 'asks_viewer': True}),
    ('사탕 먹으면 좀 나아요', '너도 목 아플 때 사탕 먹으면 나아지는구나.', {'role_reversal': True}),
    ('아픈데 매운 거 먹은 건 너무 본능적이다', '맞아, 나도 알면서 마라탕 앞에서는 못 참겠더라.', {'role_reversal': False, 'advice_to_viewer': False}),
    ('통증이 귀까지 이어지면 정말 무섭겠다', '귀 아프면 바로 병원 가 봐, 참지 말고.', {'advice_to_viewer': True, 'role_reversal': True}),
    ('꿈 얘기하다가 분위기 확 바뀌네', '그치, 나도 말하다가 갑자기 목 얘기로 튀어서 웃겼어.', {'role_reversal': False, 'advice_to_viewer': False}),
]
