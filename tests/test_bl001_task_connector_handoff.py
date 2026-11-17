"""Fail-closed stage directory handoff tests; PRIVATE tempfile only."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from tests.test_tcf_cli_contract import load_tcf_utils


class StageHandoffFailClosedTests(unittest.TestCase):
    def make_folders(self, base):
        src = Path(base) / "dataset_case_is_running_DataConverter"
        dst = Path(base) / "dataset_case_rdy_for_RunClassfier"
        src.mkdir()
        (src / "source.sql3").write_bytes(b"preserve-source")
        return src, dst

    @staticmethod
    def connector(module, src, log_file=""):
        return module.TaskConnector(
            SrcTask="DataConverter", DesTask="RunClassfier",
            WorkingDir=str(src), logFile=log_file,
        )

    def test_successful_legacy_rename_retains_files_and_no_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            calls = []
            def rename(**kwargs):
                calls.append(kwargs)
                os.rename(kwargs["SrcDir"], kwargs["DesDir"])
            module.RenameDir = rename
            self.assertIsNone(self.connector(module, src).proc())
            self.assertEqual(len(calls), 1)
            self.assertFalse(src.exists())
            self.assertEqual((dst / "source.sql3").read_bytes(), b"preserve-source")

    def test_silent_legacy_rename_failure_fails_after_bounded_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            calls = []
            module.RenameDir = lambda **kwargs: calls.append(kwargs)
            with self.assertRaisesRegex(RuntimeError, "HANDOFF_NOT_COMPLETE"):
                self.connector(module, src).proc()
            self.assertEqual(len(calls), 3)
            self.assertEqual((src / "source.sql3").read_bytes(), b"preserve-source")
            self.assertFalse(dst.exists())

    def test_rename_exception_fails_instead_of_silent_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            calls = []
            def inaccessible(**kwargs):
                calls.append(1)
                raise PermissionError("locked folder")
            module.RenameDir = inaccessible
            with self.assertRaisesRegex(RuntimeError, "HANDOFF_NOT_COMPLETE") as caught:
                self.connector(module, src).proc()
            self.assertIsInstance(caught.exception.__cause__, PermissionError)
            self.assertEqual(len(calls), 3)
            self.assertTrue(src.is_dir())
            self.assertFalse(dst.exists())

    def test_partial_copy_preserved_and_not_retried_or_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            calls = []
            def partial_copy(**kwargs):
                calls.append(1)
                shutil.copytree(kwargs["SrcDir"], kwargs["DesDir"])
                # Emulates RenameDir fallback when final source removal fails.
                # No automatic cleanup of either work directory is allowed.
            module.RenameDir = partial_copy
            with self.assertRaisesRegex(RuntimeError, "HANDOFF_NOT_COMPLETE"):
                self.connector(module, src).proc()
            self.assertEqual(len(calls), 1)
            self.assertEqual((src / "source.sql3").read_bytes(), b"preserve-source")
            self.assertEqual((dst / "source.sql3").read_bytes(), b"preserve-source")

    def test_existing_ready_destination_not_overwritten_or_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            dst.mkdir()
            (dst / "owned.txt").write_text("historical", encoding="utf-8")
            module = load_tcf_utils()
            module.RenameDir = lambda **kwargs: self.fail("must not touch existing")
            with self.assertRaisesRegex(FileExistsError,
                                        "HANDOFF_DESTINATION_ALREADY_EXISTS"):
                self.connector(module, src).proc()
            self.assertTrue(src.is_dir())
            self.assertEqual((dst / "owned.txt").read_text(encoding="utf-8"),
                             "historical")

    def test_parent_name_substring_is_not_a_valid_handoff_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "parent_is_running_DataConverter"
            src = root / "dataset_unmarked"
            src.mkdir(parents=True)
            module = load_tcf_utils()
            module.RenameDir = lambda **kwargs: self.fail("must not rename")
            with self.assertRaisesRegex(ValueError, "HANDOFF_INVALID_SOURCE_STATE"):
                self.connector(module, src).proc()
            self.assertTrue(src.is_dir())

    def test_logging_failure_after_success_never_retries_move(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            calls = []
            module.RenameDir = lambda **kwargs: (
                calls.append(1),
                os.rename(kwargs["SrcDir"], kwargs["DesDir"]),
            )
            class FailingLogger:
                def logW(self, *args, **kwargs):
                    raise OSError("logs read-only")
            module.MPlogger = lambda *args, **kwargs: FailingLogger()
            self.assertIsNone(self.connector(module, src, "stages.log").proc())
            self.assertEqual(calls, [1])
            self.assertFalse(src.exists())
            self.assertEqual((dst / "source.sql3").read_bytes(), b"preserve-source")

    def test_symlinked_source_not_moved_into_ready_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "actual"
            actual.mkdir()
            src = root / "dataset_case_is_running_DataConverter"
            try:
                src.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privileges unavailable")
            module = load_tcf_utils()
            module.RenameDir = lambda **kwargs: self.fail("must not rename symlink")
            with self.assertRaisesRegex(FileNotFoundError,
                                        "HANDOFF_SOURCE_NOT_A_DIRECTORY"):
                self.connector(module, src).proc()
            self.assertTrue(actual.is_dir())
            self.assertTrue(src.is_symlink())


if __name__ == "__main__":
    unittest.main()
