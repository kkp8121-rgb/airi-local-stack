# Mi:dm replay output-boundary readiness — 2026-08-15

## Result

The local Mi:dm tag and pinned digest were verified through a temporary
loopback-only proxy on port 11435 with memory, knowledge, evaluation,
moderation, input screening, and epistemic confidence all OFF. No external
chat, credential, remote endpoint, or operational gate promotion was used.

The first synthetic readiness turn exposed two blockers before a real
30–120-minute replay:

1. the conversation-soak runner concatenated the proxy's intentional audible
   ACT-wrapped ACK with the substantive model reply, causing a false
   `no_control` failure and contaminating later synthetic history;
2. the buffered OpenAI non-stream path used by `run_chat_replay.py` could return
   an empty assistant message after output-boundary rejection, which the replay
   runner correctly rejects.

The soak runner now removes only one exact, header-declared audible ACK before
scoring/history, reports its closed classification/count, retains unexpected
control text as a failure, and rejects the canonical waiting fallback as
non-substantive. The proxy now gives ordinary non-proactive buffered turns the
same canonical nonempty liveness fallback used by streaming, through the
existing tool-truth boundary. Designed proactive silence is unchanged.

## Runtime recheck

After restarting only the owned temporary proxy process, the same OFF profile
reported the exact `midm-airi:2.0-mini` digest as pinned and verified with
`num_ctx=2048`. The synthetic greeting stream produced one classified local
ACK, no remaining control token, and a substantive plain reply. The matching
non-stream request returned a nonempty, control-free response. The owned proxy
was then stopped; port 11435 was not left running.

This is a one-turn local readiness result, not the requested long-stream chat
campaign, not a B1b/TTS end-to-end result, and not evidence for operationally
enabling epistemic confidence or the B4c broadcast contract.

## Verification

- conversation-soak focused tests: 12 PASS;
- changed-path proxy tests: PASS;
- `test-current-checkpoint.ps1`: PASS;
- the active Python 3.14 environment has no pytest;
- the full proxy unittest file retains one unrelated pre-existing
  timing-sensitive watchdog metadata failure under Python 3.14.

## Remaining gate

The requested result still requires an actively live, explicitly authorized
YouTube broadcast and local API key/provenance, six qualifying 30–120-minute
capture phases across three anonymous sources, paired Mi:dm OFF/ON replay,
private human review, and content-free campaign aggregation. Operational ON
adoption remains a separate user decision.
