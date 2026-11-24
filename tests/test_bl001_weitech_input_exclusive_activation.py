"""BL-001 private, no-overwrite WeiTech input activation regression."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest
from unittest import mock

from text_category_profiler.pipeline import configuration
from tests.test_pipeline_configuration import namespace


class LocalTempFileSystem(configuration.LocalFileSystem):
    def make_directory(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)


class WeiTechActivationNoReplaceTests(unittest.TestCase):
    def plan(self, source):
        return configuration.build_pipeline_plan(
            parser=lambda _: namespace(
                WeiTechFormatInputPATH=str(source), ExecutionTime="20261124",
            ),
            clock=lambda: self.fail("explicit execution timestamp not preserved"),
            platform_name=lambda: "Linux",
        )

    def activate(self, source, *, filesystem=None, process_source=None):
        return configuration.activate_pipeline_runtime(
            self.plan(source),
            filesystem=filesystem or LocalTempFileSystem(),
            process_source=process_source or (
                lambda: types.SimpleNamespace(
                    ComputeNProcess=lambda: 2,
                    ComputeSPCNProcess=lambda: 1,
                )
            ),
        )

    def test_sibling_running_directory_created_once_and_new_input_recreated(self):
        with TemporaryDirectory() as temp:
            base = Path(temp) / "incoming"
            base.mkdir()
            (base / "retain.txt").write_bytes(b"original")
            context = self.activate(str(base) + os.sep)
            running = Path(str(base) + "_20261124_is_running_AI")
            self.assertEqual(context.args.WeiTechFormatInputPATH, str(running))
            self.assertEqual((running / "retain.txt").read_bytes(), b"original")
            self.assertTrue(base.is_dir())
            self.assertEqual(list(base.iterdir()), [])
            self.assertFalse((base / "_20261124_is_running_AI").exists())

    def test_existing_running_target_preserved_without_input_mutation(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "incoming"
            source.mkdir()
            (source / "work.txt").write_bytes(b"input")
            running = Path(str(source) + "_20261124_is_running_AI")
            running.mkdir()
            (running / "ctrl-c.txt").write_bytes(b"keep")
            with self.assertRaisesRegex(FileExistsError,
                                        "WEITECH_INPUT_RUNNING_DESTINATION_EXISTS"):
                self.activate(source, process_source=lambda: self.fail(
                    "do not inspect processes after a collision"
                ))
            self.assertEqual((running / "ctrl-c.txt").read_bytes(), b"keep")
            self.assertEqual((source / "work.txt").read_bytes(), b"input")

    def test_dangling_symlink_target_is_not_claimed(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "incoming"
            source.mkdir()
            (source / "work.txt").write_bytes(b"original")
            running = Path(str(source) + "_20261124_is_running_AI")
            try:
                running.symlink_to(Path(temp) / "missing", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            with self.assertRaises(FileExistsError):
                self.activate(source)
            self.assertTrue(running.is_symlink())
            self.assertEqual((source / "work.txt").read_bytes(), b"original")

    def test_source_symlink_is_rejected_without_touching_real_data(self):
        with TemporaryDirectory() as temp:
            true_dir = Path(temp) / "true-input"
            true_dir.mkdir()
            (true_dir / "safe.txt").write_bytes(b"keep")
            link = Path(temp) / "incoming"
            try:
                link.symlink_to(true_dir, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            with self.assertRaisesRegex(FileNotFoundError,
                                        "WEITECH_INPUT_SOURCE_NOT_REAL_DIRECTORY"):
                self.activate(link)
            self.assertTrue(link.is_symlink())
            self.assertEqual((true_dir / "safe.txt").read_bytes(), b"keep")

    def test_racing_destination_after_precheck_preserves_both(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "incoming"
            source.mkdir()
            (source / "original.txt").write_bytes(b"input")

            def competitor(_src, destination):
                target = Path(destination)
                target.mkdir()
                (target / "competitor.txt").write_bytes(b"keep")
                raise FileExistsError("racing writer won")

            with mock.patch.object(
                configuration, "_handoff_rename_noreplace", side_effect=competitor
            ):
                with self.assertRaisesRegex(FileExistsError, "racing writer won"):
                    self.activate(source)
            self.assertEqual((source / "original.txt").read_bytes(), b"input")
            running = Path(str(source) + "_20261124_is_running_AI")
            self.assertEqual((running / "competitor.txt").read_bytes(), b"keep")

    def test_partial_copy_fails_and_does_not_delete_either_folder(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "incoming"
            source.mkdir()
            (source / "original.txt").write_bytes(b"input")

            def incomplete_copy(_src, destination):
                dest = Path(destination)
                dest.mkdir()
                (dest / "partial.txt").write_bytes(b"partial")
                # Simulate an EXDEV copy returning without source removal.

            with mock.patch.object(configuration,
                                   "_handoff_rename_noreplace",
                                   side_effect=incomplete_copy):
                with self.assertRaisesRegex(RuntimeError,
                                            "WEITECH_INPUT_HANDOFF_INCOMPLETE"):
                    self.activate(source)
            self.assertEqual((source / "original.txt").read_bytes(), b"input")
            self.assertEqual((Path(str(source) + "_20261124_is_running_AI")
                              / "partial.txt").read_bytes(), b"partial")

    def test_reject_ambiguous_base_and_volume_roots(self):
        for value in ("", "/", "\\", "C:\\", "C:", "\\\\server\\share\\",
                      "//server/share/", ".", "../", None, 55):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError,
                                            "WEITECH_INPUT_INVALID_PATH"):
                    configuration.normalize_weitech_input_base(value)

    def test_cross_platform_path_spelling_retains_suffix_on_name(self):
        for value, expected in (
            ("C:\\WorkPool\\incoming\\", "C:\\WorkPool\\incoming"),
            ("C:/WorkPool/incoming///", "C:/WorkPool/incoming"),
            ("\\\\server\\share\\incoming\\",
             "\\\\server\\share\\incoming"),
            ("relative/folder\\\\/", "relative/folder"),
        ):
            with self.subTest(value=value):
                self.assertEqual(configuration.normalize_weitech_input_base(value),
                                 expected)

    def test_post_rename_parent_creation_failure_preserves_handoff(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "incoming"
            source.mkdir()
            (source / "work.txt").write_bytes(b"preserve")
            fs = LocalTempFileSystem()
            with mock.patch.object(fs, "make_directory",
                                   side_effect=PermissionError("mkdir denied")):
                with self.assertRaisesRegex(PermissionError, "mkdir denied"):
                    self.activate(source, filesystem=fs)
            running = Path(str(source) + "_20261124_is_running_AI")
            self.assertEqual((running / "work.txt").read_bytes(), b"preserve")
            self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
