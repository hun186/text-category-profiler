import contextlib
import io
import unittest

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
UTILS = ROOT / "PythonModule"
if str(UTILS) not in sys.path:
    sys.path.insert(0, str(UTILS))

from utils.core import log_display


class LogDisplayTests(unittest.TestCase):
    def capture(self, func, *args, **kwargs):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            func(*args, **kwargs)
        return buffer.getvalue()

    def test_summarize_sequence_truncates_long_lists(self):
        result = log_display.summarize_sequence(["a", "b", "c", "d"], limit=2)
        self.assertEqual(result, "['a', 'b'] ... (+2 more)")

    def test_key_values_wraps_and_skips_empty_values(self):
        output = self.capture(
            log_display.key_values,
            "Settings",
            [("dataset", "WorkPool/demo"), ("empty", ""), ("model", "BertScript/output")],
            icon="·",
        )
        self.assertIn("Settings", output)
        self.assertIn("dataset", output)
        self.assertIn("WorkPool/demo", output)
        self.assertIn("model", output)
        self.assertNotIn("empty", output)

    def test_print_command_keeps_copyable_command_parts(self):
        output = self.capture(
            log_display.print_command,
            "python DatasetConverter/DataConverter.py --TRVPort 8050 --ModelType PytorchXLM",
            label="DataConverter command",
        )
        self.assertIn("DataConverter command", output)
        self.assertIn("python", output)
        self.assertIn("DatasetConverter/DataConverter.py", output)
        self.assertIn("--TRVPort", output)
        self.assertIn("8050", output)

    def test_print_command_groups_multiple_args_on_each_line(self):
        output = self.capture(
            log_display.print_command,
            "python DatasetConverter/DataConverter.py "
            "--debugMode False --TRVPort 8050 --public False --train False "
            "--test True --ExecutionTime 20260805195938 --WorkPoolROOT WorkPool",
            label="DataConverter command",
        )
        self.assertIn("--debugMode False --TRVPort 8050", output)
        self.assertLess(output.count("\n"), 8)


    def test_print_once_suppresses_duplicate_messages(self):
        key = "test-print-once-duplicate-key"
        first = self.capture(log_display.print_once, "hello once", key=key)
        second = self.capture(log_display.print_once, "hello once", key=key)
        self.assertEqual(first, "hello once\n")
        self.assertEqual(second, "")

    def test_dataframe_summary_accepts_dataframe_like_objects(self):
        class FrameLike:
            shape = (3, 2)
            columns = ["Type", "pred_Type"]

            def head(self, max_rows):
                return f"head({max_rows})"

        output = self.capture(log_display.dataframe_summary, FrameLike(), label="Preview")
        self.assertIn("Preview", output)
        self.assertIn("(3, 2)", output)
        self.assertIn("Type", output)
        self.assertIn("head(6)", output)


if __name__ == "__main__":
    unittest.main()
