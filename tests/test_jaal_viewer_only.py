"""Jaal GUI-only mode must never activate the Stage 4 WorkPool lifecycle."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class ViewerOnlyLauncherTests(unittest.TestCase):
    def test_parse_explicit_viewer_mode_and_loopback_port(self):
        from BertScript.jaal_viewer_only import parse_viewer_args

        self.assertEqual(parse_viewer_args(["--viewer-only"]).port, 8059)
        self.assertEqual(parse_viewer_args(["--viewer-only", "-p", "8077"]).port, 8077)
        for argv in (
            [], ["-p", "8059"], ["--viewer-only", "-p", "0"],
            ["--viewer-only", "-p", "65536"],
            ["--viewer-only", "--host", "0.0.0.0"],
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                parse_viewer_args(argv)

    def test_main_runs_local_jaal_only_without_workpool(self):
        from BertScript import jaal_viewer_only as viewer

        fake_app = mock.Mock()
        fake_app.run = mock.Mock()
        with mock.patch.object(viewer, "build_viewer_only_app", return_value=fake_app), \
                mock.patch("os.rename", side_effect=AssertionError("no WorkPool rename")), \
                mock.patch("os.replace", side_effect=AssertionError("no WorkPool replace")):
            self.assertEqual(viewer.main(["--viewer-only", "-p", "8077"]), 0)
        fake_app.run.assert_called_once_with(
            host="127.0.0.1", port=8077, debug=False, use_reloader=False
        )

    def test_entrypoint_fast_dispatch_precedes_heavy_analysis_imports(self):
        source = (ROOT / "BertScript" / "Test_result_Vis.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        fast_path = next(
            node for node in tree.body
            if isinstance(node, ast.If)
            and "viewer-only" in ast.unparse(node.test)
        )
        import_numpy = next(
            node for node in tree.body
            if isinstance(node, ast.Import)
            and any(alias.name == "numpy" for alias in node.names)
        )
        self.assertLess(fast_path.lineno, import_numpy.lineno)
        self.assertIn("viewer_only_main(sys.argv[1:])",
                      ast.get_source_segment(source, fast_path))

    def test_direct_stage4_help_bypasses_all_heavy_imports_and_workpool(self):
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(
                [sys.executable, str(ROOT / "BertScript" / "Test_result_Vis.py"),
                 "--viewer-only", "--help"],
                cwd=cwd, text=True, capture_output=True, timeout=20,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--viewer-only", result.stdout)
            self.assertIn("--port", result.stdout)
            self.assertNotIn("no BertDatasetSubDir", result.stdout)

    def test_real_local_app_has_lazy_jaal_card_and_no_analytical_stage(self):
        try:
            import dash  # noqa: F401
            import dash_bootstrap_components  # noqa: F401
            import jaal  # noqa: F401
        except ImportError as exc:
            self.skipTest(f"Optional Jaal GUI dependencies not installed: {exc}")

        from BertScript.jaal_viewer_only import build_viewer_only_app
        app = build_viewer_only_app()
        response = app.server.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        layout = app.server.test_client().get("/_dash-layout")
        self.assertEqual(layout.status_code, 200)
        data = layout.get_data(as_text=True)
        self.assertIn("Jaal 進階檢視器", data)
        self.assertIn("JaalOriginalFrame", data)
        self.assertNotIn('"type":"Iframe"', data)
        self.assertNotIn("VisDatatable", data)


if __name__ == "__main__":
    unittest.main()
