"""Fixed SQLite output contract for the two Stage-local dfToSQL entrypoints.

Unlike the configurable canonical data.df_utils.dfToSQL, the legacy stage
writers always replace the sampleSrc table and create text_Index. The original
stage copies also leaked connections. Close via finally after the same database
operations, without introducing schema adapters, JSON conversion or fallback.
"""


def write_stage_sql(sql_name, df, saving_columns, connect):
    """Write legacy sampleSrc and text_Index, closing the connection on exit.

    `connect` is supplied by each stage's sqlite3 alias to preserve existing
    injection and environment-specific connection behavior. No actual
    database, pandas, WorkPool, or external service is loaded on import.
    """
    if len(saving_columns) == 0:
        saving_columns = df.columns.values

    # This index requires an actual "text" column.  Some SQLite builds treat
    # a double-quoted missing identifier as a string expression, so the old
    # CREATE INDEX statement can appear successful after to_sql has already
    # replaced the table.  Reject unsafe output *before opening/writing* DB.
    if "text" not in saving_columns:
        raise ValueError("Stage-local sampleSrc output requires a 'text' column")

    cnx = connect(sql_name)
    try:
        selected = df.loc[:, saving_columns]
        selected.to_sql(name="sampleSrc", con=cnx, if_exists="replace")
        cnx.execute('CREATE INDEX "text_Index" ON "sampleSrc"("text");')
    finally:
        cnx.close()
