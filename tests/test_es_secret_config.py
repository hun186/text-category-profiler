import ast
import io
import os
import re
import runpy
import tokenize
import textwrap
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
ES_RUNTIME_DISCOVERY_ROOTS = (
    REPOSITORY_ROOT / "DatasetConverter",
    REPOSITORY_ROOT / "text_category_profiler",
)
ES_RUNTIME_MARKERS = (
    "elasticsearch",
    "es_tokens",
    "esjob",
    "create_elasticsearch_client",
    "esdataconfigfile",
    "artcluesjobtemplate",
)
TEXT_SECRET_SUFFIXES = {".py", ".ini", ".txt", ".json", ".yml", ".yaml"}

PASSWORD_KEY_RE = re.compile(r"""["\']?password["\']?\s*[:=]\s*""", re.IGNORECASE)
SCALAR_AUTH_KEY_RE = re.compile(
    r"""["\']?(api_key|bearer_auth)["\']?\s*[:=]\s*""",
    re.IGNORECASE,
)
AUTH_TUPLE_KEY_RE = re.compile(
    r"""["\']?(http_auth|basic_auth)["\']?\s*[:=]\s*""",
    re.IGNORECASE,
)
AUTHORIZATION_KEY_RE = re.compile(
    r"""["\']?Authorization["\']?\s*[:=]\s*""",
    re.IGNORECASE,
)
AUTHORIZATION_VALUE_RE = re.compile(
    r"^\s*(ApiKey|Bearer|Basic)\s+(.+?)\s*$",
    re.IGNORECASE,
)
ENROLLMENT_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{20,}={0,2}(?![A-Za-z0-9_-])"
)
URL_USERINFO_RE = re.compile(
    r"""https?://[^\s/"'@:]+:(?P<password>[^\s/"'@]+)@""",
    re.IGNORECASE,
)
ENV_PLACEHOLDER_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
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


def scalar_auth_value_expressions(line):
    """Return scalar-auth value expressions found anywhere in one line."""
    return [
        (match.group(1).lower(), _password_value_expression(line, match.end()))
        for match in SCALAR_AUTH_KEY_RE.finditer(line)
    ]


def auth_tuple_value_expressions(line):
    """Return auth-tuple value expressions found anywhere in one line."""
    return [
        (match.group(1).lower(), _password_value_expression(line, match.end()))
        for match in AUTH_TUPLE_KEY_RE.finditer(line)
    ]


def authorization_value_expressions(line):
    """Return Authorization-header value expressions found anywhere in one line."""
    return [
        _password_value_expression(line, match.end())
        for match in AUTHORIZATION_KEY_RE.finditer(line)
    ]


def _strip_text_scalar(expression):
    value = expression.strip().rstrip(",").strip()
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {'"', "'"}
    ):
        value = value[1:-1].strip()
    return value


def _is_allowed_secret_placeholder(value):
    normalized = _strip_text_scalar(value)
    return bool(
        ENV_PLACEHOLDER_RE.fullmatch(normalized)
        or normalized == REDACTED_PASSWORD_SENTINEL
    )


def text_structured_auth_line_has_secret(line):
    """Return whether a non-Python config line embeds a structured credential."""
    for _name, expression in scalar_auth_value_expressions(line):
        value = _strip_text_scalar(expression)
        if _is_yaml_block_scalar_marker(value):
            continue
        if value and not _is_allowed_secret_placeholder(value):
            return True

    for expression in authorization_value_expressions(line):
        value = _strip_text_scalar(expression)
        if _is_yaml_block_scalar_marker(value):
            continue
        match = AUTHORIZATION_VALUE_RE.match(value)
        if not match:
            continue
        payload = _strip_text_scalar(match.group(2))
        if payload and not _is_allowed_secret_placeholder(payload):
            return True

    for _name, expression in auth_tuple_value_expressions(line):
        value = expression.strip()
        if not value or _is_yaml_block_scalar_marker(value):
            continue

        try:
            parsed = ast.parse(value, mode="eval").body
        except SyntaxError:
            placeholders = re.findall(r"\$\{[^}]+\}", value)
            if placeholders and all(
                _is_allowed_secret_placeholder(token)
                for token in placeholders
            ):
                continue
            return True

        if isinstance(parsed, (ast.Tuple, ast.List)) and len(parsed.elts) >= 2:
            password_node = parsed.elts[1]
            if isinstance(password_node, ast.Constant) and isinstance(
                password_node.value,
                str,
            ):
                if not _is_allowed_secret_placeholder(password_node.value):
                    return True
                continue

        if hardcoded_auth_tuple_lines(f"http_auth={value}"):
            return True

    return False


def _config_scalar_value(line):
    value = line.strip()
    if value.startswith("-"):
        value = value[1:].strip()
    if "#" in value:
        value = value.split("#", 1)[0].rstrip()
    return _strip_text_scalar(value)


def _is_yaml_block_scalar_marker(value):
    return bool(re.fullmatch(r"[>|](?:[+-]?\d?|\d?[+-]?)", value.strip()))


def _yaml_block_scalar_value(lines, index):
    """Return (line number, folded value) for an indented YAML block scalar."""
    key_line = lines[index]
    key_indent = len(key_line) - len(key_line.lstrip())
    parts = []
    first_line = None
    cursor = index + 1

    while cursor < len(lines):
        next_line = lines[cursor]
        stripped = next_line.strip()
        if not stripped:
            cursor += 1
            continue

        indent = len(next_line) - len(next_line.lstrip())
        if indent <= key_indent:
            break

        value = _config_scalar_value(next_line)
        if value:
            if first_line is None:
                first_line = cursor + 1
            parts.append(value)
        cursor += 1

    return first_line, " ".join(parts)


def text_structured_auth_secret_lines(text):
    """Return non-Python config lines containing structured auth credentials."""
    lines = text.splitlines()
    violations = set()

    for index, line in enumerate(lines):
        line_number = index + 1
        if text_structured_auth_line_has_secret(line):
            violations.add(line_number)

        structured_matches = [
            *[(match, "scalar") for match in SCALAR_AUTH_KEY_RE.finditer(line)],
            *[(match, "authorization") for match in AUTHORIZATION_KEY_RE.finditer(line)],
            *[(match, "tuple") for match in AUTH_TUPLE_KEY_RE.finditer(line)],
        ]

        for match, kind in structured_matches:
            expression = _password_value_expression(line, match.end()).strip()

            if _is_yaml_block_scalar_marker(expression):
                credential_line, block_value = _yaml_block_scalar_value(
                    lines,
                    index,
                )
                if credential_line is None or not block_value:
                    continue

                if kind == "scalar":
                    if not _is_allowed_secret_placeholder(block_value):
                        violations.add(credential_line)
                elif kind == "authorization":
                    auth_match = AUTHORIZATION_VALUE_RE.match(block_value)
                    if auth_match:
                        payload = _strip_text_scalar(auth_match.group(2))
                        if (
                            payload
                            and not _is_allowed_secret_placeholder(payload)
                        ):
                            violations.add(credential_line)
                else:
                    synthetic = f"http_auth: {block_value}"
                    if text_structured_auth_line_has_secret(synthetic):
                        violations.add(credential_line)
                continue

            if kind != "tuple" or expression:
                continue

            key_indent = len(line) - len(line.lstrip())
            continuation = []
            cursor = index + 1
            while cursor < len(lines):
                next_line = lines[cursor]
                stripped = next_line.strip()
                if not stripped:
                    cursor += 1
                    continue

                indent = len(next_line) - len(next_line.lstrip())
                is_list_item = stripped.startswith("-")
                if indent <= key_indent and not is_list_item:
                    break

                continuation.append((cursor + 1, _config_scalar_value(next_line)))
                cursor += 1

            scalar_values = [
                (candidate_line, value)
                for candidate_line, value in continuation
                if value
            ]
            if len(scalar_values) < 2:
                continue

            credential_line, credential_value = scalar_values[1]
            if not _is_allowed_secret_placeholder(credential_value):
                violations.add(credential_line)

    return sorted(violations)


def text_url_userinfo_has_secret(text):
    """Return whether URL userinfo contains a literal rather than env placeholder."""
    for match in URL_USERINFO_RE.finditer(text):
        password = match.group("password")
        if not _is_allowed_secret_placeholder(password):
            return True
    return False


def python_comment_scalar_auth_lines(source):
    """Return Python comment lines that embed scalar auth literals."""
    violations = []
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)

    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue

        for _name, expression in scalar_auth_value_expressions(token.string):
            stripped = expression.strip()
            if not stripped:
                continue
            try:
                parsed = ast.parse(stripped, mode="eval").body
            except SyntaxError:
                violations.append(token.start[0])
                continue

            if _hardcoded_comment_scalar_value(parsed):
                violations.append(token.start[0])

    return sorted(set(violations))


def _python_comment_blocks(source):
    """Return contiguous Python comment blocks with their source line numbers."""
    comments = [
        token
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]
    blocks = []
    current = []

    for token in comments:
        if current and token.start[0] != current[-1].start[0] + 1:
            blocks.append(current)
            current = []
        current.append(token)

    if current:
        blocks.append(current)

    return blocks


def _comment_payload(token):
    payload = token.string[1:]
    if payload.startswith(" "):
        payload = payload[1:]
    return payload


def python_comment_structured_auth_lines(source):
    """Return comment lines embedding structured password or auth credentials."""
    violations = []

    for block in _python_comment_blocks(source):
        payloads = [_comment_payload(token) for token in block]
        block_source = textwrap.dedent("\n".join(payloads)).strip()
        if not block_source:
            continue

        try:
            ast.parse(block_source)
        except SyntaxError:
            has_secret = _disabled_payload_text_has_secret(block_source)
        else:
            has_secret = bool(
                hardcoded_password_literal_lines(block_source)
                or hardcoded_auth_tuple_lines(block_source)
                or hardcoded_authorization_header_lines(block_source)
            )

        if has_secret:
            violations.append(block[0].start[0])

    return sorted(set(violations))


AUTH_TUPLE_NAMES = {"http_auth", "basic_auth"}
SINGLE_VALUE_AUTH_NAMES = {"api_key", "bearer_auth"}


def _is_single_auth_target(node):
    if isinstance(node, ast.Name):
        return node.id in SINGLE_VALUE_AUTH_NAMES
    if isinstance(node, ast.Subscript):
        return _literal_string(node.slice) in SINGLE_VALUE_AUTH_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in SINGLE_VALUE_AUTH_NAMES
    return False


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


def _hardcoded_comment_scalar_value(node):
    literal = _literal_string(node)
    if literal is not None:
        return bool(literal and literal != REDACTED_PASSWORD_SENTINEL)

    if _is_environment_lookup_call(node):
        return _environment_lookup_default_node(node) is not None

    if isinstance(node, ast.Name):
        return False

    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"strip", "lstrip", "rstrip", "lower", "upper", "casefold"}
        ):
            return _hardcoded_comment_scalar_value(node.func.value)
        return False

    if isinstance(node, (ast.BoolOp, ast.Tuple, ast.List, ast.Set)):
        values = node.values if isinstance(node, ast.BoolOp) else node.elts
        return any(_hardcoded_comment_scalar_value(value) for value in values)

    if isinstance(node, ast.IfExp):
        return (
            _hardcoded_comment_scalar_value(node.body)
            or _hardcoded_comment_scalar_value(node.orelse)
        )

    if isinstance(node, ast.BinOp):
        return (
            _hardcoded_comment_scalar_value(node.left)
            or _hardcoded_comment_scalar_value(node.right)
        )

    if isinstance(node, ast.JoinedStr):
        return any(
            (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and bool(value.value)
            )
            or (
                isinstance(value, ast.FormattedValue)
                and _hardcoded_comment_scalar_value(value.value)
            )
            for value in node.values
        )

    return False


def _auth_target_key(node):
    """Return a stable key for a supported auth target expression."""
    if not _is_auth_tuple_target(node):
        return None
    if isinstance(node, ast.Name):
        return ("name", node.id)
    if isinstance(node, ast.Attribute):
        return (
            "attribute",
            ast.dump(node.value, include_attributes=False),
            node.attr,
        )
    if isinstance(node, ast.Subscript):
        return (
            "subscript",
            ast.dump(node.value, include_attributes=False),
            _literal_string(node.slice),
        )
    return None


def _is_os_module_expression(
    node,
    bindings=None,
    before_position=None,
    seen_names=None,
):
    seen_names = set() if seen_names is None else set(seen_names)

    if isinstance(node, ast.Name) and node.id == "os":
        return True
    if not isinstance(node, ast.Name) or bindings is None:
        return False

    token = _binding_name_token(node.id, bindings, node)
    if token in seen_names:
        return False

    for resolved in _resolve_bound_nodes(
        node,
        bindings,
        before_position,
        seen_names,
    ):
        if isinstance(resolved, ast.Name) and resolved.id == node.id:
            continue
        if _is_os_module_expression(
            resolved,
            bindings,
            before_position,
            seen_names | {token},
        ):
            return True
    return False


def _is_os_environ_expression(
    node,
    bindings=None,
    before_position=None,
    seen_names=None,
):
    seen_names = set() if seen_names is None else set(seen_names)

    if (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and _is_os_module_expression(
            node.value,
            bindings,
            before_position,
            seen_names,
        )
    ):
        return True

    if not isinstance(node, ast.Name) or bindings is None:
        return False

    token = _binding_name_token(node.id, bindings, node)
    if token in seen_names:
        return False

    for resolved in _resolve_bound_nodes(
        node,
        bindings,
        before_position,
        seen_names,
    ):
        if isinstance(resolved, ast.Name) and resolved.id == node.id:
            continue
        if _is_os_environ_expression(
            resolved,
            bindings,
            before_position,
            seen_names | {token},
        ):
            return True
    return False


def _is_os_getenv_function(
    node,
    bindings=None,
    before_position=None,
    seen_names=None,
):
    seen_names = set() if seen_names is None else set(seen_names)

    if (
        isinstance(node, ast.Attribute)
        and node.attr == "getenv"
        and _is_os_module_expression(
            node.value,
            bindings,
            before_position,
            seen_names,
        )
    ):
        return True

    if not isinstance(node, ast.Name) or bindings is None:
        return False

    token = _binding_name_token(node.id, bindings, node)
    if token in seen_names:
        return False

    for resolved in _resolve_bound_nodes(
        node,
        bindings,
        before_position,
        seen_names,
    ):
        if isinstance(resolved, ast.Name) and resolved.id == node.id:
            continue
        if _is_os_getenv_function(
            resolved,
            bindings,
            before_position,
            seen_names | {token},
        ):
            return True
    return False


def _is_environment_lookup_call(
    node,
    bindings=None,
    before_position=None,
):
    if not isinstance(node, ast.Call):
        return False

    func = node.func
    return (
        _is_os_getenv_function(
            func,
            bindings,
            before_position,
        )
        or (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and _is_os_environ_expression(
                func.value,
                bindings,
                before_position,
            )
        )
    )


def _environment_lookup_default_node(
    node,
    bindings=None,
    before_position=None,
):
    """Return the fallback expression from supported environment lookups."""
    if not _is_environment_lookup_call(
        node,
        bindings,
        before_position,
    ):
        return None

    if len(node.args) >= 2:
        return node.args[1]

    for keyword in node.keywords:
        if keyword.arg == "default":
            return keyword.value

    return None


def _annotate_binding_scopes(tree):
    """Annotate AST nodes with lexical scopes used by credential resolution."""
    module_scope = tree
    scope_parents = {module_scope: None}
    scope_locals = {module_scope: set()}
    scope_globals = {module_scope: set()}
    scope_nonlocals = {module_scope: set()}

    class ScopeVisitor(ast.NodeVisitor):
        def __init__(self):
            self.scope_stack = [module_scope]
            self.control_path = []

        @property
        def current_scope(self):
            return self.scope_stack[-1]

        def _mark(self, node):
            node._binding_scope = self.current_scope
            node._binding_control_path = tuple(self.control_path)

        def _branch_token(self, node, label):
            return (
                type(node).__name__,
                getattr(node, "lineno", 0),
                getattr(node, "col_offset", 0),
                label,
            )

        def _visit_branch(self, owner, label, statements):
            self.control_path.append(self._branch_token(owner, label))
            for statement in statements:
                self.visit(statement)
            self.control_path.pop()

        def _new_scope(self, node, parent_scope):
            scope_parents[node] = parent_scope
            scope_locals[node] = set()
            scope_globals[node] = set()
            scope_nonlocals[node] = set()

        def _function_parent_scope(self):
            parent = self.current_scope
            while isinstance(parent, ast.ClassDef):
                parent = scope_parents[parent]
            return parent

        def _visit_argument_annotations(self, arguments):
            all_args = (
                list(arguments.posonlyargs)
                + list(arguments.args)
                + list(arguments.kwonlyargs)
            )
            for argument in all_args:
                if argument.annotation is not None:
                    self.visit(argument.annotation)
            if arguments.vararg is not None and arguments.vararg.annotation is not None:
                self.visit(arguments.vararg.annotation)
            if arguments.kwarg is not None and arguments.kwarg.annotation is not None:
                self.visit(arguments.kwarg.annotation)

        def _add_function_arguments(self, scope, arguments):
            all_args = (
                list(arguments.posonlyargs)
                + list(arguments.args)
                + list(arguments.kwonlyargs)
            )
            scope_locals[scope].update(argument.arg for argument in all_args)
            if arguments.vararg is not None:
                scope_locals[scope].add(arguments.vararg.arg)
            if arguments.kwarg is not None:
                scope_locals[scope].add(arguments.kwarg.arg)

        def _visit_function(self, node):
            self._mark(node)
            scope_locals[self.current_scope].add(node.name)

            for decorator in node.decorator_list:
                self.visit(decorator)
            self._visit_argument_annotations(node.args)
            for default in node.args.defaults:
                self.visit(default)
            for default in node.args.kw_defaults:
                if default is not None:
                    self.visit(default)
            if node.returns is not None:
                self.visit(node.returns)
            for type_param in getattr(node, "type_params", ()):
                self.visit(type_param)

            self._new_scope(node, self._function_parent_scope())
            self._add_function_arguments(node, node.args)
            self.scope_stack.append(node)
            for statement in node.body:
                self.visit(statement)
            self.scope_stack.pop()

        def visit_FunctionDef(self, node):
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node):
            self._visit_function(node)

        def visit_Lambda(self, node):
            self._mark(node)
            for default in node.args.defaults:
                self.visit(default)
            for default in node.args.kw_defaults:
                if default is not None:
                    self.visit(default)

            self._new_scope(node, self._function_parent_scope())
            self._add_function_arguments(node, node.args)
            self.scope_stack.append(node)
            self.visit(node.body)
            self.scope_stack.pop()

        def visit_ClassDef(self, node):
            self._mark(node)
            scope_locals[self.current_scope].add(node.name)
            for decorator in node.decorator_list:
                self.visit(decorator)
            for base in node.bases:
                self.visit(base)
            for keyword in node.keywords:
                self.visit(keyword.value)
            for type_param in getattr(node, "type_params", ()):
                self.visit(type_param)

            self._new_scope(node, self.current_scope)
            self.scope_stack.append(node)
            for statement in node.body:
                self.visit(statement)
            self.scope_stack.pop()

        def visit_If(self, node):
            self._mark(node)
            self.visit(node.test)
            self._visit_branch(node, "body", node.body)
            self._visit_branch(node, "orelse", node.orelse)

        def _visit_loop(self, node):
            self._mark(node)
            if hasattr(node, "iter"):
                self.visit(node.iter)
            else:
                self.visit(node.test)
            self.control_path.append(self._branch_token(node, "body"))
            if hasattr(node, "target"):
                self.visit(node.target)
            for statement in node.body:
                self.visit(statement)
            self.control_path.pop()
            self._visit_branch(node, "orelse", node.orelse)

        def visit_For(self, node):
            self._visit_loop(node)

        def visit_AsyncFor(self, node):
            self._visit_loop(node)

        def visit_While(self, node):
            self._visit_loop(node)

        def _visit_with(self, node):
            self._mark(node)
            for item in node.items:
                self.visit(item.context_expr)
            self.control_path.append(self._branch_token(node, "body"))
            for item in node.items:
                if item.optional_vars is not None:
                    self.visit(item.optional_vars)
            for statement in node.body:
                self.visit(statement)
            self.control_path.pop()

        def visit_With(self, node):
            self._visit_with(node)

        def visit_AsyncWith(self, node):
            self._visit_with(node)

        def _visit_try(self, node):
            self._mark(node)
            self._visit_branch(node, "body", node.body)
            for index, handler in enumerate(node.handlers):
                self.control_path.append(
                    self._branch_token(node, f"handler-{index}")
                )
                self.visit(handler)
                self.control_path.pop()
            self._visit_branch(node, "orelse", node.orelse)
            for statement in node.finalbody:
                self.visit(statement)

        def visit_Try(self, node):
            self._visit_try(node)

        def visit_TryStar(self, node):
            self._visit_try(node)

        def visit_Match(self, node):
            self._mark(node)
            self.visit(node.subject)
            for index, case in enumerate(node.cases):
                self.control_path.append(
                    self._branch_token(node, f"case-{index}")
                )
                self.visit(case)
                self.control_path.pop()

        def visit_Name(self, node):
            self._mark(node)
            if isinstance(node.ctx, ast.Store):
                scope_locals[self.current_scope].add(node.id)

        def visit_Global(self, node):
            self._mark(node)
            scope_globals[self.current_scope].update(node.names)

        def visit_Nonlocal(self, node):
            self._mark(node)
            scope_nonlocals[self.current_scope].update(node.names)

        def visit_Import(self, node):
            self._mark(node)
            for alias in node.names:
                scope_locals[self.current_scope].add(
                    alias.asname or alias.name.split(".", 1)[0]
                )

        def visit_ImportFrom(self, node):
            self._mark(node)
            for alias in node.names:
                if alias.name != "*":
                    scope_locals[self.current_scope].add(alias.asname or alias.name)

        def generic_visit(self, node):
            self._mark(node)
            super().generic_visit(node)

    ScopeVisitor().visit(tree)
    return {
        "module": module_scope,
        "parents": scope_parents,
        "locals": scope_locals,
        "globals": scope_globals,
        "nonlocals": scope_nonlocals,
    }


def _enclosing_binding_scope(name, lexical_scope, metadata):
    """Return the Python lexical scope that owns one referenced name."""
    module_scope = metadata["module"]
    scope = lexical_scope or module_scope

    if name in metadata["globals"].get(scope, ()):
        return module_scope

    if name in metadata["nonlocals"].get(scope, ()):
        scope = metadata["parents"].get(scope)
        while scope is not None:
            if name in metadata["locals"].get(scope, ()):
                return scope
            scope = metadata["parents"].get(scope)
        return module_scope

    while scope is not None:
        if name in metadata["globals"].get(scope, ()):
            return module_scope
        if name in metadata["locals"].get(scope, ()):
            return scope
        scope = metadata["parents"].get(scope)

    return module_scope


def _assignment_binding_scope(name, lexical_scope, metadata):
    module_scope = metadata["module"]
    scope = lexical_scope or module_scope

    if name in metadata["globals"].get(scope, ()):
        return module_scope

    if name in metadata["nonlocals"].get(scope, ()):
        parent = metadata["parents"].get(scope)
        while parent is not None:
            if name in metadata["locals"].get(parent, ()):
                return parent
            parent = metadata["parents"].get(parent)
        return module_scope

    return scope


def _node_position(node):
    """Return a source-order key that distinguishes statements on one line."""
    return (
        getattr(node, "lineno", 0),
        getattr(node, "col_offset", 0),
    )


def _position_before(node):
    line_number, column_number = _node_position(node)
    return (line_number, column_number - 1)


def _node_control_path(node):
    return tuple(getattr(node, "_binding_control_path", ()))


def _control_path_is_prefix(prefix, path):
    return len(prefix) <= len(path) and path[: len(prefix)] == prefix


def _control_paths_mutually_exclusive(binding_path, use_path):
    """Exclude assignments confined to an opposing if/else or match arm."""
    for binding_step, use_step in zip(binding_path, use_path):
        if binding_step == use_step:
            continue
        if binding_step[:3] != use_step[:3]:
            break
        if (
            binding_step[0] == "If"
            and {binding_step[3], use_step[3]} == {"body", "orelse"}
        ):
            return True
        if (
            binding_step[0] == "Match"
            and binding_step[3].startswith("case-")
            and use_step[3].startswith("case-")
        ):
            return True
        break
    return False


def _reaching_values(candidates, use_node):
    """Return conservative reaching values for one binding at a use site."""
    use_path = _node_control_path(use_node)
    reaching = []

    for _position, value in candidates:
        value_path = _node_control_path(value)
        if _control_paths_mutually_exclusive(value_path, use_path):
            continue
        if _control_path_is_prefix(value_path, use_path):
            # This assignment is unavoidable on the path to this use, so it
            # supersedes earlier values.
            reaching = [value]
        else:
            # A branch-local assignment may or may not execute before a use
            # outside that branch, so keep both possibilities.
            reaching.append(value)

    return reaching


def _name_bindings(tree):
    """Map simple variable names to source-ordered expressions per lexical scope."""
    metadata = _annotate_binding_scopes(tree)
    values = {}

    def capture_eager_expression_names(node, position, lexical_scope):
        """Freeze names evaluated as part of an assigned RHS at write time."""
        if node is None:
            return
        if isinstance(
            node,
            (ast.Lambda, ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp),
        ):
            # A deferred body has its own execution time and possibly scope.
            return
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and getattr(node, "_binding_scope", lexical_scope) is lexical_scope
        ):
            node._alias_captured_at = position
        for child in ast.iter_child_nodes(node):
            capture_eager_expression_names(child, position, lexical_scope)

    def add_binding(target, value, position):
        # Annotation-only statements (e.g. password: str) do not bind a
        # runtime value; their AnnAssign.value is None.
        if value is None:
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            resolved_values = _resolve_bound_nodes(
                value,
                bindings,
                position,
            )
            containers = [
                candidate
                for candidate in resolved_values
                if isinstance(candidate, (ast.Tuple, ast.List))
                and len(candidate.elts) == len(target.elts)
            ]
            for container in containers:
                for child_target, child_value in zip(
                    target.elts,
                    container.elts,
                ):
                    add_binding(child_target, child_value, position)
            return

        if isinstance(target, ast.Starred):
            add_binding(target.value, value, position)
            return

        if not isinstance(target, ast.Name):
            return

        lexical_scope = getattr(target, "_binding_scope", metadata["module"])
        binding_scope = _assignment_binding_scope(
            target.id,
            lexical_scope,
            metadata,
        )
        # Evaluate eager nested expressions (f-strings, joins, formatting,
        # lookups) when the target is assigned, not at a later use. Do not
        # freeze lambda/comprehension bodies that execute in other scopes.
        capture_eager_expression_names(value, position, lexical_scope)
        values.setdefault(binding_scope, {}).setdefault(target.id, []).append(
            (position, value)
        )

    binding_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            (
                ast.Assign,
                ast.AnnAssign,
                ast.AugAssign,
                ast.NamedExpr,
                ast.Import,
                ast.ImportFrom,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
    ]
    binding_nodes.sort(key=_node_position)

    bindings = {
        "values": values,
        "metadata": metadata,
    }

    for node in binding_nodes:
        position = _node_position(node)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                add_binding(target, node.value, position)
        elif isinstance(node, ast.AnnAssign):
            add_binding(node.target, node.value, position)
        elif isinstance(node, ast.NamedExpr):
            add_binding(node.target, node.value, position)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # A named local function is a source-ordered callable binding.
            # Only explicitly transparent functions are later considered
            # credential transformations.
            target = ast.Name(id=node.name, ctx=ast.Store())
            target._binding_scope = getattr(
                node, "_binding_scope", metadata["module"]
            )
            target._binding_control_path = _node_control_path(node)
            add_binding(target, node, position)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", 1)[0]
                if alias.name != "os" and local_name != "str":
                    continue
                target = ast.Name(id=local_name, ctx=ast.Store())
                target._binding_scope = getattr(
                    node,
                    "_binding_scope",
                    metadata["module"],
                )
                target._binding_control_path = _node_control_path(node)
                # A name imported as str shadows the builtin only after the
                # import executes; an opaque sentinel cannot be a transform.
                value = (
                    ast.Name(id="os", ctx=ast.Load())
                    if alias.name == "os"
                    else ast.Constant(value=None)
                )
                add_binding(target, value, position)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                local_name = alias.asname or alias.name
                if alias.name == "*" or not (
                    (node.module == "os" and alias.name in {"getenv", "environ"})
                    or local_name == "str"
                ):
                    continue
                target = ast.Name(id=local_name, ctx=ast.Store())
                target._binding_scope = getattr(
                    node,
                    "_binding_scope",
                    metadata["module"],
                )
                target._binding_control_path = _node_control_path(node)
                value = (
                    ast.Attribute(
                        value=ast.Name(id="os", ctx=ast.Load()),
                        attr=alias.name,
                        ctx=ast.Load(),
                    )
                    if node.module == "os" and alias.name in {"getenv", "environ"}
                    else ast.Constant(value=None)
                )
                add_binding(target, value, position)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            if not isinstance(node.op, ast.Add):
                continue
            previous = _bound_name_value(
                node.target.id,
                bindings,
                _position_before(node),
                set(),
                node.target,
            )
            if previous is None:
                continue
            previous = _resolve_bound_node(
                previous,
                bindings,
                _position_before(node),
            )
            appended = _resolve_bound_node(
                node.value,
                bindings,
                _node_position(node.value),
            )
            if not isinstance(previous, (ast.Tuple, ast.List)):
                continue
            if not isinstance(appended, (ast.Tuple, ast.List)):
                continue
            combined = ast.Tuple(
                elts=[*previous.elts, *appended.elts],
                ctx=ast.Load(),
            )
            combined._binding_scope = getattr(
                node,
                "_binding_scope",
                bindings["metadata"]["module"],
            )
            combined._binding_control_path = _node_control_path(node)
            add_binding(node.target, combined, position)

    return bindings


def _binding_name_token(name, bindings, use_node):
    metadata = bindings["metadata"]
    lexical_scope = getattr(use_node, "_binding_scope", metadata["module"])
    binding_scope = _enclosing_binding_scope(name, lexical_scope, metadata)
    return (binding_scope, name)


def _bound_name_values(name, bindings, before_position, seen_names, use_node):
    token = _binding_name_token(name, bindings, use_node)
    if token in seen_names:
        return []

    # The RHS of an earlier alias assignment denotes the value observed at
    # that assignment, not at the later use of the alias. This also works
    # through alias chains without discarding conservative reaching branches.
    captured_at = getattr(use_node, "_alias_captured_at", None)
    if captured_at is not None:
        before_position = min(before_position, captured_at)

    binding_scope, binding_name = token
    candidates = [
        (position, value)
        for position, value in bindings["values"]
        .get(binding_scope, {})
        .get(binding_name, ())
        if position <= before_position
    ]
    return _reaching_values(candidates, use_node)


def _bound_name_value(name, bindings, before_position, seen_names, use_node):
    values = _bound_name_values(
        name,
        bindings,
        before_position,
        seen_names,
        use_node,
    )
    return values[-1] if values else None


def _resolve_bound_nodes(node, bindings, before_position=None, seen_names=None):
    """Resolve all conservative reaching aliases visible at one use site."""
    seen_names = set() if seen_names is None else set(seen_names)
    before_position = _node_position(node) if before_position is None else before_position

    if not isinstance(node, ast.Name):
        return [node]

    token = _binding_name_token(node.id, bindings, node)
    if token in seen_names:
        return [node]

    bound_values = _bound_name_values(
        node.id,
        bindings,
        before_position,
        seen_names,
        node,
    )
    if not bound_values:
        return [node]

    resolved = []
    for bound in bound_values:
        resolved.extend(
            _resolve_bound_nodes(
                bound,
                bindings,
                before_position,
                seen_names | {token},
            )
        )
    return resolved


def _resolve_bound_node(node, bindings, before_position=None, seen_names=None):
    """Resolve the latest conservative alias value for compatibility helpers."""
    resolved = _resolve_bound_nodes(
        node,
        bindings,
        before_position,
        seen_names,
    )
    return resolved[-1] if resolved else node


def _reaching_auth_binding_values(key, bindings, before_position, use_node):
    metadata = bindings["metadata"]
    lexical_scope = getattr(use_node, "_binding_scope", metadata["module"])

    if key[0] == "name":
        scopes = [
            _enclosing_binding_scope(
                key[1],
                lexical_scope,
                metadata,
            )
        ]
    else:
        scopes = []
        scope = lexical_scope
        while scope is not None:
            scopes.append(scope)
            scope = metadata["parents"].get(scope)

    for scope in scopes:
        candidates = [
            (position, value)
            for position, value in bindings["values"]
            .get(scope, {})
            .get(key, ())
            if position <= before_position
        ]
        if candidates:
            return _reaching_values(candidates, use_node)

    return []


def _latest_auth_binding(key, bindings, before_position, use_node):
    values = _reaching_auth_binding_values(
        key,
        bindings,
        before_position,
        use_node,
    )
    return values[-1] if values else None


def _auth_bindings(tree, name_bindings):
    """Track auth tuple/list values per lexical scope, including += concatenation."""
    metadata = name_bindings["metadata"]
    values = {}
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
    ]
    nodes.sort(key=_node_position)

    bindings = {
        "values": values,
        "metadata": metadata,
    }

    def add_binding(target, value, position):
        key = _auth_target_key(target)
        if key is None:
            return

        lexical_scope = getattr(target, "_binding_scope", metadata["module"])
        if isinstance(target, ast.Name):
            binding_scope = _assignment_binding_scope(
                target.id,
                lexical_scope,
                metadata,
            )
        else:
            binding_scope = lexical_scope

        values.setdefault(binding_scope, {}).setdefault(key, []).append(
            (position, value)
        )

    for node in nodes:
        position = _node_position(node)
        if isinstance(node, ast.Assign):
            value = _resolve_bound_node(
                node.value,
                name_bindings,
                _node_position(node.value),
            )
            for target in node.targets:
                add_binding(target, value, position)
        elif isinstance(node, ast.AnnAssign):
            value = _resolve_bound_node(
                node.value,
                name_bindings,
                _node_position(node.value),
            )
            add_binding(node.target, value, position)
        elif isinstance(node, ast.AugAssign):
            key = _auth_target_key(node.target)
            if key is None or not isinstance(node.op, ast.Add):
                continue
            previous = _latest_auth_binding(
                key,
                bindings,
                _position_before(node),
                node.target,
            )
            appended = _resolve_bound_node(
                node.value,
                name_bindings,
                _node_position(node.value),
            )
            if not isinstance(previous, (ast.Tuple, ast.List)):
                continue
            if not isinstance(appended, (ast.Tuple, ast.List)):
                continue
            combined = ast.Tuple(
                elts=[*previous.elts, *appended.elts],
                ctx=ast.Load(),
            )
            combined._binding_scope = getattr(
                node,
                "_binding_scope",
                bindings["metadata"]["module"],
            )
            combined._binding_control_path = _node_control_path(node)
            add_binding(node.target, combined, position)

    return bindings


def _literal_subscript_key(node):
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, (str, int)) else None


def _resolve_constant_subscript(node, bindings, before_position):
    """Resolve a constant dict/list/tuple subscript to only its selected value."""
    if not isinstance(node, ast.Subscript):
        return None

    key = _literal_subscript_key(node.slice)
    if key is None:
        return None

    container = _resolve_bound_node(node.value, bindings, before_position)

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


def _is_transparent_string_transform_call(node, bindings, before_position):
    """Recognize only callable bindings known to preserve their input string.

    An opaque call's argument could be a vault path, lookup key, or prompt;
    the argument must not be treated as the resulting credential.
    """
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and len(node.args) == 1
        and not node.keywords
    ):
        return False

    metadata = bindings["metadata"]

    def is_unshadowed_builtin_str(name_node):
        if not isinstance(name_node, ast.Name) or name_node.id != "str":
            return False
        scope, _name = _binding_name_token("str", bindings, name_node)
        # At module scope a later assignment/import does not affect an
        # earlier call. Inside a function, a local binding anywhere makes
        # the name local, so an unbound reference is not the builtin.
        if _bound_name_values(
            "str", bindings, before_position, set(), name_node
        ):
            return False
        if scope is not metadata["module"]:
            return "str" not in metadata["locals"].get(scope, ())
        lexical_scope = getattr(name_node, "_binding_scope", metadata["module"])
        if (
            lexical_scope is not metadata["module"]
            and "str" in metadata["locals"].get(scope, ())
        ):
            # Module globals in function bodies are late-bound at runtime.
            return False
        return True

    def is_transparent_body(body, parameter_name):
        if isinstance(body, ast.Name):
            return body.id == parameter_name
        return (
            isinstance(body, ast.Call)
            and isinstance(body.func, ast.Attribute)
            and isinstance(body.func.value, ast.Name)
            and body.func.value.id == parameter_name
            and body.func.attr
            in {"strip", "lstrip", "rstrip", "lower", "upper", "casefold"}
            and not body.args
            and not body.keywords
        )

    for resolved in _resolve_bound_nodes(
        node.func, bindings, before_position
    ):
        if is_unshadowed_builtin_str(resolved):
            return True
        if isinstance(resolved, ast.FunctionDef):
            if resolved.decorator_list or len(resolved.body) != 1:
                continue
            body = resolved.body[0]
            if not isinstance(body, ast.Return):
                continue
            arguments = resolved.args
        elif isinstance(resolved, ast.Lambda):
            body = resolved.body
            arguments = resolved.args
        else:
            continue

        positional = [*arguments.posonlyargs, *arguments.args]
        if (
            len(positional) != 1
            or arguments.vararg is not None
            or arguments.kwarg is not None
            or arguments.kwonlyargs
            or arguments.defaults
            or any(value is not None for value in arguments.kw_defaults)
        ):
            continue
        return_value = body.value if isinstance(body, ast.Return) else body
        if is_transparent_body(return_value, positional[0].arg):
            return True

    return False


def _hardcoded_password_values(node, bindings, before_position, seen_names=None):
    """Return statically embedded password strings from one expression."""
    seen_names = set() if seen_names is None else set(seen_names)

    literal = _literal_string(node)
    if literal:
        return [literal]

    if isinstance(node, ast.Name):
        token = _binding_name_token(node.id, bindings, node)
        if token in seen_names:
            return []
        bound_values = _bound_name_values(
            node.id,
            bindings,
            before_position,
            seen_names,
            node,
        )
        values = []
        for bound in bound_values:
            values.extend(
                _hardcoded_password_values(
                    bound,
                    bindings,
                    before_position,
                    seen_names | {token},
                )
            )
        return values

    environment_default = _environment_lookup_default_node(
        node,
        bindings,
        before_position,
    )
    if environment_default is not None:
        return _hardcoded_password_values(
            environment_default,
            bindings,
            before_position,
            seen_names,
        )

    if isinstance(node, ast.Call):
        if _is_environment_lookup_call(
            node,
            bindings,
            before_position,
        ):
            return []

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
        ):
            # Resolve literal and aliased keys through source-ordered bindings.
            # Never inspect unrelated entries in the receiver mapping.
            selected_keys = _static_string_values(
                node.args[0],
                bindings,
                before_position,
            )
            values = []
            for selected_key in selected_keys:
                for selected in _mapping_key_values(
                    node.func.value,
                    selected_key,
                    bindings,
                    before_position,
                ):
                    values.extend(
                        _hardcoded_password_values(
                            selected,
                            bindings,
                            before_position,
                            seen_names,
                        )
                    )
            if len(node.args) >= 2:
                values.extend(
                    _hardcoded_password_values(
                        node.args[1],
                        bindings,
                        before_position,
                        seen_names,
                    )
                )
            return values

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"strip", "lstrip", "rstrip", "lower", "upper", "casefold"}
        ):
            return _hardcoded_password_values(
                node.func.value,
                bindings,
                before_position,
                seen_names,
            )

        # Only follow an argument when source-visible callable semantics
        # prove it becomes the result (or unshadowed built-in str). A name
        # such as normalize may instead be rebound to secret_manager.read.
        if _is_transparent_string_transform_call(
            node, bindings, before_position
        ):
            return _hardcoded_password_values(
                node.args[0],
                bindings,
                before_position,
                seen_names,
            )

        # Unknown/runtime provider calls may accept lookup identifiers, prompts,
        # paths, or options. Their arguments are not statically returned password
        # values, so scanning them creates false positives.
        return []

    if isinstance(node, ast.Subscript):
        selected = _resolve_constant_subscript(node, bindings, before_position)
        if selected is None:
            return []
        return _hardcoded_password_values(
            selected,
            bindings,
            before_position,
            seen_names,
        )

    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values = []
        for element in node.elts:
            values.extend(
                _hardcoded_password_values(
                    element,
                    bindings,
                    before_position,
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
                    before_position,
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
                        before_position,
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
                    before_position,
                    seen_names,
                )
            )
        return values

    if isinstance(node, ast.IfExp):
        return (
            _hardcoded_password_values(
                node.body,
                bindings,
                before_position,
                seen_names,
            )
            + _hardcoded_password_values(
                node.orelse,
                bindings,
                before_position,
                seen_names,
            )
        )

    if isinstance(node, ast.BinOp):
        return (
            _hardcoded_password_values(
                node.left,
                bindings,
                before_position,
                seen_names,
            )
            + _hardcoded_password_values(
                node.right,
                bindings,
                before_position,
                seen_names,
            )
        )

    if isinstance(node, ast.NamedExpr):
        return _hardcoded_password_values(
            node.value,
            bindings,
            before_position,
            seen_names,
        )

    return []


def _is_authorization_target(node):
    if isinstance(node, ast.Subscript):
        key = _literal_string(node.slice)
        return isinstance(key, str) and key.lower() == "authorization"
    if isinstance(node, ast.Attribute):
        return node.attr.lower() == "authorization"
    return False


def _authorization_target_key(node):
    if not _is_authorization_target(node):
        return None
    if isinstance(node, ast.Attribute):
        return (
            "authorization-attribute",
            ast.dump(node.value, include_attributes=False),
            node.attr.lower(),
        )
    if isinstance(node, ast.Subscript):
        return (
            "authorization-subscript",
            ast.dump(node.value, include_attributes=False),
            str(_literal_string(node.slice)).lower(),
        )
    return None


def _authorization_bindings(tree, name_bindings):
    """Track Authorization target values, including += string assembly."""
    metadata = name_bindings["metadata"]
    values = {}
    bindings = {
        "values": values,
        "metadata": metadata,
    }

    def add_binding(target, value, position):
        key = _authorization_target_key(target)
        if key is None:
            return
        lexical_scope = getattr(target, "_binding_scope", metadata["module"])
        values.setdefault(lexical_scope, {}).setdefault(key, []).append(
            (position, value)
        )

    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
    ]
    nodes.sort(key=_node_position)

    for node in nodes:
        position = _node_position(node)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                add_binding(target, node.value, position)
        elif isinstance(node, ast.AnnAssign):
            add_binding(node.target, node.value, position)
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Add)
        ):
            key = _authorization_target_key(node.target)
            if key is None:
                continue
            previous = _latest_auth_binding(
                key,
                bindings,
                _position_before(node),
                node.target,
            )
            if previous is None:
                continue
            combined = ast.BinOp(
                left=previous,
                op=ast.Add(),
                right=node.value,
            )
            combined._binding_scope = getattr(
                node,
                "_binding_scope",
                metadata["module"],
            )
            combined._binding_control_path = _node_control_path(node)
            add_binding(node.target, combined, position)

    return bindings


def _static_string_values(
    node,
    bindings,
    before_position,
    seen_names=None,
):
    """Return complete string values that can be reconstructed statically."""
    seen_names = set() if seen_names is None else set(seen_names)

    literal = _literal_string(node)
    if literal is not None:
        return [literal]

    if isinstance(node, ast.Name):
        token = _binding_name_token(node.id, bindings, node)
        if token in seen_names:
            return []
        values = []
        for bound in _bound_name_values(
            node.id,
            bindings,
            before_position,
            seen_names,
            node,
        ):
            values.extend(
                _static_string_values(
                    bound,
                    bindings,
                    before_position,
                    seen_names | {token},
                )
            )
        return values

    environment_default = _environment_lookup_default_node(
        node,
        bindings,
        before_position,
    )
    if environment_default is not None:
        return _static_string_values(
            environment_default,
            bindings,
            before_position,
            seen_names,
        )
    if _is_environment_lookup_call(
        node,
        bindings,
        before_position,
    ):
        return []

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    ):
        format_values = _static_string_values(
            node.func.value,
            bindings,
            before_position,
            seen_names,
        )
        if not format_values:
            return []

        positional_combinations = [()]
        for argument in node.args:
            argument_values = _static_string_values(
                argument,
                bindings,
                before_position,
                seen_names,
            )
            if not argument_values:
                return []
            positional_combinations = [
                prefix + (value,)
                for prefix in positional_combinations
                for value in argument_values
            ]

        keyword_combinations = [{}]
        for keyword in node.keywords:
            if keyword.arg is None:
                return []
            keyword_values = _static_string_values(
                keyword.value,
                bindings,
                before_position,
                seen_names,
            )
            if not keyword_values:
                return []
            keyword_combinations = [
                {**prefix, keyword.arg: value}
                for prefix in keyword_combinations
                for value in keyword_values
            ]

        results = []
        for format_value in format_values:
            for positional in positional_combinations:
                for keyword_values in keyword_combinations:
                    try:
                        results.append(
                            format_value.format(
                                *positional,
                                **keyword_values,
                            )
                        )
                    except (IndexError, KeyError, ValueError, AttributeError):
                        continue
        return results

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left_values = _static_string_values(
            node.left,
            bindings,
            before_position,
            seen_names,
        )
        right_values = _static_string_values(
            node.right,
            bindings,
            before_position,
            seen_names,
        )
        if not left_values or not right_values:
            return []
        return [
            left + right
            for left in left_values
            for right in right_values
        ]

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        format_values = _static_string_values(
            node.left,
            bindings,
            before_position,
            seen_names,
        )
        if not format_values:
            return []

        operands = []
        if isinstance(node.right, (ast.Tuple, ast.List)):
            combinations = [()]
            for element in node.right.elts:
                element_values = _static_string_values(
                    element,
                    bindings,
                    before_position,
                    seen_names,
                )
                if not element_values:
                    return []
                combinations = [
                    prefix + (value,)
                    for prefix in combinations
                    for value in element_values
                ]
            operands = combinations
        elif isinstance(node.right, ast.Dict):
            combinations = [{}]
            for key, value in zip(node.right.keys, node.right.values):
                literal_key = _literal_string(key)
                if literal_key is None:
                    return []
                value_candidates = _static_string_values(
                    value,
                    bindings,
                    before_position,
                    seen_names,
                )
                if not value_candidates:
                    return []
                combinations = [
                    {**prefix, literal_key: candidate}
                    for prefix in combinations
                    for candidate in value_candidates
                ]
            operands = combinations
        else:
            operands = _static_string_values(
                node.right,
                bindings,
                before_position,
                seen_names,
            )

        results = []
        for format_value in format_values:
            for operand in operands:
                try:
                    results.append(format_value % operand)
                except (TypeError, ValueError, KeyError):
                    continue
        return results

    if isinstance(node, ast.JoinedStr):
        combinations = [""]
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                part_values = [part.value]
            elif isinstance(part, ast.FormattedValue):
                part_values = _static_string_values(
                    part.value,
                    bindings,
                    before_position,
                    seen_names,
                )
            else:
                return []

            if not part_values:
                return []

            combinations = [
                prefix + value
                for prefix in combinations
                for value in part_values
            ]
        return combinations

    if isinstance(node, ast.BoolOp):
        values = []
        for value in node.values:
            values.extend(
                _static_string_values(
                    value,
                    bindings,
                    before_position,
                    seen_names,
                )
            )
        return values

    if isinstance(node, ast.IfExp):
        return (
            _static_string_values(
                node.body,
                bindings,
                before_position,
                seen_names,
            )
            + _static_string_values(
                node.orelse,
                bindings,
                before_position,
                seen_names,
            )
        )

    if isinstance(node, ast.NamedExpr):
        return _static_string_values(
            node.value,
            bindings,
            before_position,
            seen_names,
        )

    return []


def _authorization_mapping_mutation_values(
    node,
    bindings,
    before_position,
):
    """Return Authorization values written through mapping update/setdefault calls."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    ):
        return []

    if node.func.attr == "setdefault":
        if (
            len(node.args) >= 2
            and isinstance(_literal_string(node.args[0]), str)
            and _literal_string(node.args[0]).lower() == "authorization"
        ):
            return [node.args[1]]
        return []

    if node.func.attr != "update":
        return []

    values = []
    for argument in node.args:
        values.extend(
            _mapping_key_values(
                argument,
                "Authorization",
                bindings,
                before_position,
                case_insensitive=True,
            )
        )

    for keyword in node.keywords:
        if (
            keyword.arg is not None
            and keyword.arg.lower() == "authorization"
        ):
            values.append(keyword.value)
        elif keyword.arg is None:
            values.extend(
                _mapping_key_values(
                    keyword.value,
                    "Authorization",
                    bindings,
                    before_position,
                    case_insensitive=True,
                )
            )

    return values


def hardcoded_url_userinfo_lines(source):
    """Return lines whose statically reconstructed URL embeds userinfo credentials."""
    tree = ast.parse(source)
    bindings = _name_bindings(tree)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    violations = []

    def is_dynamic_format_template_constant(node):
        if not isinstance(node, ast.Constant):
            return False

        parent = parents.get(node)
        if (
            isinstance(parent, ast.Attribute)
            and parent.value is node
            and parent.attr in {"format", "format_map"}
        ):
            grandparent = parents.get(parent)
            return (
                isinstance(grandparent, ast.Call)
                and grandparent.func is parent
            )

        return (
            isinstance(parent, ast.BinOp)
            and parent.left is node
            and isinstance(parent.op, ast.Mod)
        )

    for node in ast.walk(tree):
        is_format_call = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
        )
        if not (
            isinstance(node, (ast.Constant, ast.BinOp, ast.JoinedStr))
            or is_format_call
        ):
            continue
        if is_dynamic_format_template_constant(node):
            continue

        values = _static_string_values(
            node,
            bindings,
            _node_position(node),
        )
        if any(text_url_userinfo_has_secret(value) for value in values):
            violations.append(getattr(node, "lineno", None))

    return sorted(set(line for line in violations if line is not None))


def _hardcoded_authorization_payloads(node, bindings, before_position):
    payloads = []
    for value in _static_string_values(
        node,
        bindings,
        before_position,
    ):
        match = AUTHORIZATION_VALUE_RE.match(value)
        if not match:
            continue
        payload = match.group(2).strip()
        if payload and payload != REDACTED_PASSWORD_SENTINEL:
            payloads.append(payload)
    return payloads


def hardcoded_authorization_header_lines(source):
    """Return lines whose Authorization header embeds a credential."""
    tree = ast.parse(source)
    bindings = _name_bindings(tree)
    authorization_bindings = _authorization_bindings(tree, bindings)
    violations = []

    for node in ast.walk(tree):
        candidates = []

        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                literal_key = _literal_string(key)
                if (
                    isinstance(literal_key, str)
                    and literal_key.lower() == "authorization"
                ):
                    candidates.append(
                        (
                            getattr(value, "lineno", getattr(node, "lineno", None)),
                            _node_position(value),
                            value,
                        )
                    )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "dict"
        ):
            for value in _mapping_key_values(
                node,
                "Authorization",
                bindings,
                _node_position(node),
                case_insensitive=True,
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", getattr(value, "lineno", None)),
                        _node_position(node),
                        value,
                    )
                )
        elif isinstance(node, ast.Call):
            for value in _authorization_mapping_mutation_values(
                node,
                bindings,
                _node_position(node),
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", getattr(value, "lineno", None)),
                        _node_position(node),
                        value,
                    )
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_is_authorization_target(target) for target in targets):
                candidates.append(
                    (
                        getattr(node, "lineno", None),
                        _node_position(node.value),
                        node.value,
                    )
                )
        elif isinstance(node, ast.AugAssign) and _is_authorization_target(node.target):
            key = _authorization_target_key(node.target)
            combined = (
                _latest_auth_binding(
                    key,
                    authorization_bindings,
                    _node_position(node),
                    node.target,
                )
                if key is not None
                else None
            )
            if combined is not None:
                candidates.append(
                    (
                        getattr(node, "lineno", None),
                        _node_position(node),
                        combined,
                    )
                )

        for line_number, use_position, value in candidates:
            if line_number is None:
                continue
            if _hardcoded_authorization_payloads(
                value,
                bindings,
                use_position,
            ):
                violations.append(line_number)

    return sorted(set(violations))


def _single_auth_mapping_call_values(
    node,
    bindings,
    before_position,
):
    """Return scalar auth values written by mapping constructors or mutations."""
    values = []

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
    ):
        for auth_name in SINGLE_VALUE_AUTH_NAMES:
            values.extend(
                _mapping_key_values(
                    node,
                    auth_name,
                    bindings,
                    before_position,
                )
            )
        return values

    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    ):
        return []

    if node.func.attr in {"setdefault", "__setitem__"}:
        if (
            len(node.args) >= 2
            and _literal_string(node.args[0]) in SINGLE_VALUE_AUTH_NAMES
        ):
            return [node.args[1]]
        return []

    if node.func.attr != "update":
        return []

    for auth_name in SINGLE_VALUE_AUTH_NAMES:
        for argument in node.args:
            values.extend(
                _mapping_key_values(
                    argument,
                    auth_name,
                    bindings,
                    before_position,
                )
            )

        for keyword in node.keywords:
            if keyword.arg == auth_name:
                values.append(keyword.value)
            elif keyword.arg is None:
                values.extend(
                    _mapping_key_values(
                        keyword.value,
                        auth_name,
                        bindings,
                        before_position,
                    )
                )

    return values


def _single_auth_mapping_merge_values(
    node,
    bindings,
    before_position,
):
    """Return scalar auth values merged through mapping |= operations."""
    if not (
        isinstance(node, ast.AugAssign)
        and isinstance(node.op, ast.BitOr)
    ):
        return []

    values = []
    for auth_name in SINGLE_VALUE_AUTH_NAMES:
        values.extend(
            _mapping_key_values(
                node.value,
                auth_name,
                bindings,
                before_position,
            )
        )
    return values


def hardcoded_single_auth_lines(source):
    """Return line numbers whose scalar client auth credential is hardcoded."""
    tree = ast.parse(source)
    bindings = _name_bindings(tree)
    violations = []

    for node in ast.walk(tree):
        candidates = []

        if isinstance(node, ast.keyword) and node.arg in SINGLE_VALUE_AUTH_NAMES:
            candidates.append(
                (
                    getattr(node, "lineno", None),
                    _node_position(node.value),
                    node.value,
                )
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_is_single_auth_target(target) for target in targets):
                candidates.append(
                    (
                        getattr(node, "lineno", None),
                        _node_position(node.value),
                        node.value,
                    )
                )
        elif isinstance(node, ast.AugAssign) and _is_single_auth_target(node.target):
            candidates.append(
                (
                    getattr(node, "lineno", None),
                    _node_position(node.value),
                    node.value,
                )
            )
        elif isinstance(node, ast.AugAssign):
            for value in _single_auth_mapping_merge_values(
                node,
                bindings,
                _node_position(node),
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", getattr(value, "lineno", None)),
                        _node_position(node),
                        value,
                    )
                )
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _literal_string(key) in SINGLE_VALUE_AUTH_NAMES:
                    candidates.append(
                        (
                            getattr(value, "lineno", getattr(node, "lineno", None)),
                            _node_position(value),
                            value,
                        )
                    )
        elif isinstance(node, ast.Call):
            for value in _single_auth_mapping_call_values(
                node,
                bindings,
                _node_position(node),
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", getattr(value, "lineno", None)),
                        _node_position(node),
                        value,
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            positional_args = list(node.args.posonlyargs) + list(node.args.args)
            positional_defaults = list(node.args.defaults)
            default_start = len(positional_args) - len(positional_defaults)
            for argument, default in zip(
                positional_args[default_start:],
                positional_defaults,
            ):
                if argument.arg in SINGLE_VALUE_AUTH_NAMES:
                    candidates.append(
                        (
                            getattr(default, "lineno", getattr(node, "lineno", None)),
                            _node_position(default),
                            default,
                        )
                    )

            for argument, default in zip(
                node.args.kwonlyargs,
                node.args.kw_defaults,
            ):
                if argument.arg in SINGLE_VALUE_AUTH_NAMES and default is not None:
                    candidates.append(
                        (
                            getattr(default, "lineno", getattr(node, "lineno", None)),
                            _node_position(default),
                            default,
                        )
                    )

        for line_number, use_position, value in candidates:
            if line_number is None:
                continue

            values = _hardcoded_password_values(
                value,
                bindings,
                use_position,
            )
            if any(
                candidate != REDACTED_PASSWORD_SENTINEL
                for candidate in values
            ):
                violations.append(line_number)

    return sorted(set(violations))


def _normalized_auth_sequences(
    node,
    bindings,
    before_position,
    seen_names=None,
):
    """Return statically constructible tuple/list auth sequences."""
    seen_names = set() if seen_names is None else set(seen_names)

    if isinstance(node, ast.Name):
        token = _binding_name_token(node.id, bindings, node)
        if token in seen_names:
            return []
        resolved = []
        for bound in _bound_name_values(
            node.id,
            bindings,
            before_position,
            seen_names,
            node,
        ):
            resolved.extend(
                _normalized_auth_sequences(
                    bound,
                    bindings,
                    before_position,
                    seen_names | {token},
                )
            )
        return resolved

    if isinstance(node, (ast.Tuple, ast.List)):
        return [node]

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left_sequences = _normalized_auth_sequences(
            node.left,
            bindings,
            before_position,
            seen_names,
        )
        right_sequences = _normalized_auth_sequences(
            node.right,
            bindings,
            before_position,
            seen_names,
        )
        combined = []
        for left in left_sequences:
            for right in right_sequences:
                sequence = ast.Tuple(
                    elts=[*left.elts, *right.elts],
                    ctx=ast.Load(),
                )
                sequence._binding_scope = getattr(
                    node,
                    "_binding_scope",
                    bindings["metadata"]["module"],
                )
                sequence._binding_control_path = _node_control_path(node)
                combined.append(sequence)
        return combined

    return []


def hardcoded_auth_tuple_lines(source):
    """Return line numbers whose auth tuple contains a hardcoded password."""
    tree = ast.parse(source)
    bindings = _name_bindings(tree)
    auth_bindings = _auth_bindings(tree, bindings)
    violations = []

    for node in ast.walk(tree):
        candidates = []

        if isinstance(node, ast.keyword) and node.arg in AUTH_TUPLE_NAMES:
            candidates.append(
                (
                    getattr(node, "lineno", None),
                    _node_position(node.value),
                    node.value,
                )
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_is_auth_tuple_target(target) for target in targets):
                candidates.append(
                    (
                        getattr(node, "lineno", None),
                        _node_position(node.value),
                        node.value,
                    )
                )
        elif isinstance(node, ast.AugAssign) and _is_auth_tuple_target(node.target):
            line_number = getattr(node, "lineno", None)
            key = _auth_target_key(node.target)
            if line_number is not None and key is not None:
                combined = _latest_auth_binding(
                    key,
                    auth_bindings,
                    _node_position(node),
                    node.target,
                )
                if combined is not None:
                    candidates.append(
                        (
                            line_number,
                            _node_position(node.value),
                            combined,
                        )
                    )
        elif isinstance(node, ast.AugAssign):
            for value in _auth_tuple_mapping_merge_values(
                node,
                bindings,
                _node_position(node),
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", getattr(value, "lineno", None)),
                        _node_position(node),
                        value,
                    )
                )
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _literal_string(key) in AUTH_TUPLE_NAMES:
                    candidates.append(
                        (
                            getattr(value, "lineno", getattr(node, "lineno", None)),
                            _node_position(value),
                            value,
                        )
                    )
        elif isinstance(node, ast.Call):
            for value in _auth_tuple_mapping_call_values(
                node,
                bindings,
                _node_position(node),
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", getattr(value, "lineno", None)),
                        _node_position(node),
                        value,
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            positional_args = list(node.args.posonlyargs) + list(node.args.args)
            positional_defaults = list(node.args.defaults)
            default_start = len(positional_args) - len(positional_defaults)
            for argument, default in zip(
                positional_args[default_start:],
                positional_defaults,
            ):
                if argument.arg in AUTH_TUPLE_NAMES:
                    candidates.append(
                        (
                            getattr(default, "lineno", getattr(node, "lineno", None)),
                            _node_position(default),
                            default,
                        )
                    )

            for argument, default in zip(
                node.args.kwonlyargs,
                node.args.kw_defaults,
            ):
                if argument.arg in AUTH_TUPLE_NAMES and default is not None:
                    candidates.append(
                        (
                            getattr(default, "lineno", getattr(node, "lineno", None)),
                            _node_position(default),
                            default,
                        )
                    )

        for line_number, use_position, value in candidates:
            if line_number is None:
                continue

            resolved_values = _resolve_bound_nodes(
                value,
                bindings,
                use_position,
            )
            expanded_values = []

            for resolved_value in resolved_values:
                expanded_values.extend(
                    _normalized_auth_sequences(
                        resolved_value,
                        bindings,
                        use_position,
                    )
                )

                key = _auth_target_key(resolved_value)
                if key is not None:
                    for auth_value in _reaching_auth_binding_values(
                        key,
                        auth_bindings,
                        use_position,
                        resolved_value,
                    ):
                        expanded_values.extend(
                            _normalized_auth_sequences(
                                auth_value,
                                bindings,
                                use_position,
                            )
                        )

            for resolved_value in expanded_values:
                if len(resolved_value.elts) < 2:
                    continue

                passwords = _hardcoded_password_values(
                    resolved_value.elts[1],
                    bindings,
                    use_position,
                )
                if any(
                    password != REDACTED_PASSWORD_SENTINEL
                    for password in passwords
                ):
                    violations.append(line_number)
                    break

    return sorted(set(violations))


def _mapping_key_values(
    mapping,
    key_name,
    bindings=None,
    before_position=None,
    seen_nodes=None,
    case_insensitive=False,
):
    """Return values for one literal mapping key, resolving simple aliases."""
    seen_nodes = set() if seen_nodes is None else set(seen_nodes)
    marker = id(mapping)
    if marker in seen_nodes:
        return []
    seen_nodes.add(marker)

    candidates = [mapping]
    if bindings is not None and isinstance(mapping, ast.Name):
        candidates = _resolve_bound_nodes(
            mapping,
            bindings,
            before_position,
        )

    def key_matches(candidate_key):
        literal = _literal_string(candidate_key)
        if not isinstance(literal, str):
            return literal == key_name
        if case_insensitive:
            return literal.lower() == str(key_name).lower()
        return literal == key_name

    def keyword_matches(keyword_name):
        if keyword_name is None:
            return False
        if case_insensitive:
            return keyword_name.lower() == str(key_name).lower()
        return keyword_name == key_name

    values = []
    for candidate in candidates:
        if isinstance(candidate, ast.Dict):
            for key, value in zip(candidate.keys, candidate.values):
                if key_matches(key):
                    values.append(value)
        elif isinstance(candidate, (ast.List, ast.Tuple, ast.Set)):
            for element in candidate.elts:
                pair_candidates = [element]
                if bindings is not None and isinstance(element, ast.Name):
                    pair_candidates = _resolve_bound_nodes(
                        element,
                        bindings,
                        before_position,
                    )
                for pair in pair_candidates:
                    if (
                        isinstance(pair, (ast.Tuple, ast.List))
                        and len(pair.elts) >= 2
                        and key_matches(pair.elts[0])
                    ):
                        values.append(pair.elts[1])
        elif (
            isinstance(candidate, ast.Call)
            and isinstance(candidate.func, ast.Name)
            and candidate.func.id == "dict"
        ):
            for argument in candidate.args:
                values.extend(
                    _mapping_key_values(
                        argument,
                        key_name,
                        bindings,
                        before_position,
                        seen_nodes,
                        case_insensitive,
                    )
                )
            for keyword in candidate.keywords:
                if keyword_matches(keyword.arg):
                    values.append(keyword.value)
                elif keyword.arg is None:
                    values.extend(
                        _mapping_key_values(
                            keyword.value,
                            key_name,
                            bindings,
                            before_position,
                            seen_nodes,
                            case_insensitive,
                        )
                    )
        elif isinstance(candidate, ast.Name) and bindings is not None:
            values.extend(
                _mapping_key_values(
                    candidate,
                    key_name,
                    bindings,
                    before_position,
                    seen_nodes,
                    case_insensitive,
                )
            )

    return values


def _auth_tuple_mapping_call_values(
    node,
    bindings,
    before_position,
):
    """Return auth tuple values written by mapping constructors or mutations."""
    values = []

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
    ):
        for auth_name in AUTH_TUPLE_NAMES:
            values.extend(
                _mapping_key_values(
                    node,
                    auth_name,
                    bindings,
                    before_position,
                )
            )
        return values

    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    ):
        return []

    if node.func.attr in {"setdefault", "__setitem__"}:
        if (
            len(node.args) >= 2
            and _literal_string(node.args[0]) in AUTH_TUPLE_NAMES
        ):
            return [node.args[1]]
        return []

    if node.func.attr != "update":
        return []

    for auth_name in AUTH_TUPLE_NAMES:
        for argument in node.args:
            values.extend(
                _mapping_key_values(
                    argument,
                    auth_name,
                    bindings,
                    before_position,
                )
            )
        for keyword in node.keywords:
            if keyword.arg == auth_name:
                values.append(keyword.value)
            elif keyword.arg is None:
                values.extend(
                    _mapping_key_values(
                        keyword.value,
                        auth_name,
                        bindings,
                        before_position,
                    )
                )

    return values


def _auth_tuple_mapping_merge_values(
    node,
    bindings,
    before_position,
):
    """Return auth tuple values merged through mapping |= operations."""
    if not (
        isinstance(node, ast.AugAssign)
        and isinstance(node.op, ast.BitOr)
    ):
        return []

    values = []
    for auth_name in AUTH_TUPLE_NAMES:
        values.extend(
            _mapping_key_values(
                node.value,
                auth_name,
                bindings,
                before_position,
            )
        )
    return values


def _password_environment_update_values(
    node,
    bindings=None,
    before_position=None,
):
    """Return TCP_ELASTIC_PASSWORD values written through os.environ mutations."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and _is_os_environ_expression(
            node.func.value,
            bindings,
            before_position,
        )
    ):
        return []

    if node.func.attr in {"setdefault", "__setitem__"}:
        if (
            len(node.args) >= 2
            and _literal_string(node.args[0]) == "TCP_ELASTIC_PASSWORD"
        ):
            return [node.args[1]]
        return []

    if node.func.attr != "update":
        return []

    values = []

    for argument in node.args:
        values.extend(
            _mapping_key_values(
                argument,
                "TCP_ELASTIC_PASSWORD",
                bindings,
                before_position,
            )
        )

    for keyword in node.keywords:
        if keyword.arg == "TCP_ELASTIC_PASSWORD":
            values.append(keyword.value)
        elif keyword.arg is None:
            values.extend(
                _mapping_key_values(
                    keyword.value,
                    "TCP_ELASTIC_PASSWORD",
                    bindings,
                    before_position,
                )
            )

    return values


def _password_environment_merge_values(
    node,
    bindings=None,
    before_position=None,
):
    """Return TCP_ELASTIC_PASSWORD values merged through os.environ |= mapping."""
    if not (
        isinstance(node, ast.AugAssign)
        and isinstance(node.op, ast.BitOr)
        and _is_os_environ_expression(
            node.target,
            bindings,
            before_position,
        )
    ):
        return []

    return _mapping_key_values(
        node.value,
        "TCP_ELASTIC_PASSWORD",
        bindings,
        before_position,
    )


def _is_password_environment_target(
    node,
    bindings=None,
    before_position=None,
):
    if not isinstance(node, ast.Subscript):
        return False
    if _literal_string(node.slice) != "TCP_ELASTIC_PASSWORD":
        return False
    return _is_os_environ_expression(
        node.value,
        bindings,
        before_position,
    )


def _is_password_target(
    node,
    bindings=None,
    before_position=None,
):
    if isinstance(node, ast.Name):
        return node.id == "password"
    if isinstance(node, ast.Subscript):
        return (
            _literal_string(node.slice) == "password"
            or _is_password_environment_target(
                node,
                bindings,
                before_position,
            )
        )
    if isinstance(node, ast.Attribute):
        return node.attr == "password"
    return False


def _password_mapping_call_values(
    node,
    bindings,
    before_position,
):
    """Return password values written by generic mapping constructors or mutations."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
    ):
        return _mapping_key_values(
            node,
            "password",
            bindings,
            before_position,
        )

    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    ):
        return []

    if node.func.attr in {"setdefault", "__setitem__"}:
        if (
            len(node.args) >= 2
            and _literal_string(node.args[0]) == "password"
        ):
            return [node.args[1]]
        return []

    if node.func.attr != "update":
        return []

    values = []
    for argument in node.args:
        values.extend(
            _mapping_key_values(
                argument,
                "password",
                bindings,
                before_position,
            )
        )

    for keyword in node.keywords:
        if keyword.arg == "password":
            values.append(keyword.value)
        elif keyword.arg is None:
            values.extend(
                _mapping_key_values(
                    keyword.value,
                    "password",
                    bindings,
                    before_position,
                )
            )

    return values


def _password_mapping_merge_values(
    node,
    bindings,
    before_position,
):
    """Return password values merged through generic mapping |= operations."""
    if not (
        isinstance(node, ast.AugAssign)
        and isinstance(node.op, ast.BitOr)
    ):
        return []

    return _mapping_key_values(
        node.value,
        "password",
        bindings,
        before_position,
    )


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
            if any(
                _is_password_target(
                    target,
                    bindings,
                    _node_position(node),
                )
                for target in targets
            ):
                candidates.append((getattr(node, "lineno", None), node.value))
        elif (
            isinstance(node, ast.NamedExpr)
            and _is_password_target(
                node.target,
                bindings,
                _node_position(node),
            )
        ):
            candidates.append((getattr(node, "lineno", None), node.value))
        elif (
            isinstance(node, ast.AugAssign)
            and _is_password_target(
                node.target,
                bindings,
                _node_position(node),
            )
        ):
            candidates.append((getattr(node, "lineno", None), node.value))
        elif isinstance(node, ast.AugAssign):
            merge_values = []
            merge_values.extend(
                _password_environment_merge_values(
                    node,
                    bindings,
                    _node_position(node),
                )
            )
            merge_values.extend(
                _password_mapping_merge_values(
                    node,
                    bindings,
                    _node_position(node),
                )
            )
            for value in merge_values:
                candidates.append(
                    (
                        getattr(node, "lineno", getattr(value, "lineno", None)),
                        value,
                    )
                )
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _literal_string(key) == "password":
                    candidates.append((getattr(value, "lineno", getattr(node, "lineno", None)), value))
        elif isinstance(node, ast.Call):
            call_values = []
            call_values.extend(
                _password_environment_update_values(
                    node,
                    bindings,
                    _node_position(node),
                )
            )
            call_values.extend(
                _password_mapping_call_values(
                    node,
                    bindings,
                    _node_position(node),
                )
            )
            for value in call_values:
                candidates.append(
                    (
                        getattr(node, "lineno", getattr(value, "lineno", None)),
                        value,
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
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
                _node_position(value),
            )
            if any(
                password != REDACTED_PASSWORD_SENTINEL
                for password in passwords
            ):
                violations.append(line_number)

    return sorted(set(line for line in violations if line is not None))


def _disabled_payload_text_has_secret(payload):
    """Inspect syntax-error fallback text for credential-bearing mapping fragments."""
    for line in payload.splitlines():
        if any(
            expression not in ALLOWED_PASSWORD_EXPRESSIONS
            for expression in password_value_expressions(line)
        ):
            return True

        for _name, expression in scalar_auth_value_expressions(line):
            stripped = expression.strip()
            if not stripped:
                continue
            try:
                parsed = ast.parse(stripped, mode="eval").body
            except SyntaxError:
                continue
            if _hardcoded_comment_scalar_value(parsed):
                return True

        for name, expression in auth_tuple_value_expressions(line):
            stripped = expression.strip()
            if not stripped:
                continue
            try:
                if hardcoded_auth_tuple_lines(f"{name}={stripped}"):
                    return True
            except SyntaxError:
                continue

        for expression in authorization_value_expressions(line):
            stripped = expression.strip()
            if not stripped:
                continue
            try:
                snippet = f'headers={{"Authorization": {stripped}}}'
                if hardcoded_authorization_header_lines(snippet):
                    return True
            except SyntaxError:
                continue

    return False


def python_disabled_code_secret_lines(source):
    """Return standalone string-block lines that contain disabled secret-bearing code."""
    tree = ast.parse(source)
    violations = []

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue

        payload = textwrap.dedent(node.value.value).strip()
        if not payload:
            continue

        parseable_snippets = []
        fallback_text_has_secret = False
        try:
            ast.parse(payload)
        except SyntaxError:
            fallback_text_has_secret = _disabled_payload_text_has_secret(payload)
            for line in payload.splitlines():
                snippet = line.strip()
                if not snippet:
                    continue
                try:
                    ast.parse(snippet)
                except SyntaxError:
                    continue
                parseable_snippets.append(snippet)
        else:
            parseable_snippets.append(payload)

        has_secret = fallback_text_has_secret
        for snippet in parseable_snippets:
            if has_secret:
                break
            if (
                hardcoded_password_literal_lines(snippet)
                or hardcoded_auth_tuple_lines(snippet)
                or hardcoded_single_auth_lines(snippet)
                or hardcoded_authorization_header_lines(snippet)
                or python_comment_password_lines(snippet)
                or python_comment_scalar_auth_lines(snippet)
                or python_comment_structured_auth_lines(snippet)
            ):
                has_secret = True
                break

        if has_secret:
            violations.append(getattr(node, "lineno", None))

    return sorted(set(line for line in violations if line is not None))


class ElasticsearchSecretConfigTests(unittest.TestCase):
    def _load_password(self, path, mapping_name):
        namespace = runpy.run_path(str(path))
        return namespace[mapping_name]["es_tokens"]["password"]

    def _runtime_es_module_paths(self):
        paths = set(RUNTIME_ES_MODULES)

        for root in ES_RUNTIME_DISCOVERY_ROOTS:
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                if not path.is_file():
                    continue
                source = path.read_text(
                    encoding="utf-8-sig",
                    errors="ignore",
                ).lower()
                if any(marker in source for marker in ES_RUNTIME_MARKERS):
                    paths.add(path)

        return sorted(paths)

    def _secret_surface_paths(self):
        paths = {path for path, _ in CONFIGS}
        paths.update(self._runtime_es_module_paths())
        paths.update(
            path
            for path in ELASTICSEARCH_SAMPLE_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in TEXT_SECRET_SUFFIXES
        )
        return sorted(paths)

    def test_secret_surface_paths_include_runtime_elasticsearch_modules(self):
        surfaces = set(self._secret_surface_paths())
        runtime_modules = set(self._runtime_es_module_paths())
        self.assertTrue(set(RUNTIME_ES_MODULES).issubset(surfaces))
        self.assertTrue(set(RUNTIME_ES_MODULES).issubset(runtime_modules))
        for path in RUNTIME_ES_MODULES:
            with self.subTest(path=path):
                self.assertTrue(path.is_file())

    def test_runtime_discovery_includes_elasticsearch_consumers(self):
        runtime_modules = set(self._runtime_es_module_paths())
        expected_consumers = {
            REPOSITORY_ROOT / "DatasetConverter" / "DataConverter.py",
            REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py",
        }
        self.assertTrue(expected_consumers.issubset(runtime_modules))
        for path in expected_consumers:
            with self.subTest(path=path):
                self.assertTrue(path.is_file())

    def test_secret_surface_paths_include_yaml_elasticsearch_samples(self):
        yaml_paths = [
            path
            for path in self._secret_surface_paths()
            if path.parent == ELASTICSEARCH_SAMPLE_ROOT
            and path.suffix.lower() in {".yml", ".yaml"}
        ]
        expected_yaml = ELASTICSEARCH_SAMPLE_ROOT / "elasticsearch.yml"
        if expected_yaml.is_file():
            self.assertIn(expected_yaml, yaml_paths)

    def test_secret_surface_paths_include_python_elasticsearch_samples(self):
        sample_python_paths = [
            path
            for path in self._secret_surface_paths()
            if path.parent == ELASTICSEARCH_SAMPLE_ROOT
            and path.suffix.lower() == ".py"
        ]
        self.assertTrue(sample_python_paths)

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

    def test_python_url_userinfo_guard_reconstructs_composed_credentials(self):
        hardcoded_examples = (
            (
                'ES_PASSWORD = "hardcoded-secret"\n'
                'host = "https://elastic:" + ES_PASSWORD + "@localhost:9200"',
                [2],
            ),
            (
                'PREFIX = "https://elastic:"\n'
                'ES_PASSWORD = "hardcoded-secret"\n'
                'host = PREFIX + ES_PASSWORD + "@localhost:9200"',
                [3],
            ),
            (
                'ES_PASSWORD = "hardcoded-secret"\n'
                'host = f"https://elastic:{ES_PASSWORD}@localhost:9200"',
                [2],
            ),
            (
                'ES_PASSWORD = "hardcoded-secret"\n'
                'host = "https://elastic:{}@localhost:9200".format(ES_PASSWORD)',
                [2],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_url_userinfo_lines(source),
                    expected,
                )

    def test_python_url_userinfo_guard_detects_implicit_literal_concatenation(self):
        source = (
            'host = (\n'
            '    "https://elastic:"\n'
            '    "hardcoded-secret@localhost:9200"\n'
            ')'
        )
        self.assertEqual(hardcoded_url_userinfo_lines(source), [2])

    def test_python_url_userinfo_guard_allows_noncredential_string_constants(self):
        safe_examples = (
            'host = ("https://localhost:" "9200")',
            'message = "elastic:hardcoded-secret@localhost"',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_url_userinfo_lines(source), [])

    def test_python_url_userinfo_guard_skips_dynamic_format_templates(self):
        safe_examples = (
            (
                'ES_PASSWORD = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                'host = "https://elastic:{}@localhost:9200".format(ES_PASSWORD)'
            ),
            (
                'ES_PASSWORD = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                'host = "https://elastic:%s@localhost:9200" % ES_PASSWORD'
            ),
            (
                'values = {"password": password_from_store}\n'
                'host = "https://elastic:{password}@localhost:9200".format_map(values)'
            ),
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_url_userinfo_lines(source), [])

    def test_python_url_userinfo_guard_allows_runtime_credentials(self):
        safe_examples = (
            (
                'ES_PASSWORD = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                'host = "https://elastic:" + ES_PASSWORD + "@localhost:9200"'
            ),
            'host = f"https://elastic:{password_from_store}@localhost:9200"',
            (
                'ES_PASSWORD = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                'host = "https://elastic:{}@localhost:9200".format(ES_PASSWORD)'
            ),
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_url_userinfo_lines(source), [])

    def test_text_structured_auth_guard_detects_non_python_credentials(self):
        hardcoded_lines = (
            'api_key: hardcoded-api-key-value',
            'bearer_auth = hardcoded-bearer-token',
            'Authorization: Bearer hardcoded-token',
            'Authorization = "ApiKey hardcoded-token"',
            'http_auth: ("elastic", "hardcoded-secret")',
            'basic_auth = ["elastic", "hardcoded-secret"]',
        )
        for line in hardcoded_lines:
            with self.subTest(line=line):
                self.assertTrue(text_structured_auth_line_has_secret(line))

    def test_text_structured_auth_guard_allows_environment_placeholders(self):
        safe_lines = (
            'api_key: ${TCP_ES_API_KEY}',
            'bearer_auth = ${TCP_ES_BEARER_TOKEN}',
            'Authorization: Bearer ${TCP_ES_BEARER_TOKEN}',
            'Authorization = "ApiKey ${TCP_ES_API_KEY}"',
            'http_auth: ("elastic", "${TCP_ELASTIC_PASSWORD}")',
        )
        for line in safe_lines:
            with self.subTest(line=line):
                self.assertFalse(text_structured_auth_line_has_secret(line))

    def test_text_structured_auth_guard_detects_multiline_auth_blocks(self):
        hardcoded_examples = (
            (
                'http_auth:\n'
                '  - elastic\n'
                '  - hardcoded-secret',
                [3],
            ),
            (
                'basic_auth:\n'
                '  - "elastic"\n'
                '  - "hardcoded-secret"',
                [3],
            ),
        )
        for text, expected in hardcoded_examples:
            with self.subTest(text=text):
                self.assertEqual(text_structured_auth_secret_lines(text), expected)

    def test_text_structured_auth_line_guard_skips_yaml_block_markers(self):
        safe_markers = (
            'api_key: >',
            'bearer_auth: |-',
            'Authorization: >-',
            'http_auth: |2',
            'basic_auth: >+',
        )
        for line in safe_markers:
            with self.subTest(line=line):
                self.assertFalse(text_structured_auth_line_has_secret(line))

    def test_text_structured_auth_guard_detects_yaml_block_scalars(self):
        hardcoded_examples = (
            (
                'Authorization: >-\n'
                '  Bearer hardcoded-token',
                [2],
            ),
            (
                'Authorization: |\n'
                '  ApiKey hardcoded-token',
                [2],
            ),
            (
                'api_key: >\n'
                '  hardcoded-api-key-value',
                [2],
            ),
            (
                'http_auth: >-\n'
                '  ("elastic", "hardcoded-secret")',
                [2],
            ),
        )
        for text, expected in hardcoded_examples:
            with self.subTest(text=text):
                self.assertEqual(text_structured_auth_secret_lines(text), expected)

    def test_text_structured_auth_guard_allows_yaml_block_scalar_placeholders(self):
        safe_examples = (
            (
                'Authorization: >-\n'
                '  Bearer ${TCP_ES_BEARER_TOKEN}'
            ),
            (
                'api_key: |\n'
                '  ${TCP_ES_API_KEY}'
            ),
            (
                'http_auth: >-\n'
                '  ("elastic", "${TCP_ELASTIC_PASSWORD}")'
            ),
        )
        for text in safe_examples:
            with self.subTest(text=text):
                self.assertEqual(text_structured_auth_secret_lines(text), [])

    def test_text_structured_auth_guard_allows_multiline_placeholders(self):
        safe_examples = (
            (
                'http_auth:\n'
                '  - elastic\n'
                '  - ${TCP_ELASTIC_PASSWORD}'
            ),
            (
                'basic_auth:\n'
                '  - "elastic"\n'
                '  - "${TCP_ELASTIC_PASSWORD}"'
            ),
        )
        for text in safe_examples:
            with self.subTest(text=text):
                self.assertEqual(text_structured_auth_secret_lines(text), [])

    def test_text_url_userinfo_guard_allows_environment_placeholders(self):
        self.assertFalse(
            text_url_userinfo_has_secret(
                'url: https://elastic:${TCP_ELASTIC_PASSWORD}@localhost:9200'
            )
        )
        self.assertTrue(
            text_url_userinfo_has_secret(
                'url: https://elastic:hardcoded-secret@localhost:9200'
            )
        )

    def test_python_disabled_code_guard_detects_secret_bearing_blocks(self):
        hardcoded_examples = (
            "'''password = \"hardcoded-secret\"'''",
            "'''http_auth=(\"elastic\", \"hardcoded-secret\")'''",
            "'''api_key = \"hardcoded-api-key-value\"'''",
            "'''headers={\"Authorization\": \"Bearer hardcoded-token\"}'''",
            (
                "'''\n"
                "AUTH = (\"elastic\", \"hardcoded-secret\")\n"
                "Elasticsearch(host, http_auth=AUTH)\n"
                "'''"
            ),
            (
                "'''\n"
                "setup notes:\n"
                "options = {\n"
                "    \"password\": \"hardcoded-secret\",\n"
                "}\n"
                "'''"
            ),
            (
                "'''\n"
                "setup notes:\n"
                "options = {\n"
                "    \"http_auth\": (\"elastic\", \"hardcoded-secret\"),\n"
                "}\n"
                "'''"
            ),
            (
                "'''\n"
                "setup notes:\n"
                "headers = {\n"
                "    \"Authorization\": \"Bearer hardcoded-token\",\n"
                "}\n"
                "'''"
            ),
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(python_disabled_code_secret_lines(source), [1])

    def test_python_disabled_code_guard_allows_safe_or_data_strings(self):
        safe_examples = (
            "'''password = password_from_store'''",
            "'''http_auth=(\"elastic\", os.getenv(\"TCP_ELASTIC_PASSWORD\"))'''",
            "'''headers={\"Authorization\": f\"Bearer {token}\"}'''",
            (
                "'''\n"
                "setup notes:\n"
                "options = {\n"
                "    \"password\": os.environ.get(\"TCP_ELASTIC_PASSWORD\"),\n"
                "    \"http_auth\": (\"elastic\", password_from_store),\n"
                "}\n"
                "'''"
            ),
            'disabled_text = \'\'\'password = "hardcoded-secret"\'\'\'',
            "'''ordinary documentation text'''",
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(python_disabled_code_secret_lines(source), [])

    def test_python_comment_password_guard_detects_commented_literals(self):
        hardcoded_examples = (
            '# "password": "embedded-value"',
            'value = 1  # password = "embedded-value"',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(python_comment_password_lines(source), [1])

    def test_python_comment_structured_auth_guard_detects_password_subscripts(self):
        hardcoded_examples = (
            '# options["password"] = "hardcoded-secret"',
            '# SECRET = "hardcoded-secret"\n# es_tokens["password"] = SECRET',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    python_comment_structured_auth_lines(source),
                    [1],
                )

    def test_python_comment_structured_auth_guard_allows_runtime_password_subscripts(self):
        safe_examples = (
            '# options["password"] = password_from_store',
            '# es_tokens["password"] = os.getenv("TCP_ELASTIC_PASSWORD")',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    python_comment_structured_auth_lines(source),
                    [],
                )

    def test_python_comment_password_guard_ignores_code_and_safe_comments(self):
        safe_examples = (
            'password = password_from_store',
            'text = \'# "password": "embedded-value"\'',
            '# "password": os.environ.get("TCP_ELASTIC_PASSWORD")',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(python_comment_password_lines(source), [])

    def test_python_comment_structured_auth_guard_detects_literals(self):
        hardcoded_examples = (
            '# http_auth=("elastic", "hardcoded-secret")',
            '# basic_auth=("elastic", "hardcoded-secret")',
            '# headers={"Authorization": "Bearer hardcoded-token"}',
            '# AUTH=("elastic", "hardcoded-secret"); http_auth=AUTH',
            '# AUTH="ApiKey hardcoded-token"; headers={"Authorization": AUTH}',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    python_comment_structured_auth_lines(source),
                    [1],
                )

    def test_python_comment_structured_auth_guard_reassembles_multiline_blocks(self):
        hardcoded_examples = (
            (
                '# options = {\n'
                '#     "http_auth": ("elastic", "hardcoded-secret"),\n'
                '# }',
                [1],
            ),
            (
                '# headers = {\n'
                '#     "Authorization": "Bearer hardcoded-token",\n'
                '# }',
                [1],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    python_comment_structured_auth_lines(source),
                    expected,
                )

    def test_python_comment_structured_auth_guard_allows_safe_multiline_blocks(self):
        safe_source = (
            '# options = {\n'
            '#     "http_auth": ("elastic", password_from_store),\n'
            '#     "headers": {"Authorization": f"Bearer {token}"},\n'
            '# }'
        )
        self.assertEqual(
            python_comment_structured_auth_lines(safe_source),
            [],
        )

    def test_python_comment_structured_auth_guard_allows_runtime_references(self):
        safe_examples = (
            '# http_auth=("elastic", password_from_store)',
            '# basic_auth=("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))',
            '# headers={"Authorization": f"Bearer {token}"}',
            '# AUTH="Bearer " + token_from_store; headers={"Authorization": AUTH}',
            "text = '# http_auth=(\"elastic\", \"hardcoded-secret\")'",
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    python_comment_structured_auth_lines(source),
                    [],
                )

    def test_python_comment_scalar_auth_guard_detects_literals(self):
        hardcoded_examples = (
            '# api_key = "hardcoded-api-key-value"',
            '# bearer_auth = "hardcoded-bearer-token"',
            'value = 1  # "api_key": "hardcoded-api-key-value"',
            '# api_key = os.getenv("TCP_ES_API_KEY", "hardcoded-api-key-value")',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(python_comment_scalar_auth_lines(source), [1])

    def test_python_comment_scalar_auth_guard_allows_runtime_references(self):
        safe_examples = (
            '# api_key = os.getenv("TCP_ES_API_KEY")',
            '# bearer_auth = token_from_store',
            '# api_key = "***REDACTED***"',
            'text = \'# api_key = "hardcoded-api-key-value"\'',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(python_comment_scalar_auth_lines(source), [])

    def test_authorization_header_guard_reconstructs_composed_values(self):
        hardcoded_examples = (
            (
                'TOKEN = "hardcoded-token"\n'
                'headers = {"Authorization": "Bearer " + TOKEN}',
                [2],
            ),
            (
                'TOKEN = "hardcoded-token"\n'
                'headers = {"Authorization": f"Bearer {TOKEN}"}',
                [2],
            ),
            (
                'PREFIX = "ApiKey "\n'
                'TOKEN = "hardcoded-token"\n'
                'headers = {"Authorization": PREFIX + TOKEN}',
                [3],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    expected,
                )

    def test_authorization_header_guard_detects_positional_dict_constructors(self):
        hardcoded_examples = (
            (
                'headers = dict([("Authorization", "Bearer hardcoded-token")])',
                [1],
            ),
            (
                'headers = dict(AUTHORIZATION="Bearer hardcoded-token")',
                [1],
            ),
            (
                'headers = dict([("AUTHORIZATION", "Bearer hardcoded-token")])',
                [1],
            ),
            (
                'pairs = [("Authorization", "ApiKey hardcoded-token")]\n'
                'headers = dict(pairs)',
                [2],
            ),
            (
                'PAIR = ("Authorization", "Basic hardcoded-token")\n'
                'pairs = [PAIR]\n'
                'headers = dict(pairs)',
                [3],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    expected,
                )

    def test_authorization_header_guard_allows_runtime_positional_dict_constructors(self):
        safe_examples = (
            'headers = dict([("Authorization", authorization_from_store)])',
            'headers = dict(AUTHORIZATION=authorization_from_store)',
            'headers = dict([("AUTHORIZATION", authorization_from_store)])',
            (
                'pairs = [("Authorization", "Bearer " + token_from_store)]\n'
                'headers = dict(pairs)'
            ),
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    [],
                )

    def test_authorization_header_guard_detects_mapping_mutations(self):
        hardcoded_examples = (
            (
                'headers = {}\n'
                'headers.update(Authorization="Bearer hardcoded-token")',
                [2],
            ),
            (
                'headers = {}\n'
                'headers.update({"Authorization": "ApiKey hardcoded-token"})',
                [2],
            ),
            (
                'headers = {}\n'
                'headers.setdefault("Authorization", "Basic hardcoded-token")',
                [2],
            ),
            (
                'AUTH = "Bearer hardcoded-token"\n'
                'headers = {}\n'
                'headers.update(Authorization=AUTH)',
                [3],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    expected,
                )

    def test_authorization_header_guard_allows_runtime_mapping_mutations(self):
        safe_examples = (
            'headers = {}\n'
            'headers.update(Authorization=authorization_from_store)',
            'headers = {}\n'
            'headers.update({"Authorization": "Bearer " + token_from_store})',
            'headers = {}\n'
            'headers.setdefault("Authorization", authorization_from_store)',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    [],
                )

    def test_authorization_header_guard_reconstructs_augmented_values(self):
        hardcoded_examples = (
            (
                'headers["Authorization"] = "Bearer "\n'
                'headers["Authorization"] += "hardcoded-token"',
                [2],
            ),
            (
                'TOKEN = "hardcoded-token"\n'
                'headers["Authorization"] = "ApiKey "\n'
                'headers["Authorization"] += TOKEN',
                [3],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    expected,
                )

    def test_authorization_header_guard_allows_runtime_augmented_values(self):
        safe_source = (
            'headers["Authorization"] = "Bearer "\n'
            'headers["Authorization"] += token_from_store'
        )
        self.assertEqual(
            hardcoded_authorization_header_lines(safe_source),
            [],
        )

    def test_authorization_header_guard_reconstructs_format_calls(self):
        hardcoded_examples = (
            (
                'TOKEN = "hardcoded-token"\n'
                'headers = {"Authorization": "{} {}".format("Bearer", TOKEN)}',
                [2],
            ),
            (
                'TOKEN = "hardcoded-token"\n'
                'headers = {"Authorization": "Bearer {}".format(TOKEN)}',
                [2],
            ),
            (
                'headers = {"Authorization": "%s %s" % '
                '("Bearer", "hardcoded-token")}',
                [1],
            ),
            (
                'TOKEN = "hardcoded-token"\n'
                'headers = {"Authorization": "ApiKey %s" % TOKEN}',
                [2],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    expected,
                )

    def test_authorization_header_guard_allows_dynamic_format_calls(self):
        safe_examples = (
            'headers = {"Authorization": "Bearer {}".format(token_from_store)}',
            'headers = {"Authorization": "%s %s" % ("Bearer", token_from_store)}',
            'headers = {"Authorization": "ApiKey %s" % token_from_store}',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    [],
                )

    def test_authorization_header_guard_allows_dynamic_composed_values(self):
        safe_examples = (
            'headers = {"Authorization": "Bearer " + token_from_store}',
            'headers = {"Authorization": f"Bearer {token_from_store}"}',
            'PREFIX = "Bearer "\n'
            'headers = {"Authorization": PREFIX + token_from_store}',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    [],
                )

    def test_authorization_header_guard_detects_dict_constructor_values(self):
        hardcoded_examples = (
            (
                'headers = dict(Authorization="Bearer hardcoded-token")',
                [1],
            ),
            (
                'TOKEN = "hardcoded-token"\n'
                'headers = dict(Authorization="ApiKey " + TOKEN)',
                [2],
            ),
            (
                'Elasticsearch(host, headers=dict('
                'Authorization="Basic hardcoded-basic-value"))',
                [1],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    expected,
                )

    def test_authorization_header_guard_allows_runtime_dict_constructor_values(self):
        safe_examples = (
            'headers = dict(Authorization=authorization_from_store)',
            'headers = dict(Authorization="Bearer " + token_from_store)',
            'Elasticsearch(host, headers=dict(Authorization=f"Bearer {token}"))',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    [],
                )

    def test_authorization_header_guard_detects_embedded_credentials(self):
        hardcoded_examples = (
            (
                'Elasticsearch(host, headers={"Authorization": '
                '"ApiKey hardcoded-api-key-value"})',
                [1],
            ),
            (
                'headers = {"authorization": "Bearer hardcoded-bearer-token"}\n'
                'Elasticsearch(host, headers=headers)',
                [1],
            ),
            (
                'AUTH = "Basic hardcoded-basic-value"\n'
                'options = {"headers": {"Authorization": AUTH}}\n'
                'Elasticsearch(host, **options)',
                [2],
            ),
            (
                'headers["Authorization"] = "Bearer hardcoded-bearer-token"',
                [1],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    expected,
                )

    def test_authorization_header_guard_allows_runtime_credentials(self):
        safe_examples = (
            'Elasticsearch(host, headers={"Authorization": f"Bearer {token}"})',
            'headers = {"Authorization": "Bearer " + token_from_store}',
            'headers["Authorization"] = authorization_from_store',
            'headers = {"Authorization": "Bearer ***REDACTED***"}',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_authorization_header_lines(source),
                    [],
                )

    def test_single_auth_guard_detects_api_key_and_bearer_literals(self):
        hardcoded_examples = (
            'Elasticsearch(host, api_key="hardcoded-api-key-value")',
            'Elasticsearch(host, bearer_auth="hardcoded-bearer-token")',
            'API_KEY = "hardcoded-api-key-value"\n'
            'Elasticsearch(host, api_key=API_KEY)',
            'TOKEN = "hardcoded-bearer-token"\n'
            'Elasticsearch(host, bearer_auth=TOKEN)',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                expected_line = 2 if "\n" in source else 1
                self.assertEqual(
                    hardcoded_single_auth_lines(source),
                    [expected_line],
                )

    def test_single_auth_guard_detects_fallbacks_and_composed_literals(self):
        hardcoded_examples = (
            'Elasticsearch(host, api_key=os.getenv("TCP_ES_API_KEY", "hardcoded-api-key-value"))',
            'Elasticsearch(host, bearer_auth=os.getenv("TCP_ES_BEARER_TOKEN") or "hardcoded-bearer-token")',
            'Elasticsearch(host, api_key="hardcoded-" + "api-key")',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_single_auth_lines(source), [1])

    def test_single_auth_guard_allows_runtime_credentials(self):
        safe_examples = (
            'Elasticsearch(host, api_key=os.getenv("TCP_ES_API_KEY"))',
            'Elasticsearch(host, bearer_auth=os.getenv("TCP_ES_BEARER_TOKEN"))',
            'API_KEY = os.getenv("TCP_ES_API_KEY")\n'
            'Elasticsearch(host, api_key=API_KEY)',
            'TOKEN = token_from_store\n'
            'Elasticsearch(host, bearer_auth=TOKEN)',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_single_auth_lines(source), [])

    def test_single_auth_guard_detects_option_mappings_and_container_targets(self):
        hardcoded_examples = (
            (
                'options = {"api_key": "hardcoded-api-key-value"}\n'
                'Elasticsearch(host, **options)',
                [1],
            ),
            (
                'options = {"bearer_auth": "hardcoded-bearer-token"}\n'
                'Elasticsearch(host, **options)',
                [1],
            ),
            (
                'API_KEY = "hardcoded-api-key-value"\n'
                'options = {"api_key": API_KEY}\n'
                'Elasticsearch(host, **options)',
                [2],
            ),
            (
                'options["api_key"] = "hardcoded-api-key-value"',
                [1],
            ),
            (
                'settings.bearer_auth = "hardcoded-bearer-token"',
                [1],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_single_auth_lines(source), expected)

    def test_single_auth_guard_detects_mapping_mutations(self):
        hardcoded_examples = (
            (
                'options = {}\n'
                'options.setdefault("api_key", "hardcoded-api-key-value")',
                [2],
            ),
            (
                'options = {}\n'
                'options.__setitem__("bearer_auth", "hardcoded-bearer-token")',
                [2],
            ),
            (
                'options = {}\n'
                'options.update(api_key="hardcoded-api-key-value")',
                [2],
            ),
            (
                'options = {}\n'
                'options.update({"bearer_auth": "hardcoded-bearer-token"})',
                [2],
            ),
            (
                'values = {"api_key": "hardcoded-api-key-value"}\n'
                'options = {}\n'
                'options.update(values)',
                [1, 3],
            ),
            (
                'options = {}\n'
                'options |= {"bearer_auth": "hardcoded-bearer-token"}',
                [2],
            ),
            (
                'options = dict([("api_key", "hardcoded-api-key-value")])',
                [1],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_single_auth_lines(source),
                    expected,
                )

    def test_single_auth_guard_allows_runtime_mapping_mutations(self):
        safe_examples = (
            'options = {}\n'
            'options.setdefault("api_key", api_key_from_store)',
            'options = {}\n'
            'options.__setitem__("bearer_auth", bearer_from_store)',
            'options = {}\n'
            'options.update(api_key=api_key_from_store)',
            'options = {}\n'
            'options.update({"bearer_auth": bearer_from_store})',
            (
                'values = {"api_key": api_key_from_store}\n'
                'options = {}\n'
                'options.update(values)'
            ),
            'options = {}\n'
            'options |= {"bearer_auth": bearer_from_store}',
            'options = dict([("api_key", api_key_from_store)])',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_single_auth_lines(source), [])

    def test_single_auth_guard_allows_runtime_option_mappings_and_targets(self):
        safe_examples = (
            (
                'options = {"api_key": os.getenv("TCP_ES_API_KEY")}\n'
                'Elasticsearch(host, **options)'
            ),
            (
                'options = {"bearer_auth": token_from_store}\n'
                'Elasticsearch(host, **options)'
            ),
            'options["api_key"] = os.getenv("TCP_ES_API_KEY")',
            'settings.bearer_auth = token_from_store',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_single_auth_lines(source), [])

    def test_credential_guards_detect_lambda_defaults(self):
        self.assertEqual(
            hardcoded_password_literal_lines(
                'client = lambda password="hardcoded-secret": password'
            ),
            [1],
        )
        self.assertEqual(
            hardcoded_auth_tuple_lines(
                'client = lambda http_auth=("elastic", "hardcoded-secret"): http_auth'
            ),
            [1],
        )
        self.assertEqual(
            hardcoded_single_auth_lines(
                'client = lambda api_key="hardcoded-api-key-value": api_key'
            ),
            [1],
        )
        self.assertEqual(
            hardcoded_single_auth_lines(
                'client = lambda *, bearer_auth="hardcoded-bearer-token": bearer_auth'
            ),
            [1],
        )

    def test_credential_guards_allow_runtime_lambda_defaults(self):
        self.assertEqual(
            hardcoded_password_literal_lines(
                'client = lambda password=password_from_store: password'
            ),
            [],
        )
        self.assertEqual(
            hardcoded_auth_tuple_lines(
                'client = lambda http_auth=("elastic", password_from_store): http_auth'
            ),
            [],
        )
        self.assertEqual(
            hardcoded_single_auth_lines(
                'client = lambda api_key=api_key_from_store: api_key'
            ),
            [],
        )

    def test_single_auth_guard_detects_function_defaults(self):
        hardcoded_examples = (
            'def client(api_key="hardcoded-api-key-value"):\n    return api_key',
            'def client(*, bearer_auth="hardcoded-bearer-token"):\n    return bearer_auth',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_single_auth_lines(source), [1])

    def test_single_auth_guard_allows_runtime_function_defaults(self):
        safe_examples = (
            'def client(api_key=os.getenv("TCP_ES_API_KEY")):\n    return api_key',
            'def client(*, bearer_auth=token_from_store):\n    return bearer_auth',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_single_auth_lines(source), [])

    def test_auth_tuple_guard_normalizes_constructed_sequences(self):
        hardcoded_examples = (
            (
                'Elasticsearch(host, http_auth=(user,) + ("embedded-value",))',
                [1],
            ),
            (
                'AUTH = (user,) + ("embedded-value",)\n'
                'Elasticsearch(host, http_auth=AUTH)',
                [2],
            ),
            (
                'LEFT = (user,)\n'
                'RIGHT = ("embedded-value",)\n'
                'AUTH = LEFT + RIGHT\n'
                'Elasticsearch(host, basic_auth=AUTH)',
                [4],
            ),
            (
                'http_auth = (user,) + ("embedded-value",)\n'
                'Elasticsearch(host, http_auth=http_auth)',
                [1, 2],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

    def test_auth_tuple_guard_allows_runtime_constructed_sequences(self):
        safe_examples = (
            'Elasticsearch(host, http_auth=(user,) + (password_from_store,))',
            'AUTH = (user,) + (os.getenv("TCP_ELASTIC_PASSWORD"),)\n'
            'Elasticsearch(host, http_auth=AUTH)',
            'LEFT = (user,)\n'
            'RIGHT = (password_from_store,)\n'
            'AUTH = LEFT + RIGHT\n'
            'Elasticsearch(host, basic_auth=AUTH)',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

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
            (
                'options["http_auth"] = ()\n'
                'options["http_auth"] += ("elastic",)\n'
                'options["http_auth"] += (password_from_store,)\n'
                'Elasticsearch(host, http_auth=options["http_auth"])'
            ),
            (
                'settings.basic_auth = ()\n'
                'settings.basic_auth += ("elastic",)\n'
                'settings.basic_auth += (password_from_store,)\n'
                'Elasticsearch(host, basic_auth=settings.basic_auth)'
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
            (
                'def normalize(value):\n'
                '    return value.strip()\n'
                'Elasticsearch(host, basic_auth=(user, normalize("real-secret")))',
                [3],
            ),
            ('Elasticsearch(host, basic_auth=(user, str("real-secret")))', [1]),
            (
                'def normalize(value):\n'
                '    return value.strip()\n'
                'literal = "real-secret"\n'
                'Elasticsearch(host, basic_auth=(user, normalize(literal)))',
                [4],
            ),
            (
                'normalize = lambda value: value.strip()\n'
                'Elasticsearch(host, basic_auth=(user, normalize("real-secret")))',
                [2],
            ),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

    def test_auth_tuple_guard_allows_runtime_secret_provider_calls(self):
        safe_examples = (
            'Elasticsearch(host, basic_auth=(user, secret_manager.read("real-secret")))',
            'Elasticsearch(host, http_auth=(user, getpass.getpass("Password: ")))',
            'Elasticsearch(host, basic_auth=(user, vault.read("secret/es/password")))',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

    def test_auth_tuple_guard_allows_rebound_callable_providers(self):
        safe_examples = (
            'normalize = secret_manager.read\n'
            'Elasticsearch(host, basic_auth=(user, normalize("credential-profile-name")))',
            'str = vault.read\n'
            'Elasticsearch(host, basic_auth=(user, str("secret/es/password")))',
            'from my_module import normalize\n'
            'Elasticsearch(host, basic_auth=(user, normalize("credential-profile-name")))',
            'def connect(normalize):\n'
            '    return Elasticsearch(host, basic_auth=(user, normalize("lookup-key")))',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

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

    def test_auth_tuple_guard_resolves_destructured_bindings(self):
        hardcoded_examples = (
            (
                'user, password = ("elastic", "embedded-value")\n'
                'Elasticsearch(host, http_auth=(user, password))',
                [2],
            ),
            (
                '(user, password), suffix = '
                '(("elastic", "embedded-value"), "ignored")\n'
                'Elasticsearch(host, basic_auth=(user, password))',
                [2],
            ),
            (
                'credentials = ("elastic", "embedded-value")\n'
                'user, password = credentials\n'
                'Elasticsearch(host, http_auth=(user, password))',
                [3],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

        safe_source = (
            'user, password = '
            '("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))\n'
            'Elasticsearch(host, http_auth=(user, password))'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(safe_source), [])

    def test_auth_tuple_guard_keeps_aliases_in_lexical_scope(self):
        hardcoded_global = (
            'AUTH = ("elastic", "embedded-value")\n'
            'def helper():\n'
            '    AUTH = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))\n'
            '    return AUTH\n'
            'def client():\n'
            '    return Elasticsearch(host, http_auth=AUTH)'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(hardcoded_global), [6])

        safe_global = (
            'AUTH = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))\n'
            'def helper():\n'
            '    AUTH = ("elastic", "embedded-value")\n'
            '    return AUTH\n'
            'def client():\n'
            '    return Elasticsearch(host, http_auth=AUTH)'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(safe_global), [])

        hardcoded_local = (
            'AUTH = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))\n'
            'def client():\n'
            '    AUTH = ("elastic", "embedded-value")\n'
            '    return Elasticsearch(host, http_auth=AUTH)'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(hardcoded_local), [4])

    def test_auth_tuple_guard_preserves_same_line_statement_order(self):
        hardcoded_then_safe = (
            'AUTH = ("elastic", "embedded-value"); '
            'Elasticsearch(host, http_auth=AUTH); '
            'AUTH = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(hardcoded_then_safe), [1])

        safe_then_hardcoded = (
            'AUTH = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD")); '
            'Elasticsearch(host, http_auth=AUTH); '
            'AUTH = ("elastic", "embedded-value")'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(safe_then_hardcoded), [])

        augmented_alias = (
            'SECRET = ("embedded-value",); '
            'basic_auth = (user,); '
            'basic_auth += SECRET; '
            'SECRET = (os.getenv("TCP_ELASTIC_PASSWORD"),)'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(augmented_alias), [1])

    def test_auth_tuple_guard_tracks_conditional_reassignments(self):
        hardcoded_then_conditional_safe = (
            'AUTH = ("elastic", "embedded-value")\n'
            'if enabled:\n'
            '    AUTH = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))\n'
            'Elasticsearch(host, http_auth=AUTH)'
        )
        self.assertEqual(
            hardcoded_auth_tuple_lines(hardcoded_then_conditional_safe),
            [4],
        )

        safe_then_conditional_hardcoded = (
            'AUTH = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))\n'
            'if enabled:\n'
            '    AUTH = ("elastic", "embedded-value")\n'
            'Elasticsearch(host, http_auth=AUTH)'
        )
        self.assertEqual(
            hardcoded_auth_tuple_lines(safe_then_conditional_hardcoded),
            [4],
        )

        conditional_local_use = (
            'AUTH = ("elastic", "embedded-value")\n'
            'if enabled:\n'
            '    AUTH = ("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))\n'
            '    Elasticsearch(host, http_auth=AUTH)'
        )
        self.assertEqual(
            hardcoded_auth_tuple_lines(conditional_local_use),
            [],
        )

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

    def test_python_password_literal_guard_keeps_aliases_in_lexical_scope(self):
        hardcoded_global = (
            'SECRET = "embedded-value"\n'
            'def helper():\n'
            '    SECRET = os.getenv("TCP_ELASTIC_PASSWORD")\n'
            '    return SECRET\n'
            'def client():\n'
            '    return connect(password=SECRET)'
        )
        self.assertEqual(hardcoded_password_literal_lines(hardcoded_global), [6])

        safe_global = (
            'SECRET = os.getenv("TCP_ELASTIC_PASSWORD")\n'
            'def helper():\n'
            '    SECRET = "embedded-value"\n'
            '    return SECRET\n'
            'def client():\n'
            '    return connect(password=SECRET)'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_global), [])

        hardcoded_local = (
            'SECRET = os.getenv("TCP_ELASTIC_PASSWORD")\n'
            'def client():\n'
            '    SECRET = "embedded-value"\n'
            '    return connect(password=SECRET)'
        )
        self.assertEqual(hardcoded_password_literal_lines(hardcoded_local), [4])

    def test_python_password_literal_guard_preserves_same_line_statement_order(self):
        hardcoded_then_safe = (
            'SECRET = "embedded-value"; '
            'connect(password=SECRET); '
            'SECRET = os.getenv("TCP_ELASTIC_PASSWORD")'
        )
        self.assertEqual(
            hardcoded_password_literal_lines(hardcoded_then_safe),
            [1],
        )

        safe_then_hardcoded = (
            'SECRET = os.getenv("TCP_ELASTIC_PASSWORD"); '
            'connect(password=SECRET); '
            'SECRET = "embedded-value"'
        )
        self.assertEqual(
            hardcoded_password_literal_lines(safe_then_hardcoded),
            [],
        )

    def test_python_password_literal_guard_tracks_conditional_reassignments(self):
        hardcoded_then_conditional_safe = (
            'SECRET = "embedded-value"\n'
            'if enabled:\n'
            '    SECRET = os.getenv("TCP_ELASTIC_PASSWORD")\n'
            'connect(password=SECRET)'
        )
        self.assertEqual(
            hardcoded_password_literal_lines(hardcoded_then_conditional_safe),
            [4],
        )

        safe_then_conditional_hardcoded = (
            'SECRET = os.getenv("TCP_ELASTIC_PASSWORD")\n'
            'if enabled:\n'
            '    SECRET = "embedded-value"\n'
            'connect(password=SECRET)'
        )
        self.assertEqual(
            hardcoded_password_literal_lines(safe_then_conditional_hardcoded),
            [4],
        )

        conditional_local_use = (
            'SECRET = "embedded-value"\n'
            'if enabled:\n'
            '    SECRET = os.getenv("TCP_ELASTIC_PASSWORD")\n'
            '    connect(password=SECRET)'
        )
        self.assertEqual(
            hardcoded_password_literal_lines(conditional_local_use),
            [],
        )

    def test_python_password_literal_guard_resolves_destructured_bindings(self):
        hardcoded_examples = (
            (
                'user, password = ("elastic", "embedded-value")\n'
                'connect(password=password)',
                [2],
            ),
            (
                '(user, password), suffix = '
                '(("elastic", "embedded-value"), "ignored")\n'
                'connect(password=password)',
                [2],
            ),
            (
                'credentials = ("elastic", "embedded-value")\n'
                'user, password = credentials\n'
                'connect(password=password)',
                [3],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    expected,
                )

        safe_source = (
            'user, password = '
            '("elastic", os.getenv("TCP_ELASTIC_PASSWORD"))\n'
            'connect(password=password)'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

    def test_python_password_literal_guard_allows_imported_environment_lookups(self):
        safe_examples = (
            (
                'from os import getenv\n'
                'password = getenv("TCP_ELASTIC_PASSWORD")'
            ),
            (
                'from os import getenv as read_env\n'
                'password = read_env("TCP_ELASTIC_PASSWORD")'
            ),
            (
                'import os as operating_system\n'
                'password = operating_system.getenv("TCP_ELASTIC_PASSWORD")'
            ),
            (
                'from os import environ\n'
                'password = environ.get("TCP_ELASTIC_PASSWORD")'
            ),
            (
                'import os\n'
                'env = os.environ\n'
                'password = env.get("TCP_ELASTIC_PASSWORD")'
            ),
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_detects_imported_environment_fallbacks(self):
        hardcoded_examples = (
            (
                'from os import getenv\n'
                'password = getenv("TCP_ELASTIC_PASSWORD", "hardcoded-secret")'
            ),
            (
                'import os as operating_system\n'
                'password = operating_system.getenv('
                '"TCP_ELASTIC_PASSWORD", "hardcoded-secret")'
            ),
            (
                'from os import environ\n'
                'password = environ.get('
                '"TCP_ELASTIC_PASSWORD", "hardcoded-secret")'
            ),
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [2])

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

    def test_python_password_literal_guard_detects_static_call_results(self):
        cases = (
            ('password = "real-secret".strip()', [1]),
            (
                'def normalize(value):\n'
                '    return value.strip()\n'
                'password = normalize("real-secret")',
                [3],
            ),
            ('password = str("real-secret")', [1]),
            ('normalize = str\npassword = normalize("real-secret")', [2]),
            ('password = config.get("password", "real-secret")', [1]),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

    def test_python_password_literal_guard_resolves_mapping_get_selected_key(self):
        hardcoded_source = (
            'config = {"elastic_secret": "hardcoded-secret"}\n'
            'password = config.get("elastic_secret")'
        )
        self.assertEqual(
            hardcoded_password_literal_lines(hardcoded_source),
            [2],
        )

        safe_source = (
            'config = {"elastic_secret": password_from_store}\n'
            'password = config.get("elastic_secret")'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

    def test_python_password_literal_guard_resolves_mapping_get_key_aliases(self):
        hardcoded_examples = (
            (
                'KEY = "elastic_secret"\n'
                'config = {"elastic_secret": "hardcoded-secret"}\n'
                'password = config.get(KEY)'
            ),
            (
                'BASE_KEY = "elastic_secret"\n'
                'KEY = BASE_KEY\n'
                'base = {"elastic_secret": "hardcoded-secret"}\n'
                'config = base\n'
                'password = config.get(KEY)'
            ),
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    [len(source.splitlines())],
                )

        safe_examples = (
            'KEY = "elastic_secret"\n'
            'config = {"elastic_secret": password_from_store}\n'
            'password = config.get(KEY)',
            'KEY = "elastic_secret"\n'
            'KEY = "user"\n'
            'config = {"elastic_secret": "hardcoded-secret", "user": runtime_user}\n'
            'password = config.get(KEY)',
            'KEY = runtime_key\n'
            'config = {"elastic_secret": "hardcoded-secret"}\n'
            'password = config.get(KEY)',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])


    def test_python_password_literal_guard_allows_annotation_only_bindings(self):
        safe_sources = (
            'password: str',
            'api_key: str',
            'password: str\\nclient = Elasticsearch(host)',
            'if enabled:\\n    password: str',
        )
        for source in safe_sources:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])
                self.assertEqual(hardcoded_authorization_header_lines(source), [])

        hardcoded_sources = (
            ('password: str = "hardcoded-secret"', [1]),
            ('password: str\\npassword = "hardcoded-secret"', [2]),
            ('password: str\\nElasticsearch(host, basic_auth=("elastic", "hardcoded-secret"))', [2]),
        )
        for source, expected in hardcoded_sources:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

    def test_python_password_literal_guard_preserves_mapping_alias_capture(self):
        hardcoded_source = (
            'BASE = "elastic_secret"\n'
            'KEY = BASE\n'
            'BASE = "user"\n'
            'config = {"elastic_secret": "hardcoded-secret", "user": runtime_user}\n'
            'password = config.get(KEY)'
        )
        self.assertEqual(hardcoded_password_literal_lines(hardcoded_source), [5])

        safe_source = (
            'BASE = "user"\n'
            'KEY = BASE\n'
            'BASE = "elastic_secret"\n'
            'config = {"elastic_secret": "hardcoded-secret", "user": runtime_user}\n'
            'password = config.get(KEY)'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

    def test_python_password_literal_guard_preserves_composed_key_capture(self):
        hardcoded_examples = (
            (
                'BASE = "elastic_secret"\n'
                'KEY = f"{BASE}"\n'
                'BASE = "user"\n'
                'config = {"elastic_secret": "hardcoded-secret", "user": runtime_user}\n'
                'password = config.get(KEY)'
            ),
            (
                'BASE = "elastic_secret"\n'
                'KEY = "{}".format(BASE)\n'
                'BASE = "user"\n'
                'config = {"elastic_secret": "hardcoded-secret", "user": runtime_user}\n'
                'password = config.get(KEY)'
            ),
            (
                'BASE = "elastic_secret"\n'
                'KEY = BASE + ""\n'
                'BASE = "user"\n'
                'config = {"elastic_secret": "hardcoded-secret", "user": runtime_user}\n'
                'password = config.get(KEY)'
            ),
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    [len(source.splitlines())],
                )

        safe_source = (
            'BASE = "user"\n'
            'KEY = f"{BASE}"\n'
            'BASE = "elastic_secret"\n'
            'config = {"elastic_secret": "hardcoded-secret", "user": runtime_user}\n'
            'password = config.get(KEY)'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

    def test_python_password_literal_guard_preserves_callable_alias_capture(self):
        hardcoded_sources = (
            'normalize = lambda value: value\n'
            'transform = normalize\n'
            'normalize = secret_manager.read\n'
            'password = transform("hardcoded-secret")',
            'normalize = lambda value: value.strip()\n'
            'first = normalize\n'
            'transform = first\n'
            'normalize = vault.read\n'
            'password = transform("hardcoded-secret")',
            'transform = str\n'
            'str = secret_manager.read\n'
            'password = transform("hardcoded-secret")',
        )
        for source in hardcoded_sources:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    [len(source.splitlines())],
                )

        safe_sources = (
            'normalize = secret_manager.read\n'
            'transform = normalize\n'
            'normalize = lambda value: value\n'
            'password = transform("credential-profile-name")',
            'str = vault.read\n'
            'transform = str\n'
            'str = lambda value: value\n'
            'password = transform("secret/es/password")',
        )
        for source in safe_sources:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_handles_builtin_str_source_order(self):
        hardcoded_examples = (
            'password = str("real-secret")\nstr = vault.read',
            'password = str("real-secret")\nfrom secrets_provider import str',
        )
        for source in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [1])

        safe_examples = (
            'str = vault.read\npassword = str("secret/es/password")',
            'from secrets_provider import str\npassword = str("secret/es/password")',
            'import secrets_provider as str\npassword = str("secret/es/password")',
            'def read_password():\n'
            '    password = str("lookup-key")\n'
            '    str = vault.read',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_respects_mutually_exclusive_str(self):
        hardcoded_examples = (
            (
                'if use_provider:\n'
                '    str = vault.read\n'
                'else:\n'
                '    password = str("hardcoded-secret")',
                [4],
            ),
            (
                'if use_provider:\n'
                '    str = vault.read\n'
                'else:\n'
                '    if another_flag:\n'
                '        password = str("hardcoded-secret")',
                [5],
            ),
            (
                'match provider:\n'
                '    case "external":\n'
                '        str = vault.read\n'
                '    case "builtin":\n'
                '        password = str("hardcoded-secret")',
                [5],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

        safe_source = (
            'str = vault.read\n'
            'if use_provider:\n'
            '    str = another_provider.read\n'
            'else:\n'
            '    password = str("secret/es/password")'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

    def test_python_password_literal_guard_allows_rebound_transform_names(self):
        safe_examples = (
            'normalize = secret_manager.read\n'
            'password = normalize("credential-profile-name")',
            'str = vault.read\n'
            'password = str("secret/es/password")',
            'from helpers import normalize\n'
            'password = normalize("credential-profile-name")',
            'def build(normalize):\n'
            '    password = normalize("lookup-key")',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_allows_runtime_provider_lookup_arguments(self):
        safe_examples = (
            'password = secret_manager.read("elasticsearch-password")',
            'password = getpass.getpass("Password: ")',
            'password = vault.read(path="secret/elasticsearch")',
            'password = provider.lookup("credential-profile-name")',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

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

    def test_python_password_literal_guard_detects_environment_target_assignments(self):
        hardcoded_examples = (
            (
                'os.environ["TCP_ELASTIC_PASSWORD"] = "embedded-value"',
                [1],
            ),
            (
                'SECRET = "embedded-value"\n'
                'os.environ["TCP_ELASTIC_PASSWORD"] = SECRET',
                [2],
            ),
            (
                "os.environ['TCP_ELASTIC_PASSWORD'] += 'embedded-value'",
                [1],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    expected,
                )

    def test_python_password_literal_guard_detects_environment_receiver_aliases(self):
        hardcoded_examples = (
            (
                'import os as operating_system\n'
                'operating_system.environ["TCP_ELASTIC_PASSWORD"] = '
                '"hardcoded-secret"',
                [2],
            ),
            (
                'from os import environ\n'
                'environ["TCP_ELASTIC_PASSWORD"] = "hardcoded-secret"',
                [2],
            ),
            (
                'import os\n'
                'env = os.environ\n'
                'env["TCP_ELASTIC_PASSWORD"] = "hardcoded-secret"',
                [3],
            ),
            (
                'from os import environ as env\n'
                'env.update({"TCP_ELASTIC_PASSWORD": "hardcoded-secret"})',
                [2],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    expected,
                )

    def test_python_password_literal_guard_allows_runtime_environment_receiver_aliases(self):
        safe_examples = (
            (
                'import os as operating_system\n'
                'operating_system.environ["TCP_ELASTIC_PASSWORD"] = '
                'password_from_store'
            ),
            (
                'from os import environ\n'
                'environ["TCP_ELASTIC_PASSWORD"] = password_from_store'
            ),
            (
                'import os\n'
                'env = os.environ\n'
                'env["TCP_ELASTIC_PASSWORD"] = password_from_store'
            ),
            (
                'from os import environ as env\n'
                'env.update({"TCP_ELASTIC_PASSWORD": password_from_store})'
            ),
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_allows_runtime_environment_target_assignments(self):
        safe_examples = (
            'os.environ["TCP_ELASTIC_PASSWORD"] = password_from_store',
            'SECRET = password_from_store\n'
            'os.environ["TCP_ELASTIC_PASSWORD"] = SECRET',
            "os.environ['TCP_ELASTIC_PASSWORD'] += suffix_from_store",
            'os.environ["OTHER_ENV"] = "embedded-value"',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_detects_environment_updates(self):
        hardcoded_examples = (
            (
                'os.environ.update({"TCP_ELASTIC_PASSWORD": "hardcoded-secret"})',
                [1],
            ),
            (
                'SECRET = "hardcoded-secret"\n'
                'os.environ.update({"TCP_ELASTIC_PASSWORD": SECRET})',
                [2],
            ),
            (
                'os.environ.update(TCP_ELASTIC_PASSWORD="hardcoded-secret")',
                [1],
            ),
            (
                'os.environ.update(dict(TCP_ELASTIC_PASSWORD="hardcoded-secret"))',
                [1],
            ),
            (
                'os.environ.update(dict([("TCP_ELASTIC_PASSWORD", "hardcoded-secret")]))',
                [1],
            ),
            (
                'values = {"TCP_ELASTIC_PASSWORD": "hardcoded-secret"}\n'
                'os.environ.update(values)',
                [2],
            ),
            (
                'BASE = {"TCP_ELASTIC_PASSWORD": "hardcoded-secret"}\n'
                'values = BASE\n'
                'os.environ.update(values)',
                [3],
            ),
            (
                'os.environ.update(**{"TCP_ELASTIC_PASSWORD": "hardcoded-secret"})',
                [1],
            ),
            (
                'values = {"TCP_ELASTIC_PASSWORD": "hardcoded-secret"}\n'
                'os.environ.update(**values)',
                [2],
            ),
            (
                'os.environ.setdefault("TCP_ELASTIC_PASSWORD", "hardcoded-secret")',
                [1],
            ),
            (
                'SECRET = "hardcoded-secret"\n'
                'os.environ.setdefault("TCP_ELASTIC_PASSWORD", SECRET)',
                [2],
            ),
            (
                'os.environ.__setitem__("TCP_ELASTIC_PASSWORD", "hardcoded-secret")',
                [1],
            ),
            (
                'SECRET = "hardcoded-secret"\n'
                'os.environ.__setitem__("TCP_ELASTIC_PASSWORD", SECRET)',
                [2],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    expected,
                )

    def test_python_password_literal_guard_allows_runtime_environment_updates(self):
        safe_examples = (
            (
                'values = {"TCP_ELASTIC_PASSWORD": password_from_store}\n'
                'os.environ.update(values)'
            ),
            'os.environ.update(**{"TCP_ELASTIC_PASSWORD": password_from_store})',
            (
                'values = {"TCP_ELASTIC_PASSWORD": password_from_store}\n'
                'os.environ.update(**values)'
            ),
            'os.environ.update({"TCP_ELASTIC_PASSWORD": password_from_store})',
            'os.environ.update(TCP_ELASTIC_PASSWORD=password_from_store)',
            'os.environ.update(dict([("TCP_ELASTIC_PASSWORD", password_from_store)]))',
            'os.environ.setdefault("TCP_ELASTIC_PASSWORD", password_from_store)',
            'os.environ.__setitem__("TCP_ELASTIC_PASSWORD", password_from_store)',
            'os.environ.__setitem__("OTHER_ENV", "hardcoded-secret")',
            'os.environ.setdefault("OTHER_ENV", "hardcoded-secret")',
            'os.environ.update({"OTHER_ENV": "hardcoded-secret"})',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_detects_environment_mapping_merges(self):
        hardcoded_examples = (
            (
                'os.environ |= {"TCP_ELASTIC_PASSWORD": "hardcoded-secret"}',
                [1],
            ),
            (
                'values = {"TCP_ELASTIC_PASSWORD": "hardcoded-secret"}\n'
                'os.environ |= values',
                [2],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    expected,
                )

    def test_python_password_literal_guard_allows_runtime_environment_mapping_merges(self):
        safe_examples = (
            'os.environ |= {"TCP_ELASTIC_PASSWORD": password_from_store}',
            (
                'values = {"TCP_ELASTIC_PASSWORD": password_from_store}\n'
                'os.environ |= values'
            ),
            'other |= {"TCP_ELASTIC_PASSWORD": "hardcoded-secret"}',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_detects_mapping_constructors_and_mutations(self):
        hardcoded_examples = (
            (
                'options = dict([("password", "hardcoded-secret")])',
                [1],
            ),
            (
                'pairs = [("password", "hardcoded-secret")]\n'
                'options = dict(pairs)',
                [2],
            ),
            (
                'options = {}\n'
                'options.setdefault("password", "hardcoded-secret")',
                [2],
            ),
            (
                'options = {}\n'
                'options.__setitem__("password", "hardcoded-secret")',
                [2],
            ),
            (
                'options = {}\n'
                'options.update(password="hardcoded-secret")',
                [2],
            ),
            (
                'values = {"password": "hardcoded-secret"}\n'
                'options = {}\n'
                'options.update(values)',
                [1, 3],
            ),
            (
                'options = {}\n'
                'options |= {"password": "hardcoded-secret"}',
                [2],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(
                    hardcoded_password_literal_lines(source),
                    expected,
                )

    def test_python_password_literal_guard_allows_runtime_mapping_constructors_and_mutations(self):
        safe_examples = (
            'options = dict([("password", password_from_store)])',
            (
                'pairs = [("password", password_from_store)]\n'
                'options = dict(pairs)'
            ),
            'options = {}\n'
            'options.setdefault("password", password_from_store)',
            'options = {}\n'
            'options.__setitem__("password", password_from_store)',
            'options = {}\n'
            'options.update(password=password_from_store)',
            (
                'values = {"password": password_from_store}\n'
                'options = {}\n'
                'options.update(values)'
            ),
            'options = {}\n'
            'options |= {"password": password_from_store}',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])

    def test_python_password_literal_guard_detects_direct_subscript_assignment(self):
        self.assertEqual(
            hardcoded_password_literal_lines(
                'es_tokens["password"] = "hardcoded-secret"'
            ),
            [1],
        )
        self.assertEqual(
            hardcoded_password_literal_lines(
                'es_tokens["password"] = password_from_store'
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

    def test_auth_tuple_guard_detects_mapping_mutations(self):
        hardcoded_examples = (
            (
                'options = {}\n'
                'options.setdefault("http_auth", ("elastic", "hardcoded-secret"))',
                [2],
            ),
            (
                'options = {}\n'
                'options.__setitem__("basic_auth", ("elastic", "hardcoded-secret"))',
                [2],
            ),
            (
                'options = {}\n'
                'options.update(http_auth=("elastic", "hardcoded-secret"))',
                [2],
            ),
            (
                'values = {"basic_auth": ("elastic", "hardcoded-secret")}\n'
                'options = {}\n'
                'options.update(values)',
                [1, 3],
            ),
            (
                'options = {}\n'
                'options |= {"http_auth": ("elastic", "hardcoded-secret")}',
                [2],
            ),
        )
        for source, expected in hardcoded_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), expected)

    def test_auth_tuple_guard_allows_runtime_mapping_mutations(self):
        safe_examples = (
            'options = {}\n'
            'options.setdefault("http_auth", ("elastic", password_from_store))',
            'options = {}\n'
            'options.__setitem__("basic_auth", ("elastic", password_from_store))',
            'options = {}\n'
            'options.update(http_auth=("elastic", password_from_store))',
            'options = {}\n'
            'options |= {"basic_auth": ("elastic", password_from_store)}',
        )
        for source in safe_examples:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])

    def test_python_password_literal_guard_mapping_get_reads_selected_key_only(self):
        safe_source = (
            'config = {"host": "localhost"}\n'
            'password = config.get("password")'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

        hardcoded_source = (
            'config = {"host": "localhost", "password": "hardcoded-secret"}\n'
            'password = config.get("password")'
        )
        self.assertEqual(hardcoded_password_literal_lines(hardcoded_source), [1, 2])

        fallback_source = (
            'config = {"host": "localhost"}\n'
            'password = config.get("password", "hardcoded-secret")'
        )
        self.assertEqual(hardcoded_password_literal_lines(fallback_source), [2])

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
        runtime_es_modules = set(self._runtime_es_module_paths())
        for path in self._secret_surface_paths():
            text = path.read_text(encoding="utf-8-sig")
            if path.suffix.lower() != ".py":
                for line_number in text_structured_auth_secret_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:structured-auth"
                    )
            if path.suffix.lower() == ".py":
                for line_number in hardcoded_auth_tuple_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:auth-tuple"
                    )
                for line_number in hardcoded_single_auth_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:client-auth-literal"
                    )
                for line_number in hardcoded_authorization_header_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:authorization-header"
                    )
                for line_number in python_comment_scalar_auth_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:client-auth-comment"
                    )
                for line_number in python_comment_structured_auth_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:structured-auth-comment"
                    )
                for line_number in python_disabled_code_secret_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:disabled-code-secret"
                    )
                for line_number in hardcoded_password_literal_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:password-literal"
                    )
                for line_number in hardcoded_url_userinfo_lines(text):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:credential-url-composed"
                    )
                if path in runtime_es_modules:
                    for line_number in python_comment_password_lines(text):
                        violations.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:password-comment"
                        )
            for line_number, line in enumerate(text.splitlines(), start=1):
                if path not in runtime_es_modules:
                    for value_expression in password_value_expressions(line):
                        if value_expression not in ALLOWED_PASSWORD_EXPRESSIONS:
                            violations.append(
                                f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:password"
                            )
                if ENROLLMENT_TOKEN_RE.search(line):
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:enrollment-token"
                    )
                if text_url_userinfo_has_secret(line):
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
