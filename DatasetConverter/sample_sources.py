"""Narrow adapters that load and prepare source documents."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceDocument:
    """Text and labels loaded from one source before sample slicing."""

    text: str
    input_labels: tuple[str, ...]


@dataclass(frozen=True)
class PreparedDocument:
    """Normalized document and ordered segments ready for sample conversion."""

    text: str
    input_labels: tuple[str, ...]
    segments: tuple[str, ...]


def read_regular_text_document(
    file_path: str,
    *,
    unique_sorted_labels: bool,
    only_letters_digits_labels: bool,
    labels_from_path: Callable[..., Sequence[str]],
    read_text: Callable[..., str],
) -> SourceDocument | None:
    """Load the legacy ``.txt``/``.ai2`` filesystem source contract.

    Unlabelled ``.txt`` files are ignored, while unlabelled ``.ai2`` files
    retain their historical ``Scrap`` fallback.  Label parsing and file I/O
    remain injected adapters so routing can be characterized without loading
    tokenizer, pandas, Elasticsearch, or the real filesystem.
    """

    extension = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if extension not in {"ai2", "txt"}:
        raise ValueError(
            "regular text document must use a .txt or .ai2 extension: "
            f"{file_path}"
        )

    input_labels = tuple(
        labels_from_path(
            file_path,
            UniqueSorted=unique_sorted_labels,
            OnlyLettersDigits=only_letters_digits_labels,
        )
    )
    if not input_labels:
        if extension == "ai2":
            input_labels = ("Scrap",)
        else:
            return None

    return SourceDocument(
        text=read_text(file=file_path, encoding="utf-8"),
        input_labels=input_labels,
    )


def read_czj_corpus_document(
    database_path: str,
    *,
    title: str,
    connect: Callable[[str], Any],
) -> SourceDocument:
    """Load one CZJ corpus title while always closing its DB connection.

    The query shape and null-label ``Scrap`` fallback preserve the reader's
    historical contract.  A missing title now raises a source-specific error
    instead of failing later while unpacking ``None``.
    """

    connection = connect(database_path)
    try:
        row = connection.execute(
            "SELECT InLabel,text FROM Corpus WHERE title=?",
            [title],
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise LookupError(
            f"CZJ corpus title {title!r} was not found in {database_path!r}"
        )
    if not isinstance(row, (list, tuple)) or len(row) != 2:
        raise ValueError(
            "CZJ corpus query must return an InLabel/text pair for "
            f"title {title!r}"
        )

    input_label, text = row
    return SourceDocument(
        text=text,
        input_labels=(input_label if input_label is not None else "Scrap",),
    )


def apply_regular_cleaning_rules(
    document: SourceDocument,
    *,
    rules: Mapping[Any, Mapping[str, Any]],
    labels_in_exemptions: Callable[[Sequence[str], Sequence[str]], Sequence[str]],
    clean_text: Callable[[str, Mapping[Any, Mapping[str, Any]]], str],
) -> SourceDocument:
    """Apply the legacy label-aware regex cleaning sequence.

    Eligible rules accumulate in mapping order.  The cleaner is intentionally
    called after each eligible rule with the accumulated mapping, matching the
    historical reader even when this means an earlier rule is applied again.
    Rules whose ``ExemptInLabelList`` overlaps the document labels are skipped.
    """

    text = document.text
    applicable_rules: dict[Any, Mapping[str, Any]] = {}
    for key, rule in rules.items():
        exemptions = rule.get("ExemptInLabelList", [])
        if labels_in_exemptions(document.input_labels, exemptions):
            continue
        applicable_rules[key] = rule
        text = clean_text(text, applicable_rules)

    return SourceDocument(text=text, input_labels=document.input_labels)


def prepare_document_segments(
    document: SourceDocument,
    *,
    normalize_text: Callable[[str], str],
    divide_text: Callable[[str], Sequence[str]],
) -> PreparedDocument:
    """Normalize a loaded document before slicing it into ordered segments.

    Both operations remain injected adapters because the production cleaner
    and divider carry legacy language, tokenizer, model-path, and FixedTest
    policies.  This boundary fixes their orchestration order and preserves the
    document labels without importing those runtime dependencies.
    """

    normalized_text = normalize_text(document.text)
    segments = tuple(divide_text(normalized_text))
    return PreparedDocument(
        text=normalized_text,
        input_labels=document.input_labels,
        segments=segments,
    )
