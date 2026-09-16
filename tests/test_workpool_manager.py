from argparse import Namespace
import os
from pathlib import Path
import tempfile
import unittest


from text_category_profiler.pipeline.configuration import PipelineContext
from text_category_profiler.pipeline.workpool import (
    DeliveryManager,
    WorkPoolManager,
    WorkPoolPlan,
)


BASE_PATTERNS = (
    "^DFPreambleCols_df_ALL.*",
    "dataset_total_with_filename_FixedTest.sql3",
    "test.sql3",
    "test.tsv",
)


class RecordingFileSystem:
    def __init__(self, listings=None, *, system="Windows", move_error=None,
                 backup_error=None):
        self.listings = listings or {}
        self.system = system
        self.move_error = move_error
        self.backup_error = backup_error
        self.calls = []

    def list_directory(self, path):
        self.calls.append(("list", path))
        return list(self.listings.get(path, ()))

    def make_directory(self, path):
        self.calls.append(("mkdir", path))

    def move(self, source, destination):
        self.calls.append(("move", source, destination))
        if self.move_error:
            raise self.move_error

    def backup(self, **kwargs):
        self.calls.append(("backup", kwargs))
        if self.backup_error:
            raise self.backup_error

    def platform_name(self):
        return self.system

    def walk(self, path):
        self.calls.append(("walk", path))
        return [os.path.join(path, "artifact.tsv")]

    def chown(self, path):
        self.calls.append(("chown", path))


def plan(**overrides):
    values = dict(
        incoming_path="/jobs/AutoBertClassify",
        pool_path="/jobs/WorkPool",
        work_id="",
        remove_dataset=False,
        task="",
        workpool_root="WorkPool",
        output_patterns=BASE_PATTERNS,
    )
    values.update(overrides)
    return WorkPoolPlan(**values)


class WorkPoolManagerTests(unittest.TestCase):
    def test_acquire_selects_latest_matching_work(self):
        fs = RecordingFileSystem({
            "/jobs/AutoBertClassify": ["job-001", "job-003", "job-002"],
            "/jobs/WorkPool": ["job-001", "job-002"],
        })
        selected = WorkPoolManager(plan(), fs).acquire()
        self.assertEqual("job-002", selected)
        processing = "/jobs/AutoBertClassify/../AutoBertClassify_Processing"
        self.assertIn(("mkdir", processing), fs.calls)
        self.assertIn(("move", "/jobs/AutoBertClassify/job-002",
                       processing + "/job-002"), fs.calls)

    def test_acquire_fails_before_command_when_empty(self):
        fs = RecordingFileSystem({"/jobs/AutoBertClassify": [], "/jobs/WorkPool": []})
        trace = []
        with self.assertRaises(Exception):
            WorkPoolManager(plan(), fs).acquire()
            trace.append("command")
        self.assertEqual([], trace)

    def test_complete_uses_exact_output_patterns(self):
        for task, expected in (
            ("", BASE_PATTERNS),
            ("SDSMS", BASE_PATTERNS + ("SDSMS.*",)),
            ("SDSMS_Prediction", BASE_PATTERNS + ("SDSMS.*",)),
        ):
            with self.subTest(task=task):
                fs = RecordingFileSystem()
                DeliveryManager(plan(task=task, work_id="job-1"), fs).backup_and_complete(
                    "/dataset"
                )
                delivery = [call[1] for call in fs.calls if call[0] == "backup"][0]
                self.assertEqual(list(expected), delivery["BackFNrePatList"])

    def test_remove_flag_controls_cleanup(self):
        for remove, expected in ((False, 0), (True, 1)):
            with self.subTest(remove=remove):
                fs = RecordingFileSystem()
                DeliveryManager(plan(remove_dataset=remove), fs).backup_and_complete("/dataset")
                self.assertEqual(expected, sum(call[0] == "backup" for call in fs.calls))

    def test_complete_moves_processing_to_processed(self):
        fs = RecordingFileSystem()
        DeliveryManager(plan(work_id="job-1"), fs).backup_and_complete("/dataset")
        self.assertIn(("move",
                       "/jobs/AutoBertClassify/../AutoBertClassify_Processing/job-1",
                       "/jobs/AutoBertClassify/../AutoBertClassify_Processed/job-1"),
                      fs.calls)

    def test_linux_chown_scope_matches_baseline(self):
        fs = RecordingFileSystem(system="Linux")
        DeliveryManager(plan(work_id="job-1"), fs).backup_and_complete("/dataset")
        processing = "/jobs/AutoBertClassify/../AutoBertClassify_Processing"
        processed = "/jobs/AutoBertClassify/../AutoBertClassify_Processed"
        self.assertEqual([
            processing,
            processed,
            processing + "/job-1",
            processed + "/job-1/artifact.tsv",
        ], [call[1] for call in fs.calls if call[0] == "chown"])

    def test_adapter_propagates_validation_and_backup_errors(self):
        context = PipelineContext(
            args=Namespace(WeiTechworkIDPath="/incoming", WeiTechWorkPoolPATH="/pool",
                           WeiTechworkID="", RemoveBertDataDir=False, task=""),
            root_paths=(), final_output_patterns=BASE_PATTERNS, run_mode="test",
        )
        derived = WorkPoolPlan.from_context(context, workpool_root="root")
        self.assertEqual("/incoming", derived.incoming_path)

        fs = RecordingFileSystem(backup_error=ValueError("backup failed"))
        with self.assertRaisesRegex(ValueError, "backup failed"):
            DeliveryManager(plan(remove_dataset=True), fs).backup_and_complete("/dataset")

        fs = RecordingFileSystem({"/incoming": ["job-1"], "/pool": ["job-1"]})
        trace = []

        def stage_boundary():
            WorkPoolManager(derived, fs).acquire()
            raise ValueError("invalid dataset")
            trace.append("command")

        with self.assertRaisesRegex(ValueError, "invalid dataset"):
            stage_boundary()
        self.assertEqual([], trace)

    def test_final_move_error_remains_caught(self):
        errors = []
        fs = RecordingFileSystem(move_error=OSError("move failed"))
        DeliveryManager(
            plan(work_id="job-1"), fs, move_error_reporter=errors.append
        ).backup_and_complete("/dataset")
        self.assertEqual(["move failed"], [str(error) for error in errors])


if __name__ == "__main__":
    unittest.main()
