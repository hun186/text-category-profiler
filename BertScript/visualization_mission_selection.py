"""Pure Stage 4 MissionTable-to-Colortable selection mapping.

This preserves legacy Topics literal parsing, duplicate labels, and selected
row order without importing Dash, pandas, WorkPool, SQLite or model code.
"""
import ast


def mission_colortable_rows(derived_virtual_selected_rows, mission_data, colortable_data):
    """Return selected ColorTable positions for the currently visible missions.

    None differs from an empty index list in the Dash caller's event model but
    both yield no selected ColorTable positions. Parse errors propagate as in
    the original callback. Duplicate Topic labels intentionally repeat matches.
    """
    selected_labels = []
    if derived_virtual_selected_rows is None:
        return []
    for row_index in derived_virtual_selected_rows:
        selected_labels.extend(ast.literal_eval(mission_data[row_index]["Topics"]))
    selected_labels = sorted(selected_labels)
    rows = []
    for label in selected_labels:
        for index, color_item in enumerate(colortable_data):
            if color_item["Label"] == label:
                rows.append(index)
    return rows
