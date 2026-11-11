"""Shared legacy TSV writer for the two stage-local DataFrame providers.

DatasetConverter.df_utils.dfToTSV and BertScript.df_utils.dfToTSV
historically have identical, fixed write semantics. Keep those existing
two-argument APIs while owning the format policy here. The separate,
configurable data.df_utils.dfToTSV performs a multicore resource probe;
do NOT silently redirect it to this writer or vice versa.
"""
import csv


def write_stage_tsv(df, output_filename):
    """Write UTF-8 tab-separated values exactly as the two stage APIs did."""
    # With QUOTE_NONE there is no quoting at all. None is equivalent to the
    # legacy empty quotechar for old pandas, but unlike "" is accepted by
    # modern pandas/Python CSV writers. Do not retry failed writes.
    df.to_csv(
        output_filename, sep="\t", index=False,
        quoting=csv.QUOTE_NONE, quotechar=None, escapechar="\\",
        header=False, encoding="utf-8",
    )
