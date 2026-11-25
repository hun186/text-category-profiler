"""Bound, read-only SQLite access for Stage 4 per-file sample queries."""
from contextlib import closing
from pathlib import Path
import sqlite3


def read_sample_rows(database, query, parameters):
    """Execute an internal SELECT with bound values; preserve legacy ListForm.

    The caller supplies trusted SQL and column names. A missing file returns
    an empty list, as for legacy reads. Read-only URI prevents accidental
    database creation and writes. Do not log bound data.
    """
    path = Path(database)
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        rows = connection.execute(query, parameters).fetchall()
    if rows and len(rows[0]) == 1:
        return [row[0] for row in rows]
    return rows


def _read_for_files(database, files, *, labels_only):
    """Run one set-based query with a bound, connection-local filename set.

    A temporary in-memory relation avoids the SQLite host-variable limit.
    The source database is opened read-only; only the temporary schema is
    populated. SQLite handles IN collation and DISTINCT, including duplicate
    input names, without deduplicating real prediction rows.
    """
    path = Path(database)
    if not path.is_file():
        return []
    # Preserve the former string interpolation's conversion of filename values.
    names = iter(files)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute(
            "CREATE TEMP TABLE stage4_selected_files (name TEXT PRIMARY KEY)"
        )
        connection.executemany(
            "INSERT OR IGNORE INTO temp.stage4_selected_files (name) VALUES (?)",
            ((str(name),) for name in names),
        )
        columns = "DISTINCT pred_Type" if labels_only else "File, pred_Type"
        rows = connection.execute(
            f"SELECT {columns} FROM main.sampleSrc "
            "WHERE File IN (SELECT name FROM temp.stage4_selected_files)"
        ).fetchall()
    if labels_only:
        return [row[0] for row in rows]
    return rows


def read_predictions_for_files(database, files):
    """Return all matching prediction rows, preserving real duplicates."""
    return _read_for_files(database, files, labels_only=False)


def read_labels_for_files(database, files):
    """Return distinct labels for the selected file set."""
    return _read_for_files(database, files, labels_only=True)
