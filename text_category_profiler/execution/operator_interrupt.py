"""Best-effort, private operator Ctrl+C evidence for the root TCF pipeline.

Never touch WorkPool, scan dataset contents, rename folders, or infer that a
nonzero subprocess exit code was an operator keyboard interruption.
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
    logs = root / "logs"
    destination = logs / _LOG_NAME
    try:
        # Never follow a custom logs symlink/junction into WorkPool/elsewhere.
        if root.is_symlink() or logs.is_symlink() or destination.is_symlink():
            return None
        if not root.is_dir():
            return None
        logs.mkdir(exist_ok=True)
        if logs.is_symlink() or not logs.is_dir():
            return None
        if destination.exists():
            info = destination.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
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
        line = (json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(destination, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                return None
            if os.write(fd, line) != len(line):
                return None
        finally:
            os.close(fd)
        return destination
    except (OSError, ValueError, TypeError, OverflowError):
        return None
