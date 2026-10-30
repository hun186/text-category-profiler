# Historical similarity TXT inputs

All 15 historical TXT research documents have been relocated without
regeneration or re-encoding from
`text_category_profiler/切片相似度比對法測試/test Document/` to
`experiments/fixtures/similarity_experiment_inputs/test Document/`.

The complete original path, original Git blob SHA-1, byte size, and destination
of each item are stored in
`experiments/fixtures/bl001_similarity_experiment_inventory.json` schema v3.
These TXT documents are frozen historical research inputs, not production data.

The commented manual examples in `text_category_profiler/text/similarity_utils.py`
now use the relocated folder independently of the invoking cwd. The two active
Chinese samples remain under `experiments/fixtures/chinese_similarity/`.
The generated XLSX result names remain caller-cwd relative and do not overwrite
archived XLSX workbooks.

Original provenance, licensing and redistribution rights are **unverified**,
including third-party article and document sources suggested by the filenames.
External, dynamic, non-Python, or manual callers of old relative paths are not
verified. No silent fallback/symlink is supplied; migrate such callers manually.
No model/Elasticsearch/WorkPool or similarity computation ran for this move.
