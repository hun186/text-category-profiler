"""Dependency-light process execution with owner-specific failure policy."""

from dataclasses import dataclass
import subprocess
from typing import Any, Callable, Protocol


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
