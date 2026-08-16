# Synthetic affect broadcast evaluation

This is the A4 synthetic-only offline foundation and transport contract: six independently authored Korean broadcast-flow scenarios with 24 continuous turns each. The turns preserve distinct AIRI speech, screen/game state, selected viewer chat, no-response moments, and a canonical typed affect event. They cover first-broadcast warming, teasing and repair, repeated game failure and recovery, correction and admission, callback/donation/noise, and fatigue with safety precedence.

The evaluator checks the closed reducer oracle, exact scenario/event manifests, bounded fixed multi-turn history, OFF/ON request pairing, and safety/repair structure. It is not a completed Mi:dm A/B evaluation and does not score model quality; causal expression, continuity, positivity collapse, repair quality, safety/privacy, and character specificity require blind human review. Character specificity remains explicitly unscored until the A0 constitution is approved.

The default command performs no network work. Optional execution is transport-injected and accepts only `http://127.0.0.1:11435/api/chat` with `x-airi-turn-origin: local-evaluation`. It freezes the Mi:dm tag/digest, `num_ctx`, temperature, seed, token limit, history bound, and operational affect gate OFF through pre/post health evidence. Every arm uses the same canonical fixture history; the ON arm adds only the bounded request-local continuity note. Unselected no-response turns never call the model. Failed HTTP/JSON, empty output, incomplete pairs, or profile drift fail closed.

The CLI deliberately stays offline even with `--execute`; a real run needs an explicitly supplied loopback transport from an operator-controlled wrapper. The evaluator never changes an environment variable, starts a model, calls raw Ollama/cloud endpoints, mutates the production affect runtime, or authorizes operational adoption.

Public reports contain only counts, closed enums, and hashes; model and fixture text stay out. `build_private_review_packet` and `build_private_arm_key` are pure, separate artifacts so review rows can remain arm-blinded. They do not write files; ignored local custody and human rubric completion are explicit operator responsibilities.

This foundation uses independently authored synthetic chat only. It is separate from the authorized 30–120 minute real-chat replay campaign and from installed AIRI→11435→TTS evidence. Operational `AIRI_AFFECT_CONTINUITY_ENABLED` remains default OFF, and neither offline oracle success nor a future A/B result automatically adopts it.
