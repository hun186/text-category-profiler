"""Ctrl+C evidence is project-local, minimal, and never a WorkPool action."""
from datetime import datetime, timezone
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from text_category_profiler.execution.operator_interrupt import (
    record_operator_interrupt,
)


class OperatorInterruptEvidenceTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Windows intentionally has console-only Ctrl+C evidence")
    def test_only_operator_event_is_appended_with_no_workpool_mutation(self):
        when = datetime(2026, 11, 17, 8, 10, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pool = root / "WorkPool"
            old = pool / "dataset_old_is_running_TestResultVis"
            old.mkdir(parents=True)
            marker = old / "keep.sql3"
            marker.write_bytes(b"original")
            before = (marker.read_bytes(), marker.stat().st_mtime_ns)
            with mock.patch("os.rename", side_effect=AssertionError(
                "must not rename any WorkPool folder"
            )), mock.patch("sqlite3.connect", side_effect=AssertionError(
                "must not open WorkPool SQLite"
            )):
                path = record_operator_interrupt(
                    "TestResultVis", project_root=root, when=when
                )
                second = record_operator_interrupt(
                    "DataConverter", project_root=root, when=when
                )
            self.assertIsNotNone(path)
            self.assertEqual(path, second)
            self.assertEqual(path, root / "logs" / "tcf_operator_interruptions.jsonl")
            data = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(data), 2)
            self.assertEqual([x["stage"] for x in data],
                             ["TestResultVis", "DataConverter"])
            self.assertEqual(data[0]["time_utc"], "2026-11-17T08:10:00+00:00")
            self.assertEqual(data[0]["schema"], "tcf_operator_interrupt_v1")
            self.assertEqual(data[0]["event"], "operator_keyboard_interrupt")
            self.assertFalse(data[0]["workpool_modified"])
            self.assertFalse(data[0]["cleanup_attempted"])
            self.assertEqual(data[0]["pid"], os.getpid())
            self.assertNotIn(str(root), path.read_text(encoding="utf-8"))
            self.assertNotIn("dataset_old", path.read_text(encoding="utf-8"))
            self.assertEqual((marker.read_bytes(), marker.stat().st_mtime_ns), before)

    @unittest.skipIf(os.name == "nt", "Windows intentionally has console-only Ctrl+C evidence")
    def test_unknown_stage_is_sanitized_without_raw_args(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = record_operator_interrupt(
                "DataConverter --password top-secret", project_root=root
            )
            self.assertIsNotNone(path)
            line = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(line["stage"], "unknown")
            self.assertNotIn("top-secret", path.read_text(encoding="utf-8"))

    def test_parent_directory_and_log_symlink_are_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pool = root / "WorkPool"
            pool.mkdir()
            logs = root / "logs"
            try:
                logs.symlink_to(pool, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            self.assertIsNone(record_operator_interrupt(
                "DataConverter", project_root=root
            ))
            self.assertEqual(list(pool.iterdir()), [])

    def test_existing_log_symlink_or_hardlink_is_not_appended(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            logs = root / "logs"
            logs.mkdir()
            target = root / "outside.txt"
            target.write_text("untouched", encoding="utf-8")
            destination = logs / "tcf_operator_interruptions.jsonl"
            try:
                destination.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            self.assertIsNone(record_operator_interrupt(
                "TestResultVis", project_root=root
            ))
            self.assertEqual(target.read_text(encoding="utf-8"), "untouched")
            destination.unlink()
            try:
                os.link(target, destination)
            except OSError:
                self.skipTest("hardlinks unavailable")
            self.assertIsNone(record_operator_interrupt(
                "TestResultVis", project_root=root
            ))
            self.assertEqual(target.read_text(encoding="utf-8"), "untouched")

    @unittest.skipIf(os.name == "nt", "POSIX nofollow dirfd fixture")
    def test_posix_logs_directory_swap_to_workpool_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pool = root / "WorkPool"
            pool.mkdir()
            real_open = os.open
            swapped = False

            def inject_directory_replacement(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "logs" and kwargs.get("dir_fd") is not None and not swapped:
                    swapped = True
                    (root / "logs").rename(root / "original-logs")
                    (root / "logs").symlink_to(pool, target_is_directory=True)
                return real_open(path, flags, *args, **kwargs)

            with mock.patch(
                "text_category_profiler.execution.operator_interrupt.os.open",
                side_effect=inject_directory_replacement,
            ):
                self.assertIsNone(record_operator_interrupt(
                    "DataConverter", project_root=root
                ))
            self.assertTrue(swapped)
            self.assertEqual(list(pool.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows junction safety fixture")
    def test_windows_junction_to_workpool_never_writes_even_on_ctrl_c(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workpool = root / "WorkPool"
            workpool.mkdir()
            logs = root / "logs"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(logs), str(workpool)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                self.skipTest("Windows junction creation unavailable")
            try:
                with mock.patch(
                    "text_category_profiler.execution.operator_interrupt.os.open",
                    side_effect=AssertionError("Windows must not file-open logs"),
                ):
                    self.assertIsNone(record_operator_interrupt(
                        "TestResultVis", project_root=root
                    ))
                self.assertEqual(list(workpool.iterdir()), [])
            finally:
                # Remove the junction itself, never recurse into its target.
                logs.rmdir()

    @unittest.skipUnless(os.name == "nt", "Windows console-only policy")
    def test_windows_no_file_creation_even_in_safe_empty_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertIsNone(record_operator_interrupt(
                "DataConverter", project_root=root
            ))
            self.assertFalse((root / "logs").exists())

    def test_unwritable_log_is_best_effort_not_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch(
                "text_category_profiler.execution.operator_interrupt.os.open",
                side_effect=PermissionError("injected"),
            ):
                self.assertIsNone(record_operator_interrupt(
                    "RunClassfier", project_root=root
                ))


if __name__ == "__main__":
    unittest.main()
