"""Fail-closed CLI tests for the optional BL-001 local writer preflight."""

from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import patch

from scripts import bl001_stage_writer_check as check


class StageWriterCheckTests(unittest.TestCase):
    def test_focused_selection_is_bounded_to_three_existing_writer_modules(self):
        self.assertEqual(check.FOCUSED_TEST_MODULES, (
            "tests.test_bl001_stage_tsv_shared",
            "tests.test_bl001_stage_xlsx_shared",
            "tests.test_bl001_stage_sql_shared",
        ))

    def test_missing_dependency_blocks_without_running_suite(self):
        output = io.StringIO()
        with patch.object(check, "import_module", side_effect=ImportError("missing")), \
                patch.object(check, "run_focused_tests") as run, \
                redirect_stderr(output):
            self.assertEqual(check.main([]), 2)
        run.assert_not_called()
        self.assertIn("STATUS=BLOCKED_DEPENDENCY", output.getvalue())

    def test_success_requires_nonempty_suite(self):
        with patch.object(check.unittest.defaultTestLoader, "loadTestsFromNames",
                          return_value=unittest.TestSuite()):
            self.assertFalse(check.run_focused_tests())

    def test_skipped_tests_cannot_claim_focused_pass(self):
        class Skipped(unittest.TestCase):
            @unittest.skip("missing native integration")
            def test_skipped(self):
                raise AssertionError("should not execute")

        suite = unittest.TestSuite([Skipped("test_skipped")])
        with patch.object(check.unittest.defaultTestLoader, "loadTestsFromNames",
                          return_value=suite), redirect_stderr(io.StringIO()):
            self.assertFalse(check.run_focused_tests())

    def test_green_result_and_exit_code_are_narrowly_labeled(self):
        stream = io.StringIO()
        with patch.object(check, "import_module") as load, \
                patch.object(check, "run_focused_tests", return_value=True), \
                redirect_stdout(stream):
            load.return_value.__version__ = "test-version"
            self.assertEqual(check.main([]), 0)
        self.assertIn("STATUS=PASS_FOCUSED", stream.getvalue())
        self.assertIn("NOT Windows/WorkPool/model acceptance", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
