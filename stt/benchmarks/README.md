# Offline STT benchmark

`benchmark_stt.py` evaluates a manifest of pre-recorded WAV files. It never opens a
microphone, contacts a network service, or loads a transcription model by default.
For deterministic CI, provide `--predictions predictions.json`; to invoke a local
decoder deliberately, pass `--transcriber package.module:function`.

The production Korean microphone corpus is private/external and is intentionally not
included here. The checked-in fixture is a metadata-only test double, not an
acceptance corpus and not evidence of microphone quality.

Example deterministic CI smoke check:

`python benchmark_stt.py --manifest synthetic-manifest.json --predictions synthetic-predictions.json --report report.json`

Manifest schema (`manifest-v1`):

```json
{"schema":"airi-stt-corpus-v1","items":[{"id":"unique-id","audio":"relative.wav","reference":"expected text","proper_nouns":["AIRI"]}]}
```

`audio` is required for decoder runs and is validated as WAV; it may be omitted
only by a metadata-only prediction test double. `proper_nouns` is optional. A
transcriber receives `(audio_path, beam_size)` and returns text.
