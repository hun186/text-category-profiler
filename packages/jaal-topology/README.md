# Jaal Topology Viewer

A self-contained Python package for visualizing **directed node relationships**:
one or more relationship CSV files, plus optional node display metadata CSV.
This package has no import from `BertScript`, `ClassesTree`, `TCFMain`, model
training, or WorkPool. It **never writes** either source CSV.

## Install and use in another Python project

Copy **only** the `packages/jaal-topology/` directory into your new repository.
With Python 3.10+ and an environment compatible with `jaal`/`dash`/`visdcc`:

```sh
python -m pip install -e ./jaal-topology
jaal-topology --edges ./relationships.csv --metadata ./labels.csv --root Root
```

Alternatively, without modifying global PATH:

```sh
python -m jaal_topology --edges ./relationships.csv --root Root -p 8059
```

The package bundles MIT-licensed Bootstrap 5.3.1 stylesheet and Jaal
browser assets for offline styling; no second backend is needed.
The server listens **only** on `127.0.0.1` (no public bind); visit
`http://127.0.0.1:8059/`. Run `jaal-topology --help` for options.

### Relationships (required)

```csv
parent,child
Root,Branch A
Root,Branch B
Branch A,Leaf
Branch B,Leaf
```

Or omit the header and use the first two fields as `from,to`.
Alternative headers: `from,to`, `source,target`, `母類別,子類別`.
Additional columns are ignored. BOM UTF-8, CSV quoting and multiple
`--edges` inputs are supported; IDs are literal strings, deduplicated edges
retain direction. Multiple parents, cross-links, cycles and disconnected
components are permitted. No conversion into a strict tree is attempted.

### Optional metadata

```csv
ClassLabel,CT,Explanation,Notes
Root,根類別,,
Branch A,分支甲,,
```

Only `ClassLabel` (identity) and `CT` (display name) are required. Missing
rows or blank `CT` fall back to English/original IDs. For custom schemas:

```sh
jaal-topology --edges links.csv --metadata names.csv \
  --metadata-id-column node_id --metadata-label-column display_name
```

The web UI provides a live, **off-by-default** Chinese label checkbox;
English IDs remain authoritative in Search and node tooltips. It also retains
the original Jaal Search/Filter/Color/Size controls plus **four**
layout modes (network/hierarchy, fully shown/structurally collapsed),
click-to-expand/collapse and the existing smooth hierarchy expansion animation.
Changing display labels never rewrites graph data.

### Size / safety

A selected view defaults to **250 nodes and 5,000 edges**, bounded to
3,000 / 5,000 respectively.
A root that is a leaf with **zero visible edges** is rejected with a helpful
message instead of creating dummy relations: upstream Jaal's Filter UI needs
at least one actual edge to initialize. Select a parent/ancestor as the root. A full graph larger than the node cap is rejected
with instructions to choose `--root`; there is no automatic full-graph
render on import. Source parsing itself rejects more than 100,000 distinct
edges. CSVs remain read-only. The renderer imports heavy dependencies only
on `build_app()`, not `import jaal_topology`.

## Known difference from the Stage 4 customized Jaal viewer

This standalone package now bundles the complete four-mode visdcc browser
engine used by Stage 4, including structural collapse, smooth 460 ms hierarchy
reflow, and reduced-motion behavior. Its own runtime and CLI require no
TextClassification project files. The project-specific same-port iframe mount,
root-search dropdown, Jaal auto-height and advanced panel/sidebar styling still
belong to Stage 4; they are **not yet shared host adapters**. The original
Stage 4 now serves the two browser-runtime scripts from this portable package
as its single source, while preserving the original same-port Jaal UI. Windows
browser visual acceptance and cross-project version compatibility remain open.

Do not delete or redirect the existing Stage 4 Jaal integration based on this
first package. Windows browser visual acceptance, packaging on a clean
external project, version compatibility across Dash 2/3/4, publishing
permissions/licensing, and public deployment security are separate gates.

## Embed on the same port as an existing Flask / Dash app

The pure-Python WSGI adapter does not create a second listening socket:

```python
from flask import Flask
from jaal_topology import load_graph, select_subgraph
from jaal_topology.integration import mount_flask

app = Flask(__name__)
graph = select_subgraph(load_graph("relationships.csv", "metadata.csv"),
                        "Root")
viewer = mount_flask(app, graph, mount_path="/topology", root="Root")
# Embed <iframe src="/topology/"></iframe> inside the host page if desired.
app.run(host="127.0.0.1", port=8059)
```

Call `mount_flask` before the host starts serving requests. All Dash
callback, stylesheet and browser-runtime URLs are prefixed `/topology/`.
The host root, other routes and controls remain intact. No automatic graph
reload: rebuild the selected view by restarting or constructing another
bounded app. This is a same-origin embedded app, not a live cross-origin
embedding or a public Internet deployment service.

## Standalone repository export

`packages/jaal-topology/` includes its own `pyproject.toml`, `LICENSE`,
`THIRD_PARTY_NOTICES.md`, `examples/`, `tests/`, and
`.github/workflows/ci.yml`. When moving this directory to a new
repository root, install and check it without importing the original
text-category-profiler project. For the verified GitHub Actions ZIP export,
integrity check, GitHub Desktop publish process, and ownership caveats,
see [REPOSITORY_SETUP.md](REPOSITORY_SETUP.md):

```sh
python -m pip install -e .
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/*.test.cjs
jaal-topology --edges examples/relationships.csv --metadata examples/metadata.csv --root Root
```

The contained workflow verifies this clean-root configuration. The parent
project's `Jaal Standalone GitHub Repository Export` workflow also verifies
and attaches a GitHub-ready ZIP with SHA-256 checksums. Do not
publish a release until PR review, root-project CI and external browser
acceptance all pass; publishing to PyPI, Docker or a public web server are
separate security/release decisions.
