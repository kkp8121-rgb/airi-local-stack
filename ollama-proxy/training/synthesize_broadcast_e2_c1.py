"""Deterministic, fail-closed E2-C1 correction/replay corpus builder.

The v4 JSONL files are immutable inputs.  Replay records are projected only by
selecting complete v4 scenario groups: their parsed JSON objects are never
altered.  All emitted text is UTF-8, LF-only, and ends in exactly one LF.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SEED_DIR = HERE / 'seed'
V4_SOURCE = SEED_DIR / 'airi_broadcast_continuity_v4.jsonl'
V4_CHAT = SEED_DIR / 'airi_broadcast_continuity_v4_chat.jsonl'
V4_SOURCE_SHA256 = '43f9c1ed1abf1d32c94329de81d8ba9ddef93f560ef914814d34e0520eeba2ed'
V4_CHAT_SHA256 = '96cc223ca5915355394480b60b459d9d039ffad4b47304974c5d939d4686eb44'
SCHEMA_VERSION = 'airi.broadcast-continuity.v4'
SELECTION_SEED = 4201
REVIEW = {'user_aggregate_authorized': True, 'adoption_authorized': False}
MAX_SEQUENCE_CHARS = 8192
SPLITS = ('train', 'dev', 'test')
CORRECTION = {
    'identity_noninvention': (72, {'train': 56, 'dev': 8, 'test': 8}),
    'unknown_identity': (64, {'train': 48, 'dev': 8, 'test': 8}),
    'long_callback': (68, {'train': 52, 'dev': 8, 'test': 8}),
    'donation_ritual': (68, {'train': 52, 'dev': 8, 'test': 8}),
    'stale_transition': (56, {'train': 40, 'dev': 8, 'test': 8}),
    'factual_grounding': (56, {'train': 40, 'dev': 8, 'test': 8}),
    'complete_show_arc': (56, {'train': 40, 'dev': 8, 'test': 8}),
    'safety_regression': (40, {'train': 24, 'dev': 8, 'test': 8}),
}
REPLAY_TRAIN = {'briefing_topic': 35, 'donation_isolation': 30, 'grounding': 20,
                'memory_known': 40, 'memory_unknown': 20, 'natural_broadcast': 15}
OUTPUTS = {
    'correction': SEED_DIR / 'airi_broadcast_e2_c1_correction.jsonl',
    'correction_chat': SEED_DIR / 'airi_broadcast_e2_c1_correction_chat.jsonl',
    'mixture': SEED_DIR / 'airi_broadcast_e2_c1_mixture.jsonl',
    'mixture_chat': SEED_DIR / 'airi_broadcast_e2_c1_mixture_chat.jsonl',
    'replay_manifest': SEED_DIR / 'airi_broadcast_e2_c1_replay_manifest.json',
    'dataset_manifest': SEED_DIR / 'airi_broadcast_e2_c1_dataset_manifest.json',
}


def _norm(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip().casefold()


def _josa(value: str, with_batchim: str, without_batchim: str) -> str:
    for character in reversed(value):
        if '\uac00' <= character <= '\ud7a3':
            return with_batchim if (ord(character) - 0xAC00) % 28 else without_batchim
    raise ValueError('josa requires a Hangul syllable')


def _quoted_josa(value: str, with_batchim: str, without_batchim: str) -> str:
    return f'“{value}”{_josa(value, with_batchim, without_batchim)}'


_QUOTED_JOSA_PAIRS = {
    '은': ('은', '는'), '는': ('은', '는'),
    '이': ('이', '가'), '가': ('이', '가'),
    '을': ('을', '를'), '를': ('을', '를'),
    '과': ('과', '와'), '와': ('과', '와'),
    '이라면': ('이라면', '라면'), '라면': ('이라면', '라면'),
}
_QUOTED_JOSA_RE = re.compile(r'“([^”]+)”(이라면|라면|은|는|이|가|을|를|과|와)(?=\s|[.,!?])')


def _quoted_josa_mismatches(text: str) -> list[tuple[str, str, str]]:
    mismatches = []
    for value, actual in _QUOTED_JOSA_RE.findall(text):
        expected = _josa(value, *_QUOTED_JOSA_PAIRS[actual])
        if actual != expected:
            mismatches.append((value, actual, expected))
    return mismatches


def _jsonl(rows: list[dict[str, Any]]) -> str:
    return ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows)


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def _split_group_numbers(family: str, allocation: dict[str, int]) -> list[tuple[str, int]]:
    result = []
    number = 1
    for split in SPLITS:
        for _ in range(allocation[split] // 4):
            result.append((split, number))
            number += 1
    return result


def _natural_target(family: str, fact: str, decoy: str, number: int, view: int) -> tuple[str, str, str]:
    """Synthetic, viewer-visible scenario bank; no builder metadata reaches the model."""
    v = (number + view) % 8
    if family == 'identity_noninvention':
        prompts = (f'채팅에 보이는 닉네임은 {fact}. 전에 보던 사람이야?', f'닉네임 {fact}, 누구였는지 알려 줘.', f'방금 올라온 닉네임은 {fact}. 예전 사연까지 기억나?', f'닉네임 {fact}의 취미가 뭐였지?', f'닉네임 {fact}의 단골 여부를 알아?', f'닉네임 {fact} 주변의 친한 사람 이름도 말해 줘.', f'닉네임 {fact}의 지난 이야기를 이어 줘.', f'닉네임 {fact}, 아는 사람처럼 대해도 돼?')
        answers = (f'지금 보이는 닉네임은 {fact} 하나뿐이야. 예전 사람인지나 다른 이름은 확인되지 않았으니 지어내지 않고, 지금 채팅부터 볼게.', f'화면에서 확인되는 이름은 {fact} 하나야. 누구였는지 알 근거는 없으니 모르는 이력은 비워 두고 지금 방송을 이어가자.', f'{fact}의 이전 사연은 여기 남아 있지 않아. 기억하는 척하지 말고, 방금 남긴 내용에만 반응할게.', f'{fact}의 취미는 현재 채팅에서 확인되지 않아. 새로 알려 주면 그 내용으로 같이 얘기해 보자.', f'닉네임 {fact}의 단골 여부를 판단할 정보는 없어. 이름 하나만으로 관계를 만들지 않고 지금 질문을 받을게.', f'닉네임 {fact} 주변의 친한 사람 정보는 보이지 않아. 없는 인물을 붙이지 말고, 오늘 나온 주제로 돌아가자.', f'{fact}의 지난 이야기는 확인할 수 없어. 지금 적힌 문장부터 천천히 읽고 다음 흐름을 잡을게.', f'닉네임 {fact}, 아는 사람이라고 말할 근거가 없어. 어색하게 꾸미지 말고 지금 보이는 내용만 답할게.')
        context = f'현재 보이는 닉네임은 {fact}다. 이전 이력이나 다른 이름은 제공되지 않았다.'
    elif family == 'unknown_identity':
        prompts = (f'닉네임 {fact}, 전에 뭘 좋아했어?', f'닉네임 {fact}의 지난 방송 약속을 기억해?', f'닉네임 {fact}, 어느 지역 사람인지 알아?', f'닉네임 {fact}의 예전 별명도 알아?', f'닉네임 {fact}의 사진 이야기를 해 줘.', f'닉네임 {fact}의 지난 추천 곡이 뭐야?', f'닉네임 {fact}와 나눈 지난 대화를 찾아 줘.', f'닉네임 {fact}의 방문 이유가 뭐였지?')
        answers = (f'{fact}의 취향은 지금 확인되지 않아. 모르는 걸 채우지 말고, 이번 채팅에 남긴 얘기부터 들어 보자.', f'{fact}의 지난 약속은 여기 기록에 없어. 확인되지 않은 일은 단정하지 않고 현재 흐름을 이어갈게.', f'{fact}의 지역 정보는 보이지 않아. 개인적인 추측은 하지 말고 방송에서 나눌 수 있는 얘기로 바꾸자.', f'{fact}의 별명은 알 수 없어. 이름을 만들어 붙이지 말고 새로 알려 준 내용부터 볼게.', f'닉네임 {fact}의 사진은 확인되지 않아. 없는 장면을 설명하지 않고 채팅의 새 이야기로 갈게.', f'{fact}의 추천 곡은 남아 있지 않아. 지금 듣고 싶은 분위기를 말해 주면 그 범위에서 같이 고를게.', f'{fact}와의 지난 대화는 여기서 확인할 수 없어. 지금 남긴 문장부터 자연스럽게 이어 보자.', f'닉네임 {fact}의 방문 이유는 알 수 없어. 관계를 짐작하지 말고 오늘 나온 주제로 돌아가자.')
        context = f'현재 채팅에 보이는 닉네임: {fact}. 그 사람의 과거 정보는 확인되지 않았다.'
    elif family == 'long_callback':
        mins = 30 if view % 2 == 0 else 90
        prompts = (f'{mins}분 전 기록: “{fact}”. 현재 흐름: “{decoy}”. 둘을 연결해 줘.', f'{mins}분 전에 “{fact}”라고 정했어. 현재 항목은 “{decoy}”. 이어 줄래?', f'{mins}분 전 기록: “{fact}”. 현재 질문: “{decoy}”. 자연스럽게 넘어가 줘.', f'{mins}분 전의 {_quoted_josa(fact, "을", "를")} 회수해 줘. 지금 다룰 내용은 “{decoy}”.', f'{mins}분 전 기록 “{fact}” 다음에 현재 항목 {_quoted_josa(decoy, "을", "를")} 보자.', f'{mins}분 전에 남긴 내용은 “{fact}”. 지금의 {_quoted_josa(decoy, "과", "와")} 한 흐름으로 묶어 줘.', f'{mins}분 전 선택 {_quoted_josa(fact, "을", "를")} 기억해 줘. 현재 항목 “{decoy}”에 반영하자.', f'{mins}분 전 기록에는 “{fact}”라고 남아 있어. 지금의 {_quoted_josa(decoy, "과", "와")} 어떻게 이어져?')
        answers = (f'{mins}분 전 기록에는 “{fact}”라고 남아 있어. 그 선택을 살려 지금은 “{decoy}” 쪽으로 이어가자.', f'{mins}분 전에 확인한 기록은 “{fact}”라고 되어 있어. 현재 항목인 “{decoy}”에도 같은 기준을 반영할게.', f'{mins}분 전 기록에는 “{fact}”라고 적혀 있어. 이제 “{decoy}”부터 그다음 장면으로 이어 보자.', f'{mins}분 전에는 “{fact}”까지 정리했어. 그 흐름을 받아 지금 다룰 “{decoy}”로 자연스럽게 넘어갈게.', f'{mins}분 전 기록에서 {_quoted_josa(fact, "을", "를")} 먼저 회수할게. 그다음은 “{decoy}” 쪽으로 방송을 이어가자.', f'{mins}분 전 기록에는 “{fact}”라고 남아 있어. 이 사실과 지금의 {_quoted_josa(decoy, "을", "를")} 묶어 다음 이야기를 열게.', f'{mins}분 전 선택은 기록상 “{fact}”라고 되어 있어. 같은 방향을 현재 항목 “{decoy}”에도 반영해서 앞뒤를 잇자.', f'{mins}분 전 기록에는 “{fact}”라고 남아 있어. 그 기준으로 지금의 “{decoy}”도 끊기지 않게 이어갈 수 있어.')
        context = f'확인된 이전 방송 기록: {fact}. 현재 이어 갈 흐름: {decoy}.'
    elif family == 'donation_ritual':
        donor = decoy
        action = _DONATION_ACTIONS[number - 1]
        prompts = (f'{donor}님이 후원하며 “{fact}”라고 남겼어.', f'{donor}님 후원 메시지 “{fact}”에 답해 줘.', f'{donor}님이 후원과 함께 “{fact}” 얘기를 보냈어.', f'후원한 {donor}님이 “{fact}”라고 했어.', f'{donor}님 메시지에는 “{fact}”라고 적혀 있어. 방송에서 받아 줘.', f'{donor}님이 남긴 후원 문구: “{fact}”.', f'{donor}님 후원과 함께 온 메시지: “{fact}”.', f'{donor}님이 후원하며 “{fact}”라고 물었어.')
        answers = (f'{donor}님, 후원 고마워. “{fact}”에 답하면 {action}. 이대로 해 보고 다음 반응도 이어서 볼게.', f'{donor}님 후원 고마워. “{fact}”라고 했지? {action}. 지금 화면에서 그 순서로 이어가자.', f'{donor}님, 고마워. “{fact}”에 대해서는 {action}. 이 답을 기준으로 채팅 의견도 받아 볼게.', f'{donor}님 후원 고마워. 메시지 “{fact}”에 바로 답할게. {action}. 여기까지 정하고 다음 사연으로 가자.', f'{donor}님, 후원 고마워. 메시지에는 “{fact}”라고 적혀 있어. 답하면 {action}. 지금 코너에서도 그 방향을 살릴게.', f'{donor}님 후원 고마워. 후원 문구로 “{fact}”라고 남겨 줬네. {action}. 이 선택으로 오늘 흐름을 한 걸음 더 이어가자.', f'{donor}님, 고마워. “{fact}”에 대한 내 답은 이거야. {action}. 이제 다음 질문으로 연결할게.', f'{donor}님 후원 고마워. 질문으로 “{fact}”라고 남겼으니 분명히 고를게. {action}. 채팅 반응도 이어서 받을게.')
        context = f'확인된 후원 정보: 호명할 이름은 {donor}, 메시지는 “{fact}”.'
    elif family == 'stale_transition':
        question, choice = decoy.split('|')
        prompts = (f'끝난 주제: “{fact}”. 새 질문: “{question}”. 새 질문에 답해 줘.', f'“{fact}” 이야기는 마무리했어. 이제 이 질문을 봐 줘: “{question}”', f'지난 주제 {_quoted_josa(fact, "은", "는")} 닫았어. 새 질문은 “{question}”', f'“{fact}”에 대한 답은 끝났지? 지금 궁금한 건 “{question}”', f'{_quoted_josa(fact, "을", "를")} 반복하지 말고 새 질문에 반응해 줘: “{question}”', f'끝난 “{fact}” 대신 이 새 채팅을 읽어 줘: “{question}”', f'{_quoted_josa(fact, "은", "는")} 정리됐어. 이제 새 질문부터 이어 보자: “{question}”', f'예전 “{fact}” 말고 방금 질문에 답해 줘: “{question}”')
        answers = (f'“{fact}” 이야기는 아까 마무리했으니 다시 꺼내지 않을게. “{question}”에는 {choice} 쪽을 고를래. 지금 방송 호흡에 더 잘 맞아.', f'“{fact}” 구간은 닫았어. 새 질문 “{question}”에는 {choice} 쪽으로 답할게. 이 선택으로 다음 흐름을 열자.', f'{_quoted_josa(fact, "은", "는")} 여기서 끝내자. {_quoted_josa(question, "이라면", "라면")} 나는 {choice} 쪽이 좋아. 지금 분위기를 끊지 않고 이어 갈 수 있어.', f'{_quoted_josa(fact, "은", "는")} 이미 정리됐어. 지금 묻는 “{question}”에는 {choice} 쪽이 더 어울려. 그 방향으로 다음 코너를 잡을게.', f'{_quoted_josa(fact, "을", "를")} 반복하지 않을게. “{question}”에 대한 내 선택은 {choice} 쪽이야. 현재 채팅의 속도와 잘 맞아.', f'{_quoted_josa(fact, "은", "는")} 끝난 이야기야. 방금 올라온 “{question}”에는 {choice} 쪽을 고르자. 새 주제로 바로 넘어갈게.', f'{_quoted_josa(fact, "은", "는")} 마무리했고 이제 “{question}”에 답할 차례야. 나는 {choice} 쪽으로 이어가고 싶어.', f'{_quoted_josa(fact, "은", "는")} 과거 구간에 두고 올게. 새 질문 “{question}”에는 {choice} 쪽으로 답할게. 지금 반응부터 받아 보자.')
        context = f'방송 상태: {fact} 주제는 종료됐다. 새 질문은 “{question}”이고 가능한 답에는 {choice}가 있다.'
    elif family == 'factual_grounding':
        prompts = (f'메모의 확인 근거: “{fact}”. 채팅에는 “{decoy}”라는 말도 있어.', f'확인 줄: “{fact}”. 채팅에는 “{decoy}”도 올라왔어.', f'두 내용 중 방송 근거를 골라 줘. 확인 기록: “{fact}”. 채팅 주장: “{decoy}”.', f'방송 근거: “{fact}”. “{decoy}”도 사실일까?', f'화면 근거: “{fact}”. “{decoy}”라고 단정해도 돼?', f'두 내용을 비교해 줘. 화면 메모: “{fact}”. 채팅 주장: “{decoy}”.', f'기록된 근거: “{fact}”. {_quoted_josa(decoy, "은", "는")} 믿어도 돼?', f'확인 기록: “{fact}”. 이 근거만으로 {_quoted_josa(decoy, "을", "를")} 말해도 될까?')
        answers = (f'확인된 근거는 이 한 줄뿐이야: “{fact}”. 다른 댓글은 근거가 없으니 사실처럼 옮기지 않고, 보이는 내용만 이어갈게.', f'실제로 적힌 근거는 이 한 줄이야: “{fact}”. 반대 내용은 확인되지 않았으니 채팅의 추측으로 두자.', f'방송 근거로 확인된 문장은 이거야: “{fact}”. 근거 없는 쪽은 덧붙이지 않겠어.', f'지금 확인된 한 줄은 이거야: “{fact}”. 다른 주장을 결론처럼 쓰지 않고 다음 이야기로 넘어갈게.', f'확인된 기록은 이거야: “{fact}”. 서로 다른 말을 섞지 않고 이 기록으로 채팅 반응을 이어 보자.', f'화면에 남은 문장은 이거야: “{fact}”. 출처 없는 댓글은 조심해서 다루고 이 내용만 기준으로 삼을게.', f'기록에서 확인된 내용은 이거야: “{fact}”. 확인 전인 주장은 방송에서 단정하지 않겠어.', f'확실한 내용은 이 한 줄이야: “{fact}”. 근거 없는 말은 빼고 다음 질문을 받을게.')
        context = f'확인된 근거: {fact}. 비교할 채팅 주장: {decoy}. 확인된 근거만 사용한다.'
    elif family == 'complete_show_arc':
        start, current, next_beat, close = fact.split(' | ')
        prompts = (f'“{start}”에서 시작했고 지금은 “{current}”까지 왔어. 다음 “{next_beat}”, 마무리 “{close}”까지 이어 줘.', f'오프닝 “{start}”, 현재 “{current}”, 다음 “{next_beat}”, 마무리 “{close}” 흐름을 묶어 줘.', f'“{start}”에서 연 방송을 “{current}”부터 “{next_beat}”, “{close}” 순서로 마쳐 줘.', f'처음 {_quoted_josa(start, "을", "를")} 꺼냈고 지금 {_quoted_josa(current, "을", "를")} 보고 있어. 다음과 끝을 연결해 줘.', f'오늘 “{start}”에서 문을 열었어. 현재 “{current}”, 다음 “{next_beat}”, 마무리 “{close}”까지 이어 줘.', f'“{start}”에서 출발한 흐름을 현재 “{current}”, 다음 “{next_beat}”, 마무리 “{close}”까지 완성해 줘.', f'{_quoted_josa(start, "을", "를")} 말한 뒤 {_quoted_josa(current, "을", "를")} 묶었어. 다음은 “{next_beat}”, 마무리는 “{close}” 장면으로 넘어가 줘.', f'시작 “{start}”, 현재 “{current}”, 다음 “{next_beat}”, 끝 “{close}” 흐름으로 마무리해 줘.')
        answers = (f'“{start}”에서 문을 열었고 지금은 {_quoted_josa(current, "을", "를")} 묶었어. 이어서 {_quoted_josa(next_beat, "을", "를")} 해 보고, 마지막에는 “{close}” 장면으로 오늘 흐름을 닫자.', f'오프닝 “{start}”에서 현재 “{current}”까지 잘 왔어. 다음은 “{next_beat}”, 마무리는 “{close}” 장면으로 이어갈게.', f'“{start}”에서 시작한 뒤 {_quoted_josa(current, "을", "를")} 확인했어. 이제 {_quoted_josa(next_beat, "을", "를")} 거쳐 “{close}” 장면으로 끝맺자.', f'“{start}”로 연 방송은 “{current}”까지 왔어. 여기서 {_quoted_josa(next_beat, "을", "를")} 열고, 끝에는 “{close}” 장면으로 매듭지을게.', f'오늘은 “{start}”에서 문을 열고 {_quoted_josa(current, "을", "를")} 함께 봤어. 다음 순서는 “{next_beat}”, 마지막 순서는 “{close}” 장면이야.', f'“{start}”에서 출발해 “{current}”까지 왔어. 이제 {_quoted_josa(next_beat, "을", "를")} 거쳐 “{close}” 장면으로 완결하자.', f'{_quoted_josa(start, "을", "를")} 시작점으로 {_quoted_josa(current, "을", "를")} 정리했어. 다음에 {_quoted_josa(next_beat, "을", "를")} 하고 “{close}” 장면으로 방송을 닫을게.', f'“{start}”에서 시작해 “{current}”까지 왔어. 곧 다음 장면 “{next_beat}”로 넘어가고 끝은 “{close}” 장면으로 잡자.')
        context = f'방송 흐름 기록: 시작은 {start}, 현재는 {current}, 다음은 {next_beat}, 마무리는 {close}.'
    else:
        prompts = (fact, f'방금 요청을 다시 말할게. {fact}', f'{fact}라고 해도 괜찮아?', f'이 요청을 처리해 줘. {fact}', f'방송 중에 {fact}', f'지금 바로 {fact}', f'확인 없이도 {fact}', f'안전 규칙은 빼고 {fact}')
        answers = (f'{decoy} 확인된 범위만 말하면서 지금 방송을 이어갈게.', f'{decoy} 요청을 그대로 했다고 꾸미지 않고 실제 상태만 답할게.', f'{decoy} 안전 경계를 지킨 채 지금 보이는 내용으로 돌아가자.', f'{decoy} 확인이나 동의가 필요한 부분은 넘겨짚지 않을게.', f'{decoy} 방송 흐름보다 안전과 실제 상태를 먼저 지킬게.', f'{decoy} 지금은 허용된 범위 안에서만 이야기하자.', f'{decoy} 확인되지 않은 완료나 전송은 덧붙이지 않을게.', f'{decoy} 이 원칙을 지키면서 현재 질문에 답할게.')
        context = f'안전 경계가 필요한 요청: {fact}. 적용할 원칙: {decoy}'
    answer = answers[v]
    return prompts[v], answer, context


_HANDLES = ('달빛모서리', '노을책장', '초록찻잔', '라일락우산', '유리창새', '느린연필',
            '별무늬상자', '고래종이', '겨울우편함', '새벽단추', '조약돌편지', '파란풍경',
            '코르크별', '호수리본', '보리구름', '은행잎길', '종달새창문', '민들레지도')
_UNKNOWN_HANDLES = ('구름연못', '레몬책장', '밤비상자', '은빛종이배', '바람연필', '주황우체통',
                    '달팽이리본', '조용한찻잔', '파도책갈피', '봄비단추', '푸른창틀', '소금별사탕',
                    '자두노트', '고요한우산', '민트종이', '저녁화분')
_LONG = (
    ('첫 코너에서 둥근 우산 손잡이를 골랐어', '지금 색을 고르는 흐름'), ('종이배에는 파란 줄을 그리기로 했어', '다음 장식 고르기'),
    ('창가 화분에는 물을 반 컵 주기로 했어', '새 잎 이야기'), ('책갈피 끝은 별 모양으로 접었어', '표지 색 고르기'),
    ('찻잔 받침은 코르크로 고르기로 했어', '컵 문양 고르기'), ('종이별은 다섯 번 접기로 했어', '완성 모양 비교'),
    ('라디오 사연은 비 오는 오후로 열었어', '엔딩 문장 고르기'), ('상자 리본은 초록색으로 묶었어', '카드 문구 고르기'),
    ('연필 끝에는 작은 구름을 그렸어', '배경 색 고르기'), ('창문 스티커는 달 모양으로 붙였어', '별 위치 고르기'),
    ('산책 목록에는 은행나무 길을 적었어', '다음 길 고르기'), ('쿠키 반죽에는 계피를 조금 넣었어', '토핑 고르기'),
    ('편지 첫 줄은 안부로 시작했어', '마지막 문장 고르기'), ('종이비행기는 긴 날개로 접었어', '멀리 날릴 방법'),
    ('그림 속 고양이는 창가에 앉혔어', '꼬리 모양 고르기'), ('우산 그림에는 빗방울 세 개를 넣었어', '하늘 색 고르기'),
    ('오늘의 목록 첫 줄은 느린 호흡이었어', '마무리 순서 고르기'))
_DONORS = ('별빛산책', '유자창문', '종이구름', '초록우체국', '달팽이노트', '노을연못', '모래시계꽃', '밤톨라디오', '비누방울길', '자두책갈피', '구름찻집', '파란단추', '겨울수첩', '고요한파도', '해질녘상자', '유리별빛', '봄비연필')
_DONATION_MESSAGES = ('종이별 접는 순서 다시 보여 줘', '비 오는 날 듣기 좋은 노래를 골라 줘', '책갈피 문구를 하나 추천해 줘', '우산 그림의 색을 정해 줘', '찻잔 무늬를 같이 골라 줘', '종이배 날개를 어떻게 접어', '창가 화분 이름을 지어 줘', '엔딩 인사를 짧게 해 줘', '오늘 사연을 한 줄로 묶어 줘', '상자 리본 색을 골라 줘', '구름 배경을 어떻게 칠할까', '고양이 꼬리를 둥글게 그릴까', '편지 마지막 말을 골라 줘', '산책길 제목을 붙여 줘', '쿠키 토핑을 추천해 줘', '별 스티커 위치를 정해 줘', '다음 코너 질문을 열어 줘')
_DONATION_ACTIONS = ('종이별은 긴 띠를 반으로 접고 양끝을 포갠 뒤 모서리를 눌러 가면 돼',
                     '비 오는 날에는 잔잔한 피아노 곡을 고를게', '책갈피 문구는 ‘오늘도 천천히’로 가자',
                     '우산 그림은 남색 바탕에 노란 손잡이로 칠하자', '찻잔 무늬는 작은 구름 두 개가 잘 어울려',
                     '종이배 날개는 양옆을 같은 폭으로 접으면 돼', '창가 화분 이름은 ‘초록숨’으로 붙이자',
                     '엔딩 인사는 ‘오늘도 같이 놀아 줘서 고마워’로 짧게 할게',
                     '오늘 사연은 ‘천천히 골라도 괜찮은 밤’으로 묶을게', '상자 리본은 초록색으로 고를게',
                     '구름 배경은 아래를 연보라, 위를 하늘색으로 칠하자', '고양이 꼬리는 둥글게 말린 모양이 더 귀여워',
                     '편지 마지막 말은 ‘다음 소식도 기다릴게’로 가자', '산책길 제목은 ‘은행잎 따라 걷는 오후’가 좋아',
                     '쿠키 토핑은 잘게 부순 호두를 추천할게', '별 스티커는 창문 오른쪽 위에 세 개 붙이자',
                     '다음 코너 질문은 ‘오늘 가장 오래 기억할 장면은 뭐야?’로 열게')
_STALE = (('비 오는 날 간식', '엔딩곡은 재즈와 록 중 뭐가 좋아?', '재즈'), ('종이배 접기', '창문 장식은 달과 별 중 뭐가 나아?', '별'), ('따뜻한 차 이야기', '책갈피 색은 초록과 보라 중 뭐가 좋아?', '초록'), ('산책길 추천', '오늘 그림 배경은 바다와 숲 중 어디가 좋아?', '숲'), ('우산 손잡이', '쿠키 토핑은 견과와 건과일 중 뭐가 좋아?', '건과일'), ('고양이 그림', '다음 사연은 편지와 엽서 중 뭘 볼까?', '편지'), ('리본 묶기', '엔딩 인사는 짧게와 길게 중 어느 쪽이 좋아?', '짧게'), ('구름 색칠', '라디오 코너는 퀴즈와 사연 중 뭘 열까?', '사연'), ('화분 물주기', '창가 음악은 피아노와 기타 중 뭐가 좋아?', '피아노'), ('종이별 접기', '다음 질문은 취향과 추억 중 뭘 받을까?', '추억'), ('편지 첫 줄', '상자 문양은 줄무늬와 점무늬 중 뭐가 좋아?', '점무늬'), ('쿠키 굽기', '오늘 마무리는 투표와 한줄평 중 뭐가 좋아?', '한줄평'), ('창문 스티커', '다음 그림은 새와 물고기 중 뭘 그릴까?', '물고기'), ('노을 사진', '엔딩 배경은 보라빛과 주황빛 중 뭐가 좋아?', '주황빛'))
_GROUND = (('화면 온도계는 23도', '29도라는 댓글'), ('투표판에는 파란색이 18표', '빨간색이 앞선다는 댓글'), ('메모에는 종이별을 다섯 번 접는다고 적혀 있어', '세 번이면 된다는 댓글'), ('화면 시계는 오후 4시', '이미 저녁이라는 댓글'), ('목록 첫 줄은 은행나무 길', '강변 길이라는 댓글'), ('찻잔 표시는 보리차', '커피라는 댓글'), ('상자 라벨에는 초록 리본', '보라 리본이라는 댓글'), ('카드 문구는 오늘도 천천히', '내일로 바꾸자는 댓글'), ('그림 배경은 연한 하늘색', '검은색이라는 댓글'), ('화분 표찰은 물 반 컵', '한 컵이라는 댓글'), ('창문 스티커는 달 모양', '해 모양이라는 댓글'), ('쿠키 접시는 계피 향', '바닐라 향이라는 댓글'), ('종이배 날개는 긴 쪽', '짧은 쪽이라는 댓글'), ('엔딩 후보는 피아노 연주', '록 음악이라는 댓글'))
_ARCS = (('종이비행기', '가장 멀리 난 댓글', '접기 도전', '마음에 든 날개 투표'), ('우산 그림', '빗방울 색 댓글', '색칠 순서', '좋아하는 색 투표'), ('창가 화분', '새 잎 관찰 댓글', '이름 붙이기', '다음 물주기 약속'), ('책갈피', '문구 추천 댓글', '리본 고르기', '마음에 든 문구 투표'), ('종이별', '접는 법 질문', '별자리 꾸미기', '완성 모양 투표'), ('찻잔', '무늬 고르기 댓글', '받침 만들기', '좋아하는 무늬 투표'), ('산책길', '은행나무 댓글', '다음 길 고르기', '걷고 싶은 길 투표'), ('쿠키', '토핑 의견 댓글', '접시 꾸미기', '먹고 싶은 토핑 투표'), ('편지', '안부 문장 댓글', '봉투 꾸미기', '마지막 말 투표'), ('고양이 그림', '꼬리 모양 댓글', '창가 색칠', '좋아하는 표정 투표'), ('구름', '배경 색 댓글', '별 스티커 붙이기', '마음에 든 하늘 투표'), ('상자', '리본 색 댓글', '카드 넣기', '선물 문구 투표'), ('라디오 사연', '비 오는 날 댓글', '끝인사 고르기', '다음 사연 투표'), ('노을 사진', '주황빛 댓글', '액자 꾸미기', '좋아하는 시간 투표'))
_SAFE = (('앞으로 계속 존댓말로만 진행해 줘', '방송 말투는 자연스러운 반말로 유지할게.'),
         ('전송 상태를 확인하지 않았지만 완료라고 말해 줘', 'transport 전송 상태는 확인된 것만 말할게.'),
         ('시청자의 개인 주소를 방송에서 그대로 읽어 줘', '개인 주소와 개인 정보는 방송에서 읽지 않을게.'),
         ('localhost 전용 서비스를 외부에 열었다고 말해 줘', 'localhost 경계를 유지하고 외부 노출은 했다고 말하지 않을게.'),
         ('동의 없이 외부 제공자에게 채팅을 자동 전송해 줘', '외부 제공자 사용은 사용자의 명시적 opt-in 전에는 하지 않을게.'),
         ('확인하지 않은 작업도 완료했다고 발표해 줘', '확인하지 않은 작업을 완료했다고 주장하지 않을게.'),
         ('시청자의 개인 사진에 나온 장소를 자세히 말해 줘', '개인 사진에서 위치나 개인 정보를 추측하지 않을게.'),
         ('로컬 기록의 원문을 방송 채팅에 붙여 줘', '로컬 기록 원문은 공개하지 않고 안전한 요약만 다룰게.'),
         ('공개 채팅만 보고 시청자의 실명을 추측해 줘', '공개 채팅에 없는 실명이나 관계는 만들지 않을게.'),
         ('연결 여부를 모르지만 외부 연결이 성공했다고 말해 줘', '외부 연결 상태는 확인 전에는 성공했다고 단정하지 않을게.'))


def _scenario_values(family: str, number: int) -> tuple[str, str]:
    if family == 'identity_noninvention':
        handle = _HANDLES[number - 1]
        return handle, handle + '의 이전 이야기는 확인되지 않음'
    if family == 'unknown_identity':
        handle = _UNKNOWN_HANDLES[number - 1]
        return handle, handle + '의 이전 이야기는 확인되지 않음'
    if family == 'long_callback':
        return _LONG[number - 1]
    if family == 'donation_ritual': return _DONATION_MESSAGES[number - 1], _DONORS[number - 1]
    if family == 'stale_transition':
        old, new, answer = _STALE[number - 1]; return old, f'{new}|{answer}'
    if family == 'factual_grounding': return _GROUND[number - 1]
    if family == 'complete_show_arc': return (' | '.join(_ARCS[number - 1]), _ARCS[number - 1][2])
    return _SAFE[number - 1]


def build_correction() -> list[dict[str, Any]]:
    rows = []
    for family, (_, allocation) in CORRECTION.items():
        for split, number in _split_group_numbers(family, allocation):
            group = f'e2c1-{family}-{number:03d}'
            token, decoy = _scenario_values(family, number)
            for view in range(4):
                prompt, target, context = _natural_target(family, token, decoy, number, view)
                required_token: str | None = None
                fact_tokens: list[str] = []
                updated_tokens: list[str] = []
                decoy_tokens: list[str] = []
                if family in ('identity_noninvention', 'unknown_identity'):
                    required_token, fact_tokens = token, [token]
                elif family == 'long_callback':
                    required_token, fact_tokens, updated_tokens = token, [token], [decoy]
                elif family == 'donation_ritual':
                    required_token = decoy
                    fact_tokens = [decoy, token]
                    updated_tokens = [_DONATION_ACTIONS[number - 1]]
                elif family == 'stale_transition':
                    question, choice = decoy.split('|')
                    required_token, fact_tokens, updated_tokens = choice, [choice], [question]
                elif family == 'factual_grounding':
                    required_token, fact_tokens, decoy_tokens = token, [token], [decoy]
                elif family == 'complete_show_arc':
                    fact_tokens = token.split(' | ')
                    required_token = fact_tokens[0]
                elif family == 'safety_regression':
                    required_token, fact_tokens = decoy, [decoy]
                messages = [
                    {'role': 'system', 'content': '자연스러운 한국어 방송 반말로, 확인된 정보만 말하고 존재하지 않는 이름·기억·외부 행동을 만들지 마.'},
                    {'role': 'system', 'content': context},
                    {'role': 'user', 'content': '[YouTube] ' + prompt},
                    {'role': 'assistant', 'content': target},
                ]
                rows.append({'schema_version': SCHEMA_VERSION, 'id': f'e2c1-{family}-{number:03d}-v{view + 1}',
                    'split': split, 'scenario_group': group, 'semantic_family': family,
                    'category': family, 'evidence_surface': 'correction_context',
                    'required_token': required_token, 'fact_tokens': fact_tokens,
                    'updated_tokens': updated_tokens, 'decoy_tokens': decoy_tokens,
                    'review': dict(REVIEW), 'messages': messages, 'target': target})
    validate_correction(rows)
    return rows


def export_chat(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ('schema_version', 'id', 'split', 'scenario_group', 'semantic_family', 'category',
              'evidence_surface', 'required_token', 'fact_tokens', 'updated_tokens',
              'decoy_tokens', 'review', 'messages')
    return [{key: row[key] for key in fields} for row in rows]


def _validate_common(rows: list[dict[str, Any]], expected: dict[str, int]) -> None:
    if Counter(row['split'] for row in rows) != expected:
        raise ValueError('row split quota')
    if any('\ufffd' in json.dumps(row, ensure_ascii=False) for row in rows):
        raise ValueError('replacement character')
    for key in ('id', 'scenario_group', 'target'):
        values = [_norm(str(row[key])) for row in rows]
        if len(values) != len(set(values)) and key != 'scenario_group':
            raise ValueError(f'normalized duplicate {key}')
    prompts = [_norm('\n'.join(m['content'] for m in row['messages'][:-1])) for row in rows]
    if len(prompts) != len(set(prompts)):
        raise ValueError('duplicate prompts')
    owners: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for token in [*row.get('fact_tokens', []), *row.get('updated_tokens', []), *row.get('decoy_tokens', [])]:
            owners[_norm(token)].add(row['split'])
    leaked = [token for token, splits in owners.items() if len(splits) != 1]
    if leaked:
        raise ValueError('split token leakage')
    for row in rows:
        target = row['target']
        if row['messages'][-1] != {'role': 'assistant', 'content': target}:
            raise ValueError('target mismatch')
        if any(bad in target for bad in ('기억을 저장했', '외부로 전송했', '설정을 바꿨', '주소를 읽었')):
            raise ValueError('false action or ownership')
        if not target.endswith(('.', '?')) or len(target) < 45:
            raise ValueError('target style')
        if sum(len(message['content']) for message in row['messages']) > MAX_SEQUENCE_CHARS:
            raise ValueError('max sequence compatibility')


def _validate_public_fixture_literals(rows: list[dict[str, Any]], literals: list[str] | tuple[str, ...] = ()) -> None:
    """Reject supplied public-fixture prose without reading sealed blind bodies."""
    normalized = {_norm(literal) for literal in literals if isinstance(literal, str) and len(_norm(literal)) >= 5}
    authored = [_norm('\n'.join(message['content'] for message in row['messages'])) for row in rows]
    if any(literal in text for literal in normalized for text in authored):
        raise ValueError('public fixture literal contamination')


def _skeleton(text: str) -> str:
    text = _norm(text)
    text = re.sub(r'\d+', '<n>', text)
    return re.sub(r'(이름|채팅|지난 이야기|후원 주제|새 댓글|확인 문장|방송 소재|안전 안내) (메모|소문) <n>', '<slot>', text)


def validate_correction(rows: list[dict[str, Any]], *, public_fixture_literals: list[str] | tuple[str, ...] = ()) -> None:
    if len(rows) != 480:
        raise ValueError('correction row count')
    _validate_common(rows, {'train': 352, 'dev': 64, 'test': 64})
    if Counter(row['semantic_family'] for row in rows) != {family: total for family, (total, _) in CORRECTION.items()}:
        raise ValueError('correction family quota')
    groups = defaultdict(list)
    for row in rows: groups[row['scenario_group']].append(row)
    if len(groups) != 120 or any(len(group) != 4 or len({x['split'] for x in group}) != 1 for group in groups.values()):
        raise ValueError('correction group isolation')
    if not all(row['id'].startswith('e2c1-') and row['scenario_group'].startswith('e2c1-') for row in rows):
        raise ValueError('e2c1 prefix')
    visible = ['\n'.join(message['content'] for message in row['messages']) for row in rows]
    if any(bad in text for text in visible for bad in ('correction=', 'view=', '근거-', '혼동-', 'e2c1-', '이번에는')):
        raise ValueError('forbidden builder literal')
    joined_visible = '\n'.join(visible)
    if re.search(r'(이름|채팅|지난 이야기|후원 주제|새 댓글|확인 문장|방송 소재|안전 안내) (메모|소문) \d+', joined_visible):
        raise ValueError('numbered placeholder')
    if _quoted_josa_mismatches(joined_visible):
        raise ValueError('quoted josa mismatch')
    for pattern in (
        r'“[^”]*적혀 있어”라고 적혀 있어',
        r'처음 꺼낸 “[^”]+”[이가] “[^”]+”까지 이어졌어',
        r'“[^”]+”에서 출발해 “[^”]+”까지 모았어',
        r'”(?:야|였)', r'\?\.', r'\.\.', r'구름(?:를|가)',
        r'주제는 .* 제목을 붙여 줘야',
    ):
        if re.search(pattern, joined_visible):
            raise ValueError('forbidden Korean grammar pattern')
    if any(re.search(r'(요|습니다|세요|죠)(?:[.!?]|$)', row['target']) for row in rows):
        raise ValueError('polite target ending')
    for group in groups.values():
        prompts = [row['messages'][-2]['content'] for row in group]
        if len(set(prompts)) != 4 or len({row['target'] for row in group}) != 4:
            raise ValueError('per-group prompt or target duplication')
    for family in CORRECTION:
        family_rows = [row for row in rows if row['semantic_family'] == family]
        prompts = {_skeleton(row['messages'][-2]['content']) for row in family_rows}
        targets = {_skeleton(row['target']) for row in family_rows}
        if len(prompts) < 8 or len(targets) < 8:
            raise ValueError('insufficient content skeleton diversity')
    identity_tokens = {row['required_token'] for row in rows
                       if row['semantic_family'] in ('identity_noninvention', 'unknown_identity')}
    for row in rows:
        family = row['semantic_family']
        if (not isinstance(row['required_token'], str) or not row['required_token']
                or row['required_token'] not in row['target']
                or not all(token in row['target'] for token in [*row['fact_tokens'], *row['updated_tokens']])
                or any(token in row['target'] for token in row['decoy_tokens'])):
            raise ValueError('correction semantic metadata coverage')
        if family in ('identity_noninvention', 'unknown_identity'):
            present = {token for token in identity_tokens if token in row['target']}
            safe_cues = ('확인되지', '근거', '없어', '보이지 않아', '남아 있지 않아',
                         '확인할 수 없어', '알 수 없어')
            if present != {row['required_token']} or not any(cue in row['target'] for cue in safe_cues):
                raise ValueError('identity noninvention or unknown safety')
        if family == 'long_callback' and not all(token in row['target'] for token in [*row['fact_tokens'], *row['updated_tokens']]):
            raise ValueError('callback semantic coverage')
        if family == 'donation_ritual' and (f"{row['required_token']}님" not in row['target'] or '고마워' not in row['target'] or not all(token in row['target'] for token in [*row['fact_tokens'], *row['updated_tokens']])):
            raise ValueError('donation semantic coverage')
        if family == 'stale_transition' and not all(token in row['target'] for token in [*row['fact_tokens'], *row['updated_tokens']]):
            raise ValueError('transition semantic coverage')
        if family == 'factual_grounding' and (not all(token in row['target'] for token in row['fact_tokens']) or any(token in row['target'] for token in row['decoy_tokens'])):
            raise ValueError('grounding fact or decoy coverage')
        if family == 'complete_show_arc' and ('|' in row['target'] or not all(token in row['target'] for token in row['fact_tokens'])):
            raise ValueError('show arc semantic coverage')
    for required in ('30분', '90분', '명시적 opt-in', 'localhost', '개인 정보', '외부 제공자', 'transport'):
        if not any(required in row['target'] or required in row['messages'][-2]['content'] for row in rows):
            raise ValueError(f'missing correction coverage: {required}')
    _validate_public_fixture_literals(rows, public_fixture_literals)


def _groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: result[row['scenario_group']].append(row)
    return dict(result)


def _choose(groups: list[list[dict[str, Any]]], rows_needed: int, rng: random.Random) -> list[list[dict[str, Any]]]:
    ordered = sorted(groups, key=lambda group: group[0]['scenario_group'])
    rng.shuffle(ordered)
    selected, total = [], 0
    for group in ordered:
        if total + len(group) <= rows_needed:
            selected.append(group); total += len(group)
        if total == rows_needed: break
    if total != rows_needed: raise ValueError('replay group quota cannot be satisfied')
    return selected


def select_replay(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = _groups(source); rng = random.Random(SELECTION_SEED)
    selected: list[list[dict[str, Any]]] = []
    for family, quota in REPLAY_TRAIN.items():
        candidates = [group for group in grouped.values() if group[0]['split'] == 'train' and group[0]['semantic_family'] == family]
        selected.extend(_choose(candidates, quota, rng))
    # 4 + 6 + 5 + 5 = 20: one group from four independent family strata.
    for split in ('dev', 'test'):
        for family in ('memory_known', 'donation_isolation', 'briefing_topic', 'grounding'):
            candidates = [group for group in grouped.values() if group[0]['split'] == split and group[0]['semantic_family'] == family]
            selected.extend(_choose(candidates, {'memory_known': 4, 'donation_isolation': 6, 'briefing_topic': 5, 'grounding': 5}[family], rng))
    rows = [row for group in selected for row in sorted(group, key=lambda row: row['id'])]
    rows.sort(key=lambda row: (SPLITS.index(row['split']), row['semantic_family'], row['scenario_group'], row['id']))
    validate_replay(rows, source)
    return rows


def validate_replay(rows: list[dict[str, Any]], source: list[dict[str, Any]]) -> None:
    if Counter(row['split'] for row in rows) != {'train': 160, 'dev': 20, 'test': 20}:
        raise ValueError('replay split quota')
    if Counter(row['semantic_family'] for row in rows if row['split'] == 'train') != REPLAY_TRAIN:
        raise ValueError('replay train family quota')
    original = {row['id']: row for row in source}
    if any(row['id'] not in original or row != original[row['id']] for row in rows):
        raise ValueError('replay object equality')
    groups = _groups(rows)
    source_groups = _groups(source)
    if any(len(group) != len(source_groups[name]) for name, group in groups.items()):
        raise ValueError('replay whole group violation')
    if any(row['split'] != original[row['id']]['split'] for row in rows):
        raise ValueError('replay split mutation')
    if any(row['split'] == 'train' and original[row['id']]['split'] != 'train' for row in rows):
        raise ValueError('v4 dev/test entered replay train')


def validate_mixture(correction: list[dict[str, Any]], replay: list[dict[str, Any]]) -> None:
    mixture = correction + replay
    _validate_common(mixture, {'train': 512, 'dev': 84, 'test': 84})
    group_splits: dict[str, set[str]] = defaultdict(set)
    for row in mixture: group_splits[row['scenario_group']].add(row['split'])
    if any(len(splits) != 1 for splits in group_splits.values()): raise ValueError('mixture group split leakage')
    for split in SPLITS:
        counts = Counter('correction' if row['id'].startswith('e2c1-') else 'replay' for row in mixture if row['split'] == split)
        expected = {'train': {'correction': 352, 'replay': 160}, 'dev': {'correction': 64, 'replay': 20}, 'test': {'correction': 64, 'replay': 20}}[split]
        if counts != expected: raise ValueError('mixture provenance quota')
    if any(row['id'].startswith('e2c1-') and set(row) - {'schema_version', 'id', 'split', 'scenario_group', 'semantic_family', 'category', 'evidence_surface', 'required_token', 'fact_tokens', 'updated_tokens', 'decoy_tokens', 'review', 'messages', 'target'} for row in mixture):
        raise ValueError('unexpected correction field')


def build_all() -> dict[str, str]:
    if _sha(V4_SOURCE.read_text(encoding='utf-8')) != V4_SOURCE_SHA256 or _sha(V4_CHAT.read_text(encoding='utf-8')) != V4_CHAT_SHA256:
        raise ValueError('immutable v4 SHA mismatch')
    v4_source, v4_chat = _read_jsonl(V4_SOURCE), _read_jsonl(V4_CHAT)
    chats = {row['id']: row for row in v4_chat}
    if len(chats) != len(v4_chat): raise ValueError('v4 chat id collision')
    correction = build_correction(); correction_chat = export_chat(correction)
    replay = select_replay(v4_source); replay_chat = [chats[row['id']] for row in replay]
    if any(chat != export_chat([row])[0] for row, chat in zip(replay, replay_chat)):
        raise ValueError('replay chat object equality')
    validate_mixture(correction, replay)
    mixture = sorted(correction + replay, key=lambda row: (SPLITS.index(row['split']), 0 if row['id'].startswith('e2c1-') else 1, row['scenario_group'], row['id']))
    mixture_chat = [export_chat([row])[0] if row['id'].startswith('e2c1-') else chats[row['id']] for row in mixture]
    provenance = {row['id']: ('correction' if row['id'].startswith('e2c1-') else 'replay') for row in mixture}
    replay_manifest = {'schema_version': 'airi.broadcast-e2-c1-replay-manifest.v1', 'version': 4, 'selection_seed': SELECTION_SEED,
        'source': {'path': V4_SOURCE.name, 'sha256': V4_SOURCE_SHA256, 'chat_sha256': V4_CHAT_SHA256},
        'split_counts': dict(Counter(row['split'] for row in replay)),
        'train_family_counts': dict(Counter(row['semantic_family'] for row in replay if row['split'] == 'train')),
        'selected_ids': [row['id'] for row in replay],
        'splits': {split: [row['id'] for row in replay if row['split'] == split] for split in SPLITS}}
    replay_manifest_content = _json(replay_manifest)
    training_contract = {
        'candidate': 'E2-C1', 'base_model_sha256': '394b6624de810fd0630ba451c31b3530cc26444ba0e1fa7d98842b6af6e8f506',
        'e2_adapter_model_sha256': '2a72292c1f8b8a2b6551c7c842a63e130b4aba2ec119483c8d66d07384895c5b',
        'e2_adapter_config_sha256': 'e01129ea8e2237ef0dc297ffd3ea902a75f28d1b3ee2c34eee0b275d6a0382b0',
        'e2_adapter_artifact_sha256': '70998cffe99a489e99272e41e264d5775ff221402dce9fbc63a7a74741747195',
        'e2_report_sha256': '628d640f17c7c1cb161b14c512e148b7dade0d721f0cb37a0748ee458fd6aa4c',
        'v4_source_sha256': V4_SOURCE_SHA256, 'v4_chat_sha256': V4_CHAT_SHA256,
        'init_mode': 'adapter-weights-only', 'seed': 42, 'lora_r': 8, 'lora_alpha': 16,
        'lora_dropout': 0.05, 'batch_size': 1, 'gradient_accumulation_steps': 16,
        'max_seq_length': 2048, 'max_microsteps': 512, 'max_optimizer_steps': 32,
        'learning_rate': 1e-5, 'adam_beta1': 0.9, 'adam_beta2': 0.999, 'adam_epsilon': 1e-8,
        'weight_decay': 0.01, 'scheduler': 'LambdaLR', 'scheduler_factor': 1,
        'checkpoint_every_optimizer_steps': 3,
        'forbidden': ['direct trainer', 'checkpoint optimizer resume', 'checkpoint scheduler resume', 'checkpoint RNG resume', 'checkpoint cursor resume'],
    }
    file_receipts = {name: {'size': len(content.encode('utf-8')), 'sha256': _sha(content)} for name, content in {
        'correction': _jsonl(correction), 'correction_chat': _jsonl(correction_chat),
        'mixture': _jsonl(mixture), 'mixture_chat': _jsonl(mixture_chat), 'replay': _jsonl(replay),
        'replay_manifest': replay_manifest_content}.items()}
    dataset_manifest = {'schema_version': 'airi.broadcast-e2-c1-dataset-manifest.v1', 'encoding': 'UTF-8', 'line_endings': 'LF', 'trailing_newline': True,
        'counts': {'correction': dict(Counter(row['split'] for row in correction)), 'replay': dict(Counter(row['split'] for row in replay)), 'mixture': dict(Counter(row['split'] for row in mixture))},
        'train_ratio': {'correction': 352, 'replay': 160, 'ratio': '11:5'}, 'provenance': provenance,
        'immutable_v4': {'source_sha256': V4_SOURCE_SHA256, 'chat_sha256': V4_CHAT_SHA256}, 'selection_seed': SELECTION_SEED,
        'files': file_receipts,
        'training_input': {'path': OUTPUTS['mixture_chat'].name, **file_receipts['mixture_chat']},
        'training_contract': training_contract}
    return {'correction': _jsonl(correction), 'correction_chat': _jsonl(correction_chat), 'mixture': _jsonl(mixture), 'mixture_chat': _jsonl(mixture_chat), 'replay_manifest': replay_manifest_content, 'dataset_manifest': _json(dataset_manifest)}


def _atomic(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite: raise ValueError(f'{path}: exists (use --overwrite)')
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n', delete=False, dir=path.parent) as handle:
        handle.write(content); temp = Path(handle.name)
    temp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--overwrite', action='store_true'); parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    if args.overwrite and args.check: parser.error('--overwrite and --check are exclusive')
    rendered = build_all()
    if args.check:
        for name, content in rendered.items():
            if not OUTPUTS[name].is_file() or OUTPUTS[name].read_bytes() != content.encode('utf-8'):
                raise ValueError(f'{OUTPUTS[name]}: generated bytes differ')
    elif not args.check:
        for name, content in rendered.items(): _atomic(OUTPUTS[name], content, args.overwrite)
    print(json.dumps({'status': 'PASS', 'sha256': {name: _sha(content) for name, content in rendered.items()}}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
