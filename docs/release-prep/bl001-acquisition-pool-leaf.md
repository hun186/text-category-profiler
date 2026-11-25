# BL-001: selected WorkPool input leaf preflight

A matching name in two directory listings is not proof that the selected
WorkPool input is a real directory. Before creating Processing or moving
Incoming, the manager checks the selected pool leaf through the filesystem
port. Missing, file-like, symlink and Windows reparse-point leaves fail with
`WORKITEM_ACQUISITION_POOL_NOT_REAL_DIRECTORY`. Automatic mode stops on
an invalid selected newest match instead of silently claiming an older job.

The preflight is read-only, does not inspect descendants or assert dataset
readiness, does not establish ownership or eliminate TOCTOU races, and
does not change the exclusive move. No retry, cleanup or repair is authorized.

Private temporary-directory tests cover regular files, stale listings,
symlinks, Windows junctions and successful claims. Hosted CI does not prove
production WorkPool, network filesystem or GPU acceptance.
