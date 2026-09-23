import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import system1_judge as judge  # noqa: E402


def common_run(left, right):
    best = 0
    for i in range(len(left)):
        for j in range(len(right)):
            k = 0
            while i + k < len(left) and j + k < len(right) and left[i + k] == right[j + k]:
                k += 1
            best = max(best, k)
    return best


def test_modes_default_to_the_existing_heuristic_first():
    assert judge.CANDIDATE_SELECT_MODES[0] == "heuristic"
    assert set(judge.CANDIDATE_SELECT_MODES) == {
        "heuristic", "rule-early-exit", "system1-shadow", "system1-early-exit",
    }


def test_rule_gate_rejects_questions_and_long_copies_but_keeps_shared_names():
    chat = "리제 목소리 오늘 진짜 쉬었다"
    assert judge.rule_reject_reason("그래서 어떻게 됐어?", chat, common_run) == "question"
    assert judge.rule_reject_reason("그래서 어떻게 됐어？ ", chat, common_run) == "question"
    assert judge.rule_reject_reason("리제 목소리 오늘 진짜 쉬었다니까.", chat, common_run) == "chat_copy"
    assert judge.rule_reject_reason("리제 목소리 걱정되긴 하지.", chat, common_run) is None


def test_stop_rules_per_mode():
    assert judge.stop_here("rule-early-exit", None, None, 0.5)
    assert not judge.stop_here("rule-early-exit", "question", None, 0.5)
    assert judge.stop_here("system1-early-exit", None, 0.7, 0.5)
    assert not judge.stop_here("system1-early-exit", None, 0.3, 0.5)
    assert not judge.stop_here("system1-early-exit", "chat_copy", 0.99, 0.5)
    assert not judge.stop_here("system1-early-exit", None, None, 0.5)
    assert not judge.stop_here("system1-shadow", None, 0.99, 0.5)
    assert not judge.stop_here("heuristic", None, 0.99, 0.5)


def test_fallback_prefers_the_best_rule_clean_score_then_any_score():
    calls = [
        {"attempt": 1, "system1_p": 0.9, "rule_reject": "question"},
        {"attempt": 2, "system1_p": 0.4, "rule_reject": None},
        {"attempt": 3, "system1_p": 0.45, "rule_reject": None},
        {"attempt": 4},
    ]
    assert judge.fallback_index(calls, [0, 1, 2, 3]) == 2
    assert judge.fallback_index(calls, [0]) == 0
    assert judge.fallback_index(calls, [3]) is None


def test_model_input_is_the_trained_format():
    assert judge.model_input("안녕", "왔구나.") == "채팅: 안녕\n반응: 왔구나."


def test_client_posts_utf8_and_validates_the_probability(monkeypatch):
    seen = {}

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return Response({"p": seen.get("p", 0.8)})

    monkeypatch.setattr(judge.urllib.request, "urlopen", fake_urlopen)
    client = judge.System1Client("http://127.0.0.1:11510/")
    probability, elapsed = client.score("목 아파", "목 관리 잘하자.")
    assert probability == 0.8 and elapsed >= 0
    assert seen["url"] == "http://127.0.0.1:11510/score"
    assert seen["body"] == {"chat": "목 아파", "candidate": "목 관리 잘하자."}
    seen["p"] = 1.5
    try:
        client.score("a", "b")
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range probability must be rejected")
