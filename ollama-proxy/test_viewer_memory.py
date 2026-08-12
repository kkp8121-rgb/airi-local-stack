import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from viewer_memory import (
    ViewerFactInput,
    ViewerMemoryStore,
    ViewerObservation,
)


TOKEN_A = "a" * 43
TOKEN_B = "b" * 43
TOKEN_C = "c" * 43


def viewer(token=TOKEN_A): return f"viewer:v1:{token}"
def event(token=TOKEN_A): return f"yt:v1:{token}"
def broadcast(token=TOKEN_A): return f"broadcast:v1:{token}"


class ViewerMemoryTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.store = ViewerMemoryStore(self.path, enabled=True)

    def tearDown(self):
        for suffix in ("", "-wal", "-shm"):
            try: os.unlink(self.path + suffix)
            except FileNotFoundError: pass

    def observation(self, **changes):
        values = dict(event_key=event(), viewer_key=viewer(), broadcast_key=broadcast(),
                      display_name="  A\u0301   viewer  ", observed_at=100.0, donation=False)
        values.update(changes)
        return ViewerObservation(**values)

    def test_default_disabled_is_inert_and_creates_no_file(self):
        target = Path(self.path + ".disabled")
        store = ViewerMemoryStore(target)
        self.assertFalse(target.exists())
        self.assertEqual(store.observe(self.observation(), now=100), {"status": "disabled"})
        self.assertEqual(store.record_fact(ViewerFactInput(viewer(), "interest", "game", "viewer_explicit", 1, 2), now=1), {"status": "disabled"})
        self.assertIsNone(store.claim_callback_candidate(viewer(), now=3))
        self.assertFalse(store.delete_viewer(viewer()))
        self.assertFalse(store.health()["ready"])

    def test_configuration_and_tier_require_exact_integers(self):
        for option in ({"tier1_cap": 10.0}, {"tier2_cap": 30.0}, {"display_name_history": 2.0},
                       {"tier1_cap": True}, {"tier2_cap": False}, {"display_name_history": True}):
            with self.subTest(option=option), self.assertRaises(ValueError):
                ViewerMemoryStore(self.path + ".invalid", enabled=True, **option)
        self.store.observe(self.observation(), now=100)
        for value in (1.0, True, "1"):
            with self.subTest(tier=value), self.assertRaises(ValueError):
                self.store.set_tier(viewer(), value)

    def test_strict_pseudonyms_and_typed_inputs_reject_raw_or_extra_data(self):
        for field, value in (("viewer_key", "raw-youtube-id"), ("viewer_key", f"viewer:v1:{'a'*42}"),
                             ("event_key", "raw-message"), ("broadcast_key", "live-stream-id")):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.store.observe(self.observation(**{field: value}), now=100)
        with self.assertRaises(ValueError):
            self.store.observe({"viewer_key": viewer(), "message": "private chat text"}, now=100)
        with self.assertRaises(ValueError):
            self.store.record_fact({"viewer_key": viewer(), "value": "parsed from chat"}, now=100)
        with self.assertRaisesRegex(ValueError, "surrogate"):
            self.store.observe(self.observation(display_name="bad\ud800name"), now=100)

    def test_exact_wire_adapter_rejects_text_extras_and_converts_milliseconds(self):
        wire = {"eventId": event(), "viewerKey": viewer(), "displayName": "Alice", "kind": "text",
                "publishedAtMs": 123456, "broadcastKey": broadcast()}
        observation = ViewerObservation.from_wire(wire)
        self.assertEqual(observation.observed_at, 123.456)
        self.assertFalse(observation.donation)
        self.assertEqual(self.store.observe(observation, now=123.456), {"status": "observed", "new_visit": True})
        for changed in ({**wire, "text": "private"}, {**wire, "kind": "superChatEvent"},
                        {**wire, "publishedAtMs": 1.5}, {key: value for key, value in wire.items() if key != "viewerKey"}):
            with self.assertRaises(ValueError):
                ViewerObservation.from_wire(changed)

    def test_observation_and_fact_future_times_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "future"):
            self.store.observe(self.observation(observed_at=131), now=100)
        self.store.observe(self.observation(observed_at=130), now=100)
        with self.assertRaisesRegex(ValueError, "future"):
            self.store.record_fact(ViewerFactInput(viewer(), "interest", "future", "viewer_explicit", 131, 200), now=100)

    def test_exact_event_is_idempotent_and_collision_fails_closed(self):
        self.assertEqual(self.store.observe(self.observation(), now=100), {"status": "observed", "new_visit": True})
        self.assertEqual(self.store.observe(self.observation(), now=100), {"status": "duplicate", "new_visit": False})
        with self.assertRaises(ValueError):
            self.store.observe(self.observation(display_name="Different"), now=100)
        self.assertEqual(self.store.health(), {"enabled": True, "ready": True, "schema": 1,
                                               "viewers": 1, "visits": 1, "facts": 0, "donations": 0})

    def test_visits_are_broadcast_scoped_and_names_are_normalized_and_bounded(self):
        self.store.observe(self.observation(), now=100)
        self.store.observe(self.observation(event_key=event(TOKEN_B), display_name="Second Name", observed_at=101), now=101)
        self.store.observe(self.observation(event_key=event(TOKEN_C), broadcast_key=broadcast(TOKEN_B),
                                            display_name="Third Name", observed_at=102), now=102)
        with self.store._session() as connection:
            profile = connection.execute("SELECT display_name,visit_count FROM viewer").fetchone()
            visits = connection.execute("SELECT event_count FROM visit ORDER BY broadcast_key").fetchall()
            names = connection.execute("SELECT display_name FROM viewer_name ORDER BY first_seen").fetchall()
        self.assertEqual((profile["display_name"], profile["visit_count"]), ("Third Name", 2))
        self.assertEqual([row[0] for row in visits], [2, 1])
        self.assertEqual([row[0] for row in names], ["Á viewer", "Second Name", "Third Name"])

        limited = ViewerMemoryStore(self.path, enabled=True, display_name_history=2)
        limited.observe(self.observation(event_key=event("d" * 43), display_name="Fourth", observed_at=103), now=103)
        with limited._session() as connection:
            retained = [row[0] for row in connection.execute("SELECT display_name FROM viewer_name ORDER BY last_seen")]
        self.assertEqual(retained, ["Third Name", "Fourth"])

    def test_out_of_order_observation_does_not_roll_current_name_backward(self):
        self.store.observe(self.observation(display_name="Current", observed_at=200), now=200)
        self.store.observe(self.observation(event_key=event(TOKEN_B), display_name="Stale", observed_at=100), now=200)
        with self.store._session() as connection:
            profile = connection.execute("SELECT display_name,first_seen,last_seen FROM viewer").fetchone()
        self.assertEqual((profile["display_name"], profile["first_seen"], profile["last_seen"]),
                         ("Current", 100, 200))

    def test_tiers_are_manual_and_caps_are_enforced(self):
        self.store.observe(self.observation(), now=100)
        with self.store._session() as connection:
            self.assertEqual(connection.execute("SELECT tier FROM viewer").fetchone()[0], 3)
        self.assertEqual(self.store.set_tier(viewer(), 1), {"status": "updated", "tier": 1})
        for index in range(1, 20):
            token = chr(ord("d") + index) * 43
            key = viewer(token)
            self.store.observe(self.observation(event_key=event(token), viewer_key=key, display_name=f"Viewer {index}"), now=100)
            self.store.set_tier(key, 1)
        extra = viewer("z" * 43)
        self.store.observe(self.observation(event_key=event("z" * 43), viewer_key=extra, display_name="Extra"), now=100)
        with self.assertRaisesRegex(ValueError, "population cap"):
            self.store.set_tier(extra, 1)

    def test_explicit_facts_expiry_and_callback_cooldown(self):
        self.store.observe(self.observation(display_name="Alice"), now=100)
        interest = ViewerFactInput(viewer(), "interest", "  puzzle   games ", "viewer_explicit", 100, 50000)
        status = ViewerFactInput(viewer(), "status", "starting a project", "operator_reviewed", 110, 50000)
        self.assertEqual(self.store.record_fact(interest, now=100), {"status": "recorded"})
        self.assertEqual(self.store.record_fact(interest, now=100), {"status": "duplicate"})
        self.store.record_fact(status, now=110)
        candidate = self.store.claim_callback_candidate(viewer(), now=200)
        self.assertEqual((candidate.display_name, candidate.fact_type, candidate.value), ("Alice", "interest", "puzzle games"))
        self.assertIsNone(self.store.claim_callback_candidate(viewer(), now=201))
        self.assertIsNotNone(self.store.claim_callback_candidate(viewer(), now=200 + 6 * 60 * 60))
        self.assertIsNone(self.store.claim_callback_candidate(viewer(), now=50001 + 6 * 60 * 60))
        with self.assertRaises(ValueError):
            self.store.record_fact(ViewerFactInput(viewer(), "interest", "parsed", "model_inferred", 1, 2), now=1)
        with self.assertRaisesRegex(ValueError, "90 days"):
            self.store.record_fact(ViewerFactInput(
                viewer(), "interest", "too durable", "viewer_explicit", 1, 1 + 91 * 24 * 60 * 60
            ), now=1)

    def test_donation_is_count_only_and_health_is_content_free(self):
        self.store.observe(self.observation(donation=True, display_name="Private Name"), now=100)
        self.store.record_fact(ViewerFactInput(viewer(), "interest", "Private Interest", "viewer_explicit", 100, 200), now=100)
        with self.store._session() as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(donation_aggregate)")]
            aggregate = connection.execute("SELECT event_count FROM donation_aggregate").fetchone()[0]
        self.assertEqual(columns, ["viewer_key", "broadcast_key", "event_count", "last_observed_at"])
        self.assertEqual(aggregate, 1)
        serialized = repr(self.store.health())
        self.assertNotIn("Private Name", serialized)
        self.assertNotIn("Private Interest", serialized)
        self.assertNotIn(viewer(), serialized)

    def test_delete_and_retention_prune_cascade(self):
        self.store.observe(self.observation(), now=100)
        self.store.set_tier(viewer(), 1)
        self.store.record_fact(ViewerFactInput(viewer(), "status", "old", "viewer_explicit", 100, 150), now=100)
        fact_prune = self.store.prune(now=200)
        self.assertEqual(fact_prune["facts"], 1)
        self.assertEqual(self.store.observe(self.observation(), now=200),
                         {"status": "duplicate", "new_visit": False})
        day = 24 * 60 * 60
        result = self.store.prune(now=400 * day)
        self.assertEqual(result["viewers"], 1)
        self.assertEqual(self.store.health()["viewers"], 0)
        self.assertEqual(self.store.observe(self.observation(), now=400 * day),
                         {"status": "duplicate", "new_visit": False})
        self.assertEqual(self.store.health()["viewers"], 0)
        tombstone_prune = self.store.prune(now=731 * day)
        self.assertEqual(tombstone_prune["events"], 1)
        self.assertEqual(self.store.observe(self.observation(), now=731 * day),
                         {"status": "observed", "new_visit": True})
        self.assertEqual(self.store.health()["viewers"], 1)
        self.assertTrue(self.store.delete_viewer(viewer()))

        self.store.observe(self.observation(event_key=event(TOKEN_B), viewer_key=viewer(TOKEN_B), donation=True), now=100)
        self.store.record_fact(ViewerFactInput(viewer(TOKEN_B), "interest", "live", "viewer_explicit", 100, 200), now=100)
        self.assertTrue(self.store.delete_viewer(viewer(TOKEN_B)))
        self.assertFalse(self.store.delete_viewer(viewer(TOKEN_B)))
        with self.store._session() as connection:
            for table in ("viewer_name", "visit", "observed_event", "viewer_fact", "donation_aggregate"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_concurrent_duplicate_and_unique_events_serialize(self):
        same = self.observation()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.observe(same, now=100), range(24)))
        self.assertEqual(sum(item["status"] == "observed" for item in results), 1)
        self.assertEqual(sum(item["status"] == "duplicate" for item in results), 23)

        observations = [self.observation(event_key=event(chr(ord("d") + index) * 43), observed_at=200 + index)
                        for index in range(12)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda item: self.store.observe(item, now=300), observations))
        with self.store._session() as connection:
            profile = connection.execute("SELECT visit_count FROM viewer").fetchone()[0]
            event_count = connection.execute("SELECT event_count FROM visit").fetchone()[0]
        self.assertEqual((profile, event_count), (1, 13))

    def test_concurrent_callback_claim_has_one_winner(self):
        self.store.observe(self.observation(), now=100)
        self.store.record_fact(ViewerFactInput(viewer(), "interest", "puzzles", "viewer_explicit", 100, 1000), now=100)
        with ThreadPoolExecutor(max_workers=8) as pool:
            candidates = list(pool.map(lambda _: self.store.claim_callback_candidate(viewer(), now=200), range(16)))
        self.assertEqual(sum(candidate is not None for candidate in candidates), 1)

    def test_concurrent_tier_promotion_stops_at_exact_cap(self):
        alternate = self.path + ".tiers"
        store = ViewerMemoryStore(alternate, enabled=True, tier1_cap=10)
        keys = []
        try:
            for index in range(20):
                token = f"{index:043d}"
                keys.append(viewer(token))
                store.observe(self.observation(event_key=event(token), viewer_key=viewer(token),
                                               display_name=f"Viewer {index}"), now=100)
            def promote(key):
                try:
                    return store.set_tier(key, 1)["status"]
                except ValueError:
                    return "capped"
            with ThreadPoolExecutor(max_workers=12) as pool:
                outcomes = list(pool.map(promote, keys))
            self.assertEqual((outcomes.count("updated"), outcomes.count("capped")), (10, 10))
            with store._session() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM viewer WHERE tier=1").fetchone()[0], 10)
        finally:
            for suffix in ("", "-wal", "-shm"):
                try: os.unlink(alternate + suffix)
                except FileNotFoundError: pass

    def test_unrelated_or_conflicting_database_is_rejected_before_ddl(self):
        for name, statement in (("unrelated", "CREATE TABLE memory(id INTEGER PRIMARY KEY, content TEXT)"),
                                ("conflict", "CREATE TABLE viewer(viewer_key TEXT PRIMARY KEY, raw_id TEXT)")):
            target = self.path + f".{name}"
            connection = sqlite3.connect(target)
            connection.execute(statement)
            connection.commit()
            before = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            connection.close()
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "dedicated"):
                ViewerMemoryStore(target, enabled=True)
            connection = sqlite3.connect(target)
            after = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            connection.close()
            self.assertEqual(after, before)
            self.assertFalse(any(row[1] == "viewer_memory_owner" for row in after))
            for suffix in ("", "-wal", "-shm"):
                try: os.unlink(target + suffix)
                except FileNotFoundError: pass

    def test_concurrent_constructors_share_one_atomic_initialization(self):
        target = self.path + ".constructors"
        try:
            with ThreadPoolExecutor(max_workers=12) as pool:
                stores = list(pool.map(lambda _: ViewerMemoryStore(target, enabled=True), range(24)))
            self.assertTrue(all(store.health()["ready"] for store in stores))
            connection = sqlite3.connect(target)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM viewer_memory_owner").fetchone()[0], 1)
            connection.close()
        finally:
            for suffix in ("", "-wal", "-shm"):
                try: os.unlink(target + suffix)
                except FileNotFoundError: pass

    def test_literal_case_schema_tampering_is_rejected_with_valid_owner_marker(self):
        target = self.path + ".tampered"
        store = ViewerMemoryStore(target, enabled=True)
        del store
        connection = sqlite3.connect(target)
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("ALTER TABLE viewer_fact RENAME TO viewer_fact_old")
        connection.execute("""CREATE TABLE viewer_fact (
          id INTEGER PRIMARY KEY, viewer_key TEXT NOT NULL REFERENCES viewer(viewer_key) ON DELETE CASCADE,
          fact_type TEXT NOT NULL CHECK(fact_type IN ('Interest','status')), value TEXT NOT NULL,
          provenance TEXT NOT NULL CHECK(provenance IN ('viewer_explicit','operator_reviewed')),
          observed_at REAL NOT NULL, expires_at REAL NOT NULL CHECK(expires_at > observed_at), last_callback_at REAL,
          UNIQUE(viewer_key, fact_type, value, provenance, observed_at))""")
        connection.execute("DROP TABLE viewer_fact_old")
        connection.commit()
        owner = connection.execute("SELECT ownership_token,schema_version,schema_signature FROM viewer_memory_owner").fetchone()
        connection.close()
        self.assertEqual(owner[1], 1)
        with self.assertRaisesRegex(RuntimeError, "dedicated"):
            ViewerMemoryStore(target, enabled=True)
        for suffix in ("", "-wal", "-shm"):
            try: os.unlink(target + suffix)
            except FileNotFoundError: pass

    def test_schema_version_mismatch_fails_without_migration_guessing(self):
        with self.store._session(immediate=True) as connection:
            connection.execute("UPDATE viewer_memory_owner SET schema_version=99")
        with self.assertRaisesRegex(RuntimeError, "ownership or schema"):
            ViewerMemoryStore(self.path, enabled=True)


if __name__ == "__main__":
    unittest.main()
