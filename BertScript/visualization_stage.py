"""Dependency-light planning and lifecycle boundary for Stage 4."""

from dataclasses import dataclass
import os
from pathlib import Path
import platform
from typing import Callable, Optional

from text_category_profiler.execution.process import (
    sanitize_windows_dot_path as sanitize_tulip_windows_dot_path,
    preflight_windows_dll_path as preflight_tulip_windows_path,
)


READY_SUFFIX = "_rdy_for_TestResultVis"
RUNNING_SUFFIX = "_is_running_TestResultVis"
NEXT_SUFFIX = "_rdy_for_Spike"


@dataclass(frozen=True)
class VisualizationPlan:
    ready_workspace: str
    output_dir: str
    hosted: bool
    host: str
    port: int
    weitech_separate_work_pool: bool
    weitech_input_path: str
    weitech_output_path: str
    ssl_context: Optional[str]
    debug: bool = True
    use_reloader: bool = False

    @property
    def running_workspace(self):
        return _replace_suffix(self.ready_workspace, READY_SUFFIX, RUNNING_SUFFIX)

    @property
    def completed_workspace(self):
        return _replace_suffix(self.running_workspace, RUNNING_SUFFIX, NEXT_SUFFIX)

    @property
    def process_name(self):
        return "TRV{}".format(self.port)


def build_visualization_plan(args, ready_workspace, output_dir):
    """Normalize execution intent without mutating the filesystem."""
    return VisualizationPlan(
        ready_workspace=ready_workspace,
        output_dir=output_dir,
        hosted=args.TRVWebHost,
        host="0.0.0.0" if args.public else "127.0.0.1",
        port=args.TRVPort,
        weitech_separate_work_pool=args.WeiTechFormatSepWorkPool,
        weitech_input_path=args.WeiTechFormatInputPATH,
        weitech_output_path=args.WeiTechFormatOutputPATH,
        ssl_context=None if "windows" in platform.system().lower() else "adhoc",
    )


def _stage4_move_noreplace(source, destination):
    """Transition Stage 4 without replacing any existing work directory.

    Only the exact ready -> running or running -> completed states are legal.
    The shared cross-platform no-replace primitive is imported on demand so
    pure planning, diagnostics and read-only viewers stay dependency-light.
    """
    source_path, destination_path = Path(source), Path(destination)
    transitions = (
        (READY_SUFFIX, RUNNING_SUFFIX),
        (RUNNING_SUFFIX, NEXT_SUFFIX),
    )
    if not any(
            source_path.name.endswith(old_suffix)
            and destination_path == source_path.with_name(
                source_path.name[:-len(old_suffix)] + new_suffix)
            for old_suffix, new_suffix in transitions):
        raise ValueError("VISUALIZATION_INVALID_STAGE_TRANSITION")

    from text_category_profiler.pipeline.TCF_utils import (
        _handoff_rename_noreplace, _is_link_or_reparse,
    )
    if not source_path.is_dir() or _is_link_or_reparse(source_path):
        raise FileNotFoundError("VISUALIZATION_SOURCE_NOT_A_DIRECTORY")
    # lexists also protects dangling symlinks and Windows junctions.
    if os.path.lexists(destination):
        raise FileExistsError("VISUALIZATION_DESTINATION_ALREADY_EXISTS")
    _handoff_rename_noreplace(source, destination)
    # EXDEV copy/removal may have failed partway. Do not run the application
    # or proclaim completion while both names still exist.
    if (os.path.lexists(source)
            or not destination_path.is_dir()
            or _is_link_or_reparse(destination_path)):
        raise RuntimeError("VISUALIZATION_STAGE_MOVE_INCOMPLETE")


def activate_visualization(plan, rename=None):
    move = _stage4_move_noreplace if rename is None else rename
    move(plan.ready_workspace, plan.running_workspace)
    return plan.running_workspace


def run_visualization_stage(
        plan,
        *,
        rename=None,
        application: Callable[[str], None],
        start_server: Callable[[VisualizationPlan], None],
        validate: Callable[[str], bool]):
    """Activate, execute, validate, and complete the visualization stage."""
    move = _stage4_move_noreplace if rename is None else rename
    running_workspace = activate_visualization(plan, rename=move)
    application(running_workspace)
    if plan.hosted:
        start_server(plan)
    if not validate(running_workspace):
        raise RuntimeError("Visualization stage output validation failed")
    move(running_workspace, plan.completed_workspace)
    return plan.completed_workspace


def run_summary_command(command, invoke):
    """Invoke summarization without translating status codes or exceptions."""
    return invoke(command)



# Retain the public visualization_stage names for existing callbacks and tests.
# Their pure implementation belongs to a Stage 4 callback policy module.
from BertScript.visualization_callback_state import (
    is_spurious_datatable_filter_notification,
    datatable_filter_state,
    is_redundant_table_filter_event,
    is_redundant_table_page_event,
)


def import_dash_runtime(import_module=None):
    """Import Dash with a targeted diagnostic for legacy Jupyter comm errors.

    Dash may initialize optional notebook comms even in a standalone CLI.
    Older comm distributions raise NotImplementedError("Cannot ") there.
    Upgrade the environment dependency; do not monkeypatch third-party code.
    """
    if import_module is None:
        from importlib import import_module

    try:
        return import_module("dash")
    except NotImplementedError as exc:
        if str(exc).strip() != "Cannot":
            raise
        raise RuntimeError(
            "Dash import failed while initializing Jupyter comm in the active "
            "Python environment. Install a compatible comm package with "
            'python -m pip install --upgrade "comm>=0.2.3" using the SAME '
            "Python interpreter used to run TCFMain.py; then verify with "
            'python -c "import dash; print(dash.__version__)". '
            "This is an environment dependency failure, not a classifier "
            "or output-merge failure."
        ) from exc


def _replace_suffix(path, old_suffix, new_suffix):
    # Pickers and explicit -VisDir may preserve trailing separators. Remove
    # only those; normpath also rewrites '/' spelling to '\\' on Windows and
    # breaks existing callback/path contracts using forward slashes.
    if not isinstance(path, str):
        raise ValueError("stage path must be a string")
    normalized = path.rstrip("/\\")
    if not os.path.basename(normalized).endswith(old_suffix):
        raise ValueError("{} does not end with {}".format(path, old_suffix))
    return normalized[:-len(old_suffix)] + new_suffix
