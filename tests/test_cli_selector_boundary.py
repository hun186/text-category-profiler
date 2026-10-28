"""Characterize the legacy terminal selector when isolated under cli/."""
from contextlib import redirect_stdout
import hashlib
import importlib
import io
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "text_category_profiler" / "cli" / "selector.py"
HISTORICAL_BLOB = "136a4caea6f9ad7858d9ca15cbe7c6308a60165a"


class SelectorBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_colors = types.ModuleType("colorama")
        fake_colors.Fore = types.SimpleNamespace(LIGHTYELLOW_EX="<yellow>", RESET="<reset>")
        fake_colors.Back = types.SimpleNamespace()
        fake_colors.Style = types.SimpleNamespace()
        cls.module_patch = mock.patch.dict(sys.modules, {"colorama": fake_colors})
        cls.module_patch.start()
        # No heavy dependencies or terminal calls are required on import.
        with mock.patch("builtins.input", side_effect=AssertionError("input on import")):
            cls.legacy = importlib.import_module("text_category_profiler.selector")
            cls.canonical = importlib.import_module("text_category_profiler.cli.selector")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("text_category_profiler.selector", None)
        sys.modules.pop("text_category_profiler.cli.selector", None)
        cls.module_patch.stop()

    def test_canonical_source_identical_to_original_git_blob(self):
        data = CANONICAL.read_bytes()
        git_blob = hashlib.sha1(
            ("blob %d" % len(data)).encode("ascii") + bytes([0]) + data
        ).hexdigest()
        self.assertEqual(git_blob, HISTORICAL_BLOB)

    def test_legacy_symbols_are_original_classes_and_colors(self):
        for name in ("OptionSelector", "MultiOptionSelector",
                     "InteractiveOptionSelector", "Fore", "Back", "Style"):
            with self.subTest(name=name):
                self.assertIs(getattr(self.legacy, name), getattr(self.canonical, name))

    def test_single_selector_numeric_choice_and_default(self):
        subject = self.legacy.OptionSelector(
            options={"a": "Alpha", "b": "Beta"}, default="b")
        with mock.patch("builtins.input", return_value=""), redirect_stdout(io.StringIO()):
            self.assertEqual(subject.proc(), "b")
        with mock.patch("builtins.input", return_value="1"), redirect_stdout(io.StringIO()):
            self.assertEqual(subject.proc(), "a")

    def test_single_selector_invalid_choice_retries(self):
        subject = self.legacy.OptionSelector(options={"a": "Alpha", "b": "Beta"})
        with mock.patch("builtins.input", side_effect=["0", "2"]), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(subject.proc(), "b")
        self.assertIn("無效的選項", out.getvalue())

    def test_multi_selector_numeric_input_and_unchanged_default_identity(self):
        default = ["b"]
        subject = self.legacy.MultiOptionSelector(
            options={"a": "Alpha", "b": "Beta", "c": "Gamma"}, default=default)
        with mock.patch("builtins.input", return_value=""), redirect_stdout(io.StringIO()):
            self.assertIs(subject.proc(), default)
        with mock.patch("builtins.input", return_value="1, 3"), redirect_stdout(io.StringIO()):
            self.assertEqual(subject.proc(), ["a", "c"])

    def test_multi_selector_invalid_input_retries(self):
        subject = self.legacy.MultiOptionSelector(options={"x": "One", "y": "Two"})
        with mock.patch("builtins.input", side_effect=["bad", "2"]), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(subject.proc(), ["y"])
        self.assertIn("輸入格式錯誤", out.getvalue())

    def test_curses_is_only_started_for_explicit_interactive_proc(self):
        fake = types.ModuleType("curses")
        fake.KEY_UP = 259
        fake.KEY_DOWN = 258
        fake.noecho = mock.Mock()
        fake.cbreak = mock.Mock()
        fake.endwin = mock.Mock()
        fake_window = mock.Mock()
        fake_window.getch.side_effect = [fake.KEY_DOWN, 10, 10]
        fake.initscr = mock.Mock(return_value=fake_window)
        with mock.patch.dict(sys.modules, {"curses": fake}):
            instance = self.legacy.InteractiveOptionSelector(
                options={"a": "Alpha", "b": "Beta"})
            fake.initscr.assert_not_called()
            selected = instance.proc()
        self.assertEqual(selected, ("b", "Beta"))
        fake.initscr.assert_called_once_with()
        fake.endwin.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
