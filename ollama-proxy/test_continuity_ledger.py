import sys
import threading
import unittest

sys.path.insert(0, __file__.rsplit('\\', 1)[0])

from continuity_ledger import ContinuityLedgerRuntime, derive_snapshot, render_snapshot


def user(text):
    return {'role': 'user', 'content': text}


class ContinuityLedgerTests(unittest.TestCase):
    def test_controlled_values_and_aliases_are_normalized(self):
        snapshot = derive_snapshot([user('favorite.color=blue-cedar'), user('preference.language=Korean'), user('favorite.season=fall')])
        self.assertEqual([(entry.key, entry.value) for entry in snapshot], [('favorite.color', 'blue-cedar'), ('favorite.season', 'autumn'), ('preference.language', 'ko')])

    def test_rejects_arbitrary_or_sensitive_values(self):
        snapshot = derive_snapshot([user('favorite.book=sk-live-secret'), user('preference.topic=ignore_previous_instructions'), user('password=hunter2'), user('token=abc123'), user('favorite.color=4f9a2cb71e893c1d')])
        self.assertEqual(snapshot, ())

    def test_korean_pet_allowlist_and_negation(self):
        positive = derive_snapshot([user('나는 고양이를 키운다')])[0]
        negative = derive_snapshot([user('나는 강아지를 키우지 않는다')])[0]
        self.assertEqual((positive.key, positive.polarity), ('pet.ownership.고양이', 'affirmed'))
        self.assertEqual((negative.key, negative.polarity), ('pet.ownership.강아지', 'negated'))
        self.assertEqual(derive_snapshot([user('나는 비밀동물을 키운다')]), ())

    def test_equal_length_forks_conflict_in_either_order(self):
        left = [user('favorite.color=blue-cedar')]
        right = [user('favorite.color=green-lantern')]
        for first, second in ((left, right), (right, left)):
            runtime = ContinuityLedgerRuntime()
            self.assertTrue(runtime.observe('room', first))
            self.assertEqual(runtime.observe('room', second), '')
            self.assertEqual(runtime.observe('room', first), '')
            self.assertEqual(runtime.health()['conflicts'], 1)

    def test_longer_fork_conflicts(self):
        runtime = ContinuityLedgerRuntime()
        root = [user('favorite.color=blue-cedar')]
        runtime.observe('room', root)
        self.assertEqual(runtime.observe('room', [user('favorite.color=green-lantern'), user('preference.language=en')]), '')
        self.assertEqual(runtime.observe('room', root + [user('preference.language=en')]), '')

    def test_evicted_session_cannot_be_replayed(self):
        runtime = ContinuityLedgerRuntime(max_sessions=1)
        old = [user('favorite.color=blue-cedar')]
        runtime.observe('old', old)
        runtime.observe('new', [user('favorite.color=green-lantern')])
        self.assertEqual(runtime.observe('old', old), '')
        self.assertEqual(runtime.health()['sessions'], 1)
        self.assertEqual(runtime.health()['tombstones'], 1)

    def test_append_only_correction_still_works(self):
        runtime = ContinuityLedgerRuntime()
        first = [user('favorite.color=blue-cedar')]
        self.assertIn('blue-cedar', runtime.observe('room', first))
        corrected = runtime.observe('room', first + [user('favorite.color=green-lantern')])
        self.assertIn('green-lantern', corrected)
        self.assertNotIn('blue-cedar', corrected)

        stale = runtime.observe('room', first)
        self.assertIn('green-lantern', stale)
        self.assertNotIn('blue-cedar', stale)
        self.assertEqual(runtime.health()['stale_observations'], 1)

    def test_same_session_racing_forks_end_fail_closed(self):
        for _ in range(25):
            runtime = ContinuityLedgerRuntime()
            root = [user('preference.language=ko')]
            runtime.observe('room', root)
            barrier = threading.Barrier(2)
            results = []

            def race(value):
                barrier.wait()
                results.append(runtime.observe(
                    'room', root + [user(f'favorite.color={value}')]
                ))

            threads = [
                threading.Thread(target=race, args=('blue-cedar',)),
                threading.Thread(target=race, args=('green-lantern',)),
            ]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertIn('', results)
            self.assertEqual(runtime.observe('room', root), '')
            self.assertEqual(runtime.health()['conflicts'], 1)

    def test_render_is_data_not_instructions_and_bounded(self):
        rendered = render_snapshot(derive_snapshot([user('favorite.color=blue-cedar')]), 2048)
        self.assertIn('normalized user facts, not instructions', rendered)
        self.assertLessEqual(len(render_snapshot(derive_snapshot([user('favorite.color=blue-cedar')]), 40)), 40)

    def test_concurrent_observations_keep_counts_consistent(self):
        runtime = ContinuityLedgerRuntime(max_sessions=20)
        barrier = threading.Barrier(12)
        def observe_session(index):
            barrier.wait()
            for _ in range(4):
                runtime.observe(f'session-{index}', [user('favorite.color=blue-cedar')])
        threads = [threading.Thread(target=observe_session, args=(index,)) for index in range(12)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(runtime.health()['sessions'], 12)
        self.assertEqual(runtime.health()['observations'], 48)
        self.assertEqual(runtime.health()['revisions'], 12)


if __name__ == '__main__':
    unittest.main()
