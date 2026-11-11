"""Shared Excel export policy for the two historically identical stage providers.

Keep the original xlsxwriter/index policy while supporting both pandas versions
that accept `to_excel(encoding=...)` and newer versions that removed it.
The canonical data.df_utils.dfToXLS has different semantics and stays separate.
"""
from inspect import Parameter, signature


def write_stage_xlsx(df, output_filename, *, excelindex=True):
    """Write once with the stage-local formatting contract; never retry a failure."""
    to_excel = df.to_excel
    try:
        parameters = signature(to_excel).parameters
    except (TypeError, ValueError):
        # Preserve the old call when a custom frame cannot be inspected.
        # Retrying on TypeError is unsafe: an export may already have started.
        parameters = None

    options = {"engine": "xlsxwriter", "index": excelindex}
    if parameters is None or "encoding" in parameters or any(
        value.kind is Parameter.VAR_KEYWORD for value in parameters.values()
    ):
        options["encoding"] = "utf-8"
    to_excel(output_filename, **options)
