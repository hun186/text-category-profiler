# Chinese similarity research fixtures

Historical files relocated byte-for-byte from the package root.
No source text, workbook contents, formulas, or filenames were rewritten.
See `experiments/fixtures/bl001_residual_inventory.json` for each original
path, Git blob SHA-1, size and the new `relocated_path`.

The two TXT documents are the active inputs of
`text_category_profiler/text/similarity_utils.py::InnerCrossSimilarityForTextListTest`.
This manual routine now reads them from this fixture folder relative to its own
source path, rather than relying on the operator working directory.

The two historical XLSX files are **frozen previous outputs**, not active
output destinations. The manual routine still writes generated Excel files by
their original relative basenames into the invoking working directory. Never
run the manual research routine inside this fixture folder.

Original upstream provenance, redistribution permissions and any external,
dynamically constructed, or untracked manual callers remain unverified.
BL-001 stays In Progress.
