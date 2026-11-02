# Portable Jaal Topology Viewer (first standalone package)

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
the original Jaal Search/Filter/Color/Size controls and adds network vs.
four layout modes (network/hierarchy, fully shown/structurally collapsed),
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
belong to Stage 4; they are **not yet shared host adapters**, and the original
Stage 4 assets have not yet been switched to the package as their runtime
source. Cross-project parity and Windows visual acceptance remain open.

Do not delete or redirect the existing Stage 4 Jaal integration based on this
first package. Windows browser visual acceptance, packaging on a clean
external project, version compatibility across Dash 2/3/4, publishing
permissions/licensing, and public deployment security are separate gates.
