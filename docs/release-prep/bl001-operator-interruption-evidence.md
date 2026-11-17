# BL-001 — Operator Ctrl+C evidence (non-destructive)

This is an **observability-only** change to the canonical `TCFMain.py`
pipeline. During a normal pipeline run, if the root Python process receives
`KeyboardInterrupt` (typically Ctrl+C), the root reports the
interrupted stage on the console and re-raises the original exception.

On **Linux/POSIX** with `O_NOFOLLOW` and `dir_fd` support, the root
additionally attempts to append one JSON Lines event at:

```text
<repository>/logs/tcf_operator_interruptions.jsonl
```

On **Windows**, the program intentionally **does not write a log file**
for this feature. Standard Python pathname opens cannot guarantee that a
directory is not replaced by a junction between checking and writing.
Instead, Ctrl+C is reported **only on the console** until a separate,
reviewed handle-relative Win32 writer is available. This avoids adding a
new WorkPool write risk for a diagnostic-only feature.

The POSIX log folder is Git-ignored. The record contains only a UTC timestamp, stage
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
interrupt continues with only a console notification. Windows uses this
console-only path by design (not because of a failed filesystem write).

**Important interpretation boundary:** a `_is_running_` directory is a
historical pipeline state label. A nonzero exit status from a child command,
including exit code 130 or the Windows Ctrl+C exit code, **is not** classified
as a confirmed operator Ctrl+C event. The root may not receive a Python
KeyboardInterrupt when the child absorbs the console signal or Windows closes
the process abruptly. Such cases are **unknown cause**, not confirmed user
interrupts. Existing 24 running-named workspace directories cannot be
retroactively reclassified based on this new log.

To view this local evidence after a future Ctrl+C on Linux/POSIX:

```sh
tail -n 10 ./logs/tcf_operator_interruptions.jsonl
```

Do not enable automatic deletion of old WorkPool workspaces based solely on
their names, stage, timestamps or these interruption records. Formal
production WorkPool readiness and detached-copy SQLite checks remain separate
acceptance gates.
