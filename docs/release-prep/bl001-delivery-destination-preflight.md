# BL-001: completed destination preflight before delivery backup

A known collision at Processed/<work-id> previously failed the final exclusive
move only after backup and optional dataset cleanup had already run.
Use read-only lstat before any backup or cleanup, rejecting existing directories,
files and dangling links and propagating unexpected inspection failures.
Keep the original move-error reporter nonmasking contract.

The preflight is not a reservation: a late competitor can still appear after
the check. The final exclusive no-replace move remains authoritative, and
backup/move are not one atomic transaction. No automatic rollback or retry.

Private temporary fixtures exercise early/late collisions and preserve both
job directories. No production data, model or real ownership changes.
