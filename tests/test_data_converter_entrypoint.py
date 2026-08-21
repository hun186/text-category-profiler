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
        returns = [
            node.value
            for node in ast.walk(set_arguments)
            if isinstance(node, ast.Return)
        ]
        self.assertTrue(
            any(
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "StageContext"
                for value in returns
            )
        )

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


if __name__ == "__main__":
    unittest.main()
