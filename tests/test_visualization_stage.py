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

    def test_tulip_windows_dll_preflight_rejects_dot_without_mutating_path(self):
        original = r"C:\Windows\system32;.;D:\AIProjects\bin"
        with mock.patch.dict(os.environ, {"PATH": original}):
            with self.assertRaisesRegex(
                RuntimeError, "TULIP_WINDOWS_PATH_RELATIVE"
            ) as caught:
                self.stage.preflight_tulip_windows_path(windows=True)
            self.assertIn("'.'", str(caught.exception))
            self.assertIn('[WinError 87]', str(caught.exception))
            self.assertIn('set "PATH=%PATH:;.=%"', str(caught.exception))
            self.assertEqual(os.environ["PATH"], original)

    def test_windows_stage4_dot_sanitizer_is_narrow_and_idempotent(self):
        # Only exact relative '.' segments are safe to drop automatically.
        original = r'C:\\Windows\\system32;.;". ";.\\plugins;..\\bin;D:\\Anaconda\\Scripts;.'
        env = {"PATH": original}
        count = self.stage.sanitize_tulip_windows_dot_path(
            environ=env, windows=True,
        )
        self.assertEqual(count, 3)
        self.assertEqual(
            env["PATH"],
            r'C:\\Windows\\system32;.\\plugins;..\\bin;D:\\Anaconda\\Scripts',
        )
        self.assertEqual(
            self.stage.sanitize_tulip_windows_dot_path(
                environ=env, windows=True,
            ), 0,
        )
        with self.assertRaisesRegex(RuntimeError, "TULIP_WINDOWS_PATH_RELATIVE"):
            self.stage.preflight_tulip_windows_path(
                path=env["PATH"], windows=True,
            )

    def test_windows_stage4_dot_sanitizer_has_no_linux_side_effect(self):
        original = r'C:\\Windows;.;.\\tools'
        env = {"PATH": original}
        self.assertEqual(
            self.stage.sanitize_tulip_windows_dot_path(
                environ=env, windows=False,
            ), 0,
        )
        self.assertEqual(env["PATH"], original)

    def test_windows_stage4_dot_sanitizer_never_changes_parent_shell(self):
        original = r'C:\\Windows;.;D:\\Anaconda'
        env = {"PATH": original}
        with mock.patch.dict(os.environ, {"PATH": "PARENT_SHELL_SENTINEL"}):
            self.assertEqual(
                self.stage.sanitize_tulip_windows_dot_path(
                    environ=env, windows=True,
                ), 1,
            )
            self.assertEqual(os.environ["PATH"], "PARENT_SHELL_SENTINEL")
            self.assertEqual(env["PATH"], r'C:\\Windows;D:\\Anaconda')
            self.assertIsNone(
                self.stage.preflight_tulip_windows_path(
                    path=env["PATH"], windows=True,
                )
            )

    def test_tulip_windows_preflight_handles_other_relative_and_absolute_paths(self):
        with self.assertRaisesRegex(
            RuntimeError, r"TULIP_WINDOWS_PATH_RELATIVE.*relative",
        ) as caught:
            self.stage.preflight_tulip_windows_path(
                path=r"C:\Windows\System32;.\\plugins;..\\bin", windows=True,
            )
        self.assertIn("plugins", str(caught.exception))
        self.assertIn("bin", str(caught.exception))
        self.assertIsNone(self.stage.preflight_tulip_windows_path(
            path=r"C:\Windows\system32;D:\ProgramData\anaconda3\\Library\\bin",
            windows=True,
        ))

    def test_tulip_windows_preflight_is_noop_on_other_platforms(self):
        self.assertIsNone(self.stage.preflight_tulip_windows_path(
            path=".;relative;more", windows=False,
        ))

    def test_full_stage4_preflights_before_workpool_and_lazily_imports_tulip(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(
            encoding="utf-8",
        )
        tree = ast.parse(source)
        self.assertFalse(any(
            isinstance(node, ast.ImportFrom)
            and node.module == "text_category_profiler.visualization.tulip_graph_builder"
            for node in tree.body
        ))
        preflight_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "preflight_tulip_windows_path"
        ]
        self.assertGreaterEqual(len(preflight_calls), 2)
        # Direct full Stage 4 sanitizes ONLY dot entries, then preflights,
        # both before heavy imports and any WorkPool lifecycle.
        self.assertLess(
            source.index("visualization_stage.sanitize_tulip_windows_dot_path()"),
            source.index("visualization_stage.preflight_tulip_windows_path()"),
        )
        self.assertLess(
            source.index("visualization_stage.preflight_tulip_windows_path()"),
            source.index("import numpy as np"),
        )
        self.assertLess(
            source.index("visualization_stage.preflight_tulip_windows_path()"),
            source.index("def main(argv=None, stage_api=visualization_stage):"),
        )
        builder = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "VisDatatableDFBuilder"
        )
        run = next(
            node for node in builder.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        self.assertTrue(any(
            isinstance(node, ast.ImportFrom)
            and node.module == "text_category_profiler.visualization.tulip_graph_builder"
            for node in ast.walk(run)
        ))
        # A dependency may add dot to PATH after initial import; re-sanitize
        # immediately before the deferred Tulip graph load as well.
        nested = list(ast.walk(run))
        sanitize_line = next(
            n.lineno for n in nested
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "sanitize_tulip_windows_dot_path"
        )
        preflight_line = next(
            n.lineno for n in nested
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "preflight_tulip_windows_path"
        )
        import_line = next(
            n.lineno for n in nested
            if isinstance(n, ast.ImportFrom)
            and n.module == "text_category_profiler.visualization.tulip_graph_builder"
        )
        self.assertLess(sanitize_line, preflight_line)
        self.assertLess(preflight_line, import_line)

    def test_dash_import_uses_dependency_light_importer(self):
        fake_dash = object()
        importer = mock.Mock(return_value=fake_dash)
        self.assertIs(self.stage.import_dash_runtime(importer), fake_dash)
        importer.assert_called_once_with("dash")

    def test_dash_import_explains_legacy_comm_failure(self):
        def legacy_importer(name):
            self.assertEqual(name, "dash")
            raise NotImplementedError("Cannot ")

        with self.assertRaisesRegex(
            RuntimeError, r'comm>=0\.2\.3',
        ) as failure:
            self.stage.import_dash_runtime(legacy_importer)
        self.assertIsInstance(failure.exception.__cause__, NotImplementedError)
        self.assertIn("TCFMain.py", str(failure.exception))

    def test_dash_import_does_not_mask_unrelated_not_implemented(self):
        original = NotImplementedError("real application failure")
        def broken_importer(_):
            raise original

        with self.assertRaises(NotImplementedError) as failure:
            self.stage.import_dash_runtime(broken_importer)
        self.assertIs(failure.exception, original)

    def test_dash_script_uses_scoped_import_diagnostic(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(
            encoding="utf-8",
        )
        root = ast.parse(source)
        self.assertTrue(any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "dash"
                for target in node.targets
            )
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "visualization_stage"
            and node.value.func.attr == "import_dash_runtime"
            for node in root.body
        ))
        self.assertFalse(any(
            isinstance(node, ast.Import)
            and any(alias.name == "dash" for alias in node.names)
            for node in root.body
        ))

    def test_recreated_datatable_empty_derived_filter_is_not_user_input(self):
        notice = [{"prop_id": "VisDatatable.derived_filter_query_structure",
                   "value": None}]
        ignore = self.stage.is_spurious_datatable_filter_notification
        params = dict(filter_query="", sort_by=[], derived_query_structure=None,
                      previous_derived_query_structure=None)
        self.assertTrue(ignore(notice, **params))
        self.assertFalse(ignore(
            [{"prop_id": "VisDatatable.sort_by", "value": []}], **params))
        self.assertFalse(ignore(
            notice + [{"prop_id": "VisDatatable.sort_by", "value": []}],
            **params))
        self.assertFalse(ignore(notice, **dict(params, filter_query="{Rating} > 0")))
        self.assertFalse(ignore(notice, **dict(params, sort_by=[
            {"column_id": "Rating", "direction": "desc"}])))
        self.assertFalse(ignore(notice, **dict(
            params, previous_derived_query_structure={"operator": "="})))
        self.assertFalse(ignore(notice, **dict(
            params, derived_query_structure={"operator": "="})))

    def test_filter_request_revision_updates_even_with_sqlite_json_sentinel(self):
        make = self.stage.datatable_filter_state
        a = make("{InfoScoreMean} i< 10", [], {"op": "<"})
        b = make("{InfoScoreMean} i< 10", [], {"op": "<"}, a)
        self.assertEqual(a["revision"], 1)
        self.assertEqual(b["revision"], 2)
        self.assertEqual(a["filter_query"], "{InfoScoreMean} i< 10")
        self.assertTrue(self.stage.is_redundant_table_filter_event(
            [{"prop_id": "VisDatatable.derived_filter_query_structure", "value": None}],
            filter_query=a["filter_query"], sort_by=[],
            derived_query_structure=a["derived_filter_query_structure"],
            previously_applied=a,
        ))
        self.assertFalse(self.stage.is_redundant_table_filter_event(
            [{"prop_id": "VisDatatable.filter_query", "value": "{InfoScoreMean} i< 11"}],
            filter_query="{InfoScoreMean} i< 11", sort_by=[],
            derived_query_structure=a["derived_filter_query_structure"],
            previously_applied=a,
        ))
        self.assertFalse(self.stage.is_redundant_table_filter_event(
            [{"prop_id": "KeyWordTable.selected_rows", "value": [1]}],
            filter_query=a["filter_query"], sort_by=[],
            derived_query_structure=a["derived_filter_query_structure"],
            previously_applied=a,
        ))
        self.assertFalse(self.stage.is_redundant_table_filter_event(
            [{"prop_id": "VisDatatable.sort_by", "value": [{"column_id": "File",
                                                               "direction": "desc"}]}],
            filter_query=a["filter_query"],
            sort_by=[{"column_id": "File", "direction": "desc"}],
            derived_query_structure=a["derived_filter_query_structure"],
            previously_applied=a,
        ))

    def test_table_page_remount_only_skips_unchanged_page_not_real_user_page(self):
        guard = self.stage.is_redundant_table_page_event
        event = [{"prop_id": "VisDatatable.page_current", "value": 0}]
        self.assertTrue(guard(event, page_current=0,
                              last_rendered={"page_current": 0}))
        self.assertFalse(guard(event, page_current=1,
                               last_rendered={"page_current": 0}))
        self.assertFalse(guard(
            [{"prop_id": "applied-table-filter.data", "value": {"revision": 3}}],
            page_current=0, last_rendered={"page_current": 0},
        ))
        self.assertFalse(guard(event, page_current=0, last_rendered=None))

    def test_real_nonempty_filter_remount_skips_logging_and_reexport(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        callback = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "FilteredDF_update"
        )
        callback.decorator_list = []

        class PreventUpdate(Exception):
            pass

        unexpected = mock.Mock(side_effect=AssertionError(
            "Remount of same nonempty filter must never hit IO"
        ))
        parsed = {"subType": "<", "type": "relational-operator"}
        import json
        ns = {
            "dash": types.SimpleNamespace(callback_context=types.SimpleNamespace(
                triggered=[{"prop_id": "VisDatatable.derived_filter_query_structure",
                            "value": None}])),
            "json": json, "visualization_stage": self.stage,
            "PreventUpdate": PreventUpdate,
            "section": unexpected,
            "dfOutputer": unexpected,
            "MPLOGGER": types.SimpleNamespace(logW=unexpected),
        }
        exec(compile(ast.Module(body=[callback], type_ignores=[]),
                     "Test_result_Vis.py", "exec"), ns)
        actual = ns["FilteredDF_update"]
        kwargs = {
            arg: None for arg in
            actual.__code__.co_varnames[:actual.__code__.co_argcount]
        }
        kwargs.update(
            filter_query="{InfoScoreMean} i< 10",
            sort_by=[],
            derived_query_structure=None,
            Old_derived_filter_query_structure_json=json.dumps(parsed),
            last_applied_table_filter=self.stage.datatable_filter_state(
                "{InfoScoreMean} i< 10", [], parsed,
            ),
        )
        with self.assertRaises(PreventUpdate):
            actual(**kwargs)
        unexpected.assert_not_called()

    def test_table_page_self_remount_skips_rebuilding_before_any_io(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        node = next(x for x in ast.parse(source).body
                    if isinstance(x, ast.FunctionDef) and x.name == "table_update")
        node.decorator_list = []

        class PreventUpdate(Exception):
            pass

        ns = {
            "visualization_stage": self.stage,
            "dash": types.SimpleNamespace(callback_context=types.SimpleNamespace(
                triggered=[{"prop_id": "VisDatatable.page_current", "value": 0}])),
            "PreventUpdate": PreventUpdate,
            "ShowElapsedTime": mock.Mock(side_effect=AssertionError(
                "Remount must not re-read database or build page"
            )),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]),
                     "Test_result_Vis.py", "exec"), ns)
        fn = ns["table_update"]
        kwargs = {arg: None for arg in
                  fn.__code__.co_varnames[:fn.__code__.co_argcount]}
        kwargs.update(page_current=0,
                      last_rendered_table_state={"page_current": 0})
        with self.assertRaises(PreventUpdate):
            fn(**kwargs)
        ns["ShowElapsedTime"].assert_not_called()

    def test_callback_graph_has_revision_only_chart_and_page_guard(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        def registration(function):
            start = source.index("def " + function + "(")
            before = source[:start]
            return before[before.rfind("\\nargs = []"):]
        filtering = registration("FilteredDF_update")
        charts = registration("ChunkDF_update")
        table = registration("table_update")
        self.assertIn('Output("applied-table-filter", "data")', filtering)
        self.assertIn("State('applied-table-filter', 'data')", filtering)
        self.assertIn("Input('applied-table-filter', 'data')", charts)
        self.assertIn("Input('applied-table-filter', 'data')", table)
        self.assertNotIn("Output('VisDatatable', \"page_current\")", charts)
        self.assertIn("Input('VisDatatable', \"page_current\")", table)
        self.assertIn("Output('last-rendered-table-state', 'data')", table)
        self.assertIn("State('VisDatatable', \"sort_by\")", table)
        self.assertIn("dcc.Store(id='applied-table-filter', data={})", source)
        self.assertIn("dcc.Store(id='last-rendered-table-state', data=None)", source)
        chunk_body = source[source.index("def ChunkDF_update("):
                            source.index("def table_update(")]
        self.assertIn("return [PredSum_children, TwinsCard_children]", chunk_body)
        table_body = source[source.index("def table_update("):
                            source.index("def func1(")]
        self.assertIn("page_current = min(max(page_current or 0, 0), page_max)",
                      table_body)
        self.assertIn("sort_by=sort_by", table_body)

    def test_idle_remount_does_not_log_write_or_reprocess_filtered_df(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        callback = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "FilteredDF_update")
        # Execute the original function body, not its Dash registration
        # decorator: the regression harness intentionally has no app/server.
        callback.decorator_list = []

        class PreventUpdate(Exception):
            pass

        logging = mock.Mock(side_effect=AssertionError(
            "Synthetic table remount must not enter expensive callback"))
        ns = {
            "dash": types.SimpleNamespace(callback_context=types.SimpleNamespace(
                triggered=[{"prop_id": "VisDatatable.derived_filter_query_structure",
                            "value": None}])),
            "json": __import__("json"),
            "visualization_stage": self.stage,
            "PreventUpdate": PreventUpdate,
            "section": logging,
            "dfOutputer": logging,
            "MPLOGGER": types.SimpleNamespace(logW=logging),
        }
        exec(compile(ast.Module(body=[callback], type_ignores=[]),
                     "Test_result_Vis.py", "exec"), ns)
        actual = ns["FilteredDF_update"]
        kwargs = {name: None for name in
                  actual.__code__.co_varnames[:actual.__code__.co_argcount]}
        kwargs.update(
            Old_derived_filter_query_structure_json="null",
            filter_query="", sort_by=[], derived_query_structure=None)
        with self.assertRaises(PreventUpdate):
            actual(**kwargs)
        logging.assert_not_called()

    def test_results_table_does_not_listen_to_its_own_data(self):
        source = Path("BertScript/Test_result_Vis.py").read_text(
            encoding="utf-8")
        prefix = source[:source.index("def table_update(")]
        # The dynamic args list is immediately above the callback function.
        registration = prefix[prefix.rfind("\nargs = []"):]
        self.assertIn("State('VisDatatable', 'data')", registration)
        self.assertNotIn("Input('VisDatatable', 'data')", registration)
        self.assertIn("Input('VisDatatable', \"page_current\")", registration)

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
