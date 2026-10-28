# Vendored source boundaries

`dijkstra_algorithm_master/` contains the existing third-party Dijkstra
algorithm demonstration formerly held under
`text_category_profiler/dijkstra_algorithm_master/`.

The bundled README identifies a tutorial by Doug Mahugh, and its MIT license
attributes copyright (c) 2019 Doug Mahugh. Its Python implementation, graph
fixtures, LICENSE and original README are copied **unchanged** into this
directory. The original license notice must be retained with redistribution.

This is a learning/reference algorithm, **not** an application service or a
supported shared utility. Production code must not import or modify this
vendored implementation. The legacy Python path still exports `Graph`,
`INFINITY` and `verify_algorithm` through an import-safe adapter; running
the legacy script still runs the original four examples. Keep the small
legacy fixture files and license under the old location until external
manual callers are inventoried, then consider dropping that compatibility
location in a separately reviewed change.

No upstream update, dependency replacement or algorithm fix is included in
this relocation.

## CPython-derived ZIP support

`cpython37_zipfile_gbk/` is an **unmodified relocation** of the repository's
historical, patched CPython 3.7.17 `zipfile.py` copy. It retains the original
8-line CP437-to-GBK local patch, carries the actual upstream CPython `LICENSE`
(separate from the Dijkstra MIT license), and documents the precise differences
in its own README. The former module path remains an import-safe facade.
