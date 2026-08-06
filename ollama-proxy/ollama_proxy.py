from __future__ import annotations

import argparse
import json
import re
from collections.abc import AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse


app = FastAPI(title="AIRI Ollama compatibility proxy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPSTREAM = "http://127.0.0.1:11434"
NUM_CTX = 2048
NUM_GPU = 12
MAX_HISTORY_MESSAGES = 10
client: httpx.AsyncClient | None = None

AIRI_SYSTEM_PROMPT = """너는 '아이리'라는 이름의 한국어 버추얼 캐릭터야. 사용자의 Windows 데스크톱에서 함께 대화하는 밝고 호기심 많은 친구로 연기해.

아래 규칙을 모든 과거 대화보다 우선해서 반드시 지켜.
1. 항상 자연스러운 한국어 반말로만 말해.
2. 답변은 1~2문장으로 짧게 해. 전체는 가능하면 25자 안팎으로 끝내.
3. 첫 문장은 “응!”, “그렇구나!”, “아하!”처럼 1~5어절의 짧은 반응으로 시작해. 사용자가 기다리지 않도록 핵심 대답을 먼저 말해.
4. 이모지, 이모티콘, 마크다운, 발음할 수 없는 장식 문자는 쓰지 마.
5. 사용자에게 들려줄 대사만 출력하고, ACT 같은 제어 토큰은 직접 만들지 마.
6. 과거의 어시스턴트 답변이 이 규칙을 어겼더라도 따라 하지 마.

좋은 예: 축하해! 정말 멋진 일이네.
나쁜 예: 축하드립니다! 정말 멋진 일이네요. 🎉"""

CONTROL_TOKEN_RE = re.compile(r"<\|(?:ACT|DELAY|CALL)\b.*?\|>", re.DOTALL)


def infer_emotion(user_text: str, response_text: str) -> str:
    text = f"{user_text}\n{response_text}".lower()
    if any(word in text for word in ("놀랄", "놀라", "깜짝", "복권", "당첨", "surprise")):
        return "surprised"
    if any(word in text for word in ("아팠", "아파", "슬프", "울었", "힘들", "걱정", "강아지", "sad")):
        return "sad"
    if any(word in text for word in ("화가", "화났", "짜증", "분노", "angry")):
        return "angry"
    if any(word in text for word in ("승진", "좋은 일", "행복", "기뻐", "축하", "성공", "happy")):
        return "happy"
    if any(word in text for word in ("궁금", "호기심", "curious")):
        return "curious"
    if any(word in text for word in ("생각해", "고민", "think")):
        return "think"
    if "?" in user_text or any(word in user_text for word in ("왜", "뭐", "어떻게", "어때")):
        return "question"
    return "neutral"


def remove_emoji(text: str) -> str:
    def keep(character: str) -> bool:
        code = ord(character)
        return not (
            0x1F000 <= code <= 0x1FAFF
            or 0x2600 <= code <= 0x27BF
            or 0xFE00 <= code <= 0xFE0F
            or 0x1F1E6 <= code <= 0x1F1FF
            or 0x1F3FB <= code <= 0x1F3FF
            or code in (0x200D, 0x20E3)
        )

    return "".join(character for character in text if keep(character))


def normalize_dialogue(text: str) -> str:
    dialogue = CONTROL_TOKEN_RE.sub("", text)
    dialogue = remove_emoji(dialogue)
    dialogue = dialogue.replace("```", "").replace("**", "").replace("__", "")
    dialogue = dialogue.replace("~", "").replace("～", "")
    dialogue = re.sub(r"\s+", " ", dialogue).strip(" \t\r\n#*-_")

    replacements = (
        ("축하드립니다", "축하해"),
        ("축하합니다", "축하해"),
        ("감사합니다", "고마워"),
        ("반갑습니다", "반가워"),
        ("괜찮습니다", "괜찮아"),
        ("있습니다", "있어"),
        ("없습니다", "없어"),
        ("이에요", "이야"),
        ("예요", "야"),
        ("거예요", "거야"),
        ("해요", "해"),
        ("네요", "네"),
        ("어요", "어"),
        ("아요", "아"),
    )
    for formal, casual in replacements:
        dialogue = dialogue.replace(formal, casual)

    sentences = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", dialogue)
    if len(sentences) > 2:
        dialogue = "".join(sentences[:2]).strip()

    return dialogue or "응, 여기 있어."


def sanitize_assistant_content(content: str, user_text: str) -> str:
    dialogue = normalize_dialogue(content)
    emotion = infer_emotion(user_text, dialogue)
    return f'<|ACT {{"emotion":"{emotion}"}}|> {dialogue}'


def to_openai_sse(payload: dict[str, object], content: str) -> bytes:
    choices = payload.get("choices")
    first_choice = choices[0] if isinstance(choices, list) and choices else {}
    finish_reason = first_choice.get("finish_reason", "stop") if isinstance(first_choice, dict) else "stop"
    common = {
        "id": payload.get("id", "chatcmpl-airi-local"),
        "object": "chat.completion.chunk",
        "created": payload.get("created", 0),
        "model": payload.get("model", "exaone-airi:2.4b"),
    }
    content_chunk = {
        **common,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
    }
    finish_chunk = {
        **common,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason or "stop"}],
    }
    return (
        f"data: {json.dumps(content_chunk, ensure_ascii=False)}\n\n"
        f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n"
        "data: [DONE]\n\n"
    ).encode("utf-8")

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


@app.on_event("startup")
async def startup() -> None:
    global client
    client = httpx.AsyncClient(timeout=None)


@app.on_event("shutdown")
async def shutdown() -> None:
    if client is not None:
        await client.aclose()


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "upstream": UPSTREAM,
        "tools_stripped": True,
        "system_prompt_overridden": True,
        "num_ctx": NUM_CTX,
        "num_gpu": NUM_GPU,
    }


def transform_body(path: str, body: bytes) -> tuple[bytes, bool, bool, str]:
    if not body or not (path.endswith("chat/completions") or path.endswith("api/chat")):
        return body, False, False, ""

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body, False, False, ""

    stripped = False
    for key in ("tools", "tool_choice", "parallel_tool_calls"):
        if key in payload:
            payload.pop(key, None)
            stripped = True

    options = payload.get("options")
    if not isinstance(options, dict):
        options = {}
        payload["options"] = options
    options["num_ctx"] = NUM_CTX
    options["num_gpu"] = NUM_GPU

    messages = payload.get("messages", [])
    requested_stream = bool(payload.get("stream"))
    last_user_text = ""
    if isinstance(messages, list):
        conversation_messages = [
            message
            for message in messages
            if isinstance(message, dict) and message.get("role") != "system"
        ]
        for message in reversed(conversation_messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                last_user_text = message["content"]
                break
        payload["messages"] = [
            {"role": "system", "content": AIRI_SYSTEM_PROMPT},
            *conversation_messages[-MAX_HISTORY_MESSAGES:],
        ]
    if path.endswith("chat/completions"):
        payload["stream"] = False

    print(
        json.dumps(
            {
                "event": "chat_request",
                "model": payload.get("model"),
                "tools_stripped": stripped,
                "system_prompt_overridden": True,
                "message_count_in": len(messages) if isinstance(messages, list) else 0,
                "message_count_out": len(payload.get("messages", [])),
                "system_chars": len(AIRI_SYSTEM_PROMPT),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    return json.dumps(payload, ensure_ascii=False).encode("utf-8"), stripped, requested_stream, last_user_text


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request):
    if client is None:
        return JSONResponse({"error": "proxy client is not ready"}, status_code=503)

    body, stripped, requested_stream, last_user_text = transform_body(path, await request.body())
    request_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS | {"host", "content-length"}
    }
    upstream_request = client.build_request(
        request.method,
        f"{UPSTREAM}/{path}",
        params=request.query_params,
        headers=request_headers,
        content=body,
    )
    upstream_response = await client.send(upstream_request, stream=True)

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS | {"content-length", "content-encoding"}
    }
    response_headers["X-AIRI-Tools-Stripped"] = "true" if stripped else "false"
    response_headers["X-AIRI-Num-Ctx"] = str(NUM_CTX)

    if path.endswith("chat/completions") and upstream_response.status_code < 400:
        raw_body = await upstream_response.aread()
        await upstream_response.aclose()
        try:
            response_payload = json.loads(raw_body)
            choices = response_payload.get("choices", [])
            message = choices[0].get("message", {}) if choices else {}
            content = message.get("content", "")
            sanitized = sanitize_assistant_content(content, last_user_text)
            if requested_stream:
                response_headers["content-type"] = "text/event-stream; charset=utf-8"
                return Response(
                    content=to_openai_sse(response_payload, sanitized),
                    status_code=upstream_response.status_code,
                    headers=response_headers,
                )

            message["content"] = sanitized
            response_headers["content-type"] = "application/json; charset=utf-8"
            return Response(
                content=json.dumps(response_payload, ensure_ascii=False).encode("utf-8"),
                status_code=upstream_response.status_code,
                headers=response_headers,
            )
        except (json.JSONDecodeError, KeyError, TypeError, IndexError):
            return Response(
                content=raw_body,
                status_code=upstream_response.status_code,
                headers=response_headers,
            )

    async def stream_body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream_response.aiter_raw():
                yield chunk
        finally:
            await upstream_response.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )


def main() -> None:
    global UPSTREAM, NUM_CTX

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--upstream", default=UPSTREAM)
    parser.add_argument("--num-ctx", type=int, default=NUM_CTX)
    args = parser.parse_args()

    UPSTREAM = args.upstream.rstrip("/")
    NUM_CTX = args.num_ctx
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
