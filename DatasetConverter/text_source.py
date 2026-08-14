"""Feature-activated adapters for the legacy text-processing utilities."""


def read_text(*, file, encoding="utf-8", n_bytes=None, logger=None):
    """Read a text source with the legacy reader and argument contract."""
    from text_category_profiler.text.TextProcessor_utils import textReader

    return textReader(
        file=file,
        encoding=encoding,
        nBytes=n_bytes,
        MPLOGGER=logger,
    ).run()


def normalize_basic_text(text, *, convert_full_width=True, dummy_space=True):
    """Apply the legacy basic normalization policy to ``text``."""
    from text_category_profiler.text.TextProcessor_utils import BasicDataCleaner

    return BasicDataCleaner(
        strQ2B=convert_full_width,
        DummySpace=dummy_space,
    ).proc(text)


def clean_text_with_patterns(text, rules, *, logger=None, print_on_screen=False):
    """Apply the legacy regex cleaning policy to ``text``."""
    from text_category_profiler.text.TextProcessor_utils import DataCleanerWithPattern

    return DataCleanerWithPattern(
        text,
        RePatternDict=rules,
        MPLOGGER=logger,
        printOnScreen=print_on_screen,
    ).proc()
