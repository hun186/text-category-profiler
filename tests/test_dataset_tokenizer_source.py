import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from DatasetConverter.adapters.tokenizer_source import load_auto_tokenizer
from DatasetConverter.adapters.tokenizer_source import resolve_tokenizer_model
from DatasetConverter.adapters.tokenizer_source import TokenizerModel


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class AutoTokenizerFactoryTests(unittest.TestCase):
    def test_passes_model_directory_and_legacy_trust_setting(self):
        from_pretrained = Mock()
        fake_auto_tokenizer = types.SimpleNamespace(from_pretrained=from_pretrained)
        fake_module = types.SimpleNamespace(AutoTokenizer=fake_auto_tokenizer)

        with patch.dict(sys.modules, {"transformers": fake_module}):
            tokenizer = load_auto_tokenizer(
                "/models/fixture", trust_remote_code=True
            )

        self.assertIs(tokenizer, from_pretrained.return_value)
        from_pretrained.assert_called_once_with(
            "/models/fixture", trust_remote_code=True
        )

    def test_reader_has_no_module_scope_transformers_import(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "transformers"
                for node in tree.body
            )
        )

    def test_reader_has_no_maintenance_probe_or_cli_parser_dependency(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_names = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        function_names = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }

        self.assertNotIn("ClassfierOptionParser", imported_names)
        self.assertNotIn("get_base_model_checkpoint", imported_names)
        self.assertNotIn("tokenization_wrap_Test", function_names)
        self.assertFalse(
            any(
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
                for node in tree.body
            )
        )

    def test_reader_has_no_legacy_path_injector_or_module_scope_chdir(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "PackageImport"
                for node in tree.body
            )
        )
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "chdir"
                for node in tree.body
            )
        )

    def test_reader_has_no_pandas_dataframe_adapter_or_corpus_file_fanout(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_names = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }

        self.assertNotIn("dfFromSQLite3", imported_names)
        self.assertNotIn("CZJ_CorpusFile", path.read_text(encoding="utf-8"))


class TokenizerModelResolutionTests(unittest.TestCase):
    def test_uses_requested_local_model_and_first_nested_checkpoint(self):
        result = resolve_tokenizer_model(
            "requested-model",
            resolve_local_directory=lambda path: "/models/requested",
            walk=lambda path: [
                (path, ["checkpoint"], []),
                (f"{path}/checkpoint", [], ["config.json"]),
            ],
        )

        self.assertEqual(
            result,
            TokenizerModel(
                requested_directory="requested-model",
                resolved_directory="/models/requested/checkpoint",
                used_fallback=False,
            ),
        )

    def test_falls_back_to_local_default_when_requested_model_is_missing(self):
        resolved_paths = []

        def resolve(path):
            resolved_paths.append(path)
            return None if path == "missing" else "/models/default"

        result = resolve_tokenizer_model(
            "missing",
            resolve_local_directory=resolve,
            walk=lambda path: [(path, [], ["config.json"])],
        )

        self.assertEqual(resolved_paths, ["missing", "xlm-roberta-base"])
        self.assertEqual(result.resolved_directory, "/models/default")
        self.assertTrue(result.used_fallback)

    def test_preserves_remote_default_name_when_no_local_model_exists(self):
        result = resolve_tokenizer_model(
            "missing",
            resolve_local_directory=lambda path: None,
            walk=lambda path: [],
        )

        self.assertEqual(result.resolved_directory, "xlm-roberta-base")
        self.assertTrue(result.used_fallback)

    def test_integration_module_has_no_module_scope_transformers_import(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "adapters" / "tokenizer_source.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "transformers"
                for node in tree.body
            )
        )


if __name__ == "__main__":
    unittest.main()
