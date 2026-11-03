"""Pure display-only formatter for the embedded original Jaal graph.

Keep node IDs untouched: layout labels are allowed to be shortened and broken
into multiple visible lines but must never become taxonomy identities.
"""
from textwrap import wrap

MAX_LABEL_LINE_CHARS = 17
MAX_LABEL_LINES = 3
# Bump when changing browser-visible label formatting so users can distinguish
# an already-running Python server from the checked-out Git revision.
LABEL_RENDERER_REVISION = "canvas-multiline-v4"


def wrapped_classlabel(name: str) -> str:
    """Explicit vis.js newlines: render at most 3 lines of about 17 chars.

    widthConstraint alone is not a reliable observable wrapping contract in
    the dot-node/Jaal/visdcc path. Longer names are ellipsized in the *label*
    only; full identifiers remain in id and the hover title.
    """
    if not isinstance(name, str):
        raise TypeError("ClassLabel must be text")
    if len(name) <= MAX_LABEL_LINE_CHARS:
        return name
    lines = wrap(
        name, width=MAX_LABEL_LINE_CHARS,
        max_lines=MAX_LABEL_LINES, placeholder="…",
        break_long_words=True, break_on_hyphens=True,
        replace_whitespace=True, drop_whitespace=True,
    )
    return "\n".join(lines) if lines else name


def search_full_classlabel(graph_data, search_text):
    """Jaal search callback with original ClassLabel semantics.

    Jaal upstream searches displayed node['label']. Embedded labels now have
    newlines and optional ellipses, so search the unchanged node['id'] instead.
    Keep Jaal's existing per-node hidden flag behaviour; no other data changes.
    """
    needle = (search_text or "").lower()
    for node in graph_data["nodes"]:
        node["hidden"] = needle not in str(node["id"]).lower()
    return graph_data


def prepare_embedded_jaal_nodes(node_df):
    """Production and tests share one node-label conversion boundary.

    Never mutate the caller DataFrame. Jaal.parse_dataframe preserves these
    explicit label/title columns and uses the stable ID for topology.
    """
    if "id" not in node_df.columns:
        raise ValueError("Embedded Jaal nodes require an id column")
    nodes = node_df.copy()
    nodes["label"] = nodes["id"].map(wrapped_classlabel)
    from html import escape as _escape_html
    nodes["title"] = nodes["id"].map(
        lambda name: _escape_html(str(name), quote=True)
    )
    return nodes


def enable_embedded_jaal_global_node_shapes(jaal_instance):
    """Remove only Jaal's embedded per-node dot override for mode-specific boxes.

    vis-network gives per-node 'shape' precedence over options.nodes.shape.
    Upstream parse_dataframe hardcodes 'shape': 'dot'; hierarchy could
    therefore never draw a space-reserving box without this adapter.
    """
    for collection in (jaal_instance.data, jaal_instance.filtered_data):
        if not isinstance(collection, dict) or not isinstance(collection.get("nodes"), list):
            raise RuntimeError("Original Jaal node payload contract changed")
        for node in collection["nodes"]:
            if "shape" in node:
                if node["shape"] != "dot":
                    raise RuntimeError("Original Jaal unexpected per-node shape")
                del node["shape"]
            # Validate the legacy shape contract before reading the ID.
            # Upstream visdcc injects string tooltip titles into innerHTML.
            from html import escape as _escape_html
            node["title"] = _escape_html(str(node["id"]), quote=True)
    return jaal_instance


def expose_embedded_jaal_text_color_choices(jaal_app, graph_data, limit=20):
    """Restore bounded original Jaal Color options with modern pandas strings.

    Jaal 0.1.9 selects only columns whose dtype is exactly object. Pandas 3
    may infer its new str dtype from the parsed node/edge records and silently
    remove those fields from both Color selectors. Work only on the embedded
    Dash layout (not a global Jaal monkeypatch, or the underlying graph).
    """
    if not isinstance(graph_data, dict):
        raise ValueError("Embedded Jaal graph must be a dictionary")

    def choices(rows, forbidden):
        if not isinstance(rows, list) or not rows:
            return []
        first = rows[0]
        if not isinstance(first, dict):
            raise ValueError("Embedded Jaal rows must be dictionaries")
        result = []
        for field in first:
            if field in forbidden:
                continue
            values = [row.get(field) for row in rows]
            if not all(isinstance(value, str) for value in values):
                continue
            if 0 < len(set(values)) <= limit:
                result.append(field)
        return result

    fields = {
        "color_nodes": choices(
            graph_data.get("nodes"),
            {"id", "label", "title", "shape", "image", "color"},
        ),
        "color_edges": choices(
            graph_data.get("edges"),
            {"id", "label", "title", "from", "to", "color"},
        ),
    }
    found = set()

    def visit(component):
        if isinstance(component, (tuple, list)):
            for child in component:
                visit(child)
            return
        if component is None or isinstance(component, (str, int, float)):
            return
        key = getattr(component, "id", None)
        if key in fields:
            found.add(key)
            current = list(getattr(component, "options", ()) or ())
            existing = {option.get("value") for option in current}
            for field in fields[key]:
                if field not in existing:
                    current.append({"label": field, "value": field})
            component.options = current
        visit(getattr(component, "children", None))

    visit(jaal_app.layout)
    if found != set(fields):
        raise RuntimeError("Embedded original Jaal Color selectors changed")
    return jaal_app
