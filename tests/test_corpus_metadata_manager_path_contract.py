import ast
import importlib
import os
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "DatasetConverter" / "CorpusMetadataManager.py"
MODULE_NAME = "DatasetConverter.CorpusMetadataManager"


class _Proc:
    def __init__(self, function=lambda value: value):
        self.function = function

    def proc(self, *args, **kwargs):
        return self.function(*args, **kwargs)


def _unexpected(name):
    def fail(*args, **kwargs):
        raise AssertionError("{} ran during module import".format(name))
    return fail


def _stub_modules(*, calls=None):
    calls = calls if calls is not None else {}
    df_utils = types.ModuleType("text_category_profiler.data.df_utils")
    df_utils.dfFromSQLite3 = calls.get("dfFromSQLite3", _unexpected("dfFromSQLite3"))

    utilities = types.ModuleType("text_category_profiler.core.utilities")
    for name in (
        "BackUp", "OSWALK", "MKDIR", "timeNow", "getFileModTime",
        "getMFNFromFN", "getFileDirFromFN", "hash", "textReader",
        "removekey",
    ):
        setattr(utilities, name, calls.get(name, _unexpected(name)))
    utilities.TextNormalizer = calls.get("TextNormalizer", object)
    utilities.fileNameNormalizer = calls.get("fileNameNormalizer", _Proc())

    mp_utils = types.ModuleType("text_category_profiler.concurrency.MP_utils")
    mp_utils.MPlogger = types.SimpleNamespace(
        logW=calls.get("logW", _unexpected("MPlogger.logW"))
    )

    source_metadata = types.ModuleType("DatasetConverter.core.source_metadata")
    source_metadata.getSrcFromFileName = calls.get(
        "getSrcFromFileName", _unexpected("getSrcFromFileName")
    )

    label_utils = types.ModuleType("ClassesTree.Label_utils")
    label_utils.getLabelsFromOSWALK = calls.get(
        "getLabelsFromOSWALK", _unexpected("getLabelsFromOSWALK")
    )
    label_utils.getLabelsFromFileName = calls.get(
        "getLabelsFromFileName", _unexpected("getLabelsFromFileName")
    )
    label_utils.LabelsStringReader = calls.get("LabelsStringReader", _Proc())
    label_utils.LabelNormalizer = calls.get("LabelNormalizer", _Proc())
    label_utils.LabelsQuerent = calls.get("LabelsQuerent", _Proc())
    label_utils.FilePathLabelsPurifier = calls.get(
        "FilePathLabelsPurifier", _Proc()
    )
    return {
        df_utils.__name__: df_utils,
        utilities.__name__: utilities,
        mp_utils.__name__: mp_utils,
        source_metadata.__name__: source_metadata,
        label_utils.__name__: label_utils,
    }


def _import_with_stubs(*, calls=None):
    sys.modules.pop(MODULE_NAME, None)
    with mock.patch.dict(sys.modules, _stub_modules(calls=calls)):
        return importlib.import_module(MODULE_NAME)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


class _Connection:
    def __init__(self):
        self.queries = []
        self.commits = 0
        self.closed = False

    def execute(self, query, values=None):
        self.queries.append((query, values))
        if "sqlite_master" in query:
            return _Cursor(["Corpus"])
        if query == "SELECT FilePath FROM Corpus":
            return _Cursor([])
        if query == "SELECT FilePath,topics FROM Corpus":
            return _Cursor([])
        return _Cursor([])

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class CorpusMetadataManagerPathContractTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop(MODULE_NAME, None)

    def test_source_contract_isolates_maintenance_in_main(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(SCRIPT))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("PackageImport", imported)
        self.assertNotIn("PackageImporter.proc()", source)
        self.assertNotIn("os.chdir", source)
        for path in ("D:/shared/PythonModule", "Z:/PythonModule", "../PythonModule"):
            self.assertNotIn(path, source)
        self.assertIn("Path(__file__).resolve().parents[1]", source)

        first_local_import = source.index("from text_category_profiler")
        self.assertLess(source.index("sys.path.insert"), first_local_import)
        bootstrap_guard = next(
            node for node in tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and ast.unparse(node.test) == "__name__ == '__main__'"
        )
        self.assertIn("sys.path.insert", ast.unparse(bootstrap_guard))

        forbidden = {
            "getLabelsFromOSWALK", "BackUp", "lite.connect", "dfFromSQLite3",
            "OSWALK", "shutil.move", "conn.execute", "conn.commit", "conn.close",
        }
        module_calls = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) or node is bootstrap_guard:
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    module_calls.add(ast.unparse(child.func))
        self.assertTrue(forbidden.isdisjoint(module_calls), module_calls & forbidden)

    def test_import_does_not_run_metadata_maintenance_or_mutate_process_state(self):
        cwd = os.getcwd()
        path = list(sys.path)
        with mock.patch("sqlite3.connect", side_effect=_unexpected("sqlite3.connect")), \
                mock.patch("shutil.move", side_effect=_unexpected("shutil.move")):
            module = _import_with_stubs()
        self.assertEqual(module.sql3File, "Books_Metadata_CLIP_False.sql3")
        self.assertEqual(os.getcwd(), cwd)
        self.assertEqual(sys.path, path)
        self.assertFalse(hasattr(module, "LabelList"))

    def test_direct_script_bootstrap_uses_repository_root_without_chdir(self):
        probe = r'''
import importlib.abc
import os
import runpy
import sys

expected_root, expected_cwd, script = sys.argv[1:]
class StopAtFirstLocalImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "text_category_profiler.data.df_utils":
            assert expected_root in sys.path, sys.path
            assert os.getcwd() == expected_cwd, os.getcwd()
            raise SystemExit(23)
        return None
sys.meta_path.insert(0, StopAtFirstLocalImport())
runpy.run_path(script, run_name="__main__")
'''
        for cwd in (REPOSITORY_ROOT, REPOSITORY_ROOT / "DatasetConverter"):
            result = subprocess.run(
                [sys.executable, "-c", probe, str(REPOSITORY_ROOT), str(cwd), str(SCRIPT)],
                cwd=cwd, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 23, result.stderr)

    def test_main_preserves_caller_relative_paths_and_metadata_workflow(self):
        normalized_inputs = []
        label_roots = []
        walked_roots = []
        backups = []
        dataframe_calls = []
        connection_calls = []
        connection = _Connection()

        def normalize(value=None, fileName=None):
            value = fileName if fileName is not None else value
            normalized_inputs.append(value)
            return value

        calls = {
            "fileNameNormalizer": _Proc(normalize),
            "getLabelsFromOSWALK": lambda roots: label_roots.append(list(roots)) or ["label"],
            "OSWALK": lambda root, Extension=None: walked_roots.append((root, Extension)) or [],
            "BackUp": lambda path: backups.append(path),
            "dfFromSQLite3": lambda path, tableList=None: dataframe_calls.append(
                (path, tableList)
            ) or object(),
        }
        module = _import_with_stubs(calls=calls)

        def connect(path, timeout=None):
            connection_calls.append((path, timeout, os.getcwd()))
            return connection

        expected_components = [
            "C_GoogleSearch", "Books", "../===DRNData",
            "C_wikisourceSearch", "C_wikisourcePortal",
        ]
        expected_roots = [module.TopicTextCrawlerROOT + item for item in expected_components]
        with tempfile.TemporaryDirectory() as caller_cwd, ExitStack() as stack:
            original_cwd = os.getcwd()
            os.chdir(caller_cwd)
            stack.callback(os.chdir, original_cwd)
            stack.enter_context(mock.patch.object(module.os.path, "isfile", return_value=True))
            stack.enter_context(mock.patch.object(module.lite, "connect", side_effect=connect))
            module.main()
            self.assertEqual(os.getcwd(), caller_cwd)

        self.assertEqual(module.ROOTPATH_COMPONENTS, expected_components)
        self.assertEqual(normalized_inputs, expected_roots)
        self.assertEqual(label_roots, [expected_roots])
        self.assertEqual(walked_roots, [(root, "txt") for root in expected_roots])
        self.assertEqual(backups, ["Books_Metadata_CLIP_False.sql3"])
        self.assertEqual(
            connection_calls,
            [("Books_Metadata_CLIP_False.sql3", 30, caller_cwd)],
        )
        self.assertEqual(
            dataframe_calls,
            [("Books_Metadata_CLIP_False.sql3", ["Corpus"])],
        )
        queries = [query for query, unused_values in connection.queries]
        self.assertIn("SELECT FilePath FROM Corpus", queries)
        self.assertIn("SELECT FilePath,topics FROM Corpus", queries)
        self.assertGreaterEqual(connection.commits, 2)
        self.assertTrue(connection.closed)

    def test_get_db_labels_contract_is_preserved(self):
        module = _import_with_stubs()
        function = next(
            node for node in ast.parse(SCRIPT.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name == "getDBLabels"
        )
        self.assertEqual(
            [argument.arg for argument in function.args.args],
            ["sql3cursor", "Table", "LabelCol", "HashCol", "HashVal", "FilePathCol", "FilePath"],
        )
        self.assertIn("lite.connect(sql3File)", ast.unparse(function))
        self.assertIn("LabelsQuerent.proc", ast.unparse(function))


if __name__ == "__main__":
    unittest.main()
