"""Bounded, read-only audit of residual package-root legacy compatibility.

The emitted JSON is candidate evidence, not a complete dependency/call graph:
manual, external, generated and computed paths remain unknown. No legacy module
is imported and no data files are executed.
"""
import argparse
import ast
from collections import defaultdict
import json
import os
from pathlib import Path
import subprocess


if __package__ in (None, ""):
    from bl001_git_blob_identity import git_blob_sha as blob_sha
    from bl001_git_blob_identity import legacy_git_blob_bytes
else:
    from scripts.bl001_git_blob_identity import git_blob_sha as blob_sha
    from scripts.bl001_git_blob_identity import legacy_git_blob_bytes


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "experiments/fixtures/bl001_legacy_root_inventory.json"
SKIP_PREFIXES = (
    "BertScript/TRV_deploy/",
    "BertScript/Dash-by-Plotly-master/",
    "BertScript/dash-cytoscape-master/",
    "vendor/",
    "tests/",
    "experiments/",
)
SKIP_PARTS = {"vendor", "tests", "experiments", "__pycache__", ".venv", "node_modules"}
LIMITATIONS = [
    "Only tracked in-repository first-party Python sources were scanned.",
    "Historical deployment snapshots, vendor, tests and experiments were excluded.",
    "Only explicit AST imports, unresolved bare-import candidates, and string-literal filename/module hints are detected.",
    "String hints do not prove file I/O, execution, or a runtime dependency.",
    "Computed loader arguments are candidates only; target identity is unresolved and calls are not executed.",
    "Manual, external, generated, non-Python, dynamic imports and computed paths remain unverified.",
]


def load_catalog(root=ROOT):
    root = Path(root)
    raw = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    items = raw["entries"]
    assert len(items) == 13
    assert len({x["path"] for x in items}) == 13
    assert sum(x["category"] == "compat_entrypoint" for x in items) == 8
    assert sum(x["category"] == "legacy_vendor_asset" for x in items) == 4
    assert sum(x["category"] == "package_marker" for x in items) == 1
    assert all(x["external_callers"] == "unverified" for x in items)
    return items


def source_in_scope(name):
    if not name.endswith(".py") or name.startswith(SKIP_PREFIXES):
        return False
    return not any(part in SKIP_PARTS for part in Path(name).parts)


def tracked_sources(root=ROOT):
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"], cwd=root, check=True,
        capture_output=True, timeout=30,
    )
    return [
        os.fsdecode(chunk) for chunk in proc.stdout.split(b"\0")
        if chunk and source_in_scope(os.fsdecode(chunk))
        and (Path(root) / os.fsdecode(chunk)).is_file()
    ]


def target_module(path):
    return path[:-3].replace("/", ".") if path.endswith(".py") else None


def scan_source(source_path, source_text, catalog):
    """AST references and string hints, never a conjectured live call graph."""
    lines = source_text.splitlines()
    targets = [
        (x["path"], target_module(x["path"]))
        for x in catalog if x["category"] == "compat_entrypoint"
    ]
    bare_lookup = defaultdict(list)
    for path, module in targets:
        bare_lookup[Path(path).stem].append(path)
    refs, hints, bare_candidates, parse_error = [], [], [], None
    try:
        tree = ast.parse(source_text, filename=source_path)
    except (SyntaxError, ValueError) as exc:
        parse_error = type(exc).__name__
    else:
        for node in ast.walk(tree):
            imported = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported = [
                    (node.module + "." + alias.name) if node.module else alias.name
                    for alias in node.names
                ]
                if node.module:
                    imported.append(node.module)
            for name in imported:
                for path, module in targets:
                    if module == name:
                        refs.append({
                            "source": source_path, "line": node.lineno,
                            "module": module, "target": path,
                            "evidence": "ast_import",
                        })
            # A plain import such as 'from ArtCluESJobTemplate import ...'
            # may be a legacy script-path import. Do not pretend resolution
            # is certain: no import, sys.path or cwd is executed here.
            bare_names = []
            if isinstance(node, ast.Import):
                bare_names = [
                    alias.name for alias in node.names if "." not in alias.name
                ]
            elif (isinstance(node, ast.ImportFrom) and node.level == 0
                  and node.module and "." not in node.module):
                bare_names = [node.module]
            for name in bare_names:
                if name in bare_lookup:
                    bare_candidates.append({
                        "source": source_path, "line": node.lineno,
                        "name": name,
                        "candidate_targets": sorted(bare_lookup[name]),
                        "evidence": "unresolved_bare_import",
                    })
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for path, module in targets:
                    if path in node.value or (module and module in node.value):
                        hints.append({
                            "source": source_path, "line": getattr(node, "lineno", 0),
                            "target": path, "evidence": "ast_string_literal",
                        })
    # Broad bounded textual path hints catch comments and malformed source;
    # clearly distinguish them from AST module imports.
    for lineno, line in enumerate(lines, 1):
        for path, module in targets:
            if path in line and not any(
                x["target"] == path and x["line"] == lineno for x in hints
            ):
                hints.append({
                    "source": source_path, "line": lineno,
                    "target": path, "evidence": "text_or_comment",
                })
    refs = list({(x["source"], x["line"], x["target"]): x for x in refs}.values())
    refs.sort(key=lambda x: (x["source"], x["line"], x["target"]))
    hints.sort(key=lambda x: (x["source"], x["line"], x["target"]))
    bare_candidates.sort(key=lambda x: (x["source"], x["line"], x["name"]))
    return refs, hints, bare_candidates, parse_error


def scan_dynamic_loader_calls(source_path, source_text, catalog):
    """Find bounded loader-call *candidates*, never evaluate target objects.

    Direct known literal targets are evidence of an in-repo dynamic reference.
    Computed arguments are unresolved even when their source contains a
    legacy filename elsewhere; do not assert a target or execute the code.
    """
    try:
        tree = ast.parse(source_text, filename=source_path)
    except (SyntaxError, ValueError):
        return []
    candidates = {}
    for item in catalog:
        if item["category"] != "compat_entrypoint":
            continue
        path = item["path"]
        module = target_module(path)
        candidates[path] = path
        if module:
            candidates[module] = path
    evidence = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = node.func
        loader = None
        if isinstance(call, ast.Name) and call.id in (
                "__import__", "import_module", "run_module", "run_path"):
            loader = call.id
        elif (isinstance(call, ast.Attribute)
                and isinstance(call.value, ast.Name)
                and (call.value.id, call.attr) in {
                    ("importlib", "import_module"),
                    ("runpy", "run_module"), ("runpy", "run_path"),
                }):
            loader = call.value.id + "." + call.attr
        if loader is None:
            continue
        argument = node.args[0] if node.args else None
        if (isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)):
            # Path hint only: do not normalize away relative/absolute
            # semantics or pretend loader invocation has succeeded.
            literal = argument.value
            target = candidates.get(literal) or candidates.get(
                literal.replace("\\", "/")
            )
            if target is None:
                continue
            classification = "known_legacy_literal"
        else:
            target = None
            classification = "computed_or_missing_argument"
        evidence.append({
            "source": source_path,
            "line": node.lineno,
            "loader": loader,
            "classification": classification,
            "target": target,
            "evidence": "ast_loader_call_candidate",
        })
    return sorted(evidence, key=lambda row: (row["source"], row["line"],
                                              row["loader"], row["target"] or ""))


def audit(root=ROOT, source_paths=None):
    root = Path(root)
    catalog = load_catalog(root)
    source_paths = tracked_sources(root) if source_paths is None else source_paths
    imports, hints, bare_imports, errors = [], [], [], []
    dynamic_loader_callsites = []
    for source in source_paths:
        text = (root / source).read_text(encoding="utf-8", errors="replace")
        i, h, bare, error = scan_source(source, text, catalog)
        imports.extend(i)
        hints.extend(h)
        bare_imports.extend(bare)
        dynamic_loader_callsites.extend(
            scan_dynamic_loader_calls(source, text, catalog)
        )
        if error:
            errors.append({"source": source, "error_type": error})
    actual_root = sorted(
        str(p.relative_to(root).as_posix())
        for p in (root / "text_category_profiler").iterdir()
        if p.is_file()
    )
    expected_root = sorted(
        x["path"] for x in catalog
        if x["path"].count("/") == 1
    )
    preserved = []
    for item in catalog:
        path = root / item["path"]
        worktree = path.read_bytes()
        content = legacy_git_blob_bytes(
            worktree, item["sha"], item["size_bytes"]
        )
        preserved.append({
            "path": item["path"], "blob_matches_baseline": blob_sha(content) == item["sha"],
            "size_matches_baseline": len(content) == item["size_bytes"],
            "canonical_exists": (root / item["canonical_path"]).is_file(),
        })
    return {
        "schema_version": 1,
        "scope": "bounded tracked first-party Python AST + literal and root inventory",
        "limitations": LIMITATIONS,
        "tracked_python_files_scanned": len(source_paths),
        "catalogued_residual_entries": len(catalog),
        "root_files_match_catalog": actual_root == expected_root,
        "preservation": preserved,
        "ast_imports": sorted(imports, key=lambda x: (x["source"], x["line"], x["target"])),
        "unresolved_bare_import_candidates": sorted(
            bare_imports, key=lambda x: (x["source"], x["line"], x["name"])
        ),
        "string_reference_candidates": sorted(hints, key=lambda x: (x["source"], x["line"], x["target"])),
        "parse_errors": errors,
        "dynamic_loader_callsites": sorted(
            dynamic_loader_callsites,
            key=lambda row: (row["source"], row["line"],
                             row["loader"], row["target"] or ""),
        ),
        "dynamic_callsites_derived_only_from_ast": True,
        "external_dynamic_callers_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not data["root_files_match_catalog"] or not all(
        x["blob_matches_baseline"] and x["size_matches_baseline"] and x["canonical_exists"]
        for x in data["preservation"]
    ):
        parser.error("Legacy package-root inventory differs from reviewed baseline")
    print(
        "Audited %d tracked Python files, %d residual items, %d AST import edges, "
        "%d unresolved bare imports, %d literal/path hints and %d syntax parse errors. "
        "External and computed callers remain unverified."
        % (
            data["tracked_python_files_scanned"],
            data["catalogued_residual_entries"],
            len(data["ast_imports"]),
            len(data["unresolved_bare_import_candidates"]),
            len(data["string_reference_candidates"]),
            len(data["parse_errors"]),
        )
    )


if __name__ == "__main__":
    main()
