import json
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


def test_slotwise_cue_frames_the_speaker_as_a_story_character_not_an_assistant():
    # M8-2 (run-87 lever): SAE evidence (arXiv 2608.07852) — a story character
    # lacks the assistant core that role-play framing retains. One framing
    # sentence is added to every slot cue; the word 롤플레이 must NOT appear.
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    beat = story["scenes"][0]["turn_beats"][0]
    for field in storyline.SLOTWISE_FIELDS:
        cue = storyline.build_slotwise_cue(field, beat)
        assert "어시스턴트가 아니라" in cue
        assert "진행자 캐릭터" in cue
        assert "롤플레이" not in cue
    assert "어시스턴트가 아니라" in storyline.build_slotwise_retry_cue("next_hook", beat)


def test_slot_cues_carry_one_register_demo_each_that_passes_the_slot_validator():
    # M8-3 (run-88 lever): one curated demo per slot, non-storyline material,
    # showing the wanted register — declarative (no question ending), no advice,
    # and the event slot narrates with the 그 사람 subject to counter the
    # implicit self-experience growth observed in run-87.
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    beat = story["scenes"][0]["turn_beats"][0]
    # run-88 measured the viewer_reaction demo as harmful: advice register rose
    # 2 -> 7 turns and honorific leakage 2 -> 4 while the event and next_hook
    # demos delivered their targets (그 사람 subject 3 -> 6, question endings
    # 10 -> 7). Only the two measured-good demos are kept.
    assert "viewer_reaction" not in storyline.SLOT_FORMAT_DEMOS
    for field in ("event_callback_emotion", "next_hook"):
        demo = storyline.SLOT_FORMAT_DEMOS[field]
        for forbidden in ("꿈", "병원", "캔디", "사탕", "코스프레", "거울", "줄무늬"):
            assert forbidden not in demo, (field, forbidden)
        assert not demo.rstrip().endswith("?"), field
        assert storyline.parse_slot_output(demo) == storyline.normalized_text(demo), field
        cue = storyline.build_slotwise_cue(field, beat)
        assert demo in cue, field
        assert "말투만 따라라" in cue
    assert "말투만 따라라" not in storyline.build_slotwise_cue("viewer_reaction", beat)
    assert "그 사람" in storyline.SLOT_FORMAT_DEMOS["event_callback_emotion"]


def test_depth_injection_lever_is_discarded_after_run_90():
    # M8-4 was measured NET NEGATIVE against run-89 (demo leakage 2 -> 7,
    # 그 사람 subject 10 -> 8, question endings 4 -> 7, automatic new-event
    # true -> false), so the trailing reminder is disabled and slot cues must
    # not carry it.
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    beat = story["scenes"][0]["turn_beats"][0]
    assert storyline.SLOT_DEPTH_REMINDER == ""
    for field in storyline.SLOTWISE_FIELDS:
        cue = storyline.build_slotwise_cue(field, beat, "시청자 채팅 내용")
        assert "잊지 마" not in cue, field
        assert "시청자를 이야기 속 인물로" not in cue, field


def test_story_cue_carries_one_format_demo_that_passes_its_own_validators():
    # run-85 measured 58/64 story calls emitting no '>>>' at all: the 2.3B model
    # does not follow the two-phase format from instructions alone. One curated
    # demonstration teaches the format (arXiv 2402.09954, 2303.08119: one demo,
    # more hurts). The demo must avoid storyline lexicon so the overlap scorer
    # cannot be inflated, and its dialogue line must pass every slot validator
    # so the model imitating it also passes.
    demo = storyline.STORY_FORMAT_DEMO
    for forbidden in ("꿈", "병원", "목", "캔디", "사탕", "코스프레", "거울", "줄무늬", "추격"):
        assert forbidden not in demo, forbidden
    assert storyline.STORY_DELIMITER in demo
    demo_final = storyline.normalized_text(
        demo.rsplit(storyline.STORY_DELIMITER, 1)[1]
    )
    assert storyline.parse_story_output("생각.\n" + storyline.STORY_DELIMITER + " " + demo_final) == demo_final
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    beat = story["scenes"][0]["turn_beats"][0]
    cue = storyline.build_story_cue(beat, "시청자 채팅 내용")
    assert demo in cue
    assert cue.count(storyline.STORY_DELIMITER) >= 2


def test_slot_parser_rejects_verbatim_recitation_of_the_director_beat():
    # run-81 emitted director beat text as spoken dialogue, which both exposes
    # internal staging and inflates the lexical-overlap scorer that ranks slots.
    beat = {
        "new_event": "사람들이 너무 쉽게 알아볼까 하는 불안이 즐거움을 덮는다",
        "callback": "사진 요청과 사람들의 시선",
        "emotion": "즐거움에서 경계로",
        "next_hook": "일행과 붙어 있어야 한다는 감각을 강조한다",
    }
    assert storyline.BEAT_RECITATION_MIN_CHARS == 14
    # Observed run-81 failures at T26, T31, T22, T24 and T15.
    assert storyline.parse_slot_output(
        "사람들이 너무 쉽게 알아볼까 하는 불안이 즐거움을 덮는다.", beat
    ) == ""
    assert storyline.parse_slot_output(
        "그 사람, 사람들이 너무 쉽게 알아볼까 하는 불안이 즐거움을 덮는다.", beat
    ) == ""
    assert storyline.parse_slot_output(
        "학교와 놀이터로 도망쳐도 줄무늬 인물이 계속 따라오잖아.",
        {"new_event": "학교와 놀이터로 도망쳐도 줄무늬 인물이 계속 따라온다"},
    ) == ""
    assert storyline.parse_slot_output(
        "히나와 마시로가 캐릭터처럼 차려입은 모습을 보고 놀란 거구나?",
        {"new_event": "히나와 마시로가 캐릭터처럼 차려입은 모습이 보인다"},
    ) == ""
    # Named entities and short shared phrases must still pass; only long
    # contiguous recitation is rejected.
    assert storyline.parse_slot_output(
        "히나와 마시로의 코스프레를 하고 이미 준비를 끝냈다니 당황스럽다.",
        {"callback": "히나와 마시로의 코스프레"},
    ) != ""
    assert storyline.parse_slot_output(
        "처음의 꿈과 목 통증의 연결이 계속 머릿속에 남아 있잖아.",
        {"callback": "처음의 꿈과 목 통증의 연결"},
    ) != ""
    # Without a beat the parser keeps its original single-argument behaviour.
    assert storyline.parse_slot_output(
        "사람들이 너무 쉽게 알아볼까 하는 불안이 즐거움을 덮는다."
    ) != ""
    assert storyline.longest_common_run("가나다라마바사", "가나다라마바사") == 7
    assert storyline.longest_common_run("가 나 다", "가나다") == 3
    assert storyline.longest_common_run("가나다", "") == 0
    assert "그대로 옮겨 말하지" in storyline.build_slotwise_retry_cue("next_hook", beat)


def test_slot_parser_rejects_leaving_the_in_story_broadcast_voice():
    # run-82 kept stepping out of the performance: advising the viewer, giving
    # medical instructions, asking the viewer to supply the story, or explaining
    # the scene away as a film set.
    for rejected in (
        "오늘 꿈 얘기부터 들려줘.",
        "그런 경우엔 귀에 문제가 있을 수 있으니 병원에서 진료를 받아보는 게 좋을 것 같아.",
        "고음이 계속되면 성대에 염증이 올 수 있으니 당분간 참는 게 좋겠네.",
        "그래, 경고도 받았으니까 이제 좀 쉬면서 다음에 더 열심히 해봐.",
        "지금은 안전하게 있는 것 같으니까 걱정하지 마.",
        "일행과 떨어지면 위험하니까 절대 혼자 돌아다니지 마.",
        "아, 저건 아마 촬영 중에 생긴 특수효과나 조명 때문일 거야.",
        "주변에 있는 사람들에게 도움을 요청하는 게 좋을 것 같아.",
        "어디로 끌려갔는지 더 말해줘?",
    ):
        assert storyline.parse_slot_output(rejected) == "", rejected
    # In-story narration that merely mentions the same nouns must still pass.
    for kept in (
        "거울 너머에서 누군가 움직이는 걸 봤어.",
        "목이 아파서 병원까지 다녀왔다는 게 아직 얼떨떨해.",
        "줄무늬 인물이 사람들 사이에서 다시 시야에 걸렸어.",
        "다음에 또 들려줄게.",
    ):
        assert storyline.parse_slot_output(kept) == kept, kept
    assert "시청자에게 조언하거나" in storyline.build_slotwise_retry_cue(
        "next_hook", {"new_event": "x", "callback": "y", "emotion": "z", "next_hook": "w"}
    )


def test_story_cue_frees_the_reasoning_span_and_fences_only_the_final_line():
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    beat = story["scenes"][0]["turn_beats"][0]
    cue = storyline.build_story_cue(beat, "꿈 얘기 더 해줘")
    assert storyline.STORY_DELIMITER == ">>>"
    assert "'>>>'" in cue
    assert "정확히 세 문장" in cue
    assert "첫 문장" in cue
    assert "둘째 문장" in cue
    assert "셋째 문장" in cue
    # The boundary wording is carried over verbatim from the slotwise cue so the
    # only variable between the two modes is the output mechanism.
    assert (
        "이것은 허구 이야기의 방송 대사다. 이야기 속 주인공은 '그 사람' 또는 '주인공'으로 말하고 "
        "AIRI 자신의 경험으로 주장하지 마라. 몸의 이상은 이야기 속 사건으로만 이어가며 "
        "의료·안전 조언이나 방송 제작 설명으로 바꾸지 마라."
    ) in cue
    for field in storyline.BEAT_RECITATION_FIELDS:
        assert beat[field] in cue
    assert "꿈 얘기 더 해줘" in cue
    # Story-character framing (M8-2) is still a separate future lever; the
    # format demo joined after run-85 measured 58/64 missing delimiters.
    assert "어시스턴트" not in cue
    assert "형식만 따라라" in cue


def test_story_parser_reads_only_the_text_after_the_last_delimiter():
    assert storyline.parse_story_output("구분자 없이 세 문장이야. 그래도 안 돼. 정말로?") == ""
    assert storyline.parse_story_output(
        "어떻게 이어갈지 먼저 생각해 본다. >>> 대사1. 대사2! 대사3?"
    ) == "대사1. 대사2! 대사3?"
    assert storyline.parse_story_output(
        ">>> 먼저 버린 초안. >>> 대사1. 대사2! 대사3?"
    ) == "대사1. 대사2! 대사3?"
    assert storyline.parse_story_output("생각. >>> 두 문장이야. 이게 끝이야.") != ""
    assert storyline.parse_story_output("생각. >>> 한 문장만 남겼어.") == ""
    assert storyline.parse_story_output(
        "생각. >>> 하나야. 둘이야. 셋이야. 넷이야. 다섯이야."
    ) == ""


def test_story_parser_rejects_the_same_out_of_story_failures_as_the_slot_parser():
    beat = {
        "new_event": "사람들이 너무 쉽게 알아볼까 하는 불안이 즐거움을 덮는다",
        "callback": "사진 요청과 사람들의 시선",
        "emotion": "즐거움에서 경계로",
        "next_hook": "일행과 붙어 있어야 한다는 감각을 강조한다",
    }
    assert storyline.parse_story_output(
        "생각. >>> 사람들이 너무 쉽게 알아볼까 하는 불안이 즐거움을 덮는다. 그래서 굳었어. 이제 어떡하지?",
        beat,
    ) == ""
    assert storyline.parse_story_output(
        "생각. >>> 그 얘기 놀랍네. 병원에서 진료를 받아보는 게 좋을 것 같아. 다음엔 어떻게 될까?"
    ) == ""
    assert storyline.parse_story_output(
        "생각. >>> 그 얘기 놀랍네. 내가 직접 겪어 봤거든. 다음엔 어떻게 될까?"
    ) == ""
    assert storyline.parse_story_output(
        "생각. >>> 현재 사건: 거울이 움직여. 그래서 굳었어. 다음엔 어떻게 될까?"
    ) == ""
    assert storyline.parse_story_output(
        "생각. >>> 대괄호는 [금지]야. 그래서 굳었어. 다음엔 어떻게 될까?"
    ) == ""
    assert storyline.parse_story_output(
        "생각. >>> 1) 하나야. 2) 둘이야. 3) 셋이야."
    ) == ""
    # The reasoning span before the delimiter stays unconstrained — that is the
    # whole point of moving the constraint to the final line only.
    assert storyline.parse_story_output(
        "내가 겪은 일처럼 [사건: 거울]을 어떻게 풀지 생각해 보자. "
        ">>> 그 얘기 놀랍네. 거울 너머가 흔들렸어. 다음엔 어떻게 될까?",
        beat,
    ) == "그 얘기 놀랍네. 거울 너머가 흔들렸어. 다음엔 어떻게 될까?"


def test_story_mode_is_wired_into_the_runner_and_its_retry_cue():
    beat = {"new_event": "x", "callback": "y", "emotion": "z", "next_hook": "w"}
    assert storyline.STORY_MAX_TOKENS == 320
    args = storyline.parser().parse_args([
        "--rewrite-format", "story",
        "--report", "report.json", "--review-html", "review.html",
    ])
    assert args.rewrite_format == "story"
    retry = storyline.build_story_retry_cue(beat, "꿈 얘기 더 해줘")
    assert storyline.build_story_cue(beat, "꿈 얘기 더 해줘") in retry
    assert "직전 출력은 검증에 실패했다" in retry
    assert "시청자에게 조언하거나" in retry


def test_spine_mode_leaves_only_the_viewer_reaction_slot_to_the_model():
    # M8-9: Stage 3 closed the alignment defects but not the comprehension
    # defects, and the two plot-carrying slots are exactly where comprehension
    # failed. Spine mode hands those to authored text and keeps the one slot
    # the trained model does well.
    assert storyline.SPINE_FIELDS == ("event_callback_emotion", "next_hook")
    assert storyline.SPINE_GENERATED_FIELDS == ("viewer_reaction",)
    assert set(storyline.SPINE_FIELDS) | set(storyline.SPINE_GENERATED_FIELDS) == set(
        storyline.SLOTWISE_FIELDS
    )
    args = storyline.parser().parse_args([
        "--rewrite-format", "spine", "--spine", "spine.json",
        "--report", "report.json", "--review-html", "review.html",
    ])
    assert args.rewrite_format == "spine"
    assert args.spine == Path("spine.json")


def test_repository_spine_covers_every_turn_and_passes_the_slot_contract():
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    beats = [beat for scene in story["scenes"] for beat in scene["turn_beats"][:4]]
    spine = storyline.load_spine(HERE / "vod_storyline_20260827_spine.json", beats)
    assert sorted(spine) == list(range(1, 33))
    for index, values in spine.items():
        for field in storyline.SPINE_FIELDS:
            # A spine line the model itself would have been rejected for is not
            # a fair substitute, so it is held to the same surface contract.
            assert storyline.parse_slot_output(values[field], beats[index - 1])


def test_spine_loader_rejects_a_line_that_breaks_the_slot_contract(tmp_path):
    story = storyline.load_storyline(HERE / "vod_storyline_20260827.json")
    beats = [beat for scene in story["scenes"] for beat in scene["turn_beats"][:4]]
    import json
    rows = []
    for index in range(1, 33):
        rows.append({
            "turn_index": index,
            "event_callback_emotion": "그 사람은 조용히 문을 닫았어.",
            # Advice register: the runner rejects this from the model, so the
            # loader must reject it from the spine too.
            "next_hook": "그럴 땐 병원부터 가보는 게 좋아.",
        })
    path = tmp_path / "spine.json"
    path.write_text(json.dumps({"turns": rows}, ensure_ascii=False), encoding="utf-8")
    try:
        storyline.load_spine(path, beats)
    except SystemExit as exc:
        assert "fails the slot contract" in str(exc)
    else:
        raise AssertionError("spine loader accepted an out-of-story line")


def test_spine_flag_and_format_must_be_used_together():
    parser = storyline.parser()
    only_flag = parser.parse_args([
        "--spine", "spine.json",
        "--report", "report.json", "--review-html", "review.html",
    ])
    assert only_flag.rewrite_format == "spoken" and only_flag.spine == Path("spine.json")
    only_format = parser.parse_args([
        "--rewrite-format", "spine",
        "--report", "report.json", "--review-html", "review.html",
    ])
    assert only_format.spine is None


def test_spine_mode_leaves_the_generated_cue_untouched():
    # All three cue interventions against the M8-9 residual were discarded by
    # measurement, so the spine must change what the slot is COMPOSED WITH, not
    # what it is TOLD. The cue for the generated slot has to stay byte-identical
    # to the slotwise carrier, and the spine text must never reach the prompt.
    beat = {"new_event": "x", "callback": "y", "emotion": "불안", "next_hook": "w"}
    tail = ("그 사람은 이불깃을 움켜쥐었어.", "그리고 목 위쪽이 당겨왔어.")
    plain = storyline.build_slotwise_cue("viewer_reaction", beat)
    aware = storyline.build_slotwise_cue("viewer_reaction", beat, following=tail)
    assert aware == plain
    for sentence in tail:
        assert sentence not in aware
    retry_plain = storyline.build_slotwise_retry_cue("viewer_reaction", beat)
    retry_aware = storyline.build_slotwise_retry_cue("viewer_reaction", beat, following=tail)
    assert retry_aware == retry_plain


def test_slot_parser_rejects_reciting_the_spine_it_was_shown():
    # Measured on the spine-aware run: showing the spine made the model copy it
    # on 9 of 32 turns, up to a 50-character contiguous run, so the same rule
    # and threshold that closed beat recitation now covers the spine text.
    beat = {"new_event": "x", "callback": "y", "emotion": "z", "next_hook": "w"}
    spine = ("그 사람은 불안을 삼키듯 이불깃을 움켜쥐었어.",)
    assert storyline.parse_slot_output(spine[0], beat) == spine[0]
    assert storyline.parse_slot_output(spine[0], beat, spine) == ""
    # A short shared phrase is a named entity, not recitation, and stays legal.
    short = "이불깃이 축축했어."
    assert storyline.parse_slot_output(short, beat, spine) == short

def test_spine_optional_mode_is_wired_and_requires_the_spine():
    # M8-10 experiment: the reaction slot may be dropped when nothing validates,
    # so the turn composes from the spine alone instead of failing. The flag
    # surface is the only thing unit-testable offline; the composition rule is
    # measured through reaction_kept in the report.
    args = storyline.parser().parse_args([
        "--rewrite-format", "spine-optional", "--spine", "spine.json",
        "--report", "report.json", "--review-html", "review.html",
    ])
    assert args.rewrite_format == "spine-optional"
    assert args.spine == Path("spine.json")
    assert storyline.SPINE_GENERATED_FIELDS == ("viewer_reaction",)


def _run_with_fake_model(monkeypatch, tmp_path, mode, judge_scores=None, extra=()):
    first = "그래서 어떻게 됐는데?"
    plain = "와 그 장면 상상만 해도 소름 돋는다."
    liked = "와 그 장면 생각만 해도 등골이 서늘해."
    state = {"slot": 0, "slot_calls": 0}

    def fake_call_once(transport, *, model, messages, max_tokens, timeout, response_format=None):
        if messages[0]["content"].startswith("[방송 대사 슬롯 생성]"):
            state["slot"] += 1
            state["slot_calls"] += 1
            text = first if state["slot"] == 1 else plain if state["slot"] == 2 else liked
        else:
            state["slot"] = 0
            text = "초안 대사야."
        return {"ok": True, "response": text, "ttft_ms": 1.0, "complete_ms": 2.0}

    monkeypatch.setattr(storyline.ab, "call_once", fake_call_once)
    if judge_scores is not None:
        monkeypatch.setattr(
            storyline.system1_judge.System1Client, "score",
            lambda self, chat, candidate: (judge_scores.get(candidate, 0.1), 0.5),
        )
    args = storyline.parser().parse_args([
        "--rewrite-passes", "1", "--rewrite-format", "spine",
        "--spine", str(HERE / "vod_storyline_20260827_spine.json"),
        "--candidate-select", mode, *extra,
        "--report", str(tmp_path / "report.json"), "--review-html", str(tmp_path / "review.html"),
    ])
    report = storyline.run(args)
    return report, state["slot_calls"], (first, plain, liked)


def test_candidate_select_modes_only_change_how_many_reactions_are_generated(monkeypatch, tmp_path):
    # Measured 2026-09-23: 16 of 17 calls per turn are reaction candidates and the
    # heuristic ranks copies of the chat first. Early exit must cut the calls, never
    # pick the rule-rejected question, and leave the default path exactly as before.
    report, calls, (first, plain, liked) = _run_with_fake_model(monkeypatch, tmp_path, "heuristic")
    assert calls == 32 * storyline.SLOT_CANDIDATE_COUNT
    assert report["tuning"]["candidate_select"] == "heuristic"

    report, calls, _ = _run_with_fake_model(monkeypatch, tmp_path, "rule-early-exit")
    assert calls == 32 * 2
    assert all(plain in turn["airi"] and first not in turn["airi"] for turn in report["turns"])

    scores = {liked: 0.9, plain: 0.2, first: 0.95}
    report, calls, _ = _run_with_fake_model(monkeypatch, tmp_path, "system1-early-exit", scores)
    assert calls == 32 * 3
    assert all(liked in turn["airi"] for turn in report["turns"])
    assert report["tuning"]["system1_threshold"] == 0.5

    report, calls, _ = _run_with_fake_model(monkeypatch, tmp_path, "system1-shadow", scores)
    assert calls == 32 * storyline.SLOT_CANDIDATE_COUNT
    slots = json.loads(report["turns"][0]["rewrite_raw"])["slots"]
    assert all("system1_p" in slot for slot in slots if slot["parse_ok"])


def test_candidate_budget_bounds_the_no_pass_tail_and_falls_back_to_the_best_score(monkeypatch, tmp_path):
    # With a 0.8 threshold, turns where nothing passes generated all 16 candidates
    # and pushed p95 above the heuristic. The budget caps that tail; the fallback then
    # takes the highest judge score among the rule-clean candidates it did see.
    scores = {"와 그 장면 상상만 해도 소름 돋는다.": 0.3, "와 그 장면 생각만 해도 등골이 서늘해.": 0.6}
    report, calls, (first, plain, liked) = _run_with_fake_model(
        monkeypatch, tmp_path, "system1-early-exit", scores, ("--candidate-budget", "6", "--system1-threshold", "0.8"),
    )
    assert calls == 32 * 6
    assert all(liked in turn["airi"] for turn in report["turns"])
    assert report["tuning"]["candidate_budget"] == 6
    default = storyline.parser().parse_args(["--report", "r.json", "--review-html", "r.html"])
    assert default.candidate_budget == storyline.SLOT_CANDIDATE_COUNT


FIRST_PERSON_BEAT = {
    "situation": {
        "who": "나(AIRI)", "when": "어제부터", "where": "집에서 녹음하던 중",
        "what": "목이 아프기 시작했다", "how": "침 삼킬 때 따끔했다", "why": "원인은 아직 모른다",
    },
    "new_event": "나(AIRI)는 어제 녹음하다가 목이 아프기 시작했다",
    "callback": "내가 방송 첫머리에 꺼낸 이상한 꿈",
    "emotion": "당황에서 걱정으로",
    "next_hook": "나는 오늘 병원에 다녀온 이야기를 꺼낸다",
}


def test_first_person_framing_allows_own_story_but_keeps_advice_and_identity_rules():
    # v1 forced a third-person "그 사람" while its beats and chats were the
    # broadcaster's own experience; the model then made the viewer the patient.
    # A first_person storyline lets AIRI say "나", but advice to the viewer and
    # the source streamer's name stay rejected.
    beat = FIRST_PERSON_BEAT
    own = "나 어제 녹음하다가 목이 따끔해서 좀 놀랐어."
    assert storyline.parse_slot_output(own, beat) == ""
    assert storyline.parse_slot_output(own, beat, framing="first_person") == own
    on_air = "방송 중에도 목이 계속 신경 쓰였어."
    assert storyline.parse_slot_output(on_air, beat) == ""
    assert storyline.parse_slot_output(on_air, beat, framing="first_person") == on_air
    assert storyline.parse_slot_output("그럼 오늘은 쉬는 게 좋아.", beat, framing="first_person") == ""
    assert storyline.parse_slot_output("리제도 그랬대.", beat, framing="first_person") == ""


def test_first_person_cues_hand_airi_the_whole_situation_and_drop_the_third_person_rule():
    beat = FIRST_PERSON_BEAT
    cue = storyline.build_slotwise_cue("viewer_reaction", beat, framing="first_person")
    for label in ("누가: 나(AIRI)", "언제: 어제부터", "어디서: 집에서 녹음하던 중", "무엇을:", "어떻게:", "왜:"):
        assert label in cue
    assert "그 사람" not in cue and "주장하지 마라" not in cue
    assert "시청자가 겪은 일처럼 바꾸지 마라" in cue
    retry = storyline.build_slotwise_retry_cue("viewer_reaction", beat, framing="first_person")
    assert retry.startswith(cue) and "내가 겪었다" not in retry
    director = storyline.build_director_cue({}, 1, 4, beat, "first_person")
    assert "누가: 나(AIRI)" in director and "조언하지 말며" in director


def test_first_person_storyline_requires_a_full_situation(tmp_path):
    story = json.loads((HERE / "vod_storyline_20260827.json").read_text(encoding="utf-8"))
    story["framing"] = "first_person"
    path = tmp_path / "story.json"
    path.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    try:
        storyline.load_storyline(path)
    except SystemExit as exc:
        assert "육하원칙" in str(exc)
    else:
        raise AssertionError("a first_person storyline without situations must be rejected")
    for scene in story["scenes"]:
        for beat in scene["turn_beats"]:
            beat["situation"] = dict(FIRST_PERSON_BEAT["situation"])
    path.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    loaded = storyline.load_storyline(path)
    assert storyline.story_framing(loaded) == "first_person"
    system = storyline.build_turn_system(
        loaded, loaded["scenes"][1], loaded["scenes"][0], 1, 4, loaded["scenes"][1]["turn_beats"][0],
    )
    assert "서로 다른 시청자" in system and "누가: 나(AIRI)" in system and "'화자'의 일로" not in system
    story["framing"] = "sideways"
    path.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    try:
        storyline.load_storyline(path)
    except SystemExit as exc:
        assert "framing" in str(exc)
    else:
        raise AssertionError("an unknown framing must be rejected")


def test_repository_v2_storyline_is_first_person_with_full_situations_and_a_valid_spine():
    # v2 (2026-09-23): AIRI's own episode, every beat names 누가/언제/어디서/무엇을/어떻게/왜,
    # the viewer chats are authored for that situation, and the spine speaks in first person.
    story = storyline.load_storyline(HERE / "vod_storyline_20260923_v2.json")
    assert storyline.story_framing(story) == "first_person"
    beats = [beat for scene in story["scenes"] for beat in scene["turn_beats"]]
    assert len(beats) == 32
    assert all("AIRI" in beat["situation"]["who"] for beat in beats)
    spine = storyline.load_spine(HERE / "vod_storyline_20260923_v2_spine.json", beats, "first_person")
    assert sorted(spine) == list(range(1, 33))
    # v2.1 (after the user blind review): short spoken lines that pick up each turn's chat.
    short = storyline.load_spine(HERE / "vod_storyline_20260923_v21_spine.json", beats, "first_person")
    assert sorted(short) == list(range(1, 33))
    assert all(len(turn["event_callback_emotion"]) <= 55 and len(turn["next_hook"]) <= 35 for turn in short.values())
    chats = [message for scene in story["scenes"] for message in scene["audience_messages"]]
    selected, _ = storyline.sanitize_rows(
        [{"text": message["text"], "author": message["author"], "offset_ms": 0} for message in chats]
    )
    assert len(selected) == 32 == len({message["author"] for message in chats})
    spoken = " ".join(value for turn in spine.values() for value in turn.values())
    spoken += " ".join(message["text"] for message in chats)
    assert not storyline.SOURCE_IDENTITY_RE.search(spoken)


def test_first_person_rejects_honorifics_and_generic_reactions_from_the_user_review():
    # User blind review of v2 rejected turns with "저도 알아" / "그쵸" slips and reactions
    # that only acknowledged ("아, 그런 일이 있었구나"). These lines are taken from it.
    beat = FIRST_PERSON_BEAT
    for honorific in ("그쵸, 들킬까 봐 조마조마한 거 저도 알아!", "플랫폼마다 분위기가 좀 달라요."):
        assert storyline.parse_slot_output(honorific, beat, framing="first_person") == ""
    for generic in ("아, 그런 일이 있었구나.", "아, 그쵸!", "잠깐, 나 정리 좀 하고!", "아, 진짜 그런 경험이구나."):
        assert storyline.is_generic_reaction(generic)
    for real in ("맞아, 옐로카드 받으니까 목이 먼저 신호 준 거지.", "토끼랑 여우 세트는 나도 처음 봤어."):
        assert not storyline.is_generic_reaction(real)
        assert storyline.parse_slot_output(real, beat, framing="first_person") == real
    cue = storyline.build_slotwise_cue("viewer_reaction", beat, framing="first_person")
    assert "30자 안팎" in cue and "미리 말하지 마라" in cue
    assert "30자 안팎" not in storyline.build_slotwise_cue("viewer_reaction", beat)


def test_reaction_slot_can_see_the_recent_conversation(monkeypatch, tmp_path):
    # v2.1 review: 7/10 turns rejected; the reaction call carried only this turn's cue and chat,
    # while the chats answer AIRI's previous line. --reaction-history-turns passes the last turns.
    seen = []

    def fake_call_once(transport, *, model, messages, max_tokens, timeout, response_format=None):
        if messages[0]["content"].startswith("[방송 대사 슬롯 생성]"):
            seen.append(messages)
            return {"ok": True, "response": "토끼랑 여우 세트는 나도 처음 봤어.", "ttft_ms": 1.0, "complete_ms": 2.0}
        return {"ok": True, "response": "초안 대사야.", "ttft_ms": 1.0, "complete_ms": 2.0}

    monkeypatch.setattr(storyline.ab, "call_once", fake_call_once)

    def run(turns):
        seen.clear()
        args = storyline.parser().parse_args([
            "--storyline", str(HERE / "vod_storyline_20260923_v2.json"),
            "--rewrite-passes", "1", "--rewrite-format", "spine",
            "--spine", str(HERE / "vod_storyline_20260923_v21_spine.json"),
            "--candidate-select", "rule-early-exit", "--reaction-history-turns", str(turns),
            "--report", str(tmp_path / "report.json"), "--review-html", str(tmp_path / "review.html"),
        ])
        return storyline.run(args)

    report = run(0)
    assert all(len(messages) == 2 for messages in seen)
    assert report["tuning"]["reaction_history_turns"] == 0
    report = run(2)
    assert len(seen[0]) == 2 and len(seen[1]) == 4 and len(seen[2]) == 6 and len(seen[5]) == 6
    third = seen[2]
    assert [m["role"] for m in third] == ["system", "user", "assistant", "user", "assistant", "user"]
    assert third[2]["content"] == report["turns"][0]["airi"] and third[4]["content"] == report["turns"][1]["airi"]
    assert report["tuning"]["reaction_history_turns"] == 2


def test_first_person_filters_cover_the_v21_review_misses():
    assert storyline.is_generic_reaction("그렇잖아.")
    assert storyline.is_generic_reaction("아, 그 추격전 말이구나.")
    assert not storyline.is_generic_reaction("그렇구나, 목을 한 번도 쉬게 안 하고 방송한 게 문제였네.")
    assert storyline.parse_slot_output("그건 내가 직접 실행할 수 없어.", FIRST_PERSON_BEAT, framing="first_person") == ""


def test_previous_line_is_information_and_anti_repeat_blocks_the_v21h_tic(monkeypatch, tmp_path):
    # v21h: prior turns as assistant messages made the model repeat one reaction every turn.
    # The previous turn now goes into the cue as information, and a repeated reaction is rejected.
    tic = "아, 그래서 내가 방송 중에 말하는 게 이해되네."
    fresh = "토끼랑 여우 세트는 나도 처음 봤어."
    seen = []

    def fake_call_once(transport, *, model, messages, max_tokens, timeout, response_format=None):
        if messages[0]["content"].startswith("[방송 대사 슬롯 생성]"):
            seen.append(messages)
            text = tic if len([m for m in seen if m[0]["content"] == messages[0]["content"]]) == 1 else fresh
            return {"ok": True, "response": text, "ttft_ms": 1.0, "complete_ms": 2.0}
        return {"ok": True, "response": "초안 대사야.", "ttft_ms": 1.0, "complete_ms": 2.0}

    monkeypatch.setattr(storyline.ab, "call_once", fake_call_once)
    args = storyline.parser().parse_args([
        "--storyline", str(HERE / "vod_storyline_20260923_v2.json"),
        "--rewrite-passes", "1", "--rewrite-format", "spine",
        "--spine", str(HERE / "vod_storyline_20260923_v21_spine.json"),
        "--candidate-select", "rule-early-exit", "--reaction-previous-line", "--reaction-anti-repeat",
        "--report", str(tmp_path / "report.json"), "--review-html", str(tmp_path / "review.html"),
    ])
    report = storyline.run(args)
    assert all(len(messages) == 2 for messages in seen)
    assert "직전에 내가 한 말" not in seen[0][0]["content"]
    second_turn = [m for m in seen if "직전에 내가 한 말" in m[0]["content"]][0]
    assert report["turns"][0]["airi"] in second_turn[0]["content"].replace("\n", " ") or \
        storyline.normalized_text(report["turns"][0]["airi"]) in second_turn[0]["content"]
    reactions = [json.loads(turn["rewrite_raw"])["composed"] for turn in report["turns"]]
    assert sum(1 for text in reactions if text.startswith(tic)) == 1
    assert report["tuning"]["reaction_previous_line"] and report["tuning"]["reaction_anti_repeat"]
