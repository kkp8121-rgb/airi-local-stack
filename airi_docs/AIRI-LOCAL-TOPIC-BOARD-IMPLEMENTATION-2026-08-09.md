# AIRI local topic board implementation

## Runtime boundary

- The board is OFF unless `AIRI_TOPIC_BOARD_PATH` is explicitly configured.
- `start-local-ollama-proxy.ps1 -TopicBoardPath ...` accepts only a regular file under `ollama-proxy/runtime`.
- The proxy reads the file only for an exact loopback `x-airi-turn-origin: local-proactive` request.
- Regular chat never receives a topic block.
- Proactive chat skips journal RAG and memory retrieval entirely.
- AIRI source uses `historyProjection: 'system-only'` and `runtimeContextProjection: 'none'`, so recent user examples and private character-state observations do not become idle-broadcast subjects.
- Cloud chat, cloud search, extraction, and evaluation collection are not enabled by this feature.

## File contract

Copy `ollama-proxy/approved-topics.example.json` into `ollama-proxy/runtime` and add explicitly approved items.

```json
{
  "schema_version": 1,
  "items": [{
    "id": "topic-2026-08-09-01",
    "title": "Short title",
    "source": "Human-approved source label",
    "published_at": "2026-08-09T00:00:00Z",
    "summary": "One or two factual sentences.",
    "expires_at": "2026-08-10T00:00:00Z",
    "approved": true
  }]
}
```

The loader requires an absolute local path, a file no larger than 256 KiB, at most 64 items, safe bounded text, a valid ID, `approved: true`, a non-future publication time, and a live expiration later than publication. One invalid approved item fails the whole board closed.

## Delivery and persistence

- At most one approved item is appended to the transformed system prompt as `[Untrusted Topic]`.
- Raw topic ID/title/source/summary stays in the transient local model request. It is never copied into `original_messages`, memory SQLite, character state, extraction, or evaluation storage.
- A topic enters the bounded in-process recent set only after a non-empty terminal response is consumed. Cancellation, failure, or empty output leaves it eligible.
- The spoken local-only assistant sentence may appear in AIRI's local chat UI, but provider history and cloud/context bridges exclude it.
- `/health.topic_board` exposes only content-free counters and status; no path, ID, title, source, or summary is returned.

## Operational default

The default launch keeps the path empty. This preserves the user's explicit approval boundary. Automatic fetching, RSS polling, and external search remain out of scope and OFF.
