"""DatasetConverter stage planning and runtime activation.

This module owns the boundary between dependency-light CLI/configuration
normalization and side-effecting directory/logger activation.  The canonical
``DataConverter.py`` entrypoint re-exports these names for legacy callers.
"""

import argparse
import time
from dataclasses import dataclass

from DatasetConverter.adapters.pipeline_source import fixed_test_paths
from DatasetConverter.adapters.pipeline_source import parse_converter_options
from DatasetConverter.adapters.pipeline_source import pick_dataset_directories
from DatasetConverter.adapters.runtime_source import create_logger
from DatasetConverter.config import ConfigValidationError
from DatasetConverter.config import ConverterConfig
from DatasetConverter.config import DEFAULT_RUNTIME_CONFIG
from DatasetConverter.config import ModeConfig
from DatasetConverter.config import OutputConfig
from DatasetConverter.config import RuntimeConfig
from DatasetConverter.config import SourceConfig
from DatasetConverter.config import WORK_POOL_ROOT
from DatasetConverter.config import WorkspaceConfig
from DatasetConverter.config import mode_config_from_namespace
from DatasetConverter.config import source_config_from_namespace
from DatasetConverter.config import workspace_config_from_namespace
from DatasetConverter.core.stage_utils import make_directory
from text_category_profiler.core.log_display import info
from text_category_profiler.core.log_display import key_values
from text_category_profiler.core.log_display import stage_banner
from text_category_profiler.core.log_display import summarize_sequence


@dataclass(frozen=True)
class StagePlan:
    """Normalized stage inputs produced before filesystem/logger activation."""

    args: argparse.Namespace
    converter_config: ConverterConfig
    source_config: SourceConfig
    output_config: OutputConfig
    mode_config: ModeConfig
    workspace_config: WorkspaceConfig

    @property
    def work_directory(self) -> str:
        return self.output_config.dataset_directory

    @property
    def converter_settings(self) -> dict:
        """Return a mutable legacy mapping for downstream compatibility."""
        return self.converter_config.as_legacy_mapping()

    @property
    def root_paths(self) -> list[str]:
        """Return a legacy-compatible copy of configured training roots."""
        return list(self.source_config.root_paths)

    @property
    def fixed_test_paths(self) -> list[str]:
        """Return a legacy-compatible copy of configured fixed-test roots."""
        return list(self.source_config.fixed_test_paths)


@dataclass(frozen=True)
class StageContext:
    """Activated runtime state owned by one stage run."""

    args: argparse.Namespace
    converter_config: ConverterConfig
    source_config: SourceConfig
    output_config: OutputConfig
    runtime_config: RuntimeConfig
    mode_config: ModeConfig
    workspace_config: WorkspaceConfig
    logger: object
    tcf_main_logger: object
    stage_start_time: float

    @property
    def converter_settings(self) -> dict:
        return self.converter_config.as_legacy_mapping()

    @property
    def root_paths(self) -> list[str]:
        return list(self.source_config.root_paths)

    @property
    def fixed_test_paths(self) -> list[str]:
        return list(self.source_config.fixed_test_paths)


def normalize_stage_plan(converter_settings, argv=None):
    """Normalize CLI and source settings without creating files or loggers."""
    args = parse_converter_options(argv)
    args.BertDatasetSubDir, _ = pick_dataset_directories(
        args=args,
        ready_for_stage="DataConverter",
    )
    dataset_directory = args.BertDatasetSubDir + "_is_running_DataConverter"
    args.BertDatasetSubDir = dataset_directory

    if args.FixedTestPATH == "" and args.test is True:
        configured_fixed_test_paths = fixed_test_paths(args)
    else:
        configured_fixed_test_paths = [args.FixedTestPATH]
    if args.WeiTechFormatInputPATH != "":
        configured_fixed_test_paths.append(args.WeiTechFormatInputPATH)

    if args.test is False:
        args.FixedTestPATH = ""
    source_config = source_config_from_namespace(
        args,
        fixed_test_paths=tuple(configured_fixed_test_paths),
    )
    converter_config = ConverterConfig.from_legacy_settings(
        converter_settings,
        fixed_test_file_bound=args.FixedTestFileBound,
    )
    output_config = OutputConfig(
        dataset_directory=dataset_directory,
        database_subdirectory=args.datasetDataBaseSubDir,
    )
    mode_config = mode_config_from_namespace(args, source_config)
    workspace_config = workspace_config_from_namespace(args, mode_config)
    return StagePlan(
        args=args,
        converter_config=converter_config,
        source_config=source_config,
        output_config=output_config,
        mode_config=mode_config,
        workspace_config=workspace_config,
    )


def activate_stage_context(plan, runtime_config=DEFAULT_RUNTIME_CONFIG):
    """Create stage directories, loggers, and timing state for a normalized plan."""
    if not isinstance(runtime_config, RuntimeConfig):
        raise ConfigValidationError("runtime_config must be a RuntimeConfig")
    args = plan.args
    stage_banner("DataConverter", detail=f"WorkDir: {plan.work_directory}")
    message = f"DataConveter started. WorkDir is {plan.work_directory}."
    make_directory(WORK_POOL_ROOT)
    make_directory(plan.work_directory)
    logger = create_logger(logSubDir=f"{plan.work_directory}/logs")
    tcf_main_logger = create_logger(
        logSubDir=f"{plan.work_directory}/logs",
        logFile="TCFMain.log",
    )
    tcf_main_logger.logW(message)
    if args.test is False:
        info("Since args.test is False, set args.FixedTestPATH=''", icon="🧪")
    else:
        key_values(
            "Fixed test detection",
            [
                ("TRVPort", args.TRVPort),
                (
                    "FixedTestPATHList",
                    summarize_sequence(plan.fixed_test_paths, limit=4),
                ),
            ],
            icon="·",
        )
    return StageContext(
        args=args,
        converter_config=plan.converter_config,
        source_config=plan.source_config,
        output_config=plan.output_config,
        runtime_config=runtime_config,
        mode_config=plan.mode_config,
        workspace_config=plan.workspace_config,
        logger=logger,
        tcf_main_logger=tcf_main_logger,
        stage_start_time=time.time(),
    )


def setArguments(converter_settings, argv=None):
    """Compatibility wrapper for callers that expect immediate activation."""
    return activate_stage_context(normalize_stage_plan(converter_settings, argv=argv))
