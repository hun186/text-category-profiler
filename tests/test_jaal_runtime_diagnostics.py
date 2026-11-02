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

    def test_missing_app_contract_fails_without_port(self):
        output, error = io.StringIO(), io.StringIO()
        result = probe.diagnose(build_app=lambda *_: object(),
                                output=output, error=error)
        self.assertEqual(result, 2)
        self.assertIn("mounted Dash app", error.getvalue())


if __name__ == "__main__":
    unittest.main()
