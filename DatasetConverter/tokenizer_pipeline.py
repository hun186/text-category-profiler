"""Dependency-free transformations for tokenizer-based document slicing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenizedChunks:
    chunks: tuple
    retokenized: tuple


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
