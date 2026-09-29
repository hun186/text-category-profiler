import ast
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPOSITORY_ROOT / "DatasetConverter" / "FreqAnalysis_dash.py"
SOURCE = TARGET.read_text(encoding="utf-8-sig")
TREE = ast.parse(SOURCE, filename=str(TARGET))


def import_from(module, name, asname=None):
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == module
        and any(
            alias.name == name and alias.asname == asname
            for alias in node.names
        )
        for node in TREE.body
    )


def assignment(name):
    return [
        node
        for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]


class FreqAnalysisDashPathContractTests(unittest.TestCase):
    def test_legacy_injector_and_bare_providers_are_absent(self):
        imported_modules = []
        for node in ast.walk(TREE):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)
            elif isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)

        self.assertNotIn("PackageImport", imported_modules)
        self.assertNotIn("MP_utils", imported_modules)
        self.assertNotIn("df_utils", imported_modules)
        self.assertNotIn("reusable_components", imported_modules)
        self.assertNotIn("BertScript.MP_utils", imported_modules)
        self.assertNotIn("DatasetConverter.df_utils", imported_modules)
        self.assertNotIn("PackageImporter.proc", SOURCE)
        for forbidden_path in (
            "D:/shared/PythonModule",
            "Z:/PythonModule",
            "../PythonModule",
        ):
            self.assertNotIn(forbidden_path, SOURCE)

    def test_bootstrap_is_direct_script_only_and_precedes_repository_imports(self):
        script_dir = assignment("SCRIPT_DIR")
        repository_root = assignment("REPOSITORY_ROOT")
        self.assertEqual(len(script_dir), 1)
        self.assertEqual(len(repository_root), 1)
        self.assertEqual(
            ast.unparse(script_dir[0].value),
            "Path(__file__).resolve().parent",
        )
        self.assertEqual(
            ast.unparse(repository_root[0].value),
            "Path(__file__).resolve().parents[1]",
        )

        main_guards = [
            node
            for node in TREE.body
            if isinstance(node, ast.If)
            and ast.unparse(node.test) == "__name__ == '__main__'"
            and any(
                isinstance(child, ast.Call)
                and ast.unparse(child.func) == "sys.path.insert"
                for child in ast.walk(node)
            )
        ]
        self.assertEqual(len(main_guards), 1)
        inserts = [
            node
            for node in ast.walk(main_guards[0])
            if isinstance(node, ast.Call)
            and ast.unparse(node.func) == "sys.path.insert"
        ]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(
            ast.unparse(inserts[0]),
            "sys.path.insert(0, str(REPOSITORY_ROOT))",
        )

        first_repository_import = min(
            node.lineno
            for node in TREE.body
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("text_category_profiler")
        )
        self.assertLess(main_guards[0].lineno, first_repository_import)

    def test_explicit_canonical_providers(self):
        self.assertTrue(
            import_from("text_category_profiler.concurrency.MP_utils", "MPlogger")
        )
        self.assertTrue(
            import_from("text_category_profiler.data.df_utils", "dfOutputer")
        )
        self.assertTrue(
            import_from(
                "text_category_profiler.visualization",
                "reusable_components",
                "rc",
            )
        )

    def test_local_str_df_from_json_preserves_legacy_semantics(self):
        functions = [
            node
            for node in TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == "StrDfFromJson"
        ]
        self.assertEqual(len(functions), 1)
        namespace = {"np": np, "pd": pd}
        module = ast.Module(body=functions, type_ignores=[])
        exec(compile(module, str(TARGET), "exec"), namespace)

        fixture = pd.DataFrame({"value": ["None", "normal string"]})
        result = namespace["StrDfFromJson"](
            io.StringIO(fixture.to_json(orient="split"))
        )

        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(pd.isna(result.loc[0, "value"]))
        self.assertEqual(result.loc[1, "value"], "normal string")
        self.assertTrue(pd.api.types.is_string_dtype(result["value"].dtype))

    def test_mplogger_uses_one_silent_caller_relative_instance(self):
        configured = assignment("MPLOGGER")
        self.assertEqual(len(configured), 1)
        call = configured[0].value
        self.assertIsInstance(call, ast.Call)
        self.assertEqual(ast.unparse(call.func), "MPlogger")
        self.assertEqual(
            {keyword.arg: ast.literal_eval(keyword.value) for keyword in call.keywords},
            {"logSubDir": "", "logFile": "mp_processing_log.txt"},
        )

        log_calls = [
            node
            for node in ast.walk(TREE)
            if isinstance(node, ast.Call)
            and ast.unparse(node.func) == "MPLOGGER.logW"
        ]
        self.assertEqual(len(log_calls), 2)
        for log_call in log_calls:
            keywords = {keyword.arg: keyword.value for keyword in log_call.keywords}
            self.assertIn("printOnScreen", keywords)
            self.assertIs(ast.literal_eval(keywords["printOnScreen"]), False)
        self.assertNotIn("MPlogger.logW(", SOURCE)

    def test_input_is_dataset_converter_resource_and_outputs_remain_caller_relative(self):
        self.assertTrue((TARGET.parent / "RandText.txt").is_file())
        self.assertTrue((TARGET.parent / "RandText_short.txt").is_file())

        input_assignments = assignment("InputFile")
        self.assertEqual(len(input_assignments), 1)
        self.assertEqual(
            ast.unparse(input_assignments[0].value),
            "str(SCRIPT_DIR / 'RandText.txt')",
        )
        resolved_input = str(TARGET.parent / "RandText.txt")
        self.assertTrue(Path(resolved_input).is_absolute())

        output_calls = [
            node
            for node in ast.walk(TREE)
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "dfOutputer"
        ]
        self.assertEqual(len(output_calls), 1)
        output_call = output_calls[0]
        self.assertEqual(ast.literal_eval(output_call.args[1]), "test")
        keywords = {keyword.arg: keyword.value for keyword in output_call.keywords}
        self.assertEqual(ast.literal_eval(keywords["IndexCols"]), ["text"])
        self.assertIsInstance(keywords["MPLOGGER"], ast.Name)
        self.assertEqual(keywords["MPLOGGER"].id, "MPLOGGER")
        self.assertIs(ast.literal_eval(keywords["AutoAdjustColWidth"]), False)
        self.assertIs(ast.literal_eval(keywords["AutoAdjustRowWidth"]), False)

    def test_direct_script_bootstrap_from_supported_working_directories(self):
        probe = textwrap.dedent(
            """
            import builtins
            import json
            import os
            import runpy
            import sys

            target, repository_root = sys.argv[1:]
            original_import = builtins.__import__

            def intercept(name, globals=None, locals=None, fromlist=(), level=0):
                if name.startswith("text_category_profiler"):
                    print("PROBE:" + json.dumps({
                        "cwd": os.getcwd(),
                        "repository_root_in_sys_path": repository_root in sys.path,
                        "first_repository_import": name,
                    }))
                    raise SystemExit(73)
                return original_import(name, globals, locals, fromlist, level)

            builtins.__import__ = intercept
            runpy.run_path(target, run_name="__main__")
            """
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            working_directories = [
                REPOSITORY_ROOT,
                TARGET.parent,
                Path(temporary_directory),
            ]
            for cwd in working_directories:
                with self.subTest(cwd=cwd):
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            probe,
                            str(TARGET),
                            str(REPOSITORY_ROOT),
                        ],
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 73, result.stderr)
                    probe_lines = [
                        line.removeprefix("PROBE:")
                        for line in result.stdout.splitlines()
                        if line.startswith("PROBE:")
                    ]
                    self.assertEqual(len(probe_lines), 1, result.stdout)
                    evidence = json.loads(probe_lines[0])
                    self.assertEqual(evidence["cwd"], str(cwd))
                    self.assertTrue(evidence["repository_root_in_sys_path"])
                    self.assertTrue(
                        evidence["first_repository_import"].startswith(
                            "text_category_profiler"
                        )
                    )


if __name__ == "__main__":
    unittest.main()
