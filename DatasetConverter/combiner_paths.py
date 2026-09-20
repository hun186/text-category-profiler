from pathlib import Path, PureWindowsPath


def resolve_repository_path(configured_path, repository_root):
    """Resolve a combiner runtime path without changing the process cwd."""
    configured_path = str(configured_path)
    if Path(configured_path).is_absolute() or PureWindowsPath(configured_path).is_absolute():
        return configured_path
    return str(Path(repository_root) / configured_path)
