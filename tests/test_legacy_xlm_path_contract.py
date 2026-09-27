import ast
import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "BertScript" / "TextClassification_XLM.py"


class LegacyXLMPathContractTests(unittest.TestCase):
    def test_source_uses_only_main_guarded_file_relative_bootstrap(self):
        source = SCRIPT.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(SCRIPT))

        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("PackageImport", imported_modules)
        self.assertNotIn("PackageImporter.proc()", source)
        self.assertNotIn("D:/shared/PythonModule", source)
        self.assertNotIn("Z:/PythonModule", source)
        self.assertNotIn("../PythonModule", source)

        main_guard = next(
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and ast.unparse(node.test) == "__name__ == '__main__'"
        )
        main_source = ast.unparse(main_guard)
        self.assertIn("Path(__file__).resolve().parents[1]", main_source)
        self.assertIn("sys.path.insert(0, str(REPOSITORY_ROOT))", main_source)

        first_local_import = next(
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("text_category_profiler")
        )
        self.assertLess(tree.body.index(main_guard), first_local_import)

        module_scope = ast.Module(
            body=[node for node in tree.body if node is not main_guard],
            type_ignores=[],
        )
        module_scope_source = ast.unparse(module_scope)
        self.assertNotIn("os.chdir(", module_scope_source)
        self.assertNotIn("sys.path.", module_scope_source)

    def test_direct_script_from_repository_root_bootstraps_without_chdir(self):
        self._assert_direct_script_contract(REPOSITORY_ROOT)

    def test_direct_script_from_bert_script_bootstraps_without_chdir(self):
        self._assert_direct_script_contract(REPOSITORY_ROOT / "BertScript")

    def _assert_direct_script_contract(self, caller_cwd):
        harness = textwrap.dedent(
            """
            import builtins
            import json
            import os
            import runpy
            import sys
            import types

            script, repository_root = sys.argv[1:]
            original_cwd = os.getcwd()
            real_import = builtins.__import__

            def module(name, **attributes):
                stub = types.ModuleType(name)
                for key, value in attributes.items():
                    setattr(stub, key, value)
                sys.modules[name] = stub

            placeholder = object()
            module("torch")
            module("tqdm", tqdm=placeholder, trange=placeholder)
            module(
                "sklearn.metrics",
                precision_recall_fscore_support=placeholder,
                accuracy_score=placeholder,
            )
            module(
                "transformers",
                TFXLMRobertaModel=placeholder,
                AutoTokenizer=placeholder,
                pipeline=placeholder,
                Trainer=placeholder,
                AutoModelForSequenceClassification=placeholder,
                TrainingArguments=placeholder,
            )

            def checked_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name.startswith("text_category_profiler"):
                    assert repository_root in sys.path
                    assert os.getcwd() == original_cwd
                    raise SystemExit(73)
                return real_import(name, globals, locals, fromlist, level)

            builtins.__import__ = checked_import
            try:
                runpy.run_path(script, run_name="__main__")
            except SystemExit as error:
                assert error.code == 73
            else:
                raise AssertionError("repo-local import interception was not reached")

            print("CONTRACT=" + json.dumps({
                "cwd_before": original_cwd,
                "cwd_after": os.getcwd(),
                "repo_on_path": repository_root in sys.path,
            }))
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", harness, str(SCRIPT), str(REPOSITORY_ROOT)],
            cwd=caller_cwd,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(
            next(
                line.removeprefix("CONTRACT=")
                for line in completed.stdout.splitlines()
                if line.startswith("CONTRACT=")
            )
        )
        self.assertEqual(payload["cwd_before"], str(caller_cwd))
        self.assertEqual(payload["cwd_after"], str(caller_cwd))
        self.assertTrue(payload["repo_on_path"])

    def test_import_mode_has_no_classifier_or_filesystem_side_effects(self):
        harness = textwrap.dedent(
            """
            import importlib
            import json
            import os
            import sys
            import types

            calls = []
            original_cwd = os.getcwd()

            def module(name, **attributes):
                stub = types.ModuleType(name)
                for key, value in attributes.items():
                    setattr(stub, key, value)
                sys.modules[name] = stub

            class Torch:
                pass

            def forbidden(*args, **kwargs):
                calls.append("runtime")
                raise AssertionError("classifier runtime executed during import")

            module("torch", cuda=Torch())
            module("tqdm", tqdm=object(), trange=object())
            module(
                "sklearn.metrics",
                precision_recall_fscore_support=forbidden,
                accuracy_score=forbidden,
            )
            module(
                "transformers",
                TFXLMRobertaModel=object(),
                AutoTokenizer=type("AutoTokenizer", (), {"from_pretrained": forbidden}),
                pipeline=forbidden,
                Trainer=forbidden,
                AutoModelForSequenceClassification=type(
                    "AutoModelForSequenceClassification", (),
                    {"from_pretrained": forbidden},
                ),
                TrainingArguments=forbidden,
            )

            stubs = {
                "text_category_profiler.core.utilities": {
                    "SplitList": forbidden, "flattenList": forbidden,
                },
                "text_category_profiler.concurrency.MP_utils": {
                    "MPlogger": object(), "multicoreJob": forbidden,
                },
                "text_category_profiler.pipeline.TCF_utils": {
                    "ClassfierOptionParser": forbidden,
                    "datasetDirOutputDirPickers": forbidden,
                },
                "text_category_profiler.data.DB_utils": {"sqlite3Query": forbidden},
                "text_category_profiler.pipeline.TextClassfier_utils": {
                    "getTopicLabelList": forbidden,
                },
            }
            for name, attributes in stubs.items():
                module(name, **attributes)

            importlib.import_module("BertScript.TextClassification_XLM")
            print("CONTRACT=" + json.dumps({
                "calls": calls,
                "cwd_before": original_cwd,
                "cwd_after": os.getcwd(),
            }))
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", harness],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(
            next(
                line.removeprefix("CONTRACT=")
                for line in completed.stdout.splitlines()
                if line.startswith("CONTRACT=")
            )
        )
        self.assertEqual(payload["calls"], [])
        self.assertEqual(payload["cwd_before"], str(REPOSITORY_ROOT))
        self.assertEqual(payload["cwd_after"], str(REPOSITORY_ROOT))


if __name__ == "__main__":
    unittest.main()
