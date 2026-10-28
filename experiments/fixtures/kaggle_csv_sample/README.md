# Historical Kaggle CSV extraction sample

These are the **26 unchanged small text fixtures** formerly stored in the
application package root under `text_category_profiler/KaggleExtraction/`
(two CSV-like sample input copies) and `text_category_profiler/csvSample/`
(24 example emitted text files). They are manually maintained research/test
artifacts, not imported Python modules or canonical pipeline fixtures.

The original Git blob SHA-1 and size of each file is in `manifest.json`.
No sample content or output filename was normalized. The two CSV sample
inputs are identical by blob SHA; the 24 emitted output files consist of
four identical-content groups of six files each. The names and duplicates
are retained for investigation, not deduplicated.

**Path change:** the preserved relative subtrees now live inside
`experiments/fixtures/kaggle_csv_sample/`. E.g.
`text_category_profiler/KaggleExtraction/csvSample.txt` is now
`experiments/fixtures/kaggle_csv_sample/KaggleExtraction/csvSample.txt`.
Git history retains the original paths and copies. No legacy path alias or
Windows symlink is added; external manual scripts referencing those exact
old data paths have not been inventoried and must update their paths.
Repository code regression tests reject direct references to moved sample
names. The unrelated manual `KaggleExtraction/us/ads.json` reference in
`text_category_profiler/data/df_utils.py` is deliberately **not** part of
this input fixture; it remains unchanged.

This move does not prove a working live Kaggle extraction workflow, run
`df_utils.py`, modify corpus processing, or touch model/WorkPool files.
Verify using
`python -m unittest -v tests.test_kaggle_csv_fixture_boundary`.
