"""Atomic Stage-local SQLite sampleSrc writer shared by DatasetConverter/BertScript.

pandas.to_sql on native sqlite3 commits internally, so wrapping its direct
sampleSrc replacement in BEGIN does not make CREATE INDEX atomic. Stage into a
unique candidate table first, then reconstruct sampleSrc, copy staged rows and build indexes inside one
SQLite transaction. Avoid ALTER TABLE RENAME because dependent views may break. Neither caller signature nor the final pandas table/index contract
changes. A killed writer before COMMIT leaves the prior sampleSrc and indexes.
A kill during candidate creation may leave a uniquely named orphan candidate;
never remove another process's candidates automatically.
"""


def _quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def _pandas_candidate_indexes(cnx, candidate):
    """Describe only simple pandas-generated indexes, without reading rows."""
    prefix = "ix_" + candidate + "_"
    columns = {
        entry[1] for entry in cnx.execute(
            "PRAGMA table_info(" + _quote_identifier(candidate) + ")"
        )
    }
    mappings = []
    for entry in cnx.execute(
        "PRAGMA index_list(" + _quote_identifier(candidate) + ")"
    ):
        index_name, unique, origin, partial = entry[1], entry[2], entry[3], entry[4]
        if (not index_name.startswith(prefix) or unique
                or origin != "c" or partial):
            raise ValueError("Unsupported pandas candidate index: " + index_name)
        keys = [
            part for part in cnx.execute(
                "PRAGMA index_xinfo(" + _quote_identifier(index_name) + ")"
            ) if part[5] == 1
        ]
        if (not keys or any(
            part[1] < 0 or part[2] not in columns
            or part[3] != 0 or part[4] != "BINARY"
            for part in keys
        )):
            raise ValueError("Unsupported pandas candidate index keys: " + index_name)
        mappings.append((
            index_name,
            "ix_sampleSrc_" + index_name[len(prefix):],
            tuple(part[2] for part in keys),
        ))
    return mappings


def _guard_existing_stage_indexes(cnx):
    """Reject index/constraint definitions that a DROP/CREATE would discard.

    Pandas Stage-local indexes are ix_sampleSrc_*, plus plain text_Index.
    An unrecognized or altered index may encode a business constraint;
    never silently replace it with a weaker schema. Schema metadata only.
    """
    entries = list(cnx.execute('PRAGMA index_list("sampleSrc")'))
    columns = {item[1] for item in cnx.execute('PRAGMA table_info("sampleSrc")')}
    for entry in entries:
        name, unique, origin, partial = entry[1:5]
        if (unique != 0 or origin != "c" or partial != 0
                or (name != "text_Index"
                    and not name.startswith("ix_sampleSrc_"))):
            raise ValueError("Unsafe existing sampleSrc index: " + name)
        keys = [
            key for key in cnx.execute(
                "PRAGMA index_xinfo(" + _quote_identifier(name) + ")"
            ) if key[5] == 1
        ]
        if (not keys or any(key[1] < 0 or key[2] not in columns
                            or key[3] != 0 or key[4] != "BINARY"
                            for key in keys)
                or (name == "text_Index"
                    and (len(keys) != 1 or keys[0][2] != "text"))):
            raise ValueError("Unsafe existing sampleSrc index keys: " + name)


def _guard_replace_dependencies(cnx):
    """Fail closed under BEGIN IMMEDIATE before DROP can erase dependencies.

    SQLite DROP TABLE can cascade into other tables when foreign_keys=ON.
    It also drops triggers defined ON the replaced table. Preserve those
    objects by refusing replacement rather than silently deleting them.
    Only sqlite_master/PRAGMA metadata is inspected; no user rows are read.
    """
    # Materialize and finish sqlite_master cursor before any rejection.
    # Otherwise an active schema cursor can block DROP of our own staged
    # candidate during failure cleanup on the SAME SQLite connection.
    metadata = list(cnx.execute(
        "SELECT type, name, tbl_name FROM sqlite_master "
        "WHERE type IN ('table', 'trigger')"
    ))
    for kind, name, owner in metadata:
        if kind == "trigger" and owner.casefold() == "samplesrc":
            raise ValueError("Unsafe sampleSrc trigger dependency: " + name)
        if kind != "table" or name.casefold() == "samplesrc":
            continue
        for foreign_key in list(cnx.execute(
            "PRAGMA foreign_key_list(" + _quote_identifier(name) + ")"
        )):
            if foreign_key[2].casefold() == "samplesrc":
                raise ValueError(
                    "Unsafe sampleSrc inbound foreign-key dependency: " + name
                )
    _guard_existing_stage_indexes(cnx)


def write_stage_sql(sql_name, df, saving_columns, connect):
    """Replace sampleSrc and its pandas/text indexes as one SQLite commit.

    The caller-provided sqlite3.connect function is retained. Unknown
    candidate indexes fail closed rather than changing persisted schema.
    """
    if len(saving_columns) == 0:
        saving_columns = df.columns.values
    if "text" not in saving_columns:
        raise ValueError("Stage-local sampleSrc output requires a 'text' column")

    import uuid

    candidate = "__bl001_stage_" + uuid.uuid4().hex
    cnx = connect(sql_name)
    transaction_started = False
    try:
        selected = df.loc[:, saving_columns]
        # pandas commits its own sqlite3 transaction. Do not touch sampleSrc
        # here: partial candidate writes must never replace the prior output.
        selected.to_sql(name=candidate, con=cnx, if_exists="fail")
        pandas_indexes = _pandas_candidate_indexes(cnx, candidate)
        schema = cnx.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (candidate,),
        ).fetchone()
        expected_prefix = "CREATE TABLE " + _quote_identifier(candidate)
        if (not schema or not schema[0].startswith(expected_prefix)
                or schema[0][len(expected_prefix):len(expected_prefix) + 1]
                not in (" ", "(")):
            raise ValueError("Unsupported pandas candidate CREATE TABLE schema")
        final_table_ddl = 'CREATE TABLE "sampleSrc"' + schema[0][len(expected_prefix):]

        # SQLite DDL and INSERT are transactional. Copying inside the final
        # transaction (instead of ALTER TABLE RENAME) preserves dependent views
        # that still refer to the name sampleSrc across the replacement.
        cnx.execute("BEGIN IMMEDIATE")
        transaction_started = True
        _guard_replace_dependencies(cnx)
        cnx.execute('DROP TABLE IF EXISTS "sampleSrc"')
        cnx.execute(final_table_ddl)
        cnx.execute(
            'INSERT INTO "sampleSrc" SELECT * FROM ' + _quote_identifier(candidate)
        )
        for _, final_name, columns in pandas_indexes:
            cnx.execute(
                "CREATE INDEX " + _quote_identifier(final_name)
                + ' ON "sampleSrc" ('
                + ", ".join(_quote_identifier(column) for column in columns) + ")"
            )
        cnx.execute('CREATE INDEX "text_Index" ON "sampleSrc"("text");')
        cnx.execute("DROP TABLE " + _quote_identifier(candidate))
        cnx.commit()
        transaction_started = False
    except BaseException:
        if transaction_started:
            try:
                cnx.rollback()
            except Exception:
                pass
        # This connection owns only this randomly named candidate. A killed
        # process may leave orphan candidates; do not guess whether any other
        # candidate table belongs to a still-running worker.
        try:
            cnx.execute(
                "DROP TABLE IF EXISTS " + _quote_identifier(candidate)
            )
            cnx.commit()
        except Exception:
            pass
        raise
    finally:
        cnx.close()
