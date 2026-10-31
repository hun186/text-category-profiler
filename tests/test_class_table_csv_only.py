"""CSV is the only active ClassTable metadata source; reject obsolete imports."""
import ast
from pathlib import Path
import subprocess
import unittest

from BertScript.class_table_metadata import DEFAULT_CSV, load_class_table

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ("BertScript/", "DatasetConverter/", "ClassesTree/",
          "text_category_profiler/", "TCF_Params/", "tests/")


def first_party_sources():
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"], cwd=ROOT,
        capture_output=True, check=True, timeout=30,
    )
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        name = entry.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        if not name.startswith(ACTIVE):
            continue
        if any(part in name.split("/") for part in (
            "TRV_deploy", "Dash-by-Plotly-master", "dash-cytoscape-master",
            "vendor", "experiments", "fixtures", "__pycache__",
        )):
            continue
        if name == "BertScript/ClassTable - 複製.py":
            continue  # historical source snapshot, not a supported import
        path = ROOT / name
        if path.is_file():
            yield path


def obsolete_imports(path):
    parsed = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    hits = []
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            hits.extend(node.lineno for alias in node.names
                        if alias.name in {"ClassTable", "BertScript.ClassTable"})
        elif isinstance(node, ast.ImportFrom):
            if node.module in {"ClassTable", "BertScript.ClassTable"}:
                hits.append(node.lineno)
        elif isinstance(node, ast.Call) and node.args:
            fn = node.func
            literal = node.args[0]
            if (isinstance(literal, ast.Constant)
                    and isinstance(literal.value, str)
                    and literal.value in {"ClassTable", "BertScript.ClassTable"}
                    and ((isinstance(fn, ast.Name) and fn.id == "__import__")
                         or (isinstance(fn, ast.Attribute)
                             and fn.attr in {"import_module", "run_module"}))):
                hits.append(node.lineno)
    return hits


class CSVOnlyClassTableTests(unittest.TestCase):
    def test_no_active_python_class_table_file(self):
        self.assertFalse((ROOT / "BertScript" / "ClassTable.py").exists())
        self.assertTrue(DEFAULT_CSV.is_file())
        self.assertEqual(DEFAULT_CSV, ROOT / "BertScript" / "ClassTable.csv")

    def test_loader_retains_existing_dict_contract(self):
        table = load_class_table()
        self.assertEqual(len(table), 1994)
        self.assertEqual(table["Academia"]["CT"], "學術")
        self.assertEqual(set(table["Academia"]), {"CT", "Explanation", "Notes"})

    def test_no_first_party_imports_of_deleted_module(self):
        violations, scanned = [], 0
        for path in first_party_sources():
            scanned += 1
            for line in obsolete_imports(path):
                violations.append(f"{path.relative_to(ROOT)}:{line}")
        self.assertGreater(scanned, 100)
        self.assertEqual(violations, [], "Retired ClassTable imports: " +
                         ", ".join(violations))


if __name__ == "__main__":
    unittest.main()
