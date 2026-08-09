import os
import tempfile
import unittest

from evaluation_store import (EvaluationConfig, EvaluationDisabledError,
                              EvaluationStore, EvaluationStoreError, EvaluationValidationError,
                              NullEvaluationStore)


class EvaluationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "evaluations.sqlite3")
        self.store = EvaluationStore(EvaluationConfig(True, self.path))
        self.provenance = {"origin": "user_approved", "model": "airi", "model_version": "v1",
                           "system_prompt_sha256": "a" * 64, "memory_schema_version": 1,
                           "dataset_version": "airi-g3-v1"}
        self.messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]

    def tearDown(self):
        self.temp.cleanup()

    def rating(self, **overrides):
        value = {"consent": True, "messages": self.messages, "response": "hi", "rating": "good", "reason_tags": ["persona_drift"]}
        value.update(overrides)
        return self.store.add_rating(value, self.provenance)

    def test_consent_must_be_exact_true_and_disabled_is_safe(self):
        for consent in (False, None, 1, "true"):
            with self.assertRaises(EvaluationValidationError): self.rating(consent=consent)
        with self.assertRaises(EvaluationDisabledError):
            EvaluationStore(EvaluationConfig(False, self.path)).add_rating({}, {})
        self.assertFalse(NullEvaluationStore().health()["enabled"])

    def test_validation_does_not_expose_raw_input(self):
        with self.assertRaises(EvaluationValidationError) as error:
            self.rating(messages=[{"role": "system", "content": "TOP-SECRET"}])
        self.assertNotIn("TOP-SECRET", str(error.exception))
        with self.assertRaises(EvaluationValidationError): self.rating(rating="revise", correction=None)
        with self.assertRaises(EvaluationValidationError): self.rating(rating="bad", reason_tags=[])
        with self.assertRaises(EvaluationValidationError): self.rating(response="   ")
        with self.assertRaises(EvaluationValidationError): self.rating(reason_tags=["not-allowed"])

    def test_rating_and_preference(self):
        rating = self.rating(rating="revise", correction="better answer")
        preference = self.store.add_preference({"consent": True, "messages": self.messages, "chosen": "A", "rejected": "B", "reason_tags": ["too_long"]}, self.provenance)
        self.assertEqual(rating["status"], "needs_review")
        all_records = self.store.export_records(False)
        self.assertEqual([item["kind"] for item in all_records], ["rating", "preference"])
        self.assertNotIn("consent", all_records[0])

    def test_review_export_delete_and_health_privacy(self):
        first = self.rating()
        second = self.rating(rating="bad")
        self.store.review(first["id"], "approved")
        self.store.review(second["id"], "rejected")
        exported = self.store.export_records()
        self.assertEqual([item["id"] for item in exported], [first["id"]])
        health = self.store.health()
        self.assertEqual(health["counts"]["approved"], 1)
        self.assertNotIn("path", str(health).lower())
        self.assertNotIn(self.path, str(health))
        with self.assertRaises(EvaluationValidationError): self.store.export_records(limit=1001)
        self.assertTrue(self.store.delete(first["id"]))
        self.assertFalse(self.store.delete(first["id"]))

    def test_reopen_persists(self):
        record = self.rating()
        reopened = EvaluationStore(EvaluationConfig(True, self.path))
        self.assertEqual(reopened.export_records(False)[0]["id"], record["id"])

    def test_capacity_is_bounded_and_delete_frees_a_slot(self):
        store = EvaluationStore(EvaluationConfig(True, self.path, max_records=2))
        first = store.add_rating(
            {"consent": True, "messages": self.messages, "response": "A", "rating": "good", "reason_tags": []},
            self.provenance,
        )
        store.add_rating(
            {"consent": True, "messages": self.messages, "response": "B", "rating": "good", "reason_tags": []},
            self.provenance,
        )
        with self.assertRaises(EvaluationStoreError):
            store.add_rating(
                {"consent": True, "messages": self.messages, "response": "C", "rating": "good", "reason_tags": []},
                self.provenance,
            )
        health = store.health()
        self.assertEqual(health["total"], 2)
        self.assertEqual(health["max_records"], 2)
        self.assertTrue(store.delete(first["id"]))
        store.add_rating(
            {"consent": True, "messages": self.messages, "response": "C", "rating": "good", "reason_tags": []},
            self.provenance,
        )

    def test_environment_defaults(self):
        old_enabled = os.environ.pop("AIRI_EVAL_ENABLED", None)
        old_db = os.environ.pop("AIRI_EVAL_DB", None)
        old_max = os.environ.pop("AIRI_EVAL_MAX_RECORDS", None)
        try:
            config = EvaluationConfig.from_env()
            self.assertFalse(config.enabled)
            self.assertEqual(config.db_path, "runtime/airi-evaluations.sqlite3")
            self.assertEqual(config.max_records, 10000)
        finally:
            if old_enabled is not None: os.environ["AIRI_EVAL_ENABLED"] = old_enabled
            if old_db is not None: os.environ["AIRI_EVAL_DB"] = old_db
            if old_max is not None: os.environ["AIRI_EVAL_MAX_RECORDS"] = old_max


if __name__ == "__main__":
    unittest.main()
