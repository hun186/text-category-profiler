"""BL-001 dependency-free AST evidence for three known duplicate provider families.

Path ownership is not proof that a canonical module is a safe drop-in runtime
replacement for stage-local code. No target module is imported or executed.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

if __package__ in (None, ""):
    from bl001_legacy_root_audit import ROOT, tracked_sources
else:
    from scripts.bl001_legacy_root_audit import ROOT, tracked_sources


FAMILIES = {
    "df_utils": (
        "text_category_profiler/data/df_utils.py",
        "DatasetConverter/df_utils.py",
        "BertScript/df_utils.py",
    ),
    "MP_utils": (
        "text_category_profiler/concurrency/MP_utils.py",
        "DatasetConverter/old_MP_utils.py",
        "BertScript/MP_utils.py",
    ),
    "utilities": (
        "text_category_profiler/core/utilities.py",
        "DatasetConverter/old_utilities.py",
        "BertScript/utilities.py",
    ),
}
LIMITATIONS = [
    "Compared exact source bytes, top-level public definitions and AST syntax, not runtime behavior.",
    "The first path of each family is a structural package owner, not a verified drop-in replacement.",
    "Only explicit in-repository Python AST imports are recorded; dynamic/non-Python/external callers are not verified.",
    "Import graph edges do not establish which call sites execute or which provider sys.path resolves.",
    "No model, GPU, SQL, ES, filesystem mutation, GUI or WorkPool acceptance performed.",
]


def _public_definitions(tree):
    return {
        node.name: ast.dump(node, annotate_fields=True, include_attributes=False)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    }


def _source_imports(source, targets):
    """Bounded explicit import syntax only, not a dynamic/runtime call graph."""
    tree = ast.parse(source)
    matches = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            base = node.module or ""
            names = [base] + [base + "." + a.name for a in node.names]
        else:
            continue
        matches.update(name for name in names if name in targets)
    return matches


def audit(root=ROOT, sources=None):
    root = Path(root)
    if sources is None:
        sources = tracked_sources(root)
    if len(set(sources)) != len(sources):
        raise AssertionError("Duplicate paths in first-party source inventory")
    result = []
    module_names = {
        path[:-3].replace("/", "."): (family, path)
        for family, paths in FAMILIES.items() for path in paths
    }
    caller_map = {name: set() for name in module_names}
    source_errors = []
    for path in sources:
        source_path = root / path
        if not source_path.is_file():
            raise AssertionError(f"First-party caller source missing: {path}")
        try:
            imports = _source_imports(source_path.read_text(encoding="utf-8-sig"), module_names)
        except (SyntaxError, UnicodeError, ValueError) as exc:
            source_errors.append({"path": path, "error": type(exc).__name__})
            continue
        for name in imports:
            caller_map[name].add(path)
    if source_errors:
        raise AssertionError(f"First-party caller syntax errors: {source_errors}")

    for family, paths in FAMILIES.items():
        versions = []
        definitions = []
        for index, path in enumerate(paths):
            source_path = root / path
            if not source_path.is_file():
                raise AssertionError(f"Duplicate provider source missing: {path}")
            raw = source_path.read_bytes()
            try:
                parsed = ast.parse(raw.decode("utf-8-sig"), filename=path)
            except (SyntaxError, UnicodeError, ValueError) as exc:
                raise AssertionError(f"Duplicate provider cannot parse: {path}") from exc
            defs = _public_definitions(parsed)
            definitions.append(defs)
            module = path[:-3].replace("/", ".")
            versions.append({
                "path": path,
                "role": "package_domain_owner" if index == 0 else "stage_local_provider",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "byte_length": len(raw),
                "public_definitions": sorted(defs),
                "explicit_first_party_import_sources": sorted(caller_map[module]),
                "runtime_authority_verified": False,
            })
        common = set.intersection(*(set(d) for d in definitions))
        identical = {
            name for name in common
            if len({d[name] for d in definitions}) == 1
        }
        result.append({
            "family": family,
            "versions": versions,
            "common_public_definitions": sorted(common),
            "all_versions_ast_identical_definitions": sorted(identical),
            "all_versions_ast_different_definitions": sorted(common - identical),
            "unique_public_definitions_by_path": {
                path: sorted(set(defs) - set().union(*(
                    set(other) for j, other in enumerate(definitions) if j != i
                )))
                for i, (path, defs) in enumerate(zip(paths, definitions))
            },
            "source_bytes_all_identical": len({v["sha256"] for v in versions}) == 1,
            "safe_to_consolidate": False,
        })
    return {
        "schema_version": 1,
        "scope": "three explicitly registered duplicate source families",
        "limitations": LIMITATIONS,
        "first_party_caller_sources_scanned": len(sources),
        "family_count": len(result),
        "provider_count": sum(len(x["versions"]) for x in result),
        "runtime_verified": False,
        "external_callers_verified": False,
        "families": result,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"BL-001 duplicate provider audit: {report['family_count']} families, "
        f"{report['provider_count']} paths, "
        f"{report['first_party_caller_sources_scanned']} AST-scanned callers; "
        "no runtime or external caller proof."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
