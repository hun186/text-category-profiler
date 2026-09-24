import ast
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


_STUBBED_MODULE_NAMES = (
    "text_category_profiler.core.utilities",
    "text_category_profiler.data.df_utils",
    "text_category_profiler.data.DB_utils",
)


def _install_dependency_light_import_stubs():
    utilities = types.ModuleType("text_category_profiler.core.utilities")
    for name in (
        "removeStrPrefix",
        "removeStrSuffix",
        "OSWALK",
        "MKDIR",
        "fileNameNormalizer",
        "getMFNFromFN",
        "getFNFromFullPath",
        "RemoveIlleagalCharForFileName",
        "DomainNameExtractor",
        "getPathFromFN",
    ):
        setattr(utilities, name, lambda *args, **kwargs: None)
    utilities.removeStrPrefix = lambda value, prefix: value.removeprefix(prefix)
    utilities.removeStrSuffix = lambda value, suffix: value.removesuffix(suffix)
    utilities.getFNFromFullPath = lambda path: os.path.basename(path)
    utilities.RemoveIlleagalCharForFileName = lambda value: value

    df_utils = types.ModuleType("text_category_profiler.data.df_utils")
    df_utils.DictRowsListToDF = pd.DataFrame
    df_utils.dfFromSQLite3 = lambda path: None
    df_utils.dfOutputer = lambda *args, **kwargs: None

    db_utils = types.ModuleType("text_category_profiler.data.DB_utils")
    db_utils.createTable = lambda *args, **kwargs: None
    db_utils.createIndex = lambda *args, **kwargs: None

    sys.modules["text_category_profiler.core.utilities"] = utilities
    sys.modules["text_category_profiler.data.df_utils"] = df_utils
    sys.modules["text_category_profiler.data.DB_utils"] = db_utils


_original_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULE_NAMES}
_install_dependency_light_import_stubs()

from DatasetConverter.EXTConverter import Combiner
from DatasetConverter.EXTConverter import ExtractionConverter

for _name, _module in _original_modules.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXTCONVERTER_ROOT = REPOSITORY_ROOT / "DatasetConverter" / "EXTConverter"
MODULE_PATHS = (
    EXTCONVERTER_ROOT / "ExtractionConverter.py",
    EXTCONVERTER_ROOT / "Combiner.py",
)


class OutputRecorder:
    calls = []

    def __init__(self, dataframe, output_main, **kwargs):
        self.dataframe = dataframe
        self.output_main = output_main
        self.kwargs = kwargs

    def run(self):
        self.calls.append((self.dataframe, self.output_main, self.kwargs))


class ExtractionInputRootTests(unittest.TestCase):
    def test_absolute_target_is_authoritative_from_supported_cwds(self):
        target = str(REPOSITORY_ROOT / "work-item")
        for cwd in (REPOSITORY_ROOT, EXTCONVERTER_ROOT):
            with self.subTest(cwd=cwd):
                self.assertEqual(
                    ExtractionConverter.resolve_extraction_input_root(
                        target, caller_cwd=cwd
                    ),
                    target,
                )

    def test_posix_and_windows_absolute_paths_keep_their_lexical_contract(self):
        self.assertEqual(
            ExtractionConverter.resolve_extraction_input_root(
                "/srv/work/item", caller_cwd=REPOSITORY_ROOT
            ),
            "/srv/work/item",
        )
        self.assertEqual(
            ExtractionConverter.resolve_extraction_input_root(
                r"D:\shared\work\item", caller_cwd=REPOSITORY_ROOT
            ),
            r"D:\shared\work\item",
        )

    def test_relative_target_reuses_an_existing_cwd_segment(self):
        self.assertEqual(
            ExtractionConverter.resolve_extraction_input_root(
                "DatasetConverter/EXTConverter/Input", caller_cwd=REPOSITORY_ROOT
            ),
            str(EXTCONVERTER_ROOT / "Input"),
        )
        self.assertEqual(
            ExtractionConverter.resolve_extraction_input_root(
                "DatasetConverter/EXTConverter/Input", caller_cwd=EXTCONVERTER_ROOT
            ),
            str(EXTCONVERTER_ROOT / "Input"),
        )

    def test_relative_target_without_matching_segment_is_below_caller(self):
        self.assertEqual(
            ExtractionConverter.resolve_extraction_input_root(
                "incoming/files", caller_cwd=EXTCONVERTER_ROOT
            ),
            str(EXTCONVERTER_ROOT / "incoming" / "files"),
        )

    def test_extractor_scans_authoritative_root_and_writes_beside_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.csv"
            source.write_text("hello world,label\n", encoding="utf-8")
            job_info = {
                "DirName": str(root),
                "fileNames": [r"source\.csv"],
                "header": False,
                "Sep": ",",
                "nCSVCol": 2,
                "TextCol": [0],
                "LabelInfo": {"nCol": 1},
                "TestSetFormatOutput": True,
                "CZJ_CorpusFileFormatOutput": True,
            }
            caller_cwd = os.getcwd()
            OutputRecorder.calls = []

            with mock.patch.object(
                ExtractionConverter, "OSWALK", return_value=[str(source)]
            ) as walk, mock.patch.object(
                ExtractionConverter, "dfOutputer", OutputRecorder
            ):
                ExtractionConverter.Extractor("SDSMS_Train", JobInfo=job_info)

            self.assertEqual(os.getcwd(), caller_cwd)
            walk.assert_called_once_with(str(root))
            self.assertEqual(
                [Path(call[1]) for call in OutputRecorder.calls],
                [
                    root / "source_CZJ_SamplesFile",
                    root / "test",
                    root / "CZJ_CorpusFile_SDSMS_Train_FixedTest",
                ],
            )


class CombinerPathContractTests(unittest.TestCase):
    def test_corpus_builder_uses_caller_owned_source_and_output_paths(self):
        source = "/caller/input.sql3"
        output = "/caller/output.sql3"
        dataframe = pd.DataFrame(
            [{"file": "article", "InLabel": "topic", "PartNO": 0, "text": "text"}]
        )
        OutputRecorder.calls = []

        with mock.patch.object(Combiner, "dfFromSQLite3", return_value=dataframe) as read, mock.patch.object(
            Combiner, "dfOutputer", OutputRecorder
        ):
            Combiner.CZJCorpusFileBuilder(source, output).Transformer()

        read.assert_called_once_with(source)
        self.assertEqual(OutputRecorder.calls[0][1], "/caller/output")

    def test_embassy_output_is_anchored_to_repository_root(self):
        combiner = Combiner.EmbassyPagesCombiner(ROOTPATH="/input")
        OutputRecorder.calls = []
        with mock.patch.object(Combiner.os, "listdir", side_effect=[["=Address"], []]), mock.patch.object(
            Combiner, "DictRowsListToDF", return_value=pd.DataFrame()
        ), mock.patch.object(Combiner, "dfOutputer", OutputRecorder):
            combiner.proc()

        self.assertEqual(
            OutputRecorder.calls[0][1],
            str(EXTCONVERTER_ROOT / "Output" / "EmbassyPages" / "EmbassyPages"),
        )


class DirectScriptCompatibilityTests(unittest.TestCase):
    def test_sources_have_guarded_file_relative_bootstrap_and_no_injector(self):
        for path in MODULE_PATHS:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                imports = {
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module
                }
                self.assertNotIn("PackageImport", imports)
                self.assertNotIn("PackageImporter", source)
                self.assertNotIn("os.chdir", source)
                self.assertIn('if __name__ == "__main__"', source)
                self.assertIn("Path(__file__).resolve().parents[2]", source)
                self.assertNotIn("D:/shared/PythonModule", source)
                self.assertNotIn("../PythonModule", source)

    def test_package_imports_resolve_from_extconverter_cwd_without_chdir(self):
        command = [
            sys.executable,
            "-c",
            (
                "import os, runpy; before=os.getcwd(); "
                "from tests.test_extconverter_path_contract import "
                "_install_dependency_light_import_stubs; "
                "_install_dependency_light_import_stubs(); "
                "runpy.run_path('ExtractionConverter.py', run_name='characterization'); "
                "runpy.run_path('Combiner.py', run_name='characterization'); "
                "assert os.getcwd() == before"
            ),
        ]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
        result = subprocess.run(
            command,
            cwd=EXTCONVERTER_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
