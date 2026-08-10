# AIRI Remediation Final Handoff - 2026-08-10

## Scope and branch

This handoff records the source/patch remediation state at the end of the
current work session.

- Branch: `fix/code-audit-remediation-2026-08-07`
- The branch is source and patch work only. It does not contain a production
  topic board, review decisions, raw discovery data, model output, or personal
  microphone content.
- The supported patch entry point is `apply-airi-patches.ps1`; restoration is
  through `restore-airi-original.ps1`. The individual `patch-airi-*.ps1`
  files are orchestrator-only implementation steps.

## Delivered contracts

The current patch set covers:

1. Opaque parent correlation for local server-channel chat events. Correlation
   is envelope metadata only and is not copied into chat text, context
   snapshots, journal records, or persisted messages.
2. A content-free supersession cancellation event. A sender waiting on an
   exact parent correlation can settle as cancelled without accepting another
   same-text request's completion.
3. A content-free playback-start event emitted only after the audio source
   successfully executes `source.start(0)`. It is correlated by the same
   parent metadata and is one-shot/fail-closed for stale, duplicate, or remote
   mirrored events.
4. Sender options that preserve the existing default `--wait-complete`
   behavior and add opt-in `--wait-playback-start`. Playback-start is a bounded
   start proof, not proof of natural playback end.
5. Byte-addressed patch artifacts with a checked manifest. Patch files are
   explicitly non-text in `.gitattributes` so checkout normalization cannot
   change their documented size or SHA-256.
6. Offline PowerShell contracts for patch manifest integrity, orchestrator-only
   child entry points, and the combined checkpoint command. The GitHub
   workflow runs those checks on Windows with immutable SHA pins for the
   Node-24-based official actions; the job itself uses Node.js 22 for the
   sender contract.

## Authoritative files

- `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` — current-vs-historical
  document map and safety boundary.
- `airi_docs/AIRI-SERVER-CHANNEL-PLAYBACK-CHECKPOINT-2026-08-10.md` — detailed
  correlation, cancellation, playback-start, and sender contract.
- `airi_docs/patches/AIRI-v0.11.3-round-cancel-source-replacement.md` — pinned
  base, combined patch manifest, sizes, hashes, and scope.
- `airi_docs/patches/AIRI-v0.11.3-context-correlation-sanitizer.patch` — the
  separate generic `context:update` sanitizer patch applied after the combined
  patch.
- `test-current-checkpoint.ps1` — one offline entry point for the manifest,
  entrypoint, and sender checks.
- `.github/workflows/remediation-checkpoint.yml` — offline Windows CI gate.

Do not use older handoff/checkpoint pages as current branch status. They may
contain historical archive hashes, runtime observations, or old test totals.

## Verification at handoff

The following checks are the minimum reproducible checkpoint and must remain
offline/model-free:

```powershell
git status --short
git diff-tree --check --no-commit-id -r HEAD -- . ':(exclude)airi_docs/patches/*.patch'
.\test-current-checkpoint.ps1
```

## Handoff finalization

This document is the boundary for the next review session. The working tree
must be clean and the branch must be pushed before a reviewer begins. The
next reviewer should treat the current commit, not an uncommitted local
checkout or an installed AIRI archive, as the source of truth. Review findings
should be reported first; edits should be limited to the smallest justified
scope, followed by the offline checkpoint and a new pushed commit.

For the next Claude session, paste the request in the final section below
verbatim. It intentionally asks for an audit before any mutation and forbids
network/model/service or real-microphone actions.

The sender contract currently passes 26 Node tests. The combined checkpoint
also verifies all three documented patch artifact sizes and hashes and the
orchestrator-only child-script contract, and invokes the applicability verifier
in its inert/default-off mode. The pinned v0.11.3 patch applies
cleanly in the dedicated pristine verification checkout; the current branch
does not require that checkout to be present. The GitHub job intentionally
does not clone or apply a v0.11.3 fixture: patch applicability is a separately
recorded pristine-checkout result, while CI stays offline and artifact-free.
That explicit applicability command was re-run against the local checkout at
`dbf8124` after the latest sender changes; both patch apply/reverse checks
passed and the installed AIRI archive was not accessed or modified.
The workflow's committed-whitespace check inspects the full push/PR range with
`git diff --check` (falling back to `git diff-tree --check` for other event
types) and excludes the byte-addressed patch files; those files are checked by
exact manifest hashes instead.

Patch applicability can be rechecked explicitly against a local checkout of
the pinned commit (the command creates and removes only a temporary detached
worktree through Git):

```powershell
.\test-patch-applicability.ps1 -BaseCheckout 'D:\src\airi-v0.11.3'
```

The verifier is inert and exits successfully when `-BaseCheckout` is omitted;
CI remains inert with respect to patch applicability and never clones a base
checkout, touches the AIRI installation, or starts services. If Git refuses to
remove its temporary worktree, the verifier leaves it untouched and reports a
warning rather than performing a path-based recursive delete.

## Latest installer-script audit

The apply/restore PowerShell boundary was re-audited after this handoff was
created. No HIGH or MED defect was found. Both supported entry points use the
same named mutex, reject installation/resources/archive reparse points, verify
the pinned pristine SHA-256, stage and re-hash bytes before publication, and
clean temporary files. All six active child steps reject direct invocation and
the orchestrator stops after the first child failure before final verification.

These are deliberate remaining boundaries, not hidden guarantees: the
filesystem checks cannot remove every hostile same-privilege TOCTOU window;
`-InternalOrchestrator` is a PowerShell calling convention rather than an
authentication boundary; and a failed partial apply is reported for explicit
manual restore rather than automatically rolled back.

## Deliberate boundaries

- Do not create or enable a governed topic board from this handoff.
- Do not send real microphone text, call a model/service, or expose raw IDs,
  paths, session identifiers, or dialogue in an audit report.
- Do not claim that playback-start proves natural playback completion.
- Do not add a `--wait-playback-end` mode without a dedicated final-round
  playback protocol and interruption semantics.
- If a future reviewer finds a defect, make the smallest scoped change, rerun
  the offline checkpoint, update this handoff, commit, and push before moving
  to the next branch of work.

## Copy/paste request for the next Claude session

```text
You are reviewing the AIRI remediation branch after its latest handoff.

Read README.md, airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md,
airi_docs/AIRI-FINAL-HANDOFF-2026-08-10.md, and
airi_docs/AIRI-SERVER-CHANNEL-PLAYBACK-CHECKPOINT-2026-08-10.md first.

Audit only the current source patch and sender/bridge protocol. Verify:
1) playback-start is emitted only after successful source.start(0);
2) parent correlation is exact and does not leak into text, context snapshots,
   journal, or persisted messages;
3) completion-first/playback-first ordering, duplicates, stale rounds, remote
   mirrors, and supersession cancellation fail closed;
4) default --wait-complete remains behavior-compatible; and
5) the patch applies cleanly to the pinned v0.11.3 base.

Run offline checks first: git status/log, git diff-tree --check --no-commit-id -r HEAD,
.\test-current-checkpoint.ps1, and node --test test-send-airi-local-text.mjs.
Do not create a governed topic board, send real microphone text, call models or
services, or expose raw IDs, paths, or dialogue. Report only findings, test
counts, and repository-relative file/line references. If a fix is needed,
describe the smallest scoped change before editing.
```
