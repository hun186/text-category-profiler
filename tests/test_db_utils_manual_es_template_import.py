"""Dependency-light regression for DB_utils' manual Elasticsearch template CLI.

The real DB_utils module has heavy optional import/runtime dependencies. These
tests compile only its __main__ AST block and inject inert collaborators:
no actual ES/SQL/file walking or other I/O can run.
"""
import ast
import importlib
from pathlib import Path
import socket
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "text_category_profiler/data/DB_utils.py"
CANONICAL = "text_category_profiler.integrations.es_job_template"


def manual_block():
    parsed = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    direct_blocks = [
        node for node in parsed.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Constant)
        and node.test.comparators[0].value == "__main__"
    ]
    if len(direct_blocks) != 1:
        raise AssertionError("Expected exactly one DB_utils manual entrypoint")
    return direct_blocks[0]


class DBUtilsManualESTemplateImportTests(unittest.TestCase):
    def test_manual_entrypoint_imports_only_canonical_es_template(self):
        entry = manual_block()
        imports = [n for n in ast.walk(entry) if isinstance(n, ast.ImportFrom)]
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0].module, CANONICAL)
        self.assertEqual([x.name for x in imports[0].names], ["esJobTemplate"])
        self.assertEqual(imports[0].level, 0)

    def test_manual_entrypoint_builds_preview_and_sqlconcat_without_io(self):
        # All potentially side-effectful collaborators in the __main__
        # block are replaced before executing its AST; the imported template
        # is the existing inert environment-backed dictionary.
        jobs = [{"job_id": "stub-a"}, {"job_id": "stub-b"}, {"job_id": "stub-c"}]
        calls = []
        builder = mock.Mock(side_effect=lambda *args, **kwargs: (
            calls.append(("builder", kwargs.copy())) or jobs
        ))
        redactor = mock.Mock(side_effect=lambda job: {"safe": job["job_id"]})
        display = mock.Mock(side_effect=lambda result: calls.append(("display", result)))
        walk = mock.Mock(side_effect=lambda root: (
            calls.append(("walk", root)) or ["sentinel-sql-file"]
        ))
        concat = mock.Mock(side_effect=lambda **kw: calls.append(("concat", kw)))
        namespace = {
            "__name__": "__main__",
            "BuildESJobList": builder,
            "_redact_es_job_for_logging": redactor,
            "DictIndentPrint": display,
            "OSWALK": walk,
            "SQLConcat": concat,
        }
        isolated = ast.Module(body=[manual_block()], type_ignores=[])
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network disabled")):
            exec(compile(isolated, str(SOURCE), "exec"), namespace)

        template = importlib.import_module(CANONICAL).esJobTemplate
        self.assertIs(builder.call_args.args[0], template)
        self.assertEqual(builder.call_args.kwargs, {
            "startDay": "20230903",
            "endDay": "20240218",
        })
        self.assertEqual(redactor.call_args_list, [
            mock.call(jobs[0]), mock.call(jobs[1]),
        ])
        self.assertEqual(display.call_args_list, [
            mock.call({"safe": "stub-a"}), mock.call({"safe": "stub-b"}),
        ])
        walk.assert_called_once_with("SQLConcatenate")
        concat.assert_called_once_with(sql3FileList=["sentinel-sql-file"])
        self.assertEqual(calls, [
            ("builder", {"startDay": "20230903", "endDay": "20240218"}),
            ("display", {"safe": "stub-a"}),
            ("display", {"safe": "stub-b"}),
            ("walk", "SQLConcatenate"),
            ("concat", {"sql3FileList": ["sentinel-sql-file"]}),
        ])

    def test_regular_module_import_is_not_required_for_ast_characterization(self):
        # This regression does not import DB_utils or its optional mongo,
        # Elasticsearch, pandas, or classifier runtime dependencies.
        source = SOURCE.read_text(encoding="utf-8")
        parsed = ast.parse(source)
        self.assertIn("BuildESJobList", [n.name for n in parsed.body if isinstance(n, ast.FunctionDef)])
        self.assertEqual(manual_block().lineno > 1, True)


if __name__ == "__main__":
    unittest.main()
