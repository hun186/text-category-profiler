"""KI-012 private release preflight with explicit non-production verdict.

Calls established PRIVATE temp DB tests and the existing disposable TCFMain
self-tests. Never executes live WorkPool or migration/cleanup commands.
No model is invoked unless operator explicitly opts in via --real-port.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


_ROOT = Path(__file__).resolve().parents[1]
_PRIVATE_CHECKS = (
    ("stage_contracts",
     ("-m", "unittest", "-v",
      "tests.test_bl001_stage_sql_atomic_fix",
      "tests.test_bl001_stage_sql_shared",
      "tests.test_bl001_df_sql_provider_contracts"), "unittest"),
    ("atomicity", ("-m", "scripts.bl001_stage_sqlite_atomicity_probe"),
     "PASS_ATOMICITY"),
    ("lock_recovery", ("-m", "scripts.bl001_stage_sqlite_lock_acceptance"), "PASS"),
    ("overlap", ("-m", "scripts.bl001_stage_sqlite_overlap_acceptance"), "PASS"),
    ("private_performance", ("-m", "scripts.bl001_stage_sqlite_performance_profile",
                             "--rows", "100", "--rounds", "1"), "PASS_MEASURED"),
    ("disk_checkpoints",
     ("-m", "scripts.bl001_stage_sqlite_disk_profile",
      "--rows", "100", "--repeat", "2"), "PASS_CHECKPOINT_MEASURED"),
    ("sqlite_full_rollback",
     ("-m", "scripts.bl001_stage_sqlite_full_rollback",
      "--rows", "120", "--repeat", "64"), "PASS_SQLITE_FULL_ROLLBACK"),
    ("parallel_stress", ("-m", "scripts.bl001_stage_sqlite_parallel_stress",
                         "--workers", "2", "--rounds", "1", "--rows", "20"), "PASS"),
    ("reader_snapshot",
     ("-m", "scripts.bl001_stage_sqlite_reader_snapshot", "--rows", "20"),
     "PASS_PRIVATE_READER_SNAPSHOT"),
    ("private_backup_restore",
     ("-m", "scripts.bl001_stage_sqlite_backup_restore", "--rows", "15"),
     "PASS_PRIVATE_BACKUP_RESTORE"),
    ("root_isolated", ("TCFMain.py", "--self-test", "isolated"), "FINAL: PASS"),
)



def _missing_child_modules(checks) -> list[str]:
    """Validate all checkout-owned commands before executing a preflight."""
    missing = []
    for _, argv, _ in checks:
        if argv[:2] == ("-m", "unittest"):
            names = [arg for arg in argv[2:] if not arg.startswith("-")]
        elif len(argv) >= 2 and argv[0] == "-m":
            names = [argv[1]]
        elif argv and argv[0].endswith(".py"):
            names = [argv[0]]
        else:
            names = []
        for name in names:
            path = (_ROOT / name) if name.endswith(".py") else (
                _ROOT / (name.replace(".", "/") + ".py")
            )
            if not path.is_file():
                missing.append(name)
    return missing

def _check_output(output: str, expected: str) -> bool:
    if expected == "unittest":
        match = re.search(r"\bRan (\d+) tests?\b", output)
        return (match is not None and int(match.group(1)) > 0
                and re.search(r"(?m)^OK(?:\s*)$", output) is not None
                and "skipped=" not in output)
    if expected == "FINAL: PASS":
        return re.search(r"(?m)^FINAL: PASS\s*$", output) is not None
    for line in reversed(output.splitlines()):
        if line.strip().startswith("{"):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            return record.get("status") == expected
    return False

def _real_selftest_outer_timeout() -> int:
    """Use CLI supervisor's actual 1800s timeout plus 300s cleanup headroom.

    config_from_cli() builds a new environment mapping and does NOT forward
    TCP_REAL_PIPELINE_TIMEOUT_SECONDS to its config resolver. Inheriting the
    wrapper's environment setting would risk killing the supervisor early.
    """
    return 2100

def run_private_preflight(*, real_port: int | None = None,
                          runner=None) -> dict:
    if real_port is not None and not 1 <= real_port <= 65535:
        raise ValueError("real_port must be between 1 and 65535")
    real_outer_timeout = (
        _real_selftest_outer_timeout() if real_port is not None else None
    )
    if runner is None:
        runner = subprocess.run
    checks = list(_PRIVATE_CHECKS)
    if real_port is not None:
        checks.append(("root_real_opt_in",
                       ("TCFMain.py", "--self-test", "real",
                        "-p", str(real_port)), "FINAL: PASS"))

    missing = _missing_child_modules(checks)
    if missing:
        return {
            "status": "FAIL",
            "scope": "private_checks_and_disposable_root_selftests_only",
            "reason": "missing_child_modules",
            "missing_modules": missing,
            "checks": [],
            "real_model_opt_in": real_port is not None,
            "production_workpool_verified": False,
        }

    results = []
    for name, argv, expected in checks:
        args = [sys.executable, *argv]
        timeout = real_outer_timeout if name == "root_real_opt_in" else 300
        try:
            done = runner(
                args, cwd=str(_ROOT), capture_output=True,
                text=True, timeout=timeout,
            )
            output = (done.stdout or "") + "\n" + (done.stderr or "")
            ok = (done.returncode == 0 and _check_output(output, expected))
            state = "PASS" if ok else "FAIL"
        except (OSError, subprocess.TimeoutExpired) as error:
            state = "FAIL"
            error_name = type(error).__name__
        result = {"name": name, "status": state}
        if state == "FAIL":
            # Do not copy arbitrary model/data/log content into JSON.
            result["error_type"] = (
                error_name if "error_name" in locals() else "FAILED_CHECK"
            )
        results.append(result)
        if state == "FAIL":
            return {
                "status": "FAIL",
                "scope": "private_checks_and_disposable_root_selftests_only",
                "checks": results,
                "real_model_opt_in": real_port is not None,
                "production_workpool_verified": False,
            }
        if "error_name" in locals():
            del error_name

    return {
        "status": ("PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION"
                   if real_port is not None else "PASS_PARTIAL_NO_REAL_MODEL"),
        "scope": "private_checks_and_disposable_root_selftests_only",
        "checks": results,
        "real_model_opt_in": real_port is not None,
        "production_workpool_verified": False,
        "limits": (
            "Even PASS with real model does not certify live WorkPool, "
            "network filesystem, production backup/rollback, or deployment."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Private-only release preflight; never touches live WorkPool."
    )
    parser.add_argument(
        "--real-port", type=int, default=None,
        help="Explicitly opt into existing real checkpoint self-test at this port",
    )
    args = parser.parse_args(argv)
    try:
        result = run_private_preflight(real_port=args.real_port)
    except Exception as error:
        result = {"status": "FAIL", "error_type": type(error).__name__}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return {
        "PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION": 0,
        "PASS_PARTIAL_NO_REAL_MODEL": 2,
    }.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
