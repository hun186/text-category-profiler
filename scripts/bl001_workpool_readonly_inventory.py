"""Bounded, metadata-only WorkPool inventory with NO database or file-content reads.

This utility is intentionally separate from detached-copy SQLite checks. It
does not open DBs, read dataset rows, acquire work, create directories, write
logs, checkpoint WAL, stop workers, or certify production deployment.
"""
from __future__ import annotations

import argparse
import json
import ntpath
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


def _canonical_windows_path(path: str) -> str:
    """Compare Win32 handle paths to ordinary drive and UNC spellings."""
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return ntpath.normcase(ntpath.normpath(path))


class _BudgetReached(Exception):
    """The bounded inventory must stop rather than silently omit entries."""


class _BoundaryLost(Exception):
    """A directory could not be tied to an approved, no-follow handle."""


def _observe_entry(report: dict, name: str, depth: int,
                   *, is_dir: bool, is_reparse: bool,
                   is_file: bool = False, size: int = 0,
                   max_depth: int = 3) -> bool:
    """Record metadata only; return whether a child directory should be opened."""
    if report["entries_observed"] >= report["max_entries"]:
        raise _BudgetReached()
    report["entries_observed"] += 1
    if is_reparse:
        report["reparse_entries_observed"] += 1
        return False
    if is_dir:
        if depth == 0:
            lower = name.casefold()
            if "_is_running_" in lower:
                report["workspace_running"] += 1
            elif "_rdy_for_" in lower:
                report["workspace_ready"] += 1
            else:
                report["workspace_other"] += 1
        if depth < max_depth:
            return True
        report["directories_not_descended"] += 1
    elif is_file:
        report["files_observed"] += 1
        lower = name.casefold()
        if lower.endswith(_SIDECARS):
            report["sqlite_sidecars_observed"] += 1
        if lower.endswith(_DATABASE_EXTENSIONS):
            report["sqlite_files_observed"] += 1
            report["sqlite_file_bytes_observed"] += size
    else:
        report["issues"].append("unsupported_entry_type")
    return False


def _walk_posix_directory(fd: int, depth: int, report: dict) -> None:
    """POSIX fd-relative, O_NOFOLLOW traversal: no pathname re-opening."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    start = _identity(os.fstat(fd))
    report["directories_observed"] += 1
    # scandir(fd) enumerates the already opened directory, never a path
    # that can be swapped to a different location by a concurrent writer.
    with os.scandir(fd) as entries:
        for entry in entries:
            info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
            child = _observe_entry(
                report, entry.name, depth,
                is_dir=stat.S_ISDIR(info.st_mode),
                is_reparse=_reparse(info),
                is_file=stat.S_ISREG(info.st_mode), size=info.st_size,
                max_depth=report["max_depth"],
            )
            if child:
                child_fd = os.open(entry.name, flags, dir_fd=fd)
                try:
                    opened = os.fstat(child_fd)
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise _BoundaryLost()
                    _walk_posix_directory(child_fd, depth + 1, report)
                finally:
                    os.close(child_fd)
    if _identity(os.fstat(fd)) != start:
        report["issues"].append("directory_changed_during_scan")


def _walk_posix(root: Path, report: dict, baseline: os.stat_result) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    try:
        opened = os.fstat(root_fd)
        if ((opened.st_dev, opened.st_ino) !=
                (baseline.st_dev, baseline.st_ino)):
            raise _BoundaryLost()
        _walk_posix_directory(root_fd, 0, report)
    finally:
        os.close(root_fd)


def _walk_windows_root_only(root: Path, expected_root: Path,
                            expected_stat: os.stat_result, report: dict) -> None:
    """Handle-bound Win32 top-level enumeration; never path-scan descendants.

    Python's Windows scandir() cannot use a directory fd, and opening child
    paths would reintroduce a junction-swap race. Therefore Windows uses
    GetFileInformationByHandleEx on one verified root handle ONLY. Descendant
    scans must use a separate handle-relative Win32 implementation later;
    do not pretend their SQLite sidecars were inspected.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    )
    CreateFileW.restype = wintypes.HANDLE
    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = (wintypes.HANDLE,)
    CloseHandle.restype = wintypes.BOOL
    GetFinalPathNameByHandleW = kernel32.GetFinalPathNameByHandleW
    GetFinalPathNameByHandleW.argtypes = (
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
    )
    GetFinalPathNameByHandleW.restype = wintypes.DWORD
    GetInfo = kernel32.GetFileInformationByHandleEx
    GetInfo.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    GetInfo.restype = wintypes.BOOL

    before = expected_root
    handle = CreateFileW(
        str(root), 0x0001 | 0x0080, 0x0001 | 0x0002 | 0x0004,
        None, 3, 0x02000000 | 0x00200000, None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise _BoundaryLost()
    try:
        attrs_buf = ctypes.create_string_buffer(8)
        if not GetInfo(handle, 9, attrs_buf, len(attrs_buf)):
            raise _BoundaryLost()
        attrs = int.from_bytes(attrs_buf.raw[:4], "little")
        if (attrs & _REPARSE_FLAG) or not (attrs & 0x10):
            raise _BoundaryLost()
        # FILE_ID_INFO (class 18) = 8-byte volume serial + 16-byte ID.
        # Paths can be replaced by an ordinary different directory without
        # changing their spelling. Match the original inode before reading
        # any entries, not just GetFinalPathNameByHandleW.
        id_buf = ctypes.create_string_buffer(24)
        if not GetInfo(handle, 18, id_buf, len(id_buf)):
            raise _BoundaryLost()
        root_file_id = int.from_bytes(id_buf.raw[8:24], "little")
        if not expected_stat.st_ino or root_file_id != expected_stat.st_ino:
            raise _BoundaryLost()
        actual_buf = ctypes.create_unicode_buffer(32768)
        length = GetFinalPathNameByHandleW(handle, actual_buf, len(actual_buf), 0)
        if not length or length >= len(actual_buf):
            raise _BoundaryLost()
        if _canonical_windows_path(actual_buf.value) != _canonical_windows_path(str(before)):
            raise _BoundaryLost()
        report["directories_observed"] += 1
        report["windows_root_only"] = True
        report["nested_files_examined"] = False
        report["sqlite_sidecar_scan_complete"] = False
        # FILE_ID_BOTH_DIR_INFO: fixed header including FileId occupies
        # 104 bytes; FileNameLength is a byte count of UTF-16LE names.
        buffer = ctypes.create_string_buffer(65536)
        while True:
            if not GetInfo(handle, 10, buffer, len(buffer)):
                error = ctypes.get_last_error()
                if error == 18:  # ERROR_NO_MORE_FILES
                    break
                raise _BoundaryLost()
            offset = 0
            while True:
                next_offset = int.from_bytes(buffer.raw[offset:offset + 4], "little")
                attrs = int.from_bytes(buffer.raw[offset + 56:offset + 60], "little")
                length_bytes = int.from_bytes(buffer.raw[offset + 60:offset + 64], "little")
                file_size = int.from_bytes(buffer.raw[offset + 40:offset + 48],
                                           "little", signed=True)
                if length_bytes % 2 or offset + 104 + length_bytes > len(buffer):
                    raise _BoundaryLost()
                raw_name = buffer.raw[offset + 104:offset + 104 + length_bytes]
                name = raw_name.decode("utf-16-le")
                if name not in (".", ".."):
                    child = _observe_entry(
                        report, name, 0, is_dir=bool(attrs & 0x10),
                        is_reparse=bool(attrs & _REPARSE_FLAG),
                        is_file=not (attrs & 0x10),
                        size=max(0, file_size), max_depth=0,
                    )
                    if child:
                        raise _BoundaryLost()  # Windows never opens children
                if not next_offset:
                    break
                if next_offset < 104 or offset + next_offset >= len(buffer):
                    raise _BoundaryLost()
                offset += next_offset
        # If root moved/renamed midscan, the opened handle remains the old
        # root. Fail instead of treating a detached handle as current.
        if _canonical_windows_path(str(root.resolve(strict=True))) != _canonical_windows_path(str(before)):
            raise _BoundaryLost()
    finally:
        CloseHandle(handle)


def inventory_workpool_metadata(workpool: str | Path, *,
                                max_entries: int = 10000,
                                max_depth: int = 3) -> dict:
    """Read only anchored directory metadata; never read file contents."""
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
        "windows_root_only": False,
        "nested_files_examined": os.name != "nt",
        "sqlite_sidecar_scan_complete": False,
        "issues": [],
        "file_contents_read": False,
        "sqlite_connections_opened": False,
        "production_workpool_verified": False,
        "deployment_authorized": False,
        "candidate_deletion_authorized": False,
        "limits": (
            "Metadata-only bounded observation; no quiescence, database "
            "integrity, writer ownership, backup recovery or deployment "
            "certification. Windows inspects top-level entries ONLY."
        ),
    }
    # Fix the expected approved inode/path BEFORE any reopen, so a
    # path-component replacement cannot redefine "the approved WorkPool".
    try:
        expected_root_stat = root.lstat()
        expected_root = root.resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        report["issues"].append("root_unavailable")
        return report
    reason = _root_guard(root)
    if reason:
        report["issues"].append(reason)
        return report
    try:
        if os.name == "nt":
            _walk_windows_root_only(root, expected_root, expected_root_stat, report)
        elif hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"):
            _walk_posix(root, report, expected_root_stat)
        else:
            report["issues"].append("handle_bound_traversal_unavailable")
            return report
    except _BudgetReached:
        report["issues"].append("entry_budget_exhausted")
        return report
    except (_BoundaryLost, OSError, ValueError, RuntimeError):
        report["issues"].append("directory_boundary_not_verifiable")
        return report
    # A bounded scan can observe zero sidecars while leaving unseen
    # descendants. Only a completed POSIX traversal with no skipped child
    # directory is allowed to claim sidecar coverage.
    report["sqlite_sidecar_scan_complete"] = (
        os.name != "nt" and report["directories_not_descended"] == 0
    )
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
