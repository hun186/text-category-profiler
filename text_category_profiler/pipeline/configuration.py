"""Root pipeline configuration planning and explicit runtime activation."""

import argparse
import copy
import os
import platform
import sys
from dataclasses import dataclass
from typing import Callable, Optional


BASE_FINAL_OUTPUT_PATTERNS = (
    "^DFPreambleCols_df_ALL.*",
    "dataset_total_with_filename_FixedTest.sql3",
    "test.sql3",
    "test.tsv",
)


@dataclass(frozen=True)
class PipelinePlan:
    """Normalized, run-owned inputs produced without runtime activation."""

    args: argparse.Namespace
    root_paths: tuple
    final_output_patterns: tuple
    run_mode: str
    n_process_explicit: bool
    n_process_spc_explicit: bool


@dataclass(frozen=True)
class PipelineContext:
    """One activated root pipeline run."""

    args: argparse.Namespace
    root_paths: tuple
    final_output_patterns: tuple
    run_mode: str


class LocalFileSystem:
    def rename(self, source, destination):
        os.rename(source, destination)

    def make_directory(self, path):
        from text_category_profiler.core.utilities import MKDIR
        MKDIR(path)


def _default_parser(argv):
    from text_category_profiler.pipeline.TCF_utils import ClassfierOptionParser
    return ClassfierOptionParser(argv)


def _default_clock():
    from text_category_profiler.core.utilities import timeNow
    return timeNow()


def _default_process_source():
    from text_category_profiler.concurrency.MP_utils import multicoreJob
    return multicoreJob()


def process_option_explicit(argv, aliases):
    """Return whether one of ``aliases`` occurs in the effective CLI input."""
    values = sys.argv[1:] if argv is None else argv
    return any(value in aliases for value in values)


def resolve_process_counts(args, argv, process_source):
    """Preserve explicit CLI counts and auto-detect only omitted counts."""
    worker_explicit = process_option_explicit(argv, ("-nProc", "--nProcess"))
    large_explicit = process_option_explicit(
        argv, ("-nProcSPC", "--nProcessSPC")
    )
    workers = args.nProcess if worker_explicit else process_source.ComputeNProcess()
    large = (
        args.nProcessSPC
        if large_explicit
        else process_source.ComputeSPCNProcess()
    )
    return workers, large


def _root_path_policy(args, platform_value):
    if args.debugMode is True:
        return ("TopicTextCrawler/TrainSamples",), "debug"
    if args.TrainDRNDataOnly is True:
        return ("===DRNData",), "TrainDRNDataOnly"
    if "linux" in platform_value.lower():
        roots = [
            "News/THUCNews", "News/AFPBB", "News/HuffPost", "Kaggle",
            "BigDataWarehouse", "===DRNData", "Books", "C_GoogleSearch",
            "C_wikisourcePortal",
        ]
        run_mode = "linux"
        if args.trainWithMaliciousDomainDataset is True:
            roots.append("惡意網址分析")
            run_mode += "+trainWithMaliciousDomainDataset"
        return tuple(roots), run_mode
    return ("TrainSamples",), "debug"


def build_pipeline_plan(
    argv=None,
    *,
    parser: Callable = _default_parser,
    clock: Callable = _default_clock,
    platform_name: Callable = platform.system,
    filesystem=None,
    process_source=None,
):
    """Parse and normalize a plan without filesystem/process activation.

    ``filesystem`` and ``process_source`` are accepted as guard dependencies so
    callers can prove they are not consulted during planning.
    """
    del filesystem, process_source
    args = copy.deepcopy(parser(argv))
    args.WeiTechworkIDPath = args.WeiTechworkIDPath.replace("\\", "/")
    if args.ExecutionTime == "":
        args.ExecutionTime = clock()
    patterns = BASE_FINAL_OUTPUT_PATTERNS
    if args.task in ("SDSMS", "SDSMS_Prediction"):
        args.ExtractionConverterTask = args.task
        patterns = patterns + ("SDSMS.*",)
    root_paths, run_mode = _root_path_policy(args, platform_name())
    return PipelinePlan(
        args=args,
        root_paths=root_paths,
        final_output_patterns=patterns,
        run_mode=run_mode,
        n_process_explicit=process_option_explicit(
            argv, ("-nProc", "--nProcess")
        ),
        n_process_spc_explicit=process_option_explicit(
            argv, ("-nProcSPC", "--nProcessSPC")
        ),
    )


def activate_pipeline_runtime(
    plan,
    *,
    filesystem=None,
    process_source: Optional[Callable] = None,
):
    """Perform filesystem and process discovery for one normalized plan."""
    filesystem = filesystem or LocalFileSystem()
    process_source = process_source or _default_process_source
    args = copy.deepcopy(plan.args)
    if args.WeiTechFormatInputPATH != "":
        original = args.WeiTechFormatInputPATH
        renamed = "{}_{}_is_running_AI".format(original, args.ExecutionTime)
        filesystem.rename(original, renamed)
        filesystem.make_directory(original)
        args.WeiTechFormatInputPATH = renamed
    processes = process_source()
    if not plan.n_process_explicit:
        args.nProcess = processes.ComputeNProcess()
    if not plan.n_process_spc_explicit:
        args.nProcessSPC = processes.ComputeSPCNProcess()
    return PipelineContext(
        args=args,
        root_paths=plan.root_paths,
        final_output_patterns=plan.final_output_patterns,
        run_mode=plan.run_mode,
    )
