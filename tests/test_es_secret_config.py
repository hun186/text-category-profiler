import ast
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
DB_UTILS_PATH = REPOSITORY_ROOT / "text_category_profiler" / "data" / "DB_utils.py"
TEXT_SECRET_SUFFIXES = {".py", ".ini", ".txt", ".json"}

PASSWORD_KEY_RE = re.compile(r"""["\']?password["\']?\s*[:=]\s*""", re.IGNORECASE)
ENROLLMENT_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{20,}={0,2}(?![A-Za-z0-9_-])"
)
URL_USERINFO_RE = re.compile(
    r"""https?://[^\s/"'@:]+:[^\s/"'@]+@""",
    re.IGNORECASE,
)
LEGACY_HOST_PASSWORD_RE = re.compile(r"^\s*[HC]:(?![\\/])\S{8,}\s*$")

ALLOWED_PASSWORD_EXPRESSIONS = {
    "${TCP_ELASTIC_PASSWORD}",
    'os.environ.get("TCP_ELASTIC_PASSWORD")',
    "os.environ.get('TCP_ELASTIC_PASSWORD')",
}


def _password_value_expression(line, start):
    """Read one complete assigned value up to a top-level delimiter/comment."""
    chars = []
    quote = None
    escaped = False
    paren_depth = 0
    placeholder_depth = 0
    index = start

    while index < len(line):
        char = line[index]

        if quote is not None:
            chars.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue

        if line.startswith("${", index):
            chars.extend(["$", "{"])
            placeholder_depth += 1
            index += 2
            continue

        if placeholder_depth > 0:
            chars.append(char)
            if char == "{":
                placeholder_depth += 1
            elif char == "}":
                placeholder_depth -= 1
            index += 1
            continue

        if char in {'"', "'"}:
            quote = char
            chars.append(char)
            index += 1
            continue

        if char == "(":
            paren_depth += 1
            chars.append(char)
            index += 1
            continue
        if char == ")":
            if paren_depth > 0:
                paren_depth -= 1
            chars.append(char)
            index += 1
            continue

        if paren_depth == 0 and char in {",", "}", "#"}:
            break

        chars.append(char)
        index += 1

    return "".join(chars).strip()


def password_value_expressions(line):
    """Return complete password value expressions found anywhere in one line."""
    return [
        _password_value_expression(line, match.end())
        for match in PASSWORD_KEY_RE.finditer(line)
    ]


AUTH_TUPLE_NAMES = {"http_auth", "basic_auth"}


def _literal_string(node):
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None


def hardcoded_auth_tuple_lines(source):
    """Return line numbers whose auth tuple contains a literal password."""
    tree = ast.parse(source)
    violations = []

    for node in ast.walk(tree):
        value = None
        line_number = getattr(node, "lineno", None)

        if isinstance(node, ast.keyword) and node.arg in AUTH_TUPLE_NAMES:
            value = node.value
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(target, ast.Name) and target.id in AUTH_TUPLE_NAMES
                for target in targets
            ):
                value = node.value

        if not isinstance(value, (ast.Tuple, ast.List)) or len(value.elts) < 2:
            continue

        password = _literal_string(value.elts[1])
        if password:
            violations.append(line_number)

    return sorted(set(line for line in violations if line is not None))


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

    def test_db_utils_redaction_helper_masks_password_without_mutating_source(self):
        source = DB_UTILS_PATH.read_text(encoding="utf-8-sig")
        module = ast.parse(source)
        helper = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_redact_es_job_for_logging"
        )
        namespace = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(DB_UTILS_PATH), "exec"), namespace)
        redact = namespace["_redact_es_job_for_logging"]

        job = {
            "indexname": "sample",
            "es_tokens": {
                "host": "https://localhost:9200",
                "user": "elastic",
                "password": "sentinel-secret",
            },
        }
        redacted = redact(job)

        self.assertEqual(redacted["es_tokens"]["password"], "***REDACTED***")
        self.assertEqual(job["es_tokens"]["password"], "sentinel-secret")
        self.assertIsNot(redacted["es_tokens"], job["es_tokens"])

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

    def test_password_guard_validates_value_before_trailing_comment(self):
        hardcoded_with_hint = '"password": "real-secret"  # replace with TCP_ELASTIC_PASSWORD'
        self.assertEqual(
            password_value_expressions(hardcoded_with_hint),
            ['"real-secret"'],
        )

    def test_password_guard_detects_inline_mapping_values(self):
        inline_examples = (
            'es_tokens = {"password": "real-secret"}',
            '{"user": "elastic", "password": "real-secret"}',
        )
        for line in inline_examples:
            with self.subTest(line=line):
                self.assertEqual(
                    password_value_expressions(line),
                    ['"real-secret"'],
                )

    def test_password_guard_rejects_suffixes_after_approved_expressions(self):
        bypass_examples = (
            '"password": os.environ.get("TCP_ELASTIC_PASSWORD") or "real-secret"',
            '"password": ${TCP_ELASTIC_PASSWORD} + "-suffix"',
        )
        for line in bypass_examples:
            with self.subTest(line=line):
                values = password_value_expressions(line)
                self.assertEqual(len(values), 1)
                self.assertNotIn(values[0], ALLOWED_PASSWORD_EXPRESSIONS)

    def test_password_guard_accepts_complete_approved_expressions(self):
        approved_examples = (
            '"password": os.environ.get("TCP_ELASTIC_PASSWORD"), "user": "elastic"',
            '"password": ${TCP_ELASTIC_PASSWORD}',
        )
        for line in approved_examples:
            with self.subTest(line=line):
                values = password_value_expressions(line)
                self.assertEqual(len(values), 1)
                self.assertIn(values[0], ALLOWED_PASSWORD_EXPRESSIONS)

    def test_password_guard_preserves_environment_placeholder_closing_brace(self):
        self.assertEqual(
            password_value_expressions("password = ${TCP_ELASTIC_PASSWORD}"),
            ["${TCP_ELASTIC_PASSWORD}"],
        )

    def test_enrollment_token_guard_detects_embedded_literals(self):
        token = "eyJ" + ("A" * 24)
        embedded_examples = (
            f"ENROLLMENT_TOKEN={token}",
            f'"token": "{token}"',
        )
        for line in embedded_examples:
            with self.subTest(line=line):
                self.assertIsNotNone(ENROLLMENT_TOKEN_RE.search(line))

    def test_url_userinfo_guard_detects_embedded_credentials(self):
        credential_urls = (
            '"host": "https://elastic:real-secret@localhost:9200"',
            "ELASTICSEARCH_URL=http://elastic:real-secret@example.test:9200",
        )
        for line in credential_urls:
            with self.subTest(line=line):
                self.assertIsNotNone(URL_USERINFO_RE.search(line))

    def test_auth_tuple_guard_detects_literal_passwords(self):
        hardcoded_examples = (
            'Elasticsearch(host, http_auth=("elastic", "real-secret"))',
            'Elasticsearch(host, basic_auth=("elastic", "real-secret"))',
            'http_auth = ("elastic", "real-secret")',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [1])

    def test_auth_tuple_guard_allows_runtime_password_references(self):
        safe_examples = (
            'Elasticsearch(host, http_auth=(es_tokens["user"], es_tokens["password"]))',
            'Elasticsearch(host, basic_auth=(user, os.environ.get("TCP_ELASTIC_PASSWORD")))',
            'http_auth = (user, password)',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

    def test_tracked_elasticsearch_surfaces_do_not_embed_credentials(self):
        violations = []
        for path in self._secret_surface_paths():
            text = path.read_text(encoding="utf-8-sig")
            if path.suffix.lower() == ".py":
                for line_number in hardcoded_auth_tuple_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:auth-tuple"
                    )
            for line_number, line in enumerate(text.splitlines(), start=1):
                for value_expression in password_value_expressions(line):
                    if value_expression not in ALLOWED_PASSWORD_EXPRESSIONS:
                        violations.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:password"
                        )
                if ENROLLMENT_TOKEN_RE.search(line):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:enrollment-token"
                    )
                if URL_USERINFO_RE.search(line):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:credential-url"
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
