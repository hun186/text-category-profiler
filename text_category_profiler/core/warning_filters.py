"""Narrow warning filters for known third-party compatibility shims."""

import warnings


def suppress_known_third_party_warnings():
    """Hide warnings that application code cannot fix at the call site.

    Keep these filters module-scoped rather than message-scoped: some older
    dash-bootstrap-components versions prefix the warning text with a newline,
    while the module that emits it remains stable.
    """
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        module=r"^dash_bootstrap_components\._table$",
    )
