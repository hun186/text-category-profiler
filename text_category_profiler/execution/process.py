"""Dependency-light process execution with owner-specific failure policy."""

from dataclasses import dataclass
import ntpath
import os
import platform
import subprocess
from typing import Any, Callable, Protocol


def _is_current_directory_path_entry(raw):
    """Recognize only Windows PATH spellings of the current directory.

    Do not canonicalize arbitrary relative directories or resolve user
    variables (which could change search order or introduce DLL hijacking).
    """
    clean = raw.strip().strip('"').strip()
    return bool(clean) and all(ch in "./\\\\" for ch in clean) and (
        ntpath.normpath(clean) == "."
    )


def sanitize_windows_dot_path(environ=None, *, windows=None):
    """Remove only dot-equivalent PATH entries in this Python process.

    Works for the old root workaround's variants (`.`, `.\\`, `./`,
    `.\\.`) while retaining every other segment exactly and in order.
    This change is inherited by new child processes; it never writes the
    parent CMD or the system environment. Can be called repeatedly.
    """
    if windows is None:
        windows = platform.system().lower() == "windows"
    if not windows:
        return 0
    if environ is None:
        environ = os.environ
    original = environ.get("PATH", "")
    entries = original.split(";")
    keep = [x for x in entries if not _is_current_directory_path_entry(x)]
    dropped = len(entries) - len(keep)
    if dropped:
        environ["PATH"] = ";".join(keep)
    return dropped


def preflight_windows_dll_path(path=None, *, windows=None):
    """Block other relative Windows PATH entries before expensive pipeline work."""
    if windows is None:
        windows = platform.system().lower() == "windows"
    if not windows:
        return
    if path is None:
        path = os.environ.get("PATH", "")
    relative = [
        item.strip() for item in path.split(";")
        if item.strip() and not ntpath.isabs(item.strip().strip('"'))
    ]
    if relative:
        displayed = ", ".join(repr(item) for item in relative[:3])
        if len(relative) > 3:
            displayed += ", ..."
        raise RuntimeError(
            "TULIP_WINDOWS_PATH_RELATIVE: Windows PATH has relative entries "
            f"({displayed}); Tulip's os.add_dll_directory may raise "
            "[WinError 87]. In the SAME Anaconda Prompt, remove these "
            "relative PATH entries before starting full Stage 4. "
            'For a trailing ";." entry, run: set "PATH=%PATH:;.=%" '
            "and retry. No PATH or WorkPool changes were made."
        )


class ProcessRunner(Protocol):
    """Execute an existing shell command string without imposing a policy."""

    def execute(self, command: str) -> Any:
        """Return the process result, including non-zero results."""


@dataclass(frozen=True)
class LegacyShellProcessRunner:
    """Reproduce the root pipeline's legacy shell invocation mechanism."""

    run_process: Callable[..., Any] = subprocess.run

    def execute(self, command: str) -> Any:
        return self.run_process(command, shell=True, check=False)


@dataclass(frozen=True)
class RootFailFastPolicy:
    """Retain the root orchestrator's non-zero exit behavior."""

    failure_reporter: Callable[[str, int, str], None]

    def check(self, result: Any, stage_name: str, command: str) -> Any:
        if result.returncode != 0:
            self.failure_reporter(stage_name, result.returncode, command)
            raise RuntimeError(
                f"{stage_name} failed with exit code {result.returncode}. "
                f"Abort following stages. Command: {command}"
            )
        return result
