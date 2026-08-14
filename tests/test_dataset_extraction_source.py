import sys
import types
import unittest
from unittest.mock import patch

from DatasetConverter.adapters.extraction_source import build_czj_corpus
from DatasetConverter.adapters.extraction_source import get_extraction_rule
from DatasetConverter.adapters.extraction_source import run_extraction


class DatasetExtractionSourceTests(unittest.TestCase):
    def test_rule_lookup_preserves_legacy_mapping_identity(self):
        selected = {"fileNames": ["sample.csv"]}
        module = types.ModuleType("DatasetConverter.EXTConverter.ExtractionRule")
        module.ExtractionRuleDict = {"task": selected}

        with patch.dict(sys.modules, {module.__name__: module}):
            self.assertIs(get_extraction_rule("task"), selected)

    def test_extractor_receives_legacy_keyword_contract(self):
        calls = []
        module = types.ModuleType("DatasetConverter.EXTConverter.ExtractionConverter")
        module.Extractor = lambda **kwargs: calls.append(kwargs) or "result"
        job_info = {"DirName": "work"}

        with patch.dict(sys.modules, {module.__name__: module}):
            result = run_extraction("task", job_info=job_info)

        self.assertEqual(result, "result")
        self.assertEqual(
            calls,
            [{"task": "task", "FileNameInSQL3": False, "JobInfo": job_info}],
        )

    def test_corpus_builder_receives_paths_and_runs_transformer(self):
        calls = []

        class FakeBuilder:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))

            def Transformer(self):
                calls.append(("transform",))
                return "corpus"

        module = types.ModuleType("DatasetConverter.EXTConverter.Combiner")
        module.CZJCorpusFileBuilder = FakeBuilder

        with patch.dict(sys.modules, {module.__name__: module}):
            result = build_czj_corpus(source_path="source.sql3", output_path="out.sql3")

        self.assertEqual(result, "corpus")
        self.assertEqual(
            calls,
            [
                (
                    "init",
                    {
                        "SourceCZJSampleFN": "source.sql3",
                        "OutputCZJCorpusFN": "out.sql3",
                    },
                ),
                ("transform",),
            ],
        )


if __name__ == "__main__":
    unittest.main()
