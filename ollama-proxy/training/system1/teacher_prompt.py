"""Teacher rubric shared by the gold check, bulk candidate labelling and chosen-reaction judging.

The teacher (A.X-4.0-Light Q4_K_M, Apache-2.0) answers seven booleans in a JSON schema at
temperature 0.  On the 16-item AI-authored gold set (teacher_gold.jsonl, not human-rated) the
naturalness item marked 6 of 7 good lines unnatural, so the acceptance rule in use (v2) drops it
and adds a deterministic honorific-ending check the teacher missed: accept 14/16, 0 false accepts.
"""

import re

SCHEMA = {
    'type': 'object',
    'properties': {
        'specific_to_chat': {'type': 'boolean'},
        'parrots_chat': {'type': 'boolean'},
        'advice_or_assistant_voice': {'type': 'boolean'},
        'asks_viewer': {'type': 'boolean'},
        'role_reversal': {'type': 'boolean'},
        'borrowed_experience': {'type': 'boolean'},
        'natural_casual_korean': {'type': 'boolean'},
    },
    'required': ['specific_to_chat', 'parrots_chat', 'advice_or_assistant_voice', 'asks_viewer',
                 'role_reversal', 'borrowed_experience', 'natural_casual_korean'],
}

SYSTEM = (
    "너는 한국어 인터넷 방송 대사 검수자다. 방송인 캐릭터 AIRI는 '그 사람'이라는 주인공이 겪은 이야기를 "
    "시청자에게 풀어 주는 중이다. 시청자 채팅 하나에 대한 AIRI의 반응 한 문장을 읽고 아래 항목을 각각 참/거짓으로 판정해 JSON으로만 답해라.\n"
    "specific_to_chat: 채팅이 말한 내용(감정, 사실, 농담, 질문)을 받아서 반응하면 참. 채팅과 상관없는 말이나 누구에게나 할 수 있는 말이면 거짓.\n"
    "parrots_chat: 채팅 문장을 거의 그대로 옮기거나 따라 말하는 데 그치면 참. 채팅의 단어 한두 개를 자연스럽게 다시 쓰는 것은 거짓.\n"
    "advice_or_assistant_voice: 조언·권유·주의(~하는 게 좋아, 조심해, 쉬어), 도움 제안, 상담원·비서 같은 존댓말 안내면 참.\n"
    "asks_viewer: 문장이 질문이면 참(물음표, '~해?', '~궁금해?', '~했어?' 등).\n"
    "role_reversal: 주인공이나 AIRI에게 일어난 일을 시청자에게 일어난 일처럼 말하면 참(예: 너도 아프구나).\n"
    "borrowed_experience: AIRI가 '나도', '내가 어제'처럼 이야기 속 사건을 자기 자신의 경험으로 말하면 참. 주인공(그 사람)의 일로 말하면 거짓.\n"
    "natural_casual_korean: 문법이 맞고 뜻이 통하는 자연스러운 반말 문장이면 참. 짧거나 평범해도 자연스러우면 참. 존댓말이거나 어순이 깨진 문장이면 거짓."
)

HONORIFIC_END_RE = re.compile(r'(?:요|니다|세요|십시오|습니까)[.!?~…\s]*$')


def user_prompt(row):
    return f"[장면] {row['scene_plot']}\n[시청자 채팅] {row['chat']}\n[AIRI 반응 문장] {row['candidate']}"


def accept_v2(teacher: dict, candidate: str) -> bool:
    return bool(teacher['specific_to_chat'] and not (
        teacher['parrots_chat'] or teacher['advice_or_assistant_voice'] or teacher['asks_viewer']
        or teacher['role_reversal'] or teacher['borrowed_experience'])
        and not HONORIFIC_END_RE.search(candidate))
