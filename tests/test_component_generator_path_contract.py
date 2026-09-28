import ast
import importlib.util
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    REPOSITORY_ROOT
    / "DatasetConverter"
    / "Dataset Generator"
    / "ComponentGenerator"
    / "ComponentGenerator.py"
)
COMPONENT_DIR = TARGET.parent


class _ModuleScopeCalls(ast.NodeVisitor):
    def __init__(self):
        self.calls = []

    def visit_FunctionDef(self, node):
        return

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        return

    def visit_Lambda(self, node):
        return

    def visit_Call(self, node):
        self.calls.append(node)
        self.generic_visit(node)


class ComponentGeneratorPathContractTests(unittest.TestCase):
    def setUp(self):
        self.sqlite_calls = []
        self.mkdir_calls = []

    def _load_module(self, rows=None):
        rows = [] if rows is None else rows

        faker = types.ModuleType("faker")
        faker.Faker = mock.Mock(name="Faker")
        utilities = types.ModuleType("text_category_profiler.core.utilities")
        utilities.MKDIR = lambda path: self.mkdir_calls.append(path)
        df_utils = types.ModuleType("text_category_profiler.data.df_utils")

        def fake_read(*, sql3File):
            self.sqlite_calls.append(sql3File)
            return {"Email": rows}

        df_utils.dfFromSQLite3 = fake_read
        module_name = f"component_generator_contract_{id(self)}_{len(self.sqlite_calls)}"
        spec = importlib.util.spec_from_file_location(module_name, TARGET)
        module = importlib.util.module_from_spec(spec)
        stubs = {
            "faker": faker,
            "text_category_profiler.core.utilities": utilities,
            "text_category_profiler.data.df_utils": df_utils,
        }
        cwd = Path.cwd()
        path = list(sys.path)
        with mock.patch.dict(sys.modules, stubs), mock.patch(
            "os.chdir", side_effect=AssertionError("import called os.chdir")
        ):
            spec.loader.exec_module(module)
        self.assertEqual(Path.cwd(), cwd)
        self.assertEqual(sys.path, path)
        return module

    def test_source_and_ast_contract(self):
        source = TARGET.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(node.module == "PackageImport" for node in imports))
        self.assertFalse(
            any(node.module == "JobTitleGenerator.jobtitlegenerator" for node in imports)
        )
        self.assertNotIn("D:/shared/PythonModule", source)
        self.assertNotIn("Z:/PythonModule", source)
        self.assertNotIn("../PythonModule", source)
        self.assertNotIn("os.chdir", source)

        root_assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "REPOSITORY_ROOT"
                for target in node.targets
            )
        )
        self.assertEqual(
            ast.unparse(root_assignment.value), "Path(__file__).resolve().parents[3]"
        )

        main_guards = [
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and ast.unparse(node.test) == "__name__ == '__main__'"
        ]
        bootstrap_guard = main_guards[0]
        inserts = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and ast.unparse(node.func) == "sys.path.insert"
        ]
        self.assertEqual(len(inserts), 1)
        self.assertIn(inserts[0], list(ast.walk(bootstrap_guard)))
        first_repository_import = next(
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("text_category_profiler")
        )
        self.assertLess(tree.body.index(bootstrap_guard), first_repository_import)

        visitor = _ModuleScopeCalls()
        for node in tree.body:
            if node not in main_guards:
                visitor.visit(node)
        forbidden = {
            "LoadEmbassyEmails",
            "dfFromSQLite3",
            "MKDIR",
            "GeneratePool",
            "GenerateContactInformation",
            "GenerateEmailAddressInEmailHeader",
            "GenerateEmailHeader",
        }
        self.assertTrue(
            forbidden.isdisjoint(ast.unparse(call.func) for call in visitor.calls)
        )

    def test_import_has_no_database_cwd_path_or_output_side_effect(self):
        module = self._load_module()
        self.assertEqual(self.sqlite_calls, [])
        self.assertEqual(self.mkdir_calls, [])
        self.assertIsNone(module.EmbassyEmails)

    def test_embassy_resource_is_component_local_without_reading_it(self):
        module = self._load_module()
        expected = COMPONENT_DIR / "EmbassyPages" / "EmbassyPages.sql3"
        self.assertTrue(expected.is_file())
        self.assertEqual(module.EMBASSY_DB, expected.resolve())
        self.assertEqual(self.sqlite_calls, [])

    def test_embassy_loading_preserves_filtering_and_caches_first_result(self):
        module = self._load_module(
            [
                "a@mfa.gov\njunk@example.com\nx@mofa.example",
                "person@gov.example\nordinary@example.com\n",
                "MFA@example.com",
            ]
        )
        self.assertEqual(self.sqlite_calls, [])
        expected = ["a@mfa.gov", "x@mofa.example", "person@gov.example"]
        self.assertEqual(module.GetEmbassyEmails(), expected)
        self.assertEqual(module.GetEmbassyEmails(), expected)
        self.assertEqual(self.sqlite_calls, [str(module.EMBASSY_DB)])
        self.assertTrue(Path(self.sqlite_calls[0]).is_absolute())

    def test_user_email_sets_only_loads_embassy_database_for_embassy_label(self):
        module = self._load_module(["first@mfa.gov", "ignored@example.com"])
        module.CompanyEmails = ["company@example.com"]
        with mock.patch.object(module.random, "randint", return_value=1), mock.patch.object(
            module.random, "choice", side_effect=lambda values: values[0]
        ):
            general = module.UserEmailSets(label="Email Header-Email Address")
            self.assertEqual(general, (["company@example.com"],) * 3)
            self.assertEqual(self.sqlite_calls, [])
            embassy = module.UserEmailSets(label="Email Address-Embassy")
            self.assertEqual(embassy, (["first@mfa.gov"],) * 3)
            module.UserEmailSets(label="Email Address-Embassy")
        self.assertEqual(self.sqlite_calls, [str(module.EMBASSY_DB)])

    def test_direct_script_bootstrap_precedes_repository_import_without_chdir(self):
        probe = r'''
import importlib.abc
import importlib.machinery
import runpy
import sys
import types
from pathlib import Path

target, repository_root, expected_cwd = map(Path, sys.argv[1:])
original_cwd = Path.cwd()
assert original_cwd == expected_cwd
sys.path.insert(0, str(target.parent))
faker = types.ModuleType("faker")
faker.Faker = object
sys.modules["faker"] = faker

class StopAtRepositoryImport(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "text_category_profiler.core.utilities":
            return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        assert str(repository_root) in sys.path
        assert Path.cwd() == original_cwd
        raise SystemExit(73)

sys.meta_path.insert(0, StopAtRepositoryImport())
try:
    runpy.run_path(str(target), run_name="__main__")
except SystemExit as error:
    assert error.code == 73
else:
    raise AssertionError("repository-local import was not intercepted")
'''
        with tempfile.TemporaryDirectory() as temporary_directory:
            for cwd in (REPOSITORY_ROOT, COMPONENT_DIR, Path(temporary_directory)):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        probe,
                        str(TARGET),
                        str(REPOSITORY_ROOT),
                        str(cwd),
                    ],
                    cwd=cwd,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_letter_greeting_output_remains_caller_cwd_relative(self):
        module = self._load_module()
        module.nGen = 1
        module.Names = ["Name"]
        module.JobTitles = ["Title"]
        opened = mock.mock_open()
        with mock.patch.object(module.random, "choice", side_effect=lambda values: values[0]), mock.patch(
            "builtins.open", opened
        ):
            module.GenerateLetterGreetings()
        opened.assert_called_once_with(
            "LetterGreetingsForClosing.tsv", "at", encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()
