"""Regression tests for the MIT Dijkstra vendor boundary and legacy entrypoint."""
from collections import deque
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from vendor.dijkstra_algorithm_master import dijkstra_algorithm as upstream
from text_category_profiler.dijkstra_algorithm_master import dijkstra_algorithm as legacy


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "text_category_profiler" / "dijkstra_algorithm_master"
VENDOR = ROOT / "vendor" / "dijkstra_algorithm_master"


class DijkstraVendorBoundaryTests(unittest.TestCase):
    def test_original_implementation_and_license_were_preserved(self):
        # This is a relocation, not an algorithm modification or relicense.
        for filename in ("LICENSE", "README.md", "simple_graph.txt", "seattle_area.txt"):
            self.assertTrue((VENDOR / filename).is_file())
        self.assertEqual((OLD / "LICENSE").read_bytes(), (VENDOR / "LICENSE").read_bytes())
        self.assertEqual((OLD / "simple_graph.txt").read_bytes(),
                         (VENDOR / "simple_graph.txt").read_bytes())
        self.assertEqual((OLD / "seattle_area.txt").read_bytes(),
                         (VENDOR / "seattle_area.txt").read_bytes())
        self.assertIn("MIT License", (VENDOR / "LICENSE").read_text())
        self.assertIn("Doug Mahugh", (VENDOR / "LICENSE").read_text())

    def test_old_module_exports_unmodified_vendor_symbols(self):
        self.assertIs(legacy.Graph, upstream.Graph)
        self.assertIs(legacy.verify_algorithm, upstream.verify_algorithm)
        self.assertIs(legacy.INFINITY, upstream.INFINITY)
        with self.assertRaises(AttributeError):
            getattr(legacy, "unknown_symbol")

    def test_importing_either_file_is_inert(self):
        for target in (OLD / "dijkstra_algorithm.py", VENDOR / "dijkstra_algorithm.py"):
            with self.subTest(target=target.name), tempfile.TemporaryDirectory() as temp:
                previous = Path.cwd()
                try:
                    os.chdir(temp)
                    with redirect_stdout(io.StringIO()) as output:
                        namespace = runpy.run_path(str(target), run_name="import_check")
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(list(Path(temp).iterdir()), [])
                    self.assertIn("main", namespace)
                finally:
                    os.chdir(previous)

    def test_shortest_path_contract_on_original_fixtures(self):
        cases = (
            ("simple_graph.txt", "A", "G", ["A", "D", "E", "G"], 11),
            ("seattle_area.txt", "Renton", "Redmond",
             ["Renton", "Factoria", "Bellevue", "Northup", "Redmond"], 16),
            ("seattle_area.txt", "Seattle", "Redmond",
             ["Seattle", "Eastlake", "Northup", "Redmond"], 15),
            ("seattle_area.txt", "Eastlake", "Issaquah",
             ["Eastlake", "Seattle", "SoDo", "Factoria", "Issaquah"], 21),
        )
        for filename, start, end, expected_path, expected_distance in cases:
            with self.subTest(start=start, end=end):
                path, distance = legacy.Graph(str(VENDOR / filename)).shortest_path(
                    start, end
                )
                self.assertIsInstance(path, deque)
                self.assertEqual(list(path), expected_path)
                self.assertEqual(distance, expected_distance)

    def test_both_direct_run_paths_still_read_graph_fixtures_from_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            for filename in ("simple_graph.txt", "seattle_area.txt"):
                shutil.copyfile(VENDOR / filename, Path(temp) / filename)
            for target in (OLD / "dijkstra_algorithm.py", VENDOR / "dijkstra_algorithm.py"):
                with self.subTest(path=target):
                    result = subprocess.run(
                        [sys.executable, str(target)], cwd=temp,
                        capture_output=True, text=True, timeout=15, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.count("shortest path:"), 4)
            self.assertEqual(
                {p.name for p in Path(temp).iterdir()},
                {"simple_graph.txt", "seattle_area.txt"},
            )

    def test_legacy_main_only_delegates_to_vendor_on_explicit_call(self):
        with mock.patch("runpy.run_path") as dispatcher:
            legacy.main()
        dispatcher.assert_called_once_with(
            str(VENDOR / "dijkstra_algorithm.py"), run_name="__main__"
        )


if __name__ == "__main__":
    unittest.main()
