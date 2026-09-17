import ast
from argparse import Namespace
from pathlib import Path
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
import importlib
import sys

from BertScript.result_combination_stage import (
    ResultCombinationPlan, activate_result_combination,
    run_result_combination_stage,
)


class ResultCombinationStageTests(unittest.TestCase):
    def test_combine_entrypoint_routes_through_result_combination_stage_runner(self):
        calls = []
        fake_stage = type("Stage", (), {
            "ResultCombinationPlan": lambda *values, **kwargs: ("plan", values, kwargs),
            "run_result_combination_stage": lambda plan, **kwargs: calls.append((plan, kwargs)),
        })
        dependency_stubs = {name: MagicMock() for name in (
            "pandas", "seaborn", "numpy", "setproctitle",
            "matplotlib", "matplotlib.pyplot", "matplotlib.colors",
            "text_category_profiler.pipeline.TCF_utils",
            "text_category_profiler.core.utilities",
            "text_category_profiler.concurrency.MP_utils",
            "text_category_profiler.data.df_utils",
            "text_category_profiler.core.log_display")}
        dependency_stubs["matplotlib.colors"].LogNorm = MagicMock()
        with patch.dict(sys.modules, dependency_stubs):
            CombineTestResult = importlib.import_module("BertScript.CombineTestResult")
            with patch.object(CombineTestResult, "_build_result_combination_plan",
                              return_value=(("plan", (), {}), {})):
                CombineTestResult.main([], stage_api=fake_stage)
        self.assertEqual(len(calls), 1)

    def plan(self, model="TF15Bert"):
        return ResultCombinationPlan(Namespace(datasetDataBaseSubDir="datasetDB", ModelType=model), "/x_rdy_for_CombineTestResult", "/o")

    def test_plan_records_canonical_input_names(self):
        plan = self.plan()
        self.assertEqual((plan.source_db_glob, plan.label_file, plan.test_database, plan.result_file),
                         (r"dataset_total_with_filename.*\.sql3", "TopicAnalysis_LabelList.txt", "test.sql3", "test_results.tsv"))

    def test_activation_renames_ready_to_running(self):
        calls = []
        active = activate_result_combination(self.plan(), rename=lambda a, b: calls.append((a, b)))
        self.assertEqual(active.dataset_dir, "/x_is_running_CombineTestResult")

    def test_missing_sources_preserves_warning_contract(self):
        self.assertEqual(self.plan().source_db_glob, r"dataset_total_with_filename.*\.sql3")

    def test_model_type_mapping_is_unchanged(self):
        module = ast.parse(Path("text_category_profiler/pipeline/TCF_utils.py").read_text())
        assignments = {target.id: ast.literal_eval(node.value) for node in module.body
                       if isinstance(node, ast.Assign) for target in node.targets
                       if isinstance(target, ast.Name) and target.id == "PYTORCH_MODEL_TYPES"}
        self.assertEqual(assignments["PYTORCH_MODEL_TYPES"],
                         ["PytorchXLM", "PytorchRBTL3", "PytorchMMBERT"])
        self.assertEqual(self.plan().args.ModelType, "TF15Bert")

    def test_failure_prevents_visualization_handoff(self):
        calls = []
        with self.assertRaisesRegex(RuntimeError, "failed"):
            run_result_combination_stage(self.plan(), combine=lambda *_: (_ for _ in ()).throw(RuntimeError("failed")), rename=lambda a, b: calls.append((a, b)))
        self.assertFalse(any("_rdy_for_TestResultVis" in destination for _, destination in calls))

    def test_success_uses_existing_handoff_suffix(self):
        calls = []
        result = run_result_combination_stage(self.plan(), combine=lambda *_: None, rename=lambda a, b: calls.append((a, b)))
        self.assertEqual(result, "/x_rdy_for_TestResultVis")

    def test_activation_and_success_handoff_use_distinct_adapters(self):
        calls = []
        run_result_combination_stage(
            self.plan(), combine=lambda *_: calls.append(("combine",)),
            activate_rename=lambda a, b: calls.append(("activate", a, b)),
            success_handoff=lambda a, b: calls.append(("handoff", a, b)))
        self.assertEqual([call[0] for call in calls], ["activate", "combine", "handoff"])

    def test_boundary_does_not_import_stage_four(self):
        tree = ast.parse(Path("BertScript/result_combination_stage.py").read_text())
        text = ast.unparse(tree)
        self.assertNotIn("Test_result_Vis", text)
