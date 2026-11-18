"""Dependency-light no-overwrite directory handoff primitives.

Shared by stage transitions and external Work-ID delivery. No models,
DataFrames, SQL or WorkPool paths are imported at module load time.
"""
import ctypes
import errno
import os
import shutil
import stat
import sys


def _is_link_or_reparse(path):
    """Detect POSIX symlink and Win32 junction/symlink from lstat metadata."""
    info = os.lstat(path)
    return (
        stat.S_ISLNK(info.st_mode)
        or bool(getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    )


def _handoff_rename_noreplace(source, destination):
    """Publish a stage directory without replacing a concurrent destination.

    Linux uses renameat2(RENAME_NOREPLACE); Windows os.rename already
    rejects existing destinations. Cross-device fallback uses copytree's
    exclusive destination creation, and may leave partial data on failure:
    the caller must stop and preserve both paths. Unsupported POSIX systems
    fail closed rather than silently overwrite an existing stage.
    """
    try:
        if os.name == "nt":
            os.rename(source, destination)
        elif sys.platform.startswith("linux"):
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is None:
                raise OSError(errno.ENOTSUP, "atomic no-replace rename unavailable")
            renameat2.argtypes = [
                ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                ctypes.c_char_p, ctypes.c_uint,
            ]
            renameat2.restype = ctypes.c_int
            # Linux constants: AT_FDCWD=-100, RENAME_NOREPLACE=1.
            outcome = renameat2(
                -100, os.fsencode(source), -100, os.fsencode(destination), 1
            )
            if outcome:
                error_number = ctypes.get_errno()
                raise OSError(error_number, os.strerror(error_number), source)
        else:
            raise OSError(errno.ENOTSUP, "atomic no-replace rename unavailable")
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        # Cross-volume destination creation remains exclusive; never pass
        # dirs_exist_ok=True or merge into a pre-existing stage directory.
        shutil.copytree(source, destination)
        shutil.rmtree(source)
