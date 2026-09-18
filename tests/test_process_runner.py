import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from text_category_profiler.execution.process import (
    LegacyShellProcessRunner,
    ProcessRunner,
    RootFailFastPolicy,
)


ROOT = Path(__file__).resolve().parents[1]


class RecordingRunner:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return self.result


def _module(name, **attributes):
    module = types.ModuleType(name)
    vars(module).update(attributes)
    return module


def load_main(subprocess_run):
    no_op = lambda *args, **kwargs: None
    stubs = {
        "setproctitle": _module("setproctitle", setproctitle=no_op),
        "subprocess": _module("subprocess", run=subprocess_run),
        "TCF_Params.TCFParameters": _module(
            "TCFParameters", setArguments=no_op, planArguments=no_op,
            activateArguments=no_op, WorkPoolROOT="WorkPool",
            BertClassfierPath="BertScript", FinalOfferedOutputFNrePatList=[],
        ),
        "text_category_profiler.core.utilities": _module(
            "utilities", OSWALK=lambda path: [], MKDIR=no_op,
            ShowElapsedTime=no_op, exit_program=no_op, chownPath=no_op,
        ),
        "text_category_profiler.core.conformer": _module(
            "conformer", HybridConformer=no_op,
        ),
        "text_category_profiler.pipeline.TCF_utils": _module(
            "TCF_utils", BackupAIPredictResultAndDelTempFile=no_op,
            convert_to_args_str=lambda args: "", datasetDirOutputDirPickers=no_op,
        ),
        "text_category_profiler.pipeline.DataConverter_utils": _module(
            "DataConverter_utils", CheckDatasetFiles=no_op,
            RawAndPredictionMerger=no_op,
        ),
        "text_category_profiler.concurrency.MP_utils": _module(
            "MP_utils", MPlogger=no_op,
        ),
        "text_category_profiler.core.log_display": _module(
            "log_display", **{name: no_op for name in
            ("info", "print_args_summary", "print_command", "stage_banner",
             "stage_done", "stage_failed", "warning")},
        ),
    }
    name = "_process_runner_tcf_main"
    spec = importlib.util.spec_from_file_location(name, ROOT / "TCFMain.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


class ProcessRunnerTests(unittest.TestCase):
    def test_protocol_accepts_string_command(self):
        runner: ProcessRunner = RecordingRunner(types.SimpleNamespace(returncode=0))
        result = runner.execute("python stage.py --path directory with spaces")
        self.assertEqual(0, result.returncode)

    def test_legacy_runner_calls_subprocess_with_shell_true_check_false(self):
        calls = []
        expected = types.SimpleNamespace(returncode=0)

        def run_process(command, **kwargs):
            calls.append((command, kwargs))
            return expected

        result = LegacyShellProcessRunner(run_process=run_process).execute("python stage.py")
        self.assertIs(expected, result)
        self.assertEqual(
            [("python stage.py", {"shell": True, "check": False})], calls
        )

    def test_runner_returns_nonzero_without_raising(self):
        expected = types.SimpleNamespace(returncode=23)
        runner = LegacyShellProcessRunner(run_process=lambda *args, **kwargs: expected)
        self.assertIs(expected, runner.execute("python failing.py"))

    def test_root_policy_reports_and_raises_on_nonzero(self):
        reports = []
        policy = RootFailFastPolicy(
            failure_reporter=lambda stage, code, command: reports.append(
                (stage, code, command)
            )
        )
        result = types.SimpleNamespace(returncode=7)
        with self.assertRaisesRegex(
            RuntimeError,
            r"Classifier failed with exit code 7\. Abort following stages\. "
            r"Command: python classifier\.py",
        ):
            policy.check(result, "Classifier", "python classifier.py")
        self.assertEqual(
            [("Classifier", 7, "python classifier.py")], reports
        )

    def test_root_compatibility_function_delegates_to_default_runner(self):
        calls = []

        def run_process(command, **kwargs):
            calls.append((command, kwargs))
            return types.SimpleNamespace(returncode=0)

        module = load_main(run_process)
        result = module.run_stage_command("python stage.py", "stage")
        self.assertEqual(0, result.returncode)
        self.assertEqual(
            [("python stage.py", {"shell": True, "check": False})], calls
        )

    def test_owner_policy_matrix_keeps_nonzero_and_python_exception_distinct(self):
        nonzero = types.SimpleNamespace(returncode=19)
        ignore_nonzero_runner = RecordingRunner(result=nonzero)
        self.assertIs(nonzero, ignore_nonzero_runner.execute("python ignored.py"))

        caught = []
        caught_exception_runner = RecordingRunner(error=OSError("cannot invoke shell"))
        try:
            caught_exception_runner.execute("python caught.py")
        except OSError as error:
            caught.append(str(error))

        self.assertEqual(["cannot invoke shell"], caught)
        self.assertEqual(["python caught.py"], caught_exception_runner.commands)


if __name__ == "__main__":
    unittest.main()
