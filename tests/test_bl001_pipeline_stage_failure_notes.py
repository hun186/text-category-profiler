"""BL-001: stage-aware original error, no replay, no downstream work."""
import ast
from argparse import Namespace
from pathlib import Path
import unittest

from text_category_profiler.pipeline.orchestrator import PipelineOrchestrator


PORTS = ("convert", "classify", "combine", "visualize", "merge", "deliver")


def execution(*, failed=None, test=True, task="SDSMS"):
    calls = []
    original = RuntimeError("private operator diagnostic")
    def port(name):
        def invoke():
            calls.append(name)
            if name == failed:
                raise original
        return invoke
    context = type("Context", (), {})()
    context.args = Namespace(test=test, task=task)
    orchestrator = PipelineOrchestrator(
        context, **{name: port(name) for name in PORTS}
    )
    return orchestrator, calls, original


class PipelineStageFailureContextTests(unittest.TestCase):
    def test_each_stage_failure_preserves_identity_and_stops_downstream(self):
        for index, failed in enumerate(PORTS):
            with self.subTest(stage=failed):
                orchestrator, calls, original = execution(failed=failed)
                with self.assertRaises(RuntimeError) as caught:
                    orchestrator.run()
                self.assertIs(caught.exception, original)
                self.assertEqual(calls, list(PORTS[:index + 1]))
                notes = getattr(original, "__notes__", ())
                if hasattr(original, "add_note"):
                    self.assertEqual(notes, [
                        "TCP_PIPELINE_FAILED_STAGE=" + failed,
                    ])
                self.assertFalse(any("private operator" in note
                                     for note in notes))

    def test_non_test_run_never_calls_later_stages(self):
        orchestrator, calls, original = execution(test=False, failed="deliver")
        self.assertIsNone(orchestrator.run())
        self.assertEqual(calls, ["convert", "classify"])
        self.assertFalse(getattr(original, "__notes__", []))

    def test_non_sdsms_still_skips_merge(self):
        orchestrator, calls, original = execution(task="", failed="deliver")
        with self.assertRaises(RuntimeError) as caught:
            orchestrator.run()
        self.assertIs(caught.exception, original)
        self.assertEqual(
            calls, ["convert", "classify", "combine", "visualize", "deliver"]
        )

    def test_existing_error_note_is_not_duplicated(self):
        original = RuntimeError("failure")
        invoked = []
        def raise_original():
            invoked.append("run")
            raise original
        for _ in range(2):
            with self.assertRaises(RuntimeError) as result:
                PipelineOrchestrator._run_named_stage("classify", raise_original)
            self.assertIs(result.exception, original)
        self.assertEqual(len(invoked), 2)
        if hasattr(original, "add_note"):
            self.assertEqual(
                getattr(original, "__notes__", ()),
                ["TCP_PIPELINE_FAILED_STAGE=classify"]
            )

    def test_base_exception_interrupt_does_not_trigger_replay(self):
        called = []
        def interrupt():
            called.append(1)
            raise KeyboardInterrupt("interrupted")
        with self.assertRaises(KeyboardInterrupt):
            PipelineOrchestrator._run_named_stage("classify", interrupt)
        self.assertEqual(called, [1])

    def test_no_stage_implementations_or_filesystem_imported(self):
        path = (Path(__file__).resolve().parents[1]
                / "text_category_profiler/pipeline/orchestrator.py")
        source = ast.parse(path.read_text(encoding="utf-8"))
        self.assertFalse(any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            for node in ast.walk(source)
        ))


if __name__ == "__main__":
    unittest.main()
