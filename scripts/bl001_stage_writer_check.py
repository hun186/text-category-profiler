"""Bounded, non-production BL-001 Stage-local export compatibility check.

Run from repository root with `python -m scripts.bl001_stage_writer_check`.
The existing tests write only to private temporary files or in-memory SQLite;
this command neither opens a production WorkPool nor invokes classifiers.
"""

import argparse
from importlib import import_module
import sys
import unittest


REQUIRED_PACKAGES = ("pandas", "xlsxwriter")
FOCUSED_TEST_MODULES = (
    "tests.test_bl001_stage_tsv_shared",
    "tests.test_bl001_stage_xlsx_shared",
    "tests.test_bl001_stage_sql_shared",
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
    print("STATUS=PASS_FOCUSED" if passed else "STATUS=FAIL_FOCUSED")
    print("Scope: private tempfile/in-memory export checks only; NOT Windows/WorkPool/model acceptance.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
