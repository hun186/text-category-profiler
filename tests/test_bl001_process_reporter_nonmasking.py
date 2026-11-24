"""Root failure-reporting faults cannot erase the actual child exit."""
import types
import unittest
from unittest import mock

from text_category_profiler.execution.process import (
    RootFailFastPolicy, child_exit_interpretation,
)


class RootReporterFailStopTests(unittest.TestCase):
    def test_broken_reporter_preserves_original_exit_code(self):
        failing_log = RuntimeError("logging unavailable")
        reporter = mock.Mock(side_effect=failing_log)
        policy = RootFailFastPolicy(failure_reporter=reporter)
        with self.assertRaises(RuntimeError) as result:
            policy.check(types.SimpleNamespace(returncode=37),
                         "Classifier", "python classifier.py")
        self.assertIn("Classifier failed with exit code 37",
                      str(result.exception))
        self.assertNotIn("logging unavailable", str(result.exception))
        reporter.assert_called_once_with(
            "Classifier", 37, "python classifier.py",
        )

    def test_signal_like_exit_remains_unconfirmed_when_reporter_fails(self):
        for code in (130, -2, -1073741510, 3221225786):
            with self.subTest(code=code):
                policy = RootFailFastPolicy(
                    failure_reporter=mock.Mock(side_effect=OSError("disk full"))
                )
                with self.assertRaises(RuntimeError) as result:
                    policy.check(types.SimpleNamespace(returncode=code),
                                 "TestResultVis", "python visual.py")
                self.assertIn(f"exit code {code}", str(result.exception))
                self.assertIn("operator interruption UNCONFIRMED",
                              str(result.exception))
                self.assertIn("no WorkPool cleanup or automatic resume",
                              str(result.exception))

    def test_good_reporter_retains_original_arguments_and_failure(self):
        reported = []
        policy = RootFailFastPolicy(
            failure_reporter=lambda *args: reported.append(args)
        )
        with self.assertRaises(RuntimeError):
            policy.check(types.SimpleNamespace(returncode=1),
                         "DataConverter", "private command placeholder")
        self.assertEqual(reported, [
            ("DataConverter", 1, "private command placeholder")
        ])

    def test_success_never_calls_reporter(self):
        reporter = mock.Mock(side_effect=AssertionError(
            "success must not call reporter"
        ))
        result = types.SimpleNamespace(returncode=0)
        policy = RootFailFastPolicy(failure_reporter=reporter)
        self.assertIs(policy.check(result, "Classifier", "python good.py"),
                      result)
        reporter.assert_not_called()

    def test_second_ctrl_c_remains_operator_interrupt(self):
        reporter = mock.Mock(side_effect=KeyboardInterrupt("operator"))
        with self.assertRaises(KeyboardInterrupt):
            RootFailFastPolicy(failure_reporter=reporter).check(
                types.SimpleNamespace(returncode=1),
                "Classifier", "python fail.py",
            )
        reporter.assert_called_once()


if __name__ == "__main__":
    unittest.main()
