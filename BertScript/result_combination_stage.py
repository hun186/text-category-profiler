"""Lifecycle boundary for Stage 3 result combination."""
from dataclasses import dataclass
import os
from typing import Callable, Optional

READY_SUFFIX = "_rdy_for_CombineTestResult"
RUNNING_SUFFIX = "_is_running_CombineTestResult"
NEXT_SUFFIX = "_rdy_for_TestResultVis"
SOURCE_DB_GLOB = r"dataset_total_with_filename.*\.sql3"


@dataclass(frozen=True)
class ResultCombinationPlan:
    args: object
    dataset_dir: str
    output_dir: str
    source_db_glob: str = SOURCE_DB_GLOB
    label_file: str = "TopicAnalysis_LabelList.txt"
    test_database: str = "test.sql3"
    result_file: str = "test_results.tsv"


def activate_result_combination(plan, rename=os.rename):
    # Only a precise basename READY suffix is eligible for acquisition.
    # Never replace a similarly named parent directory or an arbitrary path.
    if not isinstance(plan.dataset_dir, str):
        raise ValueError("COMBINE_ACTIVATION_INVALID_READY_STATE")
    # The picker may retain a trailing separator. Strip only that suffix;
    # normpath would also rewrite existing '/' spelling to '\\' on Windows,
    # breaking the caller's returned-path contract.
    ready = plan.dataset_dir.rstrip("/\\")
    if not os.path.basename(ready).endswith(READY_SUFFIX):
        raise ValueError("COMBINE_ACTIVATION_INVALID_READY_STATE")
    running = ready[:-len(READY_SUFFIX)] + RUNNING_SUFFIX
    rename(ready, running)
    return ResultCombinationPlan(
        plan.args, running, plan.output_dir, plan.source_db_glob,
        plan.label_file, plan.test_database, plan.result_file)


def run_result_combination_stage(plan, *, combine: Callable,
                                 rename=None, activate_rename=None,
                                 success_handoff=None,
                                 warn=lambda message: None):
    activation = activate_rename or rename or os.rename
    completion = success_handoff or rename or os.rename
    active = activate_result_combination(plan, rename=activation)
    database_dir = os.path.join(active.dataset_dir,
                                active.args.datasetDataBaseSubDir)
    try:
        combine(active, database_dir)
    except Exception:
        # Deliberately leave the directory in its running state.
        raise
    # Activation above produced an exact terminal RUNNING suffix. Compute
    # the next-stage destination without replacing substrings in parent paths.
    destination = active.dataset_dir[:-len(RUNNING_SUFFIX)] + NEXT_SUFFIX
    completion(active.dataset_dir, destination)
    return destination


def main(argv=None, legacy_main: Optional[Callable] = None):
    if legacy_main is None:
        raise RuntimeError("result-combination computation adapter is required")
    return legacy_main(argv)
