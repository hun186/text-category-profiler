"""Read-only Stage 4 cross-machine preflight; never launches the pipeline.

A single command reports independent environment and dataset blockers instead
of fixing one import exception only to discover the next. No package installs,
network calls, SQLite connections, model imports, or WorkPool writes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from importlib import metadata, util
import os
from pathlib import Path
import platform
import re
import sys

from BertScript import jaal_runtime_diagnostics as jaal_probe
from BertScript.visualization_stage import (
    preflight_tulip_windows_path, sanitize_tulip_windows_dot_path,
)


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str


def _version(version):
    """Numeric prefix for the small set of known runtime version contracts."""
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", str(version))
    return tuple(map(int, match.groups(default="0"))) if match else None


def _installed_versions():
    packages = ("dash", "visdcc", "comm", "jaal",
                "jaal-topology-viewer", "dash-bootstrap-components",
                "tulip-python")
    versions = {}
    for package in packages:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "(not installed)"
    return versions


def _module_available(name):
    try:
        return util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _workspaces(workpool):
    """Inspect names only. Never open result DBs, follow links, or rename."""
    root = Path(workpool)
    if not root.is_dir():
        return None
    return [
        x.name for x in root.iterdir()
        if not x.is_symlink() and x.is_dir()
        and re.match(r"^dataset_\d{12,16}_", x.name)
    ]


def collect_checks(*, mode="full", model_type="PytorchMMBERT",
                   workpool="WorkPool", versions=None,
                   has_topology=None, has_tulip=None, python_version=None,
                   windows=None, path=None, workspace_names=None):
    """Pure, injectable checks except optional read-only filesystem discovery."""
    if mode not in ("full", "viewer", "history"):
        raise ValueError("invalid Stage 4 doctor mode")
    versions = _installed_versions() if versions is None else versions
    python_version = sys.version_info[:2] if python_version is None else python_version
    windows = platform.system().lower() == "windows" if windows is None else windows
    path = os.environ.get("PATH", "") if path is None else path
    checks = []

    def add(status, key, detail):
        checks.append(Check(status, key, detail))

    if tuple(python_version[:2]) < (3, 10):
        add("FAIL", "Python", "Jaal portable viewer requires Python >=3.10.")
    else:
        add("PASS", "Python", ".".join(map(str, python_version[:2])))

    for name in ("dash", "visdcc", "comm", "jaal", "dash-bootstrap-components"):
        value = versions.get(name, "(not installed)")
        if _version(value) is None:
            add("FAIL", name, f"Not installed in this interpreter; check requirements.txt ({value}).")
        else:
            add("PASS", name, value)
    dash = _version(versions.get("dash", ""))
    comm = _version(versions.get("comm", ""))
    if dash is not None and dash[0] >= 3 and (comm is None or comm < (0, 2, 3)):
        add("FAIL", "Dash/comm", 'Install in this interpreter: python -m pip install --user "comm>=0.2.3"')
    elif dash is not None and dash[0] >= 3:
        add("PASS", "Dash/comm", "comm satisfies >=0.2.3 metadata preflight")

    if dash is not None and _version(versions.get("visdcc", "")) is not None:
        try:
            jaal_probe.check_dash_visdcc_compatibility(versions)
        except RuntimeError as exc:
            add("FAIL", "Dash/visdcc", str(exc))
        else:
            add("PASS", "Dash/visdcc", "Known version boundary is compatible")

    if has_topology is None:
        has_topology = _module_available("jaal_topology")
    if has_topology:
        add("PASS", "jaal_topology", "Portable Jaal module is discoverable")
    else:
        add("FAIL", "jaal_topology",
            "Install pinned jaal-topology-viewer from root requirements.txt in the SAME Python interpreter.")

    if mode == "full":
        if windows:
            # Doctor is read-only. Mirror the Stage 4 startup sanitation
            # against an in-memory mapping, never os.environ.
            simulated = {"PATH": path}
            removed = sanitize_tulip_windows_dot_path(
                environ=simulated, windows=True,
            )
            try:
                preflight_tulip_windows_path(
                    path=simulated["PATH"], windows=True,
                )
            except RuntimeError as exc:
                add("FAIL", "Tulip DLL PATH", str(exc))
            else:
                status = "WARN" if removed else "PASS"
                detail = (
                    f"Stage 4 startup will remove {removed} independent '.' "
                    "PATH entry/entries in its process only; this read-only "
                    "Doctor has NOT changed your PATH."
                    if removed else "No relative Windows PATH entries detected"
                )
                add(status, "Tulip DLL PATH", detail)
        if has_tulip is None:
            has_tulip = _module_available("tulip")
        if has_tulip:
            add("PASS", "Tulip module", "Module discoverable; native DLL load not verified")
        else:
            add("FAIL", "Tulip module",
                "Tulip is needed by full Stage 4 similarity clustering; verify tulip-python in this interpreter.")

    if mode != "viewer":
        names = _workspaces(workpool) if workspace_names is None else workspace_names
        if names is None:
            add("FAIL", "WorkPool", f"Directory does not exist: {workpool}")
        else:
            ready = [x for x in names if x.endswith("_rdy_for_TestResultVis")
                     and model_type.lower() in x.lower()]
            complete = [x for x in names if x.endswith("_rdy_for_Spike")]
            running = [x for x in names if x.endswith("_is_running_TestResultVis")]
            if mode == "full":
                if ready:
                    add("PASS", "WorkPool",
                        f"{len(ready)} matching {model_type} ready dataset(s); newest candidate: {max(ready)}. "
                        "Output/model data and complete GUI behavior still require runtime validation.")
                else:
                    add("FAIL", "WorkPool",
                        f"No {model_type} *_rdy_for_TestResultVis dataset in {workpool}; "
                        f"completed={len(complete)}, running/interrupted={len(running)}. "
                        "Do NOT rename completed datasets to retry. "
                        "Use --viewer-only (no WorkPool) or --history-preview (saved data).")
            elif complete or running:
                add("PASS", "WorkPool",
                    f"Historical candidates: completed={len(complete)}, "
                    f"running/interrupted={len(running)}; saved SQLite is verified by the history viewer.")
            else:
                add("FAIL", "WorkPool", "No completed/interrupted Stage 4 history candidates; use --viewer-only.")
    return checks


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="唯讀一鍵檢測 Stage 4／Jaal 的 Python 套件、Windows PATH 與 WorkPool；不安裝或寫入"
    )
    parser.add_argument("--doctor", action="store_true", required=True)
    parser.add_argument("--mode", choices=("full", "viewer", "history"), default="full")
    parser.add_argument("--model-type", default="PytorchMMBERT")
    parser.add_argument("--workpool", default="WorkPool")
    parser.add_argument("--root", default="TW Affairs", help="Jaal root used with --probe-jaal")
    parser.add_argument("--probe-jaal", action="store_true",
                        help="Also build the Jaal Dash app (read-only; no server)")
    return parser.parse_args(argv)


def main(argv=None, *, inspector=collect_checks, jaal_diagnose=None):
    args = parse_args(argv)
    print("Stage 4 read-only doctor")
    print("Interpreter:", sys.executable)
    print("Mode:", args.mode)
    checks = inspector(mode=args.mode, model_type=args.model_type,
                       workpool=args.workpool)
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
    failed = any(check.status == "FAIL" for check in checks)
    if args.probe_jaal:
        if failed:
            print("[SKIP] Jaal construction: fix metadata/path blockers before graph build")
        else:
            if jaal_diagnose is None:
                jaal_diagnose = jaal_probe.diagnose
            failed = jaal_diagnose(args.root) != 0
    print("STAGE4_DOCTOR_FAIL" if failed else "STAGE4_DOCTOR_PASS")
    print("No packages installed; no WorkPool changes; no model or service started.")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
