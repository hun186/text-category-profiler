# Stage 4 Tulip visualization module boundary

The original **24,232-byte** graph source has been preserved at
`text_category_profiler/visualization/tulip_graph_builder.py` with exactly the old Git blob SHA-1
`8d6919e56381e30003c7582ecb78f0490f04c857`, including its historical trailing spaces.
The scoped `.gitattributes` exception only exempts this one original
source from trailing-whitespace checks; all new code retains normal checks.

The source has a **real Stage 4 consumer**:
`BertScript/Test_result_Vis.py` imports `BuildGraph` and
`ClusterMetaNodeGraph` for visualization/clustering. It is therefore a
visualization-domain integration, **not** a standalone experiments fixture.

The historical import path
`text_category_profiler/tulip_utils/Graph_Builder.py`
is retained as a lazy compatibility facade. Explicit named lookup and
`main()` delegation work without importing optional modules during mere
facade import. **Actual graph calculations still require Tulip**, and
actual GUI interactions also depend on TulipGUI where used.

External/manual callers, previously imported module globals, wildcard
imports, and data provenance/licensing for embedded examples are **unverified**.
The isolated migration tests do not invoke a real Tulip GUI, ES, models, or
WorkPool. Do not interpret those tests as production Stage 4 graph acceptance.
