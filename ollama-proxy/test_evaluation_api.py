import os
import tempfile
import unittest
from unittest import mock

import httpx

import ollama_proxy
from evaluation_store import EvaluationConfig, EvaluationStore, NullEvaluationStore


class EvaluationApiTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, method, path, **kwargs):
        transport = httpx.ASGITransport(app=ollama_proxy.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    async def test_disabled_store_never_collects(self):
        with mock.patch.object(ollama_proxy, "evaluation_runtime", NullEvaluationStore()):
            status = await self.request("GET", "/v1/airi/evaluations/status")
            self.assertEqual(status.json()["enabled"], False)
            response = await self.request(
                "POST", "/v1/airi/evaluations/rating", json={"consent": True}
            )
            self.assertEqual(response.status_code, 503)

    async def test_explicit_rating_review_export_and_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EvaluationStore(EvaluationConfig(True, os.path.join(temp, "eval.db")))
            payload = {
                "consent": True,
                "messages": [{"role": "user", "content": "안녕"}],
                "response": "응, 안녕!",
                "rating": "revise",
                "correction": "응, 반가워!",
                "reason_tags": ["persona_drift"],
            }
            with mock.patch.object(ollama_proxy, "evaluation_runtime", store):
                created = await self.request(
                    "POST", "/v1/airi/evaluations/rating", json=payload
                )
                self.assertEqual(created.status_code, 201)
                record_id = created.json()["id"]
                before = await self.request("GET", "/v1/airi/evaluations/export")
                self.assertEqual(before.json()["records"], [])
                reviewed = await self.request(
                    "PATCH",
                    f"/v1/airi/evaluations/{record_id}",
                    json={"status": "approved"},
                )
                self.assertEqual(reviewed.json()["status"], "approved")
                exported = await self.request("GET", "/v1/airi/evaluations/export")
                record = exported.json()["records"][0]
                self.assertEqual(record["correction"], "응, 반가워!")
                self.assertEqual(record["provenance"]["memory_schema_version"], 1)
                self.assertEqual(len(record["provenance"]["system_prompt_sha256"]), 64)
                self.assertEqual(record["provenance"]["origin"], "user_approved")
                # Provenance follows the launcher-selected model, so an
                # unconfigured build cannot label a record with a stale tag.
                self.assertEqual(
                    record["provenance"]["model"], ollama_proxy.resolve_chat_model()
                )
                self.assertEqual(
                    record["provenance"]["model_version"],
                    ollama_proxy.resolve_chat_model(),
                )
                self.assertEqual(record["provenance"]["dataset_version"], "airi-g3-v1")
                deleted = await self.request(
                    "DELETE", f"/v1/airi/evaluations/{record_id}"
                )
                self.assertTrue(deleted.json()["deleted"])

    async def test_caller_cannot_spoof_server_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EvaluationStore(EvaluationConfig(True, os.path.join(temp, "eval.db")))
            payload = {
                "consent": True,
                "messages": [{"role": "user", "content": "안녕"}],
                "response": "응, 안녕!",
                "rating": "good",
                "origin": "synthetic",
                "model": "spoofed-model",
            }
            with mock.patch.object(ollama_proxy, "evaluation_runtime", store):
                rejected = await self.request(
                    "POST", "/v1/airi/evaluations/rating", json=payload
                )
                self.assertEqual(rejected.status_code, 400)
                self.assertEqual(store.health()["total"], 0)

    async def test_consent_and_request_size_are_enforced_without_echo(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EvaluationStore(EvaluationConfig(True, os.path.join(temp, "eval.db")))
            with mock.patch.object(ollama_proxy, "evaluation_runtime", store):
                rejected = await self.request(
                    "POST",
                    "/v1/airi/evaluations/preference",
                    json={"consent": False, "chosen": "SECRET", "rejected": "x"},
                )
                self.assertEqual(rejected.status_code, 400)
                self.assertNotIn("SECRET", rejected.text)
                oversized = await self.request(
                    "POST",
                    "/v1/airi/evaluations/rating",
                    content=b"x" * (ollama_proxy.EVALUATION_REQUEST_MAX_BYTES + 1),
                )
                self.assertEqual(oversized.status_code, 400)

    async def test_hostname_suffix_origin_cannot_read_or_mutate_evaluations(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EvaluationStore(EvaluationConfig(True, os.path.join(temp, "eval.db")))
            with mock.patch.object(ollama_proxy, "evaluation_runtime", store):
                headers = {"Origin": "http://localhost.evil"}
                exported = await self.request(
                    "GET", "/v1/airi/evaluations/export", headers=headers
                )
                self.assertEqual(exported.status_code, 403)
                created = await self.request(
                    "POST",
                    "/v1/airi/evaluations/rating",
                    headers=headers,
                    json={"consent": True},
                )
                self.assertEqual(created.status_code, 403)
                self.assertEqual(store.health()["total"], 0)


if __name__ == "__main__":
    unittest.main()
