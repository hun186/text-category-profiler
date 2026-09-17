import ast
from argparse import Namespace
from pathlib import Path
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
import importlib
import tempfile
import sys

from BertScript.classifier_stage import (
    ClassifierPlan, activate_classifier, render_pytorch_command,
    render_tf_command, run_classifier_stage,
)


def args(**changes):
    values = dict(train=False, test=True, ModelType="XLNet", ActiveHTCZeroshot=False,
                  MaxSeqLength=128, SaveOptimizer=False, keep_checkpoint_max=2)
    values.update(changes)
    return Namespace(**values)


class ClassifierStageTests(unittest.TestCase):
    def _runclassifier_module(self):
        modules = ("setproctitle", "TCF_Params.TCFParameters",
                   "text_category_profiler.core.utilities",
                   "text_category_profiler.pipeline.TCF_utils",
                   "text_category_profiler.core.conformer",
                   "text_category_profiler.concurrency.MP_utils",
                   "text_category_profiler.data.DB_utils",
                   "text_category_profiler.core.log_display")
        with patch.dict(sys.modules, {name: MagicMock() for name in modules}):
            return importlib.import_module("BertScript.RunClassfier")

    def _canonical_prepare(self, model_type, renderer, system_calls,
                           classifier_path=None):
        RunClassfier = self._runclassifier_module()
        RunClassfier.PYTORCH_MODEL_TYPES = ["PytorchXLM", "PytorchRBTL3", "PytorchMMBERT"]
        if classifier_path is not None:
            RunClassfier.BertClassfierPath = classifier_path
        dataset_dir = "/x_rdy_for_RunClassfier"
        model_dir = "/model"
        plan = ClassifierPlan(
            args(ModelType=model_type, modelDir=model_dir, test=False,
                 datasetDataBaseSubDir="datasetDB", WorkPoolROOT="/pool",
                 ExecutionTime="now"), dataset_dir, model_dir, "", "pending")
        patches = (
            patch.object(RunClassfier, "HybridConformer"),
            patch.object(RunClassfier, "MPlogger", return_value=MagicMock()),
            patch.object(RunClassfier.os.path, "isfile", return_value=False),
            patch.object(RunClassfier, "get_testResFile_Name", return_value=[]),
            patch.object(RunClassfier, "CopyModelRelatedFiles"),
            patch.object(RunClassfier, "ClearOldTestResFile"),
            patch.object(RunClassfier, "_display_model_command"),
        )
        for context in patches:
            context.start()
            self.addCleanup(context.stop)
        prepare = lambda active: RunClassfier._prepare_classifier(
            active,
            render_pytorch_command=renderer if model_type != "TF15Bert" else None,
            render_tf_command=renderer if model_type == "TF15Bert" else None)
        return plan, prepare

    def test_canonical_classifier_uses_extracted_pytorch_renderer(self):
        system_calls = []
        sentinel = "SENTINEL PYTORCH COMMAND"
        renderer = MagicMock(return_value=sentinel)
        plan, prepare = self._canonical_prepare("PytorchXLM", renderer, system_calls)
        run_classifier_stage(
            plan, prepare=prepare, system=lambda command: system_calls.append(command),
            rename=lambda *_: None, handoff=lambda *_: None)
        self.assertEqual(system_calls, [sentinel])
        renderer.assert_called_once()

    def test_canonical_classifier_uses_extracted_tf_renderer(self):
        RunClassfier = self._runclassifier_module()
        sentinel = "SENTINEL TF BATCH CONTENT"
        renderer = MagicMock(return_value=sentinel)
        system_calls = []
        with tempfile.TemporaryDirectory() as classifier_path:
            Path(classifier_path, "run_classifier_script_automatic_dynamic_template.txt").write_text(
                "template", encoding="utf-8")
            with patch.object(RunClassfier, "BertClassfierPath", classifier_path):
                plan, prepare = self._canonical_prepare(
                    "TF15Bert", renderer, system_calls, classifier_path)
                run_classifier_stage(
                    plan, prepare=prepare,
                    system=lambda command: system_calls.append(command),
                    rename=lambda *_: None, handoff=lambda *_: None)
                batch_file = Path(classifier_path, "run_classifier_script_automatic_dynamic.bat")
                self.assertEqual(batch_file.read_text(encoding="utf-8"), sentinel)
        renderer.assert_called_once()

    def test_runclassifier_entrypoint_routes_through_classifier_stage_runner(self):
        calls = []
        fake_stage = type("Stage", (), {
            "ClassifierPlan": lambda *values, **kwargs: ("plan", values, kwargs),
            "run_classifier_stage": lambda plan, **kwargs: calls.append((plan, kwargs)),
        })
        fake_plan = type("Plan", (), {"args": args(train=False)})()
        modules = ("setproctitle", "TCF_Params.TCFParameters",
                   "text_category_profiler.core.utilities",
                   "text_category_profiler.pipeline.TCF_utils",
                   "text_category_profiler.core.conformer",
                   "text_category_profiler.concurrency.MP_utils",
                   "text_category_profiler.data.DB_utils",
                   "text_category_profiler.core.log_display")
        with patch.dict(sys.modules, {name: MagicMock() for name in modules}):
            RunClassfier = importlib.import_module("BertScript.RunClassfier")
            with patch.object(RunClassfier, "_build_classifier_plan",
                              return_value=(fake_plan, {})):
                RunClassfier.main([], stage_api=fake_stage)
        self.assertEqual(len(calls), 1)

    def test_plan_preserves_pytorch_command(self):
        command = render_pytorch_command(args(), "/work_rdy_for_RunClassfier", "/model", "./BertScript")
        self.assertEqual(command, 'python ./BertScript/TextClassification_transformers.py -ts True -mdlDir /model -BertDataDir /work_rdy_for_RunClassfier -mdlType XLNet -ZeroShot False -MaxSeqLen 128 -SaveOptimizer False > "/work_rdy_for_RunClassfier/logs/RunClassfier.log" 2>&1 \n\n')

    def test_plan_preserves_tf_template_flags(self):
        command = render_tf_command(args(), "/data", "/model", "python run_classifier.py^\n", windows=False)
        self.assertEqual(
            command,
            'python run_classifier.py\\\n--do_train=False \\\n--output_dir=/model/  \\\n--do_predict=True \\\n--keep_checkpoint_max=2 \\\n--data_dir=/data/  \\\n> "/data/logs/RunClassfier.log" 2>&1 \n\n')
        for flag in ("--do_train=False", "--output_dir=/model/", "--do_predict=True", "--keep_checkpoint_max=2", "--data_dir=/data/"):
            self.assertIn(flag, command)

    def test_activation_renames_ready_to_running(self):
        calls = []
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "cmd /x_rdy_for_RunClassfier", "pytorch")
        active = activate_classifier(plan, rename=lambda a, b: calls.append((a, b)))
        self.assertEqual(calls, [("/x_rdy_for_RunClassfier", "/x_is_running_RunClassfier")])
        self.assertIn("_is_running_", active.command)

    def _run(self, plan, returns=None, raises_at=None):
        calls = []
        def system(command):
            calls.append(("system", command))
            if raises_at and raises_at in command:
                raise OSError("boom")
            return returns or 0
        result = run_classifier_stage(plan, system=system,
            wait_until_stable=lambda path: calls.append(("wait", path)),
            result_files=["result"], rename=lambda a, b: calls.append(("rename", a, b)),
            warn=lambda msg: calls.append(("warn", msg)))
        return result, calls

    def test_windows_activation_nonzero_still_runs_batch(self):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "tf", "tf", "batch", "activate")
        _, calls = self._run(plan, returns=7)
        self.assertTrue(any(call in calls for call in (("system", "batch"), ("system", "./batch"))))

    def test_chmod_nonzero_still_runs_tf_batch(self):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "tf", "tf", "batch")
        _, calls = self._run(plan, returns=7)
        self.assertIn(("system", "./batch"), calls)

    @patch("BertScript.classifier_stage.platform.system", return_value="Linux")
    def test_linux_tf_preserves_chmod_target_and_dot_slash_execution(self, _):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "tf", "tf", "/tmp/run.bat")
        _, calls = self._run(plan)
        systems = [call for call in calls if call[0] == "system"]
        self.assertEqual(systems[:2], [("system", "chmod 700 /tmp/run.bat"),
                                      ("system", ".//tmp/run.bat")])

    def test_tf_test_finalization_occurs_after_wait_and_before_handoff(self):
        calls = []
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "tf", "tf", "batch")
        run_classifier_stage(plan, system=lambda cmd: calls.append(("system", cmd)),
            wait_until_stable=lambda path: calls.append(("wait", path)), result_files=["result"],
            finalize=lambda active: calls.append(("finalize", active.dataset_dir)),
            rename=lambda a, b: calls.append(("rename", a, b)))
        self.assertLess(calls.index(("wait", "result")),
                        next(i for i, call in enumerate(calls) if call[0] == "finalize"))
        self.assertLess(next(i for i, call in enumerate(calls) if call[0] == "finalize"),
                        max(i for i, call in enumerate(calls) if call[0] == "rename"))

    def test_final_handoff_adapter_receives_legacy_destination(self):
        calls = []
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "torch", "cmd")
        result = run_classifier_stage(plan, system=lambda command: 0,
                                      result_files=[], rename=lambda a, b: None,
                                      handoff=lambda a, b: calls.append((a, b)))
        self.assertEqual(calls, [("/x_is_running_RunClassfier", "/x_rdy_for_CombineTestResult")])
        self.assertEqual(result, "/x_rdy_for_CombineTestResult")

    def test_legacy_handoff_retries_five_times_and_sleeps_after_each_attempt(self):
        modules = ("setproctitle", "TCF_Params.TCFParameters",
                   "text_category_profiler.core.utilities",
                   "text_category_profiler.pipeline.TCF_utils",
                   "text_category_profiler.core.conformer",
                   "text_category_profiler.concurrency.MP_utils",
                   "text_category_profiler.data.DB_utils",
                   "text_category_profiler.core.log_display")
        with patch.dict(sys.modules, {name: MagicMock() for name in modules}):
            module = importlib.import_module("BertScript.RunClassfier")
        calls = []
        module._retry_classifier_handoff(
            "/x_is_running_RunClassfier", "/x_rdy_for_CombineTestResult",
            rename=lambda a, b: calls.append(("rename", a, b)),
            isdir=lambda path: False,
            sleep=lambda seconds: calls.append(("sleep", seconds)))
        self.assertEqual([call[0] for call in calls], ["rename", "sleep"] * 5)

    def test_legacy_handoff_stops_when_destination_exists(self):
        from BertScript import RunClassfier
        calls = []
        states = iter((False, True))
        RunClassfier._retry_classifier_handoff(
            "source", "destination", rename=lambda a, b: calls.append((a, b)),
            isdir=lambda path: next(states), sleep=lambda seconds: None)
        self.assertEqual(calls, [("source", "destination")])

    def test_tf_batch_nonzero_reaches_artifact_wait(self):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "tf", "tf", "batch")
        _, calls = self._run(plan, returns=4)
        self.assertIn(("wait", "result"), calls)

    def test_pytorch_nonzero_reaches_artifact_wait(self):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "torch", "pytorch")
        _, calls = self._run(plan, returns=3)
        self.assertIn(("wait", "result"), calls)

    def test_pytorch_python_exception_warns_and_continues(self):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "torch", "pytorch")
        _, calls = self._run(plan, raises_at="torch")
        self.assertTrue(any(c[0] == "warn" for c in calls))
        self.assertIn(("wait", "result"), calls)

    def test_tf_python_exception_propagates(self):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "tf", "tf", "batch")
        with self.assertRaises(OSError):
            self._run(plan, raises_at="batch")

    def test_test_success_handoffs_to_combine(self):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "torch", "pytorch")
        result, _ = self._run(plan)
        self.assertEqual(result, "/x_rdy_for_CombineTestResult")

    def test_training_keeps_background_semantics(self):
        self.assertTrue(render_pytorch_command(args(train=True, test=False), "/d", "/m", "/b").endswith(" 2>&1 & \n\n"))

    def test_boundary_does_not_import_later_stages(self):
        tree = ast.parse(Path("BertScript/classifier_stage.py").read_text())
        names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(any("CombineTestResult" in name or "Test_result_Vis" in name for name in names))
