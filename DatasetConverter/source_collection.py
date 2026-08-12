"""Deterministic source discovery helpers for DatasetConverter.

The caller supplies the filesystem walker so this module stays independent of
the legacy runtime and can be tested without importing the conversion stage.
"""

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Executor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


SUPPORTED_SOURCE_EXTENSIONS = ("txt", "AI2", "sql3")
EXCLUDED_PATH_PARTS = ("untagged", "unspec")


class SourceRole(str, Enum):
    """The semantic role a source plays in dataset generation."""

    REGULAR = "regular source"
    FIXED_TEST = "fixed test source"
    CZJ_CORPUS = "CZJ corpus source"


@dataclass(frozen=True)
class SourceSpec:
    """Declarative filesystem discovery policy for one source role."""

    role: SourceRole
    root_paths: tuple[str, ...]
    filename_pattern: str | None = None
    extensions: tuple[str, ...] = SUPPORTED_SOURCE_EXTENSIONS
    excluded_path_parts: tuple[str, ...] = EXCLUDED_PATH_PARTS


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

    return discover_source_spec(
        SourceSpec(
            role=SourceRole.REGULAR,
            root_paths=tuple(root_paths),
            filename_pattern=filename_pattern,
        ),
        walker=walker,
    )


def discover_source_spec(
    source: SourceSpec,
    *,
    walker: Callable[..., Iterable[str]],
) -> list[str]:
    """Discover files for ``source`` without interpreting its source role.

    The adapter owns filesystem traversal while the immutable spec records why
    the files are being collected and which discovery policy applies.  A
    ``None`` filename pattern intentionally omits the legacy walker keyword,
    which preserves FixedTest discovery behaviour.
    """

    discovered: list[str] = []
    for root_path in source.root_paths:
        walker_kwargs = {"Extension": list(source.extensions)}
        if source.filename_pattern is not None:
            walker_kwargs["FullPathFNrePat"] = source.filename_pattern
        paths = walker(root_path, **walker_kwargs)
        discovered.extend(
            path
            for path in paths
            if not any(
                part.lower() in path.lower()
                for part in source.excluded_path_parts
            )
        )
    return sorted(discovered)


def select_unique_content_paths(
    hash_mappings: Iterable[Mapping[str, str]],
) -> list[str]:
    """Select one source path for each content hash.

    Hash calculation is an adapter concern because the legacy stage performs it
    in process workers. This pure step preserves that stage's conflict rule:
    mappings are consumed in order and the last path seen for a hash is kept.
    """

    path_hashes: dict[str, str] = {}
    for mapping in hash_mappings:
        path_hashes.update(mapping)

    hash_paths: dict[str, str] = {}
    for path, content_hash in path_hashes.items():
        hash_paths[content_hash] = path
    return list(hash_paths.values())
