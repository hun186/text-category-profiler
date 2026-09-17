import ast
from argparse import Namespace
from pathlib import Path
import unittest

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
    def test_plan_preserves_pytorch_command(self):
        command = render_pytorch_command(args(), "/work_rdy_for_RunClassfier", "/model", "./BertScript")
        self.assertEqual(command, 'python ./BertScript/TextClassification_transformers.py -ts True -mdlDir /model -BertDataDir /work_rdy_for_RunClassfier -mdlType XLNet -ZeroShot False -MaxSeqLen 128 -SaveOptimizer False > "/work_rdy_for_RunClassfier/logs/RunClassfier.log" 2>&1 \n\n')

    def test_plan_preserves_tf_template_flags(self):
        command = render_tf_command(args(), "/data", "/model", "python run_classifier.py^\n", windows=False)
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
        self.assertIn(("system", "batch"), calls)

    def test_chmod_nonzero_still_runs_tf_batch(self):
        plan = ClassifierPlan(args(), "/x_rdy_for_RunClassfier", "/m", "tf", "tf", "batch")
        _, calls = self._run(plan, returns=7)
        self.assertIn(("system", "batch"), calls)

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
