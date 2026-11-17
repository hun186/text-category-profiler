"""Fail-closed stage directory handoff tests; PRIVATE tempfile only."""
import os
from pathlib import Path
import shutil
import subprocess
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

    def test_successful_no_replace_rename_retains_files_and_no_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            calls = []
            def rename(source, destination):
                calls.append((source, destination))
                os.rename(source, destination)
            module._handoff_rename_noreplace = rename
            self.assertIsNone(self.connector(module, src).proc())
            self.assertEqual(len(calls), 1)
            self.assertFalse(src.exists())
            self.assertEqual((dst / "source.sql3").read_bytes(), b"preserve-source")

    def test_silent_legacy_rename_failure_fails_after_bounded_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            calls = []
            module._handoff_rename_noreplace = lambda *args: calls.append(args)
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
            def inaccessible(source, destination):
                calls.append(1)
                raise PermissionError("locked folder")
            module._handoff_rename_noreplace = inaccessible
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
            def partial_copy(source, destination):
                calls.append(1)
                shutil.copytree(source, destination)
                # Emulates EXDEV copy fallback when source removal fails.
                # No automatic cleanup of either work directory is allowed.
            module._handoff_rename_noreplace = partial_copy
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
            module._handoff_rename_noreplace = lambda *args: self.fail("must not touch existing")
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
            module._handoff_rename_noreplace = lambda *args: self.fail("must not rename")
            with self.assertRaisesRegex(ValueError, "HANDOFF_INVALID_SOURCE_STATE"):
                self.connector(module, src).proc()
            self.assertTrue(src.is_dir())

    def test_logging_failure_after_success_never_retries_move(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            calls = []
            module._handoff_rename_noreplace = lambda source, destination: (
                calls.append(1),
                os.rename(source, destination),
            )
            class FailingLogger:
                def logW(self, *args, **kwargs):
                    raise OSError("logs read-only")
            module.MPlogger = lambda *args, **kwargs: FailingLogger()
            self.assertIsNone(self.connector(module, src, "stages.log").proc())
            self.assertEqual(calls, [1])
            self.assertFalse(src.exists())
            self.assertEqual((dst / "source.sql3").read_bytes(), b"preserve-source")

    def test_concurrent_ready_destination_created_after_check_is_not_overwritten(self):
        # Exercise the REAL no-replace primitive, not a mocked rename.
        # The destination appears between TaskConnector's initial check
        # and the publication syscall, mirroring a Codex P2 finding.
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_folders(temp)
            module = load_tcf_utils()
            def create_competing_ready(*args, **kwargs):
                dst.mkdir()
                (dst / "other-owner").write_bytes(b"winner")
            module.key_values = create_competing_ready
            with self.assertRaisesRegex(RuntimeError, "HANDOFF_NOT_COMPLETE"):
                self.connector(module, src).proc()
            self.assertEqual((src / "source.sql3").read_bytes(), b"preserve-source")
            self.assertEqual((dst / "other-owner").read_bytes(), b"winner")
            self.assertFalse((dst / "source.sql3").exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction-only fixture")
    def test_windows_junction_source_never_moves_into_ready_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "real-data"
            target.mkdir()
            src = root / "dataset_case_is_running_DataConverter"
            dst = root / "dataset_case_rdy_for_RunClassfier"
            cmd = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(src), str(target)],
                capture_output=True, text=True, check=False,
            )
            if cmd.returncode:
                self.skipTest("junction privilege unavailable")
            try:
                module = load_tcf_utils()
                module._handoff_rename_noreplace = lambda *args: self.fail(
                    "must not rename junction"
                )
                with self.assertRaisesRegex(FileNotFoundError,
                                            "HANDOFF_SOURCE_NOT_A_DIRECTORY"):
                    self.connector(module, src).proc()
                self.assertTrue(target.is_dir())
                self.assertFalse(dst.exists())
            finally:
                # Remove the junction itself, never recurse into its target.
                src.rmdir()

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
            module._handoff_rename_noreplace = lambda *args: self.fail("must not rename symlink")
            with self.assertRaisesRegex(FileNotFoundError,
                                        "HANDOFF_SOURCE_NOT_A_DIRECTORY"):
                self.connector(module, src).proc()
            self.assertTrue(actual.is_dir())
            self.assertTrue(src.is_symlink())


if __name__ == "__main__":
    unittest.main()
