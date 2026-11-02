"""Dependency-free Jaal construction-probe and error-path tests."""
import io
import unittest
from types import SimpleNamespace
from unittest import mock

from BertScript import jaal_runtime_diagnostics as probe


class JaalRuntimeDiagnosticsTests(unittest.TestCase):
    def test_success_is_readonly_does_not_start_server(self):
        mock_builder = mock.Mock(return_value=SimpleNamespace(
            callback_map={"original.data": object()},
            server=object(),
        ))
        output, error = io.StringIO(), io.StringIO()
        code = probe.diagnose("TW Affairs", build_app=mock_builder,
                              output=output, error=error)
        self.assertEqual(code, 0)
        mock_builder.assert_called_once_with(
            "TW Affairs", "/jaal-original/diagnose/"
        )
        self.assertIn("JAAL_DIAGNOSE_PASS", output.getvalue())
        self.assertEqual(error.getvalue(), "")

    def test_attribute_error_traceback_is_printed_in_console_only(self):
        builder = mock.Mock(side_effect=AttributeError(
            "'Jaal' object has no attribute 'missing_marker'"
        ))
        output, error = io.StringIO(), io.StringIO()
        code = probe.diagnose("TW Affairs", build_app=builder,
                              output=output, error=error)
        self.assertEqual(code, 2)
        self.assertIn("JAAL_DIAGNOSE_FAILED", error.getvalue())
        self.assertIn("Traceback (most recent call last)",
                      error.getvalue())
        self.assertIn("missing_marker", error.getvalue())
        self.assertNotIn("missing_marker", output.getvalue())

    def test_dash3_dash4_with_older_visdcc_fails_before_jaal_import(self):
        for dash_version in ("3.0.0", "4.5.0"):
            with self.subTest(dash=dash_version):
                with self.assertRaisesRegex(
                    RuntimeError, "JAAL_VISDCC_DASH_INCOMPATIBLE"
                ) as caught:
                    probe.check_dash_visdcc_compatibility({
                        "dash": dash_version, "visdcc": "0.0.50"
                    })
                self.assertIn("component_loader", str(caught.exception))
                self.assertIn("visdcc==0.0.63", str(caught.exception))

    def test_modern_and_legacy_pairs_are_not_blocked(self):
        for versions in (
            {"dash": "4.5.0", "visdcc": "0.0.63"},
            {"dash": "3.2.0", "visdcc": "0.0.63"},
            {"dash": "2.18.2", "visdcc": "0.0.50"},
        ):
            with self.subTest(versions=versions):
                self.assertIsNone(
                    probe.check_dash_visdcc_compatibility(versions)
                )
        with self.assertRaisesRegex(RuntimeError, "requires Dash >=3"):
            probe.check_dash_visdcc_compatibility({
                "dash": "2.18.2", "visdcc": "0.0.63"
            })

    def test_missing_packages_are_reported_by_actual_import(self):
        self.assertIsNone(probe.check_dash_visdcc_compatibility({
            "dash": "(not installed)", "visdcc": "0.0.63",
        }))

    def test_missing_app_contract_fails_without_port(self):
        output, error = io.StringIO(), io.StringIO()
        result = probe.diagnose(build_app=lambda *_: object(),
                                output=output, error=error)
        self.assertEqual(result, 2)
        self.assertIn("mounted Dash app", error.getvalue())


if __name__ == "__main__":
    unittest.main()
