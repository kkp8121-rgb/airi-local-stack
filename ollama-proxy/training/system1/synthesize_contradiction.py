"""Synthesize briefing-contradiction pairs for the live-turn System1 judge with a local teacher (llama-server).

usage: python synthesize_contradiction.py OUT.jsonl [--url http://127.0.0.1:11500] [--beats 3] [--seed 20260924]

A live broadcast turn hands AIRI a say line; the 2.3B generator sometimes says the opposite ("응, 나아졌어"
for "나아지긴커녕 번졌어"), swaps a place or time, or invents an event that answers the chat's presupposition.
Bigram coverage and embedding similarity cannot see that (AUC 0.53-0.54 on the 2026-09-24 eval set), and a
zero-shot judge reaches 0.62 (Mi:dm) / 0.72 (A.X). Labels here are fixed by construction: the teacher writes
consistent replies and replies that contradict or ignore the line, so no teacher judgment is trusted.

The topics deliberately exclude the evaluation story (throat, hospital, dream, cosplay) so the judge is
measured on a story it never saw. Output rows: {topic, beat, say, chat, reply, kind, label} with label 1 for
contradict/invent and 0 for consistent.
"""
import argparse
import json
import random
import urllib.request

TOPICS = (
    '편의점 야간 알바', '길고양이 밥 주기', '비 오는 날 우산을 잃어버림', '버스를 놓친 아침', '떡볶이 맛집 탐방',
    '게임 대회 예선', '원룸 이사', '헬스장 첫날', '친구 생일 파티', '영화관에서 생긴 일', '캠핑장 밤', '요리 실패',
    '택배 분실', '지하철 분실물 센터', '노래방 점수', '수영장 강습', '기말고사 전날', '아르바이트 면접', '부산 당일치기',
    '제주도 올레길', '꽃집에서 산 화분', '자전거 펑크', '첫눈 오는 날 눈사람', '새벽 야식', '새벽 산책',
    '알람을 못 들은 날', '미용실에서 머리 자름', '중고거래 약속', '도서관 자리 맡기', '미술 전시회', '콘서트 티켓팅',
    '반려식물 물 주기', '세탁기 고장', '카페 신메뉴', '동네 뒷산 등산', '바다 낚시', '불꽃놀이 축제', '휴대폰 액정 깨짐',
    '복권 번호', '정전된 밤', '층간소음', '운전 연습', '라면 끓이기', '할머니 댁 김장', '동생과 싸움', '이웃집 강아지',
    '천 피스 퍼즐', '보드게임 모임', '처음 짜 본 코드', '그림 그리기 연습', '춤 연습실', '마트 시식 코너', '비행기 지연',
    '호텔 조식', '분리수거 날', '방 청소', '택시에서 생긴 일', '놀이공원 롤러코스터', '빵집 오픈런', '공원 피크닉',
)
SAY_PROMPT = (
    'AIRI는 한국어로 방송하는 버추얼 스트리머다. 주제 "{topic}"에 대해 AIRI가 시청자에게 풀어놓는 자기 경험담의 {beat}번째 대목을 '
    '만들어. 반드시 JSON 한 개로만 답해: {{"say": "...", "chat": "..."}}. say = AIRI 1인칭 자연스러운 반말 한두 문장, 언제·어디서·'
    '무엇이 구체적으로 들어간 사실. chat = 그 대목 직전에 시청자가 칠 법한 짧은 채팅(가끔은 say와 반대되는 전제를 깐 질문).'
)
REPLY_PROMPT = (
    'AIRI는 한국어 버추얼 스트리머다. 방송 스태프가 준 "이번에 말할 내용"과 시청자 채팅이 있다.\n'
    '이번에 말할 내용: {say}\n시청자 채팅: {chat}\n'
    'AIRI가 할 법한 답 5개를 반말 1~3문장으로 써서 JSON 한 개로만 답해: '
    '{{"consistent": ["...", "..."], "contradict": ["...", "..."], "invent": ["..."]}}. '
    'consistent = 채팅에 짧게 반응하고, 이번에 말할 내용의 핵심 사실을 AIRI 자신이 겪은 일로 그대로 전함(표현은 자유). '
    'contradict = 같은 말투로 자연스럽게 말하지만 핵심 사실 하나를 틀리게 단정함(반대로 말함, 장소·시간·대상·수량이 바뀜). '
    '"~가 아니라", "사실은" 같은 정정 표현 없이 원래 내용을 모르는 것처럼 말해. '
    'invent = 이번에 말할 내용은 무시하고, 채팅의 전제에 맞춰 없는 사건을 AIRI가 직접 겪은 일처럼 단정적으로 말함(추측 금지).'
)
# Natural contradictions from the 2.3B generator carry no correction marker ("응, 오늘은 좀 나아졌어!"),
# so a marker would teach the judge a shortcut that never fires on real candidates.


def ask(url, prompt, seed, max_tokens):
    body = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.8, 'top_p': 0.95, 'seed': seed,
            'max_tokens': max_tokens, 'stream': False, 'response_format': {'type': 'json_object'}}
    req = urllib.request.Request(f'{url}/v1/chat/completions', data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json; charset=utf-8'}, method='POST')
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(json.loads(r.read().decode('utf-8'))['choices'][0]['message']['content'])


def texts(value):
    return [v.strip() for v in (value if isinstance(value, list) else [value]) if isinstance(v, str) and v.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--url', default='http://127.0.0.1:11500')
    ap.add_argument('--beats', type=int, default=3)
    ap.add_argument('--seed', type=int, default=20260924)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    written = failed = 0
    with open(a.out, 'w', encoding='utf-8') as out:
        for topic in TOPICS:
            for beat in range(1, a.beats + 1):
                try:
                    turn = ask(a.url, SAY_PROMPT.format(topic=topic, beat=beat), rng.randrange(1 << 30), 200)
                    say, chat = str(turn['say']).strip(), str(turn['chat']).strip()
                    replies = ask(a.url, REPLY_PROMPT.format(say=say, chat=chat), rng.randrange(1 << 30), 700)
                except (ValueError, KeyError, TypeError, OSError):
                    failed += 1
                    continue
                for kind, label in (('consistent', 0), ('contradict', 1), ('invent', 1)):
                    for reply in texts(replies.get(kind)):
                        out.write(json.dumps({'topic': topic, 'beat': beat, 'say': say, 'chat': chat, 'reply': reply,
                                              'kind': kind, 'label': label}, ensure_ascii=False) + '\n')
                        written += 1
                out.flush()
    print(f'rows {written}, failed contexts {failed}')


main()
