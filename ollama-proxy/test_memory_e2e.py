import asyncio
import json
import os
import tempfile
import unittest
from unittest import mock

import httpx

import ollama_proxy
from memory_runtime import MemoryConfig, MemoryRuntime


class ExtractionResponse:
    def __init__(self, content): self.content = content
    def raise_for_status(self): pass
    def json(self): return {"message": {"content": self.content}}


class ExtractionClient:
    def __init__(self, replies): self.replies, self.calls = list(replies), []
    async def get(self, url, timeout=None):
        return type("Tags", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"models":[{"name":"test:latest"}]},
        })()
    async def post(self, url, json):
        self.calls.append((url, json))
        return ExtractionResponse(self.replies.pop(0))


class LocalResponse:
    status_code = 200
    headers = {"content-type": "application/x-ndjson"}
    def __init__(self, text):
        self.content = json.dumps({"choices":[{"message":{"content":text}}]}, ensure_ascii=False).encode()
        self.closed = False
    async def aread(self): return self.content
    async def aiter_raw(self):
        text = json.loads(self.content)["choices"][0]["message"]["content"]
        event = json.dumps(
            {"message": {"role": "assistant", "content": text}, "done": True},
            ensure_ascii=False,
        ).encode("utf-8")
        yield event + b"\n"
    async def aclose(self): self.closed = True


class LocalClient:
    def __init__(self, replies): self.replies, self.requests = list(replies), []
    def build_request(self, _method, _url, **kwargs): return kwargs.get("content", b"")
    async def send(self, request, stream=False):
        self.requests.append(json.loads(request))
        return LocalResponse(self.replies.pop(0))


class LocalOnlyProvider:
    ready = False
    def health(self): return {"provider":"local","ready":False}


class MemoryEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_proxy_extract_store_and_retrieve_on_next_question(self):
        stage_a=json.dumps({"extracted":[
            {"turnNumber":1,"kind":"entity","subtype":"person","name":"{{user}}","content":"아이리의 대화 상대"},
            {"turnNumber":1,"kind":"fact","subtype":"trait","subjectNames":["{{user}}"],"content":"{{user}}는 민트초코를 좋아한다.","turnRange":[1,1]},
        ]},ensure_ascii=False)
        stage_b=json.dumps({"operations":[
            {"op":"ADD_ENTITY","sourceItemIndex":0,"sourceTurnNumber":1,"alias":"e0","subtype":"person","name":"{{user}}","content":"아이리의 대화 상대","turnRange":None,"reason":None},
            {"op":"ADD_FACT","sourceItemIndex":1,"sourceTurnNumber":1,"alias":"f0","subtype":"trait","content":"{{user}}는 민트초코를 좋아한다.","subjectAliases":["e0"],"turnRange":[1,1],"reason":None},
        ]},ensure_ascii=False)
        stage_b=json.dumps({"decisions":[
            {"sourceItemIndex":0,"action":"add","candidateAlias":None,"reason":None},
            {"sourceItemIndex":1,"action":"add","candidateAlias":None,"reason":None},
        ]},ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            extraction=ExtractionClient([stage_a,stage_b])
            runtime=MemoryRuntime(MemoryConfig(
                enabled=True,db_path=os.path.join(tmp,"memory.db"),session_id="s",
                extraction_threshold=2,extraction_model="test",user_display_name="민석",
            ),http_client=extraction)
            await runtime.startup()
            local=LocalClient(["응! 기억할게.","응! 말해볼게."])
            transport=httpx.ASGITransport(app=ollama_proxy.app)
            with mock.patch.object(ollama_proxy,"client",local), mock.patch.object(
                ollama_proxy,"memory_runtime",runtime
            ), mock.patch.object(ollama_proxy,"cloud_chat_provider",LocalOnlyProvider()), mock.patch.object(
                ollama_proxy,"emit_latency_event"
            ):
                async with httpx.AsyncClient(transport=transport,base_url="http://test") as browser:
                    first=await browser.post("/v1/chat/completions",headers={"x-airi-session-id":"s"},json={
                        "model":"exaone-airi:2.4b","stream":True,
                        "messages":[{"role":"user","content":"나는 민트초코를 좋아해."}],
                    })
                    self.assertEqual(first.status_code,200)
                    if ollama_proxy.memory_journal_tasks:
                        await asyncio.gather(*list(ollama_proxy.memory_journal_tasks))
                    tasks=list(runtime._extract_tasks.values())
                    if tasks: await asyncio.gather(*tasks)
                    self.assertEqual(runtime.store.job_state("s")["extracted_up_to_msg"],1)
                    self.assertEqual(len(runtime.store.active_rows("s","fact")),1)

                    # No accepted extractor is needed for the second half of
                    # this contract; disable further scheduling after learning.
                    runtime.extraction_provider=type("Disabled",(),{"can_extract":False})()
                    second=await browser.post("/v1/chat/completions",headers={"x-airi-session-id":"s"},json={
                        "model":"exaone-airi:2.4b","stream":True,
                        "messages":[
                            {"role":"user","content":"나는 민트초코를 좋아해."},
                            {"role":"assistant","content":"기억할게."},
                            {"role":"user","content":"내가 뭘 좋아한다고 했지?"},
                        ],
                    })
                    self.assertEqual(second.status_code,200)
                    memory_blocks=[
                        message["content"] for message in local.requests[-1]["messages"]
                        if message.get("role")=="system" and str(message.get("content","")).startswith("[Character Memory]")
                    ]
                    self.assertEqual(len(memory_blocks),1)
                    self.assertIn("민석은 민트초코를 좋아한다.",memory_blocks[0])
                if ollama_proxy.memory_journal_tasks:
                    await asyncio.gather(*list(ollama_proxy.memory_journal_tasks),return_exceptions=True)
            await runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
