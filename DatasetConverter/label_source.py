"""Feature-activated adapter for legacy path-label extraction."""


def labels_from_path(
    file_path,
    *,
    unique_sorted=True,
    only_letters_digits=False,
):
    """Extract labels while preserving ``getLabelsFromFileName`` semantics."""
    from ClassesTree.Label_utils import getLabelsFromFileName

    return getLabelsFromFileName(
        file_path,
        UniqueSorted=unique_sorted,
        OnlyLettersDigits=only_letters_digits,
    )
