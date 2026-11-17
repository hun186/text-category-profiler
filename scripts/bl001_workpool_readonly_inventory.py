"""Bounded, metadata-only WorkPool inventory with NO database or file-content reads.

This utility is intentionally separate from detached-copy SQLite checks. It
does not open DBs, read dataset rows, acquire work, create directories, write
logs, checkpoint WAL, stop workers, or certify production deployment.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat


_SIDECARS = ("-wal", "-shm", "-journal")
_DATABASE_EXTENSIONS = (".sql3", ".sqlite", ".sqlite3", ".db")
_REPARSE_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _reparse(info: os.stat_result) -> bool:
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0) & _REPARSE_FLAG))


def _root_guard(path: Path) -> str | None:
    """Check all lexical ancestor boundaries without following aliases."""
    if not path.name.casefold().endswith("workpool"):
        return "root_name_not_workpool"
    try:
        for segment in (*reversed(path.parents), path):
            info = segment.lstat()
            if _reparse(info):
                return "path_reparse_point_not_allowed"
        if not stat.S_ISDIR(path.lstat().st_mode):
            return "root_not_directory"
    except (OSError, ValueError):
        return "root_unavailable"
    return None


def inventory_workpool_metadata(workpool: str | Path, *,
                                max_entries: int = 10000,
                                max_depth: int = 3) -> dict:
    """Observe ONLY bounded directory-entry metadata, never file contents.

    Directory timestamps are checked to detect some concurrent changes, but
    an observed stable snapshot is NOT a quiescence, DB integrity, or
    production acceptance assertion. No path names of individual jobs/files
    are included in the returned report.
    """
    if not 1 <= max_entries <= 100000:
        raise ValueError("max_entries must be 1..100000")
    if not 1 <= max_depth <= 4:
        raise ValueError("max_depth must be 1..4")
    root = Path(workpool).absolute()
    report = {
        "status": "UNVERIFIABLE",
        "scope": "live_or_offline_workpool_metadata_only",
        "workpool_name": root.name,
        "max_entries": max_entries,
        "max_depth": max_depth,
        "entries_observed": 0,
        "directories_observed": 0,
        "files_observed": 0,
        "workspace_running": 0,
        "workspace_ready": 0,
        "workspace_other": 0,
        "sqlite_files_observed": 0,
        "sqlite_file_bytes_observed": 0,
        "sqlite_sidecars_observed": 0,
        "reparse_entries_observed": 0,
        "directories_not_descended": 0,
        "issues": [],
        "file_contents_read": False,
        "sqlite_connections_opened": False,
        "production_workpool_verified": False,
        "deployment_authorized": False,
        "candidate_deletion_authorized": False,
        "limits": (
            "Metadata-only bounded observation. It does not establish "
            "quiescence, database integrity, writer ownership, durability, "
            "backup recoverability, or production deployment readiness."
        ),
    }
    reason = _root_guard(root)
    if reason:
        report["issues"].append(reason)
        return report

    try:
        before = _identity(root.lstat())
        stack = [(root, 0)]
        while stack:
            directory, depth = stack.pop()
            start = _identity(directory.lstat())
            report["directories_observed"] += 1
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    if report["entries_observed"] >= max_entries:
                        report["issues"].append("entry_budget_exhausted")
                        return report
                    report["entries_observed"] += 1
                    info = entry.stat(follow_symlinks=False)
                    name = entry.name
                    if _reparse(info):
                        report["reparse_entries_observed"] += 1
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        if depth == 0:
                            lower = name.casefold()
                            if "_is_running_" in lower:
                                report["workspace_running"] += 1
                            elif "_rdy_for_" in lower:
                                report["workspace_ready"] += 1
                            else:
                                report["workspace_other"] += 1
                        if depth < max_depth:
                            stack.append((Path(entry.path), depth + 1))
                        else:
                            report["directories_not_descended"] += 1
                    elif stat.S_ISREG(info.st_mode):
                        report["files_observed"] += 1
                        lower = name.casefold()
                        if lower.endswith(_SIDECARS):
                            report["sqlite_sidecars_observed"] += 1
                        if lower.endswith(_DATABASE_EXTENSIONS):
                            report["sqlite_files_observed"] += 1
                            report["sqlite_file_bytes_observed"] += info.st_size
                    else:
                        report["issues"].append("unsupported_entry_type")
            if _identity(directory.lstat()) != start:
                report["issues"].append("directory_changed_during_scan")
        if _identity(root.lstat()) != before:
            report["issues"].append("root_changed_during_scan")
    except (OSError, ValueError):
        report["issues"].append("metadata_scan_incomplete")
        return report

    if report["workspace_running"]:
        report["issues"].append("running_workspaces_observed")
    if report["sqlite_sidecars_observed"]:
        report["issues"].append("sqlite_sidecars_observed")
    if report["reparse_entries_observed"]:
        report["issues"].append("reparse_entries_not_followed")
    report["status"] = (
        "REVIEW_REQUIRED" if report["issues"]
        else "OBSERVED_METADATA_ONLY"
    )
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded WorkPool filesystem metadata-only observation; no writes."
    )
    parser.add_argument("--workpool", required=True, help="Explicit existing WorkPool root")
    parser.add_argument("--max-entries", type=int, default=10000)
    parser.add_argument("--max-depth", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        result = inventory_workpool_metadata(
            args.workpool, max_entries=args.max_entries,
            max_depth=args.max_depth,
        )
    except (ValueError, OSError):
        result = {
            "status": "UNVERIFIABLE",
            "issues": ["invalid_arguments_or_root"],
            "production_workpool_verified": False,
            "deployment_authorized": False,
            "file_contents_read": False,
            "sqlite_connections_opened": False,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return {"OBSERVED_METADATA_ONLY": 0, "REVIEW_REQUIRED": 1}.get(
        result["status"], 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
