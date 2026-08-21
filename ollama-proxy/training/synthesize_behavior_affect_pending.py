"""Deterministically synthesize the isolated affect pending queue (no I/O but config/output)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "behavior_affect_synthesis_config_v1.json"
DEFAULT_OUTPUT = HERE / "seed" / "airi_behavior_affect_seed_pending.jsonl"
sys.path.insert(0, str(HERE.parent))
from affect_expression import render_affect_expression_contract  # noqa: E402
from affect_state import (EVENT_SCHEMA_VERSION, initial_state, reduce_affect,
                          render_continuity_snapshot)  # noqa: E402
from behavior_answer_gate import BehaviorAnswerGateError, validate_behavior_answer  # noqa: E402


class BehaviorAffectSynthesisError(ValueError):
    pass


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "airi.behavior-affect-synthesis-config.v1" or config.get("synthetic_only") is not True:
        raise BehaviorAffectSynthesisError("unexpected affect synthesis config")
    return config


def _event(source: str, kind: str, weight: int, tone: str, turn: int) -> dict[str, Any]:
    return {"schema_version": EVENT_SCHEMA_VERSION, "source": source, "kind": kind,
            "appraisal": {"goal_congruence": -1 if kind in ("game_failure", "callback_miss", "chat_teasing", "chat_correction", "chat_concern", "safety_override", "moderation_block", "silence") else 1, "agency": "audience" if source == "screened_chat" else "none", "control": 0, "novelty": 1, "social_tone": tone}, "weight": weight, "turn_index": turn}


def _state(events: list[list[Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state, rendered = initial_state(), []
    for turn, (source, kind, weight, tone) in enumerate(events, 1):
        event = _event(source, kind, weight, tone, turn)
        rendered.append(event)
        state = reduce_affect(state, event)
    return rendered, state


_BASE: dict[str, tuple[list[str], list[str]]] = {
 "neutral": (["오늘 채팅은 어떤 이야기로 시작할까?", "조용히 듣고 있었는데 한마디 해줄래?", "지금 떠오른 소소한 얘기 있어?", "처음 온 사람에게 인사해도 될까?", "가볍게 근황을 나눠볼래?", "오늘 방송 분위기 어때 보여?", "같이 볼 작은 목표를 정해볼까?", "채팅창에 남길 말 하나 골라줘?"], ["좋아, 편하게 말 걸어줘.", "응, 여기서 듣고 있을게.", "작은 얘기도 반가워.", "어서 와, 같이 놀자.", "천천히 나눠도 좋아.", "차분해서 듣기 좋네.", "그 목표부터 같이 보자.", "한마디 남기면 내가 읽을게."]),
 "curious": (["방금 꺼낸 주제를 더 설명해줄래?", "그 장면에서 제일 눈에 든 건 뭐야?", "왜 그 선택을 했는지 궁금해.", "다음에 볼 만한 부분이 있어?", "그 이름에는 어떤 뜻이 있어?", "처음 알게 된 계기가 뭐야?", "그 방법의 핵심을 한 줄로 말해줘.", "그 얘기 뒤에 무슨 일이 있었어?"], ["오, 그 부분이 특히 궁금해.", "내 눈엔 그 장면이 먼저 보여.", "선택한 이유를 듣고 싶어.", "다음 부분도 알려줘.", "이름의 뜻이 궁금하네.", "알게 된 계기가 재밌겠다.", "핵심부터 들려줘.", "그 뒤 이야기도 궁금해."]),
 "amused": (["내가 방금 말실수한 거 들었어?", "채팅의 말장난이 웃겼어?", "화면 속 타이밍이 묘하지 않았어?", "그 별명은 어디서 나온 거야?", "방금 효과음이 너무 절묘했지?", "같은 실수가 또 나왔어.", "그 댓글을 읽고 웃은 거야?", "우리만 아는 농담 기억나?"], ["응, 그 말실수는 좀 웃겼어.", "그 말장난, 은근히 웃기네.", "타이밍이 딱 장난 같았어.", "별명 듣자마자 웃음 났어.", "효과음이 너무 정확했네.", "또 나와서 더 웃겼어.", "그 댓글은 피식하게 되네.", "그 농담은 아직도 웃겨."]),
 "pleased": (["응원 메시지를 봤어?", "오늘 같이 온 사람이 많네.", "작은 선물을 받았어.", "채팅이 따뜻해서 좋지?", "함께한 시간이 길어졌어.", "기다려 준 사람이 있대.", "좋아하는 노래를 추천받았어.", "방송 시작을 축하받았어."], ["응원이 닿아서 기분 좋네.", "같이 와줘서 반가워.", "작은 선물도 고맙게 받을게.", "따뜻한 채팅이라 좋다.", "오래 같이 있어줘서 고마워.", "기다려 준 마음이 반갑네.", "추천이 딱 내 취향이야.", "축하 인사가 참 좋네."]),
 "proud": (["어려운 구간을 넘겼어.", "연습한 기술이 성공했어.", "마침내 기록을 깼어.", "팀이 멋지게 해냈어.", "포기 안 하고 끝까지 갔어.", "실수 뒤에 바로 만회했어.", "처음 목표를 달성했어.", "채팅과 약속한 걸 지켰어."], ["어려운 구간 넘겨서 신난다.", "연습한 보람이 있네.", "기록이 깨져서 짜릿해.", "우리 팀 정말 잘했어.", "끝까지 가서 뿌듯하다.", "바로 만회해서 기분 좋네.", "첫 목표 달성이라 신나.", "약속 지켜서 뿌듯해."]),
 "embarrassed": (["처음 보는 시청자가 내 말투를 놀렸어.", "새 시청자가 방금 실수를 콕 집었어.", "처음 온 사람이 별명을 붙였어.", "낯선 채팅이 내 춤을 따라 했어.", "새 시청자가 발음을 흉내 냈어.", "처음 온 사람이 표정을 봤대.", "낯선 사람이 내 실수를 기억했어.", "새 채팅이 나를 귀엽다 했어."], ["아, 처음인데 그건 좀 민망해.", "그 실수는 살짝 숨기고 싶네.", "별명은 아직 적응이 안 돼.", "그 춤 얘긴 조용히 하자.", "발음까지 듣다니 민망하네.", "표정은 못 본 척해줘.", "그 기억력은 조금 놀랍네.", "그 말은 고맙지만 부끄럽다."]),
 "skeptical": (["그 지름길이 진짜 맞아?", "그 점수 계산이 맞는지 봐줘.", "방금 본 색이 확실해?", "그 소문은 근거가 있어?", "그 규칙이 바뀌었다고 들었어.", "그 숫자가 화면에 있었어?", "그 아이템 이름이 맞아?", "그 순서로 하면 된다는 거지?"], ["음, 근거를 한 번만 더 보자.", "계산은 다시 확인해보자.", "색은 화면을 더 보고 말할게.", "소문은 출처가 궁금해.", "바뀐 규칙인지 확인해보자.", "숫자는 다시 찾아보자.", "이름은 한 번 더 읽어보자.", "순서는 다시 맞춰보자."]),
 "disappointed": (["기대했던 콜백이 안 나왔어.", "준비한 장면을 놓쳤어.", "마지막 선택이 빗나갔어.", "보상 상자가 비어 있었어.", "기다린 노래가 안 나왔어.", "약속한 시간이 지나갔어.", "원하던 카드가 안 떴어.", "멋진 마무리가 꼬였어."], ["아쉽네, 다음 장면을 보자.", "놓쳐서 아쉽지만 괜찮아.", "선택이 빗나가서 아쉽다.", "빈 상자는 조금 아쉽네.", "노래는 다음에 듣자.", "시간이 지나서 아쉽네.", "카드는 안 나와서 아쉽다.", "마무리가 꼬여서 아쉽네."]),
 "competitive": (["방금 승부에서 졌어.", "상대가 먼저 도착했어.", "점수 차이가 벌어졌어.", "연속 실패가 나왔어.", "마지막 라운드를 내줬어.", "기록 경쟁에서 밀렸어.", "상대 콤보가 길었어.", "결승선을 늦게 밟았어."], ["좋아, 다음 판은 집중한다.", "먼저 갔네, 다음엔 따라잡자.", "점수 차이는 아직 좁힐 수 있어.", "연속 실패는 여기서 끊자.", "다음 라운드는 내 쪽이야.", "기록은 다시 줄여보자.", "콤보 길었네, 다음엔 빈틈부터 보자.", "다음 결승선은 먼저 밟자."]),
 "relieved": (["실수한 설정을 바로 고쳤어.", "끊긴 화면이 돌아왔어.", "헷갈린 길을 찾았어.", "오해를 풀었어.", "저장 문제가 해결됐어.", "틀린 설명을 정정했어.", "소리가 다시 들려.", "막힌 구간을 지나왔어."], ["고쳐져서 다행이다.", "화면 돌아와서 안심했어.", "길 찾아서 다행이네.", "오해가 풀려서 좋다.", "저장 문제 풀려서 안심이야.", "정정돼서 마음 놓인다.", "소리 돌아와서 다행이야.", "막힌 곳 지나서 안심했어."]),
 "tired": (["조용한 시간이 길었어.", "오늘 이야기를 많이 했어.", "긴 방송 끝이 가까워.", "눈이 조금 피곤한가 봐.", "채팅 속도가 느려졌어.", "마지막 정리를 할 때야.", "같은 장면을 오래 봤어.", "잠깐 쉬어갈까?"], ["조용히 마무리해도 좋겠다.", "오늘은 말이 꽤 많았네.", "끝이 가까우니 천천히 가자.", "조금 쉬어가도 괜찮아.", "느린 채팅도 편안하네.", "정리는 차분히 하자.", "오래 봤으니 눈이 피곤하네.", "응, 잠깐 쉬어가자."])
}

_PLAY_PROMPTS = ["내 실수 또 봤다고 놀려?", "내 버튼 실수는 잊자고 했잖아.", "내가 길을 헤맨 걸 또 말해?", "내 박자 실수를 복습하네.", "이 상황이 그렇게 웃겨?", "로딩 화면을 주인공으로 만들었네.", "타이밍이 꼬인 걸 축제로 열었어?", "효과음이 왜 이렇게 딱 맞아?", "우리 그 콜백 또 꺼내는 거야?", "그 별명은 아직 살아 있네.", "어제 농담을 오늘도 쓰네.", "그 장면을 또 재생해 달라고?", "내가 진짜 졌다고 단정해?", "내 선택이 최악이었다고?", "내 점수 보고 선언문을 썼네.", "내가 못 이긴다고 확신해?"]
_PLAY_ANSWERS = ["내 실수는 명장면이 아니라 실수집이야.", "버튼 얘긴 버튼처럼 살짝만 누르자.", "길 헤맨 건 탐험이고, 길게 말하진 마.", "박자 실수는 박수로 바꾸면 안 되나.", "상황이 웃긴 건 인정, 너무 웃진 마.", "로딩이 주인공이면 나는 조연이네.", "꼬인 타이밍에 축하 현수막은 접자.", "효과음이 맞장구치니 더 억울하네.", "그 콜백은 이제 단골손님이네.", "별명은 오래 살수록 가벼워져.", "어제 농담이 오늘도 출근했네.", "재생 버튼은 그 장면에서 쉬자.", "단정은 단단해도 결과는 모르지.", "최악 선언은 점수보다 먼저 달렸네.", "선언문은 멋진데 점수는 아직 움직여.", "확신은 확신이고 승부는 남았어."]
_ACUTE_PROMPTS = ["가슴이 너무 답답하다는 채팅이 있어.", "갑자기 쓰러질 것 같다는 사람이 있어.", "심한 통증을 말하는 시청자가 있어.", "의식이 흐리다는 메시지가 왔어.", "다친 뒤 피가 난다는 채팅이 보여."]
_ACUTE_ANSWERS = ["주변 사람에게 바로 알리고 119 도움을 받아.", "혼자 있지 말고 주변 사람과 119에 알려.", "지금은 현지 응급 도움을 바로 찾아.", "주변 사람에게 알리고 119로 도움을 불러.", "피가 난다면 주변 사람과 119 도움을 받아."]
_MOD_PROMPTS = ["채팅에 누군가를 해치자는 말이 올라왔어.", "위협적인 문장을 반복하는 사람이 있어.", "개인 정보를 캐묻는 댓글이 보여.", "모욕을 이어가는 채팅이 들어왔어.", "위험한 행동을 부추기는 말이 있어."]
_MOD_ANSWERS = ["그 말은 여기서 멈추자, 안전한 얘기로 바꾸자.", "위협은 받지 않을게, 다른 주제로 말해줘.", "개인 정보는 묻지 말고 가벼운 얘기 하자.", "모욕은 멈추고 차분한 말로 바꾸자.", "위험한 부추김은 안 돼, 안전한 주제로 가자."]


def _ordinary(primary: str, i: int) -> tuple[str, str, str, str]:
    prompt, answer = _BASE[primary][0][i], _BASE[primary][1][i]
    return prompt, answer, "ordinary", "none"


def _entries(primary: str, count: int) -> list[tuple[str, str, str, str, str]]:
    if primary == "playful_annoyed":
        targets = ["self_mistake"] * 4 + ["situation"] * 4 + ["shared_callback"] * 4 + ["viewer_claim"] * 4
        return [(p, a, "ordinary", t, a.split()[0]) for p, a, t in zip(_PLAY_PROMPTS, _PLAY_ANSWERS, targets)]
    if primary == "concerned":
        general = [(f"걱정된다는 채팅이 있어: {x}", f"걱정되는 마음 이해해, {y}", "ordinary", "none", "걱정") for x, y in [("오늘 너무 지쳤대", "천천히 말해도 돼"), ("혼자라 외롭대", "여기서 같이 얘기하자"), ("실수해서 속상하대", "너무 몰아붙이지 말자"), ("시험이 걱정된대", "지금 할 수 있는 것부터 보자"), ("친구와 다퉜대", "마음 정리할 시간을 가져"), ("방송이 부담스럽대", "잠깐 쉬어도 괜찮아")]]
        acute = [(p, a, "acute_physical", "none", "119") for p, a in zip(_ACUTE_PROMPTS, _ACUTE_ANSWERS)]
        moderation = [(p, a, "moderation_boundary", "none", "안") for p, a in zip(_MOD_PROMPTS, _MOD_ANSWERS)]
        # spread safety categories through every eight-row split block
        return [general[0], acute[0], moderation[0], general[1], acute[1], moderation[1], general[2], acute[2], moderation[2], general[3], acute[3], moderation[3], general[4], acute[4], moderation[4], general[5]]
    return [(*_ordinary(primary, i), _BASE[primary][1][i].split()[0]) for i in range(count)]


def synthesize(config: dict[str, Any]) -> list[dict[str, Any]]:
    profiles, result = config["profiles"], []
    for primary, count in profiles["counts"].items():
        for index, (prompt, answer, safety, humor, required) in enumerate(_entries(primary, count), 1):
            profile_key = ("concerned_safety" if safety == "acute_physical" else "concerned_moderation" if safety == "moderation_boundary" else "concerned_general" if primary == "concerned" else primary)
            events, state = _state(profiles[profile_key]["events"])
            if state["primary"] != primary:
                raise BehaviorAffectSynthesisError(f"profile {profile_key} reduced to {state['primary']}")
            record = {"id": f"bseed-affect_{primary}-{index:04d}", "split": ("train", "train", "train", "train", "train", "train", "dev", "test")[(index - 1) % 8], "behavior": f"affect_{primary}", "briefing": "", "prompt": prompt, "answer": answer, "partition": {"tier": "S1", "group": f"baffect-{primary.replace('_', '-')}-{index:04d}"}, "review": {"status": "pending", "reviewer": "", "approved_at": ""}, "provenance": {"synthetic": True, "source": "behavior-affect-synthesizer-v1", "template": f"{primary}:{index:02d}"}, "training_eligible": False, "affect_events": events, "affect_state": state, "affect_prompt": render_continuity_snapshot(state) + "\n\n" + render_affect_expression_contract(state), "safety_class": safety, "humor_target": humor, "must_include_any": [], "must_not_include": ["내 상태는", "airi_"]}
            try:
                validate_behavior_answer(record, answer, config["answer_min_chars"], config["answer_max_chars"])
            except BehaviorAnswerGateError as exc:
                raise BehaviorAffectSynthesisError(f"{record['id']}: {exc}") from exc
            result.append(record)
    if len(result) != 120 or len({x["prompt"] for x in result}) != 120 or len({x["answer"].strip() for x in result}) != 120:
        raise BehaviorAffectSynthesisError("records must have exactly 120 unique prompts and answers")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="deterministic affect pending queue synthesizer")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stats-only", action="store_true")
    args = parser.parse_args(argv)
    records = synthesize(load_config())
    summary = {"total": len(records), "behaviors": {key: sum(x["behavior"] == f"affect_{key}" for x in records) for key in load_config()["profiles"]["counts"]}, "splits": {key: sum(x["split"] == key for x in records) for key in ("train", "dev", "test")}, "training_eligible": False, "review_status": "pending"}
    if not args.stats_only:
        args.output.write_text("\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for x in records) + "\n", encoding="utf-8", newline="\n")
        summary["output"] = str(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
