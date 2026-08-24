---
name: feedback-report-blocked-runs-do-not-retry
description: When a test/script refuses because a live training run or process is active, stop and report the refusal verbatim instead of retrying or clearing the blocker
metadata:
  type: feedback
---

If a contract or script refuses to run because ambient state is live (e.g. an active durable
training runner), capture the refusal text and stop. Do not retry, wait it out, or remove the
blocking process.

**Why:** The supervisor owns the GPU arms and the run lifecycle; a worker retrying can pause or
disturb a real training run. On 2026-08-24 the durability contract refused with
"Durability contract refuses to invoke auto-pause while an ambient durable runner is active" after
a GPU arm restarted mid-task; the supervisor's standing instruction was to report it and let them
rerun after the arm finished.

**How to apply:** Verify the ambient state before running anything that touches process discovery,
run once, and if refused report the exact message plus the observed PIDs and their creation times.
Note in the report which assertions the refused run therefore never reached. Report it through
[[feedback-deliver-report-via-sendmessage]].
