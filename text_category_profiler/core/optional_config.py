"""Helpers for loading optional, site-local configuration modules."""

import importlib
import importlib.util


def load_optional_module(module_name):
    """Return an optional module, or ``None`` when it is not installed.

    A missing optional module is a normal configuration state.  Errors raised
    while importing a module that *does* exist are intentionally not hidden.
    """
    if importlib.util.find_spec(module_name) is None:
        return None

    return importlib.import_module(module_name)


def merge_module_mapping(target, module, attribute_name):
    """Merge one mapping attribute from a previously loaded module.

    ``target`` is the destination dictionary; it is never treated as a module.
    Passing ``None`` as ``module`` makes this a no-op and returns ``False``.
    """
    if module is None:
        return False

    target.update(getattr(module, attribute_name))
    return True
