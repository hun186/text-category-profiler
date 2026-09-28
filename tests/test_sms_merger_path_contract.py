import ast
import importlib
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "DatasetConverter" / "SMS" / "SMSMerger.py"
MODULE_NAME = "DatasetConverter.SMS.SMSMerger"


def _unexpected(name):
    def fail(*args, **kwargs):
        raise AssertionError("{} ran during module import".format(name))
    return fail


def _stub_modules(*, calls=None, class_table=None):
    calls = calls or {}
    df_utils = types.ModuleType("text_category_profiler.data.df_utils")
    for name in ("dfOutputer", "dfFromSQLite3", "CSVtodf"):
        setattr(df_utils, name, calls.get(name, _unexpected(name)))

    utilities = types.ModuleType("text_category_profiler.core.utilities")
    for name in ("getMFNFromFN", "removeStrPrefix", "ConvertTimeStrFMT"):
        setattr(utilities, name, calls.get(name, _unexpected(name)))

    provider = types.ModuleType("BertScript.ClassTable")
    provider.ClassTable = class_table if class_table is not None else {}
    return {
        df_utils.__name__: df_utils,
        utilities.__name__: utilities,
        provider.__name__: provider,
    }


def _import_with_stubs(*, calls=None, class_table=None):
    sys.modules.pop(MODULE_NAME, None)
    with mock.patch.dict(
        sys.modules,
        _stub_modules(calls=calls, class_table=class_table),
    ):
        return importlib.import_module(MODULE_NAME)


class SMSMergerPathContractTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop(MODULE_NAME, None)

    def test_source_contract_isolates_workflow_in_main(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(SCRIPT))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("PackageImport", imported)
        self.assertNotIn("PackageImporter.proc", source)
        self.assertNotIn("os.chdir", source)
        for path in ("D:/shared/PythonModule", "Z:/PythonModule", "../PythonModule"):
            self.assertNotIn(path, source)

        self.assertIn("Path(__file__).resolve().parents[2]", source)
        first_local_import = min(
            source.index("from text_category_profiler"),
            source.index("from BertScript.ClassTable import ClassTable"),
        )
        self.assertLess(source.index("sys.path.insert"), first_local_import)
        self.assertIn("BertScript.ClassTable", imported)
        self.assertNotIn("ClassTable", imported)

        main_guards = [
            node for node in tree.body
            if isinstance(node, ast.If)
            and ast.unparse(node.test) == "__name__ == '__main__'"
        ]
        self.assertEqual(len(main_guards), 2)
        path_inserts = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and ast.unparse(node.func) == "sys.path.insert"
        ]
        self.assertEqual(len(path_inserts), 1)
        self.assertIn(path_inserts[0], list(ast.walk(main_guards[0])))

        forbidden = {"os.path.isfile", "os.system", "dfFromSQLite3", "CSVtodf", "dfOutputer"}
        unguarded_calls = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If)):
                continue
            unguarded_calls.update(
                ast.unparse(child.func)
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
            )
        self.assertTrue(forbidden.isdisjoint(unguarded_calls), forbidden & unguarded_calls)

    def test_module_import_does_not_start_workflow_or_mutate_process_state(self):
        cwd = os.getcwd()
        path = list(sys.path)
        with mock.patch("os.path.isfile", side_effect=_unexpected("os.path.isfile")), \
                mock.patch("os.system", side_effect=_unexpected("os.system")):
            module = _import_with_stubs()
        self.assertEqual(os.getcwd(), cwd)
        self.assertEqual(sys.path, path)
        self.assertEqual(module.CPBatFN, "CPAntCSV.bat")
        self.assertFalse(hasattr(module, "df"))

    def test_direct_script_bootstrap_preserves_each_caller_cwd(self):
        probe = textwrap.dedent(
            """
            import builtins
            import os
            import runpy
            import sys

            repository_root, expected_cwd, script = sys.argv[1:]
            sys.path = [entry for entry in sys.path if entry != repository_root]
            original_import = builtins.__import__
            def checked_import(name, *args, **kwargs):
                if name in (
                    "text_category_profiler.data.df_utils",
                    "BertScript.ClassTable",
                ):
                    assert repository_root in sys.path, sys.path
                    assert os.getcwd() == expected_cwd, os.getcwd()
                    raise SystemExit(23)
                return original_import(name, *args, **kwargs)
            builtins.__import__ = checked_import
            runpy.run_path(script, run_name="__main__")
            raise AssertionError("repository-local import was not observed")
            """
        )
        callers = (
            REPOSITORY_ROOT,
            REPOSITORY_ROOT / "DatasetConverter",
            REPOSITORY_ROOT / "DatasetConverter" / "SMS",
        )
        for caller_cwd in callers:
            with self.subTest(caller_cwd=caller_cwd):
                result = subprocess.run(
                    [
                        sys.executable, "-c", probe, str(REPOSITORY_ROOT),
                        str(caller_cwd), str(SCRIPT),
                    ],
                    cwd=caller_cwd,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 23, result.stderr)

    def test_repository_class_table_is_the_explicit_provider(self):
        from BertScript.ClassTable import ClassTable

        self.assertIsInstance(ClassTable, dict)
        for key in ("Commerce", "Academic Research"):
            self.assertIn(key, ClassTable)
            self.assertIsInstance(ClassTable[key], dict)

    def test_main_preserves_relative_inputs_transformations_and_tsv_output(self):
        events = []
        output = {}
        sql_result = types.SimpleNamespace(
            text=pd.Series(["first", "second"]),
            pred_Type=pd.Series(["Fish", "Unmapped"]),
        )
        annotations = pd.DataFrame(
            [
                {
                    "SmsContent": "second", "ItcDate": "2024-03-02 08:00:00",
                    "Address1": "B", "Address2": "2", "SmsContentNo": None,
                    "標註類別": "Unmapped",
                },
                {
                    "SmsContent": "first", "ItcDate": "2024-03-01 08:00:00",
                    "Address1": "A", "Address2": "1", "SmsContentNo": "7",
                    "標註類別": "Fish",
                },
            ]
        )

        class Outputter:
            def __init__(self, dataframe, stem, **kwargs):
                events.append(("dfOutputer", stem, kwargs))
                output["dataframe"] = dataframe.copy()
            def run(self):
                events.append(("run",))

        calls = {
            "dfFromSQLite3": lambda path: events.append(("sql", path)) or sql_result,
            "CSVtodf": lambda **kwargs: events.append(("csv", kwargs)) or annotations.copy(),
            "getMFNFromFN": lambda path: events.append(("stem", path)) or Path(path).stem,
            "ConvertTimeStrFMT": lambda value, **kwargs: events.append(
                ("date", value, kwargs)
            ) or value[:10],
            "removeStrPrefix": lambda value, prefix: events.append(
                ("prefix", value, prefix)
            ) or (value[len(prefix):] if value.startswith(prefix) else value),
            "dfOutputer": Outputter,
        }
        module = _import_with_stubs(
            calls=calls,
            class_table={"Fish": {"CT": "漁業簡訊-漁業"}},
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            original_cwd = os.getcwd()
            os.chdir(temporary_directory)
            try:
                caller_cwd = os.getcwd()
                with mock.patch.object(
                    module.os.path, "isfile",
                    side_effect=lambda path: events.append(("isfile", path)) or True,
                ), mock.patch.object(
                    module.os, "system",
                    side_effect=lambda path: events.append(("system", path)) or 0,
                ):
                    module.main()
                self.assertEqual(os.getcwd(), caller_cwd)
            finally:
                os.chdir(original_cwd)

        self.assertIn(("isfile", "CPAntCSV.bat"), events)
        self.assertIn(("system", "CPAntCSV.bat"), events)
        self.assertIn(("sql", "test_results_verification.sql3"), events)
        self.assertIn(
            (
                "csv",
                {
                    "InputCSV": "MERGED-20231024-20240306All.csv",
                    "sep": ",", "header": True, "error_bad_lines": True,
                },
            ),
            events,
        )
        self.assertIn(
            (
                "dfOutputer", "MERGED-20231024-20240306All_Combined",
                {"OutputFormat": ["tsv"], "TSVTextAdapter": True},
            ),
            events,
        )
        self.assertIn(("run",), events)
        dataframe = output["dataframe"]
        self.assertEqual(list(dataframe["SmsContent"]), ["first", "second"])
        self.assertEqual(list(dataframe["日期"]), ["2024-03-01", "2024-03-02"])
        self.assertEqual(list(dataframe["推論類別"]), ["漁業", "Unmapped"])
        self.assertEqual(list(dataframe["標註類別"]), ["漁業", "Unmapped"])
        self.assertEqual(list(dataframe["推論正確"]), [True, True])
        self.assertEqual(list(dataframe["SmsContentNo"]), ["7", ""])


if __name__ == "__main__":
    unittest.main()
