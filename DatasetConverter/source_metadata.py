"""Dependency-free policies for deriving sample provenance from file paths."""

import re
from collections.abc import Sequence
from typing import Optional


def _split_path(file_path: str) -> list[str]:
    """Split either POSIX or Windows paths without consulting the host OS."""

    return re.split(r"/|\\", file_path)


def _capitalize_words(value: str) -> str:
    """Preserve the legacy label/path capitalization policy."""

    return " ".join(word[0].upper() + word[1:] for word in value.split())


def _labels_from_path(file_path: str) -> tuple[str, ...]:
    labels: list[str] = []
    for component in _split_path(file_path):
        if not component.startswith("#T#["):
            continue
        label_string = component[3:]
        parsed = [
            _capitalize_words(label.strip().strip("'"))
            for label in label_string[1:-1].split(",")
        ]
        labels.extend(label for label in parsed if label)
    return tuple(sorted(set(labels)))


def get_source_from_file_name(
    file_name: str,
    label_list: Sequence[str],
) -> tuple[Optional[str], Optional[str]]:
    """Return the legacy ``(SrcType, Src)`` metadata for a sample path.

    A label-bearing directory identifies the anchor in the path. For paths
    containing a ``Books`` component, metadata surrounds that anchor; regular
    source metadata is read from the two components preceding it. Unknown
    labels intentionally remain ``(None, None)`` for compatibility.
    """

    path_components = _split_path(file_name)
    normalized_components = [_capitalize_words(part) for part in path_components]
    path_labels = _labels_from_path(file_name)

    for label in label_list:
        if label not in path_labels:
            continue
        for index, component in enumerate(normalized_components):
            if component.startswith("#T#") and label in _labels_from_path(component):
                if "Books" in path_components:
                    return normalized_components[index - 1], normalized_components[index + 1]
                return normalized_components[index - 2], normalized_components[index - 1]
    return None, None


def getSrcFromFileName(
    FileName: str,
    LabelList: Sequence[str],
) -> tuple[Optional[str], Optional[str]]:
    """Compatibility wrapper retaining legacy keyword argument names."""

    return get_source_from_file_name(FileName, LabelList)
