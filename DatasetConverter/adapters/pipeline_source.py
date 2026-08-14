"""Feature-activated access to shared pipeline and CLI integrations."""

from typing import Any


def parse_converter_options(argv: list[str] | None = None) -> Any:
    """Parse the shared classifier options when the CLI is executed."""

    from text_category_profiler.pipeline.TCF_utils import ClassfierOptionParser

    return ClassfierOptionParser(argv)


def pick_dataset_directories(*, args: Any, ready_for_stage: str = "") -> Any:
    """Run the legacy dataset/output directory picker."""

    from text_category_profiler.pipeline.TCF_utils import datasetDirOutputDirPickers

    return datasetDirOutputDirPickers(
        args=args,
        rdy_for_stage=ready_for_stage,
    ).proc()


def resolve_base_model_checkpoint(model_type: str) -> str:
    """Resolve the configured fallback model checkpoint."""

    from text_category_profiler.pipeline.TCF_utils import get_base_model_checkpoint

    return get_base_model_checkpoint(model_type)


def restricted_labels(enabled: bool) -> list[str]:
    """Load the legacy restricted-label list only when requested."""

    from text_category_profiler.pipeline.TCF_utils import GetRSTRLabelList

    return GetRSTRLabelList(enabled)


def fixed_test_paths(args: Any) -> list[str]:
    """Discover the configured fixed-test directories at CLI runtime."""

    from text_category_profiler.pipeline.DataConverter_utils import GetFixedTestPATH

    return GetFixedTestPATH(args)


def connect_task(
    *, source_task: str, destination_task: str, working_directory: str, log_file: str
) -> Any:
    """Apply the legacy stage handoff after artifacts are complete."""

    from text_category_profiler.pipeline.TCF_utils import TaskConnector

    return TaskConnector(
        SrcTask=source_task,
        DesTask=destination_task,
        WorkingDir=working_directory,
        logFile=log_file,
    ).proc()
