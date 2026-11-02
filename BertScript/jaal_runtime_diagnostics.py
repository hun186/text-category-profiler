"""Read-only Jaal on-demand construction probe.

Run in the same Python interpreter/environment as --viewer-only. This
builds exactly the on-demand Jaal sub-app without opening a socket or touching
model/WorkPool lifecycles. Traceback stays in the local terminal; never send it
to browser clients or save it to repository files.
"""
from __future__ import annotations

import argparse
from importlib import metadata
import platform
import sys
import traceback


DEPENDENCIES = (
    "jaal", "visdcc", "dash", "dash-bootstrap-components", "pandas",
    "werkzeug", "flask",
)


def version_summary():
    """Installed distribution versions, without network access or secrets."""
    out = {}
    for package in DEPENDENCIES:
        try:
            out[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            out[package] = "(not installed)"
    return out


def diagnose(root="TW Affairs", *, build_app=None, output=None, error=None):
    """Return 0 on successful Jaal create + mount; 2 on full traceback.

    build_app is injectable for small dependency-free regression tests.
    """
    output = output if output is not None else sys.stdout
    error = error if error is not None else sys.stderr
    print("Jaal read-only construction preflight", file=output)
    print("Python:", platform.python_version(), file=output)
    print("Executable:", sys.executable, file=output)
    for package, version in version_summary().items():
        print(f"{package}: {version}", file=output)
    print("Selected root:", root, file=output)
    try:
        if build_app is None:
            from BertScript.jaal_original_mount import _make_original_jaal
            build_app = _make_original_jaal
        app = build_app(root, "/jaal-original/diagnose/")
        if not hasattr(app, "callback_map") or not hasattr(app, "server"):
            raise RuntimeError("Jaal build did not return a mounted Dash app")
    except Exception:
        print(
            "JAAL_DIAGNOSE_FAILED: Python traceback follows "
            "(includes local paths; review before sharing).",
            file=error,
        )
        traceback.print_exc(file=error)
        return 2
    print(
        f"JAAL_DIAGNOSE_PASS: {len(app.callback_map)} Dash callbacks; "
        "no port opened or model/WorkPool run",
        file=output,
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="唯讀診斷 Jaal 建圖階段的例外、版本與 traceback；不啟動服務"
    )
    parser.add_argument("--root", default="TW Affairs",
                        help="Exact English ClassLabel root")
    args = parser.parse_args(argv)
    return diagnose(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
