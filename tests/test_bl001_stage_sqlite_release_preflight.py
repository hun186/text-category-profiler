"""Release preflight gating logic with fake child commands, no models loaded."""
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
import io
import json

from scripts.bl001_stage_sqlite_release_preflight import (
    _PRIVATE_CHECKS, _missing_child_modules, _real_selftest_outer_timeout,
    _check_output, main, run_private_preflight,
)


def fake_runner(args, **kwargs):
    if "-m" in args:
        module = args[args.index("-m") + 1]
        if module == "unittest":
            output = "Ran 21 tests in 1.0s\n\nOK\n"
        elif module.endswith("atomicity_probe"):
            output = '{"status":"PASS_ATOMICITY"}\n'
        elif module.endswith("performance_profile"):
            output = '{"status":"PASS_MEASURED"}\n'
        elif module.endswith("disk_profile"):
            output = '{"status":"PASS_CHECKPOINT_MEASURED"}\n'
        elif module.endswith("full_rollback"):
            output = '{"status":"PASS_SQLITE_FULL_ROLLBACK"}\n'
        elif module.endswith("reader_snapshot"):
            output = '{"status":"PASS_PRIVATE_READER_SNAPSHOT"}\n'
        elif module.endswith("backup_restore"):
            output = '{"status":"PASS_PRIVATE_BACKUP_RESTORE"}\n'
        else:
            output = '{"status":"PASS"}\n'
    else:
        output = "FINAL: PASS\n"
    return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")


class ReleasePreflightTests(unittest.TestCase):
    def test_backup_restore_is_required_and_never_certifies_workpool(self):
        private = [entry for entry in _PRIVATE_CHECKS
                   if entry[0] == "private_backup_restore"]
        self.assertEqual(private, [(
            "private_backup_restore",
            ("-m", "scripts.bl001_stage_sqlite_backup_restore", "--rows", "15"),
            "PASS_PRIVATE_BACKUP_RESTORE",
        )])
        outcome = run_private_preflight(runner=fake_runner)
        self.assertEqual(outcome["status"], "PASS_PARTIAL_NO_REAL_MODEL")
        checks = {x["name"]: x["status"] for x in outcome["checks"]}
        self.assertEqual(checks["private_backup_restore"], "PASS")
        self.assertFalse(outcome["production_workpool_verified"])

    def test_backup_restore_generic_pass_cannot_fake_success(self):
        def incorrect_runner(args, **kwargs):
            if "scripts.bl001_stage_sqlite_backup_restore" in args:
                return subprocess.CompletedProcess(
                    args, 0, stdout='{"status":"PASS"}\n', stderr=""
                )
            return fake_runner(args, **kwargs)
        report = run_private_preflight(runner=incorrect_runner)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["checks"][-1]["name"], "private_backup_restore")
        self.assertFalse(report["production_workpool_verified"])

    def test_backup_restore_failure_blocks_model_tests(self):
        def broken_runner(args, **kwargs):
            if "scripts.bl001_stage_sqlite_backup_restore" in args:
                return subprocess.CompletedProcess(
                    args, 1, stdout='{"status":"FAIL_OR_BLOCKED"}\n', stderr=""
                )
            return fake_runner(args, **kwargs)
        report = run_private_preflight(real_port=8050, runner=broken_runner)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["checks"][-1]["name"], "private_backup_restore")
        self.assertFalse(any(x["name"].startswith("root_") for x in report["checks"]))

    def test_reader_snapshot_is_required_with_bounded_private_rows(self):
        required = [item for item in _PRIVATE_CHECKS
                    if item[0] == "reader_snapshot"]
        self.assertEqual(required, [(
            "reader_snapshot",
            ("-m", "scripts.bl001_stage_sqlite_reader_snapshot",
             "--rows", "20"), "PASS_PRIVATE_READER_SNAPSHOT",
        )])
        outcome = run_private_preflight(runner=fake_runner)
        self.assertEqual(outcome["status"], "PASS_PARTIAL_NO_REAL_MODEL")
        self.assertEqual(
            {item["name"]: item["status"] for item in outcome["checks"]}[
                "reader_snapshot"
            ], "PASS",
        )
        self.assertFalse(outcome["production_workpool_verified"])

    def test_reader_snapshot_wrong_success_token_fails_closed(self):
        def faulty_runner(args, **kwargs):
            if "scripts.bl001_stage_sqlite_reader_snapshot" in args:
                return subprocess.CompletedProcess(
                    args, 0, stdout='{"status":"PASS"}\n', stderr=""
                )
            return fake_runner(args, **kwargs)
        result = run_private_preflight(runner=faulty_runner)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["checks"][-1]["name"], "reader_snapshot")
        self.assertFalse(result["production_workpool_verified"])

    def test_private_preflight_includes_disk_and_sqlite_quota_checks(self):
        expected = {
            "disk_checkpoints": "PASS_CHECKPOINT_MEASURED",
            "sqlite_full_rollback": "PASS_SQLITE_FULL_ROLLBACK",
        }
        self.assertEqual(
            {name: status for name, _, status in _PRIVATE_CHECKS
             if name in expected}, expected,
        )
        outcome = run_private_preflight(runner=fake_runner)
        self.assertEqual(outcome["status"], "PASS_PARTIAL_NO_REAL_MODEL")
        statuses = {x["name"]: x["status"] for x in outcome["checks"]}
        self.assertEqual({name: statuses[name] for name in expected},
                         dict.fromkeys(expected, "PASS"))
        self.assertFalse(outcome["production_workpool_verified"])

    def test_disk_false_green_status_is_rejected(self):
        def false_green(args, **kwargs):
            if "scripts.bl001_stage_sqlite_disk_profile" in args:
                return subprocess.CompletedProcess(
                    args, 0, stdout='{"status":"PASS"}\n', stderr=""
                )
            return fake_runner(args, **kwargs)
        outcome = run_private_preflight(runner=false_green)
        self.assertEqual(outcome["status"], "FAIL")
        self.assertEqual(outcome["checks"][-1]["name"], "disk_checkpoints")
        self.assertFalse(outcome["production_workpool_verified"])

    def test_sqlite_full_failure_stops_before_any_root_selftest(self):
        def fail_full(args, **kwargs):
            if "scripts.bl001_stage_sqlite_full_rollback" in args:
                return subprocess.CompletedProcess(
                    args, 1, stdout='{"status":"FAIL_OR_BLOCKED"}\n', stderr=""
                )
            return fake_runner(args, **kwargs)
        outcome = run_private_preflight(real_port=8050, runner=fail_full)
        self.assertEqual(outcome["status"], "FAIL")
        self.assertEqual(outcome["checks"][-1]["name"], "sqlite_full_rollback")
        self.assertFalse(any(x["name"].startswith("root_") for x in outcome["checks"]))

    def test_real_supervisor_timeout_tracks_actual_cli_default_not_env(self):
        from unittest.mock import patch
        captured = []

        def capture_runner(args, **kwargs):
            captured.append((args, kwargs["timeout"]))
            return fake_runner(args, **kwargs)

        for configured in ("600", "1800", "3600", "invalid"):
            with self.subTest(configured=configured):
                with patch.dict("os.environ", {
                    "TCP_REAL_PIPELINE_TIMEOUT_SECONDS": configured,
                }):
                    self.assertEqual(_real_selftest_outer_timeout(), 2100)
                    outcome = run_private_preflight(
                        real_port=8050, runner=capture_runner,
                    )
                self.assertEqual(
                    outcome["status"], "PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION"
                )
                self.assertEqual(captured[-1][1], 2100)
                self.assertEqual(captured[-1][0][-2:], ["-p", "8050"])

    def test_all_configured_checkout_modules_exist(self):
        self.assertEqual(_missing_child_modules(_PRIVATE_CHECKS), [])
        self.assertEqual(
            _missing_child_modules((
                ("deliberate_missing", ("-m", "scripts.no_such_ki012_probe"), "PASS"),
            )),
            ["scripts.no_such_ki012_probe"],
        )

    def test_missing_child_fails_closed_without_running_commands(self):
        from unittest.mock import patch
        invoked = []
        def must_not_run(*args, **kwargs):
            invoked.append(True)
            raise AssertionError("runner must not be called")
        with patch(
            "scripts.bl001_stage_sqlite_release_preflight._missing_child_modules",
            return_value=["scripts.bl001_stage_sqlite_parallel_stress"],
        ):
            outcome = run_private_preflight(runner=must_not_run)
        self.assertEqual(outcome["status"], "FAIL")
        self.assertEqual(outcome["reason"], "missing_child_modules")
        self.assertFalse(outcome["production_workpool_verified"])
        self.assertEqual(invoked, [])

    def test_partial_without_real_model_is_not_full_pass(self):
        outcome = run_private_preflight(runner=fake_runner)
        self.assertEqual(outcome["status"], "PASS_PARTIAL_NO_REAL_MODEL")
        self.assertFalse(outcome["real_model_opt_in"])
        self.assertFalse(outcome["production_workpool_verified"])
        self.assertNotIn("root_real_opt_in", [x["name"] for x in outcome["checks"]])
        self.assertGreaterEqual(len(outcome["checks"]), 7)

    def test_explicit_real_mode_pass_still_does_not_certify_workpool(self):
        result = run_private_preflight(real_port=8050, runner=fake_runner)
        self.assertEqual(result["status"], "PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION")
        self.assertEqual(result["checks"][-1]["name"], "root_real_opt_in")
        self.assertTrue(result["real_model_opt_in"])
        self.assertFalse(result["production_workpool_verified"])

    def test_failure_stops_before_real_mode(self):
        def fail_one(args, **kwargs):
            if "scripts.bl001_stage_sqlite_lock_acceptance" in args:
                return subprocess.CompletedProcess(args, 1, stdout='{"status":"FAIL"}', stderr="")
            return fake_runner(args, **kwargs)
        outcome = run_private_preflight(real_port=8050, runner=fail_one)
        self.assertEqual(outcome["status"], "FAIL")
        self.assertEqual(outcome["checks"][-1]["name"], "lock_recovery")
        self.assertFalse(outcome["production_workpool_verified"])

    def test_preflight_rejects_skips_and_fake_green_exit_without_evidence(self):
        self.assertFalse(_check_output("Ran 0 tests\nOK", "unittest"))
        self.assertFalse(_check_output("Ran 7 tests\nOK (skipped=2)", "unittest"))
        self.assertFalse(_check_output('{"status":"FAIL"}\n', "PASS"))
        self.assertFalse(_check_output("FINAL: FAIL\n", "FINAL: PASS"))
        with self.assertRaises(ValueError):
            run_private_preflight(real_port=0, runner=fake_runner)

    def test_cli_partial_and_bad_port_reporting(self):
        from unittest.mock import patch
        with patch(
            "scripts.bl001_stage_sqlite_release_preflight.subprocess.run",
            side_effect=fake_runner,
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                status = main([])
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(out.getvalue())["status"],
                             "PASS_PARTIAL_NO_REAL_MODEL")
            out = io.StringIO()
            with redirect_stdout(out):
                status = main(["--real-port", "8050"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(out.getvalue())["status"],
                             "PASS_PRIVATE_PREFLIGHT_NOT_PRODUCTION")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--real-port", "0"]), 1)


if __name__ == "__main__":
    unittest.main()
