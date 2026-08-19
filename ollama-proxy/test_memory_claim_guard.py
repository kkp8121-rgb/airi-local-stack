import unittest

from memory_claim_guard import guard_memory_claim, is_bare_memory_assertion, is_memory_probe


FALLBACK = "음… 그건 확실하게 기억 안 나. 다시 알려줄래?"


class MemoryClaimGuardTests(unittest.TestCase):
    def test_probe_detection_covers_the_simulated_phrasings(self) -> None:
        # 100인 시뮬레이션에서 실제로 쓰인 프로브 3형 + 변형.
        for text in ("AIRI, 내 별명 기억나?", "아까 내가 뭐 끝났다고 했는지 기억해?",
                     "우리 고양이 이름 뭐랬지?", "내가 뭐라고 했지?",
                     "어제 말한 거 기억 안 나?"):
            self.assertTrue(is_memory_probe(text), text)
        for text in ("오늘 날씨 좋다", "이름 뜻이 뭐야?", "노래 해줘", ""):
            self.assertFalse(is_memory_probe(text), text)

    def test_bare_assertions_are_caught_and_content_is_not(self) -> None:
        for text in ("응, 기억해!", "응, 기억해.", "기억나!", "당연히 기억하지~",
                     "응! 기억하고 있어", "어, 기억나지…"):
            self.assertTrue(is_bare_memory_assertion(text), text)
        for text in ("새벽두시였지!", "응, 초코야!", "응, 기억해! 새벽두시잖아",
                     "아직 기억 못 했어.", "음… 그건 확실하게 기억 안 나. 다시 알려줄래?",
                     "기억해 둘게", ""):
            self.assertFalse(is_bare_memory_assertion(text), text)

    def test_guard_replaces_only_the_dishonest_combination(self) -> None:
        # T21 실측 재현: 근거 없는 "응, 기억해!" — 교체된다.
        replaced, fired = guard_memory_claim("AIRI, 내 별명 기억나?", "응, 기억해!", FALLBACK)
        self.assertTrue(fired)
        self.assertEqual(replaced, FALLBACK)
        # 내용을 말하면 맞든 틀리든 통과 — 사실성 판정은 이 가드 소관이 아니다.
        kept, fired = guard_memory_claim("우리 고양이 이름 뭐랬지?", "응, 이름이 초코야!", FALLBACK)
        self.assertFalse(fired)
        self.assertEqual(kept, "응, 이름이 초코야!")
        # 프로브가 아니면 bare assertion도 통과한다 ("기억해?"라고 안 물었으니까).
        kept, fired = guard_memory_claim("오늘 뭐 했어?", "응, 기억해!", FALLBACK)
        self.assertFalse(fired)
        # 정직한 회피는 그대로 — 가드 문구를 다시 가드하지 않는다.
        kept, fired = guard_memory_claim("내 별명 기억나?", FALLBACK, FALLBACK)
        self.assertFalse(fired)


if __name__ == "__main__":
    unittest.main()
