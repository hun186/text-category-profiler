"""Stage 4 DataTable pagination policy, independent of Dash and pandas.

The function preserves the legacy page-size-change reset, empty-data page 0,
and post-filter clamping. It performs no filesystem or browser operations.
"""


def select_table_page(row_count, page_size, page_current, button_id):
    """Return the page to render after a filter or page-size event."""
    if button_id in ["Page Size Bar"]:
        page_current = 0
    page_max = max((row_count - 1) // page_size, 0)
    return min(max(page_current or 0, 0), page_max)
