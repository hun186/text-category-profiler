"""Shared Excel export policy for the two historically identical stage providers.

This is deliberately separate from data.df_utils.dfToXLS, which has a richer
ExcelWriter, overflow and fallback policy. Preserve the legacy fixed call,
including the `encoding` keyword that newer pandas may reject; compatibility
changes require a separate, independently characterized migration.
"""


def write_stage_xlsx(df, output_filename, *, excelindex=True):
    """Apply the pre-existing stage-local XLSX options once, without fallback."""
    df.to_excel(
        output_filename, engine="xlsxwriter", index=excelindex,
        encoding="utf-8",
    )
