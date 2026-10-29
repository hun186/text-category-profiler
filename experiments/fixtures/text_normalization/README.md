# Historical punctuation comparison samples

These two TXT files were relocated **byte-for-byte**, without changing
their Chinese punctuation, encoding or names, from
`text_category_profiler/` into this research fixture folder.

The authoritative original Git blob hashes, original paths, sizes and
`relocated_path` values are preserved in
`experiments/fixtures/bl001_residual_inventory.json` (schema v4).
`testFix.txt` contains the fullwidth Chinese comma used by the existing
characterization test; `testFix - 複製.txt` does not.

The bounded static scanner found no direct first-party Python filename
references at the time of relocation. This is **not** evidence that
dynamically computed filenames, external scripts, manually invoked users
or deployment snapshots never use the old package-root paths.
Any external/manual caller must explicitly update its source path.

The upstream provenance, reuse rights, and historical research purpose
have not been independently verified. No model execution or dataset
transformation was performed. BL-001 remains In Progress.
