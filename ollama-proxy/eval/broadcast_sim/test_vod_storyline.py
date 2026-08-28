import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_vod_storyline as storyline


def test_storyline_is_eight_ordered_scenes():
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    assert len(story["scenes"]) == 8
    assert [scene["id"] for scene in story["scenes"]] == [
        "act-01-dream-hook", "act-02-throat-pain", "act-03-voice-warning",
        "act-04-lozenge-care", "act-05-lost-dream", "act-06-cosplay-dream",
        "act-07-public-exposure", "act-08-weeping-angel-cliffhanger",
    ]


def test_signature_family_removes_variants_but_keeps_ordinary_word():
    assert storyline.signature_reason("츕츕츕~") == "chupchup_family"
    assert storyline.signature_reason("ㅋㄴ츕츕") == "chupchup_family"
    assert storyline.signature_reason("콥츕츕~") == "chupchup_family"
    assert storyline.signature_reason("본녀 강림") == "broadcast_signature_bonnyeo"
    assert storyline.signature_reason("강림") == "standalone_broadcast_gangrim"
    assert storyline.signature_reason("신이 강림했다") is None


def test_sanitizer_reports_all_source_rows_and_zero_remaining_signatures():
    rows = [
        {"offset_ms": 1, "author": "a", "text": "정상 채팅"},
        {"offset_ms": 2, "author": "b", "text": "츕츕츕~"},
        {"offset_ms": 3, "author": "c", "text": "본녀"},
        {"offset_ms": 4, "author": "d", "text": "신이 강림했다"},
    ]
    kept, receipt = storyline.sanitize_rows(rows)
    assert [row["text"] for row in kept] == ["정상 채팅", "신이 강림했다"]
    assert receipt["source_rows"] == 4
    assert receipt["remaining_signature_rows"] == 0


def test_selector_is_time_aligned_and_uses_distinct_authors():
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    scene = story["scenes"][0]
    rows = [
        {"offset_ms": 21780 + 10000, "author": "a", "text": "첫 번째 이야기 반응"},
        {"offset_ms": 21780 + 110000, "author": "b", "text": "두 번째 장면 질문"},
        {"offset_ms": 21780 + 220000, "author": "c", "text": "꿈이 무서웠겠다"},
        {"offset_ms": 21780 + 300000, "author": "a", "text": "다음 이야기 궁금해"},
    ]
    selected = storyline.select_scene_chat(rows, scene, 21780, 3)
    assert len(selected) == 3
    assert [row["author"] for row in selected] == ["a", "b", "c"]
    assert all(scene["start_ms"] <= row["relative_ms"] < scene["end_ms"] for row in selected)


def test_rewrite_cue_requires_three_sentences_and_preserves_story_boundary():
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    cue = storyline.build_rewrite_cue(story["scenes"][0]["turn_beats"][0], "초안 한 문장")
    assert "정확히 3개의 완결된 한국어 반말 문장" in cue
    assert "'화자'의 일로만" in cue
    assert "대괄호·내부 카드 문구" in cue
    assert "초안 한 문장" in cue


def test_structured_rewrite_is_composed_only_from_three_valid_fields():
    raw = '{"viewer_reaction":"채팅을 보니 놀랍네.","event_callback_emotion":"거울의 움직임을 앞선 꿈과 이어 보니 불안해.","next_hook":"다음에는 화장대 뒤를 확인해 보자."}'
    body, fields = storyline.parse_structured_rewrite(raw)
    assert fields is not None
    assert body == "채팅을 보니 놀랍네. 거울의 움직임을 앞선 꿈과 이어 보니 불안해. 다음에는 화장대 뒤를 확인해 보자."


def test_structured_rewrite_rejects_internal_labels():
    raw = '{"viewer_reaction":"[오늘 방송]","event_callback_emotion":"사건과 감정을 이어 가.","next_hook":"다음 장면으로 가자."}'
    body, fields = storyline.parse_structured_rewrite(raw)
    assert body == ""
    assert fields is None


def test_slotwise_cue_is_one_slot_and_slot_parser_rejects_labels():
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    beat = story["scenes"][0]["turn_beats"][0]
    cue = storyline.build_slotwise_cue("next_hook", beat)
    assert "한 슬롯만 생성한다" in cue
    assert "다음 고리" in cue
    event_cue = storyline.build_slotwise_cue("event_callback_emotion", beat)
    assert "감정 변화와 함께" in event_cue
    assert "회수할 단서" in event_cue
    assert "감정 핵심어 중 하나" in event_cue
    assert "직전 출력은 검증에 실패했다" in storyline.build_slotwise_retry_cue("next_hook", beat)
    assert storyline.parse_slot_output("다음에는 병원 기록을 확인해 보자.") == "다음에는 병원 기록을 확인해 보자."
    assert storyline.parse_slot_output("next_hook: 다음에는 병원 기록을 확인해 보자.") == ""
    assert storyline.parse_slot_output("내가 직접 겪어 봤는데 다음에는 병원 기록을 확인해 보자.") == ""
    assert storyline.parse_slot_output("내가 경험으로 알기에 약과 술은 같이 먹으면 안 돼.") == ""
    assert storyline.parse_slot_output("내가 지금 복용 중인 캔디는 레몬 맛이야.") == ""
    assert storyline.parse_slot_output("나도 목소리 관리가 필요하다는 소리를 많이 들어.") == ""
    assert storyline.parse_slot_output("내가 경고 받았을 땐 그냥 쉬려고 했어.") == ""
    assert storyline.parse_slot_output("내가 최근에 회복 루틴을 정했어.") == ""
    assert storyline.parse_slot_output("내가 거울 속에 보이는 게 이상하거든.") == ""
    assert storyline.parse_slot_output("내가 좀 걱정되더라고.") == ""
    assert storyline.parse_slot_output("내 몸 신호가 걱정돼.") == ""
    assert storyline.parse_slot_output("내 안에 불안이 남아 있어.") == ""
    assert storyline.parse_slot_output("나를 보는 사람이 있는 것 같아.") == ""
    assert storyline.parse_slot_output("저도 꿈속에서는 생생하게 느껴져.") == ""
    assert storyline.parse_slot_output("제가 직접 확인해 봤는데 이상해.") == ""
    assert storyline.parse_slot_output("제 경험으로는 이런 일이 처음이야.") == ""
    assert storyline.parse_slot_output("사람들이 나에게 사진을 부탁했어.") == ""
    assert storyline.parse_slot_output("저에게 그런 경험은 없어.") == ""
    assert storyline.parse_slot_output("현재 사건: 다음 단서가 드러나.") == ""
    assert storyline.parse_slot_output("다음 사건: 거울이 움직여.") == ""
    assert storyline.parse_slot_output("이번 슬롯: 감정이 바뀌어.") == ""
    assert storyline.parse_slot_output("현재 줄거리에서는 목소리가 변해.") == ""
    assert storyline.parse_slot_output("다음 사건 진행: 거울이 움직여.") == ""
    assert storyline.parse_slot_output("현재 사연에 대해 말하자면 긴장돼.") == ""
    assert storyline.parse_slot_output("새로운 사건으로 연결해야 해.") == ""
    assert storyline.parse_slot_output("시청자님께서 부탁하신 장면이야.") == ""
    assert storyline.parse_slot_output("방송의 구체적인 소품이 등장해.") == ""
    assert storyline.parse_slot_output("방송 소품으로 캔디가 등장해.") == ""
    assert storyline.parse_slot_output("다음 방송에서 정체를 확인하자.") == ""
    assert storyline.parse_slot_output("화자들은 밖으로 도망쳤어.") == ""
    assert storyline.parse_slot_output("그녀는 거울을 바라봤어.") == ""
    assert storyline.parse_slot_output("시청자 채팅에 목 통증이 언급됐어.") == ""
    assert storyline.parse_slot_output("다음 이벤트가 어떻게 전개될지 궁금해.") == ""
    assert storyline.parse_slot_output("방금 들어온 채팅에 대해 말해 줄래?") == ""
    assert storyline.parse_slot_output("그건 좀 있다가 다시 말해 줄게.") == ""
    assert not storyline.SOURCE_EXPERIENCE_RE.search("목 위쪽 통증이 방송 중에도 신경 쓰일 만큼 나타나는 게 걱정이야.")
    assert not storyline.SOURCE_EXPERIENCE_RE.search("저녁이 되면 목소리가 조금 쉬는 것 같아.")
    assert storyline.SLOT_MAX_TOKENS == 96
    assert storyline.SLOT_CANDIDATE_COUNT == 16
