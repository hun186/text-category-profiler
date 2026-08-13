"""Dependency-free transformations for tokenizer-based document slicing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenizedChunks:
    chunks: tuple
    retokenized: tuple


@dataclass(frozen=True)
class TokenWordAnalysis:
    word_character_spans: tuple
    word_token_positions: tuple


def analyze_token_word_mapping(context, encoding):
    """Build the legacy debug word/token mapping without reader dependencies."""
    word_character_spans = []
    character_cursor = 0
    for word_index, word in enumerate(context.split(" ")):
        if not word:
            continue
        start = character_cursor
        end = start + len(word)
        word_character_spans.append((word_index, start, end))
        character_cursor = end + 1

    word_token_positions = {word_index: [] for word_index, _, _ in word_character_spans}
    word_ids = encoding.word_ids()
    for token_index, word_id in enumerate(word_ids):
        if word_id is None:
            continue
        character_span = encoding.token_to_chars(token_index)
        for word_index, start, end in word_character_spans:
            if character_span.start >= start and character_span.end <= end:
                word_token_positions[word_index].append(token_index)

    return TokenWordAnalysis(
        word_character_spans=tuple(word_character_spans),
        word_token_positions=tuple(
            (word_index, tuple(positions))
            for word_index, positions in word_token_positions.items()
            if positions
        ),
    )


def split_tokenized_context(
    context,
    tokenizer,
    *,
    maximum_tokens,
    reserved_tokens=3,
    retokenize=False,
    encoding=None,
):
    """Split text using tokenizer character spans while preserving legacy bounds."""
    chunk_token_count = maximum_tokens - reserved_tokens
    if chunk_token_count <= 0:
        raise ValueError("maximum_tokens must be greater than reserved_tokens")

    encoded = encoding if encoding is not None else tokenizer(context)
    tokens = encoded.tokens()
    content_positions = list(range(1, len(tokens) - 1))
    position_groups = [
        content_positions[start : start + chunk_token_count]
        for start in range(0, len(content_positions), chunk_token_count)
    ]

    character_bounds = [
        [
            encoded.token_to_chars(group[0]).start,
            encoded.token_to_chars(group[-1]).end,
        ]
        for group in position_groups
    ]
    for index in range(len(character_bounds) - 1):
        if character_bounds[index][1] == character_bounds[index + 1][0]:
            character_bounds[index][1] -= 1

    chunks = tuple(context[start : end + 1] for start, end in character_bounds)
    retokenized = (
        tuple(tuple(tokenizer(chunk).tokens()) for chunk in chunks)
        if retokenize
        else ()
    )
    return TokenizedChunks(chunks=chunks, retokenized=retokenized)
