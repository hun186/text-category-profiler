"""Best-effort, private operator Ctrl+C evidence for the root TCF pipeline.

On POSIX, only file-descriptor-relative no-follow writes are permitted.
Windows reports the stage on the console, but skips file persistence until a
reviewed, directory-handle-relative Win32 writer exists. Never touch WorkPool,
scan dataset contents, rename folders, or infer a nonzero child exit as Ctrl+C.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat


_ALLOWED_STAGES = frozenset((
    "DataConverter", "RunClassfier", "CombineTestResult",
    "TestResultVis", "RawAndPredictionMerger", "BackupAndClean",
))
_LOG_NAME = "tcf_operator_interruptions.jsonl"


def record_operator_interrupt(stage: str, *,
                              project_root: Path | None = None,
                              when: datetime | None = None) -> Path | None:
    """Append one minimal event on KeyboardInterrupt, returning log path if saved.

    This method is intentionally best-effort: failure to record must NEVER
    change the interrupted pipeline's exception or cleanup semantics.
    The log location is the PROJECT's ignored logs directory, NOT WorkPool.
    """
    root = (project_root if project_root is not None
            else Path(__file__).resolve().parents[2])
    root = Path(root)
    destination = root / "logs" / _LOG_NAME
    try:
        # Windows' os.open() cannot use a directory fd, and an ordinary
        # pathname append is vulnerable to junction or parent replacement.
        # Do not write at all on Windows until there is a reviewed,
        # handle-relative implementation; the caller prints the stage.
        if os.name == "nt":
            return None
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            return None
        if root.is_symlink() or not root.is_dir():
            return None
        moment = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        event = {
            "schema": "tcf_operator_interrupt_v1",
            "time_utc": moment.isoformat(timespec="seconds"),
            "event": "operator_keyboard_interrupt",
            "stage": stage if stage in _ALLOWED_STAGES else "unknown",
            "pid": os.getpid(),
            "workpool_modified": False,
            "cleanup_attempted": False,
        }
        line = (json.dumps(event, ensure_ascii=True, sort_keys=True) + "\\n").encode("utf-8")
        dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        previous = root.lstat()
        root_fd = os.open(root, dir_flags)
        try:
            mounted = os.fstat(root_fd)
            if (mounted.st_dev, mounted.st_ino) != (
                    previous.st_dev, previous.st_ino):
                return None
            try:
                os.mkdir("logs", mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            logs_fd = os.open("logs", dir_flags, dir_fd=root_fd)
            try:
                log_fd = os.open(
                    _LOG_NAME, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
                    0o600, dir_fd=logs_fd,
                )
                try:
                    info = os.fstat(log_fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        return None
                    if os.write(log_fd, line) != len(line):
                        return None
                finally:
                    os.close(log_fd)
            finally:
                os.close(logs_fd)
        finally:
            os.close(root_fd)
        return destination
    except (OSError, ValueError, TypeError, OverflowError):
        return None
