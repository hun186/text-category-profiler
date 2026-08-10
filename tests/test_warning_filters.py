import unittest
import warnings

from text_category_profiler.core.warning_filters import suppress_known_third_party_warnings


def _warn_as(module_name, message):
    namespace = {"__name__": module_name, "warnings": warnings}
    exec("warnings.warn(message, UserWarning)", namespace, {"message": message})


class WarningFilterTests(unittest.TestCase):
    def test_dash_bootstrap_legacy_warning_is_suppressed_even_with_newline(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            suppress_known_third_party_warnings()

            _warn_as(
                "dash_bootstrap_components._table",
                "\nThe dash_html_components package is deprecated.",
            )

        self.assertEqual(caught, [])

    def test_unrelated_user_warning_is_not_suppressed(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            suppress_known_third_party_warnings()

            _warn_as("application.worker", "keep this warning")

        self.assertEqual(len(caught), 1)
        self.assertEqual(str(caught[0].message), "keep this warning")


if __name__ == "__main__":
    unittest.main()
