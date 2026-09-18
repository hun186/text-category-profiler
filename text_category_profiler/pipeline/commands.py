"""Pure specifications for the root pipeline's legacy shell commands."""

from dataclasses import dataclass
from typing import Tuple


def _forwarded_args(args) -> str:
    """Render the canonical Namespace order without loading runtime utilities."""
    return "".join(
        f" --{key} {value}"
        for key, value in vars(args).items()
        if value != ""
    )


@dataclass(frozen=True)
class StageCommand:
    """A legacy shell command whose rendering is intentionally unescaped."""

    stage: str
    executable: str
    script: str
    forwarded_args: str
    suffixes: Tuple[str, ...] = ()

    def render_shell(self) -> str:
        return f"{self.executable} {self.script}{self.forwarded_args}{''.join(self.suffixes)}"


def dataset_command(args, args_renderer=_forwarded_args) -> StageCommand:
    return StageCommand(
        stage="DataConverter",
        executable="python",
        script="DatasetConverter/DataConverter.py",
        forwarded_args=args_renderer(args),
    )


def classifier_command(
    args, bert_classifier_path="BertScript", args_renderer=_forwarded_args
) -> StageCommand:
    return StageCommand(
        stage="RunClassfier",
        executable="python",
        script=f"{bert_classifier_path}/RunClassfier.py",
        forwarded_args=args_renderer(args),
    )


def combine_command(
    args, bert_classifier_path="BertScript", args_renderer=_forwarded_args
) -> StageCommand:
    return StageCommand(
        stage="CombineTestResult",
        executable="python",
        script=f"{bert_classifier_path}/CombineTestResult.py",
        forwarded_args=args_renderer(args),
    )


def visualization_command(
    args, bert_classifier_path="BertScript", args_renderer=_forwarded_args
) -> StageCommand:
    return StageCommand(
        stage="Test_result_Vis",
        executable="python",
        script=f"{bert_classifier_path}/Test_result_Vis.py",
        forwarded_args=args_renderer(args),
    )
