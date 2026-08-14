"""Narrow adapters that load and prepare source documents."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from DatasetConverter.core.sample_schema import validate_sample_rows


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


@dataclass(frozen=True)
class ElasticsearchDocument:
    """Document content and provenance fields mapped from one ES response."""

    document: SourceDocument
    subject: Any
    metadata: Mapping[str, Any]


def map_elasticsearch_document(
    response: Mapping[str, Any],
    *,
    include_subject: bool,
) -> ElasticsearchDocument:
    """Map the legacy Elasticsearch response shape without network access.

    Required response containers retain fail-fast ``KeyError`` behavior.  A
    missing content value is represented by ``None`` so the network adapter
    can preserve its retry policy before this result enters text processing.
    """

    source = response["_source"]
    text = source["rawInfo"].get("content")
    subject = (
        source["communication"].get("subject", "") if include_subject else None
    )
    metadata = {
        "itcDT": source.get("itcDT", ""),
    }
    if len(source.get("userNames", [])) > 0:
        metadata["Target"] = "T"
    return ElasticsearchDocument(
        document=SourceDocument(text=text, input_labels=("Scrap",)),
        subject=subject,
        metadata=metadata,
    )


def fetch_elasticsearch_response(
    *,
    attempts: int,
    create_client: Callable[[], Any],
    fetch: Callable[[Any], Mapping[str, Any]],
    content_from_response: Callable[[Mapping[str, Any]], Any],
    on_error: Callable[[int, Exception], None],
) -> Mapping[str, Any] | None:
    """Fetch a response with bounded retries and per-attempt client cleanup.

    Credentials stay inside the injected client factory.  Exceptions and
    missing content both consume an attempt; only exceptions are reported to
    ``on_error``, matching the reader's legacy diagnostics.
    """

    if attempts < 1:
        raise ValueError("Elasticsearch fetch attempts must be at least 1")

    for attempt in range(attempts):
        client = None
        try:
            client = create_client()
            response = fetch(client)
            if content_from_response(response) is not None:
                return response
        except Exception as error:
            on_error(attempt, error)
        finally:
            if client is not None:
                client.close()
    return None


def read_czj_corpus_titles(
    database_path: str,
    *,
    connect: Callable[[str], Any],
) -> tuple[str, ...]:
    """Enumerate CZJ corpus titles in database row order.

    Title discovery is kept separate from per-title document loading so job
    generation does not need pandas or a generic query helper.  Null titles
    are rejected before worker jobs are created, and the connection is always
    closed.
    """

    connection = connect(database_path)
    try:
        rows = connection.execute('SELECT "title" FROM "Corpus"').fetchall()
    finally:
        connection.close()

    titles: list[str] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != 1:
            raise ValueError(
                "CZJ corpus title query row at index "
                f"{row_index} must contain exactly one value"
            )
        title = row[0]
        if title is None:
            raise ValueError(
                f"CZJ corpus title query row at index {row_index} is null"
            )
        titles.append(title)
    return tuple(titles)


def read_czj_sample_rows(
    database_path: str,
    *,
    connect: Callable[[str], Any],
) -> tuple[Mapping[str, Any], ...]:
    """Load and validate the already-sliced rows in a CZJ samples database.

    The adapter reads only the canonical sample columns from ``sampleSrc`` so
    pandas-generated index columns never leak into the domain rows.  The
    connection is closed on every fetch path, an empty table has a stable
    empty result, and malformed schemas fail before artifact output.
    """

    connection = connect(database_path)
    try:
        cursor = connection.execute(
            'SELECT "file", "InLabel", "OutLabel", "text", "PartNO" '
            'FROM "sampleSrc"'
        )
        column_names = tuple(description[0] for description in cursor.description)
        rows = tuple(dict(zip(column_names, row)) for row in cursor.fetchall())
    finally:
        connection.close()

    return validate_sample_rows(rows, source_stage="CZJ samples database")


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
