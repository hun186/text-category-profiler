"""Dependency-light lifecycle boundary for the classifier stage.

The legacy entrypoint supplies the ML-specific preparation callback.  The
objects in this module deliberately keep planning separate from activation so
that directory and shell policies can be characterized without loading a
model runtime.
"""
from dataclasses import dataclass
import os
import platform
from typing import Callable, Optional, Sequence


READY_SUFFIX = "_rdy_for_RunClassfier"
RUNNING_SUFFIX = "_is_running_RunClassfier"
NEXT_SUFFIX = "_rdy_for_CombineTestResult"
PYTORCH_SCRIPT = "TextClassification_transformers.py"


@dataclass(frozen=True)
class ClassifierPlan:
    args: object
    dataset_dir: str
    output_dir: str
    command: str
    model_kind: str
    batch_file: Optional[str] = None
    activation_command: Optional[str] = None


def render_pytorch_command(args, dataset_dir, output_dir, classifier_path):
    command = f"python {classifier_path}/{PYTORCH_SCRIPT}"
    if args.train is True:
        command += " -tr True"
    if args.test is True:
        command += " -ts True"
    command += (f" -mdlDir {output_dir} -BertDataDir {dataset_dir}"
                f" -mdlType {args.ModelType} -ZeroShot {args.ActiveHTCZeroshot}"
                f" -MaxSeqLen {args.MaxSeqLength} -SaveOptimizer {args.SaveOptimizer} ")
    run_log = os.path.join(dataset_dir, "logs", "RunClassfier.log")
    command += f'> "{run_log}" 2>&1'
    if args.train is True:
        command += " &"
    return command + " \n\n"


def render_tf_command(args, dataset_dir, output_dir, template, windows=False):
    line_breaker = " ^\n" if windows else " \\\n"
    command = ("call activate TF1.5\n\n" + template) if windows else template.replace("^\n", "\\\n")
    command += ("--do_train=True" if args.train is True else "--do_train=False") + line_breaker
    command += f"--output_dir={output_dir}/ {line_breaker}"
    command += f"--do_predict={args.test}" + line_breaker
    command += f"--keep_checkpoint_max={args.keep_checkpoint_max}" + line_breaker
    command += f"--data_dir={dataset_dir}/ {line_breaker}"
    run_log = os.path.join(dataset_dir, "logs", "RunClassfier.log")
    command += f'> "{run_log}" 2>&1'
    if args.train is True:
        command += " &"
    return command + " \n\n"


def activate_classifier(plan, rename=os.rename):
    running = plan.dataset_dir.replace(READY_SUFFIX, RUNNING_SUFFIX)
    rename(plan.dataset_dir, running)
    return ClassifierPlan(plan.args, running, plan.output_dir,
                          plan.command.replace(plan.dataset_dir, running),
                          plan.model_kind, plan.batch_file,
                          plan.activation_command)


def run_classifier_stage(plan, *, system=os.system,
                         wait_until_stable=lambda path, **kwargs: None,
                         result_files: Sequence[str] = (), rename=os.rename,
                         warn=lambda message: None, prepare=None,
                         finalize=lambda active: None, handoff=None):
    """Activate and execute while retaining each legacy call-site policy."""
    active = activate_classifier(plan, rename=rename)
    if prepare is not None:
        prepared = prepare(active)
        active = prepared.get("plan", active)
        result_files = prepared.get("result_files", result_files)
        finalize = prepared.get("finalize", finalize)
        wait_until_stable = prepared.get("wait_until_stable", wait_until_stable)
    if active.model_kind == "tf":
        if active.activation_command:
            system(active.activation_command)       # non-zero intentionally ignored
        if active.batch_file and "windows" not in platform.system().lower():
            system(f"chmod 700 {active.batch_file}")  # non-zero intentionally ignored
        batch_command = active.batch_file or active.command
        if active.batch_file and "windows" not in platform.system().lower():
            batch_command = "." + os.path.sep + active.batch_file
        system(batch_command)  # exceptions intentionally propagate
    else:
        try:
            system(active.command)                  # non-zero intentionally ignored
        except Exception as exc:
            warn(f"RunClassfier command failed: {exc}")
    if active.args.test is True:
        for filename in result_files:
            wait_until_stable(filename)
        finalize(active)
        destination = active.dataset_dir.replace(RUNNING_SUFFIX, NEXT_SUFFIX)
        (handoff or rename)(active.dataset_dir, destination)
        return destination
    return active.dataset_dir


def main(argv=None, legacy_main: Optional[Callable] = None):
    """Compatibility composition hook used by ``RunClassfier.py``."""
    if legacy_main is None:
        raise RuntimeError("classifier computation adapter is required")
    return legacy_main(argv)
