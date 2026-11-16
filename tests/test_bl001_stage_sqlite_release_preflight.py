"""Release preflight gating logic with fake child commands, no models loaded."""
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
import io
import json

from scripts.bl001_stage_sqlite_release_preflight import (
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
        else:
            output = '{"status":"PASS"}\n'
    else:
        output = "FINAL: PASS\n"
    return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")


class ReleasePreflightTests(unittest.TestCase):
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
