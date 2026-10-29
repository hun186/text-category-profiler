# Historical RAG and similarity research samples

These are research fixtures, **not** runtime application package data.

| Path | Original package path | Git blob SHA-1 | Bytes |
| --- | --- | --- | --- |
| `RAGTest.json` | `text_category_profiler/RAGTest.json` | `4df2b417d2f19720218edc1d52ff9e847a385389` | 10156 |
| `Similarity.tsv` | `text_category_profiler/Similarity.tsv` | `9fe2e4ad6660e64a2f3befd7011735340865b345` | 34615 |

Both blobs are reused without parsing, rewriting, transcoding, or regeneration.

**Historical format caveat:** `RAGTest.json` contains two back-to-back JSON
arrays (9 and 5 records), not a single valid JSON document. A single
`json.loads()` / `JsonHandler.load()` call fails with `Extra data`. To consume
this historical fixture, explicitly use an incremental JSON decoder and keep
the arrays separate; do not silently alter the original Git blob.
The filenames and data are historical; their external source provenance and
redistribution licenses were **not** established in this migration.

The only known repository mention of `RAGTest.json` in application code is a
commented-out manual example in `text_category_profiler/core/utilities.py`;
it now documents the new fixture path and warns against single-document parsing. This is **not** a
guarantee that every dynamic/external/manual caller has been inspected.
A local script that hardcodes the former location needs an explicit update.
No Windows symlink, implicit fallback, or compatibility duplicate is added.

The direct-run Louvain example in
`text_category_profiler/visualization/Graph_utils.py` previously opened the
bare filename `Similarity.tsv` from the process working directory. It now
resolves the unchanged fixture from the repository root using `__file__`.
The existing `load_graph(path)` public behavior remains unchanged; lightweight
tests characterize 59 graph nodes but do **not** run Louvain clustering.

The separate Chinese-named similarity test documents still used by the manual
`InnerCrossSimilarityForTextListTest()` cwd-relative `open(FN)` remain at
their original locations. Do not conflate them with `Similarity.tsv`.
BL-001 remains In Progress.
