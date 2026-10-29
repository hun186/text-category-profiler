"""Conservative, reproducible in-repo *literal* research-file reference audit.

This is NOT a full call graph. Computed paths, imports outside this checkout,
and manual users cannot be ruled out by a no-match result.
"""
import argparse
import ast
from collections import defaultdict
import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
RESIDUAL = "experiments/fixtures/bl001_residual_inventory.json"
SIMILARITY = "experiments/fixtures/bl001_similarity_experiment_inventory.json"
SKIP_PREFIXES = (
    "BertScript/TRV_deploy/",
    "BertScript/Dash-by-Plotly-master/",
    "BertScript/dash-cytoscape-master/",
    "vendor/",
    "tests/",
    "experiments/",
    ".codex/",
)
SKIP_PARTS = {"tests", "experiments", "vendor", "__pycache__", ".venv", "node_modules"}
LIMITATIONS = [
    "Only tracked Python files in this checkout are scanned.",
    "Historical deployment snapshots, vendor, tests, and experiments are excluded.",
    "String and line matching is heuristic, not a verified runtime open()/call graph.",
    "Comments, examples, unreachable code, and duplicate basenames can produce candidates.",
    "Computed filenames, dynamic imports, non-Python scripts, external and manual callers are not proven absent.",
]


def load_catalog(root):
    residual = json.loads((root / RESIDUAL).read_text(encoding="utf-8"))
    similarity = json.loads((root / SIMILARITY).read_text(encoding="utf-8"))
    targets = []
    for item in residual["entries"]:
        old = item["path"]
        targets.append({
            "original_path": old,
            "current_path": item.get("relocated_path", old),
            "basename": Path(old).name,
        })
    for item in similarity["entries"]:
        targets.append({
            "original_path": item["path"],
            "current_path": item["path"],
            "basename": Path(item["path"]).name,
        })
    assert len(targets) == 39, "Unexpected bounded inventory size"
    assert len({x["original_path"] for x in targets}) == len(targets)
    return sorted(targets, key=lambda x: x["original_path"])


def first_party_python_path(name):
    """Exclude vendored/archived trees and nested test/experiment trees."""
    if not name.endswith(".py") or name.startswith(SKIP_PREFIXES):
        return False
    return not any(part in SKIP_PARTS for part in Path(name).parts)


def tracked_python_sources(root):
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=root, capture_output=True, check=True,
    )
    names = sorted(os.fsdecode(name) for name in result.stdout.split(b"\0") if name)
    return [
        name for name in names
        if first_party_python_path(name) and (root / name).is_file()
    ]


def scan_source(source_path, source_text, targets):
    """Return conservative candidates, plus whether AST analysis was possible."""
    source_lines = source_text.splitlines()
    string_literals_by_line = defaultdict(list)
    parse_error = None
    try:
        syntax = ast.parse(source_text, filename=source_path)
    except (SyntaxError, ValueError) as exc:
        parse_error = type(exc).__name__
    else:
        for node in ast.walk(syntax):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and hasattr(node, "lineno")):
                for line_no in range(node.lineno, getattr(node, "end_lineno", node.lineno) + 1):
                    string_literals_by_line[line_no].append(node.value)
    by_name = defaultdict(list)
    for item in targets:
        by_name[item["basename"]].append(item)
    matches = []
    for line_no, line in enumerate(source_lines, start=1):
        for name, candidates in by_name.items():
            if name not in line:
                continue
            referenced_paths = sorted(
                {path for item in candidates
                 for path in (item["original_path"], item["current_path"])
                 if path in line}
            )
            literal = any(name in s for s in string_literals_by_line[line_no])
            matches.append({
                "source": source_path,
                "line": line_no,
                "basename": name,
                "evidence": "ast_string_literal" if literal else "text_or_comment",
                "matching_full_paths": referenced_paths,
                "candidate_original_paths": sorted(
                    item["original_path"] for item in candidates
                ),
                "basename_ambiguous": len(candidates) > 1,
            })
    return matches, parse_error


def collect(root, source_paths=None):
    """Scan files without importing them or reading protected research contents."""
    root = Path(root)
    targets = load_catalog(root)
    sources = tracked_python_sources(root) if source_paths is None else source_paths
    hits, parse_errors = [], []
    for source in sources:
        content = (root / source).read_text(encoding="utf-8", errors="replace")
        rows, error = scan_source(source, content, targets)
        hits.extend(rows)
        if error is not None:
            parse_errors.append({"source": source, "error_type": error})
    hits.sort(key=lambda r: (r["source"], r["line"], r["basename"]))
    return {
        "schema_version": 1,
        "scope": "tracked first-party Python files only; static lexical candidates",
        "limitations": LIMITATIONS,
        "catalogued_artifacts": len(targets),
        "tracked_python_files_scanned": len(sources),
        "parse_errors": parse_errors,
        "candidate_matches": hits,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="JSON output path; file is intentionally generated, not committed")
    args = parser.parse_args()
    result = collect(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    ast_count = sum(hit["evidence"] == "ast_string_literal"
                    for hit in result["candidate_matches"])
    print(
        f"Scanned {result['tracked_python_files_scanned']} tracked Python files; "
        f"{result['catalogued_artifacts']} catalogued research files; "
        f"{len(result['candidate_matches'])} candidate references "
        f"({ast_count} AST string literals); "
        f"{len(result['parse_errors'])} source parse errors. "
        "Dynamic/external callers remain unverified."
    )


if __name__ == "__main__":
    main()
