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


# These are compatible with signal/console interruption, but can also be
# returned deliberately by a child or shell. They are NOT proof of Ctrl+C.
# POSIX: 130 commonly means shell(128 + SIGINT), -2 means terminated by SIGINT.
# Windows: STATUS_CONTROL_C_EXIT is 0xC000013A (signed and unsigned forms).
_UNCONFIRMED_INTERRUPT_EXIT_CODES = frozenset(
    (130, -2, -1073741510, 3221225786)
)


def child_exit_interpretation(returncode: int) -> str:
    """Describe child exit status without attributing intent or modifying jobs."""
    return (
        "interruption_like_unconfirmed"
        if type(returncode) is int and returncode in _UNCONFIRMED_INTERRUPT_EXIT_CODES
        else "nonzero_child_exit"
    )


@dataclass(frozen=True)
class RootFailFastPolicy:
    """Retain the root orchestrator's non-zero exit behavior."""

    failure_reporter: Callable[[str, int, str], None]

    def check(self, result: Any, stage_name: str, command: str) -> Any:
        if result.returncode != 0:
            self.failure_reporter(stage_name, result.returncode, command)
            interpretation = child_exit_interpretation(result.returncode)
            # Keep the legacy fail-fast type, stage order and exact numeric
            # code. Appending a cautious hint must NOT invoke the root's
            # KeyboardInterrupt-only recorder or imply the job can be cleaned.
            suffix = (
                " [Signal-like child exit; operator interruption UNCONFIRMED; "
                "no WorkPool cleanup or automatic resume.]"
                if interpretation == "interruption_like_unconfirmed"
                else ""
            )
            raise RuntimeError(
                f"{stage_name} failed with exit code {result.returncode}. "
                f"Abort following stages. Command: {command}{suffix}"
            )
        return result
