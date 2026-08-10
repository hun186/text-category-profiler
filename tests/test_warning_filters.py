import unittest
import warnings
from unittest import mock

from text_category_profiler.core.warning_filters import suppress_known_third_party_warnings_in_workers


def _warn_as(module_name, message):
    namespace = {"__name__": module_name, "warnings": warnings}
    exec("warnings.warn(message, UserWarning)", namespace, {"message": message})


class WarningFilterTests(unittest.TestCase):
    @mock.patch("text_category_profiler.core.warning_filters.mp.current_process")
    def test_worker_suppresses_dash_warning_even_with_newline(self, current_process):
        current_process.return_value.name = "SpawnPoolWorker-1"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            filtered = suppress_known_third_party_warnings_in_workers()

            _warn_as(
                "dash_bootstrap_components._table",
                "\nThe dash_html_components package is deprecated.",
            )

        self.assertTrue(filtered)
        self.assertEqual(caught, [])

    @mock.patch("text_category_profiler.core.warning_filters.mp.current_process")
    def test_main_process_keeps_dash_warning_visible_once(self, current_process):
        current_process.return_value.name = "MainProcess"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            filtered = suppress_known_third_party_warnings_in_workers()

            _warn_as(
                "dash_bootstrap_components._table",
                "\nThe dash_html_components package is deprecated.",
            )

        self.assertFalse(filtered)
        self.assertEqual(len(caught), 1)

    @mock.patch("text_category_profiler.core.warning_filters.mp.current_process")
    def test_unrelated_user_warning_is_not_suppressed(self, current_process):
        current_process.return_value.name = "SpawnPoolWorker-1"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            suppress_known_third_party_warnings_in_workers()

            _warn_as("application.worker", "keep this warning")

        self.assertEqual(len(caught), 1)
        self.assertEqual(str(caught[0].message), "keep this warning")


if __name__ == "__main__":
    unittest.main()
