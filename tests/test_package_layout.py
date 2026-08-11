import ast
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "text_category_profiler"
DOMAIN_PACKAGES = {
    "concurrency",
    "core",
    "data",
    "integrations",
    "pipeline",
    "text",
    "visualization",
}
MIGRATED_MODULES = {
    "DB_utils",
    "Dash_utils",
    "DataConverter_utils",
    "DataConverter_utils_Parameters",
    "DataVisualization_utils",
    "Email_utils",
    "ES_utils",
    "FTP_utils",
    "Graph_utils",
    "MP_utils",
    "TCF_utils",
    "TextClassfier_utils",
    "TextProcessor_utils",
    "conformer",
    "df_utils",
    "istarmap",
    "istarmap2",
    "json_utils",
    "log_display",
    "model_paths",
    "patch_mp_connection",
    "progress_utils",
    "reusable_components",
    "similarity_utils",
    "torch_compat",
    "utilities",
    "utilities_path",
}


class PackageLayoutTests(unittest.TestCase):
    def test_domain_directories_are_packages(self):
        for package in DOMAIN_PACKAGES:
            self.assertTrue((PACKAGE_ROOT / package / "__init__.py").is_file(), package)

    def test_migrated_modules_are_not_left_at_package_root(self):
        leftovers = {
            path.stem
            for path in PACKAGE_ROOT.glob("*.py")
            if path.stem in MIGRATED_MODULES
        }
        self.assertEqual(leftovers, set())

    def test_application_imports_use_domain_packages(self):
        legacy_prefixes = {f"text_category_profiler.{name}" for name in MIGRATED_MODULES}
        roots = [
            REPOSITORY_ROOT / "TCFMain.py",
            REPOSITORY_ROOT / "TCF_Params",
            REPOSITORY_ROOT / "ClassesTree",
            REPOSITORY_ROOT / "DatasetConverter",
            REPOSITORY_ROOT / "BertScript",
            PACKAGE_ROOT,
        ]
        violations = []
        for root in roots:
            paths = [root] if root.is_file() else root.rglob("*.py")
            for path in paths:
                if "TRV_deploy" in path.parts:
                    continue
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for node in ast.walk(tree):
                    module = None
                    if isinstance(node, ast.ImportFrom):
                        module = node.module
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if (
                                alias.name in legacy_prefixes
                                or alias.name == "tcf_utils"
                                or alias.name.startswith("tcf_utils.")
                            ):
                                violations.append(f"{path.relative_to(REPOSITORY_ROOT)}:{alias.name}")
                    if (
                        module in legacy_prefixes
                        or module == "tcf_utils"
                        or (module and module.startswith("tcf_utils."))
                    ):
                        violations.append(f"{path.relative_to(REPOSITORY_ROOT)}:{module}")
        self.assertEqual(violations, [])

    def test_package_modules_do_not_import_legacy_path_injector(self):
        roots = [
            REPOSITORY_ROOT / "TCFMain.py",
            REPOSITORY_ROOT / "TCF_Params",
            PACKAGE_ROOT,
        ]
        violations = []
        for root in roots:
            paths = [root] if root.is_file() else root.rglob("*.py")
            for path in paths:
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.ImportFrom)
                        and node.module == "PackageImport"
                    ):
                        violations.append(str(path.relative_to(REPOSITORY_ROOT)))
        self.assertEqual(violations, [])

    def test_canonical_stage_entry_points_do_not_import_legacy_path_injector(self):
        entry_points = [
            REPOSITORY_ROOT / "DatasetConverter/DataConverter.py",
            REPOSITORY_ROOT / "BertScript/RunClassfier.py",
            REPOSITORY_ROOT / "BertScript/TextClassification_transformers.py",
            REPOSITORY_ROOT / "BertScript/CombineTestResult.py",
            REPOSITORY_ROOT / "BertScript/Test_result_Vis.py",
        ]
        violations = []
        for path in entry_points:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "PackageImport"
                ):
                    violations.append(str(path.relative_to(REPOSITORY_ROOT)))

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
