import ast
import io
import os
import re
import runpy
import tokenize
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
RUNTIME_ES_MODULES = (
    DB_UTILS_PATH,
    REPOSITORY_ROOT / "DatasetConverter" / "adapters" / "elasticsearch_source.py",
    REPOSITORY_ROOT / "text_category_profiler" / "ES_ingest_txt_to_es.py",
    REPOSITORY_ROOT / "text_category_profiler" / "integrations" / "ES_utils.py",
)
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
REDACTED_PASSWORD_SENTINEL = "***REDACTED***"


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


def python_comment_password_lines(source):
    """Return Python comment lines that embed a disallowed password value."""
    violations = []
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)

    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        if any(
            value_expression not in ALLOWED_PASSWORD_EXPRESSIONS
            for value_expression in password_value_expressions(token.string)
        ):
            violations.append(token.start[0])

    return sorted(set(violations))


AUTH_TUPLE_NAMES = {"http_auth", "basic_auth"}


def _is_auth_tuple_target(node):
    if isinstance(node, ast.Name):
        return node.id in AUTH_TUPLE_NAMES
    if isinstance(node, ast.Subscript):
        return _literal_string(node.slice) in AUTH_TUPLE_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in AUTH_TUPLE_NAMES
    return False


def _literal_string(node):
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _is_environment_lookup_call(node):
    if not isinstance(node, ast.Call):
        return False

    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and (
            (
                func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            )
            or (
                func.attr == "get"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "environ"
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "os"
            )
        )
    )


def _environment_lookup_default_node(node):
    """Return the fallback expression from supported environment lookups."""
    if not _is_environment_lookup_call(node):
        return None

    if len(node.args) >= 2:
        return node.args[1]

    for keyword in node.keywords:
        if keyword.arg == "default":
            return keyword.value

    return None


def _name_bindings(tree):
    """Map simple variable names to their source-ordered assigned expressions."""
    bindings = {}

    def add_binding(target, value, line_number):
        if isinstance(target, ast.Name):
            bindings.setdefault(target.id, []).append((line_number, value))

    binding_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
    ]
    binding_nodes.sort(
        key=lambda node: (
            getattr(node, "lineno", 0),
            getattr(node, "col_offset", 0),
        )
    )

    for node in binding_nodes:
        line_number = getattr(node, "lineno", 0)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                add_binding(target, node.value, line_number)
        elif isinstance(node, ast.AnnAssign):
            add_binding(node.target, node.value, line_number)
        elif isinstance(node, ast.NamedExpr):
            add_binding(node.target, node.value, line_number)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            if not isinstance(node.op, ast.Add):
                continue
            previous = _bound_name_value(
                node.target.id,
                bindings,
                line_number - 1,
                set(),
            )
            if previous is None:
                continue
            previous = _resolve_bound_node(
                previous,
                bindings,
                line_number - 1,
            )
            appended = _resolve_bound_node(
                node.value,
                bindings,
                line_number,
            )
            if not isinstance(previous, (ast.Tuple, ast.List)):
                continue
            if not isinstance(appended, (ast.Tuple, ast.List)):
                continue
            combined = ast.Tuple(
                elts=[*previous.elts, *appended.elts],
                ctx=ast.Load(),
            )
            add_binding(node.target, combined, line_number)

    return bindings


def _bound_name_value(name, bindings, before_line, seen_names):
    if name in seen_names:
        return None

    candidates = [
        (line_number, value)
        for line_number, value in bindings.get(name, ())
        if line_number <= before_line
    ]
    if not candidates:
        return None

    return candidates[-1][1]


def _resolve_bound_node(node, bindings, before_line, seen_names=None):
    """Resolve simple name aliases to their latest preceding expression."""
    seen_names = set() if seen_names is None else set(seen_names)
    current = node

    while isinstance(current, ast.Name):
        if current.id in seen_names:
            break
        seen_names.add(current.id)
        bound = _bound_name_value(current.id, bindings, before_line, seen_names - {current.id})
        if bound is None:
            break
        current = bound

    return current


def _literal_subscript_key(node):
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, (str, int)) else None


def _resolve_constant_subscript(node, bindings, before_line):
    """Resolve a constant dict/list/tuple subscript to only its selected value."""
    if not isinstance(node, ast.Subscript):
        return None

    key = _literal_subscript_key(node.slice)
    if key is None:
        return None

    container = _resolve_bound_node(node.value, bindings, before_line)

    if isinstance(container, (ast.Tuple, ast.List)) and isinstance(key, int):
        try:
            return container.elts[key]
        except IndexError:
            return None

    if isinstance(container, ast.Dict):
        for dict_key, dict_value in zip(container.keys, container.values):
            try:
                candidate = ast.literal_eval(dict_key)
            except (ValueError, TypeError):
                continue
            if candidate == key:
                return dict_value

    return None


def _hardcoded_password_values(node, bindings, before_line, seen_names=None):
    """Return statically embedded password strings from one expression."""
    seen_names = set() if seen_names is None else set(seen_names)

    literal = _literal_string(node)
    if literal:
        return [literal]

    if isinstance(node, ast.Name):
        if node.id in seen_names:
            return []
        bound = _bound_name_value(
            node.id,
            bindings,
            before_line,
            seen_names,
        )
        if bound is None:
            return []
        return _hardcoded_password_values(
            bound,
            bindings,
            before_line,
            seen_names | {node.id},
        )

    environment_default = _environment_lookup_default_node(node)
    if environment_default is not None:
        return _hardcoded_password_values(
            environment_default,
            bindings,
            before_line,
            seen_names,
        )

    if isinstance(node, ast.Call):
        if _is_environment_lookup_call(node):
            return []

        values = []
        positional_args = node.args
        if isinstance(node.func, ast.Attribute):
            values.extend(
                _hardcoded_password_values(
                    node.func.value,
                    bindings,
                    before_line,
                    seen_names,
                )
            )
            if node.func.attr == "get":
                positional_args = node.args[1:]

        for argument in positional_args:
            values.extend(
                _hardcoded_password_values(
                    argument,
                    bindings,
                    before_line,
                    seen_names,
                )
            )
        for keyword in node.keywords:
            values.extend(
                _hardcoded_password_values(
                    keyword.value,
                    bindings,
                    before_line,
                    seen_names,
                )
            )
        return values

    if isinstance(node, ast.Subscript):
        selected = _resolve_constant_subscript(node, bindings, before_line)
        if selected is None:
            return []
        return _hardcoded_password_values(
            selected,
            bindings,
            before_line,
            seen_names,
        )

    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values = []
        for element in node.elts:
            values.extend(
                _hardcoded_password_values(
                    element,
                    bindings,
                    before_line,
                    seen_names,
                )
            )
        return values

    if isinstance(node, ast.Dict):
        values = []
        for value in node.values:
            values.extend(
                _hardcoded_password_values(
                    value,
                    bindings,
                    before_line,
                    seen_names,
                )
            )
        return values

    if isinstance(node, ast.JoinedStr):
        values = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if value.value:
                    values.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                values.extend(
                    _hardcoded_password_values(
                        value.value,
                        bindings,
                        before_line,
                        seen_names,
                    )
                )
        return values

    if isinstance(node, ast.BoolOp):
        values = []
        for value in node.values:
            values.extend(
                _hardcoded_password_values(
                    value,
                    bindings,
                    before_line,
                    seen_names,
                )
            )
        return values

    if isinstance(node, ast.IfExp):
        return (
            _hardcoded_password_values(
                node.body,
                bindings,
                before_line,
                seen_names,
            )
            + _hardcoded_password_values(
                node.orelse,
                bindings,
                before_line,
                seen_names,
            )
        )

    if isinstance(node, ast.BinOp):
        return (
            _hardcoded_password_values(
                node.left,
                bindings,
                before_line,
                seen_names,
            )
            + _hardcoded_password_values(
                node.right,
                bindings,
                before_line,
                seen_names,
            )
        )

    if isinstance(node, ast.NamedExpr):
        return _hardcoded_password_values(
            node.value,
            bindings,
            before_line,
            seen_names,
        )

    return []


def hardcoded_auth_tuple_lines(source):
    """Return line numbers whose auth tuple contains a hardcoded password."""
    tree = ast.parse(source)
    bindings = _name_bindings(tree)
    violations = []

    for node in ast.walk(tree):
        candidates = []

        if isinstance(node, ast.keyword) and node.arg in AUTH_TUPLE_NAMES:
            candidates.append((getattr(node, "lineno", None), node.value))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_is_auth_tuple_target(target) for target in targets):
                candidates.append((getattr(node, "lineno", None), node.value))
        elif isinstance(node, ast.AugAssign) and _is_auth_tuple_target(node.target):
            line_number = getattr(node, "lineno", None)
            if isinstance(node.target, ast.Name):
                combined = _bound_name_value(
                    node.target.id,
                    bindings,
                    line_number,
                    set(),
                )
                if combined is not None:
                    candidates.append((line_number, combined))
            else:
                hardcoded_values = _hardcoded_password_values(
                    node.value,
                    bindings,
                    line_number,
                )
                if any(
                    value != REDACTED_PASSWORD_SENTINEL
                    for value in hardcoded_values
                ):
                    violations.append(line_number)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _literal_string(key) in AUTH_TUPLE_NAMES:
                    candidates.append(
                        (getattr(value, "lineno", getattr(node, "lineno", None)), value)
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional_args = list(node.args.posonlyargs) + list(node.args.args)
            positional_defaults = list(node.args.defaults)
            default_start = len(positional_args) - len(positional_defaults)
            for argument, default in zip(
                positional_args[default_start:],
                positional_defaults,
            ):
                if argument.arg in AUTH_TUPLE_NAMES:
                    candidates.append(
                        (getattr(default, "lineno", getattr(node, "lineno", None)), default)
                    )

            for argument, default in zip(
                node.args.kwonlyargs,
                node.args.kw_defaults,
            ):
                if argument.arg in AUTH_TUPLE_NAMES and default is not None:
                    candidates.append(
                        (getattr(default, "lineno", getattr(node, "lineno", None)), default)
                    )

        for line_number, value in candidates:
            if line_number is None:
                continue
            resolved_value = _resolve_bound_node(value, bindings, line_number)
            if (
                not isinstance(resolved_value, (ast.Tuple, ast.List))
                or len(resolved_value.elts) < 2
            ):
                continue

            passwords = _hardcoded_password_values(
                resolved_value.elts[1],
                bindings,
                line_number,
            )
            if any(
                password != REDACTED_PASSWORD_SENTINEL
                for password in passwords
            ):
                violations.append(line_number)

    return sorted(set(violations))


def _is_password_target(node):
    if isinstance(node, ast.Name):
        return node.id == "password"
    if isinstance(node, ast.Subscript):
        return _literal_string(node.slice) == "password"
    if isinstance(node, ast.Attribute):
        return node.attr == "password"
    return False


def hardcoded_password_literal_lines(source):
    """Return Python line numbers that assign a hardcoded password value."""
    tree = ast.parse(source)
    bindings = _name_bindings(tree)
    violations = []

    for node in ast.walk(tree):
        candidates = []

        if isinstance(node, ast.keyword) and node.arg == "password":
            candidates.append((getattr(node, "lineno", None), node.value))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_is_password_target(target) for target in targets):
                candidates.append((getattr(node, "lineno", None), node.value))
        elif isinstance(node, ast.NamedExpr) and _is_password_target(node.target):
            candidates.append((getattr(node, "lineno", None), node.value))
        elif isinstance(node, ast.AugAssign) and _is_password_target(node.target):
            candidates.append((getattr(node, "lineno", None), node.value))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _literal_string(key) == "password":
                    candidates.append((getattr(value, "lineno", getattr(node, "lineno", None)), value))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional_args = list(node.args.posonlyargs) + list(node.args.args)
            positional_defaults = list(node.args.defaults)
            default_start = len(positional_args) - len(positional_defaults)
            for argument, default in zip(
                positional_args[default_start:],
                positional_defaults,
            ):
                if argument.arg == "password":
                    candidates.append(
                        (getattr(default, "lineno", getattr(node, "lineno", None)), default)
                    )

            for argument, default in zip(
                node.args.kwonlyargs,
                node.args.kw_defaults,
            ):
                if argument.arg == "password" and default is not None:
                    candidates.append(
                        (getattr(default, "lineno", getattr(node, "lineno", None)), default)
                    )

        for line_number, value in candidates:
            if line_number is None:
                continue
            passwords = _hardcoded_password_values(
                value,
                bindings,
                line_number,
            )
            if any(
                password != REDACTED_PASSWORD_SENTINEL
                for password in passwords
            ):
                violations.append(line_number)

    return sorted(set(line for line in violations if line is not None))


class ElasticsearchSecretConfigTests(unittest.TestCase):
    def _load_password(self, path, mapping_name):
        namespace = runpy.run_path(str(path))
        return namespace[mapping_name]["es_tokens"]["password"]

    def _secret_surface_paths(self):
        paths = {path for path, _ in CONFIGS}
        paths.update(RUNTIME_ES_MODULES)
        paths.update(
            path
            for path in ELASTICSEARCH_SAMPLE_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in TEXT_SECRET_SUFFIXES
        )
        return sorted(paths)

    def test_secret_surface_paths_include_runtime_elasticsearch_modules(self):
        surfaces = set(self._secret_surface_paths())
        self.assertTrue(set(RUNTIME_ES_MODULES).issubset(surfaces))
        for path in RUNTIME_ES_MODULES:
            with self.subTest(path=path):
                self.assertTrue(path.is_file())

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

    def test_python_comment_password_guard_detects_commented_literals(self):
        hardcoded_examples = (
            '# "password": "embedded-value"',
            'value = 1  # password = "embedded-value"',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(python_comment_password_lines(source), [1])

    def test_python_comment_password_guard_ignores_code_and_safe_comments(self):
        safe_examples = (
            'password = password_from_store',
            'text = \'# "password": "embedded-value"\'',
            '# "password": os.environ.get("TCP_ELASTIC_PASSWORD")',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(python_comment_password_lines(source), [])

    def test_auth_tuple_guard_detects_literal_passwords(self):
        hardcoded_examples = (
            'Elasticsearch(host, http_auth=("elastic", "real-secret"))',
            'Elasticsearch(host, basic_auth=("elastic", "real-secret"))',
            'http_auth = ("elastic", "real-secret")',
            'options = {"http_auth": ("elastic", "real-secret")}',
            'options = {"basic_auth": ["elastic", "real-secret"]}',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [1])

    def test_auth_tuple_guard_detects_container_and_attribute_targets(self):
        hardcoded_examples = (
            'options["http_auth"] = ("elastic", "embedded-value")',
            'settings.basic_auth = ("elastic", "embedded-value")',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [1])

    def test_auth_tuple_guard_allows_runtime_container_and_attribute_targets(self):
        safe_examples = (
            'options["http_auth"] = ("elastic", password_from_store)',
            'settings.basic_auth = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

    def test_auth_tuple_guard_detects_augmented_assignments(self):
        cases = (
            (
                'http_auth = (user,)\n'
                'http_auth += ("embedded-value",)\n'
                'Elasticsearch(host, http_auth=http_auth)',
                [2, 3],
            ),
            (
                'AUTH_PASSWORD = ("embedded-value",)\n'
                'basic_auth = (user,)\n'
                'basic_auth += AUTH_PASSWORD\n'
                'Elasticsearch(host, basic_auth=basic_auth)',
                [3, 4],
            ),
            (
                'options["http_auth"] = (user,)\n'
                'options["http_auth"] += ("embedded-value",)',
                [2],
            ),
            (
                'settings.basic_auth = (user,)\n'
                'settings.basic_auth += ("embedded-value",)',
                [2],
            ),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

    def test_auth_tuple_guard_allows_runtime_augmented_assignments(self):
        safe_examples = (
            (
                'http_auth = (user,)\n'
                'http_auth += (password_from_store,)\n'
                'Elasticsearch(host, http_auth=http_auth)'
            ),
            (
                'basic_auth = (user,)\n'
                'basic_auth += (os.getenv("TCP_ELASTIC_PASSWORD"),)\n'
                'Elasticsearch(host, basic_auth=basic_auth)'
            ),
            (
                'options["http_auth"] = (user,)\n'
                'options["http_auth"] += (password_from_store,)'
            ),
            (
                'settings.basic_auth = (user,)\n'
                'settings.basic_auth += (os.getenv("TCP_ELASTIC_PASSWORD"),)'
            ),
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

    def test_auth_tuple_guard_detects_environment_lookup_literal_fallbacks(self):
        hardcoded_examples = (
            'Elasticsearch(host, http_auth=(user, os.getenv("TCP_ELASTIC_PASSWORD", "real-secret")))',
            'Elasticsearch(host, basic_auth=(user, os.environ.get("TCP_ELASTIC_PASSWORD", "real-secret")))',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [1])

    def test_auth_tuple_guard_detects_composed_literal_fallbacks(self):
        hardcoded_examples = (
            'Elasticsearch(host, http_auth=(user, os.getenv("TCP_ELASTIC_PASSWORD") or "real-secret"))',
            'Elasticsearch(host, basic_auth=(user, "real-" + "secret"))',
            'Elasticsearch(host, http_auth=(user, "real-secret" if use_fallback else password))',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [1])

    def test_auth_tuple_guard_detects_literals_in_call_expressions(self):
        cases = (
            ('Elasticsearch(host, http_auth=(user, "real-secret".strip()))', [1]),
            ('Elasticsearch(host, basic_auth=(user, normalize("real-secret")))', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

    def test_auth_tuple_guard_detects_indexed_container_passwords(self):
        cases = (
            ('Elasticsearch(host, http_auth=(user, ("real-secret",)[0]))', [1]),
            ('Elasticsearch(host, basic_auth=(user, ["real-secret"][0]))', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

    def test_auth_tuple_guard_resolves_only_password_mapping_key(self):
        safe_source = (
            'es_tokens = {"host": "https://localhost:9200", '
            '"user": "elastic", '
            '"password": os.environ.get("TCP_ELASTIC_PASSWORD")}\n'
            'Elasticsearch(host, http_auth=(es_tokens["user"], es_tokens["password"]))'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(safe_source), [])

        hardcoded_source = (
            'es_tokens = {"host": "https://localhost:9200", '
            '"user": "elastic", '
            '"password": "real-secret"}\n'
            'Elasticsearch(host, http_auth=(es_tokens["user"], es_tokens["password"]))'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(hardcoded_source), [2])

    def test_auth_tuple_guard_detects_literal_aliases(self):
        cases = (
            (
                'ELASTIC_PASSWORD = "real-secret"\n'
                'Elasticsearch(host, http_auth=(user, ELASTIC_PASSWORD))',
                [2],
            ),
            (
                'AUTH = ("elastic", "real-secret")\n'
                'Elasticsearch(host, http_auth=AUTH)',
                [2],
            ),
            (
                'AUTH = ["elastic", "real-secret"]\n'
                'options = {"basic_auth": AUTH}',
                [2],
            ),
            (
                'Elasticsearch(host, http_auth=(user, f"real-secret-{suffix}"))',
                [1],
            ),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

    def test_auth_tuple_guard_detects_function_defaults(self):
        cases = (
            ('def client(http_auth=("elastic", "real-secret")):\n    return http_auth', [1]),
            ('def client(*, basic_auth=("elastic", "real-secret")):\n    return basic_auth', [1]),
            ('async def client(http_auth=("elastic", "real-secret")):\n    return http_auth', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

    def test_auth_tuple_guard_allows_runtime_function_defaults(self):
        safe_examples = (
            'def client(http_auth=("elastic", password_from_store)):\n    return http_auth',
            'def client(*, basic_auth=("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))):\n    return basic_auth',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

    def test_auth_tuple_guard_allows_runtime_password_references(self):
        safe_examples = (
            'Elasticsearch(host, http_auth=(es_tokens["user"], es_tokens["password"]))',
            'Elasticsearch(host, basic_auth=(user, os.environ.get("TCP_ELASTIC_PASSWORD")))',
            'Elasticsearch(host, http_auth=(user, os.getenv("TCP_ELASTIC_PASSWORD")))',
            'http_auth = (user, password)',
            'AUTH = (user, password)\nElasticsearch(host, http_auth=AUTH)',
            'options = {"http_auth": (es_tokens["user"], es_tokens["password"])}',
            'options = {"basic_auth": [user, os.environ.get("TCP_ELASTIC_PASSWORD")]}',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

    def test_python_password_literal_guard_detects_runtime_literals(self):
        hardcoded_examples = (
            'password = "real-secret"',
            'options = {"password": "real-secret"}',
            'options["password"] = "real-secret"',
            'connect(password="real-secret")',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [1])

    def test_python_password_literal_guard_detects_environment_lookup_fallbacks(self):
        hardcoded_examples = (
            'password = os.getenv("TCP_ELASTIC_PASSWORD", "real-secret")',
            'password = os.environ.get("TCP_ELASTIC_PASSWORD", "real-secret")',
            'options = {"password": os.getenv("TCP_ELASTIC_PASSWORD", "real-secret")}',
            'connect(password=os.environ.get("TCP_ELASTIC_PASSWORD", "real-secret"))',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [1])

    def test_python_password_literal_guard_detects_composed_fallbacks(self):
        hardcoded_examples = (
            'password = os.getenv("TCP_ELASTIC_PASSWORD") or "real-secret"',
            'password = "real-" + "secret"',
            'password = "real-secret" if use_fallback else password_from_store',
            '(password := os.getenv("TCP_ELASTIC_PASSWORD") or "real-secret")',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [1])

    def test_python_password_literal_guard_detects_literals_in_call_expressions(self):
        cases = (
            ('password = "real-secret".strip()', [1]),
            ('password = normalize("real-secret")', [1]),
            ('password = config.get("password", "real-secret")', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

    def test_python_password_literal_guard_detects_indexed_containers(self):
        cases = (
            ('password = ("real-secret",)[0]', [1]),
            ('password = ["real-secret"][0]', [1]),
            ('password = {"value": "real-secret"}["value"]', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

    def test_python_password_literal_guard_resolves_only_selected_subscript_value(self):
        safe_source = (
            'es_tokens = {"host": "https://localhost:9200", '
            '"user": "elastic", '
            '"password": os.environ.get("TCP_ELASTIC_PASSWORD")}\n'
            'password = es_tokens["password"]'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

        hardcoded_source = (
            'es_tokens = {"host": "https://localhost:9200", '
            '"user": "elastic", '
            '"password": "real-secret"}\n'
            'password = es_tokens["password"]'
        )
        self.assertEqual(hardcoded_password_literal_lines(hardcoded_source), [1, 2])

    def test_python_password_literal_guard_leaves_dynamic_subscripts_unresolved(self):
        self.assertEqual(
            hardcoded_password_literal_lines(
                'values = {"primary": "real-secret"}\npassword = values[key]'
            ),
            [],
        )

    def test_python_password_literal_guard_detects_augmented_assignments(self):
        cases = (
            ('password = os.getenv("TCP_ELASTIC_PASSWORD")\npassword += "real-secret"', [2]),
            ('settings.password += "real-secret"', [1]),
            ('options["password"] += "real-secret"', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

    def test_python_password_literal_guard_allows_runtime_augmented_assignments(self):
        safe_examples = (
            'password += suffix_from_store',
            'settings.password += suffix_from_store',
            'options["password"] += suffix_from_store',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_detects_function_defaults(self):
        cases = (
            ('def client(password="real-secret"):\n    return password', [1]),
            ('def client(*, password="real-secret"):\n    return password', [1]),
            ('async def client(password="real-secret"):\n    return password', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

    def test_python_password_literal_guard_allows_runtime_function_defaults(self):
        safe_examples = (
            'def client(password=os.getenv("TCP_ELASTIC_PASSWORD")):\n    return password',
            'def client(*, password=password_from_store):\n    return password',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_detects_attribute_targets(self):
        cases = (
            ('settings.password = "real-secret"', [1]),
            ('client.credentials.password = "real-secret"', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

    def test_python_password_literal_guard_detects_fstrings_and_literal_aliases(self):
        cases = (
            ('password = f"real-secret"', [1]),
            ('password = f"real-secret-{suffix}"', [1]),
            (
                'ELASTIC_PASSWORD = "real-secret"\n'
                'options = {"password": ELASTIC_PASSWORD}',
                [2],
            ),
            (
                'FIRST = "real-secret"\n'
                'SECOND = FIRST\n'
                'password = SECOND',
                [3],
            ),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

    def test_python_password_literal_guard_allows_exact_redaction_sentinel_only(self):
        self.assertEqual(
            hardcoded_password_literal_lines('password = "***REDACTED***"'),
            [],
        )
        self.assertEqual(
            hardcoded_password_literal_lines('password = "***REDACTED***-fallback"'),
            [1],
        )

    def test_python_password_literal_guard_allows_runtime_references(self):
        safe_examples = (
            'password = os.environ.get("TCP_ELASTIC_PASSWORD")',
            'password = os.getenv("TCP_ELASTIC_PASSWORD")',
            'password = os.getenv("TCP_ELASTIC_PASSWORD", "")',
            'password = config.get("password")',
            'password = config.get("password", password_from_store)',
            'password = passwords[0]',
            'settings.password = password_from_store',
            'password = f"{password_from_store}"',
            'ELASTIC_PASSWORD = os.environ.get("TCP_ELASTIC_PASSWORD")\npassword = ELASTIC_PASSWORD',
            'password = primary_password or secondary_password',
            'options = {"password": password}',
            'options["password"] = password',
            'connect(password=password)',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_tracked_elasticsearch_surfaces_do_not_embed_credentials(self):
        violations = []
        for path in self._secret_surface_paths():
            text = path.read_text(encoding="utf-8-sig")
            if path.suffix.lower() == ".py":
                for line_number in hardcoded_auth_tuple_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:auth-tuple"
                    )
                if path in RUNTIME_ES_MODULES:
                    for line_number in hardcoded_password_literal_lines(text):
                        violations.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:password-literal"
                        )
                    for line_number in python_comment_password_lines(text):
                        violations.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:password-comment"
                        )
            for line_number, line in enumerate(text.splitlines(), start=1):
                if path not in RUNTIME_ES_MODULES:
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
