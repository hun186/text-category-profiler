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


def _reaching_values(candidates, use_node):
    """Return conservative reaching values for one binding at a use site."""
    use_path = _node_control_path(use_node)
    reaching = []

    for _position, value in candidates:
        value_path = _node_control_path(value)
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

    def add_binding(target, value, position):
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
        values.setdefault(binding_scope, {}).setdefault(target.id, []).append(
            (position, value)
        )

    binding_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
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

    environment_default = _environment_lookup_default_node(node)
    if environment_default is not None:
        return _hardcoded_password_values(
            environment_default,
            bindings,
            before_position,
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
                    before_position,
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
                    before_position,
                    seen_names,
                )
            )
        for keyword in node.keywords:
            values.extend(
                _hardcoded_password_values(
                    keyword.value,
                    bindings,
                    before_position,
                    seen_names,
                )
            )
        return values

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
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
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
                _node_position(value),
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
                    for line_number in hardcoded_single_auth_lines(text):
                        violations.append(
                            f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}:client-auth-literal"
                        )
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
