"""BL-001: faulting exception-note handlers must never alter stage failures."""
import unittest

from text_category_profiler.pipeline.orchestrator import PipelineOrchestrator


class BadAddNote(RuntimeError):
    def add_note(self, note):
        raise ValueError("custom add_note failed")


class BadNotesProperty(RuntimeError):
    @property
    def __notes__(self):
        raise ValueError("custom __notes__ failed")


class MissingNoteSupport(RuntimeError):
    add_note = None


class StageNoteFailureIsolationTests(unittest.TestCase):
    def test_bad_custom_add_note_cannot_replace_original_failure(self):
        err = BadAddNote("original stage failure")
        events = []
        def fail():
            events.append("stage")
            raise err
        with self.assertRaises(BadAddNote) as raised:
            PipelineOrchestrator._run_named_stage("classify", fail)
        self.assertIs(raised.exception, err)
        self.assertEqual(events, ["stage"])

    def test_bad_notes_attribute_cannot_replace_original_failure(self):
        err = BadNotesProperty("original stage failure")
        def fail():
            raise err
        with self.assertRaises(BadNotesProperty) as raised:
            PipelineOrchestrator._run_named_stage("combine", fail)
        self.assertIs(raised.exception, err)

    def test_unavailable_custom_add_note_preserves_legacy_exception(self):
        err = MissingNoteSupport("original stage failure")
        def fail():
            raise err
        with self.assertRaises(MissingNoteSupport) as raised:
            PipelineOrchestrator._run_named_stage("deliver", fail)
        self.assertIs(raised.exception, err)

    def test_standard_exception_remains_annotated_once(self):
        err = RuntimeError("original stage failure")
        def fail():
            raise err
        for _ in range(2):
            with self.assertRaises(RuntimeError) as raised:
                PipelineOrchestrator._run_named_stage("convert", fail)
            self.assertIs(raised.exception, err)
        if hasattr(err, "add_note"):
            self.assertEqual(
                getattr(err, "__notes__", []),
                ["TCP_PIPELINE_FAILED_STAGE=convert"],
            )

    def test_keyboard_interrupt_remains_uncaught(self):
        err = KeyboardInterrupt("operator")
        def fail():
            raise err
        with self.assertRaises(KeyboardInterrupt) as caught:
            PipelineOrchestrator._run_named_stage("visualize", fail)
        self.assertIs(caught.exception, err)
        self.assertFalse(getattr(err, "__notes__", ()))


if __name__ == "__main__":
    unittest.main()
