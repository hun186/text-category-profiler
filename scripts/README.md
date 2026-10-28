# Maintenance scripts

These commands are manually invoked tools, separate from the production
`text_category_profiler` package and the classifier pipeline.

## Elasticsearch TXT ingestion (BL-001)

- Authoritative implementation: `scripts/ES_ingest_txt_to_es.py`.
- Legacy CLI path: `text_category_profiler/ES_ingest_txt_to_es.py` (delegates to the same implementation).
- Options `-i/--index`, `-d/--dir`, `--host`, `--batch`, `--lang`, `--user`,
  `--op` and `--dedup-by-content` retain their established defaults and meaning.
- Example read-only help: `python scripts/ES_ingest_txt_to_es.py --help`.
- **Do not run ingestion as a smoke test**: ordinary execution connects to
  Elasticsearch and can create an index or write/overwrite documents. Use an
  explicitly selected test cluster and reviewed inputs before invoking it.
- Importing the script or old wrapper does not import the Elasticsearch client,
  connect to a cluster, or enumerate the file tree; bulk insertion loads the
  optional Elasticsearch integration on demand.
- Dependency-light regression:
  `python -m unittest -v tests.test_es_ingest_script_boundary` (temporary files,
  faked Elasticsearch client, no actual service).
- Existing Python helper API is exposed by the old module through lazy delegation.
  Do not remove the wrapper until external import/CLI callers have been surveyed.
