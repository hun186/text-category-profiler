"""Pure transformations between sample readers and dataset assembly."""

import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CollectedSamples:
    """Rows and multi-label counters returned by a group of reader jobs."""

    rows: tuple[Mapping[str, Any], ...]
    multi_label_counts: tuple[Any, ...]


@dataclass(frozen=True)
class SourceMetadata:
    """Source columns resolved from a sample's provenance path."""

    source_type: Any
    source: Any


@dataclass(frozen=True)
class ElasticsearchProvenance:
    """Filename metadata assembled for an Elasticsearch sample."""

    file_path: str
    invalid_date: Any | None = None


@dataclass(frozen=True)
class SegmentResult:
    """Named outcome of transforming one sliced-text segment."""

    row: Mapping[str, Any] | None
    reason: str


def build_elasticsearch_provenance(
    file_path: str,
    *,
    es_job: Mapping[str, Any],
    metadata: Mapping[str, Any],
    subject: Any,
    sanitize_filename: Callable[[str], str],
) -> ElasticsearchProvenance:
    """Build the legacy ES subject/target/date provenance path.

    Path components retain their historical order: optional subject prefix,
    target role, then ingestion date. Invalid non-empty dates retain the
    legacy ``None/`` prefix while returning diagnostics for the adapter to log.
    """

    resolved_path = str(file_path)
    if es_job.get("Vis_ESFileNameMode", "") == "subject_id" and subject is not None:
        resolved_path = f"{sanitize_filename(str(subject))[:100]}_{resolved_path}"

    if "es_tokens" in es_job:
        target_role = "Target" if metadata.get("Target") == "T" else "NonTarget"
        resolved_path = f"{target_role}/{resolved_path}"

    source_date = metadata.get("itcDT", "")
    if not source_date:
        return ElasticsearchProvenance(resolved_path)

    parsed_date = None
    for date_format in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            parsed_date = datetime.strptime(source_date, date_format).strftime("%Y%m%d")
            break
        except (TypeError, ValueError):
            continue

    return ElasticsearchProvenance(
        f"{parsed_date}/{resolved_path}",
        invalid_date=source_date if parsed_date is None else None,
    )


def normalize_segment_layout(text: str) -> str:
    """Replace excessive line breaks using the legacy reader threshold.

    A segment is considered over-broken only when more than ten percent of
    its characters are newlines. Empty strings are preserved so this pure
    transformation remains safe independently of the reader's empty-segment
    filtering step.
    """

    if not text:
        return text
    if text.count("\n") / len(text) > 0.1:
        return text.replace("\n", " ")
    return text


def prepare_sample_text(
    text: str,
    *,
    minimum_length: int,
    conversion: str | None,
    convert: Callable[[str, str], str],
) -> str | None:
    """Convert a normal segment and apply the legacy minimum-length gate.

    Conversion intentionally happens before eligibility is evaluated. The
    strict legacy boundary accepts text with ``len(text) >= minimum_length``.
    The conversion adapter is not called when no conversion is configured.
    """

    prepared = convert(text, conversion) if conversion is not None else text
    if len(prepared) < minimum_length:
        return None
    return prepared


def detect_special_output_label(text: str) -> str | None:
    """Return the legacy rule-based label for a long malformed segment.

    The caller retains the existing ``len(text) > 50`` and rule-based-active
    gates. Candidate priority and strict thresholds intentionally mirror the
    reader: digits, then periods, then a dominant repeated character. A
    candidate is accepted only when fewer than 40 characters remain after the
    legacy ASCII range cleanup.
    """

    length = len(text)
    if length == 0:
        return None

    non_space_length = length - text.count(" ")
    digit_count = sum(character in "0123456789" for character in text)
    if digit_count / non_space_length > 0.9:
        candidate = "Uncertainty-Unidentified Digits"
    elif text.count(".") / length > 0.9:
        candidate = "BD-Table Of Contents"
    elif Counter(text).most_common(1)[0][1] / length > 0.9:
        candidate = "False Decoding-Broken Data Stream"
    else:
        return None

    if len(re.sub(r"[ -F,\[-f,\{-~]", "", text)) < 40:
        return candidate
    return None


def select_rule_based_input_label(
    text: str,
    *,
    default_label: str,
    rules: Mapping[tuple[str, tuple[int, int]], str],
    info_scores: Mapping[str, Any],
    match_counter: Callable[[str, str], int] | None = None,
) -> str:
    """Select the highest-scoring regex label that matches its interval.

    Rules retain mapping iteration order. Python's stable sort therefore
    preserves the legacy behavior where the later rule wins when candidates
    have equal information scores. The matcher is injectable so interval and
    priority behavior can be tested without coupling callers to regex I/O.
    """

    if match_counter is None:
        match_counter = lambda pattern, value: len(re.findall(pattern, value))

    normalized_text = text.lower()
    candidates = [
        label
        for (pattern, interval), label in rules.items()
        if interval[0]
        <= match_counter(pattern, normalized_text)
        <= interval[1]
    ]
    if not candidates:
        return default_label
    return sorted(candidates, key=lambda label: info_scores[label])[-1]


def select_document_samples(
    rows: Iterable[Mapping[str, Any]],
    *,
    input_label: str,
    bounds: Mapping[str, int],
    random_sample: bool,
    shuffle: Callable[[list[Mapping[str, Any]]], None],
) -> list[Mapping[str, Any]]:
    """Apply the legacy per-document shuffle and sample-count limit.

    The caller supplies the shuffle strategy so tests and future stage config
    can make randomization deterministic without changing the current runtime
    default. Label-specific bounds take precedence over ``default`` exactly as
    they did in ``SampleReader.textSegsToSamples``.
    """

    selected = list(rows)
    if random_sample:
        shuffle(selected)
    limit = bounds.get(input_label, bounds["default"])
    return selected[:limit]


def assemble_sample_row(
    *,
    file_path: str,
    input_label: str,
    output_label: str,
    text: str,
    part_number: int,
) -> dict[str, Any]:
    """Build the canonical row emitted by a sliced-text reader.

    Keeping row assembly outside ``SampleReader`` makes the reader's common
    output contract testable without importing its filesystem, tokenizer, or
    external-service adapters.  Value validation remains at the reader/schema
    boundaries so this extraction does not narrow legacy inputs.
    """

    return {
        "file": file_path,
        "InLabel": input_label,
        "OutLabel": output_label,
        "text": text,
        "PartNO": part_number,
    }


def transform_sample_segment(
    text: str,
    *,
    file_path: str,
    input_label: str,
    part_number: int,
    rule_based_active: bool,
    rules: Mapping[tuple[str, tuple[int, int]], str],
    info_scores: Mapping[str, Any],
    label_conversion: Mapping[str, str],
    minimum_length: int,
    text_conversion: str | None,
    convert: Callable[[str, str], str],
) -> SegmentResult:
    """Transform one reader segment while preserving legacy branch order.

    Special malformed-segment labels bypass regex overrides, text conversion,
    minimum-length filtering, and label conversion. Normal segments apply
    those stages in their existing order and report an explicit drop reason.
    """

    original_length = len(text)
    normalized_text = normalize_segment_layout(text)
    if rule_based_active and original_length > 50:
        special_label = detect_special_output_label(normalized_text)
        if special_label is not None:
            return SegmentResult(
                assemble_sample_row(
                    file_path=file_path,
                    input_label=input_label,
                    output_label=special_label,
                    text=normalized_text,
                    part_number=part_number,
                ),
                "special-label",
            )

    resolved_label = input_label
    if rule_based_active:
        resolved_label = select_rule_based_input_label(
            normalized_text,
            default_label=input_label,
            rules=rules,
            info_scores=info_scores,
        )

    prepared_text = prepare_sample_text(
        normalized_text,
        minimum_length=minimum_length,
        conversion=text_conversion,
        convert=convert,
    )
    if prepared_text is None:
        return SegmentResult(None, "below-minimum-length")

    output_label = (
        label_conversion[resolved_label] if label_conversion else resolved_label
    )
    return SegmentResult(
        assemble_sample_row(
            file_path=file_path,
            input_label=resolved_label,
            output_label=output_label,
            text=prepared_text,
            part_number=part_number,
        ),
        "accepted",
    )


def collect_reader_results(
    reader_results: Iterable[Sequence[Any]],
) -> CollectedSamples:
    """Assemble reader-job results without DataFrame or filesystem access.

    Each reader job uses the legacy ``(rows, multi_label_count)`` contract.
    Keeping its assembly here makes the read/assemble boundary independently
    testable while leaving source-specific reading in the existing adapters.
    """

    rows: list[Mapping[str, Any]] = []
    multi_label_counts: list[Any] = []
    for result_index, result in enumerate(reader_results):
        if len(result) != 2:
            raise ValueError(
                "reader result at index "
                f"{result_index} must contain rows and a multi-label count"
            )

        result_rows, multi_label_count = result
        if not isinstance(result_rows, (list, tuple)):
            raise TypeError(
                f"reader rows at index {result_index} must be a list or tuple"
            )
        rows.extend(result_rows)
        multi_label_counts.append(multi_label_count)

    return CollectedSamples(tuple(rows), tuple(multi_label_counts))


def aggregate_multi_label_counts(
    multi_label_counts: Iterable[Any],
) -> dict[tuple[Any, ...], int]:
    """Aggregate reader multi-label counters without stage or logger state.

    Reader adapters use ``None`` when a sample has no multi-label metadata.
    Label sets are sorted before becoming dictionary keys so equivalent sets
    from different workers are combined deterministically.
    """

    aggregated: dict[tuple[Any, ...], int] = {}
    for result_index, result in enumerate(multi_label_counts):
        if result is None:
            continue
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise ValueError(
                "multi-label count result at index "
                f"{result_index} must contain labels and a count"
            )

        labels, count = result
        if labels is None:
            continue
        key = tuple(sorted(labels))
        aggregated[key] = aggregated.get(key, 0) + count
    return aggregated


def collect_source_metadata(
    file_paths: Iterable[str],
    *,
    labels: Sequence[str],
    resolver: Callable[[str, Sequence[str]], Sequence[Any]],
) -> tuple[SourceMetadata, ...]:
    """Resolve provenance columns before the DataFrame adapter mutates data.

    The injected resolver preserves the legacy path policy while this function
    owns result validation and row-level diagnostics. A path that does not map
    to known metadata remains the legacy ``(None, None)`` result.
    """

    resolved: list[SourceMetadata] = []
    for row_index, file_path in enumerate(file_paths):
        result = resolver(file_path, labels)
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise ValueError(
                f"source metadata result at row {row_index} for path "
                f"{file_path!r} must contain source type and source"
            )
        source_type, source = result
        resolved.append(SourceMetadata(source_type, source))
    return tuple(resolved)
