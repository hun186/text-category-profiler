import os
from pathlib import Path
import unittest

from tests.smoke.full_pipeline_harness import (
    cleanup_runtime_root,
    config_from_real_runtime_environment,
    format_failure,
    run_full_pipeline,
    snapshot_regular_files,
)


ROOT = Path(__file__).resolve().parents[1]
@unittest.skipUnless(
    os.environ.get("TCP_RUN_REAL_PIPELINE_SMOKE") == "1",
    "set TCP_RUN_REAL_PIPELINE_SMOKE=1 and TCP_REAL_MODEL_DIR, "
    "TCP_REAL_FIXED_TEST_DIR, TCP_REAL_TOPIC_TREE_DIR, and "
    "TCP_REAL_TOPIC_TREE_FILES to run real-model full-pipeline smoke",
)
class FullPipelineRealRuntimeTests(unittest.TestCase):
    def test_real_model_root_pipeline_reaches_spike_handoff(self):
        source_config = config_from_real_runtime_environment(ROOT, os.environ)
        fixed_before = snapshot_regular_files(source_config.fixed_test_dir)
        model_before = snapshot_regular_files(source_config.model_dir)

        # The harness owns the temporary runtime root, so obtain it from a facade
        # factory hook rather than ever making the external model writable.
        result = run_full_pipeline(source_config, use_model_facade=True)
        diagnostics = format_failure(result)
        try:
            self.assertEqual(snapshot_regular_files(source_config.fixed_test_dir), fixed_before)
            self.assertEqual(snapshot_regular_files(source_config.model_dir), model_before)
            self.assertFalse(result.timed_out, diagnostics)
            self.assertEqual(result.returncode, 0, diagnostics)
            self.assertIsNone(result.classifier_marker, diagnostics)
            finals = [path for path in result.workspaces if path.name.endswith("_rdy_for_Spike")]
            self.assertEqual(len(finals), 1, diagnostics)
            log = finals[0] / "logs" / "RunClassfier.log"
            evidence = result.stdout + "\n" + result.stderr
            if log.is_file():
                evidence += "\n" + log.read_text(encoding="utf-8", errors="replace")
            self.assertIn("TextClassification_transformers.py", evidence, diagnostics)
            cuda_lines = [
                line for line in evidence.splitlines()
                if "cuda" in line.lower() or "gpu memory" in line.lower()
            ]
            selection = "CUDA selected" if cuda_lines else "CUDA selection not evidenced (CPU possible)"
            print(f"real pipeline classifier device: {selection}")
            for line in cuda_lines[-10:]:
                print(f"  {line}")
        finally:
            cleanup_runtime_root(result.runtime_root, ROOT)


if __name__ == "__main__":
    unittest.main()
