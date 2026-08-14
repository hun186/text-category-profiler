"""Logging adapter used by DatasetConverter readers.

Keep the multiprocessing utility dependency behind the feature boundary: readers
that receive a logger should not need to import the considerably heavier
``MP_utils`` module.
"""


def create_sample_reader_logger(*, log_file="sampleHandler.log"):
    """Create the legacy logger used when a reader has no injected logger."""
    from text_category_profiler.concurrency.MP_utils import MPlogger

    return MPlogger(logFile=log_file)
