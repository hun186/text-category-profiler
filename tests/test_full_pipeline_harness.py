import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.smoke.full_pipeline_harness import (
    RealRuntimeConfigurationError, SmokeConfig, SmokeResult,
    _discover_fixed_test_dirs, _discover_model_dir,
    build_isolated_environment, build_root_command,
    cleanup_runtime_root, config_from_real_runtime_environment, create_model_facade,
    create_python_wrapper, format_failure, run_full_pipeline,
    snapshot_directories, snapshot_regular_files,
)


class FullPipelineHarnessTests(unittest.TestCase):
    def test_build_root_command_is_explicit_and_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = SmokeConfig(
                repository_root=root,
                fixed_test_dir=root / "Fixed Test",
                topic_tree_dir=root / "taxonomy",
                topic_tree_files="TopicTree_smoke.csv",
                model_dir=root / "model",
            )
            workpool = root / "WorkPool"

            command = build_root_command(config, workpool)

            self.assertEqual(command[:2], [sys.executable, str((root / "TCFMain.py").resolve())])
            expected_pairs = {
                "-p": "18059", "-ts": "y", "-TRVHost": "False",
                "-WPRoot": str(workpool), "-FTPath": str(config.fixed_test_dir),
                "-TopicTreeDir": str(config.topic_tree_dir),
                "-TopicTreeFiles": "TopicTree_smoke.csv", "-mdlDir": str(config.model_dir),
                "-mdlType": "PytorchXLM", "-nProc": "1", "-nProcSPC": "1",
                "-RMBertData": "False", "-exectime": "20990101000000",
            }
            self.assertEqual(dict(zip(command[2::2], command[3::2])), expected_pairs)

    def make_config(self, root, **changes):
        values = dict(repository_root=root, fixed_test_dir=root / "fixed",
                      topic_tree_dir=root / "trees", topic_tree_files="trees.csv",
                      model_dir=root / "model")
        values.update(changes)
        return SmokeConfig(**values)

    def test_environment_is_confined_and_path_interception_is_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "marker.jsonl"
            config = self.make_config(root)
            wrapper = create_python_wrapper(config, root)
            environment = build_isolated_environment(config, root, marker)
            for name in ("TEMP", "TMP", "TMPDIR", "HOME", "HF_HOME", "TRANSFORMERS_CACHE"):
                self.assertTrue(Path(environment[name]).is_relative_to(root), name)
            self.assertEqual(Path(environment["PATH"].split(os.pathsep)[0]), wrapper.parent)
            plain = build_isolated_environment(self.make_config(root, intercept_classifier=False), root, None)
            self.assertNotEqual(Path(plain["PATH"].split(os.pathsep)[0]), wrapper.parent)

    def test_windows_wrapper_uses_cmd_name_for_pathext_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.make_config(root)
            with mock.patch("tests.smoke.full_pipeline_harness.os.name", "nt"):
                wrapper = create_python_wrapper(config, root)
            self.assertEqual(wrapper.name, "python.cmd")

    def test_whitespace_temporary_parent_uses_repository_fallback_that_can_be_cleaned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TCFMain.py").write_text("print('done')\n", encoding="utf-8")
            with mock.patch("tests.smoke.full_pipeline_harness.tempfile.gettempdir",
                            return_value=str(root / "parent with spaces")):
                result = run_full_pipeline(self.make_config(root, intercept_classifier=False))
            self.assertEqual(result.returncode, 0)
            self.assertTrue(result.runtime_root.is_relative_to(root / ".smoke-runtime"))
            cleanup_runtime_root(result.runtime_root, root)
            self.assertFalse(result.runtime_root.exists())
            self.assertFalse((root / ".smoke-runtime").exists())

    def test_cleanup_runtime_root_preserves_nonempty_fallback_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / ".smoke-runtime" / "owned-runtime"
            runtime_root.mkdir(parents=True)
            unrelated = root / ".smoke-runtime" / "unrelated"
            unrelated.write_text("keep", encoding="utf-8")

            cleanup_runtime_root(runtime_root, root)

            self.assertFalse(runtime_root.exists())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")

    def test_intercepted_run_uses_writable_copy_without_mutating_source_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_model = root / "model"
            source_model.mkdir()
            label_list = source_model / "TopicAnalysis_LabelList.txt"
            label_list.write_text("Aloha\n", encoding="utf-8")
            source_before = snapshot_regular_files(source_model)
            (root / "TCFMain.py").write_text(
                "import pathlib, sys\n"
                "model = pathlib.Path(sys.argv[sys.argv.index('-mdlDir') + 1])\n"
                "(model / 'UsingMark.txt').write_text('runtime', encoding='utf-8')\n",
                encoding="utf-8",
            )

            result = run_full_pipeline(self.make_config(root, model_dir=source_model))
            try:
                effective_model = Path(
                    result.command[result.command.index("-mdlDir") + 1]
                )
                self.assertFalse((source_model / "UsingMark.txt").exists())
                self.assertEqual(snapshot_regular_files(source_model), source_before)
                self.assertTrue(effective_model.is_relative_to(result.runtime_root))
                self.assertEqual(
                    (effective_model / "TopicAnalysis_LabelList.txt").read_text(
                        encoding="utf-8"
                    ),
                    "Aloha\n",
                )
            finally:
                cleanup_runtime_root(result.runtime_root, root)

    def _dispatch(self, root, child, classifier, *arguments):
        environment = os.environ.copy()
        environment.update(TCP_SMOKE_REAL_PYTHON=sys.executable,
                           TCP_SMOKE_CLASSIFIER_SCRIPT=str(classifier))
        return subprocess.run([sys.executable, str(Path(__file__).parent / "smoke/python_dispatch.py"),
                               str(child), *arguments], env=environment,
                              capture_output=True, text=True, check=False)

    def test_dispatcher_forwards_normal_child_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "normal_child.py"
            child.write_text("import json,sys; print(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
            result = self._dispatch(root, child, root / "classifier.py", "--x", "1")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), ["--x", "1"])

    def test_dispatcher_redirects_only_production_classifier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "BertScript" / "TextClassification_transformers.py"
            target.parent.mkdir()
            target.write_text("raise AssertionError('not redirected')\n", encoding="utf-8")
            classifier = root / "classifier.py"
            classifier.write_text("import sys; print('shim', *sys.argv[1:])\n", encoding="utf-8")
            result = self._dispatch(root, target, classifier, "--value")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "shim --value")

    def test_dispatcher_returns_selected_child_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child.py"
            child.write_text("raise SystemExit(23)\n", encoding="utf-8")
            result = self._dispatch(root, child, root / "classifier.py")
            self.assertEqual(result.returncode, 23)

    @unittest.skipIf(os.name == "nt", "POSIX process liveness assertion")
    def test_timeout_kills_descendants_and_formats_bounded_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TCFMain.py").write_text(
                "import subprocess,sys,time\n"
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
                "open(sys.argv[sys.argv.index('-WPRoot')+1]+'/pid','w').write(str(p.pid))\n"
                "print('out-line', flush=True)\nprint('err-line', file=sys.stderr, flush=True)\n"
                "time.sleep(60)\n", encoding="utf-8")
            result = run_full_pipeline(self.make_config(root, timeout_seconds=0.2,
                                                        intercept_classifier=False))
            self.addCleanup(cleanup_runtime_root, result.runtime_root, root)
            self.assertTrue(result.timed_out)
            pid = int((result.workpool_root / "pid").read_text())
            process_status = Path(f"/proc/{pid}/status")
            if process_status.exists():
                self.assertIn("State:\tZ", process_status.read_text())
            diagnostic = format_failure(result, tail_lines=1)
            for value in ("Command:", "timed_out=True", "out-line", "err-line",
                          str(result.workpool_root), "Workspaces:"):
                self.assertIn(value, diagnostic)

    def test_model_facade_copies_metadata_and_links_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            checkpoint = source / "checkpoint-10"
            checkpoint.mkdir(parents=True)
            (source / "TopicAnalysis_LabelList.txt").write_text("Aloha\n", encoding="utf-8")
            (checkpoint / "config.json").write_text("{}", encoding="utf-8")
            (checkpoint / "model.safetensors").write_bytes(b"weights")
            facade = create_model_facade(source, root / "runtime")
            self.assertEqual((facade / "TopicAnalysis_LabelList.txt").read_text(), "Aloha\n")
            self.assertTrue((facade / "checkpoint-10").is_dir())
            if os.name != "nt":
                self.assertTrue((facade / "checkpoint-10").is_symlink())
            (facade / "UsingMark.txt").write_text("local", encoding="utf-8")
            self.assertFalse((source / "UsingMark.txt").exists())

    def test_real_runtime_configuration_names_missing_variable_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, fixed = root / "model", root / "fixed"
            model.mkdir()
            fixed.mkdir()
            with mock.patch(
                "tests.smoke.full_pipeline_harness._discover_model_dir",
                return_value=model,
            ) as model_resolver, mock.patch(
                "tests.smoke.full_pipeline_harness._discover_fixed_test_dirs",
                return_value=(fixed,),
            ) as fixed_resolver, mock.patch("subprocess.Popen") as launch:
                config = config_from_real_runtime_environment(
                    root, {"TCP_RUN_REAL_PIPELINE_SMOKE": "1"}
                )
            launch.assert_not_called()
            model_resolver.assert_called_once_with(root.resolve(), "PytorchXLM")
            fixed_resolver.assert_called_once_with(root.resolve(), 8050)
            self.assertEqual(config.model_dir, model.resolve())
            self.assertEqual(config.fixed_test_dirs, (fixed.resolve(),))
            self.assertIsNone(config.fixed_test_dir)
            self.assertIsNone(config.topic_tree_dir)
            self.assertIsNone(config.topic_tree_files)
            self.assertEqual(config.port, 8050)
            self.assertFalse(config.intercept_classifier)

    def test_real_runtime_configuration_validates_paths_and_disables_interception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, fixed, trees = root / "model", root / "fixed", root / "trees"
            for path in (model, fixed, trees):
                path.mkdir()
            (trees / "TopicTree.csv").write_text("tree", encoding="utf-8")
            config = config_from_real_runtime_environment(root, {
                "TCP_REAL_MODEL_DIR": str(model),
                "TCP_REAL_FIXED_TEST_DIR": str(fixed),
                "TCP_REAL_TOPIC_TREE_DIR": str(trees),
                "TCP_REAL_TOPIC_TREE_FILES": "TopicTree.csv",
                "TCP_REAL_MODEL_TYPE": "PytorchXLM",
                "TCP_REAL_PIPELINE_TIMEOUT_SECONDS": "37",
            })
            self.assertEqual(config.model_dir, model.resolve())
            self.assertEqual(config.fixed_test_dirs, (fixed.resolve(),))
            self.assertFalse(config.intercept_classifier)
            self.assertEqual(config.timeout_seconds, 37)

    def test_real_runtime_explicit_model_and_fixed_test_bypass_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, fixed = root / "model", root / "fixed"
            model.mkdir()
            fixed.mkdir()
            with mock.patch(
                "tests.smoke.full_pipeline_harness._discover_model_dir"
            ) as model_resolver, mock.patch(
                "tests.smoke.full_pipeline_harness._discover_fixed_test_dirs"
            ) as fixed_resolver:
                config = config_from_real_runtime_environment(root, {
                    "TCP_REAL_MODEL_DIR": str(model),
                    "TCP_REAL_FIXED_TEST_DIR": str(fixed),
                    "TCP_REAL_PORT": "8059",
                    "TCP_REAL_MODEL_TYPE": "PytorchXLM",
                })
            model_resolver.assert_not_called()
            fixed_resolver.assert_not_called()
            self.assertEqual(config.fixed_test_dir, fixed.resolve())
            self.assertEqual(config.fixed_test_dirs, (fixed.resolve(),))
            self.assertEqual(config.port, 8059)

    def test_real_runtime_multiple_discovered_fixed_tests_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            first, second = root / "first", root / "second"
            for path in (model, first, second):
                path.mkdir()
            with mock.patch(
                "tests.smoke.full_pipeline_harness._discover_model_dir",
                return_value=model,
            ), mock.patch(
                "tests.smoke.full_pipeline_harness._discover_fixed_test_dirs",
                return_value=(first, second),
            ):
                config = config_from_real_runtime_environment(root, {})
            self.assertEqual(config.fixed_test_dirs, (first.resolve(), second.resolve()))

    def test_every_resolved_fixed_test_directory_is_snapshotted(self):
        first, second = Path("/fixed/first"), Path("/fixed/second")
        with mock.patch(
            "tests.smoke.full_pipeline_harness.snapshot_regular_files",
            side_effect=(('first-before',), ('second-before',)),
        ) as snapshot:
            result = snapshot_directories((first, second))
        self.assertEqual(result, {
            first: ('first-before',), second: ('second-before',),
        })
        self.assertEqual(snapshot.call_args_list, [mock.call(first), mock.call(second)])

    def test_model_discovery_wraps_production_picker_and_restores_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "BertScript" / "output_model"
            model.mkdir(parents=True)
            args = object()
            picker = mock.Mock()
            picker.return_value.proc.return_value = (None, "BertScript/output_model")
            original_cwd = Path.cwd()
            parser = mock.Mock(return_value=args)
            production_utils = types.ModuleType(
                "text_category_profiler.pipeline.TCF_utils"
            )
            production_utils.ClassfierOptionParser = parser
            production_utils.datasetDirOutputDirPickers = picker
            with mock.patch.dict(sys.modules, {
                "text_category_profiler.pipeline.TCF_utils": production_utils,
            }):
                resolved = _discover_model_dir(root, "PytorchXLM")
            self.assertEqual(Path.cwd(), original_cwd)
            self.assertEqual(resolved, model.resolve())
            parser.assert_called_once_with(["-mdlType", "PytorchXLM"])
            picker.assert_called_once_with(args=args)

    def test_fixed_test_discovery_wraps_production_adapter_with_port(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixed = root / "FixedTest" / "FixedTest_8059" / "Using"
            fixed.mkdir(parents=True)
            original_cwd = Path.cwd()
            with mock.patch(
                "DatasetConverter.adapters.pipeline_source.fixed_test_paths",
                return_value=["FixedTest/FixedTest_8059/Using"],
            ) as resolver:
                resolved = _discover_fixed_test_dirs(root, 8059)
            self.assertEqual(Path.cwd(), original_cwd)
            self.assertEqual(resolved, (fixed.resolve(),))
            self.assertEqual(resolver.call_args.args[0].TRVPort, 8059)

    def test_auto_mode_omits_optional_resource_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = build_root_command(self.make_config(
                root, fixed_test_dir=None, topic_tree_dir=None, topic_tree_files=None,
            ), root / "WorkPool")
            self.assertNotIn("-FTPath", command)
            self.assertNotIn("-TopicTreeDir", command)
            self.assertNotIn("-TopicTreeFiles", command)
            self.assertIn("-mdlDir", command)

    def test_topic_tree_overrides_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, fixed, trees = root / "model", root / "fixed", root / "trees"
            for path in (model, fixed, trees):
                path.mkdir()
            base = {"TCP_REAL_MODEL_DIR": str(model), "TCP_REAL_FIXED_TEST_DIR": str(fixed)}
            files_config = config_from_real_runtime_environment(
                root, {**base, "TCP_REAL_TOPIC_TREE_FILES": "custom.csv"}
            )
            directory_config = config_from_real_runtime_environment(
                root, {**base, "TCP_REAL_TOPIC_TREE_DIR": str(trees)}
            )
            files_command = build_root_command(files_config, root / "wp-files")
            directory_command = build_root_command(directory_config, root / "wp-directory")
            self.assertIn("-TopicTreeFiles", files_command)
            self.assertNotIn("-TopicTreeDir", files_command)
            self.assertIn("-TopicTreeDir", directory_command)
            self.assertNotIn("-TopicTreeFiles", directory_command)

    def test_invalid_real_runtime_overrides_fail_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch("subprocess.Popen") as launch, self.assertRaisesRegex(
                RealRuntimeConfigurationError, "TCP_REAL_MODEL_DIR"
            ):
                config_from_real_runtime_environment(
                    root, {"TCP_REAL_MODEL_DIR": str(root / "missing")}
                )
            launch.assert_not_called()

    def test_invalid_real_runtime_timeout_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model, fixed = root / "model", root / "fixed"
            model.mkdir()
            fixed.mkdir()
            with mock.patch("subprocess.Popen") as launch, self.assertRaisesRegex(
                RealRuntimeConfigurationError,
                "TCP_REAL_PIPELINE_TIMEOUT_SECONDS must be greater than zero",
            ):
                config_from_real_runtime_environment(root, {
                    "TCP_REAL_MODEL_DIR": str(model),
                    "TCP_REAL_FIXED_TEST_DIR": str(fixed),
                    "TCP_REAL_PIPELINE_TIMEOUT_SECONDS": "0",
                })
            launch.assert_not_called()

    def test_regular_file_snapshot_records_relative_size_and_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "nested" / "input.txt"
            artifact.parent.mkdir()
            artifact.write_text("input", encoding="utf-8")
            snapshot = snapshot_regular_files(root)
            self.assertEqual(snapshot[0], (
                Path("nested/input.txt"), 5, artifact.stat().st_mtime_ns,
            ))


if __name__ == "__main__":
    unittest.main()
