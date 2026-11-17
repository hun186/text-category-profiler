"""Atomic canonical DataFrame SQLite REPLACE, preserving the legacy schema contract.

pandas.to_sql(..., if_exists='replace') performs its own sqlite3 COMMIT.
Therefore materialize the *candidate* with pandas first; only swap the target
table, copy the rows, and recreate the existing pandas/IndexCols indexes under
one BEGIN IMMEDIATE. Avoid auto-delete of unowned or interrupted candidates.
Does not affect append/fail modes or the distinct Stage-local writer.
"""
from __future__ import annotations

import uuid


def _quote(name):
    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError("Invalid SQLite identifier")
    return '"' + name.replace('"', '""') + '"'


def _index_entries(cnx, table):
    result = []
    for entry in cnx.execute("PRAGMA index_list(" + _quote(table) + ")"):
        name, unique, origin, partial = entry[1:5]
        if unique or origin != "c" or partial:
            raise ValueError("Unsupported existing or staged SQLite index: " + name)
        keys = [row for row in cnx.execute(
            "PRAGMA index_xinfo(" + _quote(name) + ")"
        ) if row[5] == 1]
        cols = {row[1] for row in cnx.execute(
            "PRAGMA table_info(" + _quote(table) + ")"
        )}
        if not keys or any(
            key[1] < 0 or key[2] not in cols or key[3] != 0
            or key[4] != "BINARY" for key in keys
        ):
            raise ValueError("Unsupported SQLite index keys: " + name)
        result.append((name, tuple(key[2] for key in keys)))
    return result


def _replacement_indexes(cnx, candidate, table, requested):
    indexes = []
    prefix = "ix_" + candidate + "_"
    for name, keys in _index_entries(cnx, candidate):
        if not name.startswith(prefix) or name[len(prefix):] != "_".join(keys):
            raise ValueError("Unsupported pandas index: " + name)
        indexes.append(("ix_" + table + "_" + name[len(prefix):], keys))
    column_names = {r[1] for r in cnx.execute(
        "PRAGMA table_info(" + _quote(candidate) + ")"
    )}
    for col in requested:
        if col not in column_names:
            raise ValueError("Requested index column absent: " + str(col))
        indexes.append((col + "_Index", (col,)))
    if len({name.casefold() for name, _ in indexes}) != len(indexes):
        raise ValueError("Conflicting target index names")
    return indexes


def _guard_existing_table_contract(cnx, table):
    """Never destroy table-level constraints that pandas staging cannot copy.

    A canonical pandas-created table has ordinary nullable columns without
    defaults, primary keys, outbound FKs, generated/hidden columns, CHECK or
    collation clauses. The candidate schema replaces the original schema, so
    unsupported target constraints must be rejected before DROP, even when
    every existing index looks like a pandas-generated index.
    """
    import re

    entry = cnx.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name=? COLLATE NOCASE",
        (table,),
    ).fetchone()
    if entry is None:
        return
    ddl = entry[0] or ""
    if not re.match(r"^\s*CREATE\s+TABLE\b", ddl, re.IGNORECASE):
        raise ValueError("Unsafe existing table kind")
    # SQLite has no PRAGMA for CHECK clauses or column COLLATE clauses. This
    # conservative rejection can refuse unusual identifiers, but cannot
    # silently discard the old constraints.
    if re.search(r"\b(CHECK|COLLATE|GENERATED|STRICT)\b|\bAS\s*\(",
                 ddl, re.IGNORECASE):
        raise ValueError("Unsafe existing table DDL constraints")
    for col in cnx.execute("PRAGMA table_xinfo(" + _quote(table) + ")"):
        # table_xinfo: cid, name, type, notnull, default, pk, hidden
        if col[3] or col[4] is not None or col[5] or col[6]:
            raise ValueError("Unsafe existing table column constraints")
    if list(cnx.execute("PRAGMA foreign_key_list(" + _quote(table) + ")")):
        raise ValueError("Unsafe existing outbound foreign key")


def _view_schema_signatures(cnx):
    """Read all view column interfaces without loading any data rows.

    SQLite permits DROP+CREATE of a referenced table, but a dependent view
    may become invalid or silently change its SELECT * output. Inspecting the
    views before and after the transaction's new table DDL detects both cases.
    """
    names = [
        r[0] for r in cnx.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
        )
    ]
    signatures = {}
    for name in names:
        columns = tuple(cnx.execute("PRAGMA table_info(" + _quote(name) + ")"))
        if not columns:
            raise ValueError("Unreadable existing SQLite view: " + name)
        signatures[name] = columns
    return signatures


def _trigger_mentions_target(sql, table):
    """Conservatively reject external trigger SQL referencing the target.

    SQLite does not expose a trigger dependency graph through PRAGMA. An
    identifier-token match can refuse an innocent quoted literal, but cannot
    silently invalidate a trigger attached to another table.
    """
    import re

    normalized = (sql or "").replace('""', '"')
    return re.search(
        r"(?<![\\w])" + re.escape(table) + r"(?![\\w])",
        normalized, re.IGNORECASE,
    ) is not None


def _guard_replacement(cnx, table):
    """Fail closed before DROP would erase a trigger/FK or custom index.

    Existing *canonical* pandas/IndexCols indexes are validated against their
    own names and keys, not the new frame's index labels. A legal replacement
    may change pandas index names or requested IndexCols.
    """
    objects = list(cnx.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE type IN ('table', 'trigger')"
    ))
    for kind, name, owner, sql in objects:
        if kind == "trigger":
            if owner.casefold() == table.casefold():
                raise ValueError("Unsafe target trigger: " + name)
            if _trigger_mentions_target(sql, table):
                raise ValueError("Unsafe dependent trigger: " + name)
            continue
        if kind != "table" or name.casefold() == table.casefold():
            continue
        for foreign_key in list(cnx.execute(
            "PRAGMA foreign_key_list(" + _quote(name) + ")"
        )):
            if foreign_key[2].casefold() == table.casefold():
                raise ValueError("Unsafe inbound foreign key: " + name)

    _guard_existing_table_contract(cnx, table)
    pandas_prefix = "ix_" + table + "_"
    for name, keys in _index_entries(cnx, table):
        pandas_key = (name.startswith(pandas_prefix)
                      and name[len(pandas_prefix):] == "_".join(keys))
        canonical_column_key = (len(keys) == 1
                                and name == keys[0] + "_Index")
        if not (pandas_key or canonical_column_key):
            raise ValueError("Unsafe existing index: " + name)


def replace_canonical_table(cnx, frame, *, table, dtype, index_label, index_cols):
    """Replace target table without exposing an index-less committed target.

    Caller owns and closes `cnx`; any side effects are limited to its DB.
    Failed staging may leave an unknown-owner candidate for manual triage.
    """
    table_name = _quote(table)
    candidate = "__bl001_canonical_" + uuid.uuid4().hex
    candidate_name = _quote(candidate)
    owned = False
    started = False
    try:
        # Pandas commits automatically. This touches only a fresh candidate.
        frame.to_sql(name=candidate, con=cnx, if_exists="fail",
                     dtype=dtype, index_label=index_label)
        owned = True
        schema = cnx.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (candidate,),
        ).fetchone()
        prefix = "CREATE TABLE " + candidate_name
        if not schema or not schema[0].startswith(prefix) or (
            schema[0][len(prefix):len(prefix) + 1] not in (" ", "(")
        ):
            raise ValueError("Unexpected candidate table DDL")
        new_ddl = "CREATE TABLE " + table_name + schema[0][len(prefix):]
        indexes = _replacement_indexes(cnx, candidate, table, index_cols)

        cnx.execute("BEGIN IMMEDIATE")
        started = True
        _guard_replacement(cnx, table)
        view_signatures_before = _view_schema_signatures(cnx)
        cnx.execute("DROP TABLE IF EXISTS " + table_name)
        cnx.execute(new_ddl)
        cnx.execute(
            "INSERT INTO " + table_name + " SELECT * FROM " + candidate_name
        )
        for name, keys in indexes:
            cnx.execute(
                "CREATE INDEX " + _quote(name) + " ON " + table_name + " ("
                + ", ".join(_quote(col) for col in keys) + ")"
            )
        if _view_schema_signatures(cnx) != view_signatures_before:
            raise ValueError("Unsafe changed SQLite view interface")
        cnx.execute("DROP TABLE " + candidate_name)
        cnx.commit()
        started = False
    except BaseException:
        if started:
            try:
                cnx.rollback()
            except Exception:
                pass
        if owned:
            try:
                cnx.execute("DROP TABLE IF EXISTS " + candidate_name)
                cnx.commit()
            except Exception:
                pass
        raise
