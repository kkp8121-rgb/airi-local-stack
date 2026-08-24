---
name: feedback-deliver-report-via-sendmessage
description: Final worker reports must be delivered with SendMessage to the supervisor; ending a turn with only text output counts as going idle without reporting
metadata:
  type: feedback
---

End every assigned task by calling SendMessage to the supervisor (`main` / team-lead) with the
full final report. Plain assistant text does not reach them.

**Why:** On the E2-C1 durability-contract task (2026-08-24) I wrote a complete report as my final
assistant message and stopped. The supervisor saw nothing and had to chase it with "You went idle
without delivering your report" — the whole task looked unfinished even though the code and test
run were done.

**How to apply:** Treat the SendMessage call as part of the deliverable, not a courtesy. Send it
before ending the turn, in the exact shape the supervisor asked for (files with line ranges, what
each case asserts, exact commands with exit codes, verbatim PASS/failure line, `git diff --check`
exit code, anything unverified, and the doc/SSoT updates they now owe). Related:
[[feedback-report-blocked-runs-do-not-retry]].
