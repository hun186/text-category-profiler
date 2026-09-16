"""Process execution mechanisms shared by pipeline composition roots."""

from .process import LegacyShellProcessRunner, ProcessRunner, RootFailFastPolicy

__all__ = ["LegacyShellProcessRunner", "ProcessRunner", "RootFailFastPolicy"]
