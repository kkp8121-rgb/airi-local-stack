import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import validate_approved_topics as gate
from topic_review_contract import record_sha256


def item(**overrides):
    value = {
        "id": "secret-topic-id",
        "title": "비공개 검수 제목",
        "source": "human review", "source_url": "https://example.test/secret-topic",
        "published_at": "2026-08-08T00:00:00Z",
        "summary": "8월 12일 비공개 검수 행사가 열린다.",
        "broadcast_line": "8월 12일 비공개 검수 행사 소식을 확인했어.",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    value.update(overrides)
    pending = {"pending_schema_version": 1, **value, "review": {"status": "pending", "reviewer": "", "reviewed_at": ""}}
    pending_hash = record_sha256(pending)
    decision = {"id": value["id"], "record_sha256": pending_hash, "decision": "approve", "source_verified": True, "published_at_verified": True, "summary_grounded": True, "broadcast_line_verified": True, "expires_at_verified": True, "notes": "", "reviewer": "reviewer-a", "reviewed_at": "2026-08-08T00:00:00Z"}
    return {key: value[key] for key in ("id", "title", "source", "published_at", "summary", "broadcast_line", "expires_at")} | {"approved": True, "provenance": {"source_url": value["source_url"], "pending_record_sha256": pending_hash}, "approval": {key: decision[key] for key in decision if key not in {"id", "record_sha256"}} | {"decision_record_sha256": record_sha256(decision)}}


class ValidateApprovedTopicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name) / "runtime"
        self.runtime.mkdir()
        self.runtime_patch = mock.patch.object(gate, "RUNTIME_ROOT", self.runtime)
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)

    def write(self, name, payload, *, parent=None):
        path = (parent or self.runtime) / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def run_gate(self, board):
        output = io.StringIO()
        with redirect_stdout(output):
            code = gate.main(["--board", str(board)])
        return code, json.loads(output.getvalue())

    def test_valid_live_v2_board_passes_without_granting_approval(self):
        code, output = self.run_gate(self.write("live.json", {"schema_version": 2, "approval_workflow_version": 1, "items": [item()]}))
        self.assertEqual(code, 0)
        self.assertEqual(output, {"status": "valid", "live_approved_count": 1})

    def test_v1_empty_expired_and_malformed_boards_are_rejected(self):
        cases = (
            {"schema_version": 1, "approval_workflow_version": 1, "items": [item()]},
            {"schema_version": 2, "approval_workflow_version": 1, "items": []},
            {"schema_version": 2, "approval_workflow_version": 1, "items": [item(expires_at="2026-08-01T00:00:00Z")]},
            {"schema_version": 2, "approval_workflow_version": 1, "items": "bad"},
        )
        for index, payload in enumerate(cases):
            with self.subTest(payload=payload):
                code, output = self.run_gate(self.write(f"rejected-{index}.json", payload))
                self.assertEqual(code, 1)
                self.assertEqual(output, {"status": "rejected", "live_approved_count": 0})

    def test_path_outside_runtime_is_rejected(self):
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text(json.dumps({"schema_version": 2, "approval_workflow_version": 1, "items": [item()]}), encoding="utf-8")
        code, output = self.run_gate(outside)
        self.assertEqual(code, 1)
        self.assertEqual(output, {"status": "rejected", "live_approved_count": 0})

    def test_output_is_content_free(self):
        board = self.write("hidden-name.json", {"schema_version": 2, "approval_workflow_version": 1, "items": [item()]})
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = gate.main(["--board", str(board)])
        rendered = stream.getvalue()
        self.assertEqual(code, 0)
        for secret in (str(board), "secret-topic-id", "비공개 검수 제목", "human review"):
            self.assertNotIn(secret, rendered)
        self.assertEqual(set(json.loads(rendered)), {"status", "live_approved_count"})

    def test_path_resolution_runtime_error_is_content_free(self):
        stream = io.StringIO()
        with mock.patch.object(gate, "_inside_runtime_regular_file", side_effect=RuntimeError("hidden path")):
            with redirect_stdout(stream):
                code = gate.main(["--board", "ignored"])
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(stream.getvalue()),
            {"status": "rejected", "live_approved_count": 0},
        )
        self.assertNotIn("hidden path", stream.getvalue())

    def test_launcher_runs_the_gate_before_reusing_or_starting_proxy(self):
        launcher = Path(__file__).with_name("start-local-ollama-proxy.ps1").read_text(encoding="utf-8")
        invocation = "& $python $topicBoardValidator --board $resolvedTopicBoardPath"
        self.assertIn("validate_approved_topics.py", launcher)
        self.assertIn(invocation, launcher)
        self.assertLess(launcher.index(invocation), launcher.index("Get-NetTCPConnection"))


if __name__ == "__main__":
    unittest.main()
