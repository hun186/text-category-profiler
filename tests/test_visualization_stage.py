import importlib
import ast
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


class VisualizationStageTests(unittest.TestCase):
    def setUp(self):
        self.stage = importlib.import_module("BertScript.visualization_stage")

    def test_plan_preserves_host_and_weitech_options(self):
        args = Namespace(
            TRVWebHost=True,
            public=False,
            TRVPort=8123,
            WeiTechFormatSepWorkPool=True,
            WeiTechFormatInputPATH="input",
            WeiTechFormatOutputPATH="output",
        )
        plan = self.stage.build_visualization_plan(args, "job_rdy_for_TestResultVis", "model")
        self.assertTrue(plan.hosted)
        self.assertEqual((plan.host, plan.port), ("127.0.0.1", 8123))
        self.assertEqual(plan.weitech_input_path, "input")
        self.assertEqual(plan.weitech_output_path, "output")
        self.assertTrue(plan.weitech_separate_work_pool)

    def test_dataset_count_falls_back_from_model_to_active_workspace(self):
        utility_path = Path("text_category_profiler/pipeline/TCF_utils.py")
        visualization_path = Path("BertScript/Test_result_Vis.py")
        load_dataset_count = next(
            node for node in ast.parse(utility_path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name == "LoadDatasetCount")
        build_color_df = next(
            node for node in ast.parse(
                visualization_path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name == "BuildColorDF")

        with tempfile.TemporaryDirectory() as root:
            model_dir = Path(root, "model")
            workspace = Path(root, "dataset_workspace")
            count_file = Path(
                workspace, "datasetDB", "dataset_total_FixedTest_labels_count.sql3")
            model_dir.mkdir()
            count_file.parent.mkdir(parents=True)
            count_file.touch()

            count_frame = mock.MagicMock()
            count_frame.set_index.return_value = count_frame
            color_frame = mock.MagicMock()
            class_table_frame = mock.MagicMock()
            pandas = mock.Mock()
            pandas.DataFrame.side_effect = [color_frame, class_table_frame]
            namespace = {
                "OSWALK": lambda directory: [
                    os.path.join(path, filename)
                    for path, _, filenames in os.walk(directory)
                    for filename in filenames
                ],
                "getFNFromFullPath": os.path.basename,
                "dfFromSQLite3": mock.Mock(return_value=count_frame),
                "pd": pandas,
                "InfoScoreTable": {},
                "outputDir": str(model_dir),
                "datasetDir": str(workspace),
            }
            module = ast.Module(
                body=[load_dataset_count, build_color_df], type_ignores=[])
            exec(compile(module, "Stage4DatasetCount.py", "exec"), namespace)

            namespace["BuildColorDF"](
                {"label": "#fff"},
                {"label": {"CT": "Label", "Explaination": "Explanation"}},
            )

            namespace["dfFromSQLite3"].assert_called_once_with(str(count_file))

    def test_plan_creation_has_no_filesystem_side_effects(self):
        args = Namespace(TRVWebHost=False, public=True, TRVPort=80,
                         WeiTechFormatSepWorkPool=False,
                         WeiTechFormatInputPATH="in", WeiTechFormatOutputPATH="out")
        rename = mock.Mock()
        self.stage.build_visualization_plan(args, "x_rdy_for_TestResultVis", "model")
        rename.assert_not_called()

    def test_activation_uses_canonical_suffix(self):
        plan = self._plan()
        rename = mock.Mock()
        running = self.stage.activate_visualization(plan, rename=rename)
        self.assertEqual(running, "x_is_running_TestResultVis")
        rename.assert_called_once_with("x_rdy_for_TestResultVis", "x_is_running_TestResultVis")

    def test_nonhosted_path_does_not_start_server(self):
        plan = self._plan(hosted=False)
        calls = []
        self.stage.run_visualization_stage(
            plan, rename=lambda old, new: calls.append((old, new)),
            application=lambda active: calls.append(("application", active)),
            start_server=lambda _: calls.append("server"), validate=lambda _: True)
        self.assertNotIn("server", calls)
        self.assertEqual(calls[-1], ("x_is_running_TestResultVis", "x_rdy_for_Spike"))

    def test_hosted_path_preserves_cleanup_and_server_options(self):
        plan = self._plan(hosted=True)
        server = mock.Mock()
        self.stage.run_visualization_stage(
            plan, rename=mock.Mock(), application=mock.Mock(), start_server=server,
            validate=lambda _: True)
        server.assert_called_once_with(plan)
        self.assertEqual(plan.process_name, "TRV9000")
        self.assertEqual((plan.debug, plan.use_reloader, plan.ssl_context), (True, False, "adhoc"))

    def test_validation_failure_does_not_mark_stage_complete(self):
        plan = self._plan()
        rename = mock.Mock()
        with self.assertRaises(RuntimeError):
            self.stage.run_visualization_stage(
                plan, rename=rename, application=mock.Mock(), start_server=mock.Mock(),
                validate=lambda _: False)
        self.assertEqual(rename.call_args_list, [mock.call("x_rdy_for_TestResultVis", "x_is_running_TestResultVis")])

    def test_summary_nonzero_continues_to_artifact_processing(self):
        status = self.stage.run_summary_command("summary", lambda _: 7)
        self.assertEqual(status, 7)

    def test_summary_python_exception_propagates(self):
        def fail(_):
            raise OSError("cannot invoke")
        with self.assertRaises(OSError):
            self.stage.run_summary_command("summary", fail)

    def test_importing_stage_plan_does_not_import_dash(self):
        code = "import sys; import BertScript.visualization_stage; assert 'dash' not in sys.modules"
        subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).parents[1])

    def test_test_result_vis_bootstrap_imports_visualization_stage_after_repo_root_setup(self):
        repository_root = Path(__file__).resolve().parents[1]
        script = repository_root / "BertScript" / "Test_result_Vis.py"
        tree = ast.parse(script.read_text(encoding="utf-8"))
        bootstrap = []
        for node in tree.body:
            bootstrap.append(node)
            if (isinstance(node, ast.ImportFrom) and node.module == "BertScript"
                    and any(alias.name == "visualization_stage" for alias in node.names)):
                break
        else:
            self.fail("canonical visualization_stage bootstrap import was not found")

        prefix = ast.unparse(ast.Module(body=bootstrap, type_ignores=[]))
        harness = """
import sys
sys.path[:] = [path for path in sys.path if path not in ({root!r}, '')]
sys.path.insert(0, {script_dir!r})
namespace = {{'__file__': {script!r}}}
exec(compile({prefix!r}, {script!r}, 'exec'), namespace)
assert namespace['visualization_stage'].__name__ == 'BertScript.visualization_stage'
""".format(
            root=str(repository_root), script_dir=str(script.parent),
            script=str(script), prefix=prefix)
        subprocess.run([sys.executable, "-c", harness], check=True,
                       cwd=repository_root.parent)

    def test_canonical_summary_execution_routes_through_stage_policy(self):
        calls = []

        class StageAPI:
            @staticmethod
            def run_summary_command(command, invoke):
                calls.append((command, invoke))
                return invoke(command)

        invoke = mock.Mock(return_value=0)
        self._execute_canonical_summary_slice(
            StageAPI, invoke, mock.Mock(return_value=[]))
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][1], invoke)

    def test_canonical_summary_nonzero_continues_to_artifact_processing(self):
        artifacts = mock.Mock(return_value=[])

        class StageAPI:
            @staticmethod
            def run_summary_command(command, invoke):
                return invoke(command)

        self._execute_canonical_summary_slice(
            StageAPI, mock.Mock(return_value=7), artifacts)
        artifacts.assert_called_once_with("summary-source")

    def test_canonical_summary_python_exception_prevents_artifact_processing(self):
        artifacts = mock.Mock(return_value=[])

        class StageAPI:
            @staticmethod
            def run_summary_command(command, invoke):
                return invoke(command)

        invoke = mock.Mock(side_effect=OSError("cannot invoke"))
        with self.assertRaisesRegex(OSError, "cannot invoke"):
            self._execute_canonical_summary_slice(StageAPI, invoke, artifacts)
        artifacts.assert_not_called()

    def test_command_executor_nonzero_is_caught_and_callback_continues(self):
        source = Path("text_category_profiler/concurrency/MP_utils.py").read_text(encoding="utf-8")
        command_executor = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.ClassDef) and node.name == "CommandExecutor")
        namespace = {"threading": threading, "subprocess": subprocess}
        exec(compile(ast.Module(body=[command_executor], type_ignores=[]),
                     "MP_utils.py", "exec"), namespace)
        CommandExecutor = namespace["CommandExecutor"]
        continued = []
        with mock.patch("subprocess.run", side_effect=subprocess.CalledProcessError(2, "bad")):
            executor = CommandExecutor("bad")
            executor.run()
            executor.join()
            continued.append(True)
        self.assertEqual(continued, [True])

    def test_test_result_vis_entrypoint_routes_through_visualization_stage_runner(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        main_node = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "main")
        received = []
        plan = self._plan()
        class FakeStageAPI:
            @staticmethod
            def build_visualization_plan(args, workspace, output):
                received.append(("build", args, workspace, output))
                return plan
            @staticmethod
            def run_visualization_stage(actual_plan, **adapters):
                received.append(("run", actual_plan, adapters))
                return actual_plan.completed_workspace
        class Picker:
            def proc(self):
                return plan.ready_workspace, plan.output_dir
        logger = mock.Mock()
        namespace = {
            "visualization_stage": FakeStageAPI,
            "setproctitle": mock.Mock(), "os": mock.Mock(),
            "ClassfierOptionParser": lambda argv=None: mock.Mock(),
            "datasetDirOutputDirPickers": lambda **_: Picker(),
            "MPlogger": lambda **_: logger,
            "_run_visualization_application": mock.Mock(),
            "_start_visualization_server": mock.Mock(),
            "_validate_visualization": mock.Mock(),
            "MPLOGGER": logger, "stage_done": mock.Mock(), "MES": "hosted",
        }
        namespace["os"].getcwd.return_value = "/workspace"
        namespace["os"].path.sep = "/"
        exec(compile(ast.Module(body=[main_node], type_ignores=[]),
                     "Test_result_Vis.py", "exec"), namespace)
        namespace["main"](stage_api=FakeStageAPI)
        self.assertEqual([item[0] for item in received], ["build", "run"])
        self.assertIs(received[1][1], plan)

    def test_post_completion_logging_does_not_recreate_running_workspace(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        main_node = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "main")

        with tempfile.TemporaryDirectory() as root:
            ready_workspace = Path(root, "dataset_rdy_for_TestResultVis")
            running_workspace = Path(root, "dataset_is_running_TestResultVis")
            completed_workspace = Path(root, "dataset_rdy_for_Spike")
            ready_workspace.mkdir()
            plan = self.stage.VisualizationPlan(
                ready_workspace=str(ready_workspace), output_dir="model",
                hosted=False, host="0.0.0.0", port=9000,
                weitech_separate_work_pool=False, weitech_input_path="in",
                weitech_output_path="out", ssl_context="adhoc")

            class FileLogger:
                def __init__(self, logSubDir="logs", **_):
                    self.log_dir = Path(logSubDir)

                def logW(self, message=None, logFile="mp_processing_log.txt", **_):
                    self.log_dir.mkdir(parents=True, exist_ok=True)
                    Path(self.log_dir, logFile).write_text(str(message), encoding="utf-8")

            class StageAPI:
                @staticmethod
                def build_visualization_plan(*_):
                    return plan

                @staticmethod
                def run_visualization_stage(actual_plan, **adapters):
                    ready_workspace.rename(running_workspace)
                    adapters["application"](str(running_workspace))
                    running_workspace.rename(completed_workspace)
                    return actual_plan.completed_workspace

            class Picker:
                def proc(self):
                    return plan.ready_workspace, plan.output_dir

            namespace = {
                "visualization_stage": StageAPI,
                "setproctitle": mock.Mock(), "os": os,
                "ClassfierOptionParser": lambda argv=None: mock.Mock(),
                "datasetDirOutputDirPickers": lambda **_: Picker(),
                "MPlogger": FileLogger,
                "_start_visualization_server": mock.Mock(),
                "_validate_visualization": mock.Mock(),
                "MPLOGGER": FileLogger(), "stage_done": mock.Mock(), "MES": "hosted",
            }

            def configure_running_logger(running, _plan):
                namespace["MPLOGGER"] = FileLogger(Path(running, "logs"))

            namespace["_run_visualization_application"] = configure_running_logger
            exec(compile(ast.Module(body=[main_node], type_ignores=[]),
                         "Test_result_Vis.py", "exec"), namespace)

            namespace["main"](stage_api=StageAPI)

            self.assertTrue(completed_workspace.exists())
            self.assertFalse(running_workspace.exists())
            self.assertTrue(
                Path(completed_workspace, "logs", "Test_result_Vis.log").exists())

    def test_layout_helpers_are_module_globals_when_canonical_layout_is_evaluated(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        application = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_run_visualization_application")
        canonical_layout = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "serve_layout")
        helper_names = {"Build_Upload_Block", "Build_Finished_Task_Block"}
        helper_calls = [
            node for node in ast.walk(canonical_layout)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in helper_names]
        self.assertEqual({call.func.id for call in helper_calls}, helper_names)

        reduced_layout = ast.FunctionDef(
            name=canonical_layout.name,
            args=canonical_layout.args,
            body=[ast.Return(value=ast.Tuple(elts=helper_calls, ctx=ast.Load()))],
            decorator_list=[],
        )
        relevant_body = [
            node for node in application.body
            if isinstance(node, (ast.Global, ast.ImportFrom))
            and (not isinstance(node, ast.ImportFrom)
                 or node.module == "Test_result_Vis_layout")
        ]
        relevant_body.extend(
            node for node in application.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Name)
            and node.value.id == canonical_layout.name)
        reduced_application = ast.FunctionDef(
            name=application.name,
            args=application.args,
            body=relevant_body,
            decorator_list=[],
        )

        calls = []
        fake_layout_module = types.ModuleType("Test_result_Vis_layout")
        for helper_name in helper_names:
            setattr(
                fake_layout_module,
                helper_name,
                lambda *args, _name=helper_name, **kwargs:
                    calls.append((_name, args, kwargs)) or _name,
            )

        class EvaluatingApp:
            @property
            def layout(self):
                return self._layout

            @layout.setter
            def layout(self, value):
                self._layout = value()

        namespace = {
            "app": EvaluatingApp(),
            "date_session_id": "session",
            "UploadedFilename": "upload.txt",
            "VisSelfFinishedState": False,
            "args": Namespace(TRVPort=8059),
            "datasetDir_VisSelf": "dataset",
        }
        harness = ast.fix_missing_locations(ast.Module(
            body=[reduced_layout, reduced_application], type_ignores=[]))
        exec(compile(harness, "Test_result_Vis.py", "exec"), namespace)
        with mock.patch.dict(sys.modules, {
                "Test_result_Vis_layout": fake_layout_module}):
            namespace[application.name]("workspace", mock.Mock())

        self.assertTrue(helper_names.issubset(namespace))
        self.assertEqual({name for name, _, _ in calls}, helper_names)

    def _plan(self, hosted=False):
        return self.stage.VisualizationPlan(
            ready_workspace="x_rdy_for_TestResultVis", output_dir="model",
            hosted=hosted, host="0.0.0.0", port=9000,
            weitech_separate_work_pool=False, weitech_input_path="in",
            weitech_output_path="out", ssl_context="adhoc")

    def _execute_canonical_summary_slice(self, stage_api, invoke, artifacts):
        source = Path("BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        application = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_run_visualization_application")
        summary_if = next(
            node for node in ast.walk(application)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Attribute)
            and node.test.left.attr == "TextSummarization")
        start = next(
            index for index, node in enumerate(summary_if.body)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "CMD"
                    for target in node.targets))
        finish = next(
            index for index, node in enumerate(summary_if.body[start:], start)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "MES"
                    for target in node.targets))
        summary_slice = summary_if.body[start:finish + 1]
        namespace = {
            "visualization_stage": stage_api,
            "os": mock.Mock(system=invoke),
            "SumPath": "summary-source",
            "SumOptPath": "summary-output",
            "OSWALK": artifacts,
        }
        exec(compile(ast.Module(body=summary_slice, type_ignores=[]),
                     "Test_result_Vis.py", "exec"), namespace)


if __name__ == "__main__":
    unittest.main()
