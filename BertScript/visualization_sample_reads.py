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
