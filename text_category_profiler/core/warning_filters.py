"""Narrow warning filters for known third-party compatibility shims."""

import multiprocessing as mp
import warnings


def suppress_known_third_party_warnings_in_workers():
    """Hide known dependency warnings only in spawned worker processes.

    Keep these filters module-scoped rather than message-scoped: some older
    dash-bootstrap-components versions prefix the warning text with a newline,
    while the module that emits it remains stable.  The main process deliberately
    keeps the warning visible once so operators still see the compatibility issue.
    """
    if mp.current_process().name == "MainProcess":
        return False

    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        module=r"^dash_bootstrap_components\._table$",
    )
    return True
