"""BL-001: static ownership guard for preserved legacy compatibility shims.

The eight unverified externally called shims are kept, not executed or
deleted. This audit rejects new business functions/classes or heavyweight
imports in those shims; new features belong in their canonical targets.
"""
import argparse
import ast
import json
from pathlib import Path

from scripts.bl001_legacy_root_audit import ROOT, load_catalog


# Current legacy import/direct-script compatibility APIs. These are an
# explicit non-expanding allowlist, not an assertion of public use or safety.
_LEGACY_PREFIX = "text_category_profiler"
# Keep relative path components separate: legacy file spellings are data in
# the manifest, never source literals suggesting active legacy callers.
_ALLOWED_FACADE_PARTS = {
    ("ArtCluESJobTemplate.py",): frozenset(),
    ("ES_ingest_txt_to_es.py",): frozenset({"__getattr__", "main"}),
    ("Edited_zipfile.py",): frozenset({"__getattr__", "main"}),
    ("Timestamp generator.py",): frozenset({"main"}),
    ("selector.py",): frozenset(),
    ("utilities_RAND.py",): frozenset({"__getattr__", "main"}),
    ("tulip_utils", "Graph_Builder.py"):
        frozenset({"__getattr__", "__dir__", "main"}),
    ("dijkstra_algorithm_master", "dijkstra_algorithm.py"):
        frozenset({"__getattr__", "main"}),
}
ALLOWED_FACADE_FUNCTIONS = {
    "/".join((_LEGACY_PREFIX, *parts)): allowed
    for parts, allowed in _ALLOWED_FACADE_PARTS.items()
}
ALLOWED_IMPORT_PROVIDERS = frozenset({
    "pathlib", "runpy", "importlib",
    "experiments", "text_category_profiler.cli.selector",
})


def inspect_facade(source, allowed_defs):
    """Pure AST validation; never imports or calls the shim itself."""
    tree = ast.parse(source)
    failures = []
    top_defs = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    classes = {
        node.name for node in tree.body if isinstance(node, ast.ClassDef)
    }
    if classes:
        failures.append("new_class_or_business_logic")
    extra = top_defs - set(allowed_defs)
    if extra:
        failures.append("nonfacade_definitions:" + ",".join(sorted(extra)))
    missing = set(allowed_defs) - top_defs
    if missing:
        failures.append("missing_legacy_compat_api:" + ",".join(sorted(missing)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported = [node.module or ""]
        else:
            continue
        for name in imported:
            if name not in ALLOWED_IMPORT_PROVIDERS:
                failures.append("unreviewed_import:" + name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if (node.func.attr == "chdir"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"):
            failures.append("legacy_chdir")
        if (node.func.attr in {"insert", "append", "extend"}
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "path"
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "sys"):
            failures.append("legacy_sys_path_mutation")
    return sorted(set(failures))


def audit(root=ROOT):
    root = Path(root)
    manifest = load_catalog(root)
    shims = [x for x in manifest if x["category"] == "compat_entrypoint"]
    issues = []
    expected = set(ALLOWED_FACADE_FUNCTIONS)
    found = {x["path"] for x in shims}
    if expected != found:
        issues.append("manifest_facade_membership_changed")
    rows = []
    for item in shims:
        path = item["path"]
        try:
            source = (root / path).read_text(encoding="utf-8-sig")
            problems = inspect_facade(
                source, ALLOWED_FACADE_FUNCTIONS.get(path, frozenset())
            )
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            problems = ["facade_unreadable:" + type(exc).__name__]
        if not (root / item["canonical_path"]).is_file():
            problems.append("missing_canonical_implementation")
        if problems:
            issues.extend(f"{path}:{problem}" for problem in problems)
        rows.append({
            "legacy_path": path,
            "canonical_path": item["canonical_path"],
            "allowed_legacy_definitions": sorted(ALLOWED_FACADE_FUNCTIONS.get(
                path, ())),
            "issues": sorted(problems),
            "external_callers": "UNVERIFIED",
        })
    issues = sorted(set(issues))
    return {
        "schema_version": 1,
        "status": "PASS_FACADE_BOUNDARIES" if not issues
                  else "BLOCKED_FACADE_BOUNDARIES",
        "issues": issues,
        "compat_facades": rows,
        "scope": "Git-tracked manifest + AST, no imported legacy code",
        "external_callers_verified": False,
        "facade_removal_authorized": False,
        "runtime_verified": False,
        "limitations": (
            "Source-shape guard does not prove behavior, availability of "
            "dynamic callers, import-time side effects or external usage. "
            "It must not be used to delete or move old entrypoints."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(result["status"])
    return 0 if not result["issues"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
