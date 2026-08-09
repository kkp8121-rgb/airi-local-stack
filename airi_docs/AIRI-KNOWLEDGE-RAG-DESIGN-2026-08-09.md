# AIRI local approved-knowledge RAG

`knowledge_store.py` is a deliberately separate local SQLite database for approved reference knowledge: games, comics, general knowledge, and time-bounded topical material. It must not read, write, join, or share a database with session memory, journals, extraction, or evaluation data.

## Boundary and input contract

Only local JSON or JSONL records with `approved: true` are accepted. Each record contains `source`, `title`, `version`, optional `published_at`/`expires_at`, `content`, and `provenance`. Content receives a SHA-256 hash; a matching source/title/hash is a duplicate, while changed content updates the document and replaces its chunks. The importer accepts no URL, network access, model download, or implicit discovery.

The CLI is dry-run by default:

```powershell
python knowledge_ingest.py --runtime-dir .\runtime --input .\runtime\approved-knowledge.jsonl
python knowledge_ingest.py --runtime-dir .\runtime --input .\runtime\approved-knowledge.jsonl --apply
```

Both the input and database path must resolve below the supplied runtime directory. UNC, traversal/outside-runtime paths, oversize input, bidi/control characters, and prompt-injection/control-token patterns are rejected before writes.

## Retrieval contract

The store chunks normalized content deterministically (700 characters, 100-character overlap), indexes chunks with SQLite FTS5, and filters expired documents. `retrieve(query, top_k=4, max_chars=1600)` returns bounded `KnowledgeHit` values with public provenance metadata. The caller supplies any local embedder; embeddings are stored as JSON vectors and cosine-ranked when available. An absent or failing embedder never fetches a model and falls back to lexical retrieval.

The proxy integration should render retrieved text as untrusted, attributed reference context, never as personal memory or instructions. It must preserve the existing memory and journal isolation.

## Operations

`health()` returns only `ok`, document/chunk counts, and whether semantic retrieval was configured. It intentionally exposes no content, source title, session identifier, or filesystem path. The store has no session ID field and therefore cannot become a personal-memory store by accident.
