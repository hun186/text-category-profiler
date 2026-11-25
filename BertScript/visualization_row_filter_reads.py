"""Stage 4 classification and keyword match reads, with no GUI dependencies."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3


def _populate_labels(connection, labels):
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("CREATE TEMP TABLE filter_labels (value TEXT PRIMARY KEY)")
    connection.executemany(
        "INSERT OR IGNORE INTO temp.filter_labels VALUES (?)",
        ((str(label),) for label in labels),
    )


def read_files_for_labels(database, labels):
    """Return distinct source file values for the selected classification set."""
    path = Path(database)
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        _populate_labels(connection, labels)
        rows = connection.execute(
            "SELECT DISTINCT File FROM main.sampleSrc "
            "WHERE pred_Type IN (SELECT value FROM temp.filter_labels)"
        ).fetchall()
    return [row[0] for row in rows]


def read_matching_block_counts(database, files, labels, keywords):
    """Return total and keyword-matched piece counts for selected files/labels.

    Each keyword is a separate Python regular expression, as for the legacy
    single-keyword REGEXP. Match any pattern, count each source row once.
    Missing text is not a keyword match. Invalid regex raises re.error rather
    than silently returning misleading counts. Without keywords return no
    keyword counts; the caller retains its legacy empty-string column.
    """
    patterns = tuple(re.compile(str(keyword)) for keyword in keywords)
    path = Path(database)
    if not path.is_file():
        return [], []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        _populate_labels(connection, labels)
        connection.execute("CREATE TEMP TABLE filter_files (value TEXT PRIMARY KEY)")
        connection.executemany(
            "INSERT OR IGNORE INTO temp.filter_files VALUES (?)",
            ((str(file),) for file in files),
        )
        predicates = (
            " FROM main.sampleSrc "
            "WHERE pred_Type IN (SELECT value FROM temp.filter_labels) "
            "AND File IN (SELECT value FROM temp.filter_files)"
        )
        if not patterns:
            totals = connection.execute(
                "SELECT File, COUNT(*)" + predicates + " GROUP BY File"
            ).fetchall()
            return totals, []

        def matches_any(text):
            if text is None:
                return 0
            return int(any(pattern.search(text) is not None for pattern in patterns))

        connection.create_function("stage4_matches_any", 1, matches_any)
        # One statement provides a consistent read snapshot for both counts.
        counts = connection.execute(
            "SELECT File, COUNT(*), SUM(stage4_matches_any(text))"
            + predicates + " GROUP BY File"
        ).fetchall()
    totals = [(file, total) for file, total, matched in counts]
    keyword_counts = [(file, matched) for file, total, matched in counts if matched]
    return totals, keyword_counts
