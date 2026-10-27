"""Dependency-light planning and lifecycle boundary for Stage 4."""

from dataclasses import dataclass
import os
import platform
from typing import Callable, Optional


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


def activate_visualization(plan, rename=os.rename):
    rename(plan.ready_workspace, plan.running_workspace)
    return plan.running_workspace


def run_visualization_stage(
        plan,
        *,
        rename=os.rename,
        application: Callable[[str], None],
        start_server: Callable[[VisualizationPlan], None],
        validate: Callable[[str], bool]):
    """Activate, execute, validate, and complete the visualization stage."""
    running_workspace = activate_visualization(plan, rename=rename)
    application(running_workspace)
    if plan.hosted:
        start_server(plan)
    if not validate(running_workspace):
        raise RuntimeError("Visualization stage output validation failed")
    rename(running_workspace, plan.completed_workspace)
    return plan.completed_workspace


def run_summary_command(command, invoke):
    """Invoke summarization without translating status codes or exceptions."""
    return invoke(command)



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
    if not path.endswith(old_suffix):
        raise ValueError("{} does not end with {}".format(path, old_suffix))
    return path[:-len(old_suffix)] + new_suffix
