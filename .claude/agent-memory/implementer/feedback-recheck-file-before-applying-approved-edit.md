---
name: feedback-recheck-file-before-applying-approved-edit
description: Re-read a file right before applying a supervisor-approved out-of-scope edit; the supervisor may have already made it while approving.
metadata:
  type: feedback
---

When the supervisor grants permission to edit a file that was outside the original
allowed-write list, re-read the exact lines before editing instead of applying the
change blind.

**Why:** On the E2-C1 blind-v2 reseal the supervisor approved two edits to
`ollama-proxy/training/tests/test_verify_e2_c1_frozen_contract.py` and, in the same
window, applied those edits themselves along with the launcher-file pins they had
kept for themselves. Approval messages and their own edits crossed. Applying the
"approved" edit without looking would have duplicated or clobbered their work.

**How to apply:** After any approval that widens scope, run a targeted `grep`/`sed -n`
on the target lines (and `git status` / `git diff -U0` on the file) first. If the change
is already present, make no edit, re-run the verification commands, and say plainly in
the report that the edits were already in the tree and I changed nothing — see
[[feedback-deliver-report-via-sendmessage]].
