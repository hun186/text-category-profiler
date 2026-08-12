"""Deterministic source discovery helpers for DatasetConverter.

The caller supplies the filesystem walker so this module stays independent of
the legacy runtime and can be tested without importing the conversion stage.
"""

from collections.abc import Callable, Iterable


SUPPORTED_SOURCE_EXTENSIONS = ("txt", "AI2", "sql3")
EXCLUDED_PATH_PARTS = ("untagged", "unspec")


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
