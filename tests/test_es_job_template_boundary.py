"""No-service compatibility tests for the legacy ArtClu Elasticsearch job template."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "text_category_profiler" / "integrations" / "es_job_template.py"
LEGACY = ROOT / "text_category_profiler" / "ArtCluESJobTemplate.py"
HISTORICAL_BLOB = "28c0209d366c247c85b9053b701799c3c97e74a5"


def run_fresh_interpreter(code, *, password=None, first="legacy"):
    env = os.environ.copy()
    env.pop("TCP_ELASTIC_PASSWORD", None)
    if password is not None:
        env["TCP_ELASTIC_PASSWORD"] = password
    return subprocess.run(
        [sys.executable, "-c", code.replace("FIRST_IMPORT", repr(first))],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=15,
        check=False,
    )


class ESJobTemplateBoundaryTests(unittest.TestCase):
    def test_canonical_source_preserves_original_git_blob(self):
        content = CANONICAL.read_bytes()
        digest = hashlib.sha1(
            ("blob %d" % len(content)).encode("ascii") + bytes([0]) + content
        ).hexdigest()
        self.assertEqual(digest, HISTORICAL_BLOB)
        self.assertTrue(LEGACY.is_file())

    def test_default_settings_and_unset_password_on_both_import_orders(self):
        code = textwrap.dedent("""
            import importlib
            import sys
            first = FIRST_IMPORT
            old_name = "text_category_profiler.ArtCluESJobTemplate"
            new_name = "text_category_profiler.integrations.es_job_template"
            importlib.import_module(old_name if first == "legacy" else new_name)
            old = importlib.import_module(old_name).esJobTemplate
            new = importlib.import_module(new_name).esJobTemplate
            assert old is new
            assert new == {
                "es_tokens": {
                    "host": "https://localhost:9200",
                    "user": "elastic",
                    "password": None,
                },
                "indexnameTemplate": "movies_%m",
                "langCodeList": ["C", "E", "J"],
                "Vis_ESFileNameMode": "subject_id",
            }
            assert "elasticsearch" not in sys.modules
        """)
        for first in ("legacy", "canonical"):
            with self.subTest(first=first):
                result = run_fresh_interpreter(code, first=first)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_env_password_is_snapshotted_at_first_import(self):
        code = textwrap.dedent("""
            import importlib
            import os
            old = importlib.import_module("text_category_profiler.ArtCluESJobTemplate")
            new = importlib.import_module(
                "text_category_profiler.integrations.es_job_template"
            )
            assert old.esJobTemplate is new.esJobTemplate
            assert old.esJobTemplate["es_tokens"]["password"] == "test-value-not-real"
            os.environ["TCP_ELASTIC_PASSWORD"] = "changed-after-import"
            assert new.esJobTemplate["es_tokens"]["password"] == "test-value-not-real"
        """)
        result = run_fresh_interpreter(code, password="test-value-not-real")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mutations_remain_shared_through_legacy_alias(self):
        code = textwrap.dedent("""
            from text_category_profiler.ArtCluESJobTemplate import esJobTemplate
            from text_category_profiler.integrations.es_job_template import (
                esJobTemplate as canonical,
            )
            assert canonical is esJobTemplate
            esJobTemplate["Vis_ESFileNameMode"] = "temporary-example"
            assert canonical["Vis_ESFileNameMode"] == "temporary-example"
        """)
        result = run_fresh_interpreter(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_imports_do_not_create_es_clients_or_open_sockets(self):
        code = textwrap.dedent("""
            from unittest import mock
            import importlib
            import sys
            with mock.patch("socket.socket", side_effect=AssertionError("network")):
                importlib.import_module("text_category_profiler.ArtCluESJobTemplate")
                importlib.import_module(
                    "text_category_profiler.integrations.es_job_template"
                )
            assert "elasticsearch" not in sys.modules
        """)
        result = run_fresh_interpreter(code, password="test-value-not-real")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
