"""BL-001 tracked-package structural census, with no optional imports.

This enforces an explicit location owner for every Git-tracked file under
text_category_profiler. It does NOT prove runtime use, absence of dynamic
callers, or that a module is genuinely cross-stage shared.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

# Keep the script directly executable without mutating sys.path or cwd.
if __package__ in (None, ""):
    from bl001_legacy_root_audit import load_catalog
else:
    from scripts.bl001_legacy_root_audit import load_catalog

ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP_PATH = "experiments/fixtures/bl001_package_ownership.json"
DOMAINS = frozenset({
    "cli", "concurrency", "core", "data", "diagnostics", "execution",
    "filesystem", "integrations", "pipeline", "text", "visualization",
})
KINDS = frozenset({"domain_module", "package_initializer", "domain_document"})
LIMITATIONS = [
    "This is structural ownership of Git-tracked files, not a complete active-call graph.",
    "Domain-owned paths are not proof of cross-stage usage or correct runtime behavior.",
    "External, dynamic, generated, untracked and manual callers have not been verified.",
    "Dependency-light test results do not validate models, GPU, Elasticsearch, SQL or WorkPool.",
]


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def tracked_package_files(root=ROOT):
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "text_category_profiler/"],
        cwd=root, check=True, capture_output=True, timeout=30,
    )
    return {
        os.fsdecode(name) for name in result.stdout.split(b"\0") if name
    }


def load_ownership(root=ROOT):
    raw = json.loads(
        (Path(root) / OWNERSHIP_PATH).read_text(encoding="utf-8")
    )
    if raw.get("schema_version") != 1:
        raise AssertionError("Unexpected canonical ownership schema")
    return raw["entries"]


def _valid_relative_path(path):
    if not isinstance(path, str) or not path.startswith("text_category_profiler/"):
        return False
    parts = PurePosixPath(path).parts
    return ".." not in parts and "\\" not in path and len(parts) >= 2


def verify_catalogs(tracked, root=ROOT):
    canonical = load_ownership(root)
    legacy = load_catalog(root)
    canonical_paths = {x["path"] for x in canonical}
    legacy_paths = {x["path"] for x in legacy}
    if len(canonical_paths) != len(canonical) or len(legacy_paths) != len(legacy):
        raise AssertionError("Duplicate package ownership paths")
    if canonical_paths & legacy_paths:
        raise AssertionError("Canonical and legacy inventories overlap")
    invalid = []
    for item in canonical:
        path = item.get("path")
        parts = PurePosixPath(path).parts if isinstance(path, str) else ()
        domain = parts[1] if len(parts) >= 3 else None
        name = parts[-1] if parts else None
        suffix = Path(name).suffix if name else None
        if (not _valid_relative_path(path) or len(parts) != 3
                or domain not in DOMAINS or item.get("domain") != domain
                or item.get("kind") not in KINDS
                or (item["kind"] == "domain_document") != (suffix == ".md")
                or (item["kind"] == "package_initializer") != (name == "__init__.py")
                or suffix not in {".py", ".md"}):
            invalid.append(path)
    for item in legacy:
        if not _valid_relative_path(item["path"]):
            invalid.append(item["path"])
    missing = sorted((canonical_paths | legacy_paths) - tracked)
    unknown = sorted(tracked - canonical_paths - legacy_paths)
    if unknown:
        raise AssertionError("Tracked package paths not classified: " + repr(unknown))
    return canonical, legacy, sorted(invalid), missing


def audit_package(root=ROOT):
    root = Path(root)
    tracked = tracked_package_files(root)
    try:
        canonical, legacy, invalid, missing = verify_catalogs(tracked, root)
        unclassified = []
    except AssertionError as error:
        # CLI should emit meaningful evidence for unknown paths before failing;
        # inputs are still checked for duplicates/invalid ownership above.
        if "not classified:" not in str(error):
            raise
        canonical = load_ownership(root)
        legacy = load_catalog(root)
        paths = {x["path"] for x in canonical} | {x["path"] for x in legacy}
        unclassified = sorted(tracked - paths)
        invalid = []
        missing = sorted(paths - tracked)
    owners = {
        x["path"]: ("canonical", x["kind"], x["domain"])
        for x in canonical
    }
    owners.update({
        x["path"]: ("legacy", "legacy_" + x["category"], None)
        for x in legacy
    })
    legacy_by_path = {x["path"]: x for x in legacy}
    rows, identity_failures = [], []
    for path in sorted(tracked):
        content = (root / path).read_bytes()
        digest = git_blob_sha(content)
        legacy_item = legacy_by_path.get(path)
        if legacy_item is not None and (
            digest != legacy_item["sha"] or len(content) != legacy_item["size_bytes"]
            or not (root / legacy_item["canonical_path"]).is_file()
        ):
            identity_failures.append(path)
        group, kind, domain = owners.get(path, ("unclassified", "unclassified", None))
        rows.append({
            "path": path, "classification": kind, "domain": domain,
            "sha": digest, "size_bytes": len(content),
            "ownership": group,
        })
    summary = Counter(x["ownership"] for x in rows)
    return {
        "schema_version": 1,
        "scope": "Git-tracked package files only; structural/path owner classification",
        "limitations": LIMITATIONS,
        "full_runtime_verified": False,
        "external_callers_verified": False,
        "summary": {
            "total_tracked_package_files": len(rows),
            "canonical_domain_owned": summary["canonical"],
            "legacy_preserved": summary["legacy"],
            "unclassified": summary["unclassified"],
        },
        "unclassified_paths": unclassified,
        "catalogue_paths_missing": missing,
        "invalid_catalog_entries": invalid,
        "identity_failures": identity_failures,
        "files": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit_package()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "BL-001 tracked package structural census: %d files; "
        "%d domain-owned; %d legacy preserved; %d unclassified. "
        "External/dynamic callers and full runtime remain unverified."
        % (
            report["summary"]["total_tracked_package_files"],
            report["summary"]["canonical_domain_owned"],
            report["summary"]["legacy_preserved"],
            report["summary"]["unclassified"],
        )
    )
    if (report["unclassified_paths"] or report["catalogue_paths_missing"]
            or report["invalid_catalog_entries"] or report["identity_failures"]):
        parser.error("Package structural census requires classification or identity repair")


if __name__ == "__main__":
    main()
