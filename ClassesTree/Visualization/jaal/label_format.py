"""Pure display-only formatter for the embedded original Jaal graph.

Keep node IDs untouched: layout labels are allowed to be shortened and broken
into multiple visible lines but must never become taxonomy identities.
"""
from textwrap import wrap

MAX_LABEL_LINE_CHARS = 17
MAX_LABEL_LINES = 3


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
