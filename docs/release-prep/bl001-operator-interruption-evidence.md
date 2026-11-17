# BL-001 — Operator Ctrl+C evidence (non-destructive)

This is an **observability-only** change to the canonical `TCFMain.py`
pipeline. During a normal pipeline run, if the root Python process receives
`KeyboardInterrupt` (typically Ctrl+C), the root records **one best-effort**
JSON Lines event at:

```text
<repository>/logs/tcf_operator_interruptions.jsonl
```

The folder is Git-ignored. The record contains only a UTC timestamp, stage
name, process ID, a fixed event label and explicit `workpool_modified=false`
and `cleanup_attempted=false`. It does **not** include database contents,
dataset paths, usernames, command-line arguments, work IDs, or model weights.

Recognized stages: DataConverter, RunClassfier, CombineTestResult,
TestResultVis, RawAndPredictionMerger and BackupAndClean. Unknown stages
are recorded only as `unknown`.

**No cleanup / no automatic resume:** the handler re-raises the original
`KeyboardInterrupt` after an attempted log append. It does not swallow a
signal to keep a job running; it does not delete, rename, quarantine, unlock,
restart or alter WorkPool or SQLite. If local logs cannot be safely opened
(for example, the logs path is a symlink or is unwritable), the original
interrupt continues with only a console notification.

**Important interpretation boundary:** a `_is_running_` directory is a
historical pipeline state label. A nonzero exit status from a child command,
including exit code 130 or the Windows Ctrl+C exit code, **is not** classified
as a confirmed operator Ctrl+C event. The root may not receive a Python
KeyboardInterrupt when the child absorbs the console signal or Windows closes
the process abruptly. Such cases are **unknown cause**, not confirmed user
interrupts. Existing 24 running-named workspace directories cannot be
retroactively reclassified based on this new log.

To view this local evidence after a future Ctrl+C in PowerShell:

```powershell
Get-Content .\\logs\\tcf_operator_interruptions.jsonl -Tail 10
```

Do not enable automatic deletion of old WorkPool workspaces based solely on
their names, stage, timestamps or these interruption records. Formal
production WorkPool readiness and detached-copy SQLite checks remain separate
acceptance gates.
