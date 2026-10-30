"""Dependency-light evidence for the historical Tulip graph-demo boundary.

No real Tulip/tulipgui, model, ES, filesystem writes or GUI are used.
"""
import hashlib
import importlib
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "text_category_profiler/tulip_utils/Graph_Builder.py"
NEW = ROOT / "experiments/tulip_graph_builder.py"
README = ROOT / "experiments/tulip_graph_builder.README.md"
ORIGINAL_BLOB = "8d6919e56381e30003c7582ecb78f0490f04c857"
ORIGINAL_SIZE = 24232
SYMBOLS = (
    "ShowElapsedTime", "ExtractNodes", "find_id_src_tar",
    "find_id_of_viewLabel", "BuildEdges", "NodeLabeltoIdTable",
    "graph_global_references", "BuildGraph", "Compute_degree_of_graph",
    "set_groupID_Property", "ClusterMetaNodeGraph",
    "Create_Node_Link_Diagram_view", "load_params_specified",
    "ApplyLayoutEffect", "ShowViews",
)


def blob_sha(data):
    prefix = ("blob %d" % len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + data).hexdigest()


class TulipManualGraphBoundaryTests(unittest.TestCase):
    def test_original_experiment_source_byte_identity(self):
        source = NEW.read_bytes()
        self.assertEqual(len(source), ORIGINAL_SIZE)
        self.assertEqual(blob_sha(source), ORIGINAL_BLOB)
        self.assertNotEqual(OLD.read_bytes(), source)

    def test_legacy_facade_import_does_not_require_tulip(self):
        process = subprocess.run(
            [sys.executable, "-c",
             "import sys; "
             "import text_category_profiler.tulip_utils.Graph_Builder as m; "
             "assert 'tulip' not in sys.modules; "
             "assert 'tulipgui' not in sys.modules; "
             "assert 'experiments.tulip_graph_builder' not in sys.modules; "
             "assert callable(m.main)"],
            cwd=ROOT, text=True, capture_output=True, timeout=20, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_legacy_public_attributes_are_lazy_proxies(self):
        legacy = importlib.import_module(
            "text_category_profiler.tulip_utils.Graph_Builder"
        )
        self.assertEqual(tuple(legacy.__all__), SYMBOLS)
        payload = SimpleNamespace(**{name: object() for name in SYMBOLS},
                                  tlp=object(), time=object())
        with mock.patch.object(legacy, "import_module", return_value=payload) as loader:
            for name in SYMBOLS + ("tlp", "time"):
                self.assertIs(getattr(legacy, name), getattr(payload, name))
            with self.assertRaises(AttributeError):
                getattr(legacy, "_private")
            with self.assertRaises(AttributeError):
                getattr(legacy, "not_a_real_symbol")
        self.assertEqual(loader.call_count, len(SYMBOLS) + 3)
        self.assertTrue(all(
            call.args == ("experiments.tulip_graph_builder",)
            for call in loader.call_args_list
        ))

    def test_direct_script_invokes_historical_demo_only_when_called(self):
        legacy = importlib.import_module(
            "text_category_profiler.tulip_utils.Graph_Builder"
        )
        with mock.patch.object(legacy.runpy, "run_path") as runner:
            legacy.main()
        runner.assert_called_once_with(str(NEW), run_name="__main__")

    def test_first_party_sources_do_not_use_removed_file_as_data(self):
        # This is a lexical, in-checkout scan. Dynamic/manual external imports
        # are unverified; don't silently delete the compatibility path.
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.py"],
            cwd=ROOT, capture_output=True, check=True, timeout=20,
        )
        offenders = []
        for raw_name in proc.stdout.split(b"\0"):
            if not raw_name:
                continue
            name = raw_name.decode("utf-8", errors="surrogateescape")
            path = ROOT / name
            if path in (OLD, Path(__file__).resolve()) or not path.is_file():
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            if "tulip_utils/Graph_Builder.py" in source or (
                "tulip_utils.Graph_Builder" in source and not name.startswith("tests/")
            ):
                offenders.append(name)
        self.assertEqual(offenders, [], "Investigate caller before removing shim")

    def test_documentation_preserves_optional_dependency_and_provenance(self):
        source = README.read_text(encoding="utf-8")
        for value in (
            "experiments/tulip_graph_builder.py",
            "text_category_profiler/tulip_utils/Graph_Builder.py",
            ORIGINAL_BLOB,
            "unverified",
            "Tulip",
        ):
            self.assertIn(value, source)


if __name__ == "__main__":
    unittest.main()
