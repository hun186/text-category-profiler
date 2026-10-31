"""Characterize old DatasetConverter provider contracts without optional services."""
import ast
from contextlib import redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DATAFRAME = ROOT / "DatasetConverter" / "df_utils.py"
MP = ROOT / "DatasetConverter" / "old_MP_utils.py"
UTILITY = ROOT / "DatasetConverter" / "old_utilities.py"


def module_tree(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def definition(path, kind, name):
    matches = [
        node for node in module_tree(path).body
        if isinstance(node, kind) and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError("Expected one %s in %s" % (name, path))
    return matches[0]


class LegacyDataFrameProvidersTests(unittest.TestCase):
    def test_all_legacy_symbols_resolve_to_explicit_first_party_sources(self):
        tree = module_tree(DATAFRAME)
        imported = {
            n.module: {alias.name for alias in n.names}
            for n in tree.body if isinstance(n, ast.ImportFrom)
        }
        self.assertEqual(
            imported["DatasetConverter.old_MP_utils"],
            {"MPlogger", "multicoreJob"},
        )
        self.assertEqual(
            imported["DatasetConverter.old_utilities"],
            {"hash", "ShowElapsedTime"},
        )
        self.assertFalse({"MP_utils", "utilities"} & set(imported))
        self.assertTrue(all(
            not isinstance(n, (ast.Import, ast.ImportFrom))
            or not (
                (isinstance(n, ast.Import) and any(a.name in {"MP_utils", "utilities"} for a in n.names))
                or (isinstance(n, ast.ImportFrom) and n.module in {"MP_utils", "utilities"})
            )
            for n in ast.walk(tree)
        ))

    def test_legacy_logger_keeps_static_call_and_selected_output_path(self):
        clazz = definition(MP, ast.ClassDef, "MPlogger")
        logger = next(
            n for n in clazz.body
            if isinstance(n, ast.FunctionDef) and n.name == "logW"
        )
        self.assertEqual(logger.args.args[0].arg, "MES")
        scope = {"os": os, "timeNow": lambda FMT: "2000-01-01 00:00:00"}
        exec(compile(ast.Module(body=[clazz], type_ignores=[]), str(MP), "exec"), scope)
        with tempfile.TemporaryDirectory() as folder:
            log_path = Path(folder) / "legacy.csv"
            scope["MPlogger"].logW("legacy-dataframe", logFile=str(log_path))
            result = log_path.read_text(encoding="utf-8")
        self.assertEqual(
            result, "2000-01-01 00:00:00,PID %s: legacy-dataframe\n" % os.getpid()
        )
        df_tree = module_tree(DATAFRAME)
        calls = [
            node for node in ast.walk(df_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "MPlogger"
            and node.func.attr == "logW"
        ]
        self.assertEqual(len(calls), 7)

    def test_legacy_hash_accepts_text_and_bytes_and_legacy_none(self):
        fn = definition(UTILITY, ast.FunctionDef, "hash")
        scope = {"hashlib": hashlib}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(UTILITY), "exec"), scope)
        self.assertEqual(
            scope["hash"](b"sample", "sha1"),
            hashlib.sha1(b"sample").hexdigest(),
        )
        self.assertEqual(
            scope["hash"]("sample"),
            hashlib.sha512(b"sample").hexdigest(),
        )
        self.assertIsNone(scope["hash"](None))

    def test_legacy_elapsed_time_output_remains_unchanged(self):
        fn = definition(UTILITY, ast.FunctionDef, "ShowElapsedTime")
        class Clock:
            @staticmethod
            def time():
                return 15.25

        scope = {"time": Clock}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(UTILITY), "exec"), scope)
        captured = io.StringIO()
        with redirect_stdout(captured):
            scope["ShowElapsedTime"](10)
        self.assertEqual(captured.getvalue(), "It has been passed for 5.2500 seconds\n")

    def test_multicore_helper_remains_legacy_not_new_signature(self):
        clazz = definition(MP, ast.ClassDef, "multicoreJob")
        constructor = next(
            n for n in clazz.body
            if isinstance(n, ast.FunctionDef) and n.name == "__init__"
        )
        self.assertEqual(
            [arg.arg for arg in constructor.args.args],
            ["self", "DTBJobs", "method", "MulticoreMode", "nProcess"],
        )


if __name__ == "__main__":
    unittest.main()
