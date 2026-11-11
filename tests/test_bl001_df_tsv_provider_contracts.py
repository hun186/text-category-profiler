"""BL-001 isolated contracts for legacy and canonical dfToTSV providers.

Only a single function AST is executed with in-memory stubs; actual pandas,
multiprocessing, filesystem I/O, classifier and WorkPool are never loaded.
"""
import ast
import csv
from pathlib import Path
import tempfile
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
        # The default nonquoting dialect now matches the two Stage-local
        # writers again, but the canonical resource probe and extended
        # adapter/index/header parameters remain separate public semantics.
        self.assertEqual(sink.calls, legacy_sink.calls)
        self.assertIsNone(sink.calls[0][1]["quotechar"])

        fn(sink, "changed.tsv", tsvIndex=True, header=True, TSVTextAdapter=True)
        self.assertEqual(calls[2:], [
            ("init", None), ("compute", False), ("init", 3),
            ("parallel", "adapter"),
        ])
        self.assertEqual(sink.calls[-1][1]["index"], True)
        self.assertEqual(sink.calls[-1][1]["header"], True)

    def test_private_pandas_canonical_tsv_bytes_and_extended_options(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas is optional for dependency-light discovery")

        calls = []

        class FakeMulticore:
            def __init__(self, nProcess=None):
                calls.append(("init", nProcess))

            def ComputeNProcess(self, log=False):
                calls.append(("probe", log))
                return 2

            def parallelize_dataframe(self, frame, adapter):
                calls.append(("adapter", adapter))
                return frame

        canonical = isolated_tsv_function(
            CANONICAL, multicoreJob=FakeMulticore, DFTSVTextAdapter="fixture",
        )
        stage = isolated_tsv_function(LEGACY[0])
        df = pd.DataFrame({
            "text": ["中文\\反斜線", "含Tab\t及換行\n"],
            "label": ["TW Affairs", "TW Security"],
        })
        with tempfile.TemporaryDirectory(prefix="bl001-canonical-tsv-") as tmp:
            canonical_file = Path(tmp) / "canonical.tsv"
            stage_file = Path(tmp) / "stage.tsv"
            canonical(df, canonical_file)
            stage(df, stage_file)
            data = canonical_file.read_bytes()
            self.assertEqual(data, stage_file.read_bytes())
            self.assertIn("中文".encode("utf-8"), data)
            self.assertIn(b"\\\\", data, "Backslash must be escaped")
            self.assertIn(b"\\\t", data, "Tabs must be escaped")
            self.assertIn(b"\\\n", data, "Newlines must be escaped")
            self.assertEqual(calls, [("init", None), ("probe", False)])

            # Old pandas accepted quotechar=''; where it does, output bytes
            # must be identical. Pandas 3.x does not accept the old option.
            legacy = Path(tmp) / "historical-dialect.tsv"
            try:
                df.to_csv(
                    legacy, sep="\t", index=False, quoting=csv.QUOTE_NONE,
                    quotechar="", escapechar="\\", header=False,
                    encoding="utf-8",
                )
            except (TypeError, ValueError):
                pass
            else:
                self.assertEqual(data, legacy.read_bytes())

            # Canonical's extended options and resource-probe ordering are
            # deliberately retained; stage-local only supports two args.
            configured = Path(tmp) / "configured.tsv"
            canonical(df, configured, tsvIndex=True, header=True,
                      TSVTextAdapter=True)
            expected = Path(tmp) / "configured-reference.tsv"
            df.to_csv(
                expected, sep="\t", index=True, quoting=csv.QUOTE_NONE,
                quotechar=None, escapechar="\\", header=True,
                encoding="utf-8",
            )
            self.assertEqual(configured.read_bytes(), expected.read_bytes())
            self.assertEqual(calls[-4:], [
                ("init", None), ("probe", False),
                ("init", 2), ("adapter", "fixture"),
            ])

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
