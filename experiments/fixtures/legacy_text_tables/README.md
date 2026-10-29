# Preserved legacy text tables (BL-001)

The three files in this directory were moved **without changing any bytes**
from the root of the `text_category_profiler/` application package.
They are historical, unclassified text-table artifacts. Original Git blob
SHA-1 values, byte sizes, and old/new paths are recorded in
`experiments/fixtures/bl001_residual_inventory.json` schema v5.

- `EmojiAlll.txt` — 36,516 bytes
- `特殊符號表.txt` — 27,063 bytes
- `total.txt` — 216,074 bytes

We have not verified their exact contents, provenance, use rights or
relationship to active application logic. The first-party tracked Python
**lexical** reference audit found no direct filename matches for these
three files as of relocation; this does **not** rule out external/manual
callers, computed paths, other languages or deployment snapshots.
Those integrations must explicitly update any old paths themselves.

`text_category_profiler/FTPTEST/abc.txt` remains in its original location
because a Python source filename reference was discovered; the standalone
TRV deployment snapshot is intentionally outside this relocation.
No models, classifiers, text-transform jobs or external services ran.
BL-001 remains In Progress.
