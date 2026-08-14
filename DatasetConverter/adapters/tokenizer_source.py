"""Integration boundaries for tokenizer model discovery and loading."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenizerModel:
    requested_directory: str
    resolved_directory: str
    used_fallback: bool


def resolve_tokenizer_model(
    model_directory,
    *,
    resolve_local_directory,
    walk,
    fallback_directory="xlm-roberta-base",
):
    """Resolve the legacy local/fallback path and its first model checkpoint."""
    requested_directory = model_directory or fallback_directory
    resolved_directory = resolve_local_directory(requested_directory)
    used_fallback = resolved_directory is None
    if used_fallback:
        resolved_directory = (
            resolve_local_directory(fallback_directory) or fallback_directory
        )

    for directory, _, files in walk(resolved_directory):
        if "config.json" in files:
            resolved_directory = directory
            break

    return TokenizerModel(
        requested_directory=requested_directory,
        resolved_directory=resolved_directory,
        used_fallback=used_fallback,
    )


def load_auto_tokenizer(model_directory, *, trust_remote_code=True):
    """Load an AutoTokenizer without requiring Transformers at module import time."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        model_directory,
        trust_remote_code=trust_remote_code,
    )
