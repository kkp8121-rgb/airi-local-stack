# v2ProPlus speaker-embedding cache overlay

The overlay is process-memory-only: it caches `sv_model.compute_embedding3` for
the unchanged cached reference set; it writes neither raw audio nor embeddings.
Its hot-path identity check uses the already-cached tensor pointer/version and
does not copy or hash reference audio back to the CPU on every sentence.
The same wrapper evaluates the unchanged upstream generator under PyTorch
`inference_mode` (upstream already uses `no_grad`) to remove version-tracking
overhead without changing sampling, model weights, or streaming mode.
It fails closed unless external `TTS.py` matches the pinned SHA-256.

It does not choose the proxy streaming mode. The production campaign currently
uses fixed-length streaming mode 3 with `min_chunk_length=16`; the previous
mode 2 path remains available for diagnostic A/B runs. The overlay changes none
of WAV, reference/prompt fields,
or `parallel_infer=false`. The narrow integration hook is replacing the external
backend process command before `api_v2.py` is imported:

```powershell
$py='C:\Projects\airi\external\GPT-SoVITS\.venv\Scripts\python.exe'
& $py .\gpt-sovits\run_v2proplus_with_sv_cache.py --external-root C:\Projects\airi\external\GPT-SoVITS -- -a 127.0.0.1 -p 9880 -c .\gpt-sovits\tts-infer-v2proplus.yaml
```

For a reviewed upstream update, pass its exact TTS.py SHA-256 using
`--tts-sha256`; otherwise startup aborts before the external API starts.
