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
