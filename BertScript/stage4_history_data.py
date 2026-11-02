"""Bounded, read-only inspection of persisted Stage 4 SQLite results.

This is NOT the original analytics pipeline and never advances WorkPool stages.
All SQLite connections are immutable/read-only; WAL or rollback journal presence
fails closed because ignoring live uncheckpointed writes would be misleading.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

WORKSPACE_RE = re.compile(
    r"^dataset_\d{12,16}_.+_pt\d+_(rdy_for_Spike|is_running_TestResultVis)$"
)
DATABASES = ("DFPreambleCols_df_ALL.sql3", "test_results_verification.sql3")
PAGE_SIZE = 50
MAX_COLUMNS = 24
MAX_TEXT = 600


class HistoryPreviewError(ValueError):
    """Unsafe, absent or incomplete read-only history input."""


@dataclass(frozen=True)
class Workspace:
    name: str
    status: str
    available: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def complete(self):
        return not self.missing and self.status == "rdy_for_Spike"


def _root(workpool):
    root = Path(workpool).resolve(strict=True)
    if not root.is_dir():
        raise HistoryPreviewError("WorkPool root is not a directory")
    return root


def _workspace_path(root, name):
    if not isinstance(name, str) or not WORKSPACE_RE.fullmatch(name):
        raise HistoryPreviewError("Unrecognized Stage 4 workspace name")
    path = root / name
    if path.is_symlink() or not path.is_dir():
        raise HistoryPreviewError("Workspace does not exist or is a link")
    if path.resolve() != path or not path.is_relative_to(root):
        raise HistoryPreviewError("Workspace must stay inside the selected WorkPool")
    return path


def list_workspaces(workpool):
    """List known history candidates without importing ML, Jaal or touching files."""
    root = _root(workpool)
    found = []
    for item in root.iterdir():
        if not WORKSPACE_RE.fullmatch(item.name) or item.is_symlink() or not item.is_dir():
            continue
        available = tuple(
            name for name in DATABASES
            if (item / name).is_file() and not (item / name).is_symlink()
        )
        missing = tuple(name for name in DATABASES if name not in available)
        found.append(Workspace(
            item.name, WORKSPACE_RE.fullmatch(item.name).group(1),
            available, missing
        ))
    return sorted(found, key=lambda item: item.name, reverse=True)[:200]


def select_workspace(workpool, name):
    """Only accept a name obtained from the selected WorkPool root."""
    root = _root(workpool)
    _workspace_path(root, name)
    for entry in list_workspaces(root):
        if entry.name == name:
            return entry
    raise HistoryPreviewError("Workspace not available")


def database_path(workpool, workspace, filename, *, confirm_running=False):
    """Fail closed for incomplete, unacknowledged or live SQLite history."""
    if filename not in DATABASES:
        raise HistoryPreviewError("Unsupported history database")
    info = select_workspace(workpool, workspace)
    if info.missing:
        raise HistoryPreviewError("Incomplete results: missing " + ", ".join(info.missing))
    if info.status == "is_running_TestResultVis" and not confirm_running:
        raise HistoryPreviewError(
            "Running/interrupted dataset: confirm no other process is writing "
            "before opening its unverified results"
        )
    path = _workspace_path(_root(workpool), workspace) / filename
    if path.is_symlink() or not path.is_file():
        raise HistoryPreviewError("Result database is absent or a symbolic link")
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(path) + suffix).exists():
            raise HistoryPreviewError(
                "SQLite has a journal or WAL sidecar; refusing to ignore "
                "possibly uncheckpointed writes"
            )
    if path.stat().st_size < 100:
        raise HistoryPreviewError("SQLite database is empty/truncated")
    return path


def _connect(path):
    # URI immutable=1 tells SQLite never to write -journal/-shm, even on
    # Windows; only use after checking for WAL/journal sidecars.
    uri = "file:" + quote(path.resolve().as_posix(), safe="/:") + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True, timeout=1)
    connection.execute("PRAGMA query_only=ON")
    return connection


def list_tables(workpool, workspace, database, *, confirm_running=False):
    path = database_path(
        workpool, workspace, database, confirm_running=confirm_running
    )
    try:
        with _connect(path) as db:
            return tuple(row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ))
    except sqlite3.DatabaseError as exc:
        raise HistoryPreviewError("Invalid or unreadable SQLite result") from exc


def _quoted(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def read_page(workpool, workspace, database, table, page=1, *,
              confirm_running=False):
    """Whitelisted identifiers, parameterized bounded pagination, no SQL writes."""
    path = database_path(
        workpool, workspace, database, confirm_running=confirm_running
    )
    try:
        page = int(page)
    except (TypeError, ValueError) as exc:
        raise HistoryPreviewError("Page must be a positive integer") from exc
    if not 1 <= page <= 20000:
        raise HistoryPreviewError("Page must be in 1..20000")
    if not isinstance(table, str) or table not in list_tables(
            workpool, workspace, database, confirm_running=confirm_running):
        raise HistoryPreviewError("Unknown SQLite result table")
    try:
        with _connect(path) as db:
            names = [x[1] for x in db.execute(
                "PRAGMA table_info(" + _quoted(table) + ")"
            ).fetchall()]
            if not names:
                raise HistoryPreviewError("Table has no visible columns")
            cols = names[:MAX_COLUMNS]
            # SQLite substr bounds the returned value *before* loading it
            # into Dash memory. A bounded page prevents eager full-dataset loads.
            select = ", ".join(
                "substr(CAST(" + _quoted(name) + " AS TEXT), 1, ?) AS "
                + _quoted(name) for name in cols
            )
            query = ("SELECT " + select + " FROM " + _quoted(table)
                     + " LIMIT ? OFFSET ?")
            args = [MAX_TEXT] * len(cols) + [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE]
            result = db.execute(query, args).fetchall()
            has_next = len(result) > PAGE_SIZE
            rows = [
                {name: (value if value is not None else "") for name, value in zip(cols, row)}
                for row in result[:PAGE_SIZE]
            ]
            return {"columns": cols, "rows": rows, "page": page,
                    "has_next": has_next, "truncated_columns": len(names) > MAX_COLUMNS}
    except sqlite3.DatabaseError as exc:
        raise HistoryPreviewError("Could not read SQLite table") from exc
