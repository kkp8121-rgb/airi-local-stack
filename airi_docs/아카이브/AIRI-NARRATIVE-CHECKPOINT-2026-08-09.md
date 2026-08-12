# AIRI narrative checkpoint — 2026-08-09

## Applied

- Replaced the Korean locale's legacy Neko Ayaka / real-person / age-based identity prompt with an original AIRI identity.
- Removed the legacy gift example and outward ACT/DELAY/CALL formatting instructions from the Korean locale prompt.
- Added Korean-first language behavior and an original AIRI lore frame: signal garden, unfinished map, and audience co-creation.
- Made MapleStory, Eternal Return, and gifts occasional user-led topics rather than AIRI's default identity or recurring subject.
- Added the same narrative and a final card-precedence contract to the local Ollama proxy.
- Updated the official v0.11.3 source locale at `<AIRI_SOURCE_ROOT>/packages/i18n/src/locales/ko/base.yaml`; rebuilt the package before the renderer build.
- Preserved the existing ACT sanitizer; fragmented bare ACT envelopes are removed before wire output and journal text.
- Added a private `conversation_event` table for validated leading ACT envelopes; canonical `conversation_message` now stores only dialogue while health remains aggregate-only.

## Runtime verification

- i18n TypeScript check passed with the package-local `tsc --noEmit`.
- Proxy focused prompt/card tests passed: 4/4.
- AIRI renderer build passed with the rebuilt i18n package.
- Fresh installed app.asar SHA-256: `754D29C56A767AFF405CC8DE27020CAC2CE6DD003FABF6FD441F7FF706DA484A`.
- New local chat produced Korean dialogue without a visible ACT token and without the prior game-topic opening.
- Added bounded phrase-level casual Korean cleanup for common `-시나요/-인가요` model endings; a fresh chat now returned informal Korean.
- External search, cloud chat/extraction, evaluation collection, and 11436 remain OFF.

## Remaining work

- Separate complete user/assistant dialogue history from internal ACT/transport metadata in durable logs.
- Add an explicit Korean-language mismatch gate with a user-language exception.
- Re-test a fresh session and a real microphone utterance for the `메이플스토리` first-word path.

## 2026-08-09 response-boundary follow-up

- A recent real microphone turn was persisted with a short semantic substitution; this is an STT decode error, not a memory rewrite. The raw utterance and misrecognition are intentionally omitted. The STT service remains `large-v3-turbo/CUDA/float16` with generic beam search 3; no phrase-specific correction was added.
- The proxy now appends `AIRI_FINAL_CONTRACT` even when no active card is supplied. Inline transcript restarts such as `사용자:` and `대화 예시입니다:` are removed only after strong sentence boundaries, preserving ordinary colons in speech.
- Memory remains durable user/assistant dialogue only; system prompts and per-request contracts are not appended to the memory journal. The app's recent conversation history can still be sent as context, so a polluted historical assistant turn must be cleared by starting a fresh conversation rather than treating it as a saved system prompt.
- Focused proxy regression: 89 tests pass. A loopback request with a deliberately polluted card returned plain Korean speech without the transcript preamble after the patch.

## 2026-08-09 local broadcast incident

- A live idle-broadcast observation contained a sequence of transcript/status labels (`사용자:`, `대화 예시`, `Stage Execution Plan`, and similar). This was not intended VTuber narration and was not caused by system prompts being written into the memory DB. The idle director was accepting generic prompt-echo candidates repeatedly on its cooldown.
- `packages/stage-ui/src/stores/broadcast-director.ts` now rejects generic speaker, transcript, prompt-example, scenario, and protocol labels before TTS. The filter is semantic/protocol-level and does not enumerate user topics.
- `packages/stage-ui/src/stores/broadcast-director.test.ts` adds five representative rejection cases; focused Vitest passes 7/7. A fresh stage build completed, and a full replacement app.asar was installed at the AIRI app location with the previous bundle preserved as `app.asar.pre-broadcast-filter-20260809`.
- AIRI was left stopped after installation to prevent the previously enabled local-broadcast setting from speaking before manual verification. Before restarting, turn Local broadcast OFF, verify ordinary chat, then enable it only for a short bounded test.
- Packaging audit found and corrected an intermediate nested-`out` mistake: the final installed bundle is the corrected artifact with `/out/main/index.js`, `/out/renderer/index.html`, and the new `broadcast-director-CYJiM4HW.js` at the real renderer path. The nested intermediate bundle is preserved as `app.asar.pre-nested-out-20260809`.
- Korean-first streaming gate is now active when the latest user turn contains Hangul; explicit English input remains allowed. Re-check other languages before final regression.
- Final Python regression with temporary dependencies and `PYTHONPATH=<repo>` passed: 304 tests.
- Runtime snapshot after regression: 11435 `status=ok`, session header present 12/missing 0, proactive requests 11/completions 11; 8892 completion counter 30.
- Run the final focused regression set, then one full regression at the final logical checkpoint.
