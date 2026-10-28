"""Characterize the isolated timestamp experiment and its legacy entrypoint."""

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments" / "timestamp_generator.py"
LEGACY = ROOT / "text_category_profiler" / "Timestamp generator.py"


class TimestampExperimentBoundaryTests(unittest.TestCase):
    def test_importing_script_or_legacy_entrypoint_has_no_output_side_effects(self):
        for target in (EXPERIMENT, LEGACY):
            with self.subTest(path=target.name), tempfile.TemporaryDirectory() as temp:
                old_cwd = Path.cwd()
                try:
                    os.chdir(temp)
                    with mock.patch("locale.setlocale", side_effect=AssertionError(
                        "Import must not change process locale"
                    )), redirect_stdout(io.StringIO()) as stdout:
                        namespace = runpy.run_path(str(target))
                    self.assertEqual(list(Path(temp).iterdir()), [])
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertIn("main", namespace)
                finally:
                    os.chdir(old_cwd)

    def test_explicit_experiment_main_still_generates_timestamp_samples(self):
        import locale

        namespace = runpy.run_path(str(EXPERIMENT))
        main = namespace["main"]
        emitted = mock.Mock()
        # Keep the original generation algorithm, but bound only its 5000
        # experiment iterations. Avoid unsupported OS locales and disk writes.
        main.__globals__["range"] = lambda count: range(min(count, 3))
        main.__globals__["timeToFile"] = emitted
        with mock.patch.object(locale, "setlocale", return_value="C"), redirect_stdout(io.StringIO()) as stdout:
            main()

        self.assertGreaterEqual(emitted.call_count, 3)
        for call in emitted.call_args_list:
            self.assertIn("date_time", call.kwargs)
            self.assertIn("fmt", call.kwargs)
        self.assertIn("共生成", stdout.getvalue())

    def test_legacy_direct_run_routes_to_experiment_without_changing_cwd(self):
        legacy_namespace = runpy.run_path(str(LEGACY))
        runner = legacy_namespace["main"]
        before = Path.cwd()
        with mock.patch("runpy.run_path") as dispatch:
            runner()
        dispatch.assert_called_once_with(str(EXPERIMENT), run_name="__main__")
        self.assertEqual(Path.cwd(), before)


if __name__ == "__main__":
    unittest.main()
