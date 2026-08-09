# AIRI Focus-Free Chat Checkpoint — 2026-08-10

## Outcome

The loopback server-channel sender can submit text without mouse or keyboard
focus, correlate the matching completion, and recover assistant text from both
the completion envelope and the preceding assistant-message event.

The local proxy no longer speaks an internal language apology when a model
response is rejected. It now:

1. finalizes a terminal unpunctuated Korean candidate before quality checks;
2. retries a control-only or ungrounded response once with request-local
   correction constraints;
3. accepts only a grounded, tool-truth-preserving corrected sentence; and
4. after two model failures, uses a narrowly bounded observation that preserves
   the user's Korean declarative facts and changes only a conservative ending.

Character-card sanitization also removes generic `<|NAME PAYLOAD|>` transport
templates when they appear in control-format instruction paragraphs or as a
standalone transport-template paragraph. Persona prose and embedded harmless
angle-bracket text remain available to the character.

The final observation path is disabled for questions, commands, knowledge or
safety turns, proactive turns, foreign-language requests, control/speaker
labels, and first-, second-, or collective-person wording that could reverse
the speaker. Common Korean homographs in `하늘을 나는 새가`, `티가 나`, and
`저 산이` remain ordinary observations rather than speaker pronouns.

## Live verification

Two sequential synthetic loopback inputs completed without focusing the AIRI
window. Matching nonempty Korean assistant completions arrived in 812 ms and
919 ms. Each produced one TTS segment. The content-free latency trace marked
the bounded grounded-observation path and showed no language/meta fallback.

After the final safety review and proxy restart, one additional synthetic turn
completed in 3,236 ms with a 24-character Korean completion. It produced one
TTS segment in 2,050 ms and used the same bounded observation path.

Playback-start telemetry was still absent after both successful TTS results.
That is a separate installed-renderer/round-lifecycle checkpoint; this commit
does not claim acoustic playback success.

## Verification

- `python -m unittest -q test_ollama_proxy.py`: 211 passed
- `python -m unittest discover -q`: 528 passed
- `node --test test-send-airi-local-text.mjs test-get-airi-local-voice-status.mjs`: 12 passed
- `git diff --check`: passed (line-ending warnings only)

No real dialogue, session identifier, local absolute path, credential, audio,
runtime database, model output transcript, or topic-review artifact is included
in this checkpoint.
