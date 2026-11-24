# BL-001 Stage 4 Callback State Ownership

`visualization_stage.py` is responsible for the Stage 4 lifecycle
(`ready → running → completed`), hosted-mode execution, and Dash
import diagnostic. Four pure callback-control helpers used by the Stage 4
DataTable were historically mixed into that lifecycle file:

- `is_spurious_datatable_filter_notification`
- `datatable_filter_state`
- `is_redundant_table_filter_event`
- `is_redundant_table_page_event`

The verbatim definitions now live in
`BertScript/visualization_callback_state.py`; they are **re-exported
with the same names and object identities** in `visualization_stage`.
No callback signatures, scheduling, filter semantics, revision policy,
DataTable event wiring, filesystem, or schema behavior are changed.

The new pure module imports no Dash, pandas, SQLite, model, WorkPool,
or native DLL runtime. Its isolated Win/Ubuntu regression verifies the
exported entrypoints, legacy remount protection, revision increments,
real user filter/sort/page changes and unchanged state input.

This is a structural boundary extraction, **not** validation that
KI-008 is resolved on real Windows Dash. Actual browser idle, 0/non-0
filters, sorting, pagination, and repeated SQLite writes still require
the separately documented real GUI UAT.
