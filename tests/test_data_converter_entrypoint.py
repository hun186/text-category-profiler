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


if __name__ == "__main__":
    unittest.main()
