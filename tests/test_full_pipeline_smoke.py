import os
from pathlib import Path
import sqlite3
import unittest

from tests.smoke.full_pipeline_harness import (
    SmokeConfig,
    cleanup_runtime_root,
    format_failure,
    run_full_pipeline,
    snapshot_regular_files,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "full_pipeline_smoke"
RUNNING_SUFFIXES = (
    "_is_running_DataConverter",
    "_is_running_RunClassfier",
    "_is_running_CombineTestResult",
    "_is_running_TestResultVis",
)


def _directory_entries(path):
    return tuple(sorted(item.name for item in path.iterdir())) if path.is_dir() else ()


@unittest.skipUnless(
    os.environ.get("TCP_RUN_FULL_PIPELINE_SMOKE") == "1",
    "set TCP_RUN_FULL_PIPELINE_SMOKE=1 to run isolated root full-pipeline smoke",
)
class FullPipelineSmokeTests(unittest.TestCase):
    def test_real_root_pipeline_reaches_spike_handoff(self):
        default_workpool = ROOT / "WorkPool"
        before = _directory_entries(default_workpool)
        source_model = FIXTURES / "model"
        model_before = snapshot_regular_files(source_model)
        result = run_full_pipeline(
            SmokeConfig(
                repository_root=ROOT,
                fixed_test_dir=FIXTURES / "fixed_test" / "Using",
                topic_tree_dir=FIXTURES / "taxonomy",
                topic_tree_files="TopicTree_smoke.csv",
                model_dir=FIXTURES / "model",
            )
        )
        diagnostics = format_failure(result)
        try:
            self.assertFalse(result.timed_out, diagnostics)
            self.assertEqual(result.returncode, 0, diagnostics)
            self.assertNotIn("Traceback (most recent call last)", result.stdout, diagnostics)
            self.assertNotIn("Traceback (most recent call last)", result.stderr, diagnostics)

            marker_lines = result.classifier_marker.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(marker_lines), 1, diagnostics)
            final_workspaces = [
                workspace for workspace in result.workspaces
                if workspace.name.endswith("_rdy_for_Spike")
            ]
            self.assertEqual(len(final_workspaces), 1, diagnostics)
            self.assertFalse(
                any(workspace.name.endswith(RUNNING_SUFFIXES) for workspace in result.workspaces),
                diagnostics,
            )
            workspace = final_workspaces[0]
            required = ["test.tsv", "test.sql3", "test_results.tsv"]
            for filename in required:
                artifact = workspace / filename
                self.assertTrue(artifact.is_file() and artifact.stat().st_size > 0, diagnostics)

            verification = workspace / "test_results_verification.sql3"
            self.assertTrue(verification.is_file(), diagnostics)
            with sqlite3.connect(workspace / "test.sql3") as connection:
                source_count = connection.execute("SELECT COUNT(*) FROM sampleSrc").fetchone()[0]
            with sqlite3.connect(verification) as connection:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
                self.assertTrue(tables, diagnostics)
                result_count = connection.execute(
                    f'SELECT COUNT(*) FROM "{tables[0][0]}"'
                ).fetchone()[0]
            self.assertEqual(result_count, source_count, diagnostics)
            visualization_log = workspace / "logs" / "Test_result_Vis.log"
            self.assertTrue(visualization_log.is_file(), diagnostics)
            self.assertEqual(_directory_entries(default_workpool), before, diagnostics)
        finally:
            try:
                self.assertEqual(snapshot_regular_files(source_model), model_before)
            finally:
                cleanup_runtime_root(result.runtime_root, ROOT)


if __name__ == "__main__":
    unittest.main()
