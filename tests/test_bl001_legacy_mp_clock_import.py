"""No-service characterization of the legacy MP logger clock import."""
import ast
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "DatasetConverter" / "old_MP_utils.py"
OLD_CLOCK = ROOT / "DatasetConverter" / "old_utilities.py"
CANONICAL = ROOT / "text_category_profiler" / "concurrency" / "MP_utils.py"
PROVIDER = "text_category_profiler.concurrency.MP_utils"


def top_level_node(path, kind, name):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches = [
        n for n in tree.body if isinstance(n, kind) and n.name == name
    ]
    if len(matches) != 1:
        raise AssertionError("Expected one top-level %s in %s" % (name, path))
    return matches[0]


class LegacyMPClockImportTests(unittest.TestCase):
    def test_import_is_explicit_and_has_no_bare_fallback(self):
        tree = ast.parse(LEGACY.read_text(encoding="utf-8"))
        clock_imports = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom)
            and any(alias.name == "timeNow" for alias in n.names)
        ]
        self.assertEqual(len(clock_imports), 1)
        self.assertEqual(clock_imports[0].module, PROVIDER)
        self.assertEqual(clock_imports[0].level, 0)
        self.assertFalse(any(
            isinstance(n, ast.ImportFrom) and n.module == "utilities"
            for n in ast.walk(tree)
        ))

    def test_legacy_and_canonical_time_format_contract_match(self):
        previous = top_level_node(OLD_CLOCK, ast.FunctionDef, "timeNow")
        current = top_level_node(CANONICAL, ast.FunctionDef, "timeNow")
        self.assertEqual(
            ast.dump(previous, include_attributes=False),
            ast.dump(current, include_attributes=False),
        )
        class Clock:
            @staticmethod
            def localtime():
                return "fixed-local-clock"

            @staticmethod
            def strftime(fmt, value):
                return (fmt, value)

        scope = {"time": Clock}
        exec(compile(ast.Module(body=[current], type_ignores=[]), str(CANONICAL), "exec"), scope)
        self.assertEqual(scope["timeNow"](), ("%Y%m%d%H%M%S", "fixed-local-clock"))
        self.assertEqual(
            scope["timeNow"](FMT="%Y-%m-%d %H:%M:%S"),
            ("%Y-%m-%d %H:%M:%S", "fixed-local-clock"),
        )

    def test_canonical_failure_propagates_without_legacy_retry(self):
        tree = ast.parse(LEGACY.read_text(encoding="utf-8"))
        statement = next(
            n for n in tree.body
            if isinstance(n, ast.ImportFrom) and n.module == PROVIDER
            and any(alias.name == "timeNow" for alias in n.names)
        )
        attempts = []

        def fail_import(name, *args, **kwargs):
            attempts.append(name)
            raise ImportError("canonical clock provider unavailable")

        with patch("builtins.__import__", side_effect=fail_import):
            with self.assertRaisesRegex(ImportError, "canonical clock provider unavailable"):
                exec(compile(ast.Module(body=[statement], type_ignores=[]), str(LEGACY), "exec"), {})
        self.assertEqual(attempts, [PROVIDER])

    def test_both_legacy_logger_methods_keep_caller_selected_log_path(self):
        logger = top_level_node(LEGACY, ast.ClassDef, "MPlogger")
        multicore = top_level_node(LEGACY, ast.ClassDef, "multicoreJob")
        scope = {"os": os, "timeNow": lambda FMT: "fixed-time"}
        exec(compile(ast.Module(body=[logger, multicore], type_ignores=[]), str(LEGACY), "exec"), scope)
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "legacy.log"
            scope["MPlogger"].logW("first", logFile=str(log))
            scope["multicoreJob"].logW("second", logFile=str(log))
            lines = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, [
            "fixed-time,PID %s: first" % os.getpid(),
            "fixed-time,PID %s: second" % os.getpid(),
        ])


if __name__ == "__main__":
    unittest.main()
