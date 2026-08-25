import ast
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_CONVERTER = REPOSITORY_ROOT / "DatasetConverter/DataConverter.py"


class DataConverterEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))

    def test_module_scope_does_not_change_working_directory(self):
        module_scope_calls = [
            node.value
            for node in self.module.body
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        ]
        self.assertFalse(
            any(
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "os"
                and call.func.attr == "chdir"
                for call in module_scope_calls
            )
        )

    def test_cli_is_exposed_through_main_and_system_exit(self):
        functions = {
            node.name: node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("main", functions)
        self.assertEqual(functions["main"].args.args[0].arg, "argv")

        guard = self.module.body[-1]
        self.assertIsInstance(guard, ast.If)
        self.assertIsInstance(guard.body[0], ast.Raise)
        exit_call = guard.body[0].exc
        self.assertEqual(exit_call.func.id, "SystemExit")
        self.assertEqual(exit_call.args[0].func.id, "main")

    def test_job_generator_does_not_read_module_global_args(self):
        job_generator = next(
            node
            for node in self.module.body
            if isinstance(node, ast.ClassDef)
            and node.name == "DataConvertJobGenerater"
        )
        global_arg_reads = [
            node
            for node in ast.walk(job_generator)
            if isinstance(node, ast.Name)
            and node.id == "args"
            and isinstance(node.ctx, ast.Load)
        ]
        self.assertEqual(global_arg_reads, [])

    def test_bootstrap_state_is_returned_in_a_named_context(self):
        classes = {
            node.name: node
            for node in self.module.body
            if isinstance(node, ast.ClassDef)
        }
        self.assertIn("StageContext", classes)

        functions = {
            node.name: node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef)
        }
        set_arguments = functions["setArguments"]
        global_writes = [
            name
            for node in ast.walk(set_arguments)
            if isinstance(node, ast.Global)
            for name in node.names
        ]
        self.assertEqual(global_writes, [])
        calls = {
            node.func.id
            for node in ast.walk(set_arguments)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertEqual(
            calls,
            {"normalize_stage_plan", "activate_stage_context"},
        )

    def test_normalization_is_separate_from_runtime_activation(self):
        functions = {
            node.name: node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef)
        }
        normalize = functions["normalize_stage_plan"]
        activate = functions["activate_stage_context"]

        normalization_calls = {
            node.func.id
            for node in ast.walk(normalize)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertTrue(
            {"make_directory", "MPlogger", "stage_banner"}.isdisjoint(
                normalization_calls
            )
        )

        activation_calls = {
            node.func.id
            for node in ast.walk(activate)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertTrue(
            {"make_directory", "MPlogger", "stage_banner"}.issubset(
                activation_calls
            )
        )

        main = functions["main"]
        main_calls = [
            node.func.id
            for node in ast.walk(main)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertIn("normalize_stage_plan", main_calls)
        self.assertIn("activate_stage_context", main_calls)
        self.assertLess(
            main_calls.index("normalize_stage_plan"),
            main_calls.index("activate_stage_context"),
        )

        normalization_imports = {
            node.module
            for node in ast.walk(normalize)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("TCF_Params.TCFParameters", normalization_imports)

    def test_main_does_not_use_legacy_stage_globals(self):
        main = next(
            node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        forbidden = {"DCkwargs", "MPLOGGER", "MPLOGGER_TCFMain", "exeTimeDict"}
        referenced = {
            node.id
            for node in ast.walk(main)
            if isinstance(node, ast.Name)
        }
        self.assertTrue(forbidden.isdisjoint(referenced))
        module_assignments = {
            target.id
            for statement in self.module.body
            if isinstance(statement, ast.Assign)
            for target in statement.targets
            if isinstance(target, ast.Name)
        }
        self.assertNotIn("DCkwargs", module_assignments)

    def test_main_gets_split_ratios_from_normalized_converter_config(self):
        main = next(
            node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        referenced = {
            node.id
            for node in ast.walk(main)
            if isinstance(node, ast.Name)
        }
        self.assertNotIn("DatasetRatioDict", referenced)

        split_mapping_calls = [
            node
            for node in ast.walk(main)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "as_legacy_mapping"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "split"
        ]
        self.assertEqual(len(split_mapping_calls), 1)

    def test_main_gets_artifact_paths_from_normalized_output_config(self):
        main = next(
            node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        output_attributes = {
            node.attr
            for node in ast.walk(main)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "output_config"
        }
        self.assertTrue(
            {"output_main", "labels_count_output", "fixed_test_output"}.issubset(
                output_attributes
            )
        )

    def test_main_normalizes_discovered_process_counts_once(self):
        main = next(
            node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        runtime_config_calls = [
            node
            for node in ast.walk(main)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RuntimeConfig"
        ]
        self.assertEqual(len(runtime_config_calls), 1)

        process_names = {
            node.attr
            for node in ast.walk(main)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "runtime_config"
        }
        self.assertEqual(
            process_names,
            {"worker_processes", "large_output_processes"},
        )

    def test_main_uses_normalized_weitech_mode_for_activation(self):
        main = next(
            node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        legacy_mode_reads = {
            node.attr
            for node in ast.walk(main)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "args"
            and node.attr in {"WeiTechworkID", "ExtractionConverterTask"}
        }
        self.assertEqual(legacy_mode_reads, set())

        normalized_mode_reads = {
            node.attr
            for node in ast.walk(main)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "mode_config"
        }
        self.assertTrue(
            {"wei_tech_work_id", "extraction_task", "extraction_enabled"}.issubset(
                normalized_mode_reads
            )
        )

        legacy_workspace_reads = {
            node.attr
            for node in ast.walk(main)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "args"
            and node.attr == "WeiTechWorkPoolPATH"
        }
        self.assertEqual(legacy_workspace_reads, set())

        workspace_reads = {
            node.attr
            for node in ast.walk(main)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "workspace_config"
        }
        self.assertEqual(
            workspace_reads,
            {"work_item_directory", "work_pool_directory"},
        )


if __name__ == "__main__":
    unittest.main()
