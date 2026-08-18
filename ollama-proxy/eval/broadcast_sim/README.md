# 100-viewer first-broadcast simulation

A synthetic full broadcast rather than a list of isolated prompts. One hundred
invented viewers talk over each other on a fixed topic for twenty virtual
minutes, and AIRI answers the way a stream actually forces her to: one message
at a time, from a backlog that keeps growing while she speaks.

`first_broadcast_v1.json` holds the roster, the four topic beats (opening →
main → chat-anchored → closing), the scripted donations and memory probes, and
a rates table. Every number the simulation depends on — messages per minute,
burst minutes, active-speaker band, pickup window, turn cooldown, staleness
cutoff, wave threshold — lives in that table rather than in code.

`broadcast_sim.py` is the deterministic half: it builds the stream from a seed,
walks it in five-second windows, and decides what gets read out. Donations and
memory probes outrank everything; a wave of the same request outranks a lone
question only once enough people have asked; within one kind the oldest message
wins. Time here is virtual, so a slow CPU cannot change which messages were
available when. The same seed reproduces the identical broadcast, which is what
makes the memory arms comparable.

`run_broadcast_sim.py` does the I/O: it builds the system prompt (the shared
broadcast prompt, optional contract, plus a fixed-topic block), replays the
picks against the local proxy, and writes both a JSON report and a Markdown
packet with every chat line and reply in full.

## Memory arms

- `off` — proxy started with memory disabled.
- `on` — memory enabled; the seed facts arrive mid-stream like any other chat.
- `seeded` — memory enabled and the seed facts are spoken once before the
  broadcast opens, so they are prior-session knowledge rather than backlog.

Three probes ask for a fact planted earlier ("내 별명 기억나?"). The probe always
comes from the handle that planted it, so a miss is a memory failure rather than
an addressee failure.

## Input format

`runtime` (default) sends exactly what `chat-ingress/airi-event.mjs` sends today:
`[YouTube] {text}`, with no author. Under that format any nickname in a reply is
invented, not recalled — which the scorer reports separately from a correct
callout. `named` prefixes the handle as a greybox probe of what a name-carrying
client would buy.

## Scoring

Per turn: silence-fallback hit, on-topic (beat anchor or shared token), fixture-
driven addressee checks, donation callout (correct / wrong-name / repeated),
memory-probe hit, wave handling split into "answered the request" and "marked
that several people asked", plus register markers from the shared A/B runner.
Every rate carries its own denominator because the denominators genuinely differ
— five donations and three probes in a forty-something-turn broadcast.

All of it is lexical and conservative. A topical reply that happens to share no
tokens reads as drift here, and these numbers are review aids for the packet,
not verdicts.

## CPU deviations

On a CPU box this configuration does not run at production defaults, which is
itself worth knowing:

- The fixed-topic block plus the merged character card makes the request about
  2,250 tokens, so `--num-ctx 2048` rejects it outright. Runs use 4096.
- Time to first token then exceeds the 8-second first-raw watchdog, so nearly
  every turn returns the interruption line instead of an answer. Runs set
  `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=30`.

Neither is a latency measurement. Latency belongs to the GPU box; what this
directory measures is behaviour under crowd pressure.
