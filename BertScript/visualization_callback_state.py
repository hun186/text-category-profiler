"""Stage 4 DataTable callback state and remount-loop policy.

Dependency-free pure guards: no Dash, model, SQLite, WorkPool, or browser
runtime. GUI callbacks provide observed events, never trigger real IO here.
"""


def is_spurious_datatable_filter_notification(
        triggered, *, filter_query, sort_by, derived_query_structure,
        previous_derived_query_structure):
    """Ignore only the empty derived-filter event from remounting a DataTable.

    Dash reinitializes derived_filter_query_structure to None when the parent
    callback replaces the table component. Without this guard that event
    re-exports the same filtered dataset and starts a chart/table redraw loop.
    Other user inputs (including clearing a real filter or sort) must proceed.
    """
    if len(triggered or ()) != 1:
        return False
    event = triggered[0]
    return (
        event.get("prop_id") == "VisDatatable.derived_filter_query_structure"
        and event.get("value") is None
        and derived_query_structure is None
        and previous_derived_query_structure is None
        and not (filter_query or "")
        and not (sort_by or [])
    )


def datatable_filter_state(filter_query, sort_by, derived_query_structure,
                           previous=None):
    """A revisioned snapshot of one *completed* filter/sort calculation.

    The revision is incremented even when the legacy filtered-data store is
    only the constant '{}' SQLite sentinel; this guarantees one downstream
    chart/table refresh for a real new request without going via page_current.
    """
    previous = previous if isinstance(previous, dict) else {}
    return {
        "filter_query": filter_query or "",
        "sort_by": sort_by or [],
        "derived_filter_query_structure": derived_query_structure,
        "revision": int(previous.get("revision", 0)) + 1,
    }


def is_redundant_table_filter_event(triggered, *, filter_query,
                                    sort_by, derived_query_structure,
                                    previously_applied):
    """Prevent a re-mounted DataTable from replaying an identical filter.

    Only table-property events qualify. Real changes to filter/sort, or any
    Colortable/keyword/slider event, must still update filtered results.
    """
    if not isinstance(previously_applied, dict) or not previously_applied:
        return False
    if not triggered or not all(
            str(event.get("prop_id", "")).startswith("VisDatatable.")
            for event in triggered):
        return False
    return (
        previously_applied.get("filter_query") == (filter_query or "")
        and previously_applied.get("sort_by") == (sort_by or [])
        and previously_applied.get("derived_filter_query_structure")
        == derived_query_structure
    )


def is_redundant_table_page_event(triggered, *, page_current,
                                   last_rendered):
    """Ignore the same page_current emitted when table_update remounts itself."""
    return (
        isinstance(last_rendered, dict)
        and len(triggered or []) == 1
        and triggered[0].get("prop_id") == "VisDatatable.page_current"
        and last_rendered.get("page_current") == page_current
    )
