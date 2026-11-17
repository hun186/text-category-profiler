"""Cross-platform checkpoint copy-safety tests; never runs a real model."""
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from text_category_profiler.diagnostics.full_pipeline import (
    ModelFacadeError, _directory_copy_bytes, create_model_facade, snapshot_regular_files,
)


class ModelFacadeCopyIsolationTests(unittest.TestCase):
    def test_checkpoint_writes_and_metadata_writes_cannot_change_source(self):
        with tempfile.TemporaryDirectory(prefix="bl001-checkpoint-copy-") as parent:
            root = Path(parent)
            source = root / "source"
            ckpt = source / "checkpoint-123"
            ckpt.mkdir(parents=True)
            (source / "TopicAnalysis_LabelList.txt").write_text(
                "A\n", encoding="utf-8"
            )
            (ckpt / "model.safetensors").write_bytes(b"original-weights")
            (ckpt / "config.json").write_text("{}", encoding="utf-8")
            before = snapshot_regular_files(source)
            facade = create_model_facade(source, root / "runtime")
            copy = facade / "checkpoint-123"
            self.assertTrue(copy.is_dir())
            self.assertFalse(copy.is_symlink())
            self.assertFalse((copy / "model.safetensors").is_symlink())
            self.assertEqual((copy / "model.safetensors").read_bytes(),
                             b"original-weights")
            (copy / "model.safetensors").write_bytes(b"changed-weights")
            (copy / "config.json").write_text("changed", encoding="utf-8")
            (copy / "extra-weights").write_bytes(b"new")
            (facade / "TopicAnalysis_LabelList.txt").write_text(
                "B\n", encoding="utf-8"
            )
            self.assertEqual((ckpt / "model.safetensors").read_bytes(),
                             b"original-weights")
            self.assertEqual((ckpt / "config.json").read_text(encoding="utf-8"),
                             "{}")
            self.assertFalse((ckpt / "extra-weights").exists())
            self.assertEqual((source / "TopicAnalysis_LabelList.txt").read_text(
                encoding="utf-8"), "A\n")
            self.assertEqual(snapshot_regular_files(source), before)

    def test_copy_failure_is_fail_closed_instead_of_linking_original(self):
        with tempfile.TemporaryDirectory(prefix="bl001-checkpoint-copy-") as parent:
            root = Path(parent)
            source = root / "source"
            (source / "checkpoint-123").mkdir(parents=True)
            (source / "checkpoint-123" / "weights").write_bytes(b"original")
            with mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.shutil.copytree",
                side_effect=OSError("injected no disk space"),
            ), self.assertRaisesRegex(ModelFacadeError, "cannot copy model checkpoint"):
                create_model_facade(source, root / "runtime")
            self.assertEqual((source / "checkpoint-123" / "weights").read_bytes(),
                             b"original")
            self.assertFalse((root / "runtime" / "model-facade"
                              / "checkpoint-123").exists())

    def test_disk_shortage_blocks_before_model_copy_or_launch(self):
        with tempfile.TemporaryDirectory(prefix="bl001-checkpoint-space-") as parent:
            root = Path(parent)
            source = root / "source"
            ckpt = source / "checkpoint-123"
            ckpt.mkdir(parents=True)
            (ckpt / "weights").write_bytes(b"model-bytes")
            runtime = root / "runtime"
            runtime.mkdir()
            before = snapshot_regular_files(source)
            with mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.shutil.disk_usage",
                return_value=SimpleNamespace(free=128 * 1024 * 1024),
            ), mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.shutil.copytree",
                side_effect=AssertionError("model copy must not begin"),
            ) as copytree, self.assertRaisesRegex(
                ModelFacadeError, "insufficient temporary disk for model copy"
            ):
                create_model_facade(source, runtime)
            copytree.assert_not_called()
            self.assertFalse((runtime / "model-facade").exists())
            self.assertEqual(snapshot_regular_files(source), before)

    def test_runtime_directory_inside_source_and_vice_versa_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="bl001-checkpoint-overlap-") as parent:
            root = Path(parent)
            source = root / "source"
            ckpt = source / "checkpoint-123"
            ckpt.mkdir(parents=True)
            (ckpt / "weights").write_bytes(b"model")
            for runtime in (source / "nested-runtime", root):
                with self.subTest(runtime=runtime):
                    with mock.patch(
                        "text_category_profiler.diagnostics.full_pipeline.shutil.copytree",
                        side_effect=AssertionError("copy forbidden"),
                    ) as copytree, self.assertRaisesRegex(
                        ModelFacadeError, "model source and temporary runtime overlap"
                    ):
                        create_model_facade(source, runtime)
                    copytree.assert_not_called()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_recursive_checkpoint_symlink_is_blocked_before_copy(self):
        with tempfile.TemporaryDirectory(prefix="bl001-checkpoint-cycle-") as parent:
            root = Path(parent)
            source = root / "source"
            ckpt = source / "checkpoint-123"
            ckpt.mkdir(parents=True)
            try:
                (ckpt / "recursive").symlink_to(ckpt, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privilege unavailable")
            with mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.shutil.copytree",
                side_effect=AssertionError("copy forbidden on cyclic links"),
            ) as copytree, self.assertRaisesRegex(
                ModelFacadeError, "cyclic checkpoint directory link"
            ):
                create_model_facade(source, root / "runtime")
            copytree.assert_not_called()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_nested_directory_symlink_target_is_copied(self):
        with tempfile.TemporaryDirectory(prefix="bl001-checkpoint-copy-") as parent:
            root = Path(parent)
            source = root / "source"
            ckpt = source / "checkpoint-123"
            ckpt.mkdir(parents=True)
            target = root / "external-source"
            target.mkdir()
            (target / "weights").write_bytes(b"original")
            try:
                (ckpt / "linked").symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privilege unavailable")
            # Capacity accounting must include dereferenced source bytes.
            self.assertEqual(_directory_copy_bytes(ckpt), len(b"original"))
            facade = create_model_facade(source, root / "runtime")
            copy = facade / "checkpoint-123" / "linked"
            self.assertTrue(copy.is_dir())
            self.assertFalse(copy.is_symlink())
            (copy / "weights").write_bytes(b"changed")
            self.assertEqual((target / "weights").read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
