"""Read the Stage 4 score window without importing GUI or pandas."""
from contextlib import closing
import math
from numbers import Integral, Real
from pathlib import Path
import sqlite3


def _bound_number(value):
    # Dash emits numeric values; also accept numpy scalar integers/reals.
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("Score range bounds must be finite numbers")
    if isinstance(value, Integral):
        return int(value)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Score range bounds must be finite numbers")
    return result


def read_score_range(database, lower, upper, *, read_sql_query):
    """Return the Stage 4 sampleSrc DataFrame with inclusive score bounds.

    Use the caller's pandas reader to preserve column/dtype handling, even
    for an empty result. Do not open writable or missing databases. Do not
    silently swap reversed bounds (SQLite BETWEEN returns no matching rows).
    """
    bounds = (_bound_number(lower), _bound_number(upper))
    uri = Path(database).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        return read_sql_query(
            "SELECT * FROM sampleSrc WHERE InfoScoreSum BETWEEN ? AND ?",
            conn, params=bounds,
        )
