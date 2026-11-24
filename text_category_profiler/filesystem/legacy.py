"""Thin adapter over the legacy root filesystem operations."""

import ntpath
import os
import platform
from pathlib import Path

from text_category_profiler.filesystem.no_replace import _handoff_rename_noreplace
from text_category_profiler.filesystem.no_replace import _is_link_or_reparse


class LegacyFileSystem:
    def __init__(self, *, make_directory, walk, chown, backup,
                 platform_name=platform.system):
        self._make_directory = make_directory
        self._walk = walk
        self._chown = chown
        self._backup = backup
        self._platform_name = platform_name

    def list_directory(self, path):
        return os.listdir(path)

    def make_directory(self, path):
        return self._make_directory(path)

    def move(self, source, destination):
        """Move one work-ID folder without nesting/merging into a peer.

        shutil.move treats an existing directory as a parent, potentially
        moving a job inside a stale/competing completed job. Reuse the shared
        no-replace stage publisher, imported only for this runtime operation.
        """
        source_path, destination_path = Path(source), Path(destination)
        if not source_path.is_dir() or _is_link_or_reparse(source_path):
            raise FileNotFoundError("WORKITEM_MOVE_SOURCE_NOT_A_REAL_DIRECTORY")
        if os.path.lexists(destination):
            raise FileExistsError("WORKITEM_MOVE_DESTINATION_ALREADY_EXISTS")

        _handoff_rename_noreplace(source, destination)
        # A cross-device copy can fail after publishing a partial target.
        # Do not claim acquisition/delivery success, retry or delete either.
        if (os.path.lexists(source)
                or not destination_path.is_dir()
                or _is_link_or_reparse(destination_path)):
            raise RuntimeError("WORKITEM_MOVE_INCOMPLETE")
        return destination

    def verify_delivery_source(self, source):
        """Reject a missing or aliased Processing leaf before report backup.

        This is a *read-only preflight*, not an exclusive ownership token:
        another process can still change the leaf before the final move.
        """
        path = Path(source)
        if (not os.path.lexists(source)
                or not path.is_dir() or _is_link_or_reparse(path)):
            raise FileNotFoundError(
                "WORKITEM_DELIVERY_SOURCE_NOT_REAL_DIRECTORY"
            )

    def backup(self, **kwargs):
        """Reject an existing alias at an explicitly selected backup leaf.

        An external Work-ID backup can write directly into an existing
        WorkPool/<work-id>. Do not follow symlinks, junctions, dangling links
        or special files at that leaf; never delete or repair them here.
        Other legacy backup modes without DesDir preserve their contract.
        """
        if "DesDir" in kwargs:
            destination = kwargs["DesDir"]
            if not isinstance(destination, (str, os.PathLike)):
                raise ValueError("WORKITEM_BACKUP_INVALID_DESTINATION_PATH")
            path = os.fspath(destination)
            if not isinstance(path, str):
                raise ValueError("WORKITEM_BACKUP_INVALID_DESTINATION_PATH")
            # lstat("leaf/") can follow a directory symlink on POSIX.
            # Inspect the literal leaf instead, without altering the path
            # spelling passed to the legacy backup writer.
            inspection_path = path.rstrip("/\\")
            drive, remainder = ntpath.splitdrive(inspection_path)
            if (not inspection_path or (drive and not remainder)
                    or inspection_path in (".", "..")):
                raise ValueError("WORKITEM_BACKUP_INVALID_DESTINATION_PATH")
            if os.path.lexists(inspection_path):
                if (_is_link_or_reparse(inspection_path)
                        or not Path(inspection_path).is_dir()):
                    raise RuntimeError(
                        "WORKITEM_BACKUP_DESTINATION_NOT_REAL_DIRECTORY"
                    )
        return self._backup(**kwargs)

    def platform_name(self):
        return self._platform_name()

    def walk(self, path):
        return self._walk(path)

    def chown(self, path):
        return self._chown(path)
