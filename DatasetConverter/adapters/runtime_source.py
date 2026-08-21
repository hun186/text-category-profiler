"""Feature-activated adapters for the legacy conversion runtime.

The canonical module can be imported for configuration and test discovery
without loading numpy/pandas-backed helpers.  Actual conversion paths still
load and call the existing implementations when their features are used.
"""


def create_logger(*args, **kwargs):
    from text_category_profiler.concurrency.MP_utils import MPlogger

    return MPlogger(*args, **kwargs)


def create_multicore_job(*args, **kwargs):
    from text_category_profiler.concurrency.MP_utils import multicoreJob

    return multicoreJob(*args, **kwargs)


def create_dataframe_output(*args, **kwargs):
    from text_category_profiler.data.df_utils import dfOutputer

    return dfOutputer(*args, **kwargs)


def dataframe_from_rows(*args, **kwargs):
    from text_category_profiler.data.df_utils import DictRowsListToDF

    return DictRowsListToDF(*args, **kwargs)


def fetch_elasticsearch_data(*args, **kwargs):
    from text_category_profiler.data.DB_utils import getESData

    return getESData(*args, **kwargs)
