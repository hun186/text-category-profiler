import argparse
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def _module(name, **attributes):
    module = types.ModuleType(name)
    vars(module).update(attributes)
    return module


def load_tcf_utils():
    """Load the legacy CLI module without importing optional data dependencies."""
    truthy = {"1", "true", "yes", "y", "on"}
    stubs = {
        "text_category_profiler.concurrency.MP_utils": _module(
            "MP_utils", MPlogger=lambda *args, **kwargs: None
        ),
        "text_category_profiler.core.utilities": _module(
            "utilities",
            OSWALK=lambda path: [], BackupAndDelFile=lambda **kwargs: None,
            timeNow=lambda: "NOW", str2bool=lambda value: value if isinstance(value, bool)
            else str(value).lower() in truthy, RenameDir=lambda **kwargs: None,
            getFNFromFullPath=lambda path: Path(path).name,
        ),
        "text_category_profiler.core.utilities_path": _module(
            "utilities_path", find_similar_directory=lambda *args, **kwargs: None
        ),
        "text_category_profiler.data.df_utils": _module(
            "df_utils", dfFromSQLite3=lambda *args, **kwargs: None
        ),
        "text_category_profiler.core.log_display": _module(
            "log_display", **{name: (lambda *args, **kwargs: None) for name in
            ("key_values", "section", "stage_done", "summarize_sequence", "warning")}
        ),
    }
    name = "_phase0_tcf_utils"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "text_category_profiler" / "pipeline" / "TCF_utils.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


EXPECTED_ACTIONS = [
    ("debugMode", ("-debug", "--debugMode"), False),
    ("TRVPort", ("-p", "--TRVPort"), 8050),
    ("public", ("-pub", "--public"), False),
    ("task", ("-task", "--task"), ""),
    ("train", ("-tr", "--train"), False),
    ("trainWithMaliciousDomainDataset", ("-trMD", "--trainWithMaliciousDomainDataset"), False),
    ("TrainDRNDataOnly", ("-trDRNOnly", "--TrainDRNDataOnly"), False),
    ("test", ("-ts", "--test"), False),
    ("ExecutionTime", ("-exectime", "--ExecutionTime"), ""),
    ("WorkPoolROOT", ("-WPRoot", "--WorkPoolROOT"), "WorkPool"),
    ("BertDatasetSubDir", ("-BertDataDir", "--BertDatasetSubDir"), ""),
    ("datasetDataBaseSubDir", ("-datasetDBDir", "--datasetDataBaseSubDir"), "datasetDB"),
    ("BertDatasetSubDirExt", ("-BertDataDirExt", "--BertDatasetSubDirExt"), ""),
    ("TopicTreeDir", ("-TopicTreeDir", "--TopicTreeDir"), ""),
    ("TopicTreeFiles", ("-TopicTreeFiles", "--TopicTreeFiles"), "TopicTree.csv,TopicTree_AK4.csv"),
    ("RemoveBertDataDir", ("-RMBertData", "--RemoveBertDataDir"), False),
    ("modelDir", ("-mdlDir", "--modelDir"), ""),
    ("MaxSeqLength", ("-MaxSeqLen", "--MaxSeqLength"), 180),
    ("Run_Test_result_Vis", ("-RunTRV", "--Run_Test_result_Vis"), True),
    ("VisDatasetDir", ("-VisDir", "--VisDatasetDir"), ""),
    ("VisSelfService", ("-VisSelf", "--VisSelfService"), False),
    ("CountArticleComposition", ("-CountArtComp", "--CountArticleComposition"), True),
    ("ExportDFAllToDatabase", ("-ExpDFAllToDB", "--ExportDFAllToDatabase"), False),
    ("ExportDatabasePath", ("-ExpDBPATH", "--ExportDatabasePath"), "DFDatabase"),
    ("DFAllExportPATH", ("-DFAllExpPath", "--DFAllExportPATH"), ""),
    ("FixedTestPATH", ("-FTPath", "--FixedTestPATH"), ""),
    ("WeiTechFormatInputPATH", ("-WTFInpPath", "--WeiTechFormatInputPATH"), ""),
    ("WeiTechFormatOutputPATH", ("-WTFOptPath", "--WeiTechFormatOutputPATH"), ""),
    ("WeiTechFormatSepWorkPool", ("-WTFSepWorkPool", "--WeiTechFormatSepWorkPool"), False),
    ("WeiTechworkIDPath", ("-WTworkIDPath", "--WeiTechworkIDPath"), ""),
    ("WeiTechworkID", ("-WTworkID", "--WeiTechworkID"), ""),
    ("WeiTechWorkPoolPATH", ("-WTWorkPoolPath", "--WeiTechWorkPoolPATH"), ""),
    ("ExtractionConverterTask", ("-EXTConvTask", "--ExtractionConverterTask"), ""),
    ("ESDataConfigFile", ("-ESCFFile", "--ESDataConfigFile"), ""),
    ("FixedTestFileBound", ("-FB", "--FixedTestFileBound"), 0),
    ("TRVWebHost", ("-TRVHost", "--TRVWebHost"), True),
    ("AutoInfoScoreBound", ("-AutoISB", "--AutoInfoScoreBound"), True),
    ("InfoScoreSumLowerBound", ("-ISlbd", "--InfoScoreSumLowerBound"), -999999999),
    ("InfoScoreSumUpperBound", ("-ISubd", "--InfoScoreSumUpperBound"), 99999999999),
    ("nScoringSegUPD", ("-nScoreUPD", "--nScoringSegUPD"), 100),
    ("ModelType", ("-mdlType", "--ModelType"), "PytorchXLM"),
    ("ActiveHTCZeroshot", ("-ZeroShot", "--ActiveHTCZeroshot"), False),
    ("TwinsAfterSort", ("-TwinsAS", "--TwinsAfterSort"), False),
    ("SimilarityMethod", ("-SimMethod", "--SimilarityMethod"), "CountVectorCosine"),
    ("TwinsHighScoreNoUBD", ("-TwinsHSNoUBD", "--TwinsHighScoreNoUBD"), 99999999999),
    ("SummarizePerformance", ("-SumPerf", "--SummarizePerformance"), False),
    ("keep_checkpoint_max", ("-keep_checkpoint_max", "--keep_checkpoint_max"), 1),
    ("SaveOptimizer", ("-SaveOptimizer", "--SaveOptimizer"), False),
    ("TextSummarization", ("-TextSum", "--TextSummarization"), False),
    ("nProcess", ("-nProc", "--nProcess"), 1),
    ("nProcessSPC", ("-nProcSPC", "--nProcessSPC"), 1),
]


class ClassifierCliContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_tcf_utils()

    def _action_table(self):
        captured = {}
        original = argparse.ArgumentParser.parse_args

        def recording_parse(parser, args=None, namespace=None):
            captured["parser"] = parser
            return original(parser, [], namespace)

        with patch.object(argparse.ArgumentParser, "parse_args", recording_parse):
            self.module.ClassfierOptionParser([])
        return [(a.dest, tuple(a.option_strings), a.default)
                for a in captured["parser"]._actions if a.dest != "help"]

    def test_canonical_aliases_and_defaults_are_stable(self):
        self.assertEqual(EXPECTED_ACTIONS, self._action_table())

    def test_train_disables_test(self):
        args = self.module.ClassfierOptionParser(["--train", "true", "--test", "true"])
        self.assertTrue(args.train)
        self.assertFalse(args.test)

    def test_false_train_and_test_normalizes_to_test(self):
        args = self.module.ClassfierOptionParser(["--train", "false", "--test", "false"])
        self.assertFalse(args.train)
        self.assertTrue(args.test)

    def test_convert_to_args_str_preserves_legacy_iteration_and_filtering(self):
        args = argparse.Namespace(empty="", false=False, zero=0, none=None,
                                  path="directory with spaces")
        self.assertEqual(
            " --false False --zero 0 --none None --path directory with spaces",
            self.module.convert_to_args_str(args),
        )

    def test_contract_assertions_detect_controlled_drift(self):
        altered = list(EXPECTED_ACTIONS)
        dest, aliases, default = altered[0]
        altered[0] = (dest, aliases[:-1], not default)
        with self.assertRaises(AssertionError):
            self.assertEqual(EXPECTED_ACTIONS, altered)

        drifted_forwarding = " --zero 0 --none None --path directory with spaces"
        with self.assertRaises(AssertionError):
            self.assertEqual(
                " --false False --zero 0 --none None --path directory with spaces",
                drifted_forwarding,
            )


if __name__ == "__main__":
    unittest.main()
