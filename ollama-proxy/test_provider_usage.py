import os
import sqlite3
import tempfile
import unittest

from provider_usage import UsageLedger, UsageRecord, calculate_cost, report


class ProviderUsageTests(unittest.TestCase):
    def record(self, model="metered-model"):
        return UsageRecord("openai", model, "2026-01-01T00:00:00.000+00:00",
                           "2026-01-01T00:00:01.000+00:00", 1000, "completed",
                           10, 20, 3, 4)

    def test_ledger_only_has_operational_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "usage.sqlite3")
            ledger = UsageLedger(path)
            ledger.record(self.record())
            self.assertEqual(ledger.records(), [self.record()])
            db = sqlite3.connect(path)
            try:
                columns = {row[1] for row in db.execute("PRAGMA table_info(provider_usage)")}
            finally:
                db.close()
            self.assertEqual(columns, {"id", "provider", "model", "started_at", "ended_at", "duration_ms", "status",
                                       "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"})

    def test_cost_is_derived_at_report_time_and_unknown_without_price(self):
        prices = {"metered-model": {"input": 2.0, "output": 4.0, "cache_read": 1.0, "cache_write": 3.0}}
        # OpenAI prompt_tokens already includes the three cached tokens.
        self.assertEqual(calculate_cost(self.record(), prices), 0.000109)
        rows = report([self.record(), self.record("unpriced-model")], prices)
        self.assertEqual(rows[0]["cost_status"], "known")
        self.assertEqual(rows[1]["cost_status"], "unknown")
        self.assertIsNone(rows[1]["cost"])

    def test_anthropic_input_and_cache_counters_are_separate(self):
        record = UsageRecord("anthropic", "metered-model",
            "2026-01-01T00:00:00.000+00:00", "2026-01-01T00:00:01.000+00:00",
            1000, "completed", 10, 20, 3, 4)
        prices = {"metered-model": {"input": 2.0, "output": 4.0,
                                     "cache_read": 1.0, "cache_write": 3.0}}
        self.assertEqual(calculate_cost(record, prices), 0.000115)


if __name__ == "__main__":
    unittest.main()
