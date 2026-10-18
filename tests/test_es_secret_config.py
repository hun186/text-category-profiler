import ast
import copy
import io
from itertools import product
import os
import re
import runpy
import tokenize
import textwrap
import tempfile
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

        def _visit_comprehension(self, node, result_nodes):
            # In Python 3 comprehensions have their own implicit function
            # scope. The first iterable alone is evaluated in the enclosing
            # scope; generator targets, filters, other iterables, and the
            # produced element all execute in the comprehension frame.
            self._mark(node)
            if not node.generators:
                for result in result_nodes:
                    self.visit(result)
                return
            self.visit(node.generators[0].iter)
            # Comprehension frames do not close over class namespaces.
            # The leading iterable above still executes in that class scope,
            # but later iterables, targets and produced values do not.
            self._new_scope(node, self._function_parent_scope())
            self.scope_stack.append(node)
            first = node.generators[0]
            self.visit(first.target)
            for predicate in first.ifs:
                self.visit(predicate)
            for generator in node.generators[1:]:
                self.visit(generator.iter)
                self.visit(generator.target)
                for predicate in generator.ifs:
                    self.visit(predicate)
            for result in result_nodes:
                self.visit(result)
            self.scope_stack.pop()

        def visit_ListComp(self, node):
            self._visit_comprehension(node, [node.elt])

        def visit_SetComp(self, node):
            self._visit_comprehension(node, [node.elt])

        def visit_GeneratorExp(self, node):
            self._visit_comprehension(node, [node.elt])

        def visit_DictComp(self, node):
            self._visit_comprehension(node, [node.key, node.value])

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

            def fixed_slot_receiver_records(store):
                """Candidate (identities, source name) for fixed-key writes."""
                if selected is unknown_selection or not isinstance(
                    store, (ast.Assign, ast.AnnAssign, ast.NamedExpr)
                ):
                    return []
                targets = store.targets if isinstance(store, ast.Assign) else [store.target]
                return [
                    (identities, target.value)
                    for target in targets
                    if isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and static_selection(target.slice) == selected
                    if (identities := reaching_containers(target.value))
                    and identities & containers
                ]

            def fixed_slot_receiver_sets(store):
                return [identities for identities, _name in fixed_slot_receiver_records(store)]

            def fixed_slot_write(store):
                return bool(fixed_slot_receiver_records(store))

            def alias_is_stable(earlier_name, later_name, first_pos, last_pos):
                """Same lexical alias and no intervening rebinding of that alias."""
                if not (
                    isinstance(earlier_name, ast.Name)
                    and isinstance(later_name, ast.Name)
                    and earlier_name.id == later_name.id
                ):
                    return False
                earlier_owner = container_binding_owner(
                    earlier_name.id, getattr(earlier_name, "_binding_scope", module_scope)
                )
                later_owner = container_binding_owner(
                    later_name.id, getattr(later_name, "_binding_scope", module_scope)
                )
                if earlier_owner is not later_owner:
                    return False
                return not any(
                    isinstance(candidate, ast.Name)
                    and isinstance(candidate.ctx, (ast.Store, ast.Del))
                    and candidate.id == earlier_name.id
                    and container_binding_owner(
                        candidate.id, getattr(candidate, "_binding_scope", module_scope)
                    ) is earlier_owner
                    and first_pos < _node_position(candidate) < last_pos
                    for candidate in ast.walk(tree)
                )

            def definitely_same_receiver(
                write, earlier_identities, earlier_name=None, earlier_pos=None
            ):
                # Uniquely resolved identities match as before. An ambiguous
                # identity set can also be safe when both stores use the very
                # same stable alias: each runtime path overwrites its own object.
                for later_identities, later_name in fixed_slot_receiver_records(write):
                    if (
                        len(earlier_identities) == 1
                        and later_identities == earlier_identities
                    ):
                        return True
                    if (
                        earlier_pos is not None
                        and later_identities == earlier_identities
                        and alias_is_stable(
                            earlier_name, later_name, earlier_pos, _node_position(write)
                        )
                    ):
                        return True
                return False

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
                            and definitely_same_receiver(
                                write, stored_in, store.func.value, _node_position(store)
                            )
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
                                next_store,
                                fixed_slot_receiver_records(store)[0][0],
                                fixed_slot_receiver_records(store)[0][1],
                                _node_position(store),
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
        # Python evaluates an assignment's RHS before storing its target.
        # Freeze eager aliases at the position immediately before the store,
        # so `unused, password = (password, None)` captures the imported
        # password in `unused`, not the newly assigned None.
        capture_eager_expression_names(
            value, (position[0], position[1] - 1), lexical_scope
        )
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

        # Resolve returns of source-visible callables, including calls with
        # arguments. Unknown providers remain opaque: never consider their
        # input arguments as credentials unless a known return uses them.
        # Dynamic *args/**kwargs cannot be bound precisely here.
        if (
            not any(isinstance(arg, ast.Starred) for arg in node.args)
            and all(keyword.arg is not None for keyword in node.keywords)
        ):
            # A factory IIFE may *return* a lambda which a surrounding
            # zero-argument Call then immediately invokes. Model the outer
            # invocations inside the factory return, so its original defaults
            # remain captured; do not execute merely returned callables.
            factory_call = node.func
            extra_calls = 0
            while (
                isinstance(factory_call, ast.Call)
                and not factory_call.args and not factory_call.keywords
            ):
                extra_calls += 1
                factory_call = factory_call.func
            if extra_calls and not node.args and not node.keywords:
                for factory in _resolve_bound_nodes(
                    factory_call, bindings, before_position
                ):
                    if isinstance(factory, ast.Lambda):
                        returned_lambda = factory.body
                    elif (
                        isinstance(factory, ast.FunctionDef)
                        and not factory.decorator_list
                        and len(factory.body) == 1
                        and isinstance(factory.body[0], ast.Return)
                    ):
                        returned_lambda = factory.body[0].value
                    else:
                        continue
                    if not isinstance(returned_lambda, ast.Lambda):
                        continue
                    invoked = returned_lambda
                    for _ in range(extra_calls):
                        invoked = ast.copy_location(
                            ast.Call(func=invoked, args=[], keywords=[]),
                            node,
                        )
                    if isinstance(factory, ast.Lambda):
                        captured_factory = copy.copy(factory)
                        captured_factory.body = invoked
                    else:
                        captured_factory = copy.copy(factory)
                        captured_factory.body = [ast.copy_location(
                            ast.Return(value=invoked), factory.body[0]
                        )]
                    simulated = ast.copy_location(ast.Call(
                        func=captured_factory, args=[], keywords=[]
                    ), node)
                    values = _hardcoded_password_values(
                        simulated, bindings, before_position,
                        seen_names | {("chained-factory", id(factory))},
                    )
                    if values:
                        return values
            for callee in _resolve_bound_nodes(
                node.func, bindings, before_position
            ):
                returned = None
                if isinstance(callee, ast.Lambda):
                    arguments = callee.args
                    returned = callee.body
                elif isinstance(callee, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # An async call yields a coroutine, not the returned
                    # credential until awaited; do not equate the two.
                    if isinstance(callee, ast.AsyncFunctionDef):
                        continue
                    if callee.decorator_list or len(callee.body) != 1:
                        continue
                    if not isinstance(callee.body[0], ast.Return):
                        continue
                    arguments = callee.args
                    returned = callee.body[0].value
                else:
                    continue
                positional = [
                    *arguments.posonlyargs, *arguments.args
                ]
                supplied_defaults = len(arguments.defaults)
                defaults = {
                    argument.arg: default
                    for argument, default in zip(
                        positional[len(positional) - supplied_defaults:],
                        arguments.defaults,
                    )
                }
                defaults.update({
                    argument.arg: default
                    for argument, default in zip(
                        arguments.kwonlyargs, arguments.kw_defaults
                    )
                    if default is not None
                })
                # Python binds positional arguments first and then keywords.
                # Reject invalid/ambiguous invocations instead of attributing
                # the credential return to a call that cannot run.
                if len(node.args) > len(positional) and arguments.vararg is None:
                    continue
                provided = {
                    argument.arg: expression
                    for argument, expression in zip(positional, node.args)
                }
                if arguments.vararg is not None:
                    # Additional positional arguments are one runtime tuple,
                    # not ignored independent arguments.
                    provided[arguments.vararg.arg] = ast.copy_location(
                        ast.Tuple(
                            elts=list(node.args[len(positional):]),
                            ctx=ast.Load(),
                        ), node,
                    )
                valid = True
                positional_only = {
                    arg.arg for arg in arguments.posonlyargs
                }
                accepted = {
                    arg.arg for arg in [
                        *positional, *arguments.kwonlyargs
                    ]
                }
                keyword_extras = []
                for keyword in node.keywords:
                    if keyword.arg in provided:
                        valid = False
                        break
                    if keyword.arg in positional_only:
                        # A positional-only name can be a **kwargs key, but
                        # cannot assign the positional parameter itself.
                        if arguments.kwarg is None:
                            valid = False
                        else:
                            keyword_extras.append(keyword)
                        continue
                    if keyword.arg not in accepted:
                        if arguments.kwarg is None:
                            valid = False
                        else:
                            keyword_extras.append(keyword)
                        continue
                    provided[keyword.arg] = keyword.value
                if not valid:
                    continue
                if arguments.kwarg is not None:
                    provided[arguments.kwarg.arg] = ast.copy_location(
                        ast.Dict(
                            keys=[
                                ast.copy_location(
                                    ast.Constant(value=keyword.arg), node
                                ) for keyword in keyword_extras
                            ],
                            values=[
                                keyword.value for keyword in keyword_extras
                            ],
                        ), node,
                    )
                defaults.update(provided)
                if any(
                    arg.arg not in defaults
                    for arg in [*positional, *arguments.kwonlyargs]
                ):
                    continue
                token = ("callable-return", id(callee))
                if token in seen_names:
                    continue

                def expand_return_defaults(expression, captured=False,
                                           seen=None, active_defaults=None):
                    """Substitute default-backed names anywhere in a return AST.

                    Preserve every source-visible reaching alias. Defaults are
                    evaluated at definition time; a later module overwrite
                    cannot change their already captured values.
                    """
                    seen = set() if seen is None else set(seen)
                    active_defaults = (
                        defaults if active_defaults is None else active_defaults
                    )
                    if isinstance(expression, ast.Name):
                        if not captured and expression.id in active_defaults:
                            token = ("default-parameter", expression.id)
                            if token in seen:
                                return [expression]
                            return expand_return_defaults(
                                active_defaults[expression.id], True,
                                seen | {token}, active_defaults,
                            )
                        if captured:
                            token = ("default-source", id(expression))
                            if token not in seen:
                                candidates = _resolve_bound_nodes(
                                    expression, bindings,
                                    _node_position(expression),
                                )
                                alternatives = [
                                    candidate for candidate in candidates
                                    if candidate is not expression
                                    and not (
                                        isinstance(candidate, ast.Name)
                                        and candidate.id == expression.id
                                    )
                                ]
                                if alternatives:
                                    expanded = []
                                    for candidate in alternatives:
                                        expanded.extend(
                                            expand_return_defaults(
                                                candidate, True, seen | {token},
                                                active_defaults,
                                            )
                                        )
                                    return expanded
                        return [expression]
                    if (
                        isinstance(expression, ast.Call)
                        and isinstance(expression.func, ast.Lambda)
                        and not expression.args and not expression.keywords
                    ):
                        # A nested lambda that is immediately called runs
                        # its body now, so the outer default-backed parameter
                        # remains visible to the returned credential scan.
                        # A merely returned lambda must stay deferred.
                        nested_args = expression.func.args
                        positional = [
                            *nested_args.posonlyargs, *nested_args.args
                        ]
                        if (
                            len(nested_args.defaults) == len(positional)
                            and all(
                                default is not None
                                for default in nested_args.kw_defaults
                            )
                        ):
                            # A zero-argument IIFE may still accept parameters
                            # through defaults. Evaluate those defaults in the
                            # enclosing scope *before* entering the inner lambda
                            # so outer captures survive shadowing and overwrites.
                            pairs = [
                                *(zip(positional, nested_args.defaults)),
                                *(zip(nested_args.kwonlyargs,
                                       nested_args.kw_defaults)),
                            ]
                            choices = [
                                expand_return_defaults(
                                    default, captured, seen, active_defaults
                                )
                                for _, default in pairs
                            ]
                            expanded = []
                            for combination in product(*choices):
                                inner_defaults = dict(active_defaults)
                                inner_defaults.update({
                                    parameter.arg: value
                                    for (parameter, _), value in zip(
                                        pairs, combination
                                    )
                                })
                                expanded.extend(expand_return_defaults(
                                    expression.func.body, captured, seen,
                                    inner_defaults,
                                ))
                            return expanded
                    if isinstance(expression, ast.Lambda):
                        # Materialize captured outer defaults in a *returned*
                        # lambda without executing its body. The body may be
                        # invoked only by an enclosing Call; local parameters
                        # shadow outer captures while default expressions are
                        # evaluated in the enclosing lexical environment.
                        arguments = expression.args
                        parameters = {
                            arg.arg for arg in [
                                *arguments.posonlyargs, *arguments.args,
                                *arguments.kwonlyargs,
                                *([arguments.vararg] if arguments.vararg else []),
                                *([arguments.kwarg] if arguments.kwarg else []),
                            ]
                        }
                        defaults_list = [
                            *arguments.defaults,
                            *(value for value in arguments.kw_defaults
                              if value is not None),
                        ]
                        default_choices = [
                            expand_return_defaults(
                                value, captured, seen, active_defaults
                            ) for value in defaults_list
                        ]
                        inner_defaults = {
                            key: value for key, value in active_defaults.items()
                            if key not in parameters
                        }
                        bodies = expand_return_defaults(
                            expression.body, captured, seen, inner_defaults
                        )
                        variants = []
                        for combination in product(*default_choices):
                            for body in bodies:
                                replacement = copy.copy(expression)
                                replacement.args = copy.copy(arguments)
                                count = len(arguments.defaults)
                                replacement.args.defaults = list(combination[:count])
                                remaining = iter(combination[count:])
                                replacement.args.kw_defaults = [
                                    next(remaining) if value is not None else None
                                    for value in arguments.kw_defaults
                                ]
                                replacement.body = body
                                variants.append(replacement)
                        return variants
                    if not isinstance(expression, ast.AST) or isinstance(
                        expression, (
                            ast.FunctionDef, ast.AsyncFunctionDef,
                            ast.GeneratorExp,
                        ),
                    ):
                        return [expression]
                    variants = [copy.copy(expression)]
                    for field, field_value in ast.iter_fields(expression):
                        if isinstance(field_value, ast.AST):
                            candidates = expand_return_defaults(
                                field_value, captured, seen, active_defaults
                            )
                            next_variants = []
                            for variant in variants:
                                for candidate in candidates:
                                    replacement = copy.copy(variant)
                                    setattr(replacement, field, candidate)
                                    next_variants.append(replacement)
                            variants = next_variants
                        elif isinstance(field_value, list):
                            choices = [
                                expand_return_defaults(
                                    value, captured, seen, active_defaults
                                )
                                if isinstance(value, ast.AST) else [value]
                                for value in field_value
                            ]
                            next_variants = []
                            for variant in variants:
                                for combination in product(*choices):
                                    replacement = copy.copy(variant)
                                    setattr(replacement, field, list(combination))
                                    next_variants.append(replacement)
                            variants = next_variants
                    return variants

                def returned_passwords(expression, active):
                    secrets = []
                    for expanded in expand_return_defaults(expression):
                        secrets.extend(_hardcoded_password_values(
                            expanded, bindings, before_position, active
                        ))
                    return secrets

                if returned is not None:
                    found = returned_passwords(
                        returned, seen_names | {token}
                    )
                    if found:
                        return found

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
    """Return Authorization values written through mapping mutator calls."""
    if not isinstance(node, ast.Call):
        return []

    # A bound mapping method can be stored in a local alias, including an
    # alias of another alias. Resolve through the same source-ordered bindings
    # used for credential expressions, not just a direct ast.Attribute call.
    methods = [
        candidate.attr
        for candidate in _resolve_bound_nodes(node.func, bindings, before_position)
        if isinstance(candidate, ast.Attribute)
    ]
    if not methods:
        return []

    values = []
    if any(method in {"setdefault", "__setitem__"} for method in methods):
        if (
            len(node.args) >= 2
            and _static_key_matches(
                node.args[0], "authorization", bindings, before_position,
                case_insensitive=True,
            )
        ):
            values.append(node.args[1])

    if "update" not in methods:
        return values

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

    def _local_imported_python_paths(self, importing_path, source):
        """Resolve static project-local imports without executing modules."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        resolved = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [(alias.name, 0) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [(node.module, node.level)]
                if node.level and node.module is None:
                    # from . import * reads the current package __init__.py;
                    # for .., locate the parent package at that level.
                    modules.append(("__init__", node.level))
                # from package import provider can load package/provider.py.
                modules.extend(
                    ((node.module + "." if node.module else "") + alias.name, node.level)
                    for alias in node.names if alias.name != "*"
                )
            else:
                continue

            for name, level in modules:
                if not name:
                    continue
                if level:
                    try:
                        bases = [importing_path.parents[level - 1]]
                    except IndexError:
                        continue
                else:
                    bases = [
                        importing_path.parent,
                        REPOSITORY_ROOT,
                        *ES_RUNTIME_DISCOVERY_ROOTS,
                    ]
                parts = name.split(".")
                if not all(part.isidentifier() for part in parts):
                    continue
                for base in bases:
                    stem = base.joinpath(*parts)
                    for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
                        if not candidate.is_file():
                            continue
                        try:
                            candidate.resolve().relative_to(REPOSITORY_ROOT.resolve())
                        except ValueError:
                            continue
                        resolved.add(candidate.resolve())
        return resolved

    def _credential_import_exports(
        self, source, dependency, forwarded_exports=(), importing_path=None
    ):
        """Trace imports reaching credentials or selected re-exports, without execution."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        bindings = None

        def bound_names():
            nonlocal bindings
            if bindings is None:
                bindings = _name_bindings(tree)
            return bindings

        secret_keys = {
            "password", "api_key", "bearer_auth", "basic_auth",
            "http_auth", "authorization",
        }

        def password_side(node, name):
            # For tuple-based Basic/HTTP auth, index zero is a username, not
            # a credential; only index one can expose a password.
            if name not in {"basic_auth", "http_auth"}:
                return [node]
            possible = (
                [node] if isinstance(node, (ast.List, ast.Tuple))
                else _resolve_bound_nodes(node, bound_names(), _node_position(node))
            )
            extracted = []
            unknown = False
            for value in possible:
                if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) >= 2:
                    extracted.append(value.elts[1])
                else:
                    unknown = True
            # An unresolved shape is conservatively retained, while known
            # pairs never drag in a harmless username.
            return [*extracted, *([node] if unknown else [])]

        credential_values = []
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg in secret_keys:
                credential_values.extend(password_side(node.value, node.arg))
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value.lower() in secret_keys
                    ):
                        credential_values.extend(password_side(value, key.value.lower()))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if node.value is None:
                    continue
                for target in targets:
                    name = None
                    if isinstance(target, ast.Name):
                        name = target.id.lower()
                    elif (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.slice, ast.Constant)
                        and isinstance(target.slice.value, str)
                    ):
                        name = target.slice.value.lower()
                    if name in secret_keys:
                        # Selected module exports are analyzed using their
                        # final reaching bindings below. Adding every raw
                        # assignment value here would revive an import that a
                        # loop target (or later safe write) already shadowed.
                        if (
                            isinstance(target, ast.Name)
                            and target.id in forwarded_exports
                        ):
                            continue
                        credential_values.extend(password_side(node.value, name))

        if not credential_values and not forwarded_exports:
            return set()

        # Re-exports must follow the value that reaches the module's final
        # exported name, not an earlier import overwritten before consumers
        # import the module. Direct module-level assignments are unconditional.
        # A tuple/list unpacking binds only the element belonging to the
        # selected export, not unrelated siblings.
        def assigned_leaves(target, value):
            if isinstance(target, ast.Name):
                yield target.id, value
            elif isinstance(target, (ast.Tuple, ast.List)):
                possibilities = (
                    [value] if isinstance(value, (ast.Tuple, ast.List))
                    else _resolve_bound_nodes(
                        value, bound_names(), _node_position(value)
                    )
                )
                for resolved in possibilities:
                    if (
                        isinstance(resolved, (ast.Tuple, ast.List))
                        and len(resolved.elts) == len(target.elts)
                    ):
                        for child_target, child_value in zip(
                            target.elts, resolved.elts
                        ):
                            yield from assigned_leaves(child_target, child_value)

        # Track reaching module-level bindings and control-flow exits.
        # A loop's break does not execute its else clause; an exception
        # handler may see any binding that existed before a raising statement.
        # Each state is a map from an export to possible reaching AST nodes.
        def merge_states(*states):
            states = [state for state in states if state is not None]
            if not states:
                return None
            # The ordinary export flow tracks forwarded_exports, while a
            # credential use can temporarily track one wildcard-bound name.
            # Merge whichever names the incoming reaching states contain.
            return {
                name: set().union(*(state.get(name, ()) for state in states))
                for name in set().union(*(state.keys() for state in states))
            }

        def merge_flows(*flows):
            merged = {}
            for flow in flows:
                for exit_kind, state in flow.items():
                    merged[exit_kind] = merge_states(
                        merged.get(exit_kind), state
                    )
            return merged

        def bind_export_target(
            state, target, expressions, source_state=None
        ):
            """Bind exports from RHS values under their actual evaluation state.

            Iterable elements were evaluated before the loop body, whereas an
            assignment in the body reads its current reaching bindings.
            """
            updated = {name: set(values) for name, values in state.items()}
            source_state = state if source_state is None else source_state
            writes = {}
            def target_names(node):
                if isinstance(node, ast.Name):
                    yield node.id
                elif isinstance(node, (ast.Tuple, ast.List, ast.Starred)):
                    children = (
                        [node.value] if isinstance(node, ast.Starred)
                        else node.elts
                    )
                    for child in children:
                        yield from target_names(child)

            for expression in expressions:
                leaves = list(assigned_leaves(target, expression))
                if not leaves:
                    # Unknown unpacking shape: retaining the whole source is
                    # safer than silently losing a possible credential.
                    leaves = [(name, expression) for name in target_names(target)]
                for key, value in leaves:
                    if key in updated:
                        # A selected export reading itself (or another selected
                        # export) uses its *current* binding, not a previously
                        # shadowed import with the same spelling.
                        if (
                            isinstance(value, ast.Name)
                            and value.id in source_state
                        ):
                            writes.setdefault(key, set()).update(
                                source_state[value.id]
                            )
                        else:
                            writes.setdefault(key, set()).add(value)
            for key, values in writes.items():
                updated[key] = values
            return updated

        def named_expr_bindings(expression, state):
            """Apply walrus writes in expression evaluation order.

            A tuple, call, or arithmetic expression evaluates its children
            unconditionally when it completes normally. Only expressions
            with optional child evaluation retain a no-write alternative.
            Deferred lambda and generator bodies are not evaluated here.
            """
            if isinstance(expression, (ast.Lambda, ast.GeneratorExp)):
                return state
            if isinstance(expression, ast.NamedExpr):
                evaluated = named_expr_bindings(expression.value, state)
                return bind_export_target(
                    evaluated, expression.target, [expression.value]
                )
            if isinstance(expression, ast.BoolOp):
                evaluated = named_expr_bindings(expression.values[0], state)
                for previous, value in zip(
                    expression.values, expression.values[1:]
                ):
                    # Python skips the next operand only when the previous
                    # result short-circuits. Literal booleans are decidable.
                    truth = (
                        bool(previous.value)
                        if isinstance(previous, ast.Constant) else None
                    )
                    if truth is not None:
                        skip = (
                            isinstance(expression.op, ast.And) and not truth
                            or isinstance(expression.op, ast.Or) and truth
                        )
                        if skip:
                            continue
                        evaluated = named_expr_bindings(value, evaluated)
                    else:
                        evaluated = merge_states(
                            evaluated, named_expr_bindings(value, evaluated)
                        )
                return evaluated
            if isinstance(expression, ast.IfExp):
                tested = named_expr_bindings(expression.test, state)
                return merge_states(
                    named_expr_bindings(expression.body, tested),
                    named_expr_bindings(expression.orelse, tested),
                )
            if isinstance(expression, ast.Compare):
                evaluated = named_expr_bindings(expression.left, state)
                for index, comparator in enumerate(expression.comparators):
                    checked = named_expr_bindings(comparator, evaluated)
                    evaluated = (
                        checked if index == 0
                        else merge_states(evaluated, checked)
                    )
                return evaluated
            if isinstance(expression, (ast.ListComp, ast.SetComp, ast.DictComp)):
                # Comprehension iterations may be empty. The outer iterable
                # runs, but walruses in filters/elements are conditional.
                generators = expression.generators
                evaluated = named_expr_bindings(generators[0].iter, state)
                possible = evaluated
                for generator in generators:
                    possible = named_expr_bindings(generator.iter, possible)
                    for condition in generator.ifs:
                        possible = named_expr_bindings(condition, possible)
                parts = (
                    [expression.key, expression.value]
                    if isinstance(expression, ast.DictComp)
                    else [expression.elt]
                )
                for part in parts:
                    possible = named_expr_bindings(part, possible)
                return merge_states(evaluated, possible)
            if isinstance(expression, ast.Dict):
                children = []
                for key, value in zip(expression.keys, expression.values):
                    if key is not None:
                        children.append(key)
                    children.append(value)
            else:
                children = ast.iter_child_nodes(expression)
            current = state
            for child in children:
                current = named_expr_bindings(child, current)
            return current

        def fixed_loop_elements(iterable):
            """Return known, ordered loop elements or None for unknown inputs."""
            nodes = (
                [iterable] if isinstance(iterable, (ast.Tuple, ast.List))
                else _resolve_bound_nodes(
                    iterable, bound_names(), _node_position(iterable)
                )
            )
            if len(nodes) != 1:
                return None
            node = nodes[0]
            if not isinstance(node, (ast.Tuple, ast.List)):
                return None
            if any(isinstance(item, ast.Starred) for item in node.elts):
                return None
            return node.elts

        def loop_target_expressions(iterable):
            """Unknown iterable: conservatively retain its possible values."""
            resolved = _resolve_bound_nodes(
                iterable, bound_names(), _node_position(iterable)
            )
            elements = []
            for node in resolved:
                if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                    elements.extend(node.elts)
                else:
                    elements.append(node)
            return elements or [iterable]

        contextlib_module_names = {"contextlib"}
        contextlib_suppress_names = set()
        for import_stmt in tree.body:
            if isinstance(import_stmt, ast.Import):
                for alias in import_stmt.names:
                    if alias.name == "contextlib":
                        contextlib_module_names.add(alias.asname or alias.name)
            elif (
                isinstance(import_stmt, ast.ImportFrom)
                and import_stmt.module == "contextlib"
            ):
                for alias in import_stmt.names:
                    if alias.name == "suppress":
                        contextlib_suppress_names.add(
                            alias.asname or alias.name
                        )

        def is_suppress_callable(func, position, seen=None):
            """Resolve source-ordered aliases of contextlib.suppress."""
            seen = set() if seen is None else set(seen)
            if isinstance(func, ast.Attribute) and func.attr == "suppress":
                # Resolve ctx = contextlib and other simple module aliases.
                roots = _resolve_bound_nodes(
                    func.value, bound_names(), position
                )
                return any(
                    isinstance(root, ast.Name)
                    and root.id in contextlib_module_names
                    for root in roots
                )
            if isinstance(func, ast.Name):
                if func.id in contextlib_suppress_names:
                    return True
                if func.id in seen:
                    return False
                return any(
                    candidate is not func
                    and is_suppress_callable(
                        candidate, position, seen | {func.id}
                    )
                    for candidate in _resolve_bound_nodes(
                        func, bound_names(), position
                    )
                )
            return False

        def might_raise(stmt):
            # A store into an attribute or subscript invokes user-defined
            # methods such as __setattr__ or __setitem__; a harmless literal
            # RHS does not make that store safe from exceptions.
            if isinstance(stmt, (ast.Pass, ast.Break, ast.Continue)):
                return False
            if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.Raise)):
                return True
            if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = (
                    stmt.targets if isinstance(stmt, ast.Assign)
                    else [stmt.target]
                )
                if any(
                    isinstance(node, (ast.Attribute, ast.Subscript))
                    for target in targets for node in ast.walk(target)
                ):
                    return True
                # Augmented assignment reads the old target and can invoke
                # operators even if the RHS is a constant.
                if isinstance(stmt, ast.AugAssign):
                    return True
                value = stmt.value
            elif isinstance(stmt, ast.Expr):
                value = stmt.value
            elif isinstance(stmt, (ast.If, ast.While)):
                value = stmt.test
            else:
                return False  # Nested suites are inspected by their walkers.
            if value is None:
                return False
            return any(
                isinstance(n, (
                    ast.Call, ast.Attribute, ast.Subscript, ast.Await,
                    ast.Yield, ast.YieldFrom, ast.BinOp
                ))
                for n in ast.walk(value)
            )

        def walk_export_statements(statements, incoming, raising_states=None):
            flow = {"normal": incoming}
            for stmt in statements:
                if "normal" not in flow:
                    break
                state = flow.pop("normal")
                if raising_states is not None and might_raise(stmt):
                    # Save the binding present when the statement can raise.
                    # A later literal safe assignment cannot itself raise
                    # and must not resurrect an earlier imported credential.
                    raising_states.append(state)
                if isinstance(stmt, (ast.ImportFrom, ast.Import)):
                    updated = {name: set(values) for name, values in state.items()}
                    for item in stmt.names:
                        local = item.asname or (
                            item.name if isinstance(stmt, ast.ImportFrom)
                            else item.name.split(".", 1)[0]
                        )
                        if (
                            isinstance(stmt, ast.ImportFrom)
                            and item.name == "*"
                        ):
                            # An import-star binds every selected forwarded
                            # export whose spelling the provider supplies.
                            for name in forwarded_exports:
                                updated[name] = {stmt}
                        elif local in forwarded_exports:
                            updated[local] = {stmt}
                    next_flow = {"normal": updated}
                elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                    updated = state
                    if stmt.value is not None:
                        updated = named_expr_bindings(stmt.value, updated)
                        targets = (
                            stmt.targets if isinstance(stmt, ast.Assign)
                            else [stmt.target]
                        )
                        for target in targets:
                            updated = bind_export_target(
                                updated, target, [stmt.value]
                            )
                    next_flow = {"normal": updated}
                elif isinstance(stmt, ast.AugAssign):
                    updated = named_expr_bindings(stmt.value, state)
                    if (
                        isinstance(stmt.target, ast.Name)
                        and stmt.target.id in forwarded_exports
                    ):
                        candidate = bind_export_target(
                            updated, stmt.target, [stmt.value]
                        )
                        # An augmented assignment reads the prior target.
                        updated = merge_states(updated, candidate)
                    next_flow = {"normal": updated}
                elif isinstance(stmt, ast.If):
                    tested = named_expr_bindings(stmt.test, state)
                    next_flow = merge_flows(
                        walk_export_statements(
                            stmt.body, tested, raising_states
                        ),
                        walk_export_statements(
                            stmt.orelse, tested, raising_states
                        ),
                    )
                elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
                    # For a known finite sequence, run each target binding in
                    # order so the final element replaces earlier bindings.
                    # A break exits without executing the loop's else suite.
                    is_for = isinstance(stmt, (ast.For, ast.AsyncFor))
                    loop_head = named_expr_bindings(
                        stmt.iter if is_for else stmt.test, state
                    )
                    fixed = fixed_loop_elements(stmt.iter) if is_for else None
                    iterable_state = loop_head
                    broken = None
                    if fixed is not None and len(fixed) <= 32:
                        exhausted = loop_head
                        for element in fixed:
                            if exhausted is None:
                                break
                            iteration = bind_export_target(
                                exhausted, stmt.target, [element],
                                source_state=iterable_state
                            )
                            if raising_states is not None:
                                raising_states.append(iteration)
                            body = walk_export_statements(
                                stmt.body, iteration, raising_states
                            )
                            broken = merge_states(broken, body.get("break"))
                            exhausted = merge_states(
                                body.get("normal"), body.get("continue")
                            )
                    else:
                        # Unknown or very large loops: widen the finite
                        # reaching-bindings lattice to a fixed point.
                        # Do not claim a zero-trip path is impossible.
                        exhausted = loop_head
                        possible = (
                            loop_target_expressions(stmt.iter)
                            if is_for else None
                        )
                        while True:
                            iteration = (
                                bind_export_target(
                                    loop_head, stmt.target, possible,
                                    source_state=iterable_state
                                ) if is_for else loop_head
                            )
                            if raising_states is not None:
                                raising_states.append(iteration)
                            body = walk_export_statements(
                                stmt.body, iteration, raising_states
                            )
                            broken = merge_states(broken, body.get("break"))
                            continued = merge_states(
                                body.get("normal"), body.get("continue")
                            )
                            exhausted = merge_states(exhausted, continued)
                            widened = merge_states(loop_head, continued)
                            if widened == loop_head:
                                break
                            loop_head = widened
                    next_flow = (
                        walk_export_statements(stmt.orelse, exhausted, raising_states)
                        if exhausted is not None else {}
                    )
                    if broken is not None:
                        next_flow = merge_flows(next_flow, {"normal": broken})
                elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                    with_state = state
                    suppresses_exceptions = False
                    for item in stmt.items:
                        with_state = named_expr_bindings(
                            item.context_expr, with_state
                        )
                        call = item.context_expr
                        if isinstance(call, ast.Call):
                            func = call.func
                            if is_suppress_callable(
                                func, _node_position(item.context_expr)
                            ):
                                suppresses_exceptions = True
                        if item.optional_vars is not None:
                            sources = [item.context_expr]
                            if (
                                isinstance(call, ast.Call) and call.args
                                and (
                                    isinstance(call.func, ast.Name)
                                    and call.func.id == "nullcontext"
                                    or isinstance(call.func, ast.Attribute)
                                    and call.func.attr == "nullcontext"
                                )
                            ):
                                sources = [call.args[0]]
                            with_state = bind_export_target(
                                with_state, item.optional_vars, sources
                            )
                        if raising_states is not None:
                            raising_states.append(with_state)
                    suppressed_states = [] if suppresses_exceptions else raising_states
                    next_flow = walk_export_statements(
                        stmt.body, with_state, suppressed_states
                    )
                    if suppresses_exceptions:
                        # The with body may exit abnormally but the context
                        # manager can suppress that exception and continue.
                        suppressed = merge_states(*suppressed_states)
                        if suppressed is not None:
                            next_flow = merge_flows(
                                next_flow, {"normal": suppressed}
                            )
                elif isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                    # Capture every intermediate entry state, not just before
                    # and after the complete try body. An exception can occur
                    # after an import but before its later safe overwrite.
                    exceptions = []
                    body = walk_export_statements(
                        stmt.body, state, exceptions
                    )
                    outcomes = {}
                    if "normal" in body:
                        outcomes = walk_export_statements(
                            stmt.orelse, body["normal"], raising_states
                        )
                    outcomes = merge_flows(
                        outcomes,
                        {kind: value for kind, value in body.items()
                         if kind != "normal"},
                    )
                    if stmt.handlers:
                        for handler in stmt.handlers:
                            for possible_state in exceptions:
                                outcomes = merge_flows(
                                    outcomes,
                                    walk_export_statements(
                                        handler.body, possible_state,
                                        raising_states
                                    ),
                                )
                    catches_all = any(
                        handler.type is None
                        or isinstance(handler.type, ast.Name)
                        and handler.type.id in {"Exception", "BaseException"}
                        for handler in stmt.handlers
                    )
                    if raising_states is not None and not catches_all:
                        # Forward inner exceptional states, *after* running
                        # their finally suite, to any enclosing try handler.
                        for possible_state in exceptions:
                            cleanup = walk_export_statements(
                                stmt.finalbody, possible_state
                            )
                            exceptional = cleanup.get("normal")
                            if exceptional is not None:
                                raising_states.append(exceptional)
                    # finally executes even on a pending break or continue;
                    # a normally completing finally preserves the old exit.
                    completed = {}
                    for exit_kind, possible_state in outcomes.items():
                        cleanup = walk_export_statements(
                            stmt.finalbody, possible_state, raising_states
                        )
                        for kind, value in cleanup.items():
                            kind = exit_kind if kind == "normal" else kind
                            completed = merge_flows(
                                completed, {kind: value}
                            )
                    next_flow = completed
                elif isinstance(stmt, getattr(ast, "Match", ())):
                    matched = named_expr_bindings(stmt.subject, state)
                    possibilities = [{"normal": matched}]
                    for case in stmt.cases:
                        guarded = (
                            named_expr_bindings(case.guard, matched)
                            if case.guard is not None else matched
                        )
                        # A failing guard can still leave a walrus binding.
                        possibilities.append({"normal": guarded})
                        possibilities.append(
                            walk_export_statements(
                                case.body, guarded, raising_states
                            )
                        )
                    next_flow = merge_flows(*possibilities)
                elif isinstance(stmt, ast.Expr):
                    next_flow = {
                        "normal": named_expr_bindings(stmt.value, state)
                    }
                elif isinstance(stmt, ast.Raise):
                    # No fallthrough past an explicit raise.
                    next_flow = {}
                elif isinstance(stmt, ast.Break):
                    next_flow = {"break": state}
                elif isinstance(stmt, ast.Continue):
                    next_flow = {"continue": state}
                else:
                    # Function/class bodies have separate scopes and cannot
                    # directly reassign the module's selected export names.
                    next_flow = {"normal": state}
                flow = merge_flows(flow, next_flow)
            return flow

        latest_flow = walk_export_statements(
            tree.body, {name: {None} for name in forwarded_exports}
        )
        latest_exports = latest_flow.get("normal", {})
        forwarded_import_nodes = set()
        for reaching_values in latest_exports.values():
            for value in reaching_values:
                if isinstance(value, (ast.ImportFrom, ast.Import)):
                    forwarded_import_nodes.add(value)
                elif value is not None:
                    credential_values.append(value)

        used_names = set()
        used_name_occurrences = {}
        used_chains = set()

        def attribute_chain(node):
            parts = []
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                return tuple([node.id, *reversed(parts)])
            return ()

        def trace(node, seen=None):
            seen = set() if seen is None else seen
            if isinstance(node, ast.Name):
                used_names.add(node.id)
                used_name_occurrences.setdefault(node.id, []).append(node)
                active_bindings = bound_names()
                token = _binding_name_token(node.id, active_bindings, node)
                if token in seen:
                    return
                for value in _resolve_bound_nodes(node, active_bindings, _node_position(node)):
                    if value is not node:
                        trace(value, seen | {token})
                return
            if isinstance(node, ast.Attribute):
                chain = attribute_chain(node)
                if len(chain) >= 2:
                    used_chains.add(chain)
                    root = node
                    while isinstance(root, ast.Attribute):
                        root = root.value
                    if isinstance(root, ast.Name):
                        # Preserve the suffix while resolving alias = cp where
                        # cp is an imported module, not a credential string.
                        for resolved in _resolve_bound_nodes(
                            root, bound_names(), _node_position(root)
                        ):
                            resolved_root = attribute_chain(resolved)
                            if resolved_root:
                                used_chains.add(resolved_root + chain[1:])
            for child in ast.iter_child_nodes(node):
                trace(child, seen)

        for value in credential_values:
            trace(value)

        # Invocation-sensitive wildcard reads need lexical owners and their
        # module-level callers, not just definition-time source positions.
        ast_parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }

        def module_invocation_sites(use):
            """Snapshot actual reads, not definitions or suspended callables.

            Follow direct lexical calls through enclosing functions, tracked
            returned closures, and module-level callback escapes. An async
            function or generator only executes when its result is resumed.
            """
            metadata = bound_names()["metadata"]
            owner = getattr(use, "_binding_scope", tree)
            while owner is not None and owner is not tree:
                if isinstance(owner, (
                    ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                    ast.GeneratorExp,
                )):
                    break
                owner = metadata["parents"].get(owner)
            if owner is None or owner is tree:
                return []

            def refers_to(value, target, seen=None):
                if value is None:
                    return False
                if value is target:
                    return True
                seen = set() if seen is None else seen
                if value in seen:
                    return False
                seen = seen | {value}
                if isinstance(value, ast.Name):
                    return any(
                        refers_to(binding, target, seen)
                        for binding in _resolve_bound_nodes(
                            value, bound_names(), _node_position(value)
                        )
                        if binding is not value
                    )
                if isinstance(value, ast.Call):
                    # An outer factory can return an inner callable. Creating
                    # it does not execute the returned callable's body.
                    for function in _resolve_bound_nodes(
                        value.func, bound_names(), _node_position(value.func)
                    ):
                        if not isinstance(function, (
                            ast.FunctionDef, ast.AsyncFunctionDef,
                        )):
                            continue
                        for returned in ast.walk(function):
                            if (
                                isinstance(returned, ast.Return)
                                and getattr(returned, "_binding_scope", None)
                                is function
                                and refers_to(returned.value, target, seen)
                            ):
                                return True
                return False

            def is_suspended(target):
                if isinstance(target, (ast.AsyncFunctionDef, ast.GeneratorExp)):
                    return True
                if not isinstance(target, ast.FunctionDef):
                    return False
                return any(
                    isinstance(node, (ast.Yield, ast.YieldFrom))
                    and getattr(node, "_binding_scope", None) is target
                    for node in ast.walk(target)
                )

            def bound_resume_options(call, created, consume_anext=False):
                """Branch-correlated outcomes for calls through bound methods.

                A reaching alias is not an independent call: only the *last*
                binding executed on one control-flow path supplies the method.
                Keep the skip path too (send() without an argument, an unawaited
                __anext__(), or an alias overwritten by a different callable).
                """
                func = call.func
                candidates = (
                    [func] if isinstance(func, ast.Attribute)
                    else _resolve_bound_nodes(
                        func, bound_names(), _node_position(func)
                    )
                )
                methods = {"send", "__next__", "__anext__"}
                if not any(
                    isinstance(node, ast.Attribute)
                    and node.attr in methods
                    and refers_to(node.value, created)
                    for node in candidates
                ):
                    return None
                keys = list(dict.fromkeys(
                    step[:3]
                    for node in candidates
                    for step in _node_control_path(node)
                    if step[0] in {"If", "Match"}
                ))
                match_arms = {
                    ("Match", *_node_position(match)): tuple(
                        f"case-{index}" for index in range(len(match.cases))
                    ) + ("no-match",)
                    for match in ast.walk(tree)
                    if isinstance(match, ast.Match)
                }
                alternatives = [
                    ("body", "orelse") if key[0] == "If"
                    else match_arms.get(key, ("no-match",))
                    for key in keys
                ]
                options = []
                for decisions in product(*alternatives):
                    choices = dict(zip(keys, decisions))
                    reaching = [
                        node for node in candidates
                        if all(
                            choices.get(step[:3]) == step[3]
                            for step in _node_control_path(node)
                            if step[0] in {"If", "Match"}
                        )
                    ]
                    selected = reaching[-1] if reaching else None
                    kind = "skip"
                    if (
                        isinstance(selected, ast.Attribute)
                        and refers_to(selected.value, created)
                        and not call.keywords
                    ):
                        if selected.attr == "__next__" and not call.args:
                            kind = "step"
                        elif selected.attr == "send" and len(call.args) == 1:
                            kind = (
                                "send-value"
                                if definitely_non_none(call.args[0])
                                else "step"
                            )
                        elif (
                            selected.attr == "__anext__"
                            and not call.args and consume_anext
                        ):
                            # __anext__() itself only creates an awaitable.
                            kind = "step"
                    option = (kind, tuple(zip(keys, decisions)))
                    if option not in options:
                        options.append(option)
                return options

            def pending_anext_groups(value, created, seen=None):
                """Awaited groups of generator-step alternatives and identities.

                Each group advances at most one bound method on a path.
                gather() consumes each of its inputs, unlike alternative
                bound-method assignments. A stored __anext__ awaitable keeps
                the identity of the original Call AST across name aliases.
                """
                seen = set() if seen is None else seen
                if value in seen:
                    return []
                seen = seen | {value}
                if isinstance(value, ast.Name):
                    groups = []
                    for bound in _resolve_bound_nodes(
                        value, bound_names(), _node_position(value)
                    ):
                        if bound is not value:
                            groups.extend(
                                pending_anext_groups(bound, created, seen)
                            )
                    return groups
                if not isinstance(value, ast.Call):
                    return []
                options = bound_resume_options(
                    value, created, consume_anext=True
                )
                if options is not None:
                    return [[
                        (kind, guard, value if kind == "step" else None)
                        for kind, guard in options
                    ]]
                if (
                    isinstance(value.func, ast.Name)
                    and value.func.id == "anext"
                    and len(value.args) in (1, 2)
                    and not value.keywords
                    and refers_to(value.args[0], created)
                ):
                    return [[("step", (), value)]]
                if (
                    isinstance(value.func, ast.Attribute)
                    and isinstance(value.func.value, ast.Name)
                    and value.func.value.id == "asyncio"
                    and not value.keywords
                ):
                    if value.func.attr == "shield" and len(value.args) == 1:
                        return pending_anext_groups(value.args[0], created, seen)
                    if value.func.attr == "gather" and value.args:
                        return [
                            group
                            for arg in value.args
                            for group in pending_anext_groups(arg, created, seen)
                        ]
                    if value.func.attr == "wait_for" and len(value.args) == 2:
                        return pending_anext_groups(value.args[0], created, seen)
                return []

            def resume_expressions(created):
                """Ordered execution events, not merely awaitable creation."""
                found = []
                for expression in ast.walk(tree):
                    value = None
                    kind = "all"
                    if isinstance(expression, ast.Await):
                        groups = pending_anext_groups(
                            expression.value, created
                        )
                        if groups:
                            found.extend(
                                (expression, group) for group in groups
                            )
                            continue
                        value = expression.value
                    elif isinstance(expression, ast.YieldFrom):
                        value = expression.value
                    elif isinstance(expression, (ast.For, ast.AsyncFor)):
                        value = expression.iter
                    elif isinstance(expression, ast.Call):
                        func = expression.func
                        options = bound_resume_options(expression, created)
                        if options is not None:
                            if any(option[0] != "skip" for option in options):
                                found.append((
                                    expression,
                                    [(kind, guard, None)
                                     for kind, guard in options],
                                ))
                            continue
                        if (
                            isinstance(func, ast.Name)
                            and func.id == "next"
                            and expression.args
                        ):
                            value = expression.args[0]
                            kind = "step"
                        elif (
                            isinstance(func, ast.Name)
                            and func.id == "anext"
                        ):
                            # Builtin anext() also returns an awaitable.
                            continue
                        elif isinstance(func, ast.Name) and func.id in {
                            "list", "tuple", "set", "sum",
                            "any", "all", "max", "min",
                        } and expression.args:
                            value = expression.args[0]
                        elif (
                            isinstance(func, ast.Attribute)
                            and func.attr == "run"
                            and expression.args
                        ):
                            value = expression.args[0]
                        elif not (
                            isinstance(func, ast.Name) and func.id in {
                                "iter", "repr", "id", "type",
                            }
                        ):
                            # Opaque consumers may drive a suspended object.
                            for argument in [
                                *expression.args,
                                *(kw.value for kw in expression.keywords),
                            ]:
                                if refers_to(argument, created):
                                    value = argument
                                    break
                    if value is not None and refers_to(value, created):
                        found.append((expression, [(kind, (), None)]))
                return sorted(found, key=lambda item: _node_position(item[0]))

            def static_iterable_minimum(expression):
                """Lower bound on yields from a plainly known iterable.

                Unknown delegation may yield zero items, so it contributes
                no definite suspension before a credential read.
                """
                if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
                    if any(isinstance(item, ast.Starred) for item in expression.elts):
                        return 0
                    return len(expression.elts)
                if isinstance(expression, ast.Dict):
                    if any(key is None for key in expression.keys):
                        return 0
                    return len(expression.keys)
                if isinstance(expression, ast.Constant) and isinstance(
                    expression.value, (str, bytes, tuple, list, frozenset)
                ):
                    return len(expression.value)
                if (
                    isinstance(expression, ast.Call)
                    and isinstance(expression.func, ast.Name)
                    and expression.func.id == "range"
                    and not expression.keywords
                    and 1 <= len(expression.args) <= 3
                    and all(
                        isinstance(arg, ast.Constant) and type(arg.value) is int
                        for arg in expression.args
                    )
                ):
                    try:
                        return len(range(*(arg.value for arg in expression.args)))
                    except ValueError:
                        return 0
                return 0

            def prior_definite_yields(target):
                """Count guaranteed suspensions strictly before the read."""
                if not isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return 0
                count = 0
                for statement in target.body:
                    # A yielded expression is evaluated BEFORE suspension.
                    if (
                        _node_position(statement) >= _node_position(use)
                        or any(child is use for child in ast.walk(statement))
                    ):
                        break
                    if isinstance(statement, ast.Expr):
                        if isinstance(statement.value, ast.Yield):
                            count += 1
                        elif isinstance(statement.value, ast.YieldFrom):
                            count += static_iterable_minimum(
                                statement.value.value
                            )
                return count

            def loop_ancestors(expression):
                """Loops whose body contains this syntactic operation."""
                ancestors = []
                child = expression
                while child is not tree:
                    parent = ast_parents.get(child)
                    if parent is None:
                        break
                    if isinstance(parent, (ast.For, ast.AsyncFor, ast.While)):
                        if any(child is stmt for stmt in parent.body):
                            ancestors.append(parent)
                    child = parent
                return ancestors

            def resumes_same_instance(created, resume, loop):
                """A generator reconstructed each pass cannot accumulate steps."""
                return (
                    loop in loop_ancestors(created)
                    and loop in loop_ancestors(resume)
                    and _node_position(created) < _node_position(resume)
                )

            def resume_repeat_bound(expression, needed, created):
                """Conservatively bound repeat resumes of the same object."""
                repeats = 1
                child = expression
                while child is not tree:
                    parent = ast_parents.get(child)
                    if parent is None:
                        break
                    if isinstance(parent, (ast.For, ast.AsyncFor)):
                        # The iterable expression is evaluated once, before
                        # the loop body, so it is not a repeating resume site.
                        in_body = any(child is stmt for stmt in parent.body)
                        if in_body:
                            if resumes_same_instance(created, expression, parent):
                                repetition = 1
                            else:
                                iterable = parent.iter
                                repetition = None
                                if isinstance(iterable, (ast.List, ast.Tuple)):
                                    # Starred literal iterables expand into
                                    # their *runtime* element counts. Unknown
                                    # stars preserve an unknown upper bound.
                                    repetition = 0
                                    for item in iterable.elts:
                                        if not isinstance(item, ast.Starred):
                                            repetition += 1
                                            continue
                                        expanded = item.value
                                        if isinstance(expanded, (ast.List, ast.Tuple)):
                                            if any(
                                                isinstance(part, ast.Starred)
                                                for part in expanded.elts
                                            ):
                                                repetition = None
                                                break
                                            repetition += len(expanded.elts)
                                        elif (
                                            isinstance(expanded, ast.Constant)
                                            and isinstance(expanded.value, (
                                                str, bytes, tuple, list,
                                            ))
                                        ):
                                            repetition += len(expanded.value)
                                        else:
                                            repetition = None
                                            break
                                elif (
                                    isinstance(iterable, ast.Call)
                                    and isinstance(iterable.func, ast.Name)
                                    and iterable.func.id == "range"
                                    and not iterable.keywords
                                    and 1 <= len(iterable.args) <= 3
                                    and all(
                                        isinstance(arg, ast.Constant)
                                        and type(arg.value) is int
                                        for arg in iterable.args
                                    )
                                ):
                                    try:
                                        repetition = len(range(*(
                                            arg.value for arg in iterable.args
                                        )))
                                    except ValueError:
                                        pass
                            repeats *= (
                                min(repetition, needed)
                                if repetition is not None else needed
                            )
                        elif isinstance(parent, ast.For) and child is parent.iter:
                            pass
                    elif isinstance(parent, ast.While):
                        in_body = any(child is stmt for stmt in parent.body)
                        in_test = any(
                            node is expression for node in ast.walk(parent.test)
                        )
                        if in_body or in_test:
                            if in_body and resumes_same_instance(
                                created, expression, parent
                            ):
                                repetition = 1
                            else:
                                repetition = (
                                    0 if isinstance(parent.test, ast.Constant)
                                    and not bool(parent.test.value)
                                    else needed
                                )
                            repeats *= repetition
                    elif isinstance(parent, (
                        ast.ListComp, ast.SetComp, ast.DictComp,
                        ast.GeneratorExp,
                    )):
                        # Comprehension bodies repeat, but an inline run()
                        # in that same comprehension creates a new suspended
                        # object for each iteration; its steps cannot carry
                        # over to another fresh generator instance.
                        created_in_parent = any(
                            node is created for node in ast.walk(parent)
                        )
                        if not created_in_parent and not any(
                            node is expression
                            for generator in parent.generators
                            for node in ast.walk(generator.iter)
                        ):
                            repeats *= needed
                    child = parent
                    if repeats >= needed:
                        return needed
                return repeats

            def definitely_non_none(expr, seen=None):
                """Recognize only statically provable non-None send values."""
                if expr is None:
                    return False
                seen = set() if seen is None else seen
                if expr in seen:
                    return False
                seen = seen | {expr}
                if isinstance(expr, ast.Name):
                    values = [
                        bound for bound in _resolve_bound_nodes(
                            expr, bound_names(), _node_position(expr)
                        ) if bound is not expr
                    ]
                    return bool(values) and all(
                        definitely_non_none(bound, seen) for bound in values
                    )
                if isinstance(expr, ast.Constant):
                    return expr.value is not None
                if isinstance(expr, (
                    ast.List, ast.Tuple, ast.Set, ast.Dict,
                    ast.JoinedStr, ast.Lambda,
                )):
                    return True
                if isinstance(expr, ast.UnaryOp) and isinstance(
                    expr.op, (ast.UAdd, ast.USub, ast.Invert)
                ):
                    return definitely_non_none(expr.operand, seen)
                if isinstance(expr, ast.BinOp):
                    return (
                        definitely_non_none(expr.left, seen)
                        and definitely_non_none(expr.right, seen)
                    )
                if isinstance(expr, ast.IfExp):
                    return (
                        definitely_non_none(expr.body, seen)
                        and definitely_non_none(expr.orelse, seen)
                    )
                return False

            def reaches_call(expression, scope):
                """Exclude syntactically unreachable inner invocations."""
                child = expression
                while child is not scope:
                    parent = ast_parents.get(child)
                    if parent is None:
                        break
                    if isinstance(parent, ast.If) and isinstance(
                        parent.test, ast.Constant
                    ):
                        truth = bool(parent.test.value)
                        if child in parent.body and not truth:
                            return False
                        if child in parent.orelse and truth:
                            return False
                    for suite_name in ("body", "orelse", "finalbody"):
                        suite = getattr(parent, suite_name, None)
                        if isinstance(suite, list) and child in suite:
                            if any(
                                isinstance(previous, (ast.Return, ast.Raise))
                                for previous in suite[:suite.index(child)]
                            ):
                                return False
                    child = parent
                return True

            def tracked_name_alias_store(reference):
                """Detect name leaves in source-ordered unpacking stores."""
                child = reference
                indexes = []
                parent = ast_parents.get(child)
                while isinstance(parent, (ast.Tuple, ast.List)):
                    if any(isinstance(leaf, ast.Starred) for leaf in parent.elts):
                        return False
                    indexes.insert(0, parent.elts.index(child))
                    child, parent = parent, ast_parents.get(parent)
                if not isinstance(parent, ast.Assign) or parent.value is not child:
                    return False
                for target in parent.targets:
                    leaf = target
                    for index in indexes:
                        if not isinstance(leaf, (ast.Tuple, ast.List)):
                            break
                        if index >= len(leaf.elts):
                            break
                        leaf = leaf.elts[index]
                    else:
                        if isinstance(leaf, ast.Name):
                            return True
                return False

            sites = []
            visited = set()

            def add_site(expression):
                scope = getattr(expression, "_binding_scope", tree)
                if scope is not tree and not reaches_call(expression, scope):
                    return
                if scope is tree:
                    sites.append((
                        _node_position(expression), _node_control_path(expression)
                    ))
                elif isinstance(scope, (
                    ast.ListComp, ast.SetComp, ast.DictComp,
                )):
                    # Eager comprehensions run at their expression site.
                    # The produced element executes in their implicit scope,
                    # but that frame is not a deferred user callable.
                    add_site(scope)
                elif isinstance(scope, (
                    ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                    ast.GeneratorExp,
                )):
                    # inner() directly invoked inside outer() runs when
                    # outer itself runs; nested closure *creation* does not.
                    collect(scope)

            def static_condition_truth(condition):
                """Safely resolve side-effect-free constant boolean outcomes.

                None denotes unknown; conservative paths remain for unknown
                conditions. Short-circuit boolean logic can still prove a
                result with one unknown operand.
                """
                if isinstance(condition, ast.Constant):
                    return bool(condition.value)
                if isinstance(condition, ast.UnaryOp) and isinstance(
                    condition.op, ast.Not
                ):
                    nested = static_condition_truth(condition.operand)
                    return None if nested is None else not nested
                if isinstance(condition, ast.BoolOp):
                    known = [
                        static_condition_truth(value)
                        for value in condition.values
                    ]
                    if isinstance(condition.op, ast.And):
                        if False in known:
                            return False
                        return True if all(x is True for x in known) else None
                    if isinstance(condition.op, ast.Or):
                        if True in known:
                            return True
                        return False if all(x is False for x in known) else None
                if isinstance(condition, ast.Compare):
                    expressions = [condition.left, *condition.comparators]
                    try:
                        values = [ast.literal_eval(x) for x in expressions]
                    except (ValueError, TypeError, RecursionError):
                        return None
                    for left, op, right in zip(
                        values, condition.ops, values[1:]
                    ):
                        # Restrict comparisons to immutable scalar constants:
                        # no user-defined comparison methods or side effects.
                        if not (
                            type(left) in (str, int, float, bool, type(None))
                            and type(right) in (
                                str, int, float, bool, type(None)
                            )
                        ):
                            return None
                        if isinstance(op, ast.Eq):
                            result = left == right
                        elif isinstance(op, ast.NotEq):
                            result = left != right
                        elif isinstance(op, (ast.Is, ast.IsNot)):
                            # CPython may intern/reuse arbitrary compiled
                            # literal objects. Only singleton identity is
                            # portable and safe to fold at source level.
                            singletons = (None, True, False)
                            if not (
                                any(left is item for item in singletons)
                                and any(right is item for item in singletons)
                            ):
                                return None
                            result = (
                                left is right if isinstance(op, ast.Is)
                                else left is not right
                            )
                        elif isinstance(op, ast.Lt):
                            result = left < right if type(left) is type(right) else None
                        elif isinstance(op, ast.LtE):
                            result = left <= right if type(left) is type(right) else None
                        elif isinstance(op, ast.Gt):
                            result = left > right if type(left) is type(right) else None
                        elif isinstance(op, ast.GtE):
                            result = left >= right if type(left) is type(right) else None
                        else:
                            return None
                        if result is None:
                            return None
                        if not result:
                            return False
                    return True
                return None

            def collect(target):
                if target in visited:
                    return
                visited.add(target)
                for call in ast.walk(tree):
                    if not isinstance(call, ast.Call):
                        continue
                    if refers_to(call.func, target):
                        if is_suspended(target):
                            # Calling async def or a generator function only
                            # creates the suspended object. Its body reads
                            # globals on await/iteration, not on creation.
                            needed = prior_definite_yields(target) + 1
                            # Each possible If/else path owns an independent
                            # resume counter. Calls from opposing arms must
                            # never accumulate as though both arms ran.
                            paths = [(0, {}, frozenset())]
                            constant_if_choices = {
                                ("If", *_node_position(conditional)): (
                                    "body"
                                    if static_condition_truth(conditional.test)
                                    else "orelse"
                                )
                                for conditional in ast.walk(tree)
                                if isinstance(conditional, ast.If)
                                and static_condition_truth(
                                    conditional.test
                                ) is not None
                            }
                            for resume, options in resume_expressions(call):
                                # One call can have several reaching method
                                # bindings, but executes only one on each
                                # feasible control-flow path. Include guards
                                # from the assignment *and* the invocation.
                                event_branches = [
                                    step for step in _node_control_path(resume)
                                    if step[0] in {"If", "Match"}
                                ]
                                guarded = [
                                    (kind, identity, [
                                        *event_branches,
                                        *(tuple(key) + (arm,) for key, arm in guard),
                                    ])
                                    for kind, guard, identity in options
                                ]
                                keys = list(dict.fromkeys(
                                    step[:3]
                                    for _, _, conditions in guarded
                                    for step in conditions
                                ))
                                expanded = paths
                                for key in keys:
                                    next_paths = []
                                    for count, choices, consumed in expanded:
                                        choice = choices.get(key)
                                        constant = constant_if_choices.get(key)
                                        possible = (
                                            [constant] if constant is not None
                                            else [choice] if choice is not None
                                            else ["body", "orelse"] if key[0] == "If"
                                            else [
                                                *(f"case-{index}" for index in range(
                                                    len(next(match for match in ast.walk(tree)
                                                        if isinstance(match, ast.Match)
                                                        and ("Match", *_node_position(match)) == key
                                                    ).cases)
                                                )),
                                                "no-match",
                                            ]
                                        )
                                        for arm in possible:
                                            if choice is not None and choice != arm:
                                                continue
                                            next_choices = dict(choices)
                                            next_choices[key] = arm
                                            next_paths.append((count, next_choices, consumed))
                                    expanded = next_paths
                                updated = []
                                for count, choices, consumed in expanded:
                                    matches = [
                                        (kind, identity) for kind, identity, conditions in guarded
                                        if all(
                                            choices.get(step[:3]) == step[3]
                                            for step in conditions
                                        )
                                    ]
                                    if not matches:
                                        updated.append((count, choices, consumed))
                                        continue
                                    for kind, identity in matches:
                                        if (
                                            kind == "skip"
                                            or kind == "send-value" and count == 0
                                            or identity is not None
                                            and identity in consumed
                                        ):
                                            # A zero-arg send or invalid initial
                                            # send(non-None) cannot advance.
                                            updated.append((count, choices, consumed))
                                            continue
                                        increment = (
                                            resume_repeat_bound(
                                                resume, needed, call
                                            )
                                            if kind in {"step", "send-value"}
                                            else needed
                                        )
                                        next_count = min(
                                            needed, count + increment
                                        )
                                        if next_count >= needed:
                                            add_site(resume)
                                        updated.append((
                                            next_count, choices,
                                            consumed | {identity}
                                            if identity is not None else consumed,
                                        ))
                                paths = updated
                        else:
                            add_site(call)
                        continue
                    # A synchronous dispatcher can invoke a passed callback
                    # immediately, including callbacks passed by keyword.
                    passed = [*call.args, *(k.value for k in call.keywords)]
                    if any(refers_to(arg, target) for arg in passed):
                        add_site(call)

                # An attribute/subscript assignment cannot be followed by
                # the simple-name alias resolver. Preserve the store as an
                # opaque escape (possibly immediately invoked later).
                for ref in ast.walk(tree):
                    if not (
                        isinstance(ref, ast.Name)
                        and isinstance(ref.ctx, ast.Load)
                        and refers_to(ref, target)
                    ):
                        continue
                    parent = ast_parents.get(ref)
                    if (
                        # Returning a closure does not run it. The caller
                        # may invoke the returned value later, which is
                        # tracked independently at its actual call site.
                        isinstance(parent, ast.Return) and parent.value is ref
                        or isinstance(parent, ast.Call) and parent.func is ref
                        or isinstance(parent, (
                            ast.Assign, ast.AnnAssign, ast.NamedExpr
                        )) and parent.value is ref
                        and isinstance(
                            parent.targets[0] if isinstance(parent, ast.Assign)
                            else parent.target, ast.Name
                        )
                        or isinstance(parent, ast.Call) and (
                            ref in parent.args
                            or any(k.value is ref for k in parent.keywords)
                        )
                        or tracked_name_alias_store(ref)
                    ):
                        continue
                    add_site(ref)

            collect(owner)
            # Unknown external invocation conservatively observes module
            # end. Known calls and escape positions are independently
            # analyzed at their actual reaching-state snapshots.
            if not sites:
                return [((float("inf"), float("inf")), ())]
            return list(dict.fromkeys(sites))

        exported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module_tail = (node.module or "").split(".")[-1]
                relative_package = (
                    node.level > 0
                    and node.module is None
                    and dependency.name == "__init__.py"
                    and (
                        importing_path is None
                        or (
                            len(importing_path.parents) >= node.level
                            and importing_path.parents[node.level - 1].resolve()
                            == dependency.parent.resolve()
                        )
                    )
                )
                if (
                    node.module
                    and (
                        dependency.stem == module_tail
                        or dependency.name == "__init__.py"
                        and dependency.parent.name == module_tail
                    )
                    or relative_package
                ):
                    for alias in node.names:
                        if alias.name == "*":
                            if node in forwarded_import_nodes:
                                exported.update(forwarded_exports)
                            # For a direct ES consumer, an import-star does not
                            # have a named binding to match. Trace referenced
                            # credential names, except when a later definite
                            # module assignment shadows the imported binding.
                            for name, occurrences in used_name_occurrences.items():
                                for use in occurrences:
                                    # A lambda parameter or comprehension
                                    # target with the same spelling does not
                                    # refer to this module's wildcard import.
                                    if _binding_name_token(
                                        name, bound_names(), use
                                    )[0] is not tree:
                                        continue
                                    import_pos = _node_position(node)
                                    use_pos = _node_position(use)
                                    metadata = bound_names()["metadata"]
                                    scope = getattr(use, "_binding_scope", tree)
                                    deferred_read = False
                                    while scope is not None and scope is not tree:
                                        if isinstance(scope, (
                                            ast.FunctionDef, ast.AsyncFunctionDef,
                                            ast.Lambda, ast.GeneratorExp,
                                        )):
                                            deferred_read = True
                                            break
                                        scope = metadata["parents"].get(scope)
                                    # A closure resolves module globals on
                                    # invocation, potentially after a later
                                    # wildcard import. An eager class/module
                                    # expression instead reads at source order.
                                    if use_pos <= import_pos and not deferred_read:
                                        continue
                                    # A deferred global read observes values at
                                    # invocation, which can be after a later
                                    # import but before a subsequent overwrite.
                                    # Eager reads instead use their AST position.
                                    invocation_sites = (
                                        module_invocation_sites(use)
                                        if deferred_read else []
                                    )
                                    if not invocation_sites:
                                        invocation_sites = [(use_pos, _node_control_path(use))]
                                    if deferred_read and use_pos <= import_pos:
                                        invocation_sites = [
                                            (pos, path)
                                            for pos, path in invocation_sites
                                            if pos > import_pos
                                        ]
                                    if not invocation_sites:
                                        continue
                                    # Walk module-level reaching
                                    # writes rather than only tree.body. A
                                    # guaranteed assignment nested under
                                    # "if True" or both arms of an if/else
                                    # shadows the imported name just as a
                                    # direct store does. Unknown branches
                                    # retain the live-import possibility.
                                    use_path = _node_control_path(use)

                                    def after_header(expression, states):
                                        """Track the header's walrus writes before its arm."""
                                        if not states:
                                            return set()
                                        incoming = {name: set()}
                                        if True in states:
                                            incoming[name].add(node)
                                        if False in states:
                                            incoming[name].add(None)
                                        values = named_expr_bindings(
                                            expression, incoming
                                        )[name]
                                        possible = set()
                                        for value in values:
                                            if value is node:
                                                possible.add(True)
                                            elif value is None:
                                                possible.add(False)
                                            elif any(
                                                isinstance(child, ast.Name)
                                                and isinstance(child.ctx, ast.Load)
                                                and child.id == name
                                                and _binding_name_token(
                                                    name, bound_names(), child
                                                )[0] is tree
                                                for child in ast.walk(value)
                                            ):
                                                # Transformed self-reads retain
                                                # whichever source was reaching.
                                                possible.update(states)
                                            else:
                                                possible.add(False)
                                        return possible

                                    def conditional_header(expression, states, truth):
                                        """Track writes only along paths where test has truth.

                                        For AND's true arm, every operand must
                                        have executed; for OR's false arm likewise.
                                        The opposite arm unions each possible
                                        short-circuit point, preserving unsafe
                                        no-write paths.
                                        """
                                        if not states:
                                            return set()
                                        if isinstance(expression, ast.Constant):
                                            return (
                                                states if bool(expression.value) is truth
                                                else set()
                                            )
                                        if isinstance(expression, ast.UnaryOp) and isinstance(
                                            expression.op, ast.Not
                                        ):
                                            return conditional_header(
                                                expression.operand, states, not truth
                                            )
                                        if isinstance(expression, ast.BoolOp):
                                            is_and = isinstance(expression.op, ast.And)
                                            must_evaluate_all = is_and == truth
                                            if must_evaluate_all:
                                                result = states
                                                for part in expression.values:
                                                    result = conditional_header(
                                                        part, result, truth
                                                    )
                                                return result
                                            result = set()
                                            continuing = states
                                            for part in expression.values:
                                                result |= conditional_header(
                                                    part, continuing, truth
                                                )
                                                continuing = conditional_header(
                                                    part, continuing, not truth
                                                )
                                            return result
                                        return after_header(expression, states)

                                    def live_after(statements, states):
                                        for statement in statements:
                                            if _node_position(statement) <= import_pos:
                                                continue
                                            if _node_position(statement) >= cutoff_pos:
                                                break
                                            if isinstance(statement, ast.If):
                                                # If this read occurs within one arm,
                                                # the other arm cannot reach this
                                                # particular use. Retain both paths
                                                # only for uses after the if statement.
                                                if any(
                                                    child is use
                                                    for child in ast.walk(statement.test)
                                                ):
                                                    break  # Test is read before either arm.
                                                tested = (
                                                    statement.test.value
                                                    if isinstance(
                                                        statement.test, ast.Constant
                                                    ) else None
                                                )
                                                branch = (
                                                    "If",
                                                    statement.lineno,
                                                    statement.col_offset,
                                                )
                                                true_states = conditional_header(
                                                    statement.test, states, True
                                                )
                                                false_states = conditional_header(
                                                    statement.test, states, False
                                                )
                                                tested_states = true_states | false_states
                                                if (*branch, "body") in use_path:
                                                    states = (
                                                        live_after(statement.body, true_states)
                                                        if tested is not False else set()
                                                    )
                                                elif (*branch, "orelse") in use_path:
                                                    states = (
                                                        live_after(statement.orelse, false_states)
                                                        if tested is not True else set()
                                                    )
                                                elif tested is True:
                                                    states = live_after(
                                                        statement.body, true_states
                                                    )
                                                elif tested is False:
                                                    states = live_after(
                                                        statement.orelse, false_states
                                                    )
                                                else:
                                                    states = (
                                                        live_after(
                                                            statement.body, true_states
                                                        )
                                                        | live_after(
                                                            statement.orelse, false_states
                                                        )
                                                    )
                                                continue
                                            # The RHS of the statement
                                            # containing this particular read
                                            # runs before its assignment store.
                                            if (
                                                not deferred_read
                                                and any(
                                                    child is use
                                                    for child in ast.walk(statement)
                                                )
                                            ):
                                                # A deferred body is only
                                                # executed at its invocation
                                                # cutoff, not when its enclosing
                                                # function is defined.
                                                break
                                            targets = (
                                                statement.targets
                                                if isinstance(statement, ast.Assign)
                                                else [statement.target]
                                                if isinstance(statement, ast.AnnAssign)
                                                and statement.value is not None
                                                else []
                                            )
                                            if not targets:
                                                continue
                                            leaves = [
                                                (target_name, value)
                                                for target in targets
                                                for target_name, value in
                                                assigned_leaves(
                                                    target, statement.value
                                                )
                                            ]
                                            selected_values = [
                                                value for target_name, value in leaves
                                                if target_name == name
                                            ]
                                            if not selected_values:
                                                continue
                                            # Preserve the incoming import
                                            # when this name's own RHS leaf
                                            # reads it (including transforms).
                                            self_reads = any(
                                                isinstance(child, ast.Name)
                                                and isinstance(child.ctx, ast.Load)
                                                and child.id == name
                                                and _binding_name_token(
                                                    child.id, bound_names(), child
                                                )[0] is tree
                                                for value in selected_values
                                                for child in ast.walk(value)
                                            )
                                            states = states if self_reads else {False}
                                        return states

                                    # Keep invocation positions in this
                                    # lexical frame: live_after captures the
                                    # selected position and branch path.
                                    for cutoff_pos, use_path in invocation_sites:
                                        if True in live_after(tree.body, {True}):
                                            exported.add(name)
                                            break
                                    if name in exported:
                                        break
                        elif (
                            (alias.asname or alias.name) in used_names
                            or node in forwarded_import_nodes
                            and (alias.asname or alias.name) in forwarded_exports
                        ):
                            exported.add(alias.name)
                # "from providers import credential_provider" is a module
                # import, whose exported secret sits on a subsequent attribute.
                for alias in node.names:
                    if alias.name != dependency.stem:
                        continue
                    local = alias.asname or alias.name
                    exported.update(
                        chain[1]
                        for chain in used_chains
                        if len(chain) == 2 and chain[0] == local
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[-1] != dependency.stem:
                        continue
                    # "import providers.credential_provider" binds 'providers',
                    # not the leaf module as an independent local name.
                    prefix = (
                        (alias.asname,)
                        if alias.asname
                        else tuple(alias.name.split("."))
                    )
                    exported.update(
                        chain[-1]
                        for chain in used_chains
                        if len(chain) == len(prefix) + 1
                        and chain[:len(prefix)] == prefix
                    )
        return exported

    def _imported_credential_call_arguments(
        self, source, dependency, selected_exports
    ):
        """Pass statically known credential-call arguments to imported providers.

        Only calls feeding a recognized credential value are used. Literal
        values of their arguments are analyzed in the *consumer* scope before
        crossing the module boundary; unrelated calls stay out of the scan.
        """
        if not selected_exports:
            return []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        bindings = _name_bindings(tree)
        direct_names = {}
        module_names = set()
        import_sites = {}
        for statement in ast.walk(tree):
            if isinstance(statement, ast.ImportFrom):
                tail = (statement.module or "").split(".")[-1]
                if tail == dependency.stem or (
                    dependency.name == "__init__.py"
                    and tail == dependency.parent.name
                ):
                    for item in statement.names:
                        if item.name in selected_exports:
                            local = item.asname or item.name
                            direct_names[local] = item.name
                            import_sites.setdefault(local, []).append(statement)
                if any(item.name == dependency.stem for item in statement.names):
                    for item in statement.names:
                        if item.name == dependency.stem:
                            local = item.asname or item.name
                            module_names.add(local)
                            import_sites.setdefault(local, []).append(statement)
                if any(item.name == "*" for item in statement.names):
                    direct_names.update(
                        (name, name) for name in selected_exports
                    )
                    for name in selected_exports:
                        import_sites.setdefault(name, []).append(statement)
            elif isinstance(statement, ast.Import):
                for item in statement.names:
                    if item.name.split(".")[-1] == dependency.stem:
                        local = item.asname or item.name.split(".", 1)[0]
                        module_names.add(local)
                        import_sites.setdefault(local, []).append(statement)

        if_nodes = {
            ("If", *_node_position(node)): node
            for node in ast.walk(tree) if isinstance(node, ast.If)
        }

        def guaranteed_overwrite(writes):
            """Whether all feasible control paths execute a replacement.

            Imported names do not occur in _name_bindings. A conditional
            replacement therefore cannot erase the untouched import path.
            """
            if any(not _node_control_path(value) for _, value in writes):
                return True
            arms = {}
            for _, value in writes:
                path = _node_control_path(value)
                if len(path) != 1 or path[0][0] != "If":
                    continue
                step = path[0]
                key = step[:3]
                arms.setdefault(key, set()).add(step[3])
            for key, present in arms.items():
                statement = if_nodes.get(key)
                if statement is None:
                    continue
                if {"body", "orelse"}.issubset(present):
                    return True
                if isinstance(statement.test, ast.Constant):
                    selected = (
                        "body" if bool(statement.test.value) else "orelse"
                    )
                    if selected in present:
                        return True
            return False

        def potentially_imported(name, use_position):
            """An imported local name may survive conditional overwrites."""
            imports = [
                import_node for import_node in import_sites.get(name, ())
                if _node_position(import_node) <= use_position
            ]
            if not imports:
                return False
            scope = bindings["metadata"]["module"]
            writes = bindings["values"].get(scope, {}).get(name, ())
            for import_node in imports:
                start = _node_position(import_node)
                later = [
                    (position, value) for position, value in writes
                    if start < position <= use_position
                ]
                if not guaranteed_overwrite(later):
                    return True
            return False

        def possible_original_names(name, use_position, seen=None):
            """Follow alias copies only while their earlier value can reach."""
            seen = set() if seen is None else seen
            if name in seen:
                return set()
            seen = seen | {name}
            choices = set()
            if potentially_imported(name, use_position):
                choices.add(name)
            scope = bindings["metadata"]["module"]
            writes = [
                (position, value)
                for position, value in
                bindings["values"].get(scope, {}).get(name, ())
                if position <= use_position
            ]
            for index, (position, value) in enumerate(writes):
                if guaranteed_overwrite(writes[index + 1:]):
                    continue
                if isinstance(value, ast.Name):
                    choices.update(
                        possible_original_names(
                            value.id, position, seen
                        )
                    )
            return choices

        def provider_export(func):
            # Include an import kept alive by a conditional overwrite even
            # when the ordinary local binding resolver sees only the
            # conditional replacement. Guaranteed overwrites still win.
            candidates = _resolve_bound_nodes(
                func, bindings, _node_position(func)
            )
            for candidate in [func, *candidates]:
                if isinstance(candidate, ast.Name):
                    for name in possible_original_names(
                        candidate.id, _node_position(func)
                    ):
                        export = direct_names.get(name)
                        if export is not None:
                            return export
                elif isinstance(candidate, ast.Attribute):
                    if candidate.attr not in selected_exports:
                        continue
                    root = candidate.value
                    while isinstance(root, ast.Attribute):
                        root = root.value
                    if isinstance(root, ast.Name):
                        possible = possible_original_names(
                            root.id, _node_position(func)
                        )
                        if possible & module_names:
                            return candidate.attr
            return None

        secret_keys = {
            "password", "api_key", "bearer_auth", "basic_auth",
            "http_auth", "authorization",
        }

        def password_sides(value, key):
            if key not in {"basic_auth", "http_auth"}:
                return [value]
            possible = (
                [value] if isinstance(value, (ast.Tuple, ast.List))
                else _resolve_bound_nodes(
                    value, bindings, _node_position(value)
                )
            )
            return [
                item.elts[1] for item in possible
                if isinstance(item, (ast.Tuple, ast.List))
                and len(item.elts) >= 2
            ] or [value]

        expressions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg in secret_keys:
                expressions.extend(password_sides(node.value, node.arg))
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value.lower() in secret_keys
                    ):
                        expressions.extend(
                            password_sides(value, key.value.lower())
                        )
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                if node.value is None:
                    continue
                targets = (
                    node.targets if isinstance(node, ast.Assign)
                    else [node.target]
                )
                if any(
                    isinstance(target, ast.Name)
                    and target.id.lower() in secret_keys
                    for target in targets
                ):
                    expressions.append(node.value)

        def static_argument_choices(expression, seen=None):
            """Transfer every known consumer possibility into provider scope.

            Keep literal tuple/list/dict shape for indexed provider returns;
            do not collapse a structure to a string found in another slot.
            Unknown runtime inputs become None, not invented secrets.
            """
            seen = set() if seen is None else seen
            if expression in seen:
                return [ast.copy_location(ast.Constant(value=None), expression)]
            seen = seen | {expression}
            if isinstance(expression, ast.IfExp):
                return [
                    *static_argument_choices(expression.body, seen),
                    *static_argument_choices(expression.orelse, seen),
                ]
            if isinstance(expression, (ast.Tuple, ast.List)):
                # List/tuple displays can contain known *unpack expressions;
                # their resulting positions differ from the syntax indices.
                alternatives = []
                for child in expression.elts:
                    if isinstance(child, ast.Starred):
                        groups = [
                            list(value.elts)
                            for value in static_argument_choices(
                                child.value, seen
                            )
                            if isinstance(value, (ast.Tuple, ast.List))
                            and not any(
                                isinstance(elt, ast.Starred)
                                for elt in value.elts
                            )
                        ]
                        if not groups:
                            return [ast.copy_location(
                                ast.Constant(value=None), expression
                            )]
                        alternatives.append(groups)
                    else:
                        alternatives.append([
                            [value] for value in
                            static_argument_choices(child, seen)
                        ])
                return [
                    ast.copy_location(
                        type(expression)(
                            elts=[
                                elt for group in combination for elt in group
                            ],
                            ctx=ast.Load(),
                        ), expression,
                    )
                    for combination in product(*alternatives)
                ]
            if isinstance(expression, ast.Dict):
                # Evaluate explicit keys and ** mapping spreads in consumer
                # scope, preserving each possible source-order overwrite.
                # Condition-dependent key/value alternatives must preserve the
                # *same* branch, not invent an infeasible Cartesian pairing.
                def merge_constraints(*sets):
                    """Combine feasible correlated branch selections."""
                    merged = {}
                    for group in sets:
                        for branch, selected in group:
                            if branch in merged and merged[branch] != selected:
                                return None
                            merged[branch] = selected
                    return frozenset(merged.items())

                def condition_identity(test):
                    """Return the condition's binding epoch and known polarity.

                    A general name reassignment starts a new decision epoch.
                    The special deterministic `flag = not flag` inverts the
                    previous decision rather than making it unrelated; fold
                    those rebindings into a polarity bit to keep valid paths
                    and reject impossible key/value combinations.
                    """
                    # Calls (such as next(iterator)) and nontrivial lookups
                    # may produce different results at each evaluation even
                    # without a visible name assignment. Never correlate them
                    # just because their source text is identical.
                    explicit_negation = (
                        isinstance(test, ast.UnaryOp)
                        and isinstance(test.op, ast.Not)
                        and isinstance(test.operand, ast.Name)
                    )
                    normalized_test = (
                        test.operand if explicit_negation else test
                    )
                    if not isinstance(normalized_test, ast.Name):
                        return (
                            ("independent-evaluation", _node_position(test)),
                            False,
                        )
                    position = _node_position(test)
                    references = {}
                    inverted = explicit_negation
                    for name in ast.walk(normalized_test):
                        if not (
                            isinstance(name, ast.Name)
                            and isinstance(name.ctx, ast.Load)
                        ):
                            continue
                        scope, binding_name = _binding_name_token(
                            name.id, bindings, name
                        )
                        writes = [
                            (write_position, value)
                            for write_position, value in
                            bindings["values"].get(scope, {}).get(
                                binding_name, ()
                            )
                            if write_position <= position
                        ]
                        if name is normalized_test:
                            # Only strip unconditionally executed self-flips.
                            # A conditional write needs its own epoch because
                            # its inversion may not have executed.
                            while writes:
                                write_position, value = writes[-1]
                                if not (
                                    isinstance(value, ast.UnaryOp)
                                    and isinstance(value.op, ast.Not)
                                    and isinstance(value.operand, ast.Name)
                                    and value.operand.id == binding_name
                                    and not _node_control_path(value)
                                ):
                                    break
                                inverted = not inverted
                                writes.pop()
                        references[(scope, binding_name)] = tuple(
                            write_position for write_position, _ in writes
                        )
                    signature = tuple(
                        sorted(
                            (
                                (id(scope), name, epochs)
                                for (scope, name), epochs in references.items()
                            ),
                            key=lambda item: (item[1], item[0]),
                        )
                    )
                    return (
                        ast.dump(normalized_test, include_attributes=False),
                        signature,
                    ), inverted

                def traced_choices(element):
                    """Return AST candidates with all feasible branch constraints."""
                    if isinstance(element, ast.IfExp):
                        branch, inverted = condition_identity(element.test)
                        choices = []
                        for selected, arm in (
                            (True, element.body), (False, element.orelse)
                        ):
                            # Normalize a known self-negation to the original
                            # condition's polarity before correlating branches.
                            required = frozenset((
                                (branch, selected != inverted),
                            ))
                            for value, nested in traced_choices(arm):
                                correlated = merge_constraints(
                                    required, nested
                                )
                                if correlated is not None:
                                    choices.append((value, correlated))
                        return choices
                    if isinstance(element, ast.Name):
                        resolves = [
                            resolved for resolved in _resolve_bound_nodes(
                                element, bindings, _node_position(element)
                            )
                            if resolved is not element
                            and not (
                                isinstance(resolved, ast.Name)
                                and resolved.id == element.id
                            )
                        ]
                        if resolves:
                            return [
                                (value, constraints)
                                for resolved in resolves
                                for value, constraints in traced_choices(resolved)
                            ]
                    return [
                        (value, frozenset())
                        for value in static_argument_choices(element, seen)
                    ]

                alternatives = []
                for key, value in zip(expression.keys, expression.values):
                    if key is None:
                        possibilities = [
                            (list(zip(mapping.keys, mapping.values)), constraints)
                            for mapping, constraints in traced_choices(value)
                            if isinstance(mapping, ast.Dict)
                            and all(k is not None for k in mapping.keys)
                        ]
                    else:
                        possibilities = []
                        for resolved_key, key_constraints in traced_choices(key):
                            for resolved_value, value_constraints in traced_choices(
                                value
                            ):
                                merged = merge_constraints(
                                    key_constraints, value_constraints
                                )
                                if merged is not None:
                                    possibilities.append((
                                        [(resolved_key, resolved_value)],
                                        merged,
                                    ))
                    if not possibilities:
                        return [ast.copy_location(
                            ast.Constant(value=None), expression
                        )]
                    alternatives.append(possibilities)
                mappings = []
                for groups in product(*alternatives):
                    if merge_constraints(
                        *(constraints for _, constraints in groups)
                    ) is None:
                        continue
                    entries = []
                    for group, _constraints in groups:
                        for key, value in group:
                            try:
                                comparable = ast.literal_eval(key)
                                hash(comparable)
                            except (ValueError, TypeError, RecursionError):
                                comparable = None
                            if comparable is not None:
                                entries = [
                                    (earlier, old_value)
                                    for earlier, old_value in entries
                                    if not (
                                        isinstance(earlier, ast.Constant)
                                        and earlier.value == comparable
                                    )
                                ]
                            entries.append((key, value))
                    mappings.append(ast.copy_location(ast.Dict(
                        keys=[key for key, _ in entries],
                        values=[value for _, value in entries],
                    ), expression))
                return mappings
            if isinstance(expression, ast.Name):
                resolved = [
                    value for value in _resolve_bound_nodes(
                        expression, bindings, _node_position(expression)
                    ) if value is not expression
                    and not (
                        isinstance(value, ast.Name)
                        and value.id == expression.id
                    )
                ]
                if resolved:
                    return [
                        choice for value in resolved
                        for choice in static_argument_choices(value, seen)
                    ]
            if isinstance(expression, ast.Subscript):
                selected = _resolve_constant_subscript(
                    expression, bindings, _node_position(expression)
                )
                if selected is not None:
                    return static_argument_choices(selected, seen)
            try:
                literal = ast.literal_eval(expression)
            except (ValueError, TypeError, RecursionError):
                literal = None
            else:
                return [ast.copy_location(
                    ast.parse(repr(literal), mode="eval").body, expression
                )]
            # Unknown lookups stay opaque. For known local transforms, retain
            # every statically proven returned credential, not values[0].
            values = _hardcoded_password_values(
                expression, bindings, _node_position(expression)
            )
            if values:
                return [
                    ast.copy_location(ast.Constant(value=value), expression)
                    for value in dict.fromkeys(values)
                ]
            return [ast.copy_location(ast.Constant(value=None), expression)]

        results = []
        for expr in expressions:
            roots = _resolve_bound_nodes(
                expr, bindings, _node_position(expr)
            )
            for root in roots:
                for call in ast.walk(root):
                    if not isinstance(call, ast.Call):
                        continue
                    exported_name = provider_export(call.func)
                    if exported_name is None:
                        continue
                    # Expand only statically known argument spreads.
                    # Unknown *args/**kwargs are opaque rather than inspected
                    # as if their contents were returned passwords.
                    argument_options = []
                    for arg in call.args:
                        if isinstance(arg, ast.Starred):
                            variants = [
                                list(value.elts)
                                for value in static_argument_choices(
                                    arg.value
                                )
                                if isinstance(value, (ast.Tuple, ast.List))
                                and not any(
                                    isinstance(item, ast.Starred)
                                    for item in value.elts
                                )
                            ]
                        else:
                            variants = [
                                [value] for value in
                                static_argument_choices(arg)
                            ]
                        if not variants:
                            break
                        argument_options.append(variants)
                    else:
                        keyword_options = []
                        for kw in call.keywords:
                            if kw.arg is None:
                                variants = []
                                for mapping in static_argument_choices(kw.value):
                                    if not isinstance(mapping, ast.Dict):
                                        continue
                                    pairs = []
                                    for key, value in zip(
                                        mapping.keys, mapping.values
                                    ):
                                        if not (
                                            isinstance(key, ast.Constant)
                                            and isinstance(key.value, str)
                                            # **kwargs accepts any string key,
                                            # even one that is not an identifier.
                                        ):
                                            break
                                        pairs.append(ast.keyword(
                                            arg=key.value, value=value
                                        ))
                                    else:
                                        variants.append(pairs)
                            else:
                                variants = [
                                    [ast.keyword(arg=kw.arg, value=value)]
                                    for value in
                                    static_argument_choices(kw.value)
                                ]
                            if not variants:
                                break
                            keyword_options.append(variants)
                        else:
                            for argument_groups in product(*argument_options):
                                args = tuple(
                                    value for group in argument_groups
                                    for value in group
                                )
                                for keyword_groups in product(*keyword_options):
                                    keywords = tuple(
                                        value for group in keyword_groups
                                        for value in group
                                    )
                                    keyword_names = [
                                        value.arg for value in keywords
                                    ]
                                    if len(set(keyword_names)) != len(
                                        keyword_names
                                    ):
                                        continue
                                    results.append((
                                        exported_name, args, keywords
                                    ))
        return results

    def _imported_credential_class_accesses(self, source, dependency, exports):
        """Match class members used by a consumer's authentication expression."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}
        direct = {}
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[-1] == dependency.stem:
                    for alias in node.names:
                        if alias.name in exports:
                            direct[alias.asname or alias.name] = alias.name
                for alias in node.names:
                    if alias.name == dependency.stem:
                        modules.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[-1] == dependency.stem:
                        modules.add(alias.asname or alias.name.split(".", 1)[0])
        parents = {
            child: parent for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        bindings = _name_bindings(tree)

        def class_module_import_survives(name, use):
            """Keep ordinary imports reachable after conditional shadows."""
            imported = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                and any(
                    (alias.asname or alias.name.split(".", 1)[0]) == name
                    and alias.name.split(".")[-1] == dependency.stem
                    for alias in node.names
                )
                and _node_position(node) <= _node_position(use)
            ]
            if not imported:
                return False
            if _binding_name_token(name, bindings, use)[0] is not tree:
                return False
            for statement in imported:
                writes = [
                    (position, value)
                    for position, value in
                    bindings["values"].get(tree, {}).get(name, ())
                    if _node_position(statement) < position <= _node_position(use)
                ]
                if not any(
                    not _node_control_path(value)
                    and not (
                        isinstance(value, ast.Name) and value.id == name
                    )
                    for _, value in writes
                ):
                    return True
            return False

        def imported_class_owner(expression, at_position, seen=None):
            """Follow reaching instance aliases to a selected class import.

            A constructor result is an instance of the imported class, but
            only the member actually used by authentication is selected.
            """
            seen = set() if seen is None else seen
            if id(expression) in seen:
                return None
            seen = seen | {id(expression)}
            if isinstance(expression, ast.Call):
                # A constructor with arguments still yields an instance of
                # the imported class. Do not model __new__/__init__ effects;
                # only preserve class identity for selecting auth members.
                return imported_class_owner(expression.func, at_position, seen)
            if isinstance(expression, ast.Name):
                if expression.id in direct:
                    return direct[expression.id]
                candidates = _resolve_bound_nodes(
                    expression, bindings, at_position
                )
                owners = {
                    owner for candidate in candidates
                    if candidate is not expression
                    for owner in [
                        imported_class_owner(candidate, at_position, seen)
                    ]
                    if owner is not None
                }
                return next(iter(owners)) if len(owners) == 1 else None
            if (
                isinstance(expression, ast.Attribute)
                and expression.attr in exports
                and isinstance(expression.value, ast.Name)
            ):
                # A module import can be copied before constructing a class:
                #   import provider as cp; alias = cp; alias.Config(...)
                # Follow reaching assignments rather than assuming the module
                # must be accessed by its original import alias.
                candidates = _resolve_bound_nodes(
                    expression.value, bindings, at_position
                )
                if any(
                    isinstance(candidate, ast.Name)
                    and candidate.id in modules
                    and class_module_import_survives(
                        candidate.id, expression.value
                    )
                    for candidate in [expression.value, *candidates]
                ):
                    return expression.attr
            return None

        def is_auth_source(node):
            while node in parents:
                node = parents[node]
                if isinstance(node, ast.keyword) and node.arg in {
                    "basic_auth", "http_auth", "api_key", "bearer_auth",
                    "authorization", "password"
                }:
                    return True
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(
                        isinstance(target, ast.Name)
                        and target.id.lower() in {"password", "credential", "token"}
                        for target in targets
                    ):
                        return True
            return False
        members = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not is_auth_source(node):
                continue
            class_name = imported_class_owner(
                node.value, _node_position(node)
            )
            if class_name:
                members.setdefault(class_name, set()).add(node.attr)
        return members

    def _es_wrapper_password_parameters(self, source):
        """Find source-visible exported wrappers forwarding parameters to ES."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}
        wrappers = {}
        for statement in tree.body:
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            positional = [*statement.args.posonlyargs, *statement.args.args]
            parameters = {
                argument.arg: index for index, argument in enumerate(positional)
            }
            # Keyword-only parameters have no legal positional index.
            parameters.update({
                argument.arg: None for argument in statement.args.kwonlyargs
            })
            auth_parameters = set()
            for call in ast.walk(statement):
                if not isinstance(call, ast.Call):
                    continue
                fn = call.func
                is_es = (
                    isinstance(fn, ast.Name)
                    and fn.id in {"Elasticsearch", "AsyncElasticsearch"}
                ) or (
                    isinstance(fn, ast.Attribute)
                    and fn.attr in {"Elasticsearch", "AsyncElasticsearch"}
                )
                if not is_es:
                    continue
                for keyword in call.keywords:
                    if keyword.arg not in {
                        "basic_auth", "http_auth", "api_key", "bearer_auth"
                    }:
                        continue
                    expression = keyword.value
                    if (
                        keyword.arg in {"basic_auth", "http_auth"}
                        and isinstance(expression, (ast.Tuple, ast.List))
                        and len(expression.elts) > 1
                    ):
                        expression = expression.elts[1]
                    if isinstance(expression, ast.Name) and expression.id in parameters:
                        auth_parameters.add(expression.id)
            if auth_parameters:
                wrappers[statement.name] = {
                    name: parameters[name] for name in auth_parameters
                }
        return wrappers

    def _es_wrapper_caller_credentials(self, source, wrapper_path, wrappers):
        """Return wrapper invocations and literal credential call-site lines."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False, []
        direct = {}
        modules = set()
        import_sites = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[-1] == wrapper_path.stem:
                    for alias in node.names:
                        if alias.name in wrappers:
                            name = alias.asname or alias.name
                            direct[name] = alias.name
                            import_sites.setdefault(name, []).append(node)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[-1] == wrapper_path.stem:
                        name = alias.asname or alias.name.split(".", 1)[0]
                        modules.add(name)
                        import_sites.setdefault(name, []).append(node)
        if not direct and not modules:
            return False, []
        bindings = _name_bindings(tree)
        module_scope = bindings["metadata"]["module"]
        branch_nodes = {
            ("If", *_node_position(node)): node
            for node in ast.walk(tree) if isinstance(node, ast.If)
        }

        def definitely_overwritten(writes, import_name):
            """Keep imported callables restored via source-visible aliases."""
            def retained_identity(value, position, visited=None):
                visited = set() if visited is None else visited
                if not isinstance(value, ast.Name):
                    return False
                if value.id == import_name:
                    return True
                if value.id in visited:
                    return False
                alias_writes = [
                    (at, rhs) for at, rhs in
                    bindings["values"].get(module_scope, {}).get(value.id, ())
                    if at < position
                ]
                if not alias_writes:
                    return False
                at, rhs = alias_writes[-1]
                return not _node_control_path(rhs) and retained_identity(
                    rhs, at, visited | {value.id}
                )

            writes = [
                (position, value) for position, value in writes
                if not retained_identity(value, position)
            ]
            for _position, value in writes:
                control = _node_control_path(value)
                if not control:
                    return True
                if len(control) == 1 and control[0][0] == "If":
                    step = control[0]
                    condition = branch_nodes.get(step[:3])
                    if (
                        condition is not None
                        and isinstance(condition.test, ast.Constant)
                        and (
                            (bool(condition.test.value) and step[3] == "body")
                            or (not bool(condition.test.value)
                                and step[3] == "orelse")
                        )
                    ):
                        return True
            arms = {}
            for _position, value in writes:
                path = _node_control_path(value)
                if len(path) == 1 and path[0][0] == "If":
                    arms.setdefault(path[0][:3], set()).add(path[0][3])
            return any(
                {"body", "orelse"} <= arms
                for arms in arms.values()
            )

        def imported_name_survives(name, use):
            """An import is still reaching after only conditional shadows."""
            use_position = _node_position(use)
            if _binding_name_token(name, bindings, use)[0] is not module_scope:
                return False
            imports = [
                statement for statement in import_sites.get(name, ())
                if _node_position(statement) <= use_position
            ]
            for statement in imports:
                start = _node_position(statement)
                writes = [
                    (position, value)
                    for position, value in
                    bindings["values"].get(module_scope, {}).get(name, ())
                    if start < position <= use_position
                ]
                if not definitely_overwritten(writes, name):
                    return True
            return False

        invoked = False
        lines = []
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            # A wrapper can be reached through source-visible local aliases:
            #   from client import connect; open_es = connect; open_es(...)
            #   import client as cl; alias = cl; alias.connect(...)
            # Use reaching bindings so overwritten aliases are not resurrected.
            name = None
            candidates = _resolve_bound_nodes(
                call.func, bindings, _node_position(call.func)
            )
            for candidate in [call.func, *candidates]:
                if isinstance(candidate, ast.Name):
                    export = direct.get(candidate.id)
                    if export is not None and imported_name_survives(
                        candidate.id, call.func
                    ):
                        name = export
                        break
                elif isinstance(candidate, ast.Attribute):
                    if not isinstance(candidate.value, ast.Name):
                        continue
                    modules_reaching = _resolve_bound_nodes(
                        candidate.value, bindings,
                        _node_position(candidate.value)
                    )
                    if any(
                        isinstance(module, ast.Name)
                        and module.id in modules
                        and imported_name_survives(
                            module.id, candidate.value
                        )
                        for module in [candidate.value, *modules_reaching]
                    ):
                        name = candidate.attr
                        break
            if name not in wrappers:
                continue
            invoked = True
            for parameter, index in wrappers[name].items():
                expression = (
                    call.args[index]
                    if index is not None and len(call.args) > index
                    else next(
                        (keyword.value for keyword in call.keywords
                         if keyword.arg == parameter), None
                    )
                )
                if expression is None or isinstance(expression, ast.Starred):
                    continue
                values = _hardcoded_password_values(
                    expression, bindings, _node_position(expression)
                )
                if any(
                    value and value != REDACTED_PASSWORD_SENTINEL
                    for value in values
                ):
                    lines.append(call.lineno)
        return invoked, sorted(set(lines))

    def _runtime_es_module_paths(self):
        paths = {path.resolve() for path in RUNTIME_ES_MODULES}
        self._imported_credential_class_members = {}
        self._es_wrapper_credential_lines = {}
        candidate_modules = set()

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
                candidate_modules.add(path.resolve())
                if any(marker in source for marker in ES_RUNTIME_MARKERS):
                    paths.add(path.resolve())

        # Trace reverse-imported callers only when they invoke a wrapper
        # proven to forward a named argument into an Elasticsearch auth sink.
        wrapper_exports = {}
        for path in paths:
            if path.is_file() and path.suffix == ".py":
                source = path.read_text(encoding="utf-8-sig", errors="ignore")
                exported = self._es_wrapper_password_parameters(source)
                if exported:
                    wrapper_exports[path] = exported
        # Inspect every candidate, including marker-matched files already
        # present in paths. Being included in the generic scan does not mean
        # a wrapper call's positional credential has been checked.
        for caller in candidate_modules:
            source = caller.read_text(encoding="utf-8-sig", errors="ignore")
            if not any(wrapper.stem in source for wrapper in wrapper_exports):
                continue
            dependencies = set(self._local_imported_python_paths(caller, source))
            for wrapper, exported in wrapper_exports.items():
                if wrapper not in dependencies:
                    continue
                invoked, line_numbers = self._es_wrapper_caller_credentials(
                    source, wrapper, exported
                )
                if invoked:
                    paths.add(caller)
                if line_numbers:
                    self._es_wrapper_credential_lines.setdefault(
                        caller, set()
                    ).update(line_numbers)

        # Walk the local import graph to find credential-provider modules,
        # without broadening this *ES* guard to unrelated library functions
        # (which can contain test-only or non-ES credential examples).
        pending = list(paths)
        processed = {}
        imported_exports = {}
        while pending:
            path = pending.pop()
            if not path.is_file():
                continue
            selected_here = frozenset(imported_exports.get(path, ()))
            if processed.get(path) == selected_here:
                continue
            processed[path] = selected_here
            source = path.read_text(encoding="utf-8-sig", errors="ignore")
            for dependency in self._local_imported_python_paths(path, source):
                exports = imported_exports.setdefault(dependency, set())
                before = len(exports)
                exports.update(
                    self._credential_import_exports(
                        source, dependency, selected_here, importing_path=path
                    )
                )
                provider_source = dependency.read_text(
                    encoding="utf-8-sig", errors="ignore"
                )
                call_arguments = self._imported_credential_call_arguments(
                    source, dependency, exports
                )
                selected_classes = self._imported_credential_class_members.setdefault(
                    dependency, {}
                )
                for class_name, members in self._imported_credential_class_accesses(
                    source, dependency, exports
                ).items():
                    selected_classes.setdefault(class_name, set()).update(members)
                if self._module_uppercase_credential_literals(
                    provider_source, exports, call_arguments, selected_classes
                ):
                    paths.add(dependency)
                if dependency not in processed or len(exports) != before:
                    pending.append(dependency)

        self._imported_credential_exports = imported_exports
        return sorted(paths)

    def _module_uppercase_credential_literals(
        self, source, exported_names=(), imported_calls=(),
        selected_class_members=None,
    ):
        """Catch imported providers exporting a literal credential constant."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        bindings = _name_bindings(tree)
        violations = []
        def assigned_leaves(target, value):
            """Associate tuple/list unpacked names with the actual RHS slots."""
            if isinstance(target, ast.Name):
                yield target.id, value
            elif isinstance(target, (ast.Tuple, ast.List)):
                resolved = _resolve_bound_nodes(value, bindings, _node_position(value))
                for item in resolved:
                    if isinstance(item, (ast.Tuple, ast.List)) and len(item.elts) == len(target.elts):
                        for subtarget, subvalue in zip(target.elts, item.elts):
                            yield from assigned_leaves(subtarget, subvalue)

        def exported_return_expressions(body):
            """Fold simple provider-local stores into each reachable return.

            Preserve only source-visible linear assignments and If branches.
            Unsupported side-effecting control flow stays opaque; in
            particular, an unused secret-valued local is not a credential.
            """
            if (
                body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]

            def substitute(expression, local_values):
                if expression is None:
                    return ast.Constant(value=None)

                class ReplaceLocals(ast.NodeTransformer):
                    def visit_Name(self, node):
                        if (
                            isinstance(node.ctx, ast.Load)
                            and node.id in local_values
                        ):
                            return copy.deepcopy(local_values[node.id])
                        return node

                    def visit_Lambda(self, node):
                        # Parameter shadowing / deferred capture is not
                        # modeled by the local straight-line fold.
                        return node

                return ReplaceLocals().visit(copy.deepcopy(expression))

            def collect(statements, locals_, depth):
                if not statements or depth > 30:
                    return []
                first, *remaining = statements
                if isinstance(first, ast.Return):
                    return [substitute(first.value, locals_)]
                if isinstance(first, ast.Pass):
                    return collect(remaining, locals_, depth + 1)
                if isinstance(first, ast.If):
                    if isinstance(first.test, ast.Constant):
                        arms = [first.body if first.test.value else first.orelse]
                    else:
                        arms = [first.body, first.orelse]
                    return [
                        expression
                        for arm in arms
                        for expression in collect(
                            [*arm, *remaining], dict(locals_), depth + 1
                        )
                    ][:32]
                if isinstance(first, ast.Assign):
                    targets = first.targets
                    if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                        return []
                    name, value = targets[0].id, first.value
                elif (
                    isinstance(first, ast.AnnAssign)
                    and isinstance(first.target, ast.Name)
                    and first.value is not None
                ):
                    name, value = first.target.id, first.value
                else:
                    return []
                next_locals = dict(locals_)
                next_locals[name] = substitute(value, locals_)
                return collect(remaining, next_locals, depth + 1)

            return collect(body, {}, 0)

        for statement in tree.body:
            if isinstance(statement, ast.ClassDef):
                selected = (selected_class_members or {}).get(statement.name, ())
                if statement.name not in exported_names or not selected:
                    continue
                class_values = {}
                for member in statement.body:
                    if isinstance(member, ast.Assign):
                        for target in member.targets:
                            if isinstance(target, ast.Name):
                                class_values[target.id] = member.value
                    elif (
                        isinstance(member, ast.AnnAssign)
                        and isinstance(member.target, ast.Name)
                        and member.value is not None
                    ):
                        class_values[member.target.id] = member.value
                for name in selected:
                    expression = class_values.get(name)
                    if expression is not None:
                        values = _hardcoded_password_values(
                            expression, bindings, _node_position(expression)
                        )
                        if any(value and value != REDACTED_PASSWORD_SENTINEL for value in values):
                            violations.append(expression.lineno)
                for member in statement.body:
                    if not isinstance(
                        member, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ) or member.name not in selected:
                        continue
                    if member.decorator_list and not all(
                        isinstance(decorator, ast.Name)
                        and decorator.id in {
                            "staticmethod", "classmethod", "property"
                        }
                        for decorator in member.decorator_list
                    ):
                        continue
                    for expression in exported_return_expressions(member.body):
                        if (
                            isinstance(expression, ast.Attribute)
                            and isinstance(expression.value, ast.Name)
                            and expression.value.id in {"self", "cls", statement.name}
                        ):
                            expression = class_values.get(expression.attr, expression)
                        values = _hardcoded_password_values(
                            expression, bindings, _node_position(member)
                        )
                        if any(value and value != REDACTED_PASSWORD_SENTINEL for value in values):
                            violations.append(member.lineno)
                            break
                continue
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Only inspect selected, undecorated source-visible provider
                # returns; normalize simple local stores and branch returns
                # before simulating the consumer's actual invocation.
                return_expressions = (
                    exported_return_expressions(statement.body)
                    if statement.name in exported_names
                    and not statement.decorator_list else []
                )
                if return_expressions:
                    arguments = statement.args
                    positional = [*arguments.posonlyargs, *arguments.args]
                    defaults_start = len(positional) - len(arguments.defaults)
                    synthetic_args = [
                        ast.copy_location(ast.Constant(value=None), statement)
                        for arg in positional[:defaults_start]
                    ]
                    synthetic_keywords = [
                        ast.keyword(
                            arg=arg.arg,
                            value=ast.copy_location(
                                ast.Constant(value=None), statement
                            ),
                        )
                        for arg, default in zip(
                            arguments.kwonlyargs, arguments.kw_defaults
                        )
                        if default is None
                    ]
                    callee = ast.copy_location(
                        ast.Name(id=statement.name, ctx=ast.Load()), statement
                    )
                    invocation = ast.copy_location(
                        ast.Call(
                            func=callee, args=synthetic_args,
                            keywords=synthetic_keywords,
                        ),
                        statement,
                    )
                    # Materialize the selected return as a small sync
                    # callable only for the source-visible credential scan.
                    # Async coroutine semantics remain unchanged elsewhere.
                    module_values = bindings["values"].get(tree, {})
                    original_binding = module_values.get(statement.name, [])
                    return_callables = [
                        ast.copy_location(
                            ast.FunctionDef(
                                name=statement.name,
                                args=statement.args,
                                body=[ast.copy_location(
                                    ast.Return(value=value), statement
                                )],
                                decorator_list=[],
                                returns=statement.returns,
                                type_comment=statement.type_comment,
                            ), statement
                        )
                        for value in return_expressions
                    ]
                    invocations = [invocation]
                    invocations.extend(
                        ast.copy_location(
                            ast.Call(
                                func=callee,
                                args=list(args),
                                keywords=list(keywords),
                            ),
                            statement,
                        )
                        for name, args, keywords in imported_calls
                        if name == statement.name
                    )
                    for return_callable in return_callables:
                        module_values[statement.name] = [
                            (position, return_callable)
                            if value is statement else (position, value)
                            for position, value in original_binding
                        ]
                        for invocation in invocations:
                            values = _hardcoded_password_values(
                                invocation, bindings, _node_position(statement)
                            )
                            if any(
                                value != REDACTED_PASSWORD_SENTINEL
                                for value in values
                            ):
                                violations.append(statement.lineno)
                                break
                        if statement.lineno in violations:
                            break
                    module_values[statement.name] = original_binding
                continue
            if isinstance(statement, ast.Assign):
                targets = statement.targets
            elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
                targets = [statement.target]
            else:
                continue
            for target in targets:
                for key, expression in assigned_leaves(target, statement.value):
                    conventional_constant = (
                        key.isupper()
                        and re.search(
                            r"(?:^|_)(?:PASSWORD|PASSWD|API_KEY|BEARER_AUTH|AUTH_TOKEN)$",
                            key,
                        )
                    )
                    if not (conventional_constant or key in exported_names):
                        continue
                    values = _hardcoded_password_values(
                        expression, bindings, _node_position(statement)
                    )
                    if any(value != REDACTED_PASSWORD_SENTINEL for value in values):
                        violations.append(statement.lineno)
        return sorted(set(violations))

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

    def test_runtime_discovery_checks_local_imported_password_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            consumer = project / "es_consumer.py"
            provider = project / "credential_provider.py"
            consumer.write_text(
                'from credential_provider import PASSWORD\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", PASSWORD))\n',
                encoding="utf-8",
            )
            provider.write_text('PASSWORD = "hardcoded-secret"\n', encoding="utf-8")

            with (
                patch.dict(globals(), {
                    "REPOSITORY_ROOT": project,
                    "ES_RUNTIME_DISCOVERY_ROOTS": (project,),
                    "RUNTIME_ES_MODULES": (),
                }),
            ):
                modules = set(self._runtime_es_module_paths())
                self.assertIn(consumer.resolve(), modules)
                self.assertIn(provider.resolve(), modules)
                self.assertEqual(
                    self._module_uppercase_credential_literals(
                        provider.read_text(encoding="utf-8")
                    ),
                    [1],
                )
                provider.write_text(
                    'import os\nPASSWORD = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    encoding="utf-8",
                )
                self.assertEqual(
                    self._module_uppercase_credential_literals(
                        provider.read_text(encoding="utf-8")
                    ),
                    [],
                )

    def test_imported_credential_export_detected_by_usage_not_case(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            consumer = project / "es_consumer.py"
            provider = project / "credential_provider.py"
            consumer.write_text(
                'from credential_provider import password as credential\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", credential))\n',
                encoding="utf-8",
            )
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": project,
                "ES_RUNTIME_DISCOVERY_ROOTS": (project,),
                "RUNTIME_ES_MODULES": (),
            }):
                paths = set(self._runtime_es_module_paths())
                self.assertIn(consumer.resolve(), paths)
                self.assertIn(provider.resolve(), paths)
                names = self._imported_credential_exports[provider.resolve()]
                self.assertEqual(names, {"password"})
                self.assertEqual(
                    self._module_uppercase_credential_literals(
                        provider.read_text(encoding="utf-8"), names
                    ),
                    [1],
                )
                provider.write_text(
                    'import os\npassword = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    encoding="utf-8",
                )
                self.assertNotIn(provider.resolve(), self._runtime_es_module_paths())
                self.assertEqual(
                    self._module_uppercase_credential_literals(
                        provider.read_text(encoding="utf-8"), names
                    ),
                    [],
                )
                # A benign import containing a literal is not an auth provider.
                provider.write_text('password = "not-used-for-auth"\n', encoding="utf-8")
                consumer.write_text(
                    'from credential_provider import password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", runtime_password))\n',
                    encoding="utf-8",
                )
                self.assertNotIn(provider.resolve(), self._runtime_es_module_paths())

    def test_imported_callable_credential_providers(self):
        """Only exported ES credential functions trigger imported provider scans."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            cases = (
                ('def get_password():\n    return "hardcoded-secret"\n', True),
                ('def get_password(unused=None):\n    return "hardcoded-secret"\n', True),
                ('def get_password(unused):\n    return "hardcoded-secret"\n', True),
                ('import os\ndef get_password():\n'
                 '    return os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('def get_password():\n    return None\n'
                 'def unrelated():\n    return "hardcoded-secret"\n', False),
                ('def unrelated():\n    return "hardcoded-secret"\n'
                 'get_password = lambda: os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                consumer.write_text(
                    'from credential_provider import get_password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", '
                    'basic_auth=("elastic", get_password()))\n',
                    encoding="utf-8",
                )
                for provider_source, expected in cases:
                    with self.subTest(provider_source=provider_source):
                        provider.write_text(provider_source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        names = self._imported_credential_exports.get(
                            provider.resolve(), set()
                        )
                        self.assertIn("get_password", names)
                        self.assertEqual(
                            provider.resolve() in paths, expected
                        )
                        self.assertEqual(
                            bool(self._module_uppercase_credential_literals(
                                provider_source, names
                            )), expected
                        )

    def test_imported_provider_volatile_condition_evaluations(self):
        """Side-effecting conditions cannot share a decision identity."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            provider.write_text(
                'def get_password(value):\n'
                '    return value["credential"]\n', encoding="utf-8",
            )
            cases = (
                ('flags = iter((True, False))\n'
                 'KEY = "credential" if next(flags) else "other"\n'
                 'VALUE = None if next(flags) else "hardcoded-secret"\n'
                 'password = get_password({KEY: VALUE})\n', True),
                ('flags = iter((True, False))\n'
                 'KEY = "other" if next(flags) else "credential"\n'
                 'VALUE = None if next(flags) else "hardcoded-secret"\n'
                 'password = get_password({KEY: VALUE})\n', True),
                ('password = get_password({("credential" if flag else "other"): '
                 '("hardcoded-secret" if not flag else None)})\n', False),
                ('password = get_password({("credential" if flag else "other"): '
                 '(None if not flag else "hardcoded-secret")})\n', True),
                ('KEY = "credential" if flag else "other"\n'
                 'VALUE = "hardcoded-secret" if not flag else None\n'
                 'password = get_password({KEY: VALUE})\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for body, expected in cases:
                    with self.subTest(body=body):
                        consumer.write_text(
                            'from credential_provider import get_password\n'
                            'from elasticsearch import Elasticsearch\n'
                            + body +
                            'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_provider_multistatement_returns(self):
        """Return-flow tracks only a selected provider's actual local values."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            cases = (
                ('def get_password():\n'
                 '    value = "hardcoded-secret"\n'
                 '    return value\n', True),
                ('def get_password():\n'
                 '    unused = "hardcoded-secret"\n'
                 '    return None\n', False),
                ('def get_password():\n'
                 '    value = "hardcoded-secret"\n'
                 '    value = None\n'
                 '    return value\n', False),
                ('def get_password(value):\n'
                 '    result = value\n'
                 '    return result\n', True),
                ('async def get_password(value):\n'
                 '    """Get authentication value."""\n'
                 '    result = value\n'
                 '    return result\n', True),
                ('def get_password():\n'
                 '    if flag:\n'
                 '        value = "hardcoded-secret"\n'
                 '    else:\n'
                 '        value = None\n'
                 '    return value\n', True),
                ('def get_password():\n'
                 '    if False:\n'
                 '        return "hardcoded-secret"\n'
                 '    return None\n', False),
                ('def get_password():\n'
                 '    if flag:\n'
                 '        return None\n'
                 '    return "hardcoded-secret"\n', True),
                ('import os\ndef get_password():\n'
                 '    value = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                 '    return value\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for provider_source, expected in cases:
                    with self.subTest(provider=provider_source):
                        args = (
                            '"hardcoded-secret"' if "get_password(value)" in
                            provider_source else ""
                        )
                        consumer.write_text(
                            'from credential_provider import get_password\n'
                            'from elasticsearch import Elasticsearch\n'
                            'password = get_password(' + args + ')\n'
                            'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        provider.write_text(
                            provider_source, encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_es_wrapper_conditionally_shadowed_import(self):
        """The original wrapper survives an overwrite on one branch."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "client.py"
            caller = root / "worker.py"
            wrapper.write_text(
                'from elasticsearch import Elasticsearch\n'
                'def connect(password):\n'
                '    return Elasticsearch("localhost", '
                'basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            cases = (
                ('from client import connect\n'
                 'if flag:\n    connect = lambda password: None\n'
                 'connect("hardcoded-secret")\n', True),
                ('import client as cp\n'
                 'if flag:\n    cp = None\n'
                 'cp.connect("hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'if flag:\n    connect = lambda password: None\n'
                 'else:\n    connect = lambda password: None\n'
                 'connect("hardcoded-secret")\n', False),
                ('from client import connect\n'
                 'connect = lambda password: None\n'
                 'connect("hardcoded-secret")\n', False),
                ('from client import connect\n'
                 'if True:\n    connect = lambda password: None\n'
                 'connect("hardcoded-secret")\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for body, expected in cases:
                    with self.subTest(body=body):
                        caller.write_text(body, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        flagged = bool(
                            self._es_wrapper_credential_lines.get(caller, ())
                        )
                        self.assertEqual(flagged, expected)
                        self.assertEqual(caller.resolve() in paths, expected)

    def test_es_wrapper_keyword_only_password_parameter(self):
        """A keyword-only wrapper sink cannot be dropped from discovery."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "client.py"
            caller = root / "worker.py"
            wrapper.write_text(
                'from elasticsearch import Elasticsearch\n'
                'def connect(*, password):\n'
                '    return Elasticsearch("localhost", '
                'basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            cases = (
                ('from client import connect\n'
                 'connect(password="hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'connect(password=os.getenv("TCP_ELASTIC_PASSWORD"))\n', False),
                ('from client import connect\n'
                 'connect(password=None)\n', False),
                ('from client import connect\n'
                 'connect("hardcoded-secret")\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for body, expected in cases:
                    with self.subTest(body=body):
                        caller.write_text(body, encoding="utf-8")
                        self._runtime_es_module_paths()
                        self.assertEqual(
                            bool(self._es_wrapper_credential_lines.get(caller, ())),
                            expected,
                        )

    def test_selected_class_module_import_alias(self):
        """A copied module alias still identifies the imported config class."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            provider.write_text(
                'class Config:\n'
                '    password = "hardcoded-secret"\n'
                '    unrelated = None\n', encoding="utf-8",
            )
            cases = (
                ('import credential_provider as cp\n'
                 'alias = cp\n'
                 'cfg = alias.Config("prod")\n'
                 'password = cfg.password\n', True),
                ('import credential_provider as cp\n'
                 'alias = cp\n'
                 'cfg = alias.Config("prod")\n'
                 'password = cfg.unrelated\n', False),
                ('import credential_provider as cp\n'
                 'alias = cp\n'
                 'alias = object()\n'
                 'password = alias.Config.password\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            source + 'from elasticsearch import Elasticsearch\n'
                            'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_es_wrapper_reverse_importer_credentials(self):
        """ES wrapper callers are security surfaces only for live wrapper calls."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "client.py"
            caller = root / "worker.py"
            safe = root / "irrelevant.py"
            wrapper.write_text(
                'from elasticsearch import Elasticsearch\n'
                'def connect(password):\n'
                '    return Elasticsearch("localhost", '
                'basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            safe.write_text(
                'from client import connect\n'
                'unrelated = "hardcoded-secret"\n',
                encoding="utf-8",
            )
            cases = (
                ('from client import connect\n'
                 'connect("hardcoded-secret")\n', True),
                ('from client import connect as open_client\n'
                 'open_client("hardcoded-secret")\n', True),
                ('import client as cp\n'
                 'cp.connect("hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'token = "hardcoded-secret"\n'
                 'connect(token)\n', True),
                ('from client import connect\n'
                 'connect(password="hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'connect(os.getenv("TCP_ELASTIC_PASSWORD"))\n', False),
                ('from client import connect\n'
                 'connect(None)\n', False),
                ('from client import connect\n'
                 'unrelated("hardcoded-secret")\n', False),
                ('from client import connect\n'
                 'open_es = connect\n'
                 'open_es("hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'open_es = connect\n'
                 'delegate = open_es\n'
                 'delegate("hardcoded-secret")\n', True),
                ('import client as cp\n'
                 'open_es = cp\n'
                 'open_es.connect("hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'open_es = connect\n'
                 'open_es = lambda password: None\n'
                 'open_es("hardcoded-secret")\n', False),
                ('import client as cp\n'
                 'open_es = cp\n'
                 'open_es = object()\n'
                 'open_es.connect("hardcoded-secret")\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for caller_source, expected in cases:
                    with self.subTest(source=caller_source):
                        caller.write_text(caller_source, encoding="utf-8")
                        modules = set(self._runtime_es_module_paths())
                        flagged = bool(
                            self._es_wrapper_credential_lines.get(caller, ())
                        )
                        self.assertEqual(flagged, expected)
                        self.assertEqual(
                            caller.resolve() in modules,
                            (
                                "unrelated(" not in caller_source
                                and "open_es = lambda" not in caller_source
                                and "open_es = object()" not in caller_source
                            ),
                        )
                        self.assertNotIn(safe.resolve(), modules)
                        self.assertIn(wrapper.resolve(), modules)

    def test_selected_imported_class_credentials(self):
        """Only members actually used by auth can expose a class credential."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            cases = (
                ('from credential_provider import Config\n'
                 'Config.password',
                 'class Config:\n'
                 '    password = "hardcoded-secret"\n', True),
                ('from credential_provider import Config as C\n'
                 'C.get_password()',
                 'class Config:\n'
                 '    @staticmethod\n'
                 '    def get_password():\n'
                 '        return "hardcoded-secret"\n', True),
                ('from credential_provider import Config\n'
                 'Config().get_password()',
                 'class Config:\n'
                 '    def get_password(self):\n'
                 '        return "hardcoded-secret"\n', True),
                ('import credential_provider as cp\n'
                 'cp.Config.password',
                 'class Config:\n'
                 '    password = "hardcoded-secret"\n', True),
                ('from credential_provider import Config\n'
                 'Config().get_password()',
                 'class Config:\n'
                 '    password = "hardcoded-secret"\n'
                 '    def get_password(self):\n'
                 '        return self.password\n', True),
                ('from credential_provider import Config\n'
                 'Config().get_password()',
                 'import os\nclass Config:\n'
                 '    def get_password(self):\n'
                 '        return os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('from credential_provider import Config\n'
                 'Config.password',
                 'class Config:\n'
                 '    unrelated = "hardcoded-secret"\n'
                 '    password = None\n', False),
                ('from credential_provider import Config\n'
                 'Config.get_password()',
                 'class Config:\n'
                 '    @classmethod\n'
                 '    def get_password(cls):\n'
                 '        value = "hardcoded-secret"\n'
                 '        return value\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for combined, source, expected in cases:
                    prefix, credential = combined.rsplit('\n', 1)
                    with self.subTest(credential=credential, expected=expected):
                        consumer.write_text(
                            prefix + '\n'
                            + 'from elasticsearch import Elasticsearch\n'
                            + 'Elasticsearch("localhost", '
                            'basic_auth=("elastic", ' + credential + '))\n',
                            encoding="utf-8",
                        )
                        provider.write_text(source, encoding="utf-8")
                        modules = set(self._runtime_es_module_paths())
                        self.assertEqual(
                            provider.resolve() in modules, expected
                        )
                        members = self._imported_credential_class_members.get(
                            provider.resolve(), {}
                        )
                        self.assertIn(credential.split(".")[-1].split("(")[0], members.get("Config", ()))

    def test_es_wrapper_marked_caller_credential_lines(self):
        """Marker-matched callers still need wrapper-argument inspection."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "elasticsearch_client.py"
            caller = root / "connect_user.py"
            wrapper.write_text(
                'from elasticsearch import Elasticsearch\n'
                'def connect(password):\n'
                '    return Elasticsearch("localhost", '
                'basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            cases = (
                ('from elasticsearch_client import connect\n'
                 'connect("hardcoded-secret")\n', [2]),
                ('import elasticsearch_client as ec\n'
                 'ec.connect("hardcoded-secret")\n', [2]),
                ('from elasticsearch_client import connect\n'
                 'value = "hardcoded-secret"\n'
                 'connect(value)\n', [3]),
                ('from elasticsearch_client import connect\n'
                 'connect(password_from_store)\n', []),
                ('from elasticsearch_client import connect\n'
                 'unrelated("hardcoded-secret")\n', []),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, lines in cases:
                    with self.subTest(source=source):
                        caller.write_text(source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        self.assertIn(wrapper.resolve(), paths)
                        # The import name itself includes "elasticsearch",
                        # so this caller is already a discovered ES surface.
                        self.assertIn(caller.resolve(), paths)
                        self.assertEqual(
                            sorted(self._es_wrapper_credential_lines.get(
                                caller.resolve(), ()
                            )), lines,
                        )

    def test_selected_class_instance_alias_credentials(self):
        """Resolve only the selected auth member through constructor aliases."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            cases = (
                ('from credential_provider import Config\n'
                 'cfg = Config()\n'
                 'password = cfg.password\n',
                 'class Config:\n'
                 '    password = "hardcoded-secret"\n', True, "password"),
                ('from credential_provider import Config\n'
                 'cfg = Config()\n'
                 'alias = cfg\n'
                 'password = alias.get_password()\n',
                 'class Config:\n'
                 '    def get_password(self):\n'
                 '        return "hardcoded-secret"\n', True, "get_password"),
                ('from credential_provider import Config as C\n'
                 'cfg = C()\n'
                 'password = cfg.get_password()\n',
                 'class Config:\n'
                 '    def get_password(self):\n'
                 '        return "hardcoded-secret"\n', True, "get_password"),
                ('from credential_provider import Config\n'
                 'cfg = Config()\n'
                 'password = cfg.password\n',
                 'class Config:\n'
                 '    unrelated = "hardcoded-secret"\n'
                 '    password = None\n', False, "password"),
                ('from credential_provider import Config\n'
                 'cfg = Config()\n'
                 'cfg = object()\n'
                 'password = cfg.password\n',
                 'class Config:\n'
                 '    password = "hardcoded-secret"\n', False, None),
                ('from credential_provider import Config\n'
                 'cfg = Config("prod")\n'
                 'password = cfg.password\n',
                 'class Config:\n'
                 '    password = "hardcoded-secret"\n', True, "password"),
                ('from credential_provider import Config\n'
                 'cfg = Config("prod", region="us")\n'
                 'password = cfg.get_password()\n',
                 'class Config:\n'
                 '    def get_password(self):\n'
                 '        return "hardcoded-secret"\n', True, "get_password"),
                ('from credential_provider import Config\n'
                 'cfg = Config("prod")\n'
                 'password = cfg.password\n',
                 'class Config:\n'
                 '    password = None\n'
                 '    unrelated = "hardcoded-secret"\n', False, "password"),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for caller_source, provider_source, expected, member in cases:
                    with self.subTest(source=caller_source):
                        consumer.write_text(
                            caller_source
                            + 'from elasticsearch import Elasticsearch\n'
                            + 'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        provider.write_text(provider_source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        self.assertEqual(
                            provider.resolve() in paths, expected
                        )
                        selected = self._imported_credential_class_members.get(
                            provider.resolve(), {}
                        ).get("Config", ())
                        if member is not None:
                            self.assertIn(member, selected)
                        else:
                            self.assertNotIn("password", selected)

    def test_selected_class_property_credentials(self):
        """Inspect a selected property getter without unrelated members."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            consumer.write_text(
                'from credential_provider import Config\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", '
                'basic_auth=("elastic", Config().password))\n',
                encoding="utf-8",
            )
            cases = (
                ('class Config:\n'
                 '    @property\n'
                 '    def password(self):\n'
                 '        return "hardcoded-secret"\n', True),
                ('class Config:\n'
                 '    @property\n'
                 '    def password(self):\n'
                 '        value = "hardcoded-secret"\n'
                 '        return value\n', True),
                ('import os\nclass Config:\n'
                 '    @property\n'
                 '    def password(self):\n'
                 '        return os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('class Config:\n'
                 '    @property\n'
                 '    def unrelated(self):\n'
                 '        return "hardcoded-secret"\n'
                 '    @property\n'
                 '    def password(self):\n'
                 '        return None\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for provider_source, expected in cases:
                    with self.subTest(provider=provider_source):
                        provider.write_text(provider_source, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_class_import_survives_conditional_module_shadow(self):
        """Conditional module overwrite preserves the original ES class path."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "consumer.py"
            provider = root / "credential_provider.py"
            provider.write_text(
                'class Config:\n'
                '    password = "hardcoded-secret"\n',
                encoding="utf-8",
            )
            cases = (
                ('import credential_provider as cp\n'
                 'if flag:\n    cp = object()\n'
                 'password = cp.Config.password\n', True),
                ('import credential_provider as cp\n'
                 'cp = object()\n'
                 'password = cp.Config.password\n', False),
                ('import credential_provider as cp\n'
                 'alias = cp\n'
                 'if flag:\n    alias = object()\n'
                 'password = alias.Config.password\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            + source
                            + 'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_es_wrapper_identity_preserving_import_assignment(self):
        """Reassigning an imported wrapper to itself does not erase it."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "client.py"
            caller = root / "caller.py"
            wrapper.write_text(
                'from elasticsearch import Elasticsearch\n'
                'def connect(password):\n'
                '    return Elasticsearch("localhost", '
                'basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            cases = (
                ('from client import connect\n'
                 'connect = connect\n'
                 'connect("hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'if flag:\n    connect = connect\n'
                 'connect("hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'connect = lambda password: None\n'
                 'connect("hardcoded-secret")\n', False),
                ('from client import connect\n'
                 'saved = connect\n'
                 'connect = lambda password: None\n'
                 'connect = saved\n'
                 'connect("hardcoded-secret")\n', True),
                ('from client import connect\n'
                 'saved = connect\n'
                 'saved = lambda password: None\n'
                 'connect = saved\n'
                 'connect("hardcoded-secret")\n', False),
                ('import client as c\n'
                 'c = c\n'
                 'c.connect("hardcoded-secret")\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        caller.write_text(source, encoding="utf-8")
                        self._runtime_es_module_paths()
                        self.assertEqual(
                            bool(getattr(
                                self, "_es_wrapper_credential_lines", {}
                            ).get(caller.resolve())),
                            expected,
                        )

    def test_imported_provider_nonidentifier_keyword_keys(self):
        """Known **kwargs can use any string key, including hyphens."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            cases = (
                ('password = get_password(**{"credential-key": "hardcoded-secret"})\n',
                 'def get_password(**kwargs):\n'
                 '    return kwargs["credential-key"]\n', True),
                ('args = {"credential-key": "hardcoded-secret"}\n'
                 'password = get_password(**args)\n',
                 'def get_password(**kwargs):\n'
                 '    return kwargs["credential-key"]\n', True),
                ('password = get_password(**{"credential-key": None, '
                 '"other-key": "hardcoded-secret"})\n',
                 'def get_password(**kwargs):\n'
                 '    return kwargs["credential-key"]\n', False),
                ('password = get_password(**{"credential-key": "hardcoded-secret"})\n',
                 'def get_password(**kwargs):\n'
                 '    return kwargs.get("other-key")\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for call_source, provider_source, expected in cases:
                    with self.subTest(source=call_source):
                        consumer.write_text(
                            'from credential_provider import get_password\n'
                            'from elasticsearch import Elasticsearch\n'
                            + call_source
                            + 'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        provider.write_text(provider_source, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_provider_documented_returns(self):
        """An optional leading docstring must not hide exported returns."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            consumer.write_text(
                'from credential_provider import get_password\n'
                'from elasticsearch import Elasticsearch\n'
                'async def connect():\n'
                '    password = await get_password("hardcoded-secret")\n'
                '    return Elasticsearch("localhost", '
                'basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            cases = (
                ('def get_password(value):\n'
                 '    """Return the password."""\n'
                 '    return "hardcoded-secret"\n', True),
                ('async def get_password(value):\n'
                 '    """Return the password."""\n'
                 '    return value\n', True),
                ('async def get_password(value):\n'
                 '    """Return the password."""\n'
                 '    return "hardcoded-secret"\n', True),
                ('import os\ndef get_password(value):\n'
                 '    """Return password safely."""\n'
                 '    return os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('def get_password(value):\n'
                 '    """Return password safely."""\n'
                 '    return None\n', False),
                ('def unrelated(value):\n'
                 '    """Unused secret provider."""\n'
                 '    return "hardcoded-secret"\n'
                 'def get_password(value):\n'
                 '    """Return nothing."""\n'
                 '    return None\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for provider_source, expected in cases:
                    with self.subTest(source=provider_source):
                        provider.write_text(provider_source, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_provider_correlated_dictionary_branches(self):
        """A shared condition cannot pair key/value from opposite arms."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            provider.write_text(
                'def get_password(value):\n'
                '    return value["credential"]\n',
                encoding="utf-8",
            )
            cases = (
                ('get_password({("credential" if flag else "other"): '
                 '(None if flag else "hardcoded-secret")})', False),
                ('get_password({("credential" if flag else "other"): '
                 '("hardcoded-secret" if flag else None)})', True),
                ('get_password({("other" if flag else "credential"): '
                 '(None if flag else "hardcoded-secret")})', True),
                ('KEY = "credential" if flag else "other"\n'
                 'VALUE = None if flag else "hardcoded-secret"\n'
                 'get_password({KEY: VALUE})', False),
                ('KEY = "credential" if flag else "other"\n'
                 'VALUE = "hardcoded-secret" if flag else None\n'
                 'get_password({KEY: VALUE})', True),
                ('get_password({"credential": None if flag else '
                 '"hardcoded-secret", "other": "unused" if flag else None})', True),
                # A write between evaluations gives the same condition text
                # a new epoch. The old and new branch choices must not merge.
                ('KEY = "credential" if flag else "other"\n'
                 'flag = not flag\n'
                 'VALUE = None if flag else "hardcoded-secret"\n'
                 'get_password({KEY: VALUE})', True),
                ('KEY = "credential" if flag else "other"\n'
                 'flag = not flag\n'
                 'VALUE = "hardcoded-secret" if flag else None\n'
                 'get_password({KEY: VALUE})', False),
                # An inner branch remains correlated with a separate use of
                # the same condition outside the nested expression.
                ('get_password({("other" if outer else '
                 '("credential" if inner else "other")): '
                 '(None if inner else "hardcoded-secret")})', False),
                ('get_password({("other" if outer else '
                 '("credential" if inner else "other")): '
                 '("hardcoded-secret" if inner else None)})', True),
                ('KEY = "other" if outer else '
                 '("credential" if inner else "other")\n'
                 'VALUE = None if inner else "hardcoded-secret"\n'
                 'get_password({KEY: VALUE})', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for expression, expected in cases:
                    with self.subTest(source=expression):
                        if '\n' in expression:
                            prelude, call = expression.rsplit('\n', 1)
                            expression_source = prelude + '\npassword = ' + call
                        else:
                            expression_source = 'password = ' + expression
                        consumer.write_text(
                            'from credential_provider import get_password\n'
                            'from elasticsearch import Elasticsearch\n'
                            + expression_source + '\n'
                            + 'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_provider_statically_known_spread_arguments(self):
        """Expand known *args/**kwargs, not opaque runtime unpacking."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            cases = (
                ('args = ("hardcoded-secret",)\n'
                 'password = get_password(*args)\n',
                 'def get_password(value):\n    return value\n', True),
                ('args = [None, "hardcoded-secret"]\n'
                 'password = get_password(*args)\n',
                 'def get_password(unused, value):\n    return value\n', True),
                ('args = (None, "hardcoded-secret")\n'
                 'password = get_password(*args)\n',
                 'def get_password(value, unused):\n    return value\n', False),
                ('args = (None, "hardcoded-secret")\n'
                 'password = get_password(*args)\n',
                 'def get_password(unused, value):\n    return value\n', True),
                ('options = {"value": "hardcoded-secret"}\n'
                 'password = get_password(**options)\n',
                 'def get_password(value):\n    return value\n', True),
                ('options = {"unused": "hardcoded-secret", "value": None}\n'
                 'password = get_password(**options)\n',
                 'def get_password(value, unused):\n    return value\n', False),
                ('password = get_password(*(None, "hardcoded-secret"))\n',
                 'def get_password(unused, value):\n    return value\n', True),
                ('password = get_password(**{"value": "hardcoded-secret"})\n',
                 'def get_password(value):\n    return value\n', True),
                ('password = get_password(*unknown)\n',
                 'def get_password(value):\n    return value\n', False),
                ('password = get_password(**unknown)\n',
                 'def get_password(value):\n    return value\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for call_source, provider_source, expected in cases:
                    with self.subTest(call_source=call_source):
                        provider.write_text(provider_source, encoding="utf-8")
                        consumer.write_text(
                            'from credential_provider import get_password\n'
                            'from elasticsearch import Elasticsearch\n'
                            + call_source +
                            'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_provider_nested_dictionary_unpacking(self):
        """Preserve known **mapping spreads and their override order."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            provider.write_text(
                'def get_password(value):\n'
                '    return value["credential"]\n', encoding="utf-8"
            )
            cases = (
                ('get_password({**{"credential": "hardcoded-secret"}})', True),
                ('get_password({**{"credential": "hardcoded-secret"}, '
                 '"credential": None})', False),
                ('get_password({"credential": None, '
                 '**{"credential": "hardcoded-secret"}})', True),
                ('get_password({**{"other": "hardcoded-secret"}, '
                 '"credential": None})', False),
                ('get_password({**{"credential": None}, '
                 '"other": "hardcoded-secret"})', False),
                ('get_password({**({"credential": "hardcoded-secret"}'
                 ' if flag else {"credential": None})})', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for expression, expected in cases:
                    with self.subTest(expression=expression):
                        consumer.write_text(
                            'from credential_provider import get_password\n'
                            'from elasticsearch import Elasticsearch\n'
                            'password = ' + expression + '\n'
                            'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_async_credential_provider_return(self):
        """Awaited imported async provider returns can contain literals."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            consumer.write_text(
                'from credential_provider import get_password\n'
                'from elasticsearch import Elasticsearch\n'
                'async def connect():\n'
                '    password = await get_password("hardcoded-secret")\n'
                '    return Elasticsearch("localhost", '
                'basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            cases = (
                ('async def get_password(value):\n    return value\n', True),
                ('async def get_password(value):\n'
                 '    return "hardcoded-secret"\n', True),
                ('import os\nasync def get_password(value):\n'
                 '    return os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('async def unrelated(value):\n'
                 '    return "hardcoded-secret"\n'
                 'async def get_password(value):\n    return None\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(provider=source):
                        provider.write_text(source, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_provider_conditional_import_survival(self):
        """A conditional alias replacement cannot erase the untouched import."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            provider.write_text(
                'def get_password(value):\n    return value\n', encoding="utf-8"
            )
            cases = (
                ('from credential_provider import get_password\n'
                 'if flag:\n    get_password = lambda value: None\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'get_password("hardcoded-secret")))\n', True),
                ('import credential_provider as cp\n'
                 'if flag:\n    cp = object()\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'cp.get_password("hardcoded-secret")))\n', True),
                ('import credential_provider as cp\n'
                 'provider = cp\n'
                 'if flag:\n    provider = object()\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'provider.get_password("hardcoded-secret")))\n', True),
                ('from credential_provider import get_password\n'
                 'if flag:\n    get_password = lambda value: None\n'
                 'else:\n    get_password = lambda value: None\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'get_password("hardcoded-secret")))\n', False),
                ('from credential_provider import get_password\n'
                 'if True:\n    get_password = lambda value: None\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'get_password("hardcoded-secret")))\n', False),
                ('from credential_provider import get_password\n'
                 'if flag:\n    get_password = lambda value: None\n'
                 'get_password = lambda value: None\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'get_password("hardcoded-secret")))\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for consumer_source, expected in cases:
                    with self.subTest(source=consumer_source):
                        consumer.write_text(
                            consumer_source, encoding="utf-8"
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_provider_consumer_dictionary_keys(self):
        """Indexing exported-provider dict arguments uses resolved key slots."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            provider.write_text(
                'def get_password(value):\n'
                '    return value["credential"]\n',
                encoding="utf-8",
            )
            cases = (
                ('KEY = "credential"\n'
                 'get_password({KEY: "hardcoded-secret"})\n', True),
                ('KEY = "credential"\n'
                 'get_password({KEY: None, "other": "hardcoded-secret"})\n', False),
                ('KEY = "other"\n'
                 'get_password({KEY: "hardcoded-secret", "credential": None})\n', False),
                ('KEY = "other" if flag else "credential"\n'
                 'get_password({KEY: "hardcoded-secret"})\n', True),
                ('KEY = "credential"\n'
                 'secret = {KEY: "hardcoded-secret"}\n'
                 'get_password(secret)\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for text, expected in cases:
                    with self.subTest(source=text):
                        consumer.write_text(
                            'from credential_provider import get_password\n'
                            'from elasticsearch import Elasticsearch\n'
                            + text.replace(
                                'get_password(', 'password = get_password('
                            )
                            + 'Elasticsearch("localhost", '
                            'basic_auth=("elastic", password))\n',
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_provider_alias_and_argument_alternatives(self):
        """Aliases and every concrete argument branch reach an imported provider."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            provider_source = (
                'def get_password(value):\n    return value\n'
            )
            cases = (
                ('from credential_provider import get_password\n'
                 'fetch = get_password\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'fetch("hardcoded-secret")))\n', True),
                ('import credential_provider as cp\n'
                 'provider = cp\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'provider.get_password("hardcoded-secret")))\n', True),
                ('from credential_provider import get_password\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'get_password("***REDACTED***" if flag else "hardcoded-secret")))\n', True),
                ('from credential_provider import get_password\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'get_password("hardcoded-secret" if flag else "***REDACTED***")))\n', True),
                ('from credential_provider import get_password\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'get_password(None if flag else "hardcoded-secret")))\n', True),
                ('from credential_provider import get_password\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'get_password("***REDACTED***" if flag else None)))\n', False),
                ('from credential_provider import get_password\n'
                 'fetch = get_password\n'
                 'fetch = lambda value: None\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'fetch("hardcoded-secret")))\n', False),
                ('import credential_provider as cp\n'
                 'provider = cp\nprovider = object()\n'
                 'from elasticsearch import Elasticsearch\n'
                 'Elasticsearch("localhost", basic_auth=("elastic", '
                 'provider.get_password("hardcoded-secret")))\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                provider.write_text(provider_source, encoding="utf-8")
                for text, expected in cases:
                    with self.subTest(source=text):
                        consumer.write_text(text, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )
                provider.write_text(
                    'def get_password(value):\n    return value[0]\n',
                    encoding="utf-8",
                )
                consumer.write_text(
                    'from credential_provider import get_password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", '
                    'get_password([None, "hardcoded-secret"])))\n',
                    encoding="utf-8",
                )
                self.assertNotIn(provider.resolve(), self._runtime_es_module_paths())
                consumer.write_text(
                    'from credential_provider import get_password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", '
                    'get_password(["hardcoded-secret", None])))\n',
                    encoding="utf-8",
                )
                self.assertIn(provider.resolve(), self._runtime_es_module_paths())

    def test_imported_provider_uses_consumer_call_arguments(self):
        """Cross-module returns observe actual consumer arguments, not None."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "credential_provider.py"
            cases = (
                (
                    'from credential_provider import get_password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", '
                    'get_password("hardcoded-secret")))\n',
                    'def get_password(value):\n    return value\n', True,
                ),
                (
                    'from credential_provider import get_password as fetch\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", '
                    'fetch(value="hardcoded-secret")))\n',
                    'def get_password(value):\n    return value\n', True,
                ),
                (
                    'import credential_provider as cp\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", '
                    'cp.get_password("hardcoded-secret")))\n',
                    'def get_password(value):\n    return value\n', True,
                ),
                (
                    'from credential_provider import get_password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'credential = get_password("hardcoded-secret")\n'
                    'Elasticsearch("localhost", '
                    'basic_auth=("elastic", credential))\n',
                    'def get_password(value):\n    return value\n', True,
                ),
                (
                    'from credential_provider import get_password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", '
                    'get_password("hardcoded-secret")))\n',
                    'def get_password(value):\n    return None\n', False,
                ),
                (
                    'from credential_provider import get_password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'get_password("hardcoded-secret")\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", '
                    'get_password(None)))\n',
                    'def get_password(value):\n    return value\n', False,
                ),
                (
                    'from credential_provider import get_password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", '
                    'get_password("hardcoded-secret")))\n',
                    'import os\ndef get_password(value):\n'
                    '    return os.getenv("TCP_ELASTIC_PASSWORD")\n', False,
                ),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for consumer_source, provider_source, expected in cases:
                    with self.subTest(consumer_source=consumer_source):
                        consumer.write_text(consumer_source, encoding="utf-8")
                        provider.write_text(provider_source, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_imported_auth_providers_follow_aliases_dotted_paths_and_unpacking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            providers = root / "providers"
            providers.mkdir()
            (providers / "__init__.py").write_text("", encoding="utf-8")
            provider = providers / "credential_provider.py"
            consumer = root / "es_consumer.py"
            scenarios = (
                (
                    'from providers.credential_provider import password as imported\n'
                    'credential = imported\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", credential))\n',
                    'password = "hardcoded-secret"\n',
                    True,
                ),
                (
                    'import providers.credential_provider\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", providers.credential_provider.password))\n',
                    'password = "hardcoded-secret"\n',
                    True,
                ),
                (
                    'from providers.credential_provider import password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                    'password, unused = "hardcoded-secret", None\n',
                    True,
                ),
                (
                    'from providers.credential_provider import username\n'
                    'import os\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=(username, os.environ["TCP_ELASTIC_PASSWORD"]))\n',
                    'username = "elastic"\n',
                    False,
                ),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for client_source, provider_source, should_flag in scenarios:
                    with self.subTest(source=client_source):
                        consumer.write_text(client_source, encoding="utf-8")
                        provider.write_text(provider_source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        selected = self._imported_credential_exports.get(
                            provider.resolve(), set()
                        )
                        detected = self._module_uppercase_credential_literals(
                            provider_source, selected
                        )
                        self.assertEqual(provider.resolve() in paths, should_flag)
                        self.assertEqual(bool(detected), should_flag)

    def test_local_module_alias_attributes_and_transitive_reexports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "providers"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            provider = package / "credential_provider.py"
            consumer = root / "es_consumer.py"
            a = root / "provider_a.py"
            b = root / "provider_b.py"

            cases = (
                (
                    'from providers import credential_provider as cp\n'
                    'alias = cp\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", alias.password))\n',
                    'password = "hardcoded-secret"\n',
                ),
                (
                    'from providers import credential_provider as cp\n'
                    'intermediate = cp\n'
                    'alias = intermediate\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", alias.password))\n',
                    'password = "hardcoded-secret"\n',
                ),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for client_source, provider_source in cases:
                    with self.subTest(source=client_source):
                        consumer.write_text(client_source, encoding="utf-8")
                        provider.write_text(provider_source, encoding="utf-8")
                        included = set(self._runtime_es_module_paths())
                        self.assertIn(provider.resolve(), included)
                        self.assertIn(
                            "password",
                            self._imported_credential_exports[provider.resolve()],
                        )

                consumer.write_text(
                    'from provider_a import password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                    encoding="utf-8",
                )
                provider.write_text("unrelated = 1\n", encoding="utf-8")
                b.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
                for reexport in (
                    'from provider_b import password\n',
                    'from provider_b import password as secret\npassword = secret\n',
                ):
                    with self.subTest(reexport=reexport):
                        a.write_text(reexport, encoding="utf-8")
                        included = set(self._runtime_es_module_paths())
                        self.assertIn(b.resolve(), included)
                        self.assertIn(
                            "password", self._imported_credential_exports[b.resolve()]
                        )
                b.write_text(
                    'import os\npassword = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    encoding="utf-8",
                )
                self.assertNotIn(b.resolve(), self._runtime_es_module_paths())

    def test_transitive_destructuring_and_shadowed_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            intermediary = root / "provider_a.py"
            provider = root / "provider_b.py"
            consumer.write_text(
                'from provider_a import password\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            scenarios = (
                (
                    'from provider_b import password as secret\n'
                    'password, unused = secret, None\n',
                    True,
                ),
                (
                    'from provider_b import password\n'
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'from provider_b import password as secret\n'
                    'import os\n'
                    'password, unused = os.getenv("TCP_ELASTIC_PASSWORD"), secret\n',
                    False,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'from provider_b import password\n',
                    True,
                ),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for intermediary_source, expected in scenarios:
                    with self.subTest(source=intermediary_source):
                        intermediary.write_text(
                            intermediary_source, encoding="utf-8"
                        )
                        modules = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in modules, expected)
                        exports = self._imported_credential_exports.get(
                            provider.resolve(), set()
                        )
                        self.assertEqual("password" in exports, expected)

    def test_nested_module_reexports_preserve_reaching_import_paths(self):
        """Keep conditional imports, but discard imports definitely overwritten."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            intermediary = root / "provider_a.py"
            provider = root / "provider_b.py"
            alternate = root / "provider_c.py"
            consumer.write_text(
                'from provider_a import password\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            alternate.write_text(
                'import os\n'
                'password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                encoding="utf-8",
            )
            cases = (
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'if enabled:\n'
                    '    from provider_b import password\n',
                    True,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'if enabled:\n'
                    '    if second_condition:\n'
                    '        from provider_b import password\n',
                    True,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'if enabled:\n'
                    '    from provider_b import password\n'
                    'else:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    True,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'try:\n'
                    '    optional_operation()\n'
                    'except Exception:\n'
                    '    from provider_b import password\n',
                    True,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'if enabled:\n'
                    '    from provider_b import password\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'if enabled:\n'
                    '    from provider_b import password\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'if enabled:\n'
                    '    from provider_b import password\n'
                    'else:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'from provider_b import password\n'
                    'from provider_c import password\n',
                    False,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'try:\n'
                    '    from provider_b import password\n'
                    'finally:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'if enabled:\n'
                    '    from provider_b import password as imported\n'
                    '    password, unused = imported, None\n',
                    True,
                ),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, should_include in cases:
                    with self.subTest(source=source):
                        intermediary.write_text(source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in paths, should_include)
                        self.assertEqual(
                            "password" in self._imported_credential_exports.get(
                                provider.resolve(), set()
                            ),
                            should_include,
                        )

    def test_try_intermediate_imports_and_loop_break_exports(self):
        """Exception and break paths must not lose a reachable secret import."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            intermediary = root / "provider_a.py"
            provider = root / "provider_b.py"
            consumer.write_text(
                'from provider_a import password\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            cases = (
                (
                    'import os\n'
                    'try:\n'
                    '    from provider_b import password\n'
                    '    optional_operation()\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'except Exception:\n'
                    '    pass\n',
                    True,
                ),
                (
                    'import os\n'
                    'try:\n'
                    '    if enabled:\n'
                    '        from provider_b import password\n'
                    '        optional_operation()\n'
                    '        password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'except Exception:\n'
                    '    pass\n',
                    True,
                ),
                (
                    'import os\n'
                    'try:\n'
                    '    from provider_b import password\n'
                    '    optional_operation()\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'except Exception:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'try:\n'
                    '    from provider_b import password\n'
                    '    optional_operation()\n'
                    'except Exception:\n'
                    '    pass\n'
                    'finally:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'for _ in [1]:\n'
                    '    from provider_b import password\n'
                    '    break\n'
                    'else:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    True,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'for _ in [1]:\n'
                    '    if enabled:\n'
                    '        from provider_b import password\n'
                    '        break\n'
                    'else:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    True,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'for _ in [1]:\n'
                    '    from provider_b import password\n'
                    '    continue\n'
                    'else:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'for _ in [1]:\n'
                    '    from provider_b import password\n'
                    '    break\n'
                    'else:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'try:\n'
                    '    for _ in [1]:\n'
                    '        from provider_b import password\n'
                    '        break\n'
                    'finally:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'try:\n'
                    '    for _ in [1]:\n'
                    '        from provider_b import password\n'
                    '        break\n'
                    'except Exception:\n'
                    '    pass\n',
                    True,
                ),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, should_include in cases:
                    with self.subTest(source=source):
                        intermediary.write_text(source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in paths, should_include)
                        self.assertEqual(
                            "password" in self._imported_credential_exports.get(
                                provider.resolve(), set()
                            ),
                            should_include,
                        )

    def test_loop_with_and_named_expression_reexports(self):
        """Check selected exports rebound by Python's other assignment forms."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            intermediary = root / "provider_a.py"
            provider = root / "provider_b.py"
            consumer.write_text(
                'from provider_a import password\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            cases = (
                (
                    'from provider_b import password as imported\n'
                    'for password in [imported]:\n'
                    '    pass\n',
                    True,
                ),
                (
                    'from provider_b import password as imported\n'
                    'for password, unused in [(imported, None)]:\n'
                    '    pass\n',
                    True,
                ),
                (
                    'from provider_b import password as imported\n'
                    'for password in [imported]:\n'
                    '    break\n'
                    'else:\n'
                    '    password = None\n',
                    True,
                ),
                (
                    'import os\n'
                    'from provider_b import password as imported\n'
                    'for password in [imported]:\n'
                    '    pass\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'from provider_b import password as imported\n'
                    'for password in [imported]:\n'
                    '    pass\n'
                    'else:\n'
                    '    password = None\n',
                    False,
                ),
                (
                    'from contextlib import nullcontext\n'
                    'import provider_b\n'
                    'with nullcontext(provider_b.password) as password:\n'
                    '    pass\n',
                    True,
                ),
                (
                    'from contextlib import nullcontext\n'
                    'from provider_b import password as imported\n'
                    'with nullcontext(imported) as password:\n'
                    '    pass\n',
                    True,
                ),
                (
                    'import os\n'
                    'from contextlib import nullcontext\n'
                    'import provider_b\n'
                    'with nullcontext(provider_b.password) as password:\n'
                    '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'from contextlib import nullcontext\n'
                    'import provider_b\n'
                    'with nullcontext(provider_b.password) as unused:\n'
                    '    pass\n'
                    'password = None\n',
                    False,
                ),
                (
                    'import provider_b\n'
                    '(password := provider_b.password)\n',
                    True,
                ),
                (
                    'from provider_b import password as imported\n'
                    '(password := imported)\n',
                    True,
                ),
                (
                    'import provider_b\n'
                    'if (password := provider_b.password):\n'
                    '    pass\n',
                    True,
                ),
                (
                    'import provider_b\n'
                    'if enabled and (password := provider_b.password):\n'
                    '    pass\n',
                    True,
                ),
                (
                    'import os\n'
                    'import provider_b\n'
                    '(password := provider_b.password)\n'
                    'password = os.getenv("TCP_ELASTIC_PASSWORD")\n',
                    False,
                ),
                (
                    'import os\n'
                    'from provider_b import password as imported\n'
                    '(password := os.getenv("TCP_ELASTIC_PASSWORD"))\n',
                    False,
                ),
                (
                    'import provider_b\n'
                    'value = lambda: (password := provider_b.password)\n'
                    'password = None\n',
                    False,
                ),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        intermediary.write_text(source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in paths, expected)
                        self.assertEqual(
                            "password" in self._imported_credential_exports.get(
                                provider.resolve(), set()
                            ), expected,
                        )

    def test_walrus_rhs_and_fixed_nonempty_loop_exports(self):
        """Do not miss RHS walruses or resurrect overwritten loop secrets."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            intermediary = root / "provider_a.py"
            provider = root / "provider_b.py"
            consumer.write_text(
                'from provider_a import password\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            cases = (
                ('import provider_b\n'
                 'value = (password := provider_b.password)\n', True),
                ('from provider_b import password as imported\n'
                 'value = (password := imported)\n', True),
                ('import provider_b\n'
                 'value, other = (password := provider_b.password), None\n', True),
                ('import provider_b\n'
                 'value = ((password := provider_b.password), "safe")\n', True),
                ('import os\nimport provider_b\n'
                 'value = (password := provider_b.password)\n'
                 'password = os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('from provider_b import password\n'
                 '(password := None,)\n', False),
                ('from provider_b import password\n'
                 'value = ((password := None),)\n', False),
                ('from provider_b import password\n'
                 '[password := None]\n', False),
                ('from provider_b import password\n'
                 'value = (password := None, 1)\n', False),
                ('from provider_b import password\n'
                 'value = False and (password := None)\n', True),
                ('from provider_b import password\n'
                 'value = True or (password := None)\n', True),
                ('from provider_b import password\n'
                 'value = True and (password := None)\n', False),
                ('from provider_b import password\n'
                 'for password in [None]:\n'
                 '    pass\n', False),
                ('from provider_b import password\n'
                 'for password in [password, None]:\n'
                 '    pass\n', False),
                ('from provider_b import password\n'
                 'for password in [None, password]:\n'
                 '    pass\n', True),
                ('from provider_b import password\n'
                 'for password in []:\n'
                 '    pass\n', True),
                ('from provider_b import password\n'
                 'for password in [None]:\n'
                 '    break\n', False),
                ('from provider_b import password\n'
                 'for password in [None]:\n'
                 '    pass\n'
                 'else:\n'
                 '    password = None\n', False),
                ('from provider_b import password\n'
                 'for password in [password]:\n'
                 '    pass\n', True),
                ('from provider_b import password\n'
                 'for password in [None]:\n'
                 '    continue\n', False),
                ('from provider_b import password\n'
                 'for password in [None]:\n'
                 '    if enabled:\n'
                 '        password = password\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        intermediary.write_text(source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in paths, expected)
                        self.assertEqual(
                            "password" in self._imported_credential_exports.get(
                                provider.resolve(), set()
                            ), expected,
                        )

    def test_augassign_nested_try_suppress_and_match_guard_paths(self):
        """Track module exports through interrupted and guarded control flow."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            intermediary = root / "provider_a.py"
            provider = root / "provider_b.py"
            consumer.write_text(
                'from provider_a import password\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            cases = (
                ('import provider_b\nvalue = ""\n'
                 'value += (password := provider_b.password)\n', True),
                ('from provider_b import password as imported\nvalue = ""\n'
                 'value += (password := imported)\n', True),
                ('import os\nimport provider_b\nvalue = ""\n'
                 'value += (password := provider_b.password)\n'
                 'password = os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('import os\ntry:\n    try:\n'
                 '        from provider_b import password\n'
                 '        optional_operation()\n'
                 '        password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                 '    finally:\n        pass\n'
                 'except Exception:\n    pass\n', True),
                ('import os\ntry:\n    try:\n'
                 '        from provider_b import password\n'
                 '        optional_operation()\n'
                 '    finally:\n'
                 '        password = None\n'
                 'except Exception:\n    pass\n', False),
                ('import os\ntry:\n    try:\n'
                 '        from provider_b import password\n'
                 '        optional_operation()\n'
                 '    finally:\n        pass\n'
                 '    password = None\n'
                 'except Exception:\n'
                 '    password = None\n', False),
                ('import contextlib\n'
                 'with contextlib.suppress(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n'
                 '    password = None\n', True),
                ('from contextlib import suppress\n'
                 'with suppress(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n'
                 '    password = None\n', True),
                ('import contextlib as ctx\n'
                 'with ctx.suppress(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n'
                 '    password = None\n', True),
                ('import os\nimport contextlib\n'
                 'with contextlib.suppress(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n'
                 'password = os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('import contextlib\n'
                 'with contextlib.suppress(Exception):\n'
                 '    from provider_b import password\n'
                 '    password = None\n', False),
                ('import provider_b\nmatch 1:\n'
                 '    case 1 if (password := provider_b.password):\n'
                 '        pass\n', True),
                ('import provider_b\nmatch 1:\n'
                 '    case 1 if (password := provider_b.password):\n'
                 '        pass\n'
                 '    case _:\n'
                 '        pass\n', True),
                ('import os\nimport provider_b\nmatch 1:\n'
                 '    case 1 if (password := provider_b.password):\n'
                 '        pass\n'
                 'password = os.getenv("TCP_ELASTIC_PASSWORD")\n', False),
                ('import os\nimport provider_b\nmatch 1:\n'
                 '    case 1 if (password := os.getenv("TCP_ELASTIC_PASSWORD")):\n'
                 '        pass\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        intermediary.write_text(source, encoding="utf-8")
                        paths = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in paths, expected)
                        self.assertEqual(
                            "password" in self._imported_credential_exports.get(
                                provider.resolve(), set()
                            ), expected,
                        )

    def test_raising_assignment_targets_and_suppress_aliases(self):
        """Store targets and aliased context managers preserve secret paths."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            intermediary = root / "provider_a.py"
            provider = root / "provider_b.py"
            consumer.write_text(
                'from provider_a import password\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                encoding="utf-8",
            )
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            cases = (
                ('import os\ntry:\n'
                 '    from provider_b import password\n'
                 '    receiver.value = None\n'
                 '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                 'except Exception:\n'
                 '    pass\n', True),
                ('import os\ntry:\n'
                 '    from provider_b import password\n'
                 '    receiver["value"] = None\n'
                 '    password = os.getenv("TCP_ELASTIC_PASSWORD")\n'
                 'except Exception:\n'
                 '    pass\n', True),
                ('import os\ntry:\n'
                 '    from provider_b import password\n'
                 '    receiver.value = None\n'
                 '    password = None\n'
                 'except Exception:\n'
                 '    password = None\n', False),
                ('import os\ntry:\n'
                 '    from provider_b import password\n'
                 '    receiver.value = None\n'
                 'finally:\n'
                 '    password = None\n', False),
                ('import contextlib\n'
                 'ignore = contextlib.suppress\n'
                 'with ignore(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n'
                 '    password = None\n', True),
                ('import contextlib\n'
                 'ignore = contextlib.suppress\n'
                 'another = ignore\n'
                 'with another(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n'
                 '    password = None\n', True),
                ('import contextlib as ctx\n'
                 'ignore = ctx.suppress\n'
                 'with ignore(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n', True),
                ('from contextlib import suppress as original\n'
                 'ignore = original\n'
                 'with ignore(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n', True),
                ('import contextlib\n'
                 'ignore = contextlib.suppress\n'
                 'with ignore(Exception):\n'
                 '    from provider_b import password\n'
                 '    raise RuntimeError()\n'
                 'password = None\n', False),
                ('import contextlib\n'
                 'ignore = contextlib.suppress\n'
                 'with ignore(Exception):\n'
                 '    from provider_b import password\n'
                 '    password = None\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        intermediary.write_text(source, encoding="utf-8")
                        included = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in included, expected)
                        self.assertEqual(
                            "password" in self._imported_credential_exports.get(
                                provider.resolve(), set()
                            ), expected,
                        )

    def test_wildcard_provider_credentials_and_overwrites(self):
        """Follow star imports only when their credential values can reach ES."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            intermediary = root / "provider_a.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            consumer_source = (
                'from provider_a import password\n'
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                cases = (
                    ('from provider_b import *\n', True),
                    ('from provider_b import *\npassword = password\n', True),
                    ('from provider_b import *\npassword = password.strip()\n', True),
                    ('from provider_b import *\npassword = password.replace("x", "y")\n', True),
                    ('from provider_b import *\npassword = str(password)\n', True),
                    ('from provider_b import *\npassword: str = password.strip()\n', True),
                    ('from provider_b import *\npassword = password.strip()\npassword = None\n', False),
                    ('from provider_b import *\npassword: str = password\n', True),
                    ('from provider_b import *\npassword, unused = (password, None)\n', True),
                    ('from provider_b import *\nunused, password = (None, password)\n', True),
                    ('from provider_b import *\nunused, password = (None, password.strip())\n', True),
                    ('from provider_b import *\nunused, password = (password.strip(), None)\n', False),
                    ('from provider_b import *\nunused, password = (password, None)\n', False),
                    ('from provider_b import *\nunused, password = (password, 0)\n', False),
                    ('from provider_b import *\npassword, unused = (None, password)\n', False),
                    ('from provider_b import *\nunused, password = (password, None)\npassword = password\n', False),
                    ('from provider_b import *\nunused, password = (password, None)\npassword = None\n', False),
                    ('from provider_b import *\npassword = password\npassword = None\n', False),
                    ('from provider_b import *\npassword = None\n', False),
                    ('from provider_b import *\npassword = 0\n', False),
                    ('password = None\nfrom provider_b import *\n', True),
                )
                for source, expected in cases:
                    with self.subTest(source=source):
                        intermediary.write_text(source, encoding="utf-8")
                        consumer.write_text(consumer_source, encoding="utf-8")
                        included = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in included, expected)
                        self.assertEqual(
                            "password" in self._imported_credential_exports.get(
                                provider.resolve(), set()
                            ), expected,
                        )
                consumer.write_text(
                    'from provider_b import *\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                    encoding="utf-8",
                )
                intermediary.write_text('pass\n', encoding="utf-8")
                included = set(self._runtime_es_module_paths())
                self.assertIn(provider.resolve(), included)
                self.assertIn(
                    "password",
                    self._imported_credential_exports.get(
                        provider.resolve(), set()
                    ),
                )
                consumer.write_text(
                    'from provider_b import *\n'
                    'password = password\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                    encoding="utf-8",
                )
                included = set(self._runtime_es_module_paths())
                self.assertIn(provider.resolve(), included)
                self.assertIn(
                    "password",
                    self._imported_credential_exports.get(
                        provider.resolve(), set()
                    ),
                )
                consumer.write_text(
                    'from provider_b import *\n'
                    'password = password.strip()\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                    encoding="utf-8",
                )
                included = set(self._runtime_es_module_paths())
                self.assertIn(provider.resolve(), included)
                self.assertIn(
                    "password",
                    self._imported_credential_exports.get(
                        provider.resolve(), set()
                    ),
                )
                consumer.write_text(
                    'from provider_b import *\n'
                    'unused, password = (password, None)\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                    encoding="utf-8",
                )
                included = set(self._runtime_es_module_paths())
                self.assertNotIn(provider.resolve(), included)
                consumer.write_text(
                    'from provider_b import *\n'
                    'unused, password = (password, None)\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", unused))\n',
                    encoding="utf-8",
                )
                included = set(self._runtime_es_module_paths())
                self.assertIn(provider.resolve(), included)
                self.assertIn(
                    "password",
                    self._imported_credential_exports.get(
                        provider.resolve(), set()
                    ),
                )
                consumer.write_text(
                    'from provider_b import *\n'
                    'password = None\n'
                    'from elasticsearch import Elasticsearch\n'
                    'Elasticsearch("localhost", basic_auth=("elastic", password))\n',
                    encoding="utf-8",
                )
                included = set(self._runtime_es_module_paths())
                self.assertNotIn(provider.resolve(), included)

    def test_relative_package_wildcard_credentials(self):
        """Bare relative star imports reach package __init__ credentials."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "credential_package"
            package.mkdir()
            provider = package / "__init__.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            consumer = package / "es_consumer.py"
            prefix = (
                'from . import *\n'
                'from elasticsearch import Elasticsearch\n'
            )
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                consumer.write_text(prefix + auth, encoding="utf-8")
                paths = set(self._runtime_es_module_paths())
                self.assertIn(provider.resolve(), paths)
                self.assertIn(
                    "password", self._imported_credential_exports.get(
                        provider.resolve(), set()
                    )
                )
                consumer.write_text(
                    prefix + 'password = None\n' + auth, encoding="utf-8"
                )
                self.assertNotIn(provider.resolve(), self._runtime_es_module_paths())
                # Parent-package relative star imports must resolve too.
                nested = package / "nested"
                nested.mkdir()
                consumer.unlink()
                consumer = nested / "es_consumer.py"
                consumer.write_text(
                    'from .. import *\n'
                    'from elasticsearch import Elasticsearch\n' + auth,
                    encoding="utf-8",
                )
                self.assertIn(provider.resolve(), self._runtime_es_module_paths())

    def test_wildcard_self_reads_respect_nested_lambda_scope(self):
        """A lambda-local password is not a star-imported module password."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            prefix = (
                'import os\n'
                'from provider_b import *\n'
            )
            auth = (
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
            )
            cases = (
                ('password = (lambda password: password.strip())('
                 'os.environ["TCP_ELASTIC_PASSWORD"])\n', False),
                ('password = (lambda password: password)("safe")\n', False),
                ('password = (lambda: password.strip())()\n', True),
                ('password = password.strip()\n', True),
                ('password = (lambda password: password.strip())('
                 'os.environ["TCP_ELASTIC_PASSWORD"])\n'
                 'password = None\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for assignment, expected in cases:
                    with self.subTest(assignment=assignment):
                        consumer.write_text(
                            prefix + assignment + auth, encoding="utf-8"
                        )
                        included = set(self._runtime_es_module_paths())
                        self.assertEqual(provider.resolve() in included, expected)
                        self.assertEqual(
                            "password" in self._imported_credential_exports.get(
                                provider.resolve(), set()
                            ), expected,
                        )

    def test_wildcard_comprehension_local_names(self):
        """Comprehension binding scopes distinguish local from imported passwords."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            prefix = 'import os\nfrom provider_b import *\n'
            suffix = (
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
            )
            cases = (
                ('password = [password.strip() for password in '
                 '[os.environ["TCP_ELASTIC_PASSWORD"]]][0]\n', False),
                ('password = {password.strip() for password in '
                 '[os.environ["TCP_ELASTIC_PASSWORD"]]}.pop()\n', False),
                ('password = next(password.strip() for password in '
                 '[os.environ["TCP_ELASTIC_PASSWORD"]])\n', False),
                ('password = [password.strip() for unused in [None]][0]\n', True),
                ('password = [x.strip() for x in [password]][0]\n', True),
                ('password = password.strip()\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for assignment, expected in cases:
                    with self.subTest(assignment=assignment):
                        consumer.write_text(
                            prefix + assignment + suffix, encoding="utf-8"
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_comprehension_skips_enclosing_class_scope(self):
        """The first iterable reads class locals; comprehension body does not."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            prefix = (
                'import os\n'
                'from provider_b import *\n'
                'from elasticsearch import Elasticsearch\n'
                'class Client:\n'
                '    password = None\n'
            )
            cases = (
                # Comprehension result reads the imported module password.
                ('    result = Elasticsearch("localhost", basic_auth='
                 '("elastic", [password for _ in [None]][0]))\n', True),
                ('    result = Elasticsearch("localhost", basic_auth='
                 '("elastic", {password for _ in [None]}.pop()))\n', True),
                ('    result = Elasticsearch("localhost", basic_auth='
                 '("elastic", {"key": password for _ in [None]}["key"]))\n', True),
                ('    result = Elasticsearch("localhost", basic_auth='
                 '("elastic", next(password for _ in [None])))\n', True),
                ('    result = Elasticsearch("localhost", basic_auth='
                 '("elastic", [[password for _ in [None]] for _ in [None]][0][0]))\n', True),
                # First iterable is evaluated in the enclosing class scope.
                ('    result = Elasticsearch("localhost", basic_auth='
                 '("elastic", [item for item in [password]][0]))\n', False),
                # A local target shadows both class and module bindings.
                ('    result = Elasticsearch("localhost", basic_auth='
                 '("elastic", [password for password in '
                 '[os.environ["TCP_ELASTIC_PASSWORD"]]][0]))\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for code, expected in cases:
                    with self.subTest(code=code):
                        consumer.write_text(prefix + code, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_use_inside_conditional_branch(self):
        """An opposite branch cannot flow into a call in the selected branch."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            prefix = (
                'from provider_b import *\n'
                'from elasticsearch import Elasticsearch\n'
            )
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
            cases = (
                ('if flag:\n'
                 '    password = None\n'
                 '    ' + auth, False),
                ('if flag:\n'
                 '    password = None\n'
                 '    if other_flag:\n'
                 '        ' + auth, False),
                ('if flag:\n'
                 '    password = password.strip()\n'
                 '    ' + auth, True),
                ('if flag:\n'
                 '    ' + auth +
                 'else:\n'
                 '    password = None\n', True),
                ('if flag:\n'
                 '    password = None\n'
                 'else:\n'
                 '    ' + auth, True),
                ('if flag:\n'
                 '    password = None\n' + auth, True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for code, expected in cases:
                    with self.subTest(code=code):
                        consumer.write_text(prefix + code, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_import_after_deferred_global_read(self):
        """Global reads in deferred callables can see later star imports."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = (
                'Elasticsearch("localhost", basic_auth=("elastic", password))'
            )
            cases = (
                ('password = None\n'
                 'def run():\n    ' + auth + '\n'
                 'from provider_b import *\nrun()\n', True),
                ('password = None\n'
                 'run = lambda: ' + auth + '\n'
                 'from provider_b import *\nrun()\n', True),
                ('password = None\n'
                 'def run():\n    ' + auth + '\n'
                 'from provider_b import *\n'
                 'password = password.strip()\nrun()\n', True),
                # The only module-level call precedes the later import;
                # it cannot read a credential introduced afterwards.
                ('password = None\n'
                 'def run():\n    ' + auth + '\n'
                 'run()\nfrom provider_b import *\n', False),
                ('password = None\n'
                 'def run():\n    password = None\n    ' + auth + '\n'
                 'from provider_b import *\nrun()\n', False),
                ('password = None\n'
                 + auth + '\nfrom provider_b import *\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, should_include in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            should_include,
                        )

    def test_wildcard_if_header_walrus_reaching_state(self):
        """Walrus writes in a conditional header precede reads in its arms."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = (
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
            )
            cases = (
                ('if (password := os.environ["TCP_ELASTIC_PASSWORD"]):\n'
                 '    ' + auth, False),
                ('if (password := os.environ["TCP_ELASTIC_PASSWORD"]):\n'
                 '    if enabled:\n        ' + auth, False),
                ('if (password := os.environ["TCP_ELASTIC_PASSWORD"]):\n'
                 '    pass\nelse:\n    ' + auth, False),
                ('if (password := password.strip()):\n'
                 '    ' + auth, True),
                ('if (safe := os.environ["TCP_ELASTIC_PASSWORD"]):\n'
                 '    ' + auth, True),
                ('if enabled:\n'
                 '    password = None\n'
                 '    if (other := 1):\n'
                 '        ' + auth, False),
                # Entering the true arm proves the short-circuited
                # walrus did execute, so the imported secret is overwritten.
                ('if enabled and (password := os.environ["TCP_ELASTIC_PASSWORD"]):\n'
                 '    ' + auth, False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for code, should_include in cases:
                    with self.subTest(code=code):
                        consumer.write_text(
                            'import os\n'
                            'from provider_b import *\n'
                            'from elasticsearch import Elasticsearch\n'
                            + code,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            should_include,
                        )

    def test_wildcard_deferred_invocation_before_later_overwrite(self):
        """At the call, a later module overwrite has not executed yet."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            cases = (
                ('password = None\n'
                 'def run():\n    ' + auth + '\n'
                 'from provider_b import *\nrun()\npassword = None\n', True),
                ('password = None\n'
                 'run = lambda: ' + auth + '\n'
                 'from provider_b import *\nrun()\npassword = None\n', True),
                ('password = None\n'
                 'def run():\n    ' + auth + '\n'
                 'from provider_b import *\n'
                 'alias = run\nalias()\npassword = None\n', True),
                ('password = None\n'
                 'def run():\n    ' + auth + '\n'
                 'from provider_b import *\n'
                 'password = None\nrun()\n', False),
                ('password = None\n'
                 'def run():\n    ' + auth + '\n'
                 'from provider_b import *\n'
                 'run()\npassword = None\nrun()\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for code, expected in cases:
                    with self.subTest(code=code):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n' + code,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_callable_escape_alias_and_closure_invocation(self):
        """Invocation snapshots follow live aliases and returned closures."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            direct = 'def run():\n    ' + auth + '\n'
            nested = (
                'def outer():\n'
                '    def inner():\n'
                '        ' + auth + '\n'
                '    return inner\n'
            )
            cases = (
                (direct + 'invoke(run)\npassword = None\n', True),
                (direct + 'callback = run\ninvoke(callback)\n'
                 'password = None\n', True),
                (direct + 'alias = run\nalias = lambda: None\n'
                 'alias()\npassword = None\n', False),
                (direct + 'alias = run\nalias()\n'
                 'alias = lambda: None\npassword = None\n', True),
                (direct + 'alias = run\nalias = lambda: None\n'
                 'alias()\n', True),
                (nested + 'callback = outer()\npassword = None\n'
                 'callback()\n', False),
                (nested + 'callback = outer()\ncallback()\n'
                 'password = None\n', True),
                (nested + 'callback = outer()\n'
                 'password = None\nalias = callback\nalias()\n', False),
                (nested + 'callback = outer()\n'
                 'invoke(callback)\npassword = None\n', True),
                (nested + 'outer()\npassword = None\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for body, expected in cases:
                    with self.subTest(body=body):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + body,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_nested_direct_and_suspended_invocation(self):
        """Nested call, opaque storage and coroutine/generator resume timing."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            nested = (
                'def outer():\n'
                '    def inner():\n'
                '        ' + auth + '\n'
                '    inner()\n'
            )
            direct = 'def run():\n    ' + auth + '\n'
            asynchronous = 'async def run():\n    ' + auth + '\n'
            generator = 'def run():\n    yield 1\n    ' + auth + '\n'
            cases = (
                (nested + 'outer()\npassword = None\n', True),
                (nested + 'password = None\nouter()\n', False),
                ('holder = type("Holder", (), {})()\n' + direct
                 + 'holder.cb = run\nholder.cb()\npassword = None\n', True),
                ('holder = {}\n' + direct
                 + 'holder["cb"] = run\nholder["cb"]()\npassword = None\n', True),
                (asynchronous
                 + 'coro = run()\npassword = None\n'
                 'asyncio.run(coro)\n', False),
                (asynchronous
                 + 'coro = run()\nasyncio.run(coro)\n'
                 'password = None\n', True),
                (generator
                 + 'gen = run()\npassword = None\n'
                 'next(gen)\nnext(gen)\n', False),
                (generator
                 + 'gen = run()\nnext(gen)\nnext(gen)\n'
                 'password = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_generator_consumers_reachability_and_unpacking(self):
        """Resume receivers, unknown consumers, suspension steps, and dead calls."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            generator = 'def run():\n    yield 1\n    ' + auth + '\n'
            immediate = 'def run():\n    ' + auth + '\n    yield 1\n'
            direct = 'def run():\n    ' + auth + '\n'
            cases = (
                (immediate + 'gen = run()\ngen.send(None)\npassword = None\n', True),
                (immediate + 'gen = run()\ngen.__next__()\npassword = None\n', True),
                (generator + 'gen = run()\ngen.send(None)\n'
                 'password = None\ngen.__next__()\n', False),
                (generator + 'gen = run()\ngen.__next__()\n'
                 'gen.send(None)\npassword = None\n', True),
                (generator + 'gen = run()\nnext(gen)\n'
                 'password = None\nnext(gen)\n', False),
                (generator + 'gen = run()\nnext(gen)\n'
                 'next(gen)\npassword = None\n', True),
                (immediate + 'gen = run()\nconsume(gen)\n'
                 'password = None\n', True),
                (immediate + 'gen = run()\npassword = None\n'
                 'consume(gen)\n', False),
                ('def outer():\n'
                 '    def inner():\n        ' + auth + '\n'
                 '    if False:\n        inner()\n'
                 'outer()\npassword = None\n', False),
                ('def outer():\n'
                 '    def inner():\n        ' + auth + '\n'
                 '    return None\n    inner()\n'
                 'outer()\npassword = None\n', False),
                ('def outer():\n'
                 '    def inner():\n        ' + auth + '\n'
                 '    if True:\n        inner()\n'
                 'outer()\npassword = None\n', True),
                (direct + 'callback, unused = run, None\n'
                 'password = None\ncallback()\n', False),
                (direct + 'callback, unused = run, None\n'
                 'callback()\npassword = None\n', True),
                (direct + 'callbacks = [run]\n'
                 'callbacks[0]()\npassword = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_generator_yield_loop_and_initial_send(self):
        """Credential evaluation at a yield, repeated resume, invalid first send."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            yielded_auth = 'def run():\n    yield ' + auth + '\n'
            later_auth = 'def run():\n    yield 1\n    ' + auth + '\n'
            cases = (
                (yielded_auth + 'gen = run()\nnext(gen)\npassword = None\n', True),
                (yielded_auth + 'gen = run()\npassword = None\nnext(gen)\n', False),
                (yielded_auth + 'gen = run()\ngen.send(None)\n'
                 'password = None\n', True),
                (later_auth + 'gen = run()\n'
                 'for _ in range(2):\n    next(gen)\n'
                 'password = None\n', True),
                (later_auth + 'gen = run()\n'
                 'for _ in range(1):\n    next(gen)\n'
                 'password = None\n', False),
                (later_auth + 'gen = run()\n'
                 'for _ in range(0):\n    next(gen)\n'
                 'password = None\n', False),
                (later_auth + 'gen = run()\n'
                 'password = None\n'
                 'for _ in range(2):\n    next(gen)\n', False),
                (yielded_auth + 'gen = run()\n'
                 'try:\n    gen.send(7)\n'
                 'except TypeError:\n    pass\n'
                 'password = None\nnext(gen)\n', False),
                (yielded_auth + 'gen = run()\n'
                 'try:\n    gen.send(7)\n'
                 'except TypeError:\n    pass\n'
                 'next(gen)\npassword = None\n', True),
                (later_auth + 'gen = run()\nnext(gen)\n'
                 'gen.send(7)\npassword = None\n', True),
                (later_auth + 'gen = run()\nnext(gen)\n'
                 'password = None\ngen.send(7)\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_generator_review_resumption_paths(self):
        """While tests, starred loops, delegation, fresh instances, send aliases."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            after_yield = 'def run():\n    yield True\n    ' + auth + '\n'
            yielded_auth = 'def run():\n    yield ' + auth + '\n'
            cases = (
                (after_yield + 'gen = run()\nwhile next(gen):\n    pass\n'
                 'password = None\n', True),
                (after_yield + 'gen = run()\npassword = None\n'
                 'while next(gen):\n    pass\n', False),
                (after_yield + 'gen = run()\n'
                 'for _ in [*(1, 2)]:\n    next(gen)\n'
                 'password = None\n', True),
                (after_yield + 'gen = run()\n'
                 'for _ in [*()]:\n    next(gen)\n'
                 'password = None\n', False),
                (after_yield + 'gen = run()\n'
                 'results = [next(gen) for _ in range(2)]\n'
                 'password = None\n', True),
                (after_yield + 'gen = run()\n'
                 'password = None\n'
                 'results = [next(gen) for _ in range(2)]\n', False),
                ('def run():\n    yield from []\n    ' + auth + '\n'
                 'gen = run()\nnext(gen)\npassword = None\n', True),
                ('def run():\n    yield from xs\n    ' + auth + '\n'
                 'gen = run()\nnext(gen)\npassword = None\n', True),
                ('def run():\n    yield from [1, 2]\n    ' + auth + '\n'
                 'gen = run()\nnext(gen)\nnext(gen)\n'
                 'password = None\nnext(gen)\n', False),
                (after_yield
                 + 'for _ in range(2):\n'
                 '    gen = run()\n    next(gen)\n'
                 'password = None\n', False),
                (after_yield
                 + 'for _ in range(2):\n'
                 '    gen = run()\n    next(gen)\n    next(gen)\n'
                 'password = None\n', True),
                (yielded_auth
                 + 'gen = run()\nvalue = 7\n'
                 'try:\n    gen.send(value)\n'
                 'except TypeError:\n    pass\n'
                 'password = None\nnext(gen)\n', False),
                (yielded_auth
                 + 'gen = run()\nvalue = 7\n'
                 'try:\n    gen.send(value)\n'
                 'except TypeError:\n    pass\n'
                 'next(gen)\npassword = None\n', True),
                (after_yield
                 + 'gen = run()\nvalue = 7\nnext(gen)\n'
                 'gen.send(value)\npassword = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_source_visible_callable_password_literal_returns(self):
        """Only provable callable return literals count as hardcoded secrets."""
        cases = (
            ('password = (lambda: "hardcoded-secret")()\n', True),
            ('def secret():\n    return "hardcoded-secret"\n'
             'password = secret()\n', True),
            ('def secret():\n    return "hardcoded-secret"\n'
             'alias = secret\npassword = alias()\n', True),
            ('secret = lambda: "hardcoded-secret"\n'
             'password = secret()\n', True),
            ('secret = lambda: "hardcoded-secret"\n'
             'secret = lambda: None\npassword = secret()\n', False),
            ('password = resolver("lookup-key")\n', False),
            ('password = (lambda: os.environ["TCP_ELASTIC_PASSWORD"])()\n', False),
            ('def secret():\n    return os.getenv("TCP_ELASTIC_PASSWORD")\n'
             'password = secret()\n', False),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    bool(hardcoded_password_literal_lines(source)), expected
                )
        auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        self.assertTrue(hardcoded_auth_tuple_lines(
            'password = (lambda: "hardcoded-secret")()\n' + auth
        ))
        self.assertTrue(hardcoded_auth_tuple_lines(
            'def secret():\n    return "hardcoded-secret"\n'
            'password = secret()\n' + auth
        ))

    def test_wildcard_comprehension_identity_and_branch_resume(self):
        """Fresh generators and mutually exclusive branches are not cumulative."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            source_def = 'def run():\n    yield 1\n    ' + auth + '\n'
            cases = (
                (source_def + 'results = [next(run()) for _ in range(2)]\n'
                 'password = None\n', False),
                (source_def + 'gen = run()\n'
                 'results = [next(gen) for _ in range(2)]\n'
                 'password = None\n', True),
                (source_def + 'gen = run()\n'
                 'if flag:\n    next(gen)\n'
                 'else:\n    next(gen)\n'
                 'password = None\nnext(gen)\n', False),
                (source_def + 'gen = run()\n'
                 'if flag:\n    next(gen)\n'
                 'else:\n    next(gen)\n'
                 'next(gen)\npassword = None\n', True),
                (source_def + 'gen = run()\n'
                 'if flag:\n    next(gen)\n'
                 'else:\n    next(gen)\n'
                 'password = None\n', False),
                (source_def + 'gen = run()\n'
                 'next(gen)\n'
                 'if flag:\n    next(gen)\n'
                 'password = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_hardcoded_default_argument_return_callables(self):
        """Zero-arg calls can return required positional/keyword defaults."""
        cases = (
            ('password = (lambda value="hardcoded-secret": value)()\n', True),
            ('password = (lambda *, value="hardcoded-secret": value)()\n', True),
            ('password = (lambda a="hardcoded-secret", b="safe": a)()\n', True),
            ('def get_password(value="hardcoded-secret"):\n'
             '    return value\npassword = get_password()\n', True),
            ('def get_password(*, value="hardcoded-secret"):\n'
             '    return value\npassword = get_password()\n', True),
            ('def get_password(value="hardcoded-secret"):\n'
             '    return value.strip()\npassword = get_password()\n', True),
            ('def get_password(value="hardcoded-secret"):\n'
             '    return None\npassword = get_password()\n', False),
            ('password = (lambda value="hardcoded-secret": None)()\n', False),
            ('password = (lambda required, opt="hardcoded-secret": opt)()\n', False),
            ('password = (lambda value=os.getenv("TCP_ELASTIC_PASSWORD"): value)()\n', False),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    bool(hardcoded_password_literal_lines(source)), expected
                )
        self.assertTrue(hardcoded_auth_tuple_lines(
            'def get_password(value="hardcoded-secret"):\n'
            '    return value\n'
            'password = get_password()\n'
            'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        ))

    def test_wildcard_generator_prune_constant_if_resume(self):
        """An unreachable branch must not advance the generator counter."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            generator = 'def run():\n    yield 1\n    ' + auth + '\n'
            cases = (
                (generator + 'gen = run()\n'
                 'if False:\n    next(gen)\n'
                 'next(gen)\npassword = None\n', False),
                (generator + 'gen = run()\n'
                 'if True:\n    next(gen)\n'
                 'next(gen)\npassword = None\n', True),
                (generator + 'gen = run()\n'
                 'if False:\n    next(gen)\n'
                 'else:\n    next(gen)\n'
                 'next(gen)\npassword = None\n', True),
                (generator + 'gen = run()\n'
                 'if True:\n    next(gen)\n'
                 'else:\n    next(gen)\n'
                 'password = None\n', False),
                (generator + 'gen = run()\n'
                 'if False:\n    next(gen)\n'
                 'password = None\nnext(gen)\n', False),
                (generator + 'gen = run()\n'
                 'if flag:\n    next(gen)\n'
                 'else:\n    next(gen)\n'
                 'next(gen)\npassword = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_hardcoded_callable_default_captured_before_overwrite(self):
        """Default values freeze earlier name aliases at definition time."""
        cases = (
            ('secret = "hardcoded-secret"\n'
             'get_password = lambda value=secret: value\n'
             'secret = None\npassword = get_password()\n', True),
            ('secret = "hardcoded-secret"\n'
             'def get_password(value=secret):\n    return value\n'
             'secret = None\npassword = get_password()\n', True),
            ('secret = "hardcoded-secret"\n'
             'get_password = lambda *, value=secret: value\n'
             'secret = None\npassword = get_password()\n', True),
            ('secret = None\n'
             'get_password = lambda value=secret: value\n'
             'secret = "hardcoded-secret"\npassword = get_password()\n', False),
            ('secret = os.getenv("TCP_ELASTIC_PASSWORD")\n'
             'get_password = lambda value=secret: value\n'
             'secret = "hardcoded-secret"\npassword = get_password()\n', False),
            ('secret = "hardcoded-secret"\n'
             'get_password = lambda value=secret: None\n'
             'secret = None\npassword = get_password()\n', False),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    bool(hardcoded_password_literal_lines(source)), expected
                )
        self.assertTrue(hardcoded_auth_tuple_lines(
            'secret = "hardcoded-secret"\n'
            'get_password = lambda value=secret: value\n'
            'secret = None\n'
            'password = get_password()\n'
            'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        ))

    def test_wildcard_generator_static_false_expressions(self):
        """Provably unreachable expression branches cannot advance resumes."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            definition = 'def run():\n    yield 1\n    ' + auth + '\n'
            cases = (
                ('if not True:\n    next(gen)\nnext(gen)\npassword = None\n', False),
                ('if 1 == 2:\n    next(gen)\nnext(gen)\npassword = None\n', False),
                ('if False and flag:\n    next(gen)\nnext(gen)\npassword = None\n', False),
                ('if True or flag:\n    next(gen)\nnext(gen)\npassword = None\n', True),
                ('if not False:\n    next(gen)\nnext(gen)\npassword = None\n', True),
                ('if 1 != 2:\n    next(gen)\nnext(gen)\npassword = None\n', True),
                ('if True and flag:\n    next(gen)\nnext(gen)\npassword = None\n', True),
                ('if not True:\n    next(gen)\nelse:\n    next(gen)\n'
                 'next(gen)\npassword = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n'
                            + definition + 'gen = run()\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_source_visible_variadic_provider_credentials(self):
        """Variadic parameters retain only actual argument/keyword slots."""
        cases = (
            ('def provider(*values):\n    return values[0]\n'
             'password = provider("hardcoded-secret")\n', True),
            ('password = (lambda *values: values[1])(None, "hardcoded-secret")\n', True),
            ('def provider(*values):\n    return values[0]\n'
             'password = provider(None, "hardcoded-secret")\n', False),
            ('def provider(prefix, *values):\n    return values[0]\n'
             'password = provider(None, "hardcoded-secret")\n', True),
            ('def provider(**values):\n    return values["password"]\n'
             'password = provider(password="hardcoded-secret")\n', True),
            ('def provider(**values):\n    return values["password"]\n'
             'password = provider(password=None, unused="hardcoded-secret")\n', False),
            ('def provider(value, **values):\n    return value\n'
             'password = provider(None, unused="hardcoded-secret")\n', False),
            ('def provider(*values):\n    return values[0]\n'
             'password = provider(*external)\n', False),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(bool(hardcoded_password_literal_lines(source)), expected)
        self.assertTrue(hardcoded_auth_tuple_lines(
            'def provider(*values):\n    return values[0]\n'
            'password = provider("hardcoded-secret")\n'
            'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        ))

    def test_source_visible_argumented_provider_credentials(self):
        """Known positional/keyword returns are inspectable; opaque calls are not."""
        cases = (
            ('def provider(unused):\n    return "hardcoded-secret"\n'
             'password = provider(None)\n', True),
            ('password = (lambda unused: "hardcoded-secret")(None)\n', True),
            ('def provider(*, unused):\n    return "hardcoded-secret"\n'
             'password = provider(unused=None)\n', True),
            ('def provider(value):\n    return value\n'
             'password = provider("hardcoded-secret")\n', True),
            ('def provider(first, second=None):\n    return first\n'
             'password = provider("hardcoded-secret", second=None)\n', True),
            ('def provider(unused):\n    return os.getenv("TCP_ELASTIC_PASSWORD")\n'
             'password = provider("hardcoded-secret")\n', False),
            ('password = vault.lookup("hardcoded-secret")\n', False),
            ('def provider(value):\n    return value\n'
             'password = provider(os.getenv("TCP_ELASTIC_PASSWORD"))\n', False),
            ('def provider(value):\n    return value\n'
             'password = provider()\n', False),
            ('def provider(value):\n    return value\n'
             'password = provider("hardcoded-secret", extra=True)\n', False),
            ('def provider(value):\n    return value\n'
             'password = provider(None, value="hardcoded-secret")\n', False),
            ('def provider(value):\n    return "hardcoded-secret"\n'
             'password = provider(*args)\n', False),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    bool(hardcoded_password_literal_lines(source)), expected
                )
        self.assertTrue(hardcoded_auth_tuple_lines(
            'def provider(unused):\n    return "hardcoded-secret"\n'
            'password = provider(None)\n'
            'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        ))

    def test_callable_return_nested_default_substitution(self):
        """Defaults resolve recursively through returned access paths."""
        cases = (
            ('password = (lambda value=("hardcoded-secret",): value[0])()\n', True),
            ('password = (lambda value=[None, "hardcoded-secret"]: value[1])()\n', True),
            ('password = (lambda value={"key": "hardcoded-secret"}: value["key"])()\n', True),
            ('password = (lambda value=("hardcoded-secret",): value[0].strip())()\n', True),
            ('password = (lambda value=("hardcoded-secret",): value[0] if True else None)()\n', True),
            ('def secret(value=("hardcoded-secret",)):\n'
             '    return value[0]\npassword = secret()\n', True),
            ('secret = "hardcoded-secret"\n'
             'fn = lambda value=(secret,): value[0]\n'
             'secret = None\npassword = fn()\n', True),
            ('secret = None\nfn = lambda value=(secret,): value[0]\n'
             'secret = "hardcoded-secret"\npassword = fn()\n', False),
            ('password = (lambda value=(None, "hardcoded-secret"): value[0])()\n', False),
            ('password = (lambda value={"key": None, "other": "hardcoded-secret"}: value["key"])()\n', False),
            ('password = (lambda value=(os.getenv("TCP_ELASTIC_PASSWORD"),): value[0])()\n', False),
            ('password = secret_manager.get("lookup-key")\n', False),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    bool(hardcoded_password_literal_lines(source)), expected
                )
        self.assertTrue(hardcoded_auth_tuple_lines(
            'password = (lambda value=("hardcoded-secret",): value[0])()\n'
            'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        ))

    def test_generator_identity_comparison_unknown_branch(self):
        """Only true language-level singleton identity can be folded."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            definition = 'def run():\n    yield 1\n    ' + auth + '\n'
            cases = (
                ('if 1000 is 1000:\n    next(gen)\nnext(gen)\n'
                 'password = None\n', True),
                ('if 1000 is not 1000:\n    next(gen)\nnext(gen)\n'
                 'password = None\n', True),
                ('if "token" is "token":\n    next(gen)\nnext(gen)\n'
                 'password = None\n', True),
                ('if 1 == 2:\n    next(gen)\nnext(gen)\n'
                 'password = None\n', False),
                ('if None is None:\n    next(gen)\nnext(gen)\n'
                 'password = None\n', True),
                ('if None is not None:\n    next(gen)\nnext(gen)\n'
                 'password = None\n', False),
                ('if True is False:\n    next(gen)\nnext(gen)\n'
                 'password = None\n', False),
                ('if True is not False:\n    next(gen)\nnext(gen)\n'
                 'password = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + definition
                            + 'gen = run()\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_nested_immediate_lambda_default_credentials(self):
        """An invoked nested lambda reads the outer captured default."""
        cases = (
            ('password = (lambda value="hardcoded-secret": (lambda: value)())()\n', True),
            ('password = (lambda value=("hardcoded-secret",): (lambda: value[0])())()\n', True),
            ('password = (lambda value="hardcoded-secret": (lambda: (lambda: value)())())()\n', True),
            ('secret = "hardcoded-secret"\n'
             'get_password = lambda value=secret: (lambda: value)()\n'
             'secret = None\npassword = get_password()\n', True),
            ('password = (lambda value="hardcoded-secret": (lambda: None)())()\n', False),
            ('password = (lambda value="hardcoded-secret": (lambda: value))()\n', False),
            ('password = (lambda value=os.getenv("TCP_ELASTIC_PASSWORD"): (lambda: value)())()\n', False),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    bool(hardcoded_password_literal_lines(source)), expected
                )
        self.assertTrue(hardcoded_auth_tuple_lines(
            'password = (lambda value="hardcoded-secret": (lambda: value)())()\n'
            'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        ))

    def test_defaulted_immediate_nested_lambda_capture_boundaries(self):
        """Defaulted IIFEs execute; merely returned lambdas do not."""
        cases = (
            ('password = (lambda value="hardcoded-secret": '
             '(lambda copied=value: copied)())()\n', True),
            ('password = (lambda value="hardcoded-secret": '
             '(lambda first=value: (lambda second=first: second)())())()\n', True),
            ('password = (lambda value="hardcoded-secret": '
             '(lambda *, copied=value: copied)())()\n', True),
            ('password = (lambda value="hardcoded-secret": '
             '(lambda value=None: value)())()\n', False),
            ('password = (lambda value="hardcoded-secret": '
             '(lambda copied=value: copied))()\n', False),
            ('secret = "hardcoded-secret"\n'
             'getter = lambda value=secret: (lambda copied=value: copied)()\n'
             'secret = None\npassword = getter()\n', True),
            ('secret = None\ngetter = lambda value=secret: '
             '(lambda copied=value: copied)()\n'
             'secret = "hardcoded-secret"\npassword = getter()\n', False),
            ('password = (lambda value=os.getenv("TCP_ELASTIC_PASSWORD"): '
             '(lambda copied=value: copied)())()\n', False),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(bool(hardcoded_password_literal_lines(source)), expected)
        self.assertTrue(hardcoded_auth_tuple_lines(
            'password = (lambda value="hardcoded-secret": '
            '(lambda copied=value: copied)())()\n'
            'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        ))

    def test_chained_returned_lambda_immediate_invocations(self):
        """A returned callable runs only at the subsequent call site."""
        cases = (
            ('password = (lambda value="hardcoded-secret": '
             '(lambda copied=value: copied))()()\n', True),
            ('password = (lambda value="hardcoded-secret": '
             '(lambda: value))()()\n', True),
            ('password = (lambda value="hardcoded-secret": '
             '(lambda copied=value: copied))()\n', False),
            ('password = (lambda value="hardcoded-secret": '
             '(lambda copied=None: copied))()()\n', False),
            ('password = (lambda value=os.getenv("TCP_ELASTIC_PASSWORD"): '
             '(lambda copied=value: copied))()()\n', False),
            ('secret = "hardcoded-secret"\n'
             'factory = lambda value=secret: (lambda copied=value: copied)\n'
             'secret = None\npassword = factory()()\n', True),
            ('secret = None\n'
             'factory = lambda value=secret: (lambda copied=value: copied)\n'
             'secret = "hardcoded-secret"\npassword = factory()()\n', False),
            ('def factory(value="hardcoded-secret"):\n'
             '    return lambda copied=value: copied\n'
             'password = factory()()\n', True),
            ('password = (lambda value="hardcoded-secret": '
             '(lambda copied=value: (lambda final=copied: final)))()()()\n', True),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(bool(hardcoded_password_literal_lines(source)), expected)
        self.assertTrue(hardcoded_auth_tuple_lines(
            'password = (lambda value="hardcoded-secret": '
            '(lambda copied=value: copied))()()\n'
            'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
        ))

    def test_wildcard_bound_generator_method_aliases(self):
        """Source-ordered bound-method aliases preserve generator resume sites."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            generator = 'def run():\n    yield 1\n    ' + auth + '\n'
            cases = (
                ('advance = gen.__next__\nadvance()\nadvance()\npassword = None\n', True),
                ('advance = gen.__next__\nadvance()\npassword = None\nadvance()\n', False),
                ('advance = gen.__next__\nalias = advance\nalias()\nalias()\npassword = None\n', True),
                ('advance = gen.send\nadvance(None)\nadvance(7)\npassword = None\n', True),
                ('advance = gen.send\nadvance(None)\npassword = None\nadvance(7)\n', False),
                ('advance = gen.__next__\nadvance = lambda: None\n'
                 'advance()\npassword = None\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for suffix, expected in cases:
                    with self.subTest(suffix=suffix):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + generator
                            + 'gen = run()\n' + suffix,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_bound_generator_reaching_method_branches(self):
        """One call must never count two mutually exclusive bound methods."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            cases = (
                ('def run():\n    ' + auth + '\n    yield 1\n',
                 'advance = gen.send\nif flag:\n    advance = gen.__next__\n'
                 'advance()\npassword = None\n', True),
                ('def run():\n    yield 1\n    ' + auth + '\n',
                 'advance = gen.send\nif flag:\n    advance = gen.__next__\n'
                 'advance()\npassword = None\n', False),
                ('def run():\n    yield 1\n    ' + auth + '\n',
                 'advance = gen.send\nif flag:\n    advance = gen.__next__\n'
                 'advance()\nadvance()\npassword = None\n', True),
                ('def run():\n    ' + auth + '\n    yield 1\n',
                 'advance = gen.send\nif True:\n    advance = lambda: None\n'
                 'advance()\npassword = None\n', False),
                ('def run():\n    ' + auth + '\n    yield 1\n',
                 'advance = gen.__next__\nalias = advance\n'
                 'advance = gen.send\nalias()\npassword = None\n', True),
                ('def run():\n    ' + auth + '\n    yield 1\n',
                 'advance = gen.__next__\nif False:\n'
                 '    advance = gen.send\nadvance()\npassword = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for definition, suffix, expected in cases:
                    with self.subTest(suffix=suffix):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n'
                            + definition + 'gen = run()\n' + suffix,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_async_generator_anext_awaitable_timing(self):
        """Aliased __anext__ creation is inert until a legal await."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            generator = (
                'async def run():\n    ' + auth + '\n    yield 1\n'
                'gen = run()\nadvance = gen.__anext__\n'
            )
            cases = (
                ('pending = advance()\npassword = None\n', False),
                ('pending = advance()\npassword = None\n'
                 'async def consume():\n    await pending\n'
                 'import asyncio\nasyncio.run(consume())\n', False),
                ('pending = advance()\nasync def consume():\n'
                 '    await pending\nimport asyncio\n'
                 'asyncio.run(consume())\npassword = None\n', True),
                ('async def consume():\n    await advance()\n'
                 'import asyncio\nasyncio.run(consume())\n'
                 'password = None\n', True),
                ('pending = advance()\nasync def consume():\n'
                 '    return 1\nimport asyncio\n'
                 'asyncio.run(consume())\npassword = None\n', False),
                ('async def consume():\n    await anext(gen)\n'
                 'import asyncio\nasyncio.run(consume())\n'
                 'password = None\n', True),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for suffix, expected in cases:
                    with self.subTest(suffix=suffix):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n'
                            + generator + suffix, encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_generator_match_arm_aliases(self):
        """Bound method decisions are correlated across match/case arms."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            cases = (
                ('advance = gen.__next__\nmatch choice:\n'
                 '    case 0:\n        advance = gen.send\n'
                 '    case 1:\n        advance = gen.__next__\n'
                 'advance()\npassword = None\n', True),
                ('advance = gen.send\nmatch choice:\n'
                 '    case 0:\n        advance = gen.__next__\n'
                 '    case _:\n        advance = gen.send\n'
                 'advance()\npassword = None\n', True),
                ('advance = gen.send\nmatch choice:\n'
                 '    case 0:\n        advance = gen.__next__\n'
                 'advance()\npassword = None\n', True),
                ('advance = gen.send\nmatch choice:\n'
                 '    case 0:\n        advance = gen.send\n'
                 '    case _:\n        advance = lambda: None\n'
                 'advance()\npassword = None\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n'
                            'def run():\n    ' + auth + '\n    yield 1\n'
                            'gen = run()\n' + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_async_anext_wrappers_and_single_use(self):
        """Await wrappers consume inputs; reawaiting an object cannot resume."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))'
            generator = (
                'async def run():\n    yield 1\n    ' + auth + '\n'
                'gen = run()\nimport asyncio\n'
            )
            cases = (
                ('async def consume():\n    await asyncio.gather(anext(gen))\n'
                 '    await anext(gen)\n'
                 'asyncio.run(consume())\npassword = None\n', True),
                ('pending = anext(gen)\nasync def consume():\n'
                 '    await asyncio.shield(pending)\n'
                 '    await anext(gen)\n'
                 'asyncio.run(consume())\npassword = None\n', True),
                ('pending = anext(gen)\nasync def consume():\n'
                 '    await pending\n    try:\n        await pending\n'
                 '    except RuntimeError:\n        pass\n'
                 'asyncio.run(consume())\npassword = None\n', False),
                ('pending = anext(gen)\nasync def consume():\n'
                 '    await pending\n    try:\n        await pending\n'
                 '    except RuntimeError:\n        pass\n'
                 '    await anext(gen)\n'
                 'asyncio.run(consume())\npassword = None\n', True),
                ('pending = anext(gen)\nasync def consume():\n'
                 '    await asyncio.shield(pending)\n'
                 'password = None\nasyncio.run(consume())\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for source, expected in cases:
                    with self.subTest(source=source):
                        consumer.write_text(
                            'from elasticsearch import Elasticsearch\n'
                            'from provider_b import *\n' + generator + source,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_if_header_truthy_short_circuit(self):
        """The selected arm proves which short-circuit walruses ran."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            auth = 'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
            env = 'os.environ["TCP_ELASTIC_PASSWORD"]'
            cases = (
                ('if enabled and (password := ' + env + '):\n'
                 '    ' + auth, False),
                ('if enabled or (password := ' + env + '):\n'
                 '    ' + auth, True),
                ('if enabled or (password := ' + env + '):\n'
                 '    pass\nelse:\n    ' + auth, False),
                ('if not (enabled and (password := ' + env + ')):\n'
                 '    ' + auth, True),
                ('if enabled and (password := password.strip()):\n'
                 '    ' + auth, True),
                ('if (enabled and (password := ' + env + ')) and other:\n'
                 '    ' + auth, False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for code, expected in cases:
                    with self.subTest(code=code):
                        consumer.write_text(
                            'import os\n'
                            'from provider_b import *\n'
                            'from elasticsearch import Elasticsearch\n' + code,
                            encoding="utf-8",
                        )
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

    def test_wildcard_nested_guaranteed_overwrites(self):
        """Guaranteed module-scope branch stores shadow a wildcard credential."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / "es_consumer.py"
            provider = root / "provider_b.py"
            provider.write_text('password = "hardcoded-secret"\n', encoding="utf-8")
            prefix = 'from provider_b import *\n'
            suffix = (
                'from elasticsearch import Elasticsearch\n'
                'Elasticsearch("localhost", basic_auth=("elastic", password))\n'
            )
            cases = (
                ('if True:\n    password = None\n', False),
                ('if False:\n    password = None\n', True),
                ('if False:\n    password = 1\nelse:\n    password = None\n', False),
                ('if True:\n    if True:\n        password = None\n', False),
                ('if flag:\n    password = None\n', True),
                ('if flag:\n    password = None\nelse:\n    password = 0\n', False),
                ('if True:\n    password = password.strip()\n', True),
                ('if True:\n    password = None\npassword = password\n', False),
                ('if True:\n    password = None\npassword = "safe"\n', False),
            )
            with patch.dict(globals(), {
                "REPOSITORY_ROOT": root,
                "ES_RUNTIME_DISCOVERY_ROOTS": (root,),
                "RUNTIME_ES_MODULES": (),
            }):
                for code, expected in cases:
                    with self.subTest(code=code):
                        consumer.write_text(prefix + code + suffix, encoding="utf-8")
                        self.assertEqual(
                            provider.resolve() in self._runtime_es_module_paths(),
                            expected,
                        )

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

    def test_authorization_setitem_mutation_is_guarded(self):
        for source, expected in (
            ('headers.__setitem__("Authorization", "Bearer hardcoded-token")', [1]),
            ('headers.__setitem__("AUTHORIZATION", "Bearer hardcoded-token")', [1]),
            ('KEY = "Authorization"\nheaders.__setitem__(KEY, "Bearer hardcoded-token")', [2]),
            ('headers.__setitem__("Authorization", runtime_token)', []),
            ('headers.__setitem__("X-Trace", "Bearer hardcoded-token")', []),
        ):
            with self.subTest(source=source):
                self.assertEqual(hardcoded_authorization_header_lines(source), expected)

    def test_ambiguous_alias_repeated_write_overrides_its_own_callback(self):
        scanners = (
            (hardcoded_password_literal_lines, "password", "hardcoded-secret"),
            (hardcoded_single_auth_lines, "api_key", "hardcoded-api-key"),
            (hardcoded_authorization_header_lines, "Authorization", "Bearer hardcoded-token"),
        )
        for scanner, rebound, secret in scanners:
            dangerous = (
                'headers.setdefault(KEY, "' + secret + '")'
                if rebound == "Authorization"
                else 'options.__setitem__(KEY, "' + secret + '")'
            )
            for use_update in (True, False):
                initial = (
                    '        source.update({"exported": lambda: ' + dangerous + '})\n'
                    if use_update else
                    '        source["exported"] = lambda: ' + dangerous + '\n'
                )
                safe = (
                    'KEY = "username"\n'
                    'def configure(flag, left_side=False):\n'
                    '    global KEY\n'
                    '    if flag:\n'
                    '        left = {}\n'
                    '        right = {}\n'
                    '        if left_side:\n'
                    '            source = left\n'
                    '        else:\n'
                    '            source = right\n'
                    + initial
                    + '        source["exported"] = lambda: None\n'
                    '        return source["exported"]\n'
                    '    else:\n'
                    '        KEY = "' + rebound + '"\n'
                    'saved = configure(True, True)\n'
                    'configure(False)\n'
                    'saved()'
                )
                changed = safe.replace(
                    '        source["exported"] = lambda: None\n',
                    '        original = source\n'
                    '        source = right\n'
                    '        source["exported"] = lambda: None\n',
                ).replace(
                    'return source["exported"]',
                    'return original["exported"]',
                )
                with self.subTest(scanner=scanner.__name__, update=use_update):
                    self.assertEqual(scanner(safe), [])
                    # A reassignment between the two writes changes which
                    # dictionary is modified, so suppression would be unsafe.
                    self.assertEqual(scanner(changed), [11])
    def test_authorization_method_aliases_are_not_missed(self):
        cases = (
            ('put = headers.__setitem__\nput("Authorization", "Bearer hardcoded-token")', [2]),
            ('put = headers.__setitem__\nwriter = put\nwriter("Authorization", "Bearer hardcoded-token")', [3]),
            ('put = headers.setdefault\nput("AUTHORIZATION", "Bearer hardcoded-token")', [2]),
            ('put = headers.update\nput({"Authorization": "Bearer hardcoded-token"})', [2]),
            ('put = headers.__setitem__\nput("Authorization", runtime_token)', []),
            ('put = headers.__setitem__\nput("X-Trace", "Bearer hardcoded-token")', []),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(hardcoded_authorization_header_lines(source), expected)

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
                if path in runtime_es_modules:
                    for line_number in getattr(
                        self, "_es_wrapper_credential_lines", {}
                    ).get(path, ()):
                        violations.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:"
                            f"{line_number}:wrapper-auth-literal"
                        )
                    for line_number in self._module_uppercase_credential_literals(
                        text, getattr(self, "_imported_credential_exports", {}).get(path, ()),
                        selected_class_members=getattr(
                            self, "_imported_credential_class_members", {}
                        ).get(path, {}),
                    ):
                        violations.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:imported-credential-literal"
                        )
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
