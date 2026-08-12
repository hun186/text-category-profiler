"""Deterministic source discovery helpers for DatasetConverter.

The caller supplies the filesystem walker so this module stays independent of
the legacy runtime and can be tested without importing the conversion stage.
"""

from collections.abc import Callable, Iterable
from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_SOURCE_EXTENSIONS = ("txt", "AI2", "sql3")
EXCLUDED_PATH_PARTS = ("untagged", "unspec")


@dataclass(frozen=True)
class TextSource:
    """A decoded source file with its path-derived classifier label."""

    path: str
    label: str
    text: str


def read_labeled_text_source(path: str) -> TextSource:
    """Read the small ``#T#[label]`` text-file contract used by fixtures.

    This reader is deliberately limited to plain-text sources. The legacy AI2,
    SQLite, Elasticsearch, tokenization and cleanup adapters remain responsible
    for their own formats.
    """

    source_path = Path(path)
    label_parts = [
        part[4:-1]
        for part in source_path.parts
        if part.startswith("#T#[") and part.endswith("]")
    ]
    if not label_parts:
        raise ValueError(f"source path has no #T#[label] component: {path}")
    return TextSource(
        path=str(source_path),
        label=label_parts[-1],
        text=source_path.read_text(encoding="utf-8"),
    )


def read_text_sources(
    paths: Iterable[str], *, executor: Executor | None = None
) -> list[TextSource]:
    """Read text sources sequentially or through an injected worker executor."""

    ordered_paths = list(paths)
    if executor is None:
        return [read_labeled_text_source(path) for path in ordered_paths]
    return list(executor.map(read_labeled_text_source, ordered_paths))


def discover_source_files(
    root_paths: Iterable[str],
    filename_pattern: str,
    *,
    walker: Callable[..., Iterable[str]],
) -> list[str]:
    """Return a stable, filtered list of files found below ``root_paths``.

    ``walker`` follows the existing ``OSWALK`` keyword contract. Keeping it
    injected preserves current traversal behaviour while separating discovery
    ordering and path filtering from the conversion job class.
    """

    discovered: list[str] = []
    for root_path in root_paths:
        paths = walker(
            root_path,
            Extension=list(SUPPORTED_SOURCE_EXTENSIONS),
            FullPathFNrePat=filename_pattern,
        )
        discovered.extend(
            path
            for path in paths
            if not any(part in path.lower() for part in EXCLUDED_PATH_PARTS)
        )

    return sorted(discovered)
