# BL-001 — WorkPool metadata-only inventory (NOT deployment acceptance)

This tool is deliberately different from the **detached-copy SQLite** checks. It can observe the WorkPool directory while the application is running, but **only** enumerates bounded filesystem metadata (directory entry names, types, timestamps and file lengths). It never reads database pages, textual data, predictions, weights, or record contents; it does not open SQLite connections, alter permissions, acquire tasks, or create checkpoints.

On a Windows machine, from a locally updated checkout:

```bat
git pull --ff-only origin main
run-bl001-workpool-readonly-inventory.bat --workpool "D:\shared\AIProjects\text-category-profiler\WorkPool"
```

On Linux:

```sh
python -m scripts.bl001_workpool_readonly_inventory --workpool /path/to/WorkPool
```

Supply the actual WorkPool root **explicitly**. Its final path component must end with `WorkPool` (case insensitive). If a path component is a symbolic link / Windows reparse point, the tool refuses it; choose the canonical local location and do not bypass this guard by running a different audit on a live database.

### Interpretation

- `OBSERVED_METADATA_ONLY` (exit 0): bounded directory enumeration completed without detecting the selected warning signals. **It does not certify that writers are stopped, SQLite is healthy, backups work, or deployment is ready.**
- `REVIEW_REQUIRED` (exit 1): the scan detected running workspace names, SQLite WAL/SHM/journal sidecars, or untraversed symlink/reparse entries. These are observation signals, **not proof of corruption**. Never delete a stage candidate, sidecar or running workspace based on its name.
- `UNVERIFIABLE` (exit 2): root/path unsafe, not accessible, scan interrupted, or entry budget exhausted. Resolve the observation boundary; no deployment verdict is possible.

The report provides counts, not individual job names or document text. The default scan is limited to 10,000 entries and depth 3. On **Linux/POSIX**, the directory walk is bound to no-follow directory file descriptors. On **Windows**, to avoid any path-replacement/junction race, only the **top-level WorkPool directory** is enumerated through a verified native Win32 directory handle; nested SQLite files and sidecars are **not scanned**. The report explicitly sets `windows_root_only=true`, `nested_files_examined=false` and `sqlite_sidecar_scan_complete=false`; do not interpret a count of 0 as proof there are no nested sidecars. `directories_not_descended` indicates directories below the scan limit (or, on Windows, all child directories). Directory timestamps can reveal some concurrent changes on POSIX but **cannot** establish an atomic or quiescent snapshot. Reports always carry `production_workpool_verified=false`, `deployment_authorized=false`, and `candidate_deletion_authorized=false`.

### Running-name age distribution (metadata, not process status)

When `workspace_running` is nonzero, the report now includes
`workspace_running_dir_lastwrite_age` with the following mutually exclusive
**top-level directory LastWriteTime / mtime** buckets:

- `under_1h`: directory last-write timestamp within the preceding hour
- `from_1h_to_24h`: at least 1 hour and less than 24 hours old
- `from_1d_to_7d`: at least 24 hours and less than 7 days old
- `at_least_7d`: at least 7 days old
- `unknown_or_future`: unavailable, invalid or future timestamp

Their counts must sum to `workspace_running` on a complete scan.
On Windows the values come from the already-open WorkPool root handle's
directory entries; Linux uses the existing no-follow directory-fd scan.
No job names, file contents, processes or nested directories are inspected
to calculate these buckets. This is **not** a task-heartbeat or activity
detector. Writing to an existing SQLite database or log file need not update
the parent directory's last-write time; an old directory timestamp **does
not mean a job is dead**, and a recent timestamp **does not prove it is
alive**. The buckets only help prioritize an operator's subsequent,
separately authorized task-state investigation; they **never permit cleanup,
renaming or resumption**.

### Next gate — independent detached SQLite copy

For SQLite integrity and schema checks, stop writers and prepare a verified **independent copy outside WorkPool** using the site's approved backup process. Existing `run-bl001-sqlite-offline-health.bat --db <copy>` and the stage dependency/inventory scripts are for those offline copies only; do **not** run them directly on a live WorkPool file. Keep production write-enable and automated deletion disabled until a separately authorized, documented production acceptance plan has passed.
