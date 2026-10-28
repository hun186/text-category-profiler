# Modified CPython 3.7.17 `zipfile.py` — GBK filename compatibility

## Provenance

This is the repository's historical `text_category_profiler/Edited_zipfile.py`
moved here **without changing a byte**. A line-by-line comparison against
[`python/cpython` release `v3.7.17`, `Lib/zipfile.py`](https://github.com/python/cpython/blob/v3.7.17/Lib/zipfile.py)
found the original 2,178 lines in the same order, with **only two insertions
of four lines each** (total eight added lines). This is an attribution and
comparison to the tagged source; the original modifier and original
change date remain unknown.

The original upstream is part of CPython, licensed under the Python Software
Foundation license and its incorporated historical notices. An unmodified
copy of the release's `LICENSE` is included alongside the copied source.
This is **not** MIT-licensed simply because another vendored module is.

## Recorded local changes

The two additions occur after decoding a ZIP member filename as CP437 when
the ZIP UTF-8 bit is **not** set:

- central-directory filename processing: try to encode the CP437 string back
  as CP437 and decode the bytes as GBK; on any error, keep the CP437 result.
- local-file-header filename processing: apply the same GBK-first/fallback
  decoding so the archive's two names continue to agree during `open()`.

Files that explicitly set the UTF-8 flag still use the original UTF-8 path.
The historical broad `except:` and permissive fallback are preserved
verbatim; this relocation intentionally does not improve decoding policy,
zip-bomb handling, extraction policy or Python-version compatibility.

## Integration boundary

The active algorithm lives at `vendor/cpython37_zipfile_gbk/zipfile.py`.
The old `text_category_profiler/Edited_zipfile.py` remains an import-safe
compatibility facade for public `zipfile` symbols and direct CLI operation.
Production code should prefer Python's maintained `zipfile` module unless
the specific legacy GBK behavior is explicitly required.

Do not remove the old facade until external callers are surveyed. Validate
the legacy decoder on read-only temporary fixtures using
`python -m unittest -v tests.test_edited_zipfile_vendor_boundary`.
CI does not process external or untrusted ZIP archives.
