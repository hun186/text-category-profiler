"""Bounded, non-production BL-001 Stage-local export compatibility check.

Run from repository root with `python -m scripts.bl001_stage_writer_check`.
The existing tests write only to private temporary files or in-memory SQLite;
this command neither opens a production WorkPool nor invokes classifiers.
"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from importlib import import_module
import sys
import unittest


REQUIRED_PACKAGES = ("pandas", "xlsxwriter")
FOCUSED_TEST_MODULES = (
    "tests.test_bl001_stage_tsv_shared",
    "tests.test_bl001_stage_xlsx_shared",
    "tests.test_bl001_stage_sql_shared",
    "tests.test_bl001_df_tsv_provider_contracts",
)


def run_focused_tests():
    """Fail if any test fails, is skipped, or the selection runs no tests."""
    suite = unittest.defaultTestLoader.loadTestsFromNames(FOCUSED_TEST_MODULES)
    expected = suite.countTestCases()
    if expected == 0:
        return False
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return (
        result.wasSuccessful()
        and result.testsRun == expected
        and not result.skipped
    )



def verify_real_tsv_export():
    """Require an actual private TSV export; exception matching is not enough.

    The legacy characterization allows an old pandas failure to remain equal
    to its baseline, so it cannot by itself certify successful TSV output.
    """
    import pandas as pd
    from text_category_profiler.data.stage_tsv import write_stage_tsv

    frame = pd.DataFrame({"ClassLabel": ["TW Affairs"], "text": ["中文分類"]})
    with TemporaryDirectory(prefix="bl001-writer-check-") as folder:
        output = Path(folder) / "stage.tsv"
        write_stage_tsv(frame, output)
        if output.read_text(encoding="utf-8").splitlines() != ["TW Affairs\t中文分類"]:
            raise ValueError("Stage-local TSV bytes did not match expected rows")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run focused, non-production Stage-local TSV/XLSX/SQLite checks."
    )
    parser.parse_args(argv)
    for name in REQUIRED_PACKAGES:
        try:
            package = import_module(name)
        except ImportError as exc:
            print(f"Missing or broken required dependency: {name}: {exc}", file=sys.stderr)
            print("STATUS=BLOCKED_DEPENDENCY", file=sys.stderr)
            return 2
        print(f"{name}={getattr(package, '__version__', 'unknown')}")

    passed = run_focused_tests()
    try:
        verify_real_tsv_export()
    except Exception as exc:
        print(f"Real private TSV export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        passed = False
    print("STATUS=PASS_FOCUSED" if passed else "STATUS=FAIL_FOCUSED")
    print("Scope: private tempfile/in-memory export checks only; NOT Windows/WorkPool/model acceptance.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
