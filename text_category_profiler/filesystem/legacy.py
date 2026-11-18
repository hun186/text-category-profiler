"""Thin adapter over the legacy root filesystem operations."""

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

    def backup(self, **kwargs):
        return self._backup(**kwargs)

    def platform_name(self):
        return self._platform_name()

    def walk(self, path):
        return self._walk(path)

    def chown(self, path):
        return self._chown(path)
