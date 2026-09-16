"""Thin adapter over the legacy root filesystem operations."""

import os
import platform
import shutil


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
        return shutil.move(source, destination)

    def backup(self, **kwargs):
        return self._backup(**kwargs)

    def platform_name(self):
        return self._platform_name()

    def walk(self, path):
        return self._walk(path)

    def chown(self, path):
        return self._chown(path)
