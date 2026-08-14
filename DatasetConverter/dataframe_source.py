"""Feature-activated constructors for DataConverter pandas operations."""


def dataframe_from_dict(data, *, orient="columns", columns=None):
    """Build a DataFrame while preserving the pandas constructor contract."""
    import pandas as pd

    return pd.DataFrame.from_dict(data, orient=orient, columns=columns)


def empty_dataframe():
    """Return an empty pandas DataFrame when a conversion path needs one."""
    import pandas as pd

    return pd.DataFrame()


def concat_dataframes(frames, *, ignore_index=False):
    """Concatenate DataFrames with the configured index policy."""
    import pandas as pd

    return pd.concat(frames, ignore_index=ignore_index)
