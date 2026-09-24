import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sim_broadcast as sim  # noqa: E402
from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER, render_broadcast_context  # noqa: E402


class SimBroadcastTests(unittest.TestCase):
    def test_receipt_answer_drops_only_the_attested_marker(self) -> None:
        raw = '<|ACT {"emotion":"think"}|>오늘은 여기까지야!'
        self.assertEqual(sim.receipt_answer(raw, 'marker'), '오늘은 여기까지야!')
        self.assertEqual(sim.receipt_answer(raw, 'silent'), raw)
        self.assertEqual(sim.receipt_answer(' 안녕 ', None), '안녕')

    def test_forced_history_is_the_conversation_before_the_turn(self) -> None:
        rows = [{'chat': '안녕', 'answer': '반가워!'}, {'chat': '뭐 해?', 'answer': '방송 중이야.'}, {'chat': '셋째', 'answer': 'x'}]
        self.assertEqual(sim.forced_history(rows, 0), [])
        self.assertEqual(sim.forced_history(rows, 2), [
            {'role': 'user', 'content': '[YouTube] 안녕'}, {'role': 'assistant', 'content': '반가워!'},
            {'role': 'user', 'content': '[YouTube] 뭐 해?'}, {'role': 'assistant', 'content': '방송 중이야.'},
        ])

    def test_broadcast_context_passes_the_proxy_wire_validation(self) -> None:
        context = sim.broadcast_context('첫 방송', '오프닝', '막 시작했다.', '- 이번 턴에 말할 것: 반가워!\n')
        self.assertTrue(context['briefing'].startswith(BROADCAST_BRIEFING_HEADER + '\n'))
        self.assertIn('- 이번 턴에 말할 것: 반가워!', render_broadcast_context(context))
        self.assertEqual(sim.broadcast_context('첫 방송', '오프닝', '막 시작했다.', '  ')['briefing'], '')


if __name__ == '__main__':
    unittest.main()
