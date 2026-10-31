"""Version-selected canonical Pool.istarmap providers, no live workers."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MP = ROOT / "text_category_profiler" / "concurrency" / "MP_utils.py"
OLD = ROOT / "text_category_profiler" / "concurrency" / "istarmap.py"
NEW = ROOT / "text_category_profiler" / "concurrency" / "istarmap2.py"

def tree(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

def gate():
    cases = [n for n in tree(MP).body if isinstance(n, ast.If)
             and isinstance(n.test, ast.Call) and isinstance(n.test.func, ast.Name)
             and n.test.func.id == "IsVersionValid"]
    if len(cases) != 1:
        raise AssertionError("Expected unique Python version selector")
    return cases[0]

class IstarmapProviderTests(unittest.TestCase):
    def test_version_branches_select_canonical_modules_and_no_catch_all(self):
        node = gate()
        for statements, target in (
            (node.body, "text_category_profiler.concurrency.istarmap2"),
            (node.orelse, "text_category_profiler.concurrency.istarmap"),
        ):
            with self.subTest(provider=target):
                self.assertFalse(any(isinstance(n, ast.Try)
                                     for stmt in statements for n in ast.walk(stmt)))
                imports = [a for stmt in statements if isinstance(stmt, ast.Import)
                           for a in stmt.names]
                self.assertEqual([(a.name, a.asname) for a in imports],
                                 [(target, "istarmap")])
        self.assertFalse(any(
            alias.name in {"istarmap", "istarmap2"}
            for n in ast.walk(tree(MP)) if isinstance(n, ast.Import)
            for alias in n.names
        ))

    def test_both_patch_providers_keep_signature_and_fake_pool_side_effect(self):
        for path in (OLD, NEW):
            with self.subTest(provider=path.name):
                body = tree(path).body
                methods = [n for n in body if isinstance(n, ast.FunctionDef)
                           and n.name == "istarmap"]
                assigns = [n for n in body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Attribute) and t.attr == "istarmap"
                                   and isinstance(t.value, ast.Attribute)
                                   and t.value.attr == "Pool" for t in n.targets)]
                self.assertEqual((len(methods), len(assigns)), (1, 1))
                self.assertEqual([a.arg for a in methods[0].args.args],
                                 ["self", "func", "iterable", "chunksize"])
                self.assertEqual(methods[0].args.defaults[0].value, 1)
                fake = type("FakePool", (), {})
                scope = {"mpp": SimpleNamespace(Pool=fake)}
                exec(compile(ast.Module(body=methods + assigns, type_ignores=[]),
                             str(path), "exec"), scope)
                self.assertIs(fake.istarmap, scope["istarmap"])

    def test_canonical_import_failure_propagates(self):
        stmt = next(n for n in gate().body if isinstance(n, ast.Import))
        calls = []
        def fail(name, *args, **kwargs):
            calls.append(name)
            raise RuntimeError("canonical provider failed")
        with patch("builtins.__import__", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "canonical provider failed"):
                exec(compile(ast.Module(body=[stmt], type_ignores=[]),
                             str(MP), "exec"), {})
        self.assertEqual(calls, ["text_category_profiler.concurrency.istarmap2"])

if __name__ == "__main__":
    unittest.main()
