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


def _is_single_auth_target(node, bindings=None, before_position=None):
    if isinstance(node, ast.Name):
        return node.id in SINGLE_VALUE_AUTH_NAMES
    if isinstance(node, ast.Subscript):
        return _static_key_matches(
            node.slice, SINGLE_VALUE_AUTH_NAMES, bindings, before_position
        )
    if isinstance(node, ast.Attribute):
        return node.attr in SINGLE_VALUE_AUTH_NAMES
    return False


def _is_auth_tuple_target(node, bindings=None, before_position=None):
    if isinstance(node, ast.Name):
        return node.id in AUTH_TUPLE_NAMES
    if isinstance(node, ast.Subscript):
        return _static_key_matches(
            node.slice, AUTH_TUPLE_NAMES, bindings, before_position
        )
    if isinstance(node, ast.Attribute):
        return node.attr in AUTH_TUPLE_NAMES
    return False


def _literal_string(node):
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _static_key_strings(node, bindings=None, before_position=None):
    """Resolve a mapping key only when it is statically reconstructible."""
    if node is None:
        return []
    if bindings is None:
        literal = _literal_string(node)
        return [literal] if literal is not None else []
    if before_position is None:
        before_position = _node_position(node)
    return _static_string_values(node, bindings, before_position)


def _static_key_matches(
    node, names, bindings=None, before_position=None, case_insensitive=False
):
    candidates = _static_key_strings(node, bindings, before_position)
    if isinstance(names, str):
        names = {names}
    if case_insensitive:
        allowed = {name.lower() for name in names}
        return any(key.lower() in allowed for key in candidates)
    return any(key in names for key in candidates)


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


def _auth_target_key(node, bindings=None, before_position=None):
    """Return a stable key for a supported auth target expression."""
    if not _is_auth_tuple_target(node, bindings, before_position):
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
        keys = [
            key for key in _static_key_strings(node.slice, bindings, before_position)
            if key in AUTH_TUPLE_NAMES
        ]
        return (
            "subscript",
            ast.dump(node.value, include_attributes=False),
            keys[0],
        ) if keys else None
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

    # A nested function can outlive the path that defined it, for example
    # when it is returned and called after a later invocation of its parent.
    # Direct calls in the same lexical scope do not themselves escape.
    ast_parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    # Record callable values by their real source-ordered bindings, rather
    # than treating every definition with a matching name as one function.
    # Include lambda assignments and noncallable rebindings (which mask the
    # earlier function at later uses).
    callable_bindings = {}

    def record_callable_binding(owner, name, node, value):
        callable_bindings.setdefault((owner, name), []).append(
            (_node_position(node), value)
        )

    for node in ast.walk(tree):
        owner = getattr(node, "_binding_scope", module_scope)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            record_callable_binding(owner, node.name, node, node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    record_callable_binding(owner, target.id, node, node.value)
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None and isinstance(node.target, ast.Name):
                record_callable_binding(owner, node.target.id, node, node.value)
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            record_callable_binding(owner, node.target.id, node, node.value)

    for entries in callable_bindings.values():
        entries.sort(key=lambda item: item[0])

    def reaching_callables(name, use_node, seen=None):
        seen = set() if seen is None else set(seen)
        owner = getattr(use_node, "_binding_scope", module_scope)
        while owner is not None:
            token = (owner, name)
            if token in seen:
                return []
            if token in callable_bindings:
                break
            if name in scope_locals.get(owner, ()):
                return []
            owner = scope_parents.get(owner)
        if owner is None:
            return []

        reaching = _reaching_values(
            [
                (position, value)
                for position, value in callable_bindings[token]
                if position <= _node_position(use_node)
            ],
            use_node,
        )
        found = []
        for value in reaching:
            if isinstance(value, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                found.append(value)
            elif isinstance(value, ast.Name):
                found.extend(reaching_callables(value.id, value, seen | {token}))
        return found

    # Use the reaching container *binding* rather than just (scope, name).
    # Branches may rebind the same local variable to unrelated collections.
    container_bindings = {}

    def statically_unpacked_values(value, owner, seen=None):
        """Resolve source-ordered tuple/list aliases before destructuring."""
        if isinstance(value, (ast.Tuple, ast.List)):
            return [value]
        if not isinstance(value, ast.Name):
            return []
        seen = set() if seen is None else set(seen)
        # The unpacking assignment may occur in a nested closure while its
        # source tuple/list was created in an enclosing frame. Resolve the
        # actual lexical name owner rather than assuming the target's scope.
        scope = getattr(value, "_binding_scope", owner)
        binding_owner = scope
        while binding_owner is not None:
            if value.id in scope_globals.get(binding_owner, ()):
                binding_owner = module_scope
                break
            if value.id in scope_nonlocals.get(binding_owner, ()):
                binding_owner = scope_parents.get(binding_owner)
                continue
            if value.id in scope_locals.get(binding_owner, ()):
                break
            binding_owner = scope_parents.get(binding_owner)
        if binding_owner is None:
            binding_owner = module_scope
        token = (binding_owner, value.id)
        if token in seen:
            return []
        candidates = [
            (position, candidate)
            for position, candidate in container_bindings.get(token, ())
            if position < _node_position(value)
            or binding_owner is not scope
        ]
        if binding_owner is scope:
            reaching = _reaching_values(candidates, value)
        else:
            # Reading a captured tuple in a closure can occur after the
            # enclosing assignment; exclude only mutually exclusive arms.
            reaching = [
                candidate for _position, candidate in candidates
                if not _control_paths_mutually_exclusive(
                    _node_control_path(candidate), _node_control_path(value)
                )
            ]
        # If a name could refer to a non-container or to different shapes,
        # do not assert that any particular destructured local is private.
        if not reaching:
            return []
        resolved = []
        for candidate in reaching:
            choices = statically_unpacked_values(
                candidate, binding_owner, seen | {token}
            )
            if len(choices) != 1:
                return []
            resolved.extend(choices)
        return resolved

    def record_container_assignment(target, value, owner, position):
        """Keep each destructured local's initializer and control path."""
        if isinstance(target, ast.Name):
            container_bindings.setdefault((owner, target.id), []).append(
                (position, value)
            )
        elif isinstance(target, (ast.Tuple, ast.List)):
            choices = statically_unpacked_values(value, owner)
            if len(choices) != 1:
                return
            container = choices[0]
            if len(target.elts) != len(container.elts):
                return
            for child_target, child_value in zip(
                target.elts, container.elts
            ):
                record_container_assignment(
                    child_target, child_value, owner, position
                )

    def record_destructured_callable_assignment(target, value, owner, position):
        """Bind callable-valued tuple/list elements to their actual target names.

        A bound collection accessor can be exported after unpacking, e.g.
        `extract, unused = source.pop, None`. Resolve only known, matching
        unpack shapes and preserve source order and each value's branch path.
        """
        if not isinstance(target, (ast.Tuple, ast.List)):
            return
        choices = statically_unpacked_values(value, owner)
        if len(choices) != 1 or len(choices[0].elts) != len(target.elts):
            return
        for child_target, child_value in zip(target.elts, choices[0].elts):
            if isinstance(child_target, ast.Name):
                record_callable_binding(owner, child_target.id, target, child_value)
            else:
                record_destructured_callable_assignment(
                    child_target, child_value, owner, position
                )

    assignment_nodes = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
        ),
        key=_node_position,
    )
    for node in assignment_nodes:
        owner = getattr(node, "_binding_scope", module_scope)
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if node.value is None:
            continue
        for target in targets:
            record_container_assignment(
                target, node.value, owner, _node_position(node)
            )
            record_destructured_callable_assignment(
                target, node.value, owner, _node_position(node)
            )
    for entries in container_bindings.values():
        entries.sort(key=lambda item: item[0])
    for entries in callable_bindings.values():
        entries.sort(key=lambda item: item[0])

    def container_binding_owner(name, scope):
        """Locate the frame owning a container reference."""
        current = scope
        while current is not None:
            if name in scope_globals.get(current, ()):
                return module_scope
            if name in scope_nonlocals.get(current, ()):
                current = scope_parents.get(current)
                continue
            if name in scope_locals.get(current, ()):
                return current
            current = scope_parents.get(current)
        return module_scope

    def outward_assignment_target(target, scope):
        """A name stored in an outer/global frame or an object really escapes."""
        if isinstance(target, ast.Attribute):
            return True
        if isinstance(target, ast.Name):
            return (
                scope is module_scope
                or container_binding_owner(target.id, scope) is not scope
            )
        if isinstance(target, (ast.Tuple, ast.List)):
            return any(
                outward_assignment_target(child, scope) for child in target.elts
            )
        # Indexed writes into a local container are not escape sinks merely
        # because their target is an ast.Subscript; inspect them at fixed point.
        return False

    def reaching_containers(name_node, seen=None):
        """Resolve container identities along the reachable assignment path."""
        seen = set() if seen is None else set(seen)
        scope = getattr(name_node, "_binding_scope", module_scope)
        owner = container_binding_owner(name_node.id, scope)
        token = (owner, name_node.id)
        if token in seen:
            return set()

        candidates = container_bindings.get(token, ())
        if scope is owner:
            reaching = _reaching_values(
                [
                    (position, value)
                    for position, value in candidates
                    if position <= _node_position(name_node)
                ],
                name_node,
            )
        else:
            # A closure can read its captured container after its source
            # definition. Its read path still excludes conflicting arms.
            use_path = _node_control_path(name_node)
            reaching = [
                value
                for _position, value in candidates
                if not _control_paths_mutually_exclusive(
                    _node_control_path(value), use_path
                )
            ]
        resolved = set()
        for value in reaching:
            if isinstance(value, ast.Name):
                resolved.update(reaching_containers(value, seen | {token}))
            else:
                resolved.add(value)
        return resolved

    def exposed_container_bindings(expression):
        """Find retained container values without walking callable bodies."""
        if expression is None or isinstance(expression, ast.Lambda):
            return set()
        if isinstance(expression, ast.Subscript):
            # Returning a selected value does not export the whole source.
            # Selected callback and child containers are handled below.
            return set()
        if isinstance(expression, ast.Name):
            if isinstance(expression.ctx, ast.Load):
                return reaching_containers(expression)
            return set()
        if isinstance(expression, ast.Call):
            # A call result may escape, but this does not mean its receiver
            # is a *live* alias. A .copy() is a snapshot, handled separately.
            children = [*expression.args, *[kw.value for kw in expression.keywords]]
        else:
            children = ast.iter_child_nodes(expression)
        retained = set()
        for child in children:
            retained.update(exposed_container_bindings(child))
        return retained

    # Built-in mutator method arguments are stored in their *receiver*, not
    # handed to an opaque callback-retaining consumer. Defer escape decisions
    # until the exact receiver binding has actually escaped its frame.
    mutator_methods = {
        ast.List: frozenset(("append", "extend", "insert")),
        ast.Set: frozenset(("add", "update")),
        ast.Dict: frozenset(("update", "setdefault")),
    }

    def known_container_mutator_type(binding):
        if isinstance(binding, tuple(mutator_methods)):
            return type(binding)
        # Empty built-in constructors produce new private containers, just
        # like literals. Only trust their identity if the built-in name is not
        # shadowed by any lexical binding.
        constructors = {"list": ast.List, "dict": ast.Dict, "set": ast.Set}
        if not (
            isinstance(binding, ast.Call)
            and isinstance(binding.func, ast.Name)
            and binding.func.id in constructors
            and not binding.args
            and not binding.keywords
        ):
            return None
        name = binding.func.id
        scope = getattr(binding, "_binding_scope", module_scope)
        while scope is not None:
            if name in scope_locals.get(scope, ()):
                return None
            scope = scope_parents.get(scope)
        return constructors[name]

    def known_container_mutator_bindings(call):
        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
        ):
            return None
        bindings = reaching_containers(call.func.value)
        if not bindings or any(
            (kind := known_container_mutator_type(binding)) is None
            or call.func.attr not in mutator_methods[kind]
            for binding in bindings
        ):
            return None
        return bindings

    # Shallow copies retain callback values existing at the instant of copy.
    # They do NOT retain callbacks inserted into the original afterwards.
    copied_container_snapshots = set()

    def record_escaping_copies(expression):
        if expression is None or isinstance(expression, ast.Lambda):
            return
        if isinstance(expression, ast.Call):
            if (
                isinstance(expression.func, ast.Attribute)
                and expression.func.attr == "copy"
                and not expression.args
                and not expression.keywords
            ):
                for binding in exposed_container_bindings(expression.func.value):
                    copied_container_snapshots.add((binding, expression))
            # Do not descend through the callable expression of other calls.
            children = [*expression.args, *[kw.value for kw in expression.keywords]]
        else:
            children = ast.iter_child_nodes(expression)
        for child in children:
            record_escaping_copies(child)

    # Returned containers, values passed to opaque consumers and values
    # written to object/mapping slots can all outlive the current frame.
    escaping_container_bindings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)):
            escaping_container_bindings.update(
                exposed_container_bindings(node.value)
            )
            record_escaping_copies(node.value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            scope = getattr(node, "_binding_scope", module_scope)
            if node.value is not None and any(
                outward_assignment_target(target, scope) for target in targets
            ):
                escaping_container_bindings.update(
                    exposed_container_bindings(node.value)
                )
                record_escaping_copies(node.value)
        elif isinstance(node, ast.Call):
            if known_container_mutator_bindings(node) is not None:
                continue
            for argument in node.args:
                escaping_container_bindings.update(
                    exposed_container_bindings(argument)
                )
                record_escaping_copies(argument)
            for keyword in node.keywords:
                escaping_container_bindings.update(
                    exposed_container_bindings(keyword.value)
                )
                record_escaping_copies(keyword.value)

    escaping_functions = set()

    def reaching_assigned_values(name_node):
        """Look through local aliases when an extracted callback reaches a sink."""
        owner = container_binding_owner(
            name_node.id, getattr(name_node, "_binding_scope", module_scope)
        )
        candidates = callable_bindings.get((owner, name_node.id), ())
        if getattr(name_node, "_binding_scope", module_scope) is owner:
            return _reaching_values(
                [
                    (position, value)
                    for position, value in candidates
                    if position <= _node_position(name_node)
                ],
                name_node,
            )
        return [
            value for _position, value in candidates
            if not _control_paths_mutually_exclusive(
                _node_control_path(value), _node_control_path(name_node)
            )
        ]

    # An extracted value can escape while its source collection stays private.
    # Accessor method objects may themselves be aliased before they are called.
    def extracted_accesses(node):
        if isinstance(node, ast.Subscript):
            return [(node.value, node.slice)]
        if not isinstance(node, ast.Call):
            return []

        def bound_accessors(function, seen=None):
            if isinstance(function, ast.Attribute):
                if function.attr in {"pop", "popitem", "get", "__getitem__"}:
                    return [(function.value, function.attr)]
                return []
            if not isinstance(function, ast.Name):
                return []
            seen = set() if seen is None else seen
            scope = getattr(function, "_binding_scope", module_scope)
            token = (container_binding_owner(function.id, scope), function.id)
            if token in seen:
                return []
            found = []
            for value in reaching_assigned_values(function):
                found.extend(bound_accessors(value, seen | {token}))
            return found

        accesses = []
        for receiver, method in bound_accessors(node.func):
            # A no-argument pop() has a position-dependent element. Keep the
            # conservative fallback rather than invent a static selection.
            key = (
                node.args[0]
                if method in {"pop", "get", "__getitem__"} and node.args
                else None
            )
            accesses.append((receiver, key))
        return accesses

    unknown_selection = object()

    def static_selection(node, seen=None):
        """Resolve a literal dict key/list index through reaching local aliases."""
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
            return node.value
        if not isinstance(node, ast.Name):
            return unknown_selection
        seen = set() if seen is None else seen
        scope = getattr(node, "_binding_scope", module_scope)
        token = (container_binding_owner(node.id, scope), node.id)
        if token in seen:
            return unknown_selection
        candidates = reaching_assigned_values(node)
        if not candidates:
            return unknown_selection
        values = [
            static_selection(value, seen | {token}) for value in candidates
        ]
        if any(value is unknown_selection or value != values[0] for value in values):
            return unknown_selection
        return values[0]

    def selected_elements(container, key):
        """Select only provably reachable literal elements for a fixed key."""
        if isinstance(container, ast.Dict):
            values = []
            for entry_key, entry_value in zip(container.keys, container.values):
                if entry_key is None:
                    # A **mapping expansion can supply the selected key.
                    values.append(entry_value)
                elif (
                    key is unknown_selection
                    or (candidate := static_selection(entry_key)) is unknown_selection
                    or candidate == key
                ):
                    values.append(entry_value)
            return values
        if isinstance(container, (ast.List, ast.Tuple)):
            def expanded_items(value, seen=None):
                """Flatten only sequence spreads whose runtime length is fixed."""
                seen = set() if seen is None else seen
                if isinstance(value, ast.Name):
                    bindings = reaching_containers(value)
                    if len(bindings) != 1:
                        return None
                    binding = next(iter(bindings))
                    if binding in seen:
                        return None
                    return expanded_items(binding, seen)
                if not isinstance(value, (ast.List, ast.Tuple)):
                    return None
                if value in seen:
                    return None
                seen = seen | {value}
                items = []
                for item in value.elts:
                    if isinstance(item, ast.Starred):
                        spread = expanded_items(item.value, seen)
                        if spread is None:
                            return None
                        items.extend(spread)
                    else:
                        items.append(item)
                return items

            expanded = expanded_items(container)
            if expanded is not None:
                if isinstance(key, int) and not isinstance(key, bool):
                    if -len(expanded) <= key < len(expanded):
                        return [expanded[key]]
                    return []
                # Unresolved selections still consider all candidate values.
                return expanded if key is unknown_selection else []

            # A dynamic spread may shift every index. Retain conservative
            # candidates when it cannot be flattened with known cardinality.
            candidates = []
            for item in container.elts:
                if isinstance(item, ast.Starred):
                    candidates.append(item.value)
                    if isinstance(item.value, (ast.List, ast.Tuple, ast.Set)):
                        candidates.extend(item.value.elts)
                    elif isinstance(item.value, ast.Name):
                        for binding in reaching_containers(item.value):
                            if isinstance(binding, (ast.List, ast.Tuple, ast.Set)):
                                candidates.extend(binding.elts)
                            elif isinstance(binding, ast.Dict):
                                candidates.extend(k for k in binding.keys if k is not None)
                else:
                    candidates.append(item)
            return candidates
        if isinstance(container, ast.Set):
            return container.elts
        return []

    def mark_extracted_callbacks(node, seen):
        for receiver, key_node in extracted_accesses(node):
            if not isinstance(receiver, ast.Name):
                continue
            containers = reaching_containers(receiver)
            if not containers or any(
                known_container_mutator_type(binding) is None
                for binding in containers
            ):
                continue
            selected = (
                unknown_selection if key_node is None
                else static_selection(key_node)
            )

            # A private collection can give away just one of its callbacks.
            # Do not implicitly export unrelated literal or indexed values.
            for binding in containers:
                if isinstance(binding, (ast.List, ast.Tuple, ast.Dict, ast.Set)):
                    for value in selected_elements(binding, selected):
                        mark_escaping_expression(value, seen)
                        escaping_container_bindings.update(
                            exposed_container_bindings(value)
                        )
                        record_escaping_copies(value)

            # A later direct assignment to a known slot in the same straight-
            # line block definitely supersedes its prior callback value.
            statement = node
            while statement in ast_parents and not isinstance(statement, ast.stmt):
                statement = ast_parents[statement]
            block = ast_parents.get(statement)

            def fixed_slot_receiver_sets(store):
                """Reaching identities for every known selected-key write target."""
                if selected is unknown_selection or not isinstance(
                    store, (ast.Assign, ast.AnnAssign, ast.NamedExpr)
                ):
                    return []
                targets = store.targets if isinstance(store, ast.Assign) else [store.target]
                return [
                    identities
                    for target in targets
                    if isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and static_selection(target.slice) == selected
                    if (identities := reaching_containers(target.value))
                    and identities & containers
                ]

            def fixed_slot_write(store):
                return bool(fixed_slot_receiver_sets(store))

            def definitely_same_receiver(write, earlier_identities):
                # An overlap is insufficient: if source may be left OR right,
                # a write to right does not definitely replace source's value.
                # Only suppress when both identities resolve to the same
                # unique container for this straight-line execution.
                return (
                    len(earlier_identities) == 1
                    and any(
                        targets == earlier_identities
                        for targets in fixed_slot_receiver_sets(write)
                    )
                )

            known_writes = [
                candidate for candidate in ast.walk(tree)
                if fixed_slot_write(candidate)
                and ast_parents.get(candidate) is block
                and getattr(candidate, "_binding_scope", module_scope)
                    is getattr(node, "_binding_scope", module_scope)
                and _node_position(candidate) < _node_position(node)
            ]

            for store in ast.walk(tree):
                if _control_paths_mutually_exclusive(
                    _node_control_path(store), _node_control_path(node)
                ):
                    continue
                if (
                    getattr(store, "_binding_scope", module_scope)
                    is getattr(node, "_binding_scope", module_scope)
                    and _node_position(store) > _node_position(node)
                ):
                    continue
                if isinstance(store, ast.Call):
                    stored_in = known_container_mutator_bindings(store)
                    if stored_in is None or not stored_in & containers:
                        continue
                    method = store.func.attr
                    if method == "setdefault" and selected is not unknown_selection:
                        key = static_selection(store.args[0]) if store.args else unknown_selection
                        if key is not unknown_selection and key != selected:
                            continue
                        values = store.args[1:2]
                    elif method == "update" and selected is not unknown_selection and all(
                        isinstance(binding, ast.Dict) for binding in stored_in
                    ):
                        # A concrete keyword overrides a positional mapping
                        # entry with the same key *within this update call*.
                        selected_keyword = next(
                            (kw.value for kw in reversed(store.keywords)
                             if kw.arg == selected),
                            None,
                        )
                        if selected_keyword is not None:
                            values = [selected_keyword]
                        else:
                            values = []
                            for arg in store.args:
                                if isinstance(arg, ast.Dict):
                                    values.extend(selected_elements(arg, selected))
                                else:
                                    values.append(arg)
                            for keyword in store.keywords:
                                if keyword.arg is None:
                                    values.append(keyword.value)
                    else:
                        values = [
                            *store.args,
                            *(keyword.value for keyword in store.keywords),
                        ]
                    # A straight-line write to the same fixed key after
                    # update() supersedes the update's callback value.
                    # Conditional writes must not suppress possible escape.
                    enclosing_stmt = store
                    while enclosing_stmt in ast_parents and not isinstance(
                        enclosing_stmt, ast.stmt
                    ):
                        enclosing_stmt = ast_parents[enclosing_stmt]
                    superseded_update = (
                        method == "update"
                        and selected is not unknown_selection
                        and isinstance(enclosing_stmt, ast.Expr)
                        and enclosing_stmt.value is store
                        and ast_parents.get(enclosing_stmt) is block
                        and any(
                            _node_position(write) > _node_position(store)
                            and definitely_same_receiver(write, stored_in)
                            for write in known_writes
                        )
                    )
                    if not superseded_update:
                        for value in values:
                            mark_escaping_expression(value, seen)
                elif isinstance(store, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                    targets = (
                        store.targets if isinstance(store, ast.Assign)
                        else [store.target]
                    )
                    matches = False
                    for target in targets:
                        if not (
                            isinstance(target, ast.Subscript)
                            and isinstance(target.value, ast.Name)
                            and reaching_containers(target.value) & containers
                        ):
                            continue
                        stored_key = static_selection(target.slice)
                        if (
                            selected is unknown_selection
                            or stored_key is unknown_selection
                            or stored_key == selected
                        ):
                            matches = True
                    superseded = (
                        fixed_slot_write(store)
                        and ast_parents.get(store) is block
                        and len(fixed_slot_receiver_sets(store)) == 1
                        and any(
                            _node_position(next_store) > _node_position(store)
                            and definitely_same_receiver(
                                next_store, fixed_slot_receiver_sets(store)[0]
                            )
                            for next_store in known_writes
                        )
                    )
                    if matches and not superseded:
                        mark_escaping_expression(store.value, seen)
                elif isinstance(store, ast.AugAssign):
                    if (
                        isinstance(store.target, ast.Name)
                        and reaching_containers(store.target) & containers
                    ):
                        mark_escaping_expression(store.value, seen)

    def mark_escaping_expression(node, seen=None):
        """Follow callbacks from actual outward sinks, including extracted ones."""
        if node is None:
            return
        seen = set() if seen is None else seen
        # A callback extracted from a collection may itself refer to an
        # accessor of that same collection. Prevent cyclic AST walks.
        if node in seen:
            return
        seen = seen | {node}
        if isinstance(node, ast.Lambda):
            escaping_functions.add(node)
            return  # Its body runs later, not during the store.
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                escaping_functions.update(reaching_callables(node.id, node))
                scope = getattr(node, "_binding_scope", module_scope)
                owner = container_binding_owner(node.id, scope)
                token = (owner, node.id)
                if token not in seen:
                    for value in reaching_assigned_values(node):
                        if isinstance(value, (ast.Name, ast.Call, ast.Subscript)):
                            mark_escaping_expression(value, seen | {token})
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            escaping_functions.add(node)
            return
        if isinstance(node, (ast.Call, ast.Subscript)):
            mark_extracted_callbacks(node, seen)
        if isinstance(node, ast.Call):
            # A recognized collection mutation is not an outward sink for
            # its arguments unless the exact receiver is itself retained.
            if known_container_mutator_bindings(node) is not None:
                return
            # The callable is invoked here: its result may escape, not the
            # function object. Only callback-valued arguments can be retained
            # by that invocation or its consumer.
            for argument in node.args:
                mark_escaping_expression(argument, seen)
            for keyword in node.keywords:
                mark_escaping_expression(keyword.value, seen)
            return
        for child in ast.iter_child_nodes(node):
            mark_escaping_expression(child, seen)

    for node in ast.walk(tree):
        # Copying a local function to another local name is not an escape.
        # A later return, yield, object store or opaque call can be one.
        if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)):
            mark_escaping_expression(node.value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if node.value is None:
                continue
            scope = getattr(node, "_binding_scope", module_scope)
            if any(outward_assignment_target(target, scope) for target in targets):
                mark_escaping_expression(node.value)
        elif isinstance(node, ast.Call):
            # Calls to recognized local container mutators only retain their
            # callbacks inside the receiver; revisit in the fixed point.
            if known_container_mutator_bindings(node) is not None:
                continue
            # A callback passed to an opaque call can be retained; invoking
            # a function without passing it is not by itself an escape.
            for argument in node.args:
                mark_escaping_expression(argument)
            for keyword in node.keywords:
                mark_escaping_expression(keyword.value)

    # Escaping closures keep their enclosing frame's captured containers
    # alive. Mark those exact bindings, then revisit augmented callback
    # stores; the newly escaped callback may itself capture a container.
    augmented_stores = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AugAssign)
        and isinstance(node.op, (ast.Add, ast.BitOr))
        and isinstance(node.value, (ast.Dict, ast.List, ast.Tuple, ast.Set))
    ]
    mutator_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and known_container_mutator_bindings(node) is not None
    ]
    indexed_stores = [
        (node, target)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
        and node.value is not None
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Subscript)
    ]

    def contained_container_bindings(parent):
        """Resolve existing child references of an escaped container literal.

        Starred iterable expansion copies only the elements already present
        when the parent is built. Its source iterable itself is not retained:
        later additions to that source do not appear in the expanded parent.
        """
        if isinstance(parent, (ast.Tuple, ast.List, ast.Set)):
            children = parent.elts
        elif isinstance(parent, ast.Dict):
            children = [value for value in parent.values if value is not None]
        else:
            return set()

        retained = set()
        for child in children:
            if isinstance(child, ast.Starred):
                # For [*source] or (*source,), retain the existing elements
                # of source, not source itself or its future append/extend.
                source = child.value
                if isinstance(source, ast.Name):
                    iterable_bindings = reaching_containers(source)
                elif isinstance(source, (ast.Tuple, ast.List, ast.Set)):
                    iterable_bindings = {source}
                else:
                    iterable_bindings = set()
                for iterable in iterable_bindings:
                    if isinstance(iterable, ast.Dict):
                        # Iterating a dict (e.g. [*source]) yields *keys*.
                        # Its values, including callbacks, are not copied.
                        for key in iterable.keys:
                            if isinstance(key, ast.Name):
                                retained.update(reaching_containers(key))
                            elif isinstance(
                                key, (ast.Tuple, ast.List, ast.Set, ast.Dict)
                            ):
                                retained.add(key)
                    else:
                        retained.update(contained_container_bindings(iterable))
            elif isinstance(child, ast.Name):
                retained.update(reaching_containers(child))
            elif isinstance(child, (ast.Tuple, ast.List, ast.Set, ast.Dict)):
                retained.add(child)
        return retained

    changed = True
    while changed:
        before = (
            len(escaping_functions),
            len(escaping_container_bindings),
            len(copied_container_snapshots),
        )
        # Both a live exported parent and a shallow copy of its slots keep
        # *existing children* alive by reference. Mutations of those children
        # after the copy are visible; later insertions into the parent are not.
        for parent in tuple(escaping_container_bindings):
            # A local collection literal is not an escape by itself. Only
            # propagate its enclosed callbacks after a real outward sink
            # has retained the exact container binding.
            mark_escaping_expression(parent)
            escaping_container_bindings.update(
                contained_container_bindings(parent)
            )
        for parent, copy_call in tuple(copied_container_snapshots):
            # A shallow copy retains values already present in the original
            # literal when the copy happens (later AugAssign stores are
            # handled separately by source-order filtering below).
            if _node_position(parent) <= _node_position(copy_call):
                mark_escaping_expression(parent)
            escaping_container_bindings.update(
                contained_container_bindings(parent)
            )
        for function in tuple(escaping_functions):
            # Default expressions are evaluated in the *enclosing* frame
            # when a function/lambda is created, then retained on the escaped
            # callable. They are not annotated with the callable's own scope.
            defaults = (
                list(function.args.defaults)
                + [
                    default
                    for default in function.args.kw_defaults
                    if default is not None
                ]
            )
            for default in defaults:
                escaping_container_bindings.update(
                    exposed_container_bindings(default)
                )
                record_escaping_copies(default)

            for read in ast.walk(function):
                if not (
                    isinstance(read, ast.Name)
                    and isinstance(read.ctx, ast.Load)
                    and getattr(read, "_binding_scope", module_scope) is function
                ):
                    continue
                owner = container_binding_owner(read.id, function)
                if owner is not function and owner is not module_scope:
                    escaping_container_bindings.update(reaching_containers(read))

        for node, target in indexed_stores:
            scope = getattr(node, "_binding_scope", module_scope)
            base = target.value
            if isinstance(base, ast.Name):
                root_owner = container_binding_owner(base.id, scope)
                shared = scope is module_scope or root_owner is not scope
                if not shared:
                    reaching = reaching_containers(base)
                    # Unresolved and externally supplied collections cannot
                    # be safely treated as new frame-private literals.
                    shared = (
                        not reaching
                        or any(
                            not isinstance(value, (ast.List, ast.Dict, ast.Tuple, ast.Set))
                            for value in reaching
                        )
                        or bool(reaching & escaping_container_bindings)
                        or any(
                            binding in reaching
                            and _node_position(node) <= _node_position(copy_call)
                            and not _control_paths_mutually_exclusive(
                                _node_control_path(node),
                                _node_control_path(copy_call),
                            )
                            for binding, copy_call in copied_container_snapshots
                        )
                    )
            else:
                # Without a statically known local binding, remain
                # conservative about attribute/nested indexed containers.
                shared = True
            if shared:
                mark_escaping_expression(node.value)
                escaping_container_bindings.update(
                    exposed_container_bindings(node.value)
                )
                record_escaping_copies(node.value)

        for node in mutator_calls:
            receiver = node.func.value
            scope = getattr(node, "_binding_scope", module_scope)
            owner = container_binding_owner(receiver.id, scope)
            reaching = known_container_mutator_bindings(node)
            shared = (
                scope is module_scope
                or owner is module_scope
                or not reaching
                or bool(reaching & escaping_container_bindings)
                or any(
                    binding in reaching
                    and _node_position(node) <= _node_position(copy_call)
                    and not _control_paths_mutually_exclusive(
                        _node_control_path(node),
                        _node_control_path(copy_call),
                    )
                    for binding, copy_call in copied_container_snapshots
                )
            )
            if shared:
                for value in [
                    *node.args, *(keyword.value for keyword in node.keywords)
                ]:
                    mark_escaping_expression(value)
                    escaping_container_bindings.update(
                        exposed_container_bindings(value)
                    )
                    record_escaping_copies(value)

        for node in augmented_stores:
            owner = getattr(node, "_binding_scope", module_scope)
            target = node.target
            shared = owner is module_scope or not isinstance(target, ast.Name)
            if isinstance(target, ast.Name) and owner is not module_scope:
                shared = (
                    target.id in scope_globals.get(owner, ())
                    or target.id in scope_nonlocals.get(owner, ())
                )
                if not shared:
                    reaching = reaching_containers(target)
                    # Without a resolvable local initialization, do not
                    # assume a passed-in container is frame-private.
                    shared = (
                        not reaching
                        or bool(reaching & escaping_container_bindings)
                        or any(
                            binding in reaching
                            and _node_position(node) <= _node_position(copy_call)
                            and not _control_paths_mutually_exclusive(
                                _node_control_path(node),
                                _node_control_path(copy_call),
                            )
                            for binding, copy_call in copied_container_snapshots
                        )
                    )
            if shared:
                mark_escaping_expression(node.value)

        changed = before != (
            len(escaping_functions),
            len(escaping_container_bindings),
            len(copied_container_snapshots),
        )

    return {
        "module": module_scope,
        "parents": scope_parents,
        "locals": scope_locals,
        "globals": scope_globals,
        "nonlocals": scope_nonlocals,
        "escaping_functions": escaping_functions,
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

    binding_scope, binding_name = token
    metadata = bindings["metadata"]
    lexical_scope = getattr(use_node, "_binding_scope", metadata["module"])

    # A function/lambda reads an outer name when it *runs*, not when its
    # source body is defined. At a use site inside that deferred scope,
    # source order alone cannot rule out later outer assignments: retain
    # all potential outer binding values for conservative credential scans.
    scope = lexical_scope
    deferred_outer_lookup = False
    while scope is not None and scope is not binding_scope:
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            deferred_outer_lookup = True
        scope = metadata["parents"].get(scope)

    # Eager aliases instead capture their RHS at assignment time. Continue
    # to apply that bound for ordinary source-ordered local/module lookups.
    captured_at = getattr(use_node, "_alias_captured_at", None)
    if captured_at is not None and not deferred_outer_lookup:
        before_position = min(before_position, captured_at)

    candidates = [
        (position, value)
        for position, value in bindings["values"]
        .get(binding_scope, {})
        .get(binding_name, ())
        if deferred_outer_lookup or position <= before_position
    ]
    if deferred_outer_lookup:
        # A returned/exported nested function can run after a *different*
        # invocation of its parent mutates an outer/shared name in a sibling
        # branch. Its definition path cannot exclude those later writes.
        # A local variable owned by that very parent instead belongs to a
        # distinct frame on each invocation, so keep branch filtering there.
        scope = lexical_scope
        escaped_shared_lookup = False
        while scope is not None and scope is not binding_scope:
            parent = metadata["parents"].get(scope)
            if (
                scope in metadata["escaping_functions"]
                and parent is not binding_scope
            ):
                escaped_shared_lookup = True
                break
            scope = parent

        use_path = _node_control_path(use_node)
        return [
            value
            for _position, value in candidates
            if escaped_shared_lookup
            or not _control_paths_mutually_exclusive(
                _node_control_path(value), use_path
            )
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
        if value is None:
            return
        key = _auth_target_key(target, name_bindings, position)
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
            if node.value is None:
                continue
            value = _resolve_bound_node(
                node.value,
                name_bindings,
                _node_position(node.value),
            )
            add_binding(node.target, value, position)
        elif isinstance(node, ast.AugAssign):
            key = _auth_target_key(node.target, name_bindings, position)
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


def _is_authorization_target(node, bindings=None, before_position=None):
    if isinstance(node, ast.Subscript):
        return _static_key_matches(
            node.slice, "authorization", bindings, before_position,
            case_insensitive=True,
        )
    if isinstance(node, ast.Attribute):
        return node.attr.lower() == "authorization"
    return False


def _authorization_target_key(node, bindings=None, before_position=None):
    if not _is_authorization_target(node, bindings, before_position):
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
            "authorization",
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
        if value is None:
            return
        key = _authorization_target_key(target, name_bindings, position)
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
            if node.value is not None:
                add_binding(node.target, node.value, position)
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Add)
        ):
            key = _authorization_target_key(node.target, name_bindings, position)
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
            and _static_key_matches(
                node.args[0], "authorization", bindings, before_position,
                case_insensitive=True,
            )
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
                if _static_key_matches(
                    key, "authorization", bindings, _node_position(node),
                    case_insensitive=True,
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
            if node.value is not None and any(
                _is_authorization_target(target, bindings, _node_position(node))
                for target in targets
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", None),
                        _node_position(node.value),
                        node.value,
                    )
                )
        elif isinstance(node, ast.AugAssign) and _is_authorization_target(
            node.target, bindings, _node_position(node)
        ):
            key = _authorization_target_key(node.target, bindings, _node_position(node))
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
            and _static_key_matches(
                node.args[0], SINGLE_VALUE_AUTH_NAMES, bindings, before_position
            )
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
            if node.value is not None and any(
                _is_single_auth_target(target, bindings, _node_position(node))
                for target in targets
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", None),
                        _node_position(node.value),
                        node.value,
                    )
                )
        elif isinstance(node, ast.AugAssign) and _is_single_auth_target(
            node.target, bindings, _node_position(node)
        ):
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
                if _static_key_matches(
                    key, SINGLE_VALUE_AUTH_NAMES, bindings, _node_position(node)
                ):
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
            if node.value is not None and any(
                _is_auth_tuple_target(target, bindings, _node_position(node))
                for target in targets
            ):
                candidates.append(
                    (
                        getattr(node, "lineno", None),
                        _node_position(node.value),
                        node.value,
                    )
                )
        elif isinstance(node, ast.AugAssign) and _is_auth_tuple_target(
            node.target, bindings, _node_position(node)
        ):
            line_number = getattr(node, "lineno", None)
            key = _auth_target_key(node.target, bindings, _node_position(node))
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
                if _static_key_matches(
                    key, AUTH_TUPLE_NAMES, bindings, _node_position(node)
                ):
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

                key = _auth_target_key(resolved_value, bindings, use_position)
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
        if bindings is not None:
            return _static_key_matches(
                candidate_key, key_name, bindings, before_position,
                case_insensitive=case_insensitive,
            )
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
            and _static_key_matches(
                node.args[0], AUTH_TUPLE_NAMES, bindings, before_position
            )
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
            and _static_key_matches(
                node.args[0], "TCP_ELASTIC_PASSWORD", bindings, before_position
            )
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
    if not _static_key_matches(
        node.slice, "TCP_ELASTIC_PASSWORD", bindings, before_position
    ):
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
            _static_key_matches(
                node.slice, "password", bindings, before_position
            )
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
            and _static_key_matches(
                node.args[0], "password", bindings, before_position
            )
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
                if _static_key_matches(
                    key, "password", bindings, _node_position(node)
                ):
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
            'password: str\nclient = Elasticsearch(host)',
            'if enabled:\n    password: str',
        )
        for source in safe_sources:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), [])
                self.assertEqual(hardcoded_auth_tuple_lines(source), [])
                self.assertEqual(hardcoded_authorization_header_lines(source), [])

        hardcoded_sources = (
            ('password: str = "hardcoded-secret"', [1]),
            ('password: str\npassword = "hardcoded-secret"', [2]),
        )
        for source, expected in hardcoded_sources:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_password_literal_lines(source), expected)

        auth_source = (
            'password: str\n'
            'Elasticsearch(host, basic_auth=("elastic", "hardcoded-secret"))'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(auth_source), [2])

    def test_annotation_only_auth_bindings_do_not_reset_augmented_values(self):
        auth_tuple_source = (
            'basic_auth = (runtime_user,)\n'
            'basic_auth: tuple\n'
            'basic_auth += ("hardcoded-secret",)'
        )
        self.assertEqual(hardcoded_auth_tuple_lines(auth_tuple_source), [3])

        authorization_source = (
            'headers.Authorization = "Bearer "\n'
            'headers.Authorization: str\n'
            'headers.Authorization += "hardcoded-token"'
        )
        self.assertEqual(
            hardcoded_authorization_header_lines(authorization_source),
            [3],
        )

    def test_credential_guards_resolve_aliases_used_as_mapping_keys(self):
        hardcoded_cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "password"\noptions = {}\n'
                'options[KEY] = "hardcoded-secret"',
                [3],
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "password"\noptions = {KEY: "hardcoded-secret"}',
                [2],
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "password"\noptions.setdefault(KEY, "hardcoded-secret")',
                [2],
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "password"\noptions.__setitem__(KEY, "hardcoded-secret")',
                [2],
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "password"\nALIAS = KEY\nKEY = "username"\n'
                'options[ALIAS] = "hardcoded-secret"',
                [4],
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "api_key"\noptions[KEY] = "hardcoded-api-key"',
                [2],
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "bearer_auth"\n'
                'options.setdefault(KEY, "hardcoded-bearer")',
                [2],
            ),
            (
                hardcoded_auth_tuple_lines,
                'KEY = "basic_auth"\n'
                'options[KEY] = ("elastic", "hardcoded-secret")',
                [2],
            ),
            (
                hardcoded_auth_tuple_lines,
                'KEY = "http_auth"\n'
                'options.setdefault(KEY, ("elastic", "hardcoded-secret"))',
                [2],
            ),
            (
                hardcoded_authorization_header_lines,
                'KEY = "Authorization"\n'
                'headers[KEY] = "Bearer hardcoded-token"',
                [2],
            ),
            (
                hardcoded_authorization_header_lines,
                'KEY = "authorization"\n'
                'headers.setdefault(KEY, "ApiKey hardcoded-token")',
                [2],
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "TCP_ELASTIC_PASSWORD"\n'
                'os.environ[KEY] = "hardcoded-secret"',
                [2],
            ),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

        safe_cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\noptions[KEY] = "hardcoded-secret"',
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "password"\nKEY = "username"\n'
                'options[KEY] = "hardcoded-secret"',
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = dynamic_key\noptions[KEY] = "hardcoded-secret"',
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "username"\noptions[KEY] = "hardcoded-api-key"',
            ),
            (
                hardcoded_auth_tuple_lines,
                'KEY = "username"\n'
                'options[KEY] = ("elastic", "hardcoded-secret")',
            ),
            (
                hardcoded_authorization_header_lines,
                'KEY = "x-trace"\nheaders[KEY] = "Bearer hardcoded-token"',
            ),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_credential_guards_resolve_deferred_outer_key_rebindings(self):
        hardcoded_cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def build():\n'
                '    options[KEY] = "hardcoded-secret"\n'
                'KEY = "password"\n'
                'build()',
                [3],
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def build():\n'
                '    local_key = f"{KEY}"\n'
                '    options[local_key] = "hardcoded-secret"\n'
                'KEY = "password"\n'
                'build()',
                [4],
            ),
            (
                hardcoded_password_literal_lines,
                'def outer():\n'
                '    KEY = "username"\n'
                '    def build():\n'
                '        options[KEY] = "hardcoded-secret"\n'
                '    KEY = "password"\n'
                '    build()\n'
                'outer()',
                [4],
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "username"\n'
                'def build():\n'
                '    options[KEY] = "hardcoded-api-key"\n'
                'KEY = "api_key"\n'
                'build()',
                [3],
            ),
            (
                hardcoded_auth_tuple_lines,
                'KEY = "username"\n'
                'def build():\n'
                '    options[KEY] = ("elastic", "hardcoded-secret")\n'
                'KEY = "basic_auth"\n'
                'build()',
                [3],
            ),
            (
                hardcoded_authorization_header_lines,
                'KEY = "x-trace"\n'
                'def build():\n'
                '    headers[KEY] = "Bearer hardcoded-token"\n'
                'KEY = "Authorization"\n'
                'build()',
                [3],
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def build():\n'
                '    os.environ[KEY] = "hardcoded-secret"\n'
                'KEY = "TCP_ELASTIC_PASSWORD"\n'
                'build()',
                [3],
            ),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

        safe_cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def build():\n'
                '    options[KEY] = "hardcoded-secret"\n'
                'build()',
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "password"\n'
                'def build():\n'
                '    KEY = "username"\n'
                '    options[KEY] = "hardcoded-secret"\n'
                'build()',
            ),
            (
                hardcoded_password_literal_lines,
                'def build(KEY):\n'
                '    options[KEY] = "hardcoded-secret"\n'
                'build(runtime_key)',
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "username"\n'
                'def build():\n'
                '    options[KEY] = "hardcoded-api-key"\n'
                'build()',
            ),
            (
                hardcoded_auth_tuple_lines,
                'KEY = "username"\n'
                'def build():\n'
                '    options[KEY] = ("elastic", "hardcoded-secret")\n'
                'build()',
            ),
            (
                hardcoded_authorization_header_lines,
                'KEY = "x-trace"\n'
                'def build():\n'
                '    headers[KEY] = "Bearer hardcoded-token"\n'
                'build()',
            ),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_deferred_key_lookup_excludes_mutually_exclusive_branches(self):
        safe_cases = (
            (
                hardcoded_password_literal_lines,
                'if flag:\n'
                '    KEY = "password"\n'
                'else:\n'
                '    KEY = "username"\n'
                '    def build():\n'
                '        options[KEY] = "hardcoded-secret"\n'
                '    build()',
            ),
            (
                hardcoded_password_literal_lines,
                'match mode:\n'
                '    case "secret":\n'
                '        KEY = "password"\n'
                '    case "safe":\n'
                '        KEY = "username"\n'
                '        def build():\n'
                '            options[KEY] = "hardcoded-secret"\n'
                '        build()',
            ),
            (
                hardcoded_single_auth_lines,
                'if flag:\n'
                '    KEY = "api_key"\n'
                'else:\n'
                '    KEY = "username"\n'
                '    def build():\n'
                '        options[KEY] = "hardcoded-api-key"\n'
                '    build()',
            ),
            (
                hardcoded_auth_tuple_lines,
                'if flag:\n'
                '    KEY = "basic_auth"\n'
                'else:\n'
                '    KEY = "username"\n'
                '    def build():\n'
                '        options[KEY] = ("elastic", "hardcoded-secret")\n'
                '    build()',
            ),
            (
                hardcoded_authorization_header_lines,
                'if flag:\n'
                '    KEY = "Authorization"\n'
                'else:\n'
                '    KEY = "x-trace"\n'
                '    def build():\n'
                '        headers[KEY] = "Bearer hardcoded-token"\n'
                '    build()',
            ),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

        hardcoded_cases = (
            (
                hardcoded_password_literal_lines,
                'if flag:\n'
                '    KEY = "username"\n'
                'else:\n'
                '    KEY = "password"\n'
                '    def build():\n'
                '        options[KEY] = "hardcoded-secret"\n'
                '    build()',
                [6],
            ),
            (
                hardcoded_password_literal_lines,
                'if flag:\n'
                '    KEY = "username"\n'
                'else:\n'
                '    KEY = "username"\n'
                '    def build():\n'
                '        options[KEY] = "hardcoded-secret"\n'
                '    KEY = "password"\n'
                '    build()',
                [6],
            ),
            (
                hardcoded_single_auth_lines,
                'if flag:\n'
                '    KEY = "username"\n'
                'else:\n'
                '    KEY = "api_key"\n'
                '    def build():\n'
                '        options[KEY] = "hardcoded-api-key"\n'
                '    build()',
                [6],
            ),
            (
                hardcoded_auth_tuple_lines,
                'if flag:\n'
                '    KEY = "username"\n'
                'else:\n'
                '    KEY = "basic_auth"\n'
                '    def build():\n'
                '        options[KEY] = ("elastic", "hardcoded-secret")\n'
                '    build()',
                [6],
            ),
            (
                hardcoded_authorization_header_lines,
                'if flag:\n'
                '    KEY = "x-trace"\n'
                'else:\n'
                '    KEY = "Authorization"\n'
                '    def build():\n'
                '        headers[KEY] = "Bearer hardcoded-token"\n'
                '    build()',
                [6],
            ),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_escaped_closure_reaches_shared_sibling_branch_bindings(self):
        hardcoded_cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        def build():\n'
                '            options[KEY] = "hardcoded-secret"\n'
                '        return build\n'
                '    else:\n'
                '        KEY = "password"\n'
                'build = configure(True)\n'
                'configure(False)\n'
                'build()',
                [6],
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        def build():\n'
                '            options[KEY] = "hardcoded-api-key"\n'
                '        return build\n'
                '    else:\n'
                '        KEY = "api_key"\n'
                'build = configure(True)\n'
                'configure(False)\n'
                'build()',
                [6],
            ),
            (
                hardcoded_auth_tuple_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        def build():\n'
                '            options[KEY] = ("elastic", "hardcoded-secret")\n'
                '        return build\n'
                '    else:\n'
                '        KEY = "basic_auth"\n'
                'build = configure(True)\n'
                'configure(False)\n'
                'build()',
                [6],
            ),
            (
                hardcoded_authorization_header_lines,
                'KEY = "x-trace"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        def build():\n'
                '            headers[KEY] = "Bearer hardcoded-token"\n'
                '        return build\n'
                '    else:\n'
                '        KEY = "Authorization"\n'
                'build = configure(True)\n'
                'configure(False)\n'
                'build()',
                [6],
            ),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

        # A closure retains its own configure() frame for local variables;
        # rebinding a sibling path during another call cannot affect it.
        safe_source = (
            'def configure(flag):\n'
            '    KEY = "username"\n'
            '    if flag:\n'
            '        def build():\n'
            '            options[KEY] = "hardcoded-secret"\n'
            '        return build\n'
            '    else:\n'
            '        KEY = "password"\n'
            'build = configure(True)\n'
            'configure(False)\n'
            'build()'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

    def test_escaped_lambda_alias_reaches_later_sibling_global_binding(self):
        hardcoded_cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        build = lambda: options.__setitem__(KEY, "hardcoded-secret")\n'
                '        return build\n'
                '    else:\n'
                '        KEY = "password"\n'
                'build = configure(True)\n'
                'configure(False)\n'
                'build()',
                [5],
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        build = lambda: options.__setitem__(KEY, "hardcoded-secret")\n'
                '        alias = build\n'
                '        return alias\n'
                '    else:\n'
                '        KEY = "password"\n'
                'build = configure(True)\n'
                'configure(False)\n'
                'build()',
                [5],
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        build = lambda: options.__setitem__(KEY, "hardcoded-token")\n'
                '        return build\n'
                '    else:\n'
                '        KEY = "api_key"\n'
                'build = configure(True)\n'
                'configure(False)\n'
                'build()',
                [5],
            ),
            (
                hardcoded_authorization_header_lines,
                'KEY = "x-trace"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        build = lambda: headers.setdefault(KEY, "Bearer hardcoded-token")\n'
                '        return build\n'
                '    else:\n'
                '        KEY = "Authorization"\n'
                'build = configure(True)\n'
                'configure(False)\n'
                'build()',
                [5],
            ),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_escape_tracking_uses_reaching_same_name_definition(self):
        safe_cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        def build():\n'
                '            options[KEY] = "hardcoded-secret"\n'
                '        build()\n'
                '    else:\n'
                '        KEY = "password"\n'
                '        def build():\n'
                '            pass\n'
                '        return build\n'
                'configure(True)',
            ),
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        build = lambda: options.__setitem__(KEY, "hardcoded-secret")\n'
                '        build()\n'
                '    else:\n'
                '        KEY = "password"\n'
                '        build = lambda: None\n'
                '        return build\n'
                'configure(True)',
            ),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

        hardcoded_source = (
            'def configure(flag):\n'
            '    global KEY\n'
            '    if flag:\n'
            '        KEY = "username"\n'
            '        def build():\n'
            '            pass\n'
            '    else:\n'
            '        KEY = "password"\n'
            '        def build():\n'
            '            options[KEY] = "hardcoded-secret"\n'
            '        return build\n'
            'configure(False)'
        )
        self.assertEqual(hardcoded_password_literal_lines(hardcoded_source), [10])

    def test_callback_storage_escapes_and_local_alias_does_not(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        holder.build = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.build()", [5]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks[0] = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\ncallbacks[0]()", [5]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        holder.build = lambda: options.__setitem__(KEY, \"hardcoded-token\")\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\nholder.build()", [5]),
            (hardcoded_auth_tuple_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        holder.build = lambda: options.__setitem__(KEY, (\"elastic\", \"hardcoded-secret\"))\n    else:\n        KEY = \"basic_auth\"\nconfigure(True)\nconfigure(False)\nholder.build()", [5]),
            (hardcoded_authorization_header_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        holder.build = lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nholder.build()", [5]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        return callbacks\n    else:\n        KEY = \"password\"\ncallbacks = configure(True)\nconfigure(False)\ncallbacks[0]()", [5]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        def build():\n            options[KEY] = \"hardcoded-secret\"\n        alias = build\n        alias()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        build = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n        alias = build\n        alias()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        build = lambda: options.__setitem__(KEY, \"hardcoded-token\")\n        alias = build\n        alias()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        build = lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")\n        alias = build\n        alias()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_callable_results_do_not_escape_and_augmented_containers_do(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        def build():\n            options[KEY] = \"hardcoded-secret\"\n        return build()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        def build():\n            options[KEY] = \"hardcoded-secret\"\n        consume(build())\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        build = lambda: options.__setitem__(KEY, \"hardcoded-token\")\n        return build()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        build = lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")\n        consume(build())\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

        hardcoded_cases = (
            (hardcoded_password_literal_lines, "callbacks = []\nKEY = \"username\"\ndef configure(flag):\n    global KEY, callbacks\n    if flag:\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\ncallbacks[0]()", [6]),
            (hardcoded_password_literal_lines, "callbacks = {}\nKEY = \"username\"\ndef configure(flag):\n    global KEY, callbacks\n    if flag:\n        callbacks |= {\"build\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\ncallbacks[\"build\"]()", [6]),
            (hardcoded_single_auth_lines, "callbacks = []\nKEY = \"username\"\ndef configure(flag):\n    global KEY, callbacks\n    if flag:\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-token\")]\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\ncallbacks[0]()", [6]),
            (hardcoded_auth_tuple_lines, "callbacks = {}\nKEY = \"username\"\ndef configure(flag):\n    global KEY, callbacks\n    if flag:\n        callbacks |= {\"build\": lambda: options.__setitem__(KEY, (\"elastic\", \"hardcoded-secret\"))}\n    else:\n        KEY = \"basic_auth\"\nconfigure(True)\nconfigure(False)\ncallbacks[\"build\"]()", [6]),
            (hardcoded_authorization_header_lines, "callbacks = []\nKEY = \"x-trace\"\ndef configure(flag):\n    global KEY, callbacks\n    if flag:\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\ncallbacks[0]()", [6]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_augmented_callbacks_only_escape_with_their_container(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = {}\n        callbacks |= {\"build\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        callbacks[\"build\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        callbacks[0]()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = {}\n        callbacks |= {\"build\": lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")}\n        callbacks[\"build\"]()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        return callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        return callbacks\n    else:\n        KEY = \"password\"\ncallbacks = configure(True)\nconfigure(False)\ncallbacks[0]()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        alias = callbacks\n        return alias\n    else:\n        KEY = \"password\"\ncallbacks = configure(True)\nconfigure(False)\ncallbacks[0]()", [6]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = {}\n        callbacks |= {\"build\": lambda: options.__setitem__(KEY, \"hardcoded-api-key\")}\n        return callbacks\n    else:\n        KEY = \"api_key\"\ncallbacks = configure(True)\nconfigure(False)\ncallbacks[\"build\"]()", [6]),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        holder.saved = callbacks\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nholder.saved[0]()", [6]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_augmented_container_binding_and_escaping_closure_capture(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        callbacks = []\n        KEY = \"password\"\n        consume(callbacks)\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = {}\n        callbacks |= {\"build\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        callbacks[\"build\"]()\n    else:\n        callbacks = {}\n        KEY = \"password\"\n        consume(callbacks)\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        callbacks[0]()\n    else:\n        callbacks = []\n        KEY = \"api_key\"\n        consume(callbacks)\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        def dispatch():\n            callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = {}\n        callbacks |= {\"build\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        def dispatch():\n            callbacks[\"build\"]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        dispatch = lambda: callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        def dispatch():\n            callbacks[0]()\n        return dispatch\n    else:\n        callbacks = []\n        KEY = \"password\"\n        consume(callbacks)\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        def dispatch():\n            callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"api_key\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        def dispatch():\n            callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"Authorization\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_escaped_function_defaults_capture_augmented_containers(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        def dispatch(saved=callbacks):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        def dispatch(*, saved=callbacks):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        dispatch = lambda saved=callbacks: saved[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        alias = callbacks\n        def dispatch(saved=alias):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks, unused = [], None\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        def dispatch(saved=callbacks):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        [callbacks, unused] = [[], None]\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        def dispatch(saved=callbacks):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        def dispatch(saved=callbacks):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"api_key\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        def dispatch(saved=callbacks):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"Authorization\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_destructured_local_callback_containers_remain_frame_local(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks, unused = [], None\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        [callbacks, unused] = [[], None]\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks, unused = [], None\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        callbacks = []\n        KEY = \"password\"\n        consume(callbacks)\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks, unused = [], None\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        callbacks[0]()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_shallow_copy_defaults_capture_retained_callbacks(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        def dispatch(saved=callbacks.copy()):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        dispatch = lambda saved=callbacks.copy(): saved[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        def dispatch(saved=callbacks.copy()):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"api_key\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
            (hardcoded_authorization_header_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        def dispatch(*, saved=callbacks.copy()):\n            saved[0]()\n        return dispatch\n    else:\n        KEY = \"Authorization\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [6]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_alias_unpacking_respects_local_and_escaped_containers(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = ([], None)\n        callbacks, unused = pair\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = ([], None)\n        alias = pair\n        callbacks, unused = alias\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = [[], None]\n        [callbacks, unused] = pair\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = ([], None)\n        callbacks, unused = pair\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        callbacks[0]()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = ([], None)\n        callbacks, unused = pair\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        callbacks[0]()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = ([], None)\n        callbacks, unused = pair\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        return callbacks\n    else:\n        KEY = \"password\"\ncallbacks = configure(True)\nconfigure(False)\ncallbacks[0]()", [7]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = [[], None]\n        callbacks, unused = pair\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        return callbacks\n    else:\n        KEY = \"api_key\"\ncallbacks = configure(True)\nconfigure(False)\ncallbacks[0]()", [7]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_snapshot_copy_precedes_callback_insertion(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        def dispatch(saved=callbacks.copy()):\n            return len(saved)\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = {}\n        dispatch = lambda saved=callbacks.copy(): len(saved)\n        callbacks |= {\"build\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        callbacks[\"build\"]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        def dispatch(saved=callbacks.copy()):\n            return len(saved)\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"api_key\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()"),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        def dispatch(saved=callbacks.copy()):\n            return len(saved)\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"Authorization\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_escaped_parent_retains_destructured_child_container(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = [[], None]\n        holder.pair = pair\n        callbacks, unused = pair\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [8]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = ([], None)\n        holder.pair = pair\n        callbacks, unused = pair\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [8]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = [[], None]\n        holder.pair = pair\n        alias = pair\n        callbacks, unused = alias\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [9]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = [[], None]\n        holder.pair = pair\n        callbacks, unused = pair\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [8]),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        pair = [[], None]\n        holder.pair = pair\n        callbacks, unused = pair\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [8]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_shallow_copy_keeps_existing_named_child_containers(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        parent = [callbacks]\n        def dispatch(saved=parent.copy()):\n            saved[0][0]()\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [9]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        parent = [callbacks]\n        dispatch = lambda saved=parent.copy(): saved[0][0]()\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        return dispatch\n    else:\n        KEY = \"api_key\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [8]),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        parent = {\"callbacks\": callbacks}\n        def dispatch(saved=parent.copy()):\n            saved[\"callbacks\"][0]()\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        return dispatch\n    else:\n        KEY = \"Authorization\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [9]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_exported_parent_resolves_named_child_container_bindings(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        pair = [callbacks, None]\n        holder.pair = pair\n        child, _ = pair\n        child += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [9]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        pair = (callbacks, None)\n        holder.pair = pair\n        alias = pair\n        child, _ = alias\n        child += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [10]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        pair = [callbacks, None]\n        holder.pair = pair\n        child, _ = pair\n        child += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [9]),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        pair = [callbacks, None]\n        holder.pair = pair\n        child, _ = pair\n        child += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nholder.pair[0][0]()", [9]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_shallow_copy_does_not_retain_later_parent_or_name_rebindings(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        parent = [callbacks]\n        def dispatch(saved=parent.copy()):\n            return len(saved[0])\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        parent = []\n        def dispatch(saved=parent.copy()):\n            return len(saved)\n        parent += [callbacks]\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_exported_starred_parent_keeps_existing_child_references(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = [callbacks]\n        parent = [*source]\n        holder.parent = parent\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.parent[0][0]()", [9]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = (callbacks,)\n        parent = (*source,)\n        holder.parent = parent\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.parent[0][0]()", [9]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = [callbacks]\n        alias = source\n        parent = [*alias]\n        holder.parent = parent\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.parent[0][0]()", [10]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = [callbacks]\n        parent = [*source]\n        holder.parent = parent\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\nholder.parent[0][0]()", [9]),
            (hardcoded_authorization_header_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = [callbacks]\n        parent = [*source]\n        holder.parent = parent\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nholder.parent[0][0]()", [9]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = [callbacks]\n        parent = [*source]\n        def dispatch(saved=parent.copy()):\n            saved[0][0]()\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        return dispatch\n    else:\n        KEY = \"password\"\ndispatch = configure(True)\nconfigure(False)\ndispatch()", [10]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_starred_parent_does_not_capture_future_iterable_additions(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = []\n        parent = [*source]\n        holder.parent = parent\n        source += [callbacks]\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        first = []\n        source = [first]\n        parent = [*source]\n        holder.parent = parent\n        callbacks = []\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = []\n        parent = [*source]\n        holder.parent = parent\n        source += [callbacks]\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        callbacks[0]()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = []\n        parent = [*source]\n        holder.parent = parent\n        source += [callbacks]\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        callbacks[0]()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_dict_starred_expansion_keeps_keys_not_callback_values(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = {\"callbacks\": callbacks}\n        parent = [*source]\n        holder.parent = parent\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = {\"callbacks\": callbacks}\n        parent = (*source,)\n        holder.parent = parent\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = {\"callbacks\": callbacks}\n        alias = source\n        parent = [*alias]\n        holder.parent = parent\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        callbacks[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = {\"callbacks\": callbacks}\n        parent = [*source]\n        holder.parent = parent\n        callbacks += [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        callbacks[0]()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        callbacks = []\n        source = {\"callbacks\": callbacks}\n        parent = [*source]\n        holder.parent = parent\n        callbacks += [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        callbacks[0]()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_frame_local_collection_callbacks_do_not_escape_implicitly(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        parent = [*source]\n        holder.parent = parent\n        source[\"callback\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        parent = (*source,)\n        holder.parent = parent\n        source[\"callback\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: options.__setitem__(KEY, \"hardcoded-api-key\")}\n        parent = [*source]\n        holder.parent = parent\n        source[\"callback\"]()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")}\n        parent = [*source]\n        holder.parent = parent\n        source[\"callback\"]()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        source[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        alias = source\n        parent = [*alias]\n        holder.parent = parent\n        source[\"callback\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_escaped_collection_callbacks_are_still_detected(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        holder.source = source\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source[\"callback\"]()", [5]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")}\n        holder.source = source.copy()\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source[\"callback\"]()", [5]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: options.__setitem__(KEY, \"hardcoded-api-key\")}\n        holder.source = source\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\nholder.source[\"callback\"]()", [5]),
            (hardcoded_authorization_header_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {\"callback\": lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")}\n        holder.source = source\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nholder.source[\"callback\"]()", [5]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        holder.source = source\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source[0]()", [5]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_global_and_nonlocal_callback_sinks_retain_collections(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "SAVED = None\nKEY = \"username\"\ndef configure(flag):\n    global KEY, SAVED\n    if flag:\n        source = [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        SAVED = source\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nSAVED[0]()", [6]),
            (hardcoded_password_literal_lines, "SAVED = None\nKEY = \"username\"\ndef configure(flag):\n    global KEY, SAVED\n    if flag:\n        source = [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        alias = source\n        SAVED = alias\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nSAVED[0]()", [6]),
            (hardcoded_single_auth_lines, "SAVED = None\nKEY = \"username\"\ndef configure(flag):\n    global KEY, SAVED\n    if flag:\n        source = [lambda: options.__setitem__(KEY, \"hardcoded-api-key\")]\n        SAVED = source\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\nSAVED[0]()", [6]),
            (hardcoded_authorization_header_lines, "SAVED = None\nKEY = \"x-trace\"\ndef configure(flag):\n    global KEY, SAVED\n    if flag:\n        source = [lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")]\n        SAVED = source\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nSAVED[0]()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef outer():\n    saved = None\n    def configure(flag):\n        nonlocal saved\n        global KEY\n        if flag:\n            source = [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n            saved = source\n        else:\n            KEY = \"password\"\n    configure(True)\n    configure(False)\n    saved[0]()\nouter()", [8]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_indexed_callback_stores_only_escape_with_container(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source[\"cb\"] = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n        source[\"cb\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        alias = source\n        alias[\"cb\"] = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n        alias[\"cb\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source[\"cb\"] = lambda: options.__setitem__(KEY, \"hardcoded-api-key\")\n        source[\"cb\"]()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source[\"cb\"] = lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")\n        source[\"cb\"]()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        holder.source = source.copy()\n        source[\"cb\"] = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n        source[\"cb\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        source[0:0] = [lambda: options.__setitem__(KEY, \"hardcoded-secret\")]\n        source[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source[\"cb\"] = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n        holder.source = source\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source['cb']()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        holder.source = source\n        source[\"cb\"] = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source['cb']()", [7]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source[\"cb\"] = lambda: options.__setitem__(KEY, \"hardcoded-secret\")\n        holder.source = source.copy()\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source['cb']()", [6]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source[\"cb\"] = lambda: options.__setitem__(KEY, \"hardcoded-api-key\")\n        holder.source = source\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\nholder.source['cb']()", [6]),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source[\"cb\"] = lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\")\n        holder.source = source\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nholder.source['cb']()", [6]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

    def test_known_local_collection_mutators_do_not_escape_callbacks(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        source.append(lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        source[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source.update({\"cb\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")})\n        source[\"cb\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source.setdefault(\"cb\", lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        source[\"cb\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = set()\n        source.add(lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        for callback in source:\n            callback()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        source.append(lambda: options.__setitem__(KEY, \"hardcoded-api-key\"))\n        source[0]()\n    else:\n        KEY = \"api_key\"\nconfigure(True)"),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source.update(cb=lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\"))\n        source[\"cb\"]()\n    else:\n        KEY = \"Authorization\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        alias = source\n        alias.append(lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        alias[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        holder.source = source.copy()\n        source.append(lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        source[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_builtin_empty_container_constructors_keep_local_mutators_private(self):
        safe_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = list()\n        source.append(lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        source[0]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = dict()\n        source.setdefault(\"cb\", lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        source[\"cb\"]()\n    else:\n        KEY = \"password\"\nconfigure(True)"),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_known_mutators_retain_callbacks_when_receiver_escapes(self):
        hardcoded_cases = (
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        source.append(lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        holder.source = source\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source[0]()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        holder.source = source\n        source.append(lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        pass\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source[0]()", [7]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        source.append(lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        holder.source = source.copy()\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source[0]()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source.update({\"cb\": lambda: options.__setitem__(KEY, \"hardcoded-secret\")})\n        holder.source = source\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source[\"cb\"]()", [6]),
            (hardcoded_password_literal_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source.setdefault(\"cb\", lambda: options.__setitem__(KEY, \"hardcoded-secret\"))\n        holder.source = source\n    else:\n        KEY = \"password\"\nconfigure(True)\nconfigure(False)\nholder.source[\"cb\"]()", [6]),
            (hardcoded_single_auth_lines, "KEY = \"username\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = []\n        source.append(lambda: options.__setitem__(KEY, \"hardcoded-api-key\"))\n        holder.source = source\n    else:\n        KEY = \"api_key\"\nconfigure(True)\nconfigure(False)\nholder.source[0]()", [6]),
            (hardcoded_authorization_header_lines, "KEY = \"x-trace\"\ndef configure(flag):\n    global KEY\n    if flag:\n        source = {}\n        source.update(cb=lambda: headers.setdefault(KEY, \"Bearer hardcoded-token\"))\n        holder.source = source\n    else:\n        KEY = \"Authorization\"\nconfigure(True)\nconfigure(False)\nholder.source[\"cb\"]()", [6]),
        )
        for scanner, source, expected in hardcoded_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)


    def test_nested_synchronous_mutator_uses_enclosing_private_container(self):
        safe_cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        source = []\n'
                '        def build():\n'
                '            source.append(lambda: options.__setitem__(KEY, "hardcoded-secret"))\n'
                '            source[0]()\n'
                '        build()\n'
                '    else:\n'
                '        KEY = "password"\n'
                'configure(True)',
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        source = {}\n'
                '        def build():\n'
                '            source.setdefault("cb", lambda: options.__setitem__(KEY, "hardcoded-api-key"))\n'
                '            source["cb"]()\n'
                '        build()\n'
                '    else:\n'
                '        KEY = "api_key"\n'
                'configure(True)',
            ),
        )
        for scanner, source in safe_cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), [])

    def test_private_container_extracted_callbacks_escape_independently(self):
        cases = (
            (
                hardcoded_password_literal_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        source = []\n'
                '        source.append(lambda: options.__setitem__(KEY, "hardcoded-secret"))\n'
                '        return source.pop()\n'
                '    KEY = "password"\n'
                'saved = configure(True)\n'
                'configure(False)\n'
                'saved()',
                [6],
            ),
            (
                hardcoded_single_auth_lines,
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        source = {}\n'
                '        alias = source\n'
                '        alias.update(cb=lambda: options.__setitem__(KEY, "hardcoded-api-key"))\n'
                '        saved = alias.pop("cb")\n'
                '        return saved\n'
                '    KEY = "api_key"\n'
                'saved = configure(True)\n'
                'configure(False)\n'
                'saved()',
                [7],
            ),
            (
                hardcoded_authorization_header_lines,
                'KEY = "x-trace"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        source = {}\n'
                '        source["cb"] = lambda: headers.setdefault(KEY, "Bearer hardcoded-token")\n'
                '        consume(source.get("cb"))\n'
                '    else:\n'
                '        KEY = "Authorization"\n'
                'configure(True)\n'
                'configure(False)',
                [6],
            ),
        )
        for scanner, source, expected in cases:
            with self.subTest(scanner=scanner.__name__, source=source):
                self.assertEqual(scanner(source), expected)

        safe_source = (
            'KEY = "username"\n'
            'def configure(flag):\n'
            '    global KEY\n'
            '    if flag:\n'
            '        source = []\n'
            '        source.append(lambda: options.__setitem__(KEY, "hardcoded-secret"))\n'
            '        callback = source.pop()\n'
            '        callback()\n'
            '    else:\n'
            '        KEY = "password"\n'
            'configure(True)'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe_source), [])

    def test_aliased_private_container_accessors_retain_escaped_callbacks(self):
        cases = (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        )
        for scanner, rebound, value in cases:
            expression = (
                'headers.setdefault(KEY, "' + value + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + value + '")'
            )
            source = (
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        source = []\n'
                '        source.append(lambda: ' + expression + ')\n'
                '        extract = source.pop\n'
                '        alias = extract\n'
                '        return alias()\n'
                '    KEY = "' + rebound + '"\n'
                'saved = configure(True)\n'
                'configure(False)\n'
                'saved()'
            )
            with self.subTest(scanner=scanner.__name__):
                self.assertEqual(scanner(source), [6])

        safe = (
            'KEY = "username"\n'
            'def configure(flag):\n'
            '    global KEY\n'
            '    if flag:\n'
            '        source = []\n'
            '        source.append(lambda: options.__setitem__(KEY, "hardcoded-secret"))\n'
            '        extract = source.pop\n'
            '        extract()()\n'
            '    else:\n'
            '        KEY = "password"\n'
            'configure(True)'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe), [])

    def test_constant_key_extraction_does_not_export_private_callback(self):
        for accessor in (
            'source["exported"]',
            'source.get("exported")',
            'source.pop("exported")',
            'source[selection]',
        ):
            safe = (
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        selection = "exported"\n'
                '        source = {"private": lambda: options.__setitem__(KEY, "hardcoded-secret"), '
                '"exported": lambda: None}\n'
                '        return ' + accessor + '\n'
                '    else:\n'
                '        KEY = "password"\n'
                'saved = configure(True)\n'
                'configure(False)\n'
                'saved()'
            )
            with self.subTest(accessor=accessor):
                self.assertEqual(hardcoded_password_literal_lines(safe), [])

        positive = (
            'KEY = "username"\n'
            'def configure(flag):\n'
            '    global KEY\n'
            '    if flag:\n'
            '        source = {"private": lambda: None, '
            '"exported": lambda: options.__setitem__(KEY, "hardcoded-secret")}\n'
            '        return source["exported"]\n'
            '    else:\n'
                '        KEY = "password"\n'
            'saved = configure(True)\n'
            'configure(False)\n'
            'saved()'
        )
        self.assertEqual(hardcoded_password_literal_lines(positive), [5])

    def test_constant_key_extraction_respects_indexed_and_update_stores(self):
        safe = (
            'KEY = "username"\n'
            'def configure(flag):\n'
            '    global KEY\n'
            '    if flag:\n'
            '        source = {}\n'
            '        source.update(private=lambda: options.__setitem__(KEY, "hardcoded-secret"))\n'
            '        source["exported"] = lambda: None\n'
            '        return source.get("exported")\n'
            '    else:\n'
                '        KEY = "password"\n'
            'saved = configure(True)\n'
            'configure(False)\n'
            'saved()'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe), [])

        positive = safe.replace(
            'source["exported"] = lambda: None',
            'source["exported"] = lambda: options.__setitem__(KEY, "hardcoded-secret")',
        ).replace(
            'source.update(private=lambda: options.__setitem__(KEY, "hardcoded-secret"))',
            'source.update(private=lambda: None)',
        )
        self.assertEqual(hardcoded_password_literal_lines(positive), [7])

    def test_destructured_accessor_aliases_escape_from_private_collections(self):
        cases = (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        )
        for scanner, rebound, value in cases:
            expression = (
                'headers.setdefault(KEY, "' + value + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + value + '")'
            )
            source = (
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        source = []\n'
                '        source.append(lambda: ' + expression + ')\n'
                '        extract, unused = source.pop, None\n'
                '        return extract()\n'
                '    else:\n'
                '        KEY = "' + rebound + '"\n'
                'saved = configure(True)\n'
                'configure(False)\n'
                'saved()'
            )
            with self.subTest(scanner=scanner.__name__):
                self.assertEqual(scanner(source), [6])

        safe = (
            'KEY = "username"\n'
            'def configure(flag):\n'
            '    global KEY\n'
            '    if flag:\n'
            '        source = []\n'
            '        source.append(lambda: options.__setitem__(KEY, "hardcoded-secret"))\n'
            '        extract, unused = source.pop, None\n'
            '        extract()()\n'
            '    else:\n'
            '        KEY = "password"\n'
            'configure(True)'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe), [])

    def test_starred_list_extraction_does_not_miss_shifted_indices(self):
        cases = (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        )
        for scanner, rebound, value in cases:
            expression = (
                'headers.setdefault(KEY, "' + value + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + value + '")'
            )
            source = (
                'KEY = "username"\n'
                'def configure(flag):\n'
                '    global KEY\n'
                '    if flag:\n'
                '        source = [*[], lambda: ' + expression + ']\n'
                '        return source[0]\n'
                '    else:\n'
                '        KEY = "' + rebound + '"\n'
                'saved = configure(True)\n'
                'configure(False)\n'
                'saved()'
            )
            with self.subTest(scanner=scanner.__name__):
                self.assertEqual(scanner(source), [5])

        safe = (
            'KEY = "username"\n'
            'def configure(flag):\n'
            '    global KEY\n'
            '    if flag:\n'
            '        source = [*[], lambda: options.__setitem__(KEY, "hardcoded-secret")]\n'
            '        source[0]()\n'
            '    else:\n'
            '        KEY = "password"\n'
            'configure(True)'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe), [])

    def test_selected_dict_update_keyword_overrides_mapping_callback(self):
        cases = (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        )
        for scanner, rebound, value in cases:
            expression = (
                'headers.setdefault(KEY, "' + value + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + value + '")'
            )
            def build(mapping_expr, keyword_expr):
                return (
                    'KEY = "username"\n'
                    'def configure(flag):\n'
                    '    global KEY\n'
                    '    if flag:\n'
                    '        source = {}\n'
                    '        source.update({"exported": lambda: ' + mapping_expr
                    + '}, exported=lambda: ' + keyword_expr + ')\n'
                    '        return source["exported"]\n'
                    '    else:\n'
                    '        KEY = "' + rebound + '"\n'
                    'saved = configure(True)\n'
                    'configure(False)\n'
                    'saved()'
                )
            with self.subTest(scanner=scanner.__name__):
                self.assertEqual(scanner(build(expression, 'None')), [])
                self.assertEqual(scanner(build('None', expression)), [6])

    def test_unpack_outer_scope_accessor_method_in_nested_function(self):
        cases = (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        )
        for scanner, rebound, value in cases:
            expression = (
                'headers.setdefault(KEY, "' + value + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + value + '")'
            )
            source = (
                'KEY = "username"\n'
                'def outer():\n'
                '    source = []\n'
                '    pair = (source.pop, None)\n'
                '    def configure(flag):\n'
                '        global KEY\n'
                '        if flag:\n'
                '            source.append(lambda: ' + expression + ')\n'
                '            extract, unused = pair\n'
                '            return extract()\n'
                '        else:\n'
                '            KEY = "' + rebound + '"\n'
                '    return configure\n'
                'configure = outer()\n'
                'saved = configure(True)\n'
                'configure(False)\n'
                'saved()'
            )
            with self.subTest(scanner=scanner.__name__):
                self.assertEqual(scanner(source), [8])

        safe = (
            'KEY = "username"\n'
            'def outer():\n'
            '    source = []\n'
            '    pair = (source.pop, None)\n'
            '    def configure(flag):\n'
            '        global KEY\n'
            '        if flag:\n'
            '            source.append(lambda: options.__setitem__(KEY, "hardcoded-secret"))\n'
            '            extract, unused = pair\n'
            '            extract()()\n'
            '        else:\n'
            '            KEY = "password"\n'
            '    configure(True)\n'
            'outer()'
        )
        self.assertEqual(hardcoded_password_literal_lines(safe), [])

    def test_fixed_length_starred_sequence_respects_selected_index(self):
        cases = (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        )
        for scanner, rebound, value in cases:
            expression = (
                'headers.setdefault(KEY, "' + value + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + value + '")'
            )
            def sample(first, spread):
                return (
                    'KEY = "username"\n'
                    'def configure(flag):\n'
                    '    global KEY\n'
                    '    if flag:\n'
                    '        source = [' + first + ', *' + spread + ']\n'
                    '        return source[1]\n'
                    '    else:\n'
                    '        KEY = "' + rebound + '"\n'
                    'saved = configure(True)\n'
                    'configure(False)\n'
                    'saved()'
                )
            hardcoded = 'lambda: ' + expression
            safe = 'lambda: None'
            with self.subTest(scanner=scanner.__name__):
                # Credential callback at index 0 is never exported.
                self.assertEqual(scanner(sample(hardcoded, '[' + safe + ']')), [])
                # Credential callback in the statically expanded slot is exported.
                self.assertEqual(scanner(sample(safe, '[' + hardcoded + ']')), [5])

        nested = (
            'KEY = "username"\n'
            'def configure(flag):\n'
            '    global KEY\n'
            '    if flag:\n'
            '        prefix = [lambda: None]\n'
            '        source = [lambda: options.__setitem__(KEY, "hardcoded-secret"), *prefix]\n'
            '        return source[1]\n'
            '    else:\n'
            '        KEY = "password"\n'
            'saved = configure(True)\n'
            'configure(False)\n'
            'saved()'
        )
        self.assertEqual(hardcoded_password_literal_lines(nested), [])

    def test_repeated_selected_dict_slots_honor_definite_overwrite(self):
        for scanner, key, value in (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        ):
            dangerous = (
                'headers.setdefault(KEY, "' + value + '")'
                if key == "Authorization"
                else 'options.__setitem__(KEY, "' + value + '")'
            )

            def snippet(first, last, uncertain=False):
                middle = (
                    '        if uncertain:\n'
                    '            source["exported"] = lambda: ' + last + '\n'
                    if uncertain else
                    '        source["exported"] = lambda: ' + last + '\n'
                )
                return (
                    'KEY = "username"\n'
                    'def configure(flag, uncertain=False):\n'
                    '    global KEY\n'
                    '    if flag:\n'
                    '        source = {}\n'
                    '        source["exported"] = lambda: ' + first + '\n'
                    + middle +
                    '        return source["exported"]\n'
                    '    else:\n'
                    '        KEY = "' + key + '"\n'
                    'saved = configure(True)\n'
                    'configure(False)\n'
                    'saved()'
                )

            with self.subTest(scanner=scanner.__name__):
                self.assertEqual(scanner(snippet(dangerous, "None")), [])
                self.assertEqual(scanner(snippet("None", dangerous)), [7])
                self.assertEqual(scanner(snippet(dangerous, "None", True)), [6])

    def test_fixed_key_update_callbacks_respect_later_definite_write(self):
        scanners = (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        )
        for scanner, rebound, secret in scanners:
            write = (
                'headers.setdefault(KEY, "' + secret + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + secret + '")'
            )
            for update_callback, replacement, conditional, expected in (
                (write, "None", False, []),
                ("None", write, False, [7]),
                (write, "None", True, [6]),
            ):
                assignment = (
                    '        if uncertain:\n'
                    '            source["exported"] = lambda: ' + replacement + '\n'
                    if conditional
                    else '        source["exported"] = lambda: ' + replacement + '\n'
                )
                source = (
                    'KEY = "username"\n'
                    'def configure(flag, uncertain=False):\n'
                    '    global KEY\n'
                    '    if flag:\n'
                    '        source = {}\n'
                    '        source.update({"exported": lambda: ' + update_callback + '})\n'
                    + assignment
                    + '        return source["exported"]\n'
                    '    else:\n'
                    '        KEY = "' + rebound + '"\n'
                    'saved = configure(True)\n'
                    'configure(False)\n'
                    'saved()'
                )
                with self.subTest(scanner=scanner.__name__, conditional=conditional, expected=expected):
                    self.assertEqual(scanner(source), expected)

    def test_fixed_key_overwrites_require_identical_receiver_bindings(self):
        for scanner, rebound, literal in (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        ):
            callback = (
                'headers.setdefault(KEY, "' + literal + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + literal + '")'
            )
            for use_update in (True, False):
                store = (
                    '        source.update({"exported": lambda: ' + callback + '})\n'
                    if use_update else
                    '        source["exported"] = lambda: ' + callback + '\n'
                )
                unsafe = (
                    'KEY = "username"\n'
                    'def configure(flag, choose_left=False):\n'
                    '    global KEY\n'
                    '    if flag:\n'
                    '        left = {}\n'
                    '        right = {}\n'
                    '        if choose_left:\n'
                    '            source = left\n'
                    '        else:\n'
                    '            source = right\n'
                    + store
                    + '        right["exported"] = lambda: None\n'
                    '        return source["exported"]\n'
                    '    else:\n'
                    '        KEY = "' + rebound + '"\n'
                    'saved = configure(True, True)\n'
                    'configure(False)\n'
                    'saved()'
                )
                with self.subTest(scanner=scanner.__name__, use_update=use_update):
                    self.assertEqual(scanner(unsafe), [11])

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
