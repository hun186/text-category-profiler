import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from DatasetConverter.adapters.elasticsearch_source import create_elasticsearch_client


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ElasticsearchClientFactoryTests(unittest.TestCase):
    def test_passes_legacy_connection_arguments_to_client(self):
        constructor = Mock()
        fake_module = types.SimpleNamespace(Elasticsearch=constructor)
        with patch.dict(sys.modules, {"elasticsearch": fake_module}):
            client = create_elasticsearch_client(
                {"host": "https://example.invalid", "user": "user", "password": "secret"}
            )

        self.assertIs(client, constructor.return_value)
        constructor.assert_called_once_with(
            "https://example.invalid",
            http_auth=("user", "secret"),
            verify_certs=False,
        )

    def test_module_has_no_module_scope_elasticsearch_import(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "adapters" / "elasticsearch_source.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom) and node.module == "elasticsearch"
                for node in tree.body
            )
        )


if __name__ == "__main__":
    unittest.main()
