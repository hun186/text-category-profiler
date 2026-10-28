# dijkstra-algorithm
This is a simple Python 3 implementation of the Dijkstra algorithm which returns the shortest path between two nodes in a directed graph. It only uses the Python standard library, and should work with any Python 3.x version. I've tested it with Python 3.4 and Python 3.7.

For a walkthrough of how it works, see the blog post [Dijkstra's Algorithm](https://www.dougmahugh.com/dijkstra/).

## Compatibility relocation note (2026-10-28)

This repository now keeps the authoritative, **unchanged MIT-licensed**
Dijkstra example in `vendor/dijkstra_algorithm_master/`. This original
folder retains the old Python import/entrypoint, graph input fixtures and
LICENSE for callers that have not migrated. The Python file here is a thin
adapter; its direct-run behavior and graph data filenames remain relative
to the invoking working directory. See `vendor/README.md` for scope.
