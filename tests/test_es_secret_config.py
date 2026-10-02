import os
import re
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

CONFIGS = (
    (REPOSITORY_ROOT / "text_category_profiler" / "ArtCluESJobTemplate.py", "esJobTemplate"),
    (REPOSITORY_ROOT / "DatasetConverter" / "ESDataConfigFile.py", "esJob"),
)

ELASTICSEARCH_SAMPLE_ROOT = REPOSITORY_ROOT / "DatasetConverter" / "elasticsearch"
TEXT_SECRET_SUFFIXES = {".py", ".ini", ".txt", ".json"}

PASSWORD_ASSIGNMENT_RE = re.compile(
    r"""^\s*#?\s*["']?password["']?\s*[:=]\s*(.+?)\s*,?\s*$""",
    re.IGNORECASE,
)
ENROLLMENT_TOKEN_RE = re.compile(r"^\s*eyJ[A-Za-z0-9_-]{20,}={0,2}\s*$")
LEGACY_HOST_PASSWORD_RE = re.compile(r"^\s*[HC]:(?![\\/])\S{8,}\s*$")


class ElasticsearchSecretConfigTests(unittest.TestCase):
    def _load_password(self, path, mapping_name):
        namespace = runpy.run_path(str(path))
        return namespace[mapping_name]["es_tokens"]["password"]

    def _secret_surface_paths(self):
        paths = {path for path, _ in CONFIGS}
        paths.update(
            path
            for path in ELASTICSEARCH_SAMPLE_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in TEXT_SECRET_SUFFIXES
        )
        return sorted(paths)

    def test_configs_read_password_from_environment(self):
        with patch.dict(os.environ, {"TCP_ELASTIC_PASSWORD": "sentinel-secret"}, clear=False):
            for path, mapping_name in CONFIGS:
                with self.subTest(path=path):
                    self.assertEqual(
                        self._load_password(path, mapping_name),
                        "sentinel-secret",
                    )

    def test_configs_have_no_password_fallback_when_environment_is_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            for path, mapping_name in CONFIGS:
                with self.subTest(path=path):
                    self.assertIsNone(self._load_password(path, mapping_name))

    def test_tracked_elasticsearch_surfaces_do_not_embed_credentials(self):
        violations = []
        for path in self._secret_surface_paths():
            text = path.read_text(encoding="utf-8-sig")
            for line_number, line in enumerate(text.splitlines(), start=1):
                match = PASSWORD_ASSIGNMENT_RE.match(line)
                if match:
                    rhs = match.group(1)
                    if "TCP_ELASTIC_PASSWORD" not in rhs:
                        violations.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:password"
                        )
                if ENROLLMENT_TOKEN_RE.match(line):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:enrollment-token"
                    )
                if (
                    path.name == "架站說明.txt"
                    and LEGACY_HOST_PASSWORD_RE.match(line)
                ):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:legacy-password-note"
                    )

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
