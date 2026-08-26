---
name: project-crlf-check-grep-is-broken
description: Verify CRLF with Python byte counting, not `grep -c $'\r'` — that pattern matches every line in this repo's Git Bash
metadata:
  type: project
---

To satisfy the supervisor's standing "CRLF count 0" check, count bytes in Python
(`open(f,'rb').read().count(b'\r\n')`), not `grep -c $'\r' <file>`.

**Why:** In this machine's Git Bash the `$'\r'` pattern degenerates and matches
*every* line — it reported `cr == total_lines` for pure-LF files and `0` for a
file that genuinely contained CRLF, i.e. exactly backwards. Acting on it would
mean either reporting a false CRLF violation or missing a real one.

**How to apply:** Any time a task says "verify CRLF 0 after edits". Note that
`core.autocrlf=true` here, so the working tree may legitimately hold CRLF while
git stores LF; the authoritative checks are the byte count on files you wrote
plus `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`. See
[[feedback-deliver-report-via-sendmessage]] — report the gotcha in the receipt so
the supervisor does not re-run the bad command.
