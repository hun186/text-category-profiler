"""Dependency-light compatibility tests for the modified CPython ZIP vendor."""
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
import zipfile as stdzip

from text_category_profiler import Edited_zipfile as legacy
from vendor.cpython37_zipfile_gbk import zipfile as modified


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "cpython37_zipfile_gbk"
OLD = ROOT / "text_category_profiler" / "Edited_zipfile.py"
# Git blob SHA for the historical Edited_zipfile.py in main before relocation.
HISTORICAL_BLOB = "99cd87143bd3b707ff3e95a3af1181901197e00e"


def sample_zip(name, data=b"sample-data"):
    """Make a standard archive; for raw names use an equal-length replacement."""
    output = io.BytesIO()
    with stdzip.ZipFile(output, "w", compression=stdzip.ZIP_STORED) as zf:
        zf.writestr("file.txt", data)
    archive = output.getvalue()
    if name is not None:
        assert len(name) == len(b"file.txt")
        assert archive.count(b"file.txt") == 2
        archive = archive.replace(b"file.txt", name)
    return archive


class EditedZipfileVendorBoundaryTests(unittest.TestCase):
    def test_historical_vendor_blob_and_upstream_license_kept(self):
        data = (VENDOR / "zipfile.py").read_bytes()
        digest = hashlib.sha1(
            ("blob %d\0" % len(data)).encode("ascii") + data
        ).hexdigest()
        self.assertEqual(digest, HISTORICAL_BLOB)
        license_text = (VENDOR / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("PYTHON SOFTWARE FOUNDATION LICENSE", license_text.upper())
        self.assertIn("Python Software Foundation", license_text)
        readme = (VENDOR / "README.md").read_text(encoding="utf-8")
        self.assertIn("v3.7.17", readme)
        self.assertIn("GBK", readme)

    def test_legacy_public_api_is_exact_vendor_api(self):
        self.assertEqual(legacy.__all__, modified.__all__)
        for name in modified.__all__:
            with self.subTest(name=name):
                self.assertIs(getattr(legacy, name), getattr(modified, name))
        with self.assertRaises(AttributeError):
            getattr(legacy, "not_a_symbol")

    def test_importing_vendor_or_legacy_is_inert(self):
        for target in (VENDOR / "zipfile.py", OLD):
            with self.subTest(path=target.name), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(io.StringIO()) as output:
                    namespace = runpy.run_path(str(target), run_name="import_check")
                self.assertIn("main", namespace)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_gbk_filename_in_central_directory_and_local_header(self):
        archive = sample_zip("测试.txt".encode("gbk"))
        with modified.ZipFile(io.BytesIO(archive), "r") as zf:
            self.assertEqual(zf.namelist(), ["测试.txt"])
            # This exercises local-header decoding, not only the central dir.
            self.assertEqual(zf.read("测试.txt"), b"sample-data")

    def test_cp437_fallback_on_invalid_gbk_bytes(self):
        archive = sample_zip(b"caf\x82.txt")
        with modified.ZipFile(io.BytesIO(archive)) as zf:
            self.assertEqual(zf.namelist(), ["café.txt"])
            self.assertEqual(zf.read("café.txt"), b"sample-data")

    def test_explicit_utf8_names_and_plain_ascii_unchanged(self):
        archive = io.BytesIO()
        with stdzip.ZipFile(archive, "w") as zf:
            zf.writestr("中文.txt", "UTF8")
            zf.writestr("plain.txt", "ASCII")
        with modified.ZipFile(io.BytesIO(archive.getvalue())) as zf:
            self.assertEqual(set(zf.namelist()), {"中文.txt", "plain.txt"})
            self.assertEqual(zf.read("中文.txt"), b"UTF8")
            self.assertEqual(zf.read("plain.txt"), b"ASCII")

    def test_legacy_cli_and_direct_main_still_list_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "sample.zip"
            archive.write_bytes(sample_zip(None))
            for script in (OLD, VENDOR / "zipfile.py"):
                with self.subTest(script=script):
                    child = subprocess.run(
                        [sys.executable, str(script), "-l", str(archive)],
                        cwd=tmp, text=True, capture_output=True, timeout=15,
                        check=False,
                    )
                    self.assertEqual(child.returncode, 0, child.stderr)
                    self.assertIn("file.txt", child.stdout)
            with redirect_stdout(io.StringIO()) as output:
                legacy.main(["--list", str(archive)])
            self.assertIn("file.txt", output.getvalue())


if __name__ == "__main__":
    unittest.main()
