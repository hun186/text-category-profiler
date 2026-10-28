"""Legacy import/CLI facade for a modified CPython 3.7.17 zipfile module.

Implementation and upstream PSF license live under
vendor/cpython37_zipfile_gbk/. Importing this facade does not load
the copied ZIP engine. Public exports retain the historical names.
"""
import importlib
from pathlib import Path
import runpy

__all__ = [
    "BadZipFile", "BadZipfile", "error",
    "ZIP_STORED", "ZIP_DEFLATED", "ZIP_BZIP2", "ZIP_LZMA",
    "is_zipfile", "ZipInfo", "ZipFile", "PyZipFile", "LargeZipFile",
]


def __getattr__(name):
    implementation = importlib.import_module("vendor.cpython37_zipfile_gbk.zipfile")
    return getattr(implementation, name)


def main(args=None):
    implementation = importlib.import_module("vendor.cpython37_zipfile_gbk.zipfile")
    return implementation.main(args)


if __name__ == "__main__":
    upstream = (
        Path(__file__).resolve().parents[1]
        / "vendor"
        / "cpython37_zipfile_gbk"
        / "zipfile.py"
    )
    runpy.run_path(str(upstream), run_name="__main__")
