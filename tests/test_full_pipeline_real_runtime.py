import os
from pathlib import Path
import unittest

from text_category_profiler.diagnostics.full_pipeline import (
    cleanup_runtime_root,
    config_from_real_runtime_environment,
    format_failure,
    parse_classifier_device,
    run_full_pipeline,
    snapshot_directories,
    snapshot_regular_files,
)


ROOT = Path(__file__).resolve().parents[1]
@unittest.skipUnless(
    os.environ.get("TCP_RUN_REAL_PIPELINE_SMOKE") == "1",
    "set TCP_RUN_REAL_PIPELINE_SMOKE=1 to run real-model full-pipeline smoke; "
    "TCP_REAL_PORT and TCP_REAL_MODEL_TYPE are optional selectors and resource "
    "path variables are optional overrides",
)
class FullPipelineRealRuntimeTests(unittest.TestCase):
    def test_real_model_root_pipeline_reaches_spike_handoff(self):
        source_config = config_from_real_runtime_environment(ROOT, os.environ)
        fixed_before = snapshot_directories(source_config.fixed_test_dirs)
        model_before = snapshot_regular_files(source_config.model_dir)

        # The harness owns the temporary runtime root, so obtain it from a facade
        # factory hook rather than ever making the external model writable.
        result = run_full_pipeline(source_config, use_model_facade=True)
        diagnostics = format_failure(result)
        try:
            self.assertEqual(snapshot_directories(source_config.fixed_test_dirs), fixed_before)
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
            device, cuda_available, gpu_name = parse_classifier_device(evidence)
            self.assertIsNotNone(device, diagnostics)
            print(f"real pipeline classifier device: {device}; "
                  f"torch CUDA available: {cuda_available}; GPU: {gpu_name}")
        finally:
            cleanup_runtime_root(result.runtime_root, ROOT)


if __name__ == "__main__":
    unittest.main()
