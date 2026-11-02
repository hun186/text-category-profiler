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
import re
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


def check_dash_visdcc_compatibility(versions=None):
    """Fail early on the cross-machine visdcc/Dash import incompatibility.

    This is a narrow check for the two verified package boundaries, not a
    blanket promise that any two untested versions are fully compatible.
    Reading distribution metadata does not import visdcc or start Dash.
    Older Dash 2 environments are allowed if paired with an older visdcc.
    """
    versions = version_summary() if versions is None else versions

    def version_key(package):
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(versions.get(package, "")))
        return tuple(map(int, match.groups())) if match else None

    dash = version_key("dash")
    visdcc = version_key("visdcc")
    if dash is None or visdcc is None:
        # Import will report a missing package, or a nonstandard package
        # version, with a more accurate traceback during actual build.
        return
    if dash[0] >= 3 and visdcc < (0, 0, 63):
        raise RuntimeError(
            "JAAL_VISDCC_DASH_INCOMPATIBLE: Dash "
            + str(versions["dash"]) + " and visdcc "
            + str(versions["visdcc"]) + " are incompatible. "
            "Dash 3+ removed dash.development.component_loader, "
            "which this older visdcc imports. On this Python environment, "
            "run: python -m pip install --upgrade \"visdcc==0.0.63\"; "
            "then: python -m pip check. Do NOT downgrade Dash in Anaconda "
            "base without checking other applications."
        )
    if dash[0] < 3 and visdcc >= (0, 0, 63):
        raise RuntimeError(
            "JAAL_VISDCC_DASH_INCOMPATIBLE: visdcc "
            + str(versions["visdcc"]) + " requires Dash >=3, "
            "but Dash is " + str(versions["dash"]) + ". "
            "Preserve this legacy Dash 2 environment with a compatible "
            "older visdcc, or use a separate Dash >=3 environment."
        )


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
            check_dash_visdcc_compatibility()
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
