---
name: project-pytest-not-installed
description: pytest is NOT on the default python (3.14), but the repo's pinned venv has it; use the pinned interpreters from the current handoff instead of falling back to unittest (corrected 2026-08-26).
metadata:
  type: project
---

`python -m pytest` fails with `No module named pytest` on the default interpreter
(`C:\Users\kkp74\AppData\Local\Python\pythoncore-3.14-64\python.exe`, also behind the
WindowsApps `python.exe`/`python3.exe` shims), and `py --list` only shows 3.14. That does NOT mean
pytest is unavailable: the repository's pinned pytest interpreter is
`D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe` (Python 3.12.13, pytest 9.1.1),
and the proxy/runtime unittest suites are run with the WindowsApps 3.14 python because it has
`httpx`. Both paths are recorded in the current handoff's "인터프리터" section
(e.g. `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-25-M4.md`).

**Why:** on 2026-08-26 an implementer concluded "pytest is not installed anywhere" and reported
unittest counts only; the supervisor then re-ran the same suites with the pinned venv (pytest
green) — the wrong conclusion cost a verification round.

**How to apply:** before declaring pytest unavailable, check the current handoff for the pinned
interpreter paths and run `D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe -m pytest -q <files>`
with `PYTHONUTF8=1`. Use `python -m unittest` only for the proxy/runtime suites the handoff assigns
to the WindowsApps 3.14 interpreter. Never pip install into any interpreter. See
[[feedback-report-blocked-runs-do-not-retry]].
