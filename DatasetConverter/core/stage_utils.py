"""Dependency-light filesystem and sampling helpers for the converter stage."""

import hashlib
import os
import random
import string
import time
from collections.abc import Iterable, Sequence
from typing import Any


def walk_files(
    root_path: str,
    Extension: str | Sequence[str] = (),
    FNrePat: str | None = None,
    FullPathFNrePat: str | None = None,
) -> list[str]:
    """Preserve the legacy ``OSWALK`` discovery and normalization contract."""

    import re

    extensions = [Extension] if isinstance(Extension, str) else list(Extension)
    extensions = [extension.lower() for extension in extensions]
    result: list[str] = []
    for directory, _, filenames in os.walk(root_path):
        for filename in filenames:
            full_path = os.path.join(directory, filename)
            if FNrePat is not None and re.search(FNrePat, filename) is None:
                continue
            if (
                FullPathFNrePat is not None
                and re.search(FullPathFNrePat, full_path) is None
            ):
                continue
            if not extensions or any(
                filename.lower().endswith(extension) for extension in extensions
            ):
                result.append(full_path.replace("\\", "/"))
    return result


def make_directory(path: str) -> None:
    """Create ``path`` like the legacy ``MKDIR`` helper."""

    if path:
        os.makedirs(path, exist_ok=True)


def split_list(values: Sequence[Any], chunks: int = 2) -> list[list[Any]]:
    """Distribute contiguous values across exactly ``chunks`` buckets."""

    if chunks <= 0:
        raise ValueError("chunks must be greater than zero")
    quotient, remainder = divmod(len(values), chunks)
    result: list[list[Any]] = []
    offset = 0
    for index in range(chunks):
        size = quotient + (1 if index < remainder else 0)
        result.append(list(values[offset : offset + size]))
        offset += size
    return result


class FileHashJob:
    """Serializable worker job that hashes a list of files."""

    def __init__(
        self,
        file_list: Iterable[str],
        hash_algorithm: str = "md5",
        byte_limit: int | None = None,
    ) -> None:
        self.file_list = list(file_list)
        self.hash_algorithm = hash_algorithm
        self.byte_limit = byte_limit

    def run(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for path in self.file_list:
            digest = getattr(hashlib, self.hash_algorithm)()
            with open(path, "rb") as source:
                digest.update(source.read(self.byte_limit))
            hashes[path] = digest.hexdigest()
        return hashes


def random_sample(values: Sequence[Any], count: int) -> list[Any]:
    """Sample no more items than are available."""

    return random.sample(list(values), min(len(values), count))


def random_replace(text: str, replaced_characters: int = 1) -> str:
    """Preserve the legacy one-character augmentation behavior."""

    characters = list(text)
    characters[random.randint(0, len(characters) - 1)] = "".join(
        random.choice(string.ascii_uppercase + string.digits)
        for _ in range(replaced_characters)
    )
    return "".join(characters)


def show_elapsed_time(start_time: float | None = None) -> float | None:
    """Print and return elapsed seconds when timing was enabled."""

    if start_time is None:
        return None
    elapsed = time.time() - start_time
    print(f"Elapsed time · {elapsed:.2f} seconds")
    return elapsed
