"""BL-001 application structure gate: evidence, not deployment acceptance.

Reads tracked in-repository Python files and the existing package ownership
manifest. Never imports stage entrypoints, starts GUI/model/service processes,
or inspects a real WorkPool/SQLite/database.
"""
import argparse
import ast
import json
from pathlib import Path

from scripts.bl001_package_census import ROOT, audit_package


CONTRACTS = {
    "TCFMain.py": {
        "DataConvert", "RunClassfier", "CombineTestResult",
        "TestResultVis", "BackupAndClean", "ArticleAnalysis", "main",
    },
    "DatasetConverter/stage.py": {
        "StagePlan", "StageContext", "normalize_stage_plan",
        "activate_stage_context",
    },
    "BertScript/classifier_stage.py": {
        "ClassifierPlan", "activate_classifier", "run_classifier_stage",
    },
    "BertScript/result_combination_stage.py": {
        "ResultCombinationPlan", "activate_result_combination",
        "run_result_combination_stage",
    },
    "BertScript/visualization_stage.py": {
        "VisualizationPlan", "activate_visualization",
        "run_visualization_stage",
    },
    "BertScript/visualization_filter.py": {
        "to_string", "split_filter_part", "construct_filter",
        "df_upd_filter_query",
    },
    "BertScript/visualization_callback_state.py": {
        "is_spurious_datatable_filter_notification", "datatable_filter_state",
        "is_redundant_table_filter_event", "is_redundant_table_page_event",
        "restore_derived_query_state",
    },
    "BertScript/visualization_mission_selection.py": {"mission_colortable_rows"},
    "BertScript/visualization_pagination.py": {"select_table_page"},
    "text_category_profiler/pipeline/orchestrator.py": {
        "PipelineOrchestrator",
    },
    "text_category_profiler/pipeline/workpool.py": {
        "WorkPoolPlan", "WorkPoolManager", "DeliveryManager",
        "validate_external_work_id",
    },
    "text_category_profiler/pipeline/configuration.py": {
        "PipelinePlan", "PipelineContext", "LocalFileSystem",
        "normalize_weitech_input_base",
    },
    "text_category_profiler/filesystem/no_replace.py": {
        "_handoff_rename_noreplace",
    },
}

ROOT_STAGE_TIMING = {
    "DataConvert", "RunClassfier", "CombineTestResult",
    "TestResultVis", "ArticleAnalysis",
}

EXTERNAL_ACCEPTANCE = {
    "external_and_dynamic_callers": "UNVERIFIED",
    "real_windows_gui_filter_sort_pagination": "UNVERIFIED",
    "real_model_and_gpu": "UNVERIFIED",
    "live_workpool_and_network_filesystem": "UNVERIFIED",
    "production_sqlite_and_recovery": "UNVERIFIED",
}


def inspect_module(path, expected):
    """Check only authoritative public boundary symbols, never import a module."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
        return None, ["module_not_parseable:" + type(exc).__name__]
    available = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    return tree, ["missing_symbol:" + name for name in sorted(expected - available)]


STAGE4_POLICY_OWNERS = {
    "BertScript/visualization_callback_state.py": (
        "BertScript/visualization_stage.py", set(),
    ),
    "BertScript/visualization_mission_selection.py": (
        "BertScript/Test_result_Vis.py", {"ast"},
    ),
    "BertScript/visualization_pagination.py": (
        "BertScript/Test_result_Vis.py", set(),
    ),
}


def check_policy_owner(owner_tree, consumer_tree, module, names, allowed_imports):
    """Check bounded AST ownership and explicit compatibility imports."""
    issues = []
    for node in ast.walk(owner_tree):
        if isinstance(node, ast.Import):
            if any(alias.name not in allowed_imports for alias in node.names):
                issues.append("unexpected_policy_import")
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module not in allowed_imports:
                issues.append("unexpected_policy_import")
    imported = {
        alias.name for node in consumer_tree.body
        if isinstance(node, ast.ImportFrom) and not node.level and node.module == module
        for alias in node.names if alias.asname in (None, alias.name)
    }
    if names - imported:
        issues.append("missing_consumer_exports")
    if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
           and node.name in names for node in consumer_tree.body):
        issues.append("duplicate_consumer_logic")
    return sorted(set(issues))


def check_boundary(root, package_report):
    """Purely structural result; no production state or external caller claims."""
    root = Path(root)
    issues = []
    summary = package_report.get("summary", {})
    for field in ("unclassified_paths", "catalogue_paths_missing",
                  "invalid_catalog_entries", "identity_failures"):
        if package_report.get(field):
            issues.append("package_inventory:" + field)
    if summary.get("unclassified") != 0:
        issues.append("package_inventory:unclassified_count")
    if summary.get("total_tracked_package_files") != (
        summary.get("canonical_domain_owned", -1)
        + summary.get("legacy_preserved", -1)
    ):
        issues.append("package_inventory:count_mismatch")
    if package_report.get("external_callers_verified") is not False:
        issues.append("package_inventory:external_caller_status_changed")
    if package_report.get("full_runtime_verified") is not False:
        issues.append("package_inventory:runtime_status_changed")

    trees = {}
    for path, names in CONTRACTS.items():
        tree, errors = inspect_module(root / path, names)
        issues.extend(path + ":" + err for err in errors)
        if tree is not None:
            trees[path] = tree

    root_tree = trees.get("TCFMain.py")
    if root_tree is not None:
        for function in root_tree.body:
            if isinstance(function, ast.FunctionDef) and function.name in ROOT_STAGE_TIMING:
                default = function.args.defaults[-1] if function.args.defaults else None
                if not isinstance(default, ast.Constant) or default.value is not None:
                    issues.append("root_mutable_timing_default:" + function.name)

    filter_tree = trees.get("BertScript/visualization_filter.py")
    if filter_tree is not None and any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        for node in ast.walk(filter_tree)
    ):
        issues.append("stage4_filter_runtime_import")

    app_path = root / "BertScript/Test_result_Vis.py"
    app_tree, app_errors = inspect_module(app_path, set())
    issues.extend("BertScript/Test_result_Vis.py:" + x for x in app_errors)
    if app_tree is not None:
        expected = CONTRACTS["BertScript/visualization_filter.py"]
        imported = {
            alias.name for node in app_tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "BertScript.visualization_filter"
            for alias in node.names
        }
        if expected - imported:
            issues.append("stage4_filter_missing_entrypoint_exports")
        duplicates = {
            node.name for node in app_tree.body
            if isinstance(node, ast.FunctionDef) and node.name in expected
        }
        if duplicates:
            issues.append("stage4_filter_duplicate_entrypoint_logic")

    if app_tree is not None:
        trees["BertScript/Test_result_Vis.py"] = app_tree
    for path, (consumer, allowed_imports) in STAGE4_POLICY_OWNERS.items():
        if path in trees and consumer in trees:
            module = path[:-3].replace("/", ".")
            issues.extend(path + ":" + issue for issue in check_policy_owner(
                trees[path], trees[consumer], module, CONTRACTS[path], allowed_imports))
        # Callback-state compatibility exports must not become duplicated
        # implementations in the main Dash entrypoint either.
        if path == "BertScript/visualization_callback_state.py" and app_tree is not None:
            if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                   and node.name in CONTRACTS[path] for node in app_tree.body):
                issues.append(path + ":duplicate_dash_entrypoint_logic")

    issues = sorted(set(issues))
    return {
        "status": ("PASS_STRUCTURAL_BOUNDARIES_EXTERNAL_GATES_PENDING"
                   if not issues else "BLOCKED_STRUCTURAL_BOUNDARIES"),
        "scope": "Git-tracked static code and ownership; no runtime validation",
        "issues": issues,
        "structural_evidence": {
            "tracked_package_files": summary.get("total_tracked_package_files"),
            "domain_owned": summary.get("canonical_domain_owned"),
            "legacy_compatibility_and_assets": summary.get("legacy_preserved"),
            "covered_boundary_modules": len(CONTRACTS),
        },
        "external_acceptance": dict(EXTERNAL_ACCEPTANCE),
        "external_callers_verified": False,
        "production_workpool_verified": False,
        "real_gui_verified": False,
        "model_gpu_verified": False,
        "deployment_authorized": False,
        "bl001_formally_done": False,
    }


def audit(root=ROOT):
    root = Path(root)
    return check_boundary(root, audit_package(root))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report["status"])
    return 0 if not report["issues"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
