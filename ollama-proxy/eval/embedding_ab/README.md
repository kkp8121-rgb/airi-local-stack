# Korean memory-recall embedding A/B

`korean_memory_recall_v1.json` is a pinned synthetic set of 48 memory statements
and 24 queries, six in each of four categories. It exists because the stock
`benchmark_memory_track.py --mode embedding` fixture is four documents and three
queries — enough to smoke-test that an embedder loads, not enough to separate two
strong Korean models, which both score a perfect MRR on it.

The distractors are the point:

- `lexical` — the query shares surface tokens with its target; the easy baseline.
- `paraphrase` — target and query share almost no content words, so lexical
  matching cannot succeed and only the embedding can.
- `disambiguation` — several documents mention the same attribute for different
  people (one keeps cats, another is allergic to them, a third wants a dog), so
  picking the right entity is the whole task.
- `supersede` — an old fact and its replacement both exist, and the query decides
  which one is wanted ("지금 어디 살아?" versus "예전에 어디 살았어?").

Every person, donation, and broadcast event here is invented. Nothing in this
directory is viewer data.

`run_embedding_ab.py` ranks the entire corpus per query by cosine similarity and
reports MRR, recall@1/3/5, median rank, and per-category breakdowns, plus the
individual misses so a regression can be read rather than guessed. Reporting per
category is deliberate: an aggregate mean hides the trade-off that actually
matters, where one model wins on paraphrase while losing on disambiguation.

Loading a model is the only step that can reach the network and it is refused
unless `--allow-download` is passed. A model that fails to load is recorded as an
error entry rather than aborting the run, so the other arm still produces a
result.

```
python run_embedding_ab.py --model kure=nlpai-lab/KURE-v1 --model bge=BAAI/bge-m3 --report out.json
```

The scores describe ranking behaviour on this authored set only. They are not a
claim about production recall quality, not a latency measurement of the runtime
path, and not an approval to switch the operational embedder.
