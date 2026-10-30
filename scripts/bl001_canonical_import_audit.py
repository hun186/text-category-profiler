"""Bounded BL-001 first-party AST import evidence for canonical domain modules.

The graph describes source import syntax, not verified execution or active call
sites. Dynamic import candidates and bare-name ambiguities are separate from
explicit qualified edges. No application modules or services are imported.
"""
import argparse
import ast
from collections import defaultdict
import json
from pathlib import Path

# Both python scripts/bl001_canonical_import_audit.py and module import work.
if __package__ in (None, ""):
    from bl001_legacy_root_audit import tracked_sources
    from bl001_package_census import ROOT, audit_package, load_ownership
else:
    from scripts.bl001_legacy_root_audit import tracked_sources
    from scripts.bl001_package_census import ROOT, audit_package, load_ownership


LIMITATIONS = [
    "Static AST imports are lexical evidence, not proof that code was executed.",
    "Stage classification is by source directory, not runtime dispatch.",
    "A module with no explicit scoped import may have dynamic, plugin, direct-script, external or other callers.",
    "Sources exclude tests, experiments, vendors, copied Dash examples and TRV_deploy, following the earlier bounded audit.",
    "Calls with computed import strings, non-Python launchers, source generated at runtime and outside-repository callers remain unverified.",
    "No model, GPU, SQL, Elasticsearch, WorkPool or UI acceptance performed.",
]


def canonical_modules(root=ROOT):
    entries = load_ownership(root)
    modules = {
        item["path"][:-3].replace("/", "."): item["path"]
        for item in entries if item["kind"] == "domain_module"
    }
    if len(modules) != len([x for x in entries if x["kind"] == "domain_module"]):
        raise AssertionError("Duplicate canonical module names")
    return modules


def source_area(path):
    if path == "TCFMain.py":
        return "root_composition"
    roots = {
        "TCF_Params": "root_configuration",
        "DatasetConverter": "dataset_converter_workspace",
        "BertScript": "bert_stage_workspace",
        "ClassesTree": "taxonomy_workspace",
        "text_category_profiler": "package_internal",
        "scripts": "maintenance_script",
    }
    return roots.get(path.split("/", 1)[0], "other_first_party")


def resolve_from(path, node):
    """Return absolute import base for qualified/relative AST ImportFrom."""
    if node.level == 0:
        return node.module or ""
    if not path.startswith("text_category_profiler/"):
        return None
    parts = path[:-3].split("/")[:-1]  # package of current source
    if node.level > len(parts):
        return None
    prefix = parts[: len(parts) - node.level + 1]
    suffix = node.module.split(".") if node.module else []
    return ".".join(prefix + suffix)


def scan_source(path, source, targets):
    """Return four separate evidence buckets; parse errors are explicit."""
    qualified, dynamic, bare, unresolved_from = [], [], [], []
    basename_targets = defaultdict(list)
    for module in targets:
        basename_targets[module.rsplit(".", 1)[-1]].append(module)
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError) as exc:
        return qualified, dynamic, bare, unresolved_from, type(exc).__name__

    def evidence(node, module, kind):
        return {
            "source": path, "area": source_area(path),
            "line": node.lineno, "target_module": module, "evidence": kind,
        }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in targets:
                    qualified.append(evidence(node, alias.name, "qualified_import"))
                elif "." not in alias.name and alias.name in basename_targets:
                    bare.append({
                        "source": path, "area": source_area(path),
                        "line": node.lineno, "bare_name": alias.name,
                        "possible_targets": sorted(basename_targets[alias.name]),
                        "evidence": "unresolved_bare_import",
                    })
        elif isinstance(node, ast.ImportFrom):
            base = resolve_from(path, node)
            if base is None:
                unresolved_from.append({
                    "source": path, "line": node.lineno, "reason": "relative_outside_package",
                })
                continue
            if base in targets:
                qualified.append(evidence(node, base, "from_module"))
            for alias in node.names:
                if alias.name != "*":
                    candidate = base + "." + alias.name if base else alias.name
                    if candidate in targets:
                        qualified.append(evidence(node, candidate, "from_package"))
            if node.level == 0 and base in basename_targets:
                bare.append({
                    "source": path, "area": source_area(path),
                    "line": node.lineno, "bare_name": base,
                    "possible_targets": sorted(basename_targets[base]),
                    "evidence": "unresolved_bare_import",
                })
        elif isinstance(node, ast.Call):
            fn = node.func
            name = (
                fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute)
                and isinstance(fn.value, ast.Name)
                and fn.value.id in {"importlib", "runpy"} else None
            )
            if name not in {"import_module", "__import__", "run_module"}:
                continue
            if not node.args:
                continue
            value = node.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if value.value in targets:
                    dynamic.append(evidence(node, value.value, "dynamic_import_string_candidate"))
    # Deduplicate repeated representation, preserving separate evidence types.
    qualified = sorted({
        (x["source"], x["line"], x["target_module"], x["evidence"]): x
        for x in qualified
    }.values(), key=lambda x: (x["source"], x["line"], x["target_module"], x["evidence"]))
    dynamic.sort(key=lambda x: (x["source"], x["line"], x["target_module"]))
    bare.sort(key=lambda x: (x["source"], x["line"], x["bare_name"]))
    return qualified, dynamic, bare, unresolved_from, None


def audit(root=ROOT, sources=None):
    root = Path(root)
    structural = audit_package(root)
    if any(structural[key] for key in (
        "unclassified_paths", "catalogue_paths_missing",
        "invalid_catalog_entries", "identity_failures",
    )):
        raise AssertionError("Package structural census must pass before import audit")
    targets = canonical_modules(root)
    selected = tracked_sources(root) if sources is None else sources
    qualified, dynamic, bare, unresolved, parse_errors = [], [], [], [], []
    for path in selected:
        data = (root / path).read_text(encoding="utf-8", errors="replace")
        q, d, b, u, error = scan_source(path, data, targets)
        qualified.extend(q)
        dynamic.extend(d)
        bare.extend(b)
        unresolved.extend(u)
        if error:
            parse_errors.append({"source": path, "error_type": error})
    by_module = defaultdict(list)
    for edge in qualified:
        by_module[edge["target_module"]].append(edge)
    module_rows = []
    for module, path in sorted(targets.items()):
        edges = by_module[module]
        areas = sorted({e["area"] for e in edges if e["area"] != "package_internal"})
        module_rows.append({
            "module": module,
            "path": path,
            "domain": path.split("/")[1],
            "qualified_import_occurrences": len(edges),
            "first_party_nonpackage_areas": areas,
            "has_explicit_scoped_qualified_import": bool(edges),
            "status": (
                "explicit_import_syntax_observed" if edges
                else "no_scoped_explicit_import_observed"
            ),
        })
    return {
        "schema_version": 1,
        "scope": "Git tracked first-party Python AST, with excluded boundaries",
        "limitations": LIMITATIONS,
        "runtime_verified": False,
        "external_callers_verified": False,
        "summary": {
            "scanned_python_sources": len(selected),
            "canonical_modules": len(targets),
            "qualified_import_occurrences": len(qualified),
            "modules_with_explicit_import_syntax": sum(bool(by_module[m]) for m in targets),
            "modules_without_scoped_import_syntax": sum(not by_module[m] for m in targets),
            "dynamic_import_string_candidates": len(dynamic),
            "unresolved_bare_imports": len(bare),
            "parse_errors": len(parse_errors),
        },
        "module_evidence": module_rows,
        "qualified_imports": qualified,
        "dynamic_import_candidates": dynamic,
        "unresolved_bare_import_candidates": bare,
        "unresolved_relative_imports": unresolved,
        "parse_errors": parse_errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    counts = result["summary"]
    print(
        "BL-001 canonical import evidence: %d first-party Python files, "
        "%d canonical modules, %d qualified import syntax occurrences; "
        "%d no scoped qualified import, %d dynamic candidates, "
        "%d unresolved bare imports, %d parse errors. No live/runtime proof."
        % (
            counts["scanned_python_sources"], counts["canonical_modules"],
            counts["qualified_import_occurrences"],
            counts["modules_without_scoped_import_syntax"],
            counts["dynamic_import_string_candidates"],
            counts["unresolved_bare_imports"], counts["parse_errors"],
        )
    )
    if result["parse_errors"]:
        parser.error("Source parse errors require investigation before relying on audit")


if __name__ == "__main__":
    main()
