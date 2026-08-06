import os


def resolve_local_model_directory(model_dir, search_roots=("", "BertScript")):
    """Return the first existing local directory for a configured model name.

    Model names in the CLI configuration are historically bare directory names,
    while downloaded base models may live either at the repository root or under
    ``BertScript``. Keep explicit paths first and only add search roots for bare
    names so an absolute or caller-relative path is never unexpectedly rewritten.
    """
    if not model_dir:
        return None

    normalized = os.path.normpath(model_dir)
    candidates = [normalized]
    if not os.path.isabs(normalized) and os.path.dirname(normalized) in ("", "."):
        candidates.extend(
            os.path.join(root, normalized)
            for root in search_roots
            if root
        )

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None
