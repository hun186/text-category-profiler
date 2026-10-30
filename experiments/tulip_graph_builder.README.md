# Historical Tulip graph visualization research script

The original 24,232-byte `text_category_profiler/tulip_utils/Graph_Builder.py`
has been moved to `experiments/tulip_graph_builder.py` **byte for byte**,
using original Git blob `8d6919e56381e30003c7582ecb78f0490f04c857`. It contains a manual graph-building
experiment using optional `tulip` / `tulipgui` dependencies and a
direct-script example with `os.system("pause")`. It is **not** a required
classifier or Dash stage.

The former module path
`text_category_profiler/tulip_utils/Graph_Builder.py` is now a small,
import-safe facade: public named function access loads the original module
lazily, and its explicit `main()` delegates to the preserved original demo.
This keeps the known function names and module attribute access, not a
claim of full equivalence for introspection or `from ... import *` of
historically imported globals.

**External/manual callers remain unverified**; in particular legacy user
scripts may assume a working directory, Tulip GUI session, private module
attributes or import side effects. This move does not verify those contracts.
No live Tulip GUI, model, ES, WorkPool or large NLP flow was run.

The source contains historical research examples; origin, permissions for
embedded research text, and data provenance are **unverified**. The source
has not been rewritten. Do not treat this move as clearance to redistribute
third-party texts.
