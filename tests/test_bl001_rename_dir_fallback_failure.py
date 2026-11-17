"""Execute the real RenameDir function body on disposable directories only.

No model, production WorkPool, network shares or CLI stage is loaded.
"""
import ast
import errno
import os
from pathlib import Path
import shutil
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "text_category_profiler" / "core" / "utilities_path.py"


def load_rename_dir(*, os_module=os, shutil_module=shutil):
    """Compile only the real RenameDir AST to avoid optional heavy imports."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "RenameDir"
    )
    code = compile(ast.Module(body=[function], type_ignores=[]),
                   str(SOURCE), "exec")
    namespace = {
        "os": os_module, "shutil": shutil_module,
        "print": lambda *args, **kwargs: None,
    }
    exec(code, namespace)
    return namespace["RenameDir"]


class LegacyRenameDirFailureTests(unittest.TestCase):
    def make_source(self, root):
        source = Path(root) / "dataset_is_running_CombineTestResult"
        target = Path(root) / "dataset_rdy_for_TestResultVis"
        source.mkdir()
        (source / "test.sql3").write_bytes(b"existing-sqlite")
        return source, target

    def test_same_volume_rename_succeeds_without_copy_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_source(temp)
            no_copy = types.SimpleNamespace(
                copytree=lambda *a, **k: self.fail("must not copy"),
                rmtree=lambda *a, **k: self.fail("must not delete via fallback"),
            )
            rename_dir = load_rename_dir(shutil_module=no_copy)
            self.assertIsNone(rename_dir(str(src), str(dst)))
            self.assertFalse(src.exists())
            self.assertEqual((dst / "test.sql3").read_bytes(), b"existing-sqlite")

    def test_cross_device_fallback_success_retains_legacy_behavior(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_source(temp)
            def exdev(*args, **kwargs):
                raise OSError(errno.EXDEV, "synthetic separate volumes")
            rename_dir = load_rename_dir(
                os_module=types.SimpleNamespace(rename=exdev),
            )
            self.assertIsNone(rename_dir(str(src), str(dst)))
            self.assertFalse(src.exists())
            self.assertEqual((dst / "test.sql3").read_bytes(), b"existing-sqlite")

    def test_failed_copy_is_not_swallowed_and_original_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_source(temp)
            calls = []
            def locked_rename(*args):
                calls.append("rename")
                raise PermissionError("rename locked")
            def failed_copy(*args):
                calls.append("copy")
                raise OSError("copy blocked")
            fake = types.SimpleNamespace(
                copytree=failed_copy,
                rmtree=lambda *args: self.fail("must not delete after copy fails"),
            )
            rename_dir = load_rename_dir(
                os_module=types.SimpleNamespace(rename=locked_rename),
                shutil_module=fake,
            )
            with self.assertRaisesRegex(OSError, "copy blocked"):
                rename_dir(str(src), str(dst))
            self.assertEqual(calls, ["rename", "copy"])
            self.assertEqual((src / "test.sql3").read_bytes(), b"existing-sqlite")
            self.assertFalse(dst.exists())

    def test_failed_cleanup_propagates_and_preserves_partial_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_source(temp)
            def exdev(*args, **kwargs):
                raise OSError(errno.EXDEV, "different volumes")
            def refuse_delete(*args, **kwargs):
                raise PermissionError("source removal blocked")
            fake = types.SimpleNamespace(
                copytree=shutil.copytree,
                rmtree=refuse_delete,
            )
            rename_dir = load_rename_dir(
                os_module=types.SimpleNamespace(rename=exdev),
                shutil_module=fake,
            )
            with self.assertRaisesRegex(PermissionError, "source removal blocked"):
                rename_dir(str(src), str(dst))
            self.assertEqual((src / "test.sql3").read_bytes(), b"existing-sqlite")
            self.assertEqual((dst / "test.sql3").read_bytes(), b"existing-sqlite")
            # No cleanup of either side, retry or automatic recovery.

    def test_existing_destination_survives_fallback_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = self.make_source(temp)
            dst.mkdir()
            (dst / "other-owner").write_bytes(b"historical")
            rename_dir = load_rename_dir(
                os_module=types.SimpleNamespace(
                    rename=lambda *args: (_ for _ in ()).throw(
                        FileExistsError("destination already exists")
                    )
                )
            )
            with self.assertRaises(FileExistsError):
                rename_dir(str(src), str(dst))
            self.assertTrue(src.exists())
            self.assertEqual((dst / "other-owner").read_bytes(), b"historical")

    def test_missing_source_is_not_a_false_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rename_dir = load_rename_dir()
            with self.assertRaises(Exception):
                rename_dir(str(root / "absent"), str(root / "ready"))
            self.assertFalse((root / "ready").exists())


if __name__ == "__main__":
    unittest.main()
