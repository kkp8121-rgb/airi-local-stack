from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name + "_affect_test", HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = _load("export_behavior_chat_dataset")
PLAIN_PENDING = HERE / "seed" / "airi_behavior_seed_pending.jsonl"
AFFECT_PENDING = HERE / "seed" / "airi_behavior_affect_seed_pending.jsonl"


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _approve(records: list[dict]) -> list[dict]:
    reviewed = copy.deepcopy(records)
    for record in reviewed:
        record["review"] = {
            "status": "approved",
            "reviewer": "human-reviewer",
            "approved_at": "2026-08-21",
        }
        record["training_eligible"] = True
    return reviewed


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")) for record in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class AffectBehaviorExportTests(unittest.TestCase):
    def test_affect_rows_use_exact_request_local_conversation_shape(self) -> None:
        reviewed = _approve(_read(AFFECT_PENDING))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "affect-reviewed.jsonl"
            _write(path, reviewed)
            rows, summary = exporter.export(path)

        self.assertEqual(summary["records"], 120)
        self.assertEqual(summary["splits"], {"train": 90, "dev": 15, "test": 15})
        for source, row in zip(reviewed, rows):
            self.assertEqual(
                [message["role"] for message in row["messages"]],
                ["system", "system", "user", "assistant"],
            )
            self.assertEqual(row["messages"][1], {
                "role": "system",
                "name": "airi_request_local",
                "content": source["affect_prompt"],
            })
            self.assertTrue(row["messages"][2]["content"].startswith("[YouTube] "))
            self.assertEqual(row["messages"][3]["content"], source["answer"])

    def test_plain_and_affect_reviews_combine_without_changing_plain_shape(self) -> None:
        plain = _approve(_read(PLAIN_PENDING))
        affect = _approve(_read(AFFECT_PENDING))
        with tempfile.TemporaryDirectory() as directory:
            plain_path = Path(directory) / "plain.jsonl"
            affect_path = Path(directory) / "affect.jsonl"
            _write(plain_path, plain)
            _write(affect_path, affect)
            rows, summary = exporter.export_many([plain_path, affect_path])

        self.assertEqual(summary["records"], 301)
        self.assertEqual(summary["splits"], {"train": 235, "dev": 33, "test": 33})
        self.assertTrue(all(len(row["messages"]) == 3 for row in rows[:181]))
        self.assertTrue(all(len(row["messages"]) == 4 for row in rows[181:]))

    def test_duplicate_and_affect_contract_drift_fail_closed(self) -> None:
        affect = _approve(_read(AFFECT_PENDING))
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.jsonl"
            second = Path(directory) / "second.jsonl"
            _write(first, affect)
            _write(second, [affect[0]])
            with self.assertRaises(exporter.BehaviorExportError):
                exporter.export_many([first, second])

            mutations = []
            prompt_drift = copy.deepcopy(affect[0])
            prompt_drift["affect_prompt"] += " drift"
            mutations.append(prompt_drift)
            event_drift = copy.deepcopy(affect[0])
            event_drift["affect_events"] = affect[8]["affect_events"]
            event_drift["affect_state"] = affect[8]["affect_state"]
            event_drift["affect_prompt"] = affect[8]["affect_prompt"]
            mutations.append(event_drift)
            wrong_split = copy.deepcopy(affect[0])
            wrong_split["split"] = "holdout"
            mutations.append(wrong_split)
            for index, mutation in enumerate(mutations):
                path = Path(directory) / f"broken-{index}.jsonl"
                _write(path, [mutation])
                with self.assertRaises(exporter.BehaviorExportError):
                    exporter.export(path)

    def test_pending_affect_rows_never_export(self) -> None:
        with self.assertRaises(exporter.BehaviorExportError):
            exporter.export(AFFECT_PENDING)


if __name__ == "__main__":
    unittest.main()
