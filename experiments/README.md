# Experiments

This directory contains standalone research prototypes, benchmarks, and exploratory scripts that are not part of the production `text_category_profiler` application package.

## Boundaries

- Code here is not a supported application import surface.
- Scripts may have heavyweight optional dependencies, process/thread side effects, local pauses, or benchmark-style module execution.
- Moving a prototype here does not promote it to a regression test; stable behavior should be covered under `tests/` before it becomes a maintained contract.
- Production code must not depend on modules in this directory.

## Residual package-root batch 1

The first BL-001 residual cleanup moved these prototypes out of `text_category_profiler/` without rewriting their behavior:

- `concurrency/df_mpTest.py`
- `concurrency/df_mpTest_ThreadPoolExecutor.py`
- `concurrency/df_mpTest_wrapper.py`
- `concurrency/mp_test.py`
- `output_prototypes/WTFOutputer_test.py`

They are retained for historical/research value while the remaining package-root residual inventory is classified.

## Residual package-root batch 2 — timestamp corpus generator

- Authoritative implementation: `experiments/timestamp_generator.py` (former `text_category_profiler/Timestamp generator.py`). This manually invoked experiment generates timestamp-text samples under the **caller's current working directory** (`RandomTimeGeneration/` and `total.txt`), not the module directory. Running it has potentially large file and locale side effects; do not execute during ordinary tests.
- Legacy direct-script command `python "text_category_profiler/Timestamp generator.py"` remains supported by a **thin delegation wrapper**. Normal import of either file no longer generates files or modifies the process locale. Run `python experiments/timestamp_generator.py` for new manual usage.
- The wrapper can be removed only after external callers have been checked and the old command retired explicitly. The rest of the package-root residual inventory remains open.
- Targeted regression: `python -m unittest tests.test_timestamp_experiment_boundary`, which uses bounded in-memory generation and checks the old CLI dispatch without producing actual data files.
