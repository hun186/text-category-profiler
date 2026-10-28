"""Compatibility imports for the interactive CLI option selectors.

Canonical implementation: text_category_profiler.cli.selector. The original
classes and colorama color names are re-exported without changing behavior.
Import does not request terminal input or initialize curses.
"""
from text_category_profiler.cli.selector import (
    Back,
    Fore,
    Style,
    OptionSelector,
    MultiOptionSelector,
    InteractiveOptionSelector,
)

__all__ = (
    "Fore", "Back", "Style",
    "OptionSelector", "MultiOptionSelector", "InteractiveOptionSelector",
)
