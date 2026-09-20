import ast
import unittest
import warnings
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


def imported_modules(source):
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


STAGE_IMPLEMENTATION_MODULES = {
    "DatasetConverter.DataConverter",
    "BertScript.RunClassfier",
    "BertScript.CombineTestResult",
    "BertScript.Test_result_Vis",
}


class PackageLayoutTests(unittest.TestCase):
    def test_shared_boundaries_do_not_import_stage_implementations(self):
        self.assertIn(
            "BertScript.RunClassfier",
            imported_modules("from BertScript.RunClassfier import main"),
        )
        violations = []
        for package in ("pipeline", "execution", "filesystem"):
            for path in (PACKAGE_ROOT / package).rglob("*.py"):
                forbidden = imported_modules(path.read_text(encoding="utf-8-sig"))
                forbidden &= STAGE_IMPLEMENTATION_MODULES
                violations.extend(
                    "{}:{}".format(path.relative_to(REPOSITORY_ROOT), module)
                    for module in sorted(forbidden)
                )
        self.assertEqual(violations, [])

    def test_stage_implementations_do_not_import_next_stage(self):
        rules = {
            "DatasetConverter/DataConverter.py": {
                "BertScript.RunClassfier", "BertScript.CombineTestResult",
                "BertScript.Test_result_Vis",
            },
            "BertScript/RunClassfier.py": {
                "BertScript.CombineTestResult", "BertScript.Test_result_Vis",
            },
            "BertScript/classifier_stage.py": {
                "BertScript.CombineTestResult", "BertScript.Test_result_Vis",
            },
            "BertScript/CombineTestResult.py": {"BertScript.Test_result_Vis"},
            "BertScript/result_combination_stage.py": {"BertScript.Test_result_Vis"},
            "BertScript/Test_result_Vis.py": set(),
            "BertScript/visualization_stage.py": set(),
        }
        synthetic = imported_modules("from BertScript.Test_result_Vis import main")
        self.assertTrue(synthetic & {"BertScript.Test_result_Vis"})
        violations = []
        for relative_path, forbidden_modules in rules.items():
            path = REPOSITORY_ROOT / relative_path
            found = imported_modules(path.read_text(encoding="utf-8-sig"))
            violations.extend(
                "{}:{}".format(relative_path, module)
                for module in sorted(found & forbidden_modules)
            )
        self.assertEqual(violations, [])

    def test_datasetconverter_stage_plan_modules_remain_present(self):
        boundaries = (
            "DatasetConverter/stage.py",
            "DatasetConverter/config.py",
            "DatasetConverter/core/stage_utils.py",
            "DatasetConverter/adapters/pipeline_source.py",
            "DatasetConverter/sources/source_collection.py",
        )
        self.assertEqual(
            [path for path in boundaries if not (REPOSITORY_ROOT / path).is_file()],
            [],
        )

    def test_legacy_entrypoints_remain_present(self):
        entrypoints = (
            "TCFMain.py",
            "DatasetConverter/DataConverter.py",
            "BertScript/RunClassfier.py",
            "BertScript/CombineTestResult.py",
            "BertScript/Test_result_Vis.py",
        )
        self.assertEqual(
            [path for path in entrypoints if not (REPOSITORY_ROOT / path).is_file()],
            [],
        )

    def test_active_data_converter_apis_have_no_mutable_defaults(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "DataConverter.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        dataset_generator = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "DatasetGenerator"
        )
        callables = [
            next(
                node for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "BuildSamplesDfFromPaths"
            ),
            next(
                node for node in dataset_generator.body
                if isinstance(node, ast.FunctionDef) and node.name == "__init__"
            ),
        ]

        violations = {
            function.name: [
                ast.unparse(default)
                for default in function.args.defaults
                if isinstance(default, (ast.Dict, ast.List, ast.Set))
            ]
            for function in callables
        }

        self.assertEqual(violations, {
            "BuildSamplesDfFromPaths": [],
            "__init__": [],
        })

    def test_data_convert_job_generator_has_no_mutable_defaults(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "DataConverter.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        generator = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "DataConvertJobGenerater"
        )
        constructor = next(
            node for node in generator.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )

        mutable_defaults = [
            ast.unparse(default)
            for default in constructor.args.defaults
            if isinstance(default, (ast.Dict, ast.List, ast.Set))
        ]

        self.assertEqual(mutable_defaults, [])

    def test_sample_handler_does_not_import_elasticsearch_at_module_scope(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        imported_modules = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_from = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertNotIn("elasticsearch", imported_modules)
        self.assertNotIn("elasticsearch", imported_from)

    def test_sample_reader_constructor_has_no_mutable_defaults(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        sample_reader = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "SampleReader"
        )
        constructor = next(
            node for node in sample_reader.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )

        mutable_defaults = [
            ast.unparse(default)
            for default in constructor.args.defaults
            if isinstance(default, (ast.Dict, ast.List, ast.Set))
        ]

        self.assertEqual(mutable_defaults, [])

    def test_application_source_has_no_invalid_escape_warnings(self):
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
                if {"TRV_deploy", "Dash-by-Plotly-master"}.intersection(path.parts):
                    continue
                try:
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        ast.parse(
                            path.read_text(encoding="utf-8-sig"),
                            filename=str(path),
                        )
                except (SyntaxError, UnicodeDecodeError):
                    continue
                violations.extend(
                    str(path.relative_to(REPOSITORY_ROOT))
                    for warning in caught
                    if "invalid escape sequence" in str(warning.message)
                )

        self.assertEqual(violations, [])

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
                if {"TRV_deploy", "Dash-by-Plotly-master"}.intersection(path.parts):
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

    def test_active_classes_tree_boundary_does_not_import_legacy_path_injector(self):
        path = REPOSITORY_ROOT / "ClassesTree/ClassesTree_utils.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "PackageImport" or any(
                    alias.name == "PackageImporter" for alias in node.names
                ):
                    violations.append(ast.unparse(node))
            elif isinstance(node, ast.Import):
                violations.extend(
                    alias.name
                    for alias in node.names
                    if alias.name in {"PackageImport", "PackageImporter"}
                )

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
