"""BL-001 isolated contracts for legacy and canonical dfToTSV providers.

Only a single function AST is executed with in-memory stubs; actual pandas,
multiprocessing, filesystem I/O, classifier and WorkPool are never loaded.
"""
import ast
import csv
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LEGACY = (
    "DatasetConverter/df_utils.py",
    "BertScript/df_utils.py",
)
CANONICAL = "text_category_profiler/data/df_utils.py"


class Recorder:
    def __init__(self):
        self.calls = []

    def to_csv(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def isolated_tsv_function(path, **dependencies):
    source = (ROOT / path).read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=path)
    defs = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "dfToTSV"
    ]
    if len(defs) != 1:
        raise AssertionError(f"Expected exactly one dfToTSV: {path}")
    scope = {"csv": csv, **dependencies}
    # No target import or module-scope code execution.
    code = compile(ast.Module(body=defs, type_ignores=[]), path, "exec")
    exec(code, scope)
    return scope["dfToTSV"]


class StageLocalTSVContractTests(unittest.TestCase):
    def test_two_legacy_stage_exports_keep_identical_tsv_contract(self):
        observed = []
        for provider in LEGACY:
            with self.subTest(provider=provider):
                sink = Recorder()
                fn = isolated_tsv_function(provider)
                self.assertIsNone(fn(sink, "output.tsv"))
                self.assertEqual(len(sink.calls), 1)
                observed.append(sink.calls[0])
                with self.assertRaises(TypeError):
                    fn(sink, "output.tsv", header=True)
        self.assertEqual(observed[0], observed[1])
        args, kwargs = observed[0]
        self.assertEqual(args, ("output.tsv",))
        self.assertEqual(kwargs, {
            "sep": "\t", "index": False, "quoting": csv.QUOTE_NONE,
            "quotechar": None, "escapechar": "\\", "header": False,
            "encoding": "utf-8",
        })

    def test_canonical_default_csv_settings_match_but_probe_multiprocessing(self):
        calls = []

        class StubMulticore:
            def __init__(self, nProcess=None):
                calls.append(("init", nProcess))

            def ComputeNProcess(self, log=False):
                calls.append(("compute", log))
                return 3

            def parallelize_dataframe(self, df, adapter):
                calls.append(("parallel", adapter))
                return df

        fn = isolated_tsv_function(
            CANONICAL, multicoreJob=StubMulticore, DFTSVTextAdapter="adapter",
        )
        sink = Recorder()
        fn(sink, "output.tsv")
        self.assertEqual(len(sink.calls), 1)
        self.assertEqual(calls, [("init", None), ("compute", False)])
        legacy_sink = Recorder()
        isolated_tsv_function(LEGACY[0])(legacy_sink, "output.tsv")
        # The canonical provider retains its own historical empty-string
        # quotechar contract and multiprocessing probe. Stage-local providers
        # deliberately use None for modern pandas; their bytes stay unchanged
        # under QUOTE_NONE. Do not silently consolidate these distinct APIs.
        canonical_args, canonical_options = sink.calls[0]
        stage_args, stage_options = legacy_sink.calls[0]
        self.assertEqual(canonical_args, stage_args)
        self.assertEqual(canonical_options["quotechar"], "")
        self.assertIsNone(stage_options["quotechar"])
        self.assertEqual(
            {k: v for k, v in canonical_options.items() if k != "quotechar"},
            {k: v for k, v in stage_options.items() if k != "quotechar"},
        )

        fn(sink, "changed.tsv", tsvIndex=True, header=True, TSVTextAdapter=True)
        self.assertEqual(calls[2:], [
            ("init", None), ("compute", False), ("init", 3),
            ("parallel", "adapter"),
        ])
        self.assertEqual(sink.calls[-1][1]["index"], True)
        self.assertEqual(sink.calls[-1][1]["header"], True)

    def test_canonical_probe_failure_propagates_without_writing_tsv(self):
        class FailingMulticore:
            def ComputeNProcess(self, log=False):
                raise RuntimeError("injected resource probe failure")

        fn = isolated_tsv_function(CANONICAL, multicoreJob=FailingMulticore)
        sink = Recorder()
        with self.assertRaisesRegex(RuntimeError, "resource probe failure"):
            fn(sink, "should-not-write.tsv")
        self.assertEqual(sink.calls, [])
        legacy = isolated_tsv_function(LEGACY[1])
        legacy(sink, "stage-local.tsv")
        self.assertEqual(len(sink.calls), 1)


if __name__ == "__main__":
    unittest.main()
