import ast
from argparse import Namespace
from pathlib import Path
import unittest


from text_category_profiler.pipeline.configuration import PipelineContext
from text_category_profiler.pipeline.orchestrator import PipelineOrchestrator


ROOT = Path(__file__).resolve().parents[1]


def context(*, test=True, task=""):
    return PipelineContext(
        args=Namespace(test=test, task=task),
        root_paths=(),
        final_output_patterns=(),
        run_mode="test",
    )


class PipelineOrchestratorTests(unittest.TestCase):
    def orchestrator(self, pipeline_context, trace, **overrides):
        ports = {
            name: (lambda name=name: trace.append(name))
            for name in ("convert", "classify", "combine", "visualize", "merge", "deliver")
        }
        ports.update(overrides)
        return PipelineOrchestrator(pipeline_context, **ports)

    def test_test_pipeline_runs_four_stages_in_order(self):
        trace = []
        self.orchestrator(context(), trace).run()
        self.assertEqual(
            ["convert", "classify", "combine", "visualize", "deliver"], trace
        )

    def test_non_test_pipeline_stops_after_classifier(self):
        trace = []
        self.orchestrator(context(test=False), trace).run()
        self.assertEqual(["convert", "classify"], trace)

    def test_failure_prevents_following_stages(self):
        trace = []

        def fail():
            trace.append("classify")
            raise RuntimeError("classifier failed")

        with self.assertRaisesRegex(RuntimeError, "classifier failed"):
            self.orchestrator(context(), trace, classify=fail).run()
        self.assertEqual(["convert", "classify"], trace)

    def test_sdsms_merge_precedes_delivery(self):
        for task in ("SDSMS", "SDSMS_Prediction"):
            with self.subTest(task=task):
                trace = []
                self.orchestrator(context(task=task), trace).run()
                self.assertEqual(
                    ["convert", "classify", "combine", "visualize", "merge", "deliver"],
                    trace,
                )

    def test_stage_ports_do_not_import_stage_implementations(self):
        source = (ROOT / "text_category_profiler/pipeline/orchestrator.py").read_text(
            encoding="utf-8"
        )
        imports = {
            node.module or ""
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom)
        }
        imports.update(
            alias.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden = ("DatasetConverter", "BertScript", "filesystem", "execution")
        self.assertFalse(
            [name for name in imports if any(token in name for token in forbidden)]
        )


if __name__ == "__main__":
    unittest.main()
