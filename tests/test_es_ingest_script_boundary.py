"""Dependency-light contract tests for the manual Elasticsearch TXT ingest CLI."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from scripts import ES_ingest_txt_to_es as script
from text_category_profiler import ES_ingest_txt_to_es as legacy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ES_ingest_txt_to_es.py"
LEGACY = ROOT / "text_category_profiler" / "ES_ingest_txt_to_es.py"


class ESIngestScriptBoundaryTests(unittest.TestCase):
    def test_importing_both_entrypoints_is_inert_without_elasticsearch(self):
        for target in (SCRIPT, LEGACY):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp:
                with mock.patch.dict(sys.modules, {"elasticsearch": None}):
                    with redirect_stdout(io.StringIO()) as captured:
                        namespace = runpy.run_path(str(target), run_name="import_check")
                self.assertEqual(captured.getvalue(), "")
                self.assertEqual(list(Path(temp).iterdir()), [])
                self.assertIn("main", namespace)

    def test_both_direct_entrypoints_support_help_without_elasticsearch(self):
        for target in (SCRIPT, LEGACY):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as cwd:
                completed = subprocess.run(
                    [sys.executable, str(target), "--help"],
                    cwd=cwd, capture_output=True, text=True, timeout=20,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("--dedup-by-content", completed.stdout)
                self.assertIn("--batch", completed.stdout)
                self.assertIn("--dir", completed.stdout)
                self.assertEqual(list(Path(cwd).iterdir()), [])

    def test_original_python_helpers_remain_importable(self):
        for name in ("iter_txt_paths", "read_text_best_effort", "make_uuid_from_file",
                     "make_uuid_from_content", "build_doc_from_file",
                     "build_doc_from_file_OLD", "bulk_insert_txt_dir", "chunked"):
            with self.subTest(name=name):
                self.assertIs(getattr(legacy, name), getattr(script, name))
        with self.assertRaises(AttributeError):
            getattr(legacy, "nonexistent_helper")

    def test_scan_and_document_contract_and_dedup_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            first = root / "One.TXT"
            second = root / "sub" / "Two.txt"
            first.write_text("中文 sample", encoding="utf-8")
            second.write_text("中文 sample", encoding="utf-8")
            (root / "ignore.pdf").write_text("not txt", encoding="utf-8")

            found = set(script.iter_txt_paths(tmp))
            self.assertEqual(found, {str(first), str(second)})
            self.assertEqual(script.read_text_best_effort(str(first)), "中文 sample")
            a_id, a_doc = script.build_doc_from_file(str(first))
            b_id, b_doc = script.build_doc_from_file(str(second))
            self.assertNotEqual(a_id, b_id)
            self.assertEqual(a_doc["rawInfo"], {"content": "中文 sample", "langCode": "C"})
            self.assertEqual(a_doc["communication"]["subject"], "One")
            self.assertEqual(a_doc["itc"]["rawTypeCode"], "05")
            self.assertFalse(a_doc["sourceFile"]["dedupByContent"])
            self.assertEqual(b_doc["communication"]["subject"], "Two")
            ca, ca_doc = script.build_doc_from_file(str(first), dedup_by_content=True)
            cb, _ = script.build_doc_from_file(str(second), dedup_by_content=True)
            self.assertEqual(ca, cb)
            self.assertTrue(ca_doc["sourceFile"]["dedupByContent"])
            self.assertEqual(ca_doc["uuid"], ca)

    def test_chunk_boundaries(self):
        self.assertEqual(list(script.chunked(range(5), 2)), [[0, 1], [2, 3], [4]])

    def test_bulk_uses_mocked_client_and_preserves_action_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.txt"
            path.write_text("sample", encoding="utf-8")
            fake_client = object()
            backend = types.ModuleType("text_category_profiler.integrations.ES_utils")
            backend.INDEX_MAPPINGS = {"properties": {}}
            backend.get_es_client = mock.Mock(return_value=fake_client)
            backend.ensure_index = mock.Mock()
            fake_es = types.ModuleType("elasticsearch")
            actions = []
            def fake_bulk(client, batch, raise_on_error=False):
                self.assertIs(client, fake_client)
                self.assertFalse(raise_on_error)
                actions.extend(batch)
                return len(batch), []
            fake_es.helpers = types.SimpleNamespace(bulk=fake_bulk)
            with mock.patch.dict(sys.modules, {
                "elasticsearch": fake_es,
                "text_category_profiler.integrations.ES_utils": backend,
            }), redirect_stdout(io.StringIO()):
                result = script.bulk_insert_txt_dir(
                    "test_index", tmp, batch_size=1, op_type="create",
                    dedup_by_content=True,
                )
            self.assertEqual(result, 1)
            backend.get_es_client.assert_called_once_with("http://localhost:9200")
            backend.ensure_index.assert_called_once_with(
                index_name="test_index", mappings=backend.INDEX_MAPPINGS,
                es_client=fake_client,
            )
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["_op_type"], "create")
            self.assertEqual(actions[0]["_index"], "test_index")
            self.assertEqual(actions[0]["_id"], actions[0]["_source"]["uuid"])
            self.assertEqual(actions[0]["_source"]["rawInfo"]["content"], "sample")

    def test_cli_options_and_defaults_are_unchanged(self):
        with mock.patch.object(script, "bulk_insert_txt_dir", return_value=0) as insert:
            script.main(["-d", "example", "--dedup-by-content"])
        insert.assert_called_once_with(
            index_name="news_test", root_dir="example",
            es_host="http://localhost:9200", batch_size=500,
            lang_code="C", user_name="crawler",
            op_type="index", dedup_by_content=True,
        )

    def test_legacy_main_delegates_only_when_called(self):
        with mock.patch("runpy.run_path") as run:
            legacy.main()
        run.assert_called_once_with(str(SCRIPT), run_name="__main__")


if __name__ == "__main__":
    unittest.main()
