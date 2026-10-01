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
