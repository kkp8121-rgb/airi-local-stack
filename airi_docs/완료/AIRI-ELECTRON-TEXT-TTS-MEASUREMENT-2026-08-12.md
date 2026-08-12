# AIRI Electron text-to-speech measurement — 2026-08-12

## Scope

This checkpoint measures the real Electron client from direct text ingress to
the first substantive signal at the Windows default multimedia render
endpoint. Per the operator's direction, microphone speech and STT are replaced
by authenticated loopback `input:text`; the STT service was not started.

The tested client is the rebuilt Upgrade Scout source at `ef0217c5`, not the
older installed `app.asar`. The installed archive remained unchanged. The
runtime used the local Mi:dm model, the normal memory/knowledge configuration,
and the warmed GPT-SoVITS voice cache. The 20 measured prompts were synthetic
and non-personal. No raw audio, microphone audio, transcript, response text,
session ID, or trace ID was recorded by the meter.

## Live defect found and fixed

The first Scout build still waited for the full TTS body. GPT-SoVITS emits a
streaming RIFF header with a zero-sized `data` chunk and then continues with
PCM16 frames. `IncrementalPcmWavParser` treated that header as a genuinely empty
WAV, so the client fell back to `decodeAudioData` after the response ended.

The client fix treats subsequent bytes after that header as an open-ended PCM16
stream, while retaining odd trailing bytes and never exposing the RIFF header
as audio. A true empty WAV still emits no samples. Focused parser/response tests
pass 8/8, Stage UI typecheck passes, and the production Electron build passes.
The third runtime patch was regenerated from the fixed source and its manifest
was repinned.

Before the fix, the observed substantive playback event followed TTS end by
8 ms in the diagnostic turn. That turn also activated the repeat director, so
its 7.448 s total is evidence of full-buffer fallback, not a fair latency A/B
baseline.

## Measurement method

- `send-airi-local-text.mjs` now starts its monotonic timer immediately before
  `sendOrThrow`, after the WebSocket is connected, and returns a content-free
  wall-clock send timestamp only when the measurement-only timing flag is set.
- `measure-airi-text-to-speech.ps1` samples only
  `IAudioMeterInformation.GetPeakValue()` from the Windows default multimedia
  render endpoint every 15 ms. It stores only bounded peak regions.
- The first approximately 30 ms playback event is the fixed spoken ACK. The
  first render region after model content is reported as substantive speech;
  it is not confused with the ACK.
- The latency monitor is used only when its LLM, TTS, and playback correlation
  is explicit. Its cross-process event delivery can be reordered, so WASAPI
  render timing remains independently available when a same-ID monitor row is
  not preserved.

Twenty warm, distinct Korean prompts were run sequentially with enough spacing
to avoid overlapping the next measurement. Percentiles below use linear
interpolation.

## Results

| Metric | n | P50 | P95 | Range |
|---|---:|---:|---:|---:|
| text send → assistant completion | 20 | 718 ms | 794 ms | 534–828 ms |
| text send → first raw model content | 17 | 603 ms | 679 ms | 459–681 ms |
| text send → first accepted model content | 17 | 668 ms | 779 ms | 514–808 ms |
| text send → first substantive TTS proxy bytes | 17 | 1,801 ms | 2,402 ms | 1,347–2,607 ms |
| text send → first substantive default-render signal | 20 | **1,963 ms** | **2,720 ms** | 1,442–2,865 ms |
| TTS proxy first bytes → default-render signal | 17 | 182 ms | 385 ms | 95–386 ms |
| render lead before the same TTS segment ended | 17 | 772 ms | 1,735 ms | -53–1,874 ms |

All 20 sender calls completed without cancellation or timeout and all 20 had a
substantive render signal. In 15/17 explicitly correlated turns, rendering
began before the corresponding TTS segment ended. The other two utterances
were shorter than the playback pre-roll and began 53 ms after segment end.
This confirms that the zero-length-WAV fix activates progressive playback;
it does not merely make full-buffer decode faster.

The immediate ACK playback event was 29–44 ms and must not be reported as
answer latency. STT events were zero in every explicitly correlated turn, and
port 8890 remained closed.

## Remaining measurement limits

- Correlation was fully explicit in 17/20 turns. In the other three turns, ACK
  TTS/playback telemetry reached the monitor before the same runtime round's
  authoritative `llm/start`. The correlator immediately attached those events
  to the preceding row and cached the heuristic mapping, so the later start
  could not create an independent row. The affected rows consequently counted
  four TTS requests: two normal requests from each of two folded turns, not four
  PCM chunks. Runtime round IDs remained consistent. Their default-render
  measurements succeeded, but their per-stage telemetry is excluded from the
  17-turn phase percentiles. This is a remaining arrival-order instrumentation
  defect, not an audio failure; it needs a bounded per-request pending buffer.
- The render endpoint meter proves a signal entered the selected Windows output
  mix. It is stronger evidence than `AudioBufferSourceNode.start()`, but it does
  not prove physical sound pressure at the speaker. That would require an
  external acoustic sensor, which was intentionally not used.
- The sender still has no round-level natural-playback-end event. This report
  measures first substantive output, not complete utterance drain or lip-sync.
- The normal text path writes synthetic turns through the normal local journal.
  Those records were not deleted after the test. This is separate from approved
  knowledge fixture reproducibility and from operational knowledge deployment;
  no approved fixture was deployed here.

## Reproduction and verification

```powershell
node --test .\test-send-airi-local-text.mjs

.\measure-airi-text-to-speech.ps1 `
  -Text '집에서 할 수 있는 편안한 활동 하나만 추천해줘.' `
  -SourceRoot '<fixed Upgrade Scout client checkout>' `
  -Threshold 0.003
```

The Electron source test also requires the local proxy, warmed GPT-SoVITS
stack, latency monitor, and rebuilt Tamagotchi renderer. Do not infer STT,
microphone, physical-speaker, or natural-playback-end performance from this
text-only checkpoint.
