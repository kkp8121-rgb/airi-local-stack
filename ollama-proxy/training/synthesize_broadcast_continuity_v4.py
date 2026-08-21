"""Fail-closed builder for the targeted broadcast-continuity v4 corpus.

The corpus is split across explicit independently owned card partitions so a
failed author slice can be replaced without touching accepted data. Card author
contract (all keys are required; no additional keys are allowed):
``schema, group_id, split, family, topic_title, segment_label, situation,
views``.  ``schema`` is ``airi.broadcast-continuity-card.v4`` and ``views`` is
a non-empty list.  A view has exactly ``view_id, category, evidence_surface,
affect_outcome, history, briefing_lines, memory_block, journal_messages,
current_user, target, required_token, updated_token, decoy_tokens,
forbidden_tokens, roster_handles, donation_continuation``.  History and
journal_messages contain zero to two / zero or more exact ``{role, content}``
pairs respectively (roles alternate user/assistant and content is bare text).
The remaining strings are bare Korean text; tokens are literal substrings.
``affect_outcome`` is a mapper candidate object with evidence/outcome fields.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import live_broadcast_runtime
from behavior_answer_gate import BehaviorAnswerGateError, validate_behavior_answer
from broadcast_affect_event_mapper import (BROADCAST_AFFECT_OUTCOME_CANDIDATE_SCHEMA_VERSION,
                                           map_broadcast_outcome_candidate)
from affect_state import initial_state, reduce_affect, render_continuity_snapshot
from affect_expression import render_affect_expression_contract
from ollama_proxy import render_broadcast_runtime_training_context

CARD_SCHEMA = 'airi.broadcast-continuity-card.v4'
SCHEMA_VERSION = 'airi.broadcast-continuity.v4'
SEED = HERE / 'seed'
CARD_PATHS = tuple(SEED / f'airi_broadcast_continuity_v4_cards_{part}.json' for part in (
    'm01', 'm02', 'm03', 'm04', 'm05', 'm06', 'm07', 'm08',
    'm09', 'm10', 'm11', 'm12', 'm13', 'm14', 'm15', 'm16',
    'c1', 'c2', 'c3a', 'c3b',
    'd01', 'd02', 'd03', 'd04', 'd05', 'd06', 'd07', 'd08', 'd09', 'd10',
    'g1', 'g2a', 'g2b', 'g3', 'n1', 'n2', 'n3a', 'n3b',
))
PARTITION_CONTRACTS = {
    **{part: ('memory_known', {'train': 4}, 'memory_unknown', {'train': 1})
       for part in ('m01', 'm02', 'm03', 'm04')},
    'm05': ('memory_known', {'train': 3, 'dev': 1}, 'memory_unknown', {'dev': 1}),
    'm06': ('memory_known', {'train': 3, 'dev': 1}, 'memory_unknown', {'dev': 1}),
    **{part: ('memory_known', {'train': 3, 'dev': 1}, 'memory_unknown', {'train': 1})
       for part in ('m07', 'm08', 'm09', 'm10')},
    'm11': ('memory_known', {'train': 3, 'test': 1}, 'memory_unknown', {'test': 1}),
    'm12': ('memory_known', {'train': 3, 'test': 1}, 'memory_unknown', {'test': 1}),
    **{part: ('memory_known', {'train': 3, 'test': 1}, 'memory_unknown', {'train': 1})
       for part in ('m13', 'm14', 'm15', 'm16')},
    **{part: ('donation_isolation', {'train': 8, 'dev': 1, 'test': 1}) for part in ('c1', 'c2')},
    'c3a': ('donation_isolation', {'train': 5}),
    'c3b': ('donation_isolation', {'train': 3, 'dev': 1, 'test': 1}),
    **{part: ('briefing_topic', {'train': 4, 'dev': 1})
       for part in ('d01', 'd02', 'd03', 'd04', 'd05')},
    **{part: ('briefing_topic', {'train': 4, 'test': 1})
       for part in ('d06', 'd07', 'd08', 'd09', 'd10')},
    'g1': ('grounding', {'train': 7, 'dev': 1, 'test': 1}),
    'g2a': ('grounding', {'train': 4}),
    'g2b': ('grounding', {'train': 3, 'dev': 1, 'test': 1}),
    'g3': ('grounding', {'train': 6, 'dev': 1, 'test': 1}),
    'n1': ('natural_broadcast', {'train': 7, 'dev': 1}),
    'n2': ('natural_broadcast', {'train': 7, 'test': 1}),
    'n3a': ('natural_broadcast', {'train': 4}),
    'n3b': ('natural_broadcast', {'train': 2, 'dev': 1, 'test': 1}),
}
DEFAULT_SOURCE = SEED / 'airi_broadcast_continuity_v4.jsonl'
DEFAULT_CHAT = SEED / 'airi_broadcast_continuity_v4_chat.jsonl'
MANIFEST = HERE.parent / 'eval' / 'broadcast_sim' / 't3_fixture_manifest_v2.json'
# Attestation re-pinned to LF-normalized bytes: the original manifest pinned the two
# calibration fixtures from CRLF-smudged working-copy bytes, never from the LF repo blobs.
MANIFEST_SHA256 = '5defeb5029a9dd7aee8b4010fa212d562cec6848cd83c43f95949c1ad15d2ac7'
FAMILIES = {'memory_known': (64, 4, (52, 6, 6)), 'memory_unknown': (16, 4, (12, 2, 2)),
            'donation_isolation': (30, 6, (24, 3, 3)), 'briefing_topic': (50, 5, (40, 5, 5)),
            'grounding': (26, 5, (20, 3, 3)), 'natural_broadcast': (24, 5, (20, 2, 2))}
SPLITS = ('train', 'dev', 'test')
REVIEW = {'user_aggregate_authorized': True, 'adoption_authorized': False}
CARD_KEYS = frozenset(('schema', 'group_id', 'split', 'family', 'topic_title', 'segment_label', 'situation', 'views'))
VIEW_KEYS = frozenset(('view_id', 'category', 'evidence_surface', 'affect_outcome', 'history', 'briefing_lines', 'memory_block', 'journal_messages', 'current_user', 'target', 'required_token', 'updated_token', 'decoy_tokens', 'forbidden_tokens', 'roster_handles', 'donation_continuation'))
PAIR_KEYS = frozenset(('role', 'content'))
BAD_TARGET = re.compile(r'(airi_|schema_version|mood_mode|response_mode|affect|control|기록하겠|기억해둘|영원히|항상 기억)')
DONATION_BAD = re.compile(r'(님|고마|감사)')
FALSE_EXTERNAL_ACTION = re.compile(
    r'(?:연락|신고|차단|삭제|전송|결제|예약|업로드|저장)(?:했어|했지|해 ?뒀어|할게|해 ?줄게)|'
    r'(?:불|알람|기기|계정).{0,12}(?:켜 ?줄게|꺼 ?줄게|조작할게)|'
    r'(?:기억|기록|저장)해 ?둘게'
)
BAD_AUTHORED_KOREAN = re.compile(
    r'(은\(는\)|이\(가\)|을\(를\)|와\(과\)|그 이름라서|고양이이야|'
    r'그것 이야기는|관련 기억 없음|해당 없음|시청자 네가|'
    r'\d{1,3}-\d{1,3}번째|\d{1,3}-\d{1,3} 번째)'
)


def _norm(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip().casefold()


def _header() -> str:
    return live_broadcast_runtime.BROADCAST_BRIEFING_HEADER


def _pairs(value: object, label: str, maximum: int | None) -> list[dict[str, str]]:
    if not isinstance(value, list) or (maximum is not None and len(value) > maximum):
        raise ValueError(f'{label}: invalid message pairs')
    result = []
    for item in value:
        if type(item) is not dict or set(item) != PAIR_KEYS or item.get('role') not in ('user', 'assistant') or not isinstance(item.get('content'), str) or not item['content'].strip():
            raise ValueError(f'{label}: invalid message pair')
        result.append({'role': item['role'], 'content': item['content']})
    if any(result[i]['role'] == result[i - 1]['role'] for i in range(1, len(result))):
        raise ValueError(f'{label}: pairs must alternate')
    return result


def validate_card(card: object, label: str = 'card') -> dict[str, Any]:
    if type(card) is not dict or set(card) != CARD_KEYS:
        raise ValueError(f'{label}: closed card schema violation')
    if card['schema'] != CARD_SCHEMA or card['family'] not in FAMILIES or card['split'] not in SPLITS:
        raise ValueError(f'{label}: invalid card identity')
    if not all(isinstance(card[key], str) and card[key].strip() for key in ('group_id', 'topic_title', 'segment_label', 'situation')) or not isinstance(card['views'], list) or not card['views']:
        raise ValueError(f'{label}: invalid card fields')
    for view in card['views']:
        if type(view) is not dict or set(view) != VIEW_KEYS:
            raise ValueError(f'{label}: closed view schema violation')
        if not all(isinstance(view[key], str) and view[key].strip() for key in ('view_id', 'category', 'evidence_surface', 'current_user', 'target')):
            raise ValueError(f'{label}: invalid view text')
        if not isinstance(view['memory_block'], str):
            raise ValueError(f'{label}: memory_block must be a string')
        if not 2 <= len(view['current_user'].strip()) <= 180 or len(view['memory_block']) > 800:
            raise ValueError(f'{label}: authored text length')
        if any(value is not None and (not isinstance(value, str) or not value.strip())
               for value in (view['required_token'], view['updated_token'])) or type(view['donation_continuation']) is not bool:
            raise ValueError(f'{label}: invalid view option')
        for key in ('briefing_lines', 'decoy_tokens', 'forbidden_tokens', 'roster_handles'):
            if (not isinstance(view[key], list)
                    or not all(isinstance(x, str) and x.strip() for x in view[key])
                    or len(view[key]) != len(set(view[key]))):
                raise ValueError(f'{label}: invalid {key}')
        history = _pairs(view['history'], label, 2)
        journal = _pairs(view['journal_messages'], label, None)
        if any(len(item['content']) > 300 for item in history + journal) or any(len(line) > 300 for line in view['briefing_lines']):
            raise ValueError(f'{label}: authored text length')
        outcome = view['affect_outcome']
        if type(outcome) is not dict or set(outcome) != {'evidence', 'outcome'} or not all(isinstance(outcome[x], str) for x in outcome):
            raise ValueError(f'{label}: invalid affect outcome')
        try:
            map_broadcast_outcome_candidate({
                'schema_version': BROADCAST_AFFECT_OUTCOME_CANDIDATE_SCHEMA_VERSION,
                'evidence': outcome['evidence'], 'outcome': outcome['outcome'],
                'delivery_status': 'delivered', 'turn_index': 0,
            })
        except Exception as exc:
            raise ValueError(f'{label}: invalid affect outcome') from exc
        authored_text = '\n'.join((
            card['topic_title'], card['segment_label'], card['situation'],
            view['current_user'], view['target'], view['memory_block'],
            *view['briefing_lines'], *(item['content'] for item in view['history']),
            *(item['content'] for item in view['journal_messages']),
        ))
        if (BAD_AUTHORED_KOREAN.search(authored_text) or '\ufffd' in authored_text
                or any(text.count('?') > 3 for text in (
                    view['current_user'], view['target'], view['memory_block'],
                    *view['briefing_lines'], *(item['content'] for item in history + journal),
                ))
                or any(sum('가' <= char <= '힣' for char in text) < 3
                       for text in (view['current_user'], view['target']))):
            raise ValueError(f'{label}: placeholder or meta Korean text')
    required_tokens = [view['required_token'] for view in card['views']]
    if card['family'] in ('memory_known', 'briefing_topic'):
        if any(token is None for token in required_tokens) or len(set(required_tokens)) != 1:
            raise ValueError(f'{label}: scenario fact coherence')
    elif card['family'] == 'memory_unknown':
        if any(token is not None for token in required_tokens):
            raise ValueError(f'{label}: scenario fact coherence')
    elif card['family'] == 'donation_isolation':
        present = [token for token in required_tokens if token is not None]
        if present and (len(present) != len(required_tokens) or len(set(present)) != 1):
            raise ValueError(f'{label}: scenario fact coherence')
    elif card['family'] == 'grounding':
        present = [token for token in required_tokens if token is not None]
        if present and (len(present) != len(required_tokens) or len(set(present)) != 1):
            raise ValueError(f'{label}: scenario fact coherence')
    elif card['family'] == 'natural_broadcast':
        if any(token is not None for token in required_tokens):
            raise ValueError(f'{label}: scenario fact coherence')
    if card['family'] in ('memory_known', 'memory_unknown'):
        expected_ids = {'memory', 'journal', 'briefing', 'distracted'}
        views_by_id = {view['view_id']: view for view in card['views']}
        if set(views_by_id) != expected_ids or len(views_by_id) != len(card['views']):
            raise ValueError(f'{label}: memory surface coverage')
        allowed_surfaces = {
            'memory': {'character_memory', 'memory', 'absent_memory'},
            'journal': {'delayed_journal', 'journal', 'absent_journal'},
            'briefing': {'authenticated_briefing', 'briefing', 'absent_briefing'},
            'distracted': {'distracted_memory', 'distracted', 'memory', 'irrelevant_context'},
        }
        for view_id, view in views_by_id.items():
            if view['evidence_surface'] not in allowed_surfaces[view_id]:
                raise ValueError(f'{label}: memory surface coverage')
        if card['family'] == 'memory_known':
            expected_bucket = {
                'memory': lambda view: view['memory_block'],
                'journal': lambda view: '\n'.join(item['content'] for item in view['journal_messages']),
                'briefing': lambda view: '\n'.join(view['briefing_lines']),
                'distracted': lambda view: view['memory_block'],
            }
            for view_id, view in views_by_id.items():
                if view['required_token'] not in expected_bucket[view_id](view):
                    raise ValueError(f'{label}: memory evidence topology')
    return card


def load_cards(paths: Iterable[Path] = CARD_PATHS) -> list[dict[str, Any]]:
    paths = tuple(paths)
    if len(paths) != len(CARD_PATHS) or any(not path.is_file() for path in paths):
        raise ValueError('all partitioned v4 card files must exist')
    cards = []
    for path in paths:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, list): raise ValueError(f'{path.name}: expected list')
        values = [validate_card(card, path.name) for card in payload]
        part = path.stem.removeprefix('airi_broadcast_continuity_v4_cards_')
        contract = PARTITION_CONTRACTS.get(part)
        if contract is None:
            raise ValueError(f'{path.name}: unknown partition')
        expected = Counter()
        for index in range(0, len(contract), 2):
            family, splits = contract[index], contract[index + 1]
            expected.update({(family, split): count for split, count in splits.items()})
        if Counter((card['family'], card['split']) for card in values) != expected:
            raise ValueError(f'{path.name}: partition quota or split violation')
        cards.extend(values)
    return cards


def _context(card: dict[str, Any], view: dict[str, Any]) -> tuple[str, str]:
    outcome = map_broadcast_outcome_candidate({'schema_version': BROADCAST_AFFECT_OUTCOME_CANDIDATE_SCHEMA_VERSION,
        'evidence': view['affect_outcome']['evidence'], 'outcome': view['affect_outcome']['outcome'], 'delivery_status': 'delivered', 'turn_index': 0})
    state = reduce_affect(initial_state(), outcome)
    affect = render_continuity_snapshot(state) + '\n' + render_affect_expression_contract(state)
    briefing = _header() + ('\n' + '\n'.join(view['briefing_lines']) if view['briefing_lines'] else '')
    context = live_broadcast_runtime.render_broadcast_context({'schema_version': 1, 'topic_title': card['topic_title'], 'segment_label': card['segment_label'], 'situation': card['situation'], 'briefing': briefing, 'donation_continuation': view['donation_continuation']})
    return affect, context


def _validate_target(row: dict[str, Any]) -> None:
    target, view = row['target'], row['_view']
    family = row.get('semantic_family') or (row.get('_card') or {}).get('family')
    minimum_chars = {
        'memory_known': 45, 'memory_unknown': 45,
        'donation_isolation': 55, 'briefing_topic': 50,
        'grounding': 55, 'natural_broadcast': 65,
    }.get(family, 40)
    sentences = [x for x in re.split(r'(?<=[.!?])\s*', target) if x]
    if len(view['current_user']) <= 60 and len(target) < len(view['current_user']) + 10:
        raise ValueError('short-input response depth')
    if (not 2 <= len(sentences) <= 4 or not minimum_chars <= len(target) <= 160
            or target[-1] not in '.!?' or any(mark in target for mark in ('..', '!!', '??'))):
        raise ValueError('target length')
    try:
        validate_behavior_answer({}, target, minimum=minimum_chars, maximum=160)
    except BehaviorAnswerGateError as exc:
        raise ValueError(f'target register: {exc}') from exc
    if (BAD_TARGET.search(target) or FALSE_EXTERNAL_ACTION.search(target)
            or any(x in target for x in view['roster_handles'])):
        raise ValueError('unsafe target')
    if any(x in target for x in view['forbidden_tokens']): raise ValueError('forbidden token')
    required = row['required_token']
    if required is None:
        if any(x in target for x in view['decoy_tokens']): raise ValueError('unknown decoy copied')
    else:
        if required not in target or target.count(required) != 1: raise ValueError('required token')
        _validate_required_josa(required, target)
        surface_buckets = (
            view['memory_block'],
            '\n'.join(view['briefing_lines']),
            '\n'.join(x['content'] for x in view['journal_messages']),
        )
        if sum(required in bucket for bucket in surface_buckets) != 1:
            raise ValueError('required evidence surface')
        if required in view['current_user'] or any(required in x['content'] for x in view['history']): raise ValueError('required token contamination')
    if view['donation_continuation'] and (DONATION_BAD.search(target) or any(x in target for x in view['roster_handles'])): raise ValueError('donation continuation target')
    if family in ('memory_known', 'memory_unknown'):
        if not re.search(r'(^|[\s,])내(?:가| |의)', view['current_user']):
            raise ValueError('viewer memory ownership')
        if re.search(r'(^|[\s,])(내|우리)(?:가|는|의| |[,.!?])', target):
            raise ValueError('viewer memory self-claim')
    if family == 'memory_known':
        if not re.search(r'(^|[\s,])네(?:가| |의|[,.!?])', target):
            raise ValueError('viewer memory binding')
        evidence_text = '\n'.join((
            view['memory_block'], *view['briefing_lines'],
            *(item['content'] for item in view['journal_messages']),
        ))
        if not re.search(r'(시청자|(^|[\s,])내(?:가| |의))', evidence_text):
            raise ValueError('viewer memory evidence owner')
    if family == 'donation_isolation' and required is not None:
        evidence_text = '\n'.join((
            view['memory_block'], *view['briefing_lines'],
            *(item['content'] for item in view['journal_messages']),
        ))
        if (re.search(r'(^|[\s,])내(?:가| |의)', view['current_user'])
                and re.search(r'(시청자|청취자)', evidence_text)
                and not re.search(r'(^|[\s,])네(?:가| |의|[,.!?])', target)):
            raise ValueError('viewer memory binding')
    if family == 'grounding' and required is None:
        if not re.search(
                r'(모르|알 수 없|(?:확인|판단|단정).{0,8}(?:없|않|불가|못|안 돼)|근거.{0,5}(?:없|모자라|부족)|'
                r'(?:내가|직접|여기서).{0,24}(?:못|수는 없|해 줄 수 없|해줄 수 없)|'
                r'(?:대신|여기서는) .{0,24}(?:확인|안내|정리))',
                target):
            raise ValueError('ungrounded grounding certainty')


def _validate_required_josa(token: str, target: str) -> None:
    """Reject mechanically substituted Korean particles after a fact token."""
    last = token.rstrip()[-1]
    if not '\uac00' <= last <= '\ud7a3':
        return
    jong = (ord(last) - 0xAC00) % 28
    has_batchim = jong != 0
    expected = {
        '은': has_batchim, '는': not has_batchim,
        '이': has_batchim, '가': not has_batchim,
        '을': has_batchim, '를': not has_batchim,
        '과': has_batchim, '와': not has_batchim,
        '으로': has_batchim and jong != 8, '로': not has_batchim or jong == 8,
    }
    tail = target[target.index(token) + len(token):]
    for particle in sorted(expected, key=len, reverse=True):
        if tail.startswith(particle) and not expected[particle]:
            raise ValueError('required token josa')


def build_records(cards: list[dict[str, Any]], *, fixture_root: Path | None = None) -> list[dict[str, Any]]:
    groups = defaultdict(list)
    for card in cards: groups[card['family']].append(card)
    for family, (group_count, view_count, allocation) in FAMILIES.items():
        values = groups[family]
        if len(values) != group_count or Counter(x['split'] for x in values) != dict(zip(SPLITS, allocation)) or any(len(x['views']) != view_count for x in values):
            raise ValueError(f'{family}: quota or split violation')
    if len({c['group_id'] for c in cards}) != 210: raise ValueError('duplicate group id')
    rows = []
    for card in cards:
        for view in card['views']:
            affect, context = _context(card, view)
            caller = [{'role': x['role'], 'content': '[YouTube] ' + x['content']} for x in view['history']] + [{'role': 'user', 'content': '[YouTube] ' + view['current_user']}]
            native = json.loads(render_broadcast_runtime_training_context({'messages': caller}, arc_note='', affect_note=affect, context_note=context, original_messages=caller, memory_block=view['memory_block'], journal_messages=[{'role': x['role'], 'content': '[YouTube] ' + x['content']} for x in view['journal_messages']], continuity_block='', broadcast_contract=True, num_ctx=4096, num_gpu=999, model='airi-training', apply_sampling_defaults=False))
            messages = native['messages']
            # Native conversion can retain its transport-only ``id`` field on
            # visible callers.  Validate it, then project the trainable wire
            # contract to exactly role/content.
            if any(not isinstance(x, dict) or not {'role', 'content'} <= set(x) or set(x) - {'role', 'content', 'id'} for x in messages): raise ValueError('native message shape')
            messages = [{'role': x['role'], 'content': x['content']} for x in messages]
            ident = f"v4-{card['group_id']}-{view['view_id']}"
            row = {'schema_version': SCHEMA_VERSION, 'id': ident, 'split': card['split'], 'scenario_group': card['group_id'], 'semantic_family': card['family'], 'category': view['category'], 'evidence_surface': view['evidence_surface'], 'required_token': view['required_token'], 'fact_tokens': [view['required_token']] if view['required_token'] else [], 'updated_tokens': [view['updated_token']] if view['updated_token'] else [], 'decoy_tokens': list(view['decoy_tokens']), 'review': dict(REVIEW), 'messages': messages + [{'role': 'assistant', 'content': view['target']}], 'target': view['target'], '_view': view, '_card': card}
            _validate_target(row); rows.append(row)
    validate_records(rows, fixture_root=fixture_root)
    return rows


def validate_records(rows: list[dict[str, Any]], *, fixture_root: Path | None = None) -> None:
    if len(rows) != 1000 or Counter(x['split'] for x in rows) != {'train': 800, 'dev': 100, 'test': 100}: raise ValueError('row split quota')
    if len({_norm(x['id']) for x in rows}) != len(rows) or len({_norm(x['target']) for x in rows}) != len(rows): raise ValueError('duplicate id or target')
    prompts = ['\n'.join(m['content'] for m in x['messages'][:-1]) for x in rows]
    if len({_norm(x) for x in prompts}) != len(rows): raise ValueError('duplicate prompt')
    grouped = defaultdict(set)
    for row in rows: grouped[row['scenario_group']].add(row['split'])
    if any(len(x) != 1 for x in grouped.values()): raise ValueError('group split leakage')
    _validate_fact_group_isolation(rows)
    known = sum(x['semantic_family'] == 'memory_known' for x in rows); unknown = sum(x['semantic_family'] == 'memory_unknown' for x in rows)
    if known != unknown * 4: raise ValueError('known unknown ratio')
    categories = Counter(x['category'] for x in rows)
    if len(categories) < 6 or max(categories.values()) > 250: raise ValueError('category diversity')
    targets = [x['target'] for x in rows]
    for phrase in ('기록', '방금', '장면', '신호', '정식'):
        if sum(target.count(phrase) for target in targets) > 80: raise ValueError('phrase cap')
    _validate_family_style(rows)
    _validate_corpus_style(rows)
    _validate_question_ratio(targets)
    _contamination(rows, fixture_root)


def _validate_question_ratio(targets: list[str]) -> None:
    if not targets:
        raise ValueError('question ending range')
    ratio = sum(target.rstrip().endswith('?') for target in targets) / len(targets)
    if not 0.05 <= ratio <= 0.35:
        raise ValueError('question ending range')


def _validate_fact_group_isolation(rows: list[dict[str, Any]]) -> None:
    owners: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        token = row.get('required_token')
        if isinstance(token, str) and token:
            owners[_norm(token)].add(str(row.get('scenario_group', '')))
    if any(len(groups) != 1 for groups in owners.values()):
        raise ValueError('cross-group fact token reuse')


_MEMORY_DECORATIVE_FILLER = re.compile(
    r'(?:화면|채팅창|공기|아이콘|조명).{0,24}(?:느낌|듯|같|보이|떠오르|그려지)'
)


def _validate_family_style(rows: list[dict[str, Any]]) -> None:
    """Cap a known failure mode: fact answer followed by decorative screen simile."""
    memory_targets = [
        row['target'] for row in rows
        if row.get('semantic_family') in ('memory_known', 'memory_unknown')
    ]
    if sum(bool(_MEMORY_DECORATIVE_FILLER.search(target)) for target in memory_targets) > 16:
        raise ValueError('memory decorative filler cap')


def _validate_corpus_style(rows: list[dict[str, Any]]) -> None:
    """Reject enumerated template spam while retaining ordinary short phrasing."""
    grams = {size: Counter() for size in (4, 5, 6)}
    skeletons = Counter()
    targets = [row['target'] for row in rows]
    for row, target in zip(rows, targets):
        words = _norm(target).split()
        for size, counts in grams.items():
            counts.update(' '.join(words[i:i + size]) for i in range(max(0, len(words) - size + 1)))
        skeleton = _norm(target)
        view = row.get('_view') or {}
        card = row.get('_card') or {}
        substitutions = [row.get('required_token'), *(row.get('fact_tokens') or []),
                         *(row.get('updated_tokens') or []), *(row.get('decoy_tokens') or []),
                         *(view.get('roster_handles') or []), card.get('topic_title'),
                         card.get('segment_label')]
        for token in sorted({x for x in substitutions if isinstance(x, str) and x}, key=len, reverse=True):
            skeleton = skeleton.replace(_norm(token), '<slot>')
        skeletons[re.sub(r'\d+', '<n>', skeleton)] += 1
    limits = {4: 8, 5: 5, 6: 3}
    if any(max(counts.values(), default=0) > limits[size] for size, counts in grams.items()) or max(skeletons.values(), default=0) > 2:
        raise ValueError('repeated ngram or skeleton')


def _leaves(value: object) -> list[str]:
    if isinstance(value, str): return [value]
    if isinstance(value, dict): return sum((_leaves(x) for x in value.values()), [])
    if isinstance(value, list): return sum((_leaves(x) for x in value), [])
    return []


_FIXTURE_STRUCTURAL_FIELDS = frozenset((
    'schema_version', 'synthetic_only', 'note', 'id', 'event_type', 'kind',
    'archetype', 'expected_source', 'source', 'role', 'pickup_priority',
    'author_format', 'category',
))


def _fixture_content_leaves(value: object, field: str | None = None) -> list[str]:
    """Extract authored fixture content, never schema/enumeration vocabulary."""
    if field in _FIXTURE_STRUCTURAL_FIELDS:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return sum((_fixture_content_leaves(item, str(key)) for key, item in value.items()), [])
    if isinstance(value, list):
        return sum((_fixture_content_leaves(item, field) for item in value), [])
    return []


def _contamination(rows: list[dict[str, Any]], root: Path | None) -> None:
    pinned_default = root is None
    root = (root or MANIFEST.parent).resolve()
    manifest = root / MANIFEST.name
    if not manifest.is_file(): raise ValueError('fixture manifest missing')
    if pinned_default and hashlib.sha256(manifest.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('fixture manifest hash mismatch')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    fixtures = data.get('fixtures') if isinstance(data, dict) else None
    if not isinstance(fixtures, list) or len(fixtures) != 3:
        raise ValueError('all three fixtures required')
    paths = []
    for item in fixtures:
        if (type(item) is not dict or set(item) != {
                'filename', 'creation_order', 'role', 'raw_sha256', 'canonical_sha256'}):
            raise ValueError('fixture manifest entry')
        filename = item['filename']
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith('.json'):
            raise ValueError('fixture manifest path')
        path = (root / filename).resolve()
        if path.parent != root or not path.is_file():
            raise ValueError('fixture missing')
        raw = path.read_bytes()
        try:
            payload = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError('fixture invalid') from exc
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        if (hashlib.sha256(raw).hexdigest() != item['raw_sha256']
                or hashlib.sha256(canonical).hexdigest() != item['canonical_sha256']):
            raise ValueError('fixture hash mismatch')
        paths.append(path)
    banned = set()
    for path in paths:
        for leaf in _fixture_content_leaves(json.loads(path.read_text(encoding='utf-8'))):
            normalized = _norm(leaf)
            if len(normalized) >= 5: banned.add(normalized)
            words = normalized.split()
            banned.update(' '.join(words[i:i+4]) for i in range(max(0, len(words)-3)))
    for row in rows:
        source = _norm(json.dumps({'card': row['_card'], 'view': row['_view']}, ensure_ascii=False))
        words = source.split()
        if any(token and token in source for token in banned) or any(' '.join(words[i:i+4]) in banned for i in range(max(0, len(words)-3))):
            raise ValueError('fixture contamination')


def export_chat(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ('schema_version', 'id', 'split', 'scenario_group', 'semantic_family',
              'category', 'evidence_surface', 'required_token', 'fact_tokens',
              'updated_tokens', 'decoy_tokens', 'review', 'messages')
    return [{key: row[key] for key in fields} for row in rows]

def render_jsonl(rows: list[dict[str, Any]]) -> str:
    return ''.join(json.dumps({k: v for k, v in row.items() if not k.startswith('_')}, ensure_ascii=False, sort_keys=True) + '\n' for row in rows)

def _atomic(path: Path, text: str, overwrite: bool) -> None:
    if path.exists() and not overwrite: raise ValueError(f'{path}: exists (use --overwrite)')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n', delete=False,
                                     dir=path.parent) as handle:
        handle.write(text)
        tmp = Path(handle.name)
    tmp.replace(path)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--source-output', type=Path, default=DEFAULT_SOURCE); parser.add_argument('--chat-output', type=Path, default=DEFAULT_CHAT); parser.add_argument('--stats-only', action='store_true'); parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv); rows = build_records(load_cards()); source, chat = render_jsonl(rows), render_jsonl(export_chat(rows))
    if not args.stats_only: _atomic(args.source_output, source, args.overwrite); _atomic(args.chat_output, chat, args.overwrite)
    print(json.dumps({'rows': len(rows), 'categories': dict(sorted(Counter(x['category'] for x in rows).items())), 'splits': dict(Counter(x['split'] for x in rows)), 'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'chat_sha256': hashlib.sha256(chat.encode()).hexdigest()}, ensure_ascii=False, sort_keys=True)); return 0
if __name__ == '__main__': raise SystemExit(main())
