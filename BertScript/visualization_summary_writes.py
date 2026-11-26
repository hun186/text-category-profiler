"""Bound Stage 4 summary updates with an explicit transaction boundary."""
from contextlib import closing
from pathlib import Path
import sqlite3


def write_summary_updates(database, updates):
    """Update existing sampleSrc rows by exact File, atomically per batch.

    Each input is (summary_text, filename). Preserve the caller's order and
    SQLite column collation; unmatched files remain no-ops. Never create a
    missing database. An empty batch is a no-op. Exceptions propagate after
    rollback, and the connection is always closed.
    """
    updates = tuple(updates)
    if not updates:
        return 0
    path = Path(database)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True)) as connection:
        with connection:
            cursor = connection.executemany(
                "UPDATE sampleSrc SET Summary = ? WHERE File = ?", updates
            )
            count = cursor.rowcount
    return count
