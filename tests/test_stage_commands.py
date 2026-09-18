import argparse
from dataclasses import FrozenInstanceError
import unittest

from text_category_profiler.pipeline.commands import (
    StageCommand,
    classifier_command,
    combine_command,
    dataset_command,
    visualization_command,
)


def forwarding_args(**overrides):
    values = dict(
        train=False,
        test=True,
        task="BDS",
        FixedTestFileBound=0,
        optional=None,
        modelDir="directory with spaces",
        WeiTechFormatInputPATH="",
        WeiTechFormatOutputPATH="",
        WeiTechFormatSepWorkPool=False,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


FORWARDED = (
    " --train False --test True --task BDS --FixedTestFileBound 0"
    " --optional None --modelDir directory with spaces"
    " --WeiTechFormatSepWorkPool False"
)


class StageCommandTests(unittest.TestCase):
    def test_stage_command_is_frozen_and_renders_literal_components(self):
        command = StageCommand(
            stage="example", executable="python", script="stage.py",
            forwarded_args=" --flag False", suffixes=(" -extra 0",),
        )
        self.assertEqual(
            "python stage.py --flag False -extra 0", command.render_shell()
        )
        with self.assertRaises(FrozenInstanceError):
            command.stage = "changed"

    def test_dataset_command_matches_characterized_shell_string(self):
        self.assertEqual(
            "python DatasetConverter/DataConverter.py" + FORWARDED,
            dataset_command(forwarding_args()).render_shell(),
        )

    def test_classifier_command_matches_characterized_shell_string(self):
        self.assertEqual(
            "python BertScript/RunClassfier.py" + FORWARDED,
            classifier_command(forwarding_args()).render_shell(),
        )

    def test_combine_command_matches_characterized_shell_string(self):
        self.assertEqual(
            "python BertScript/CombineTestResult.py" + FORWARDED,
            combine_command(forwarding_args()).render_shell(),
        )

    def test_visualization_command_forwards_namespace_once(self):
        command = visualization_command(forwarding_args())
        self.assertEqual(
            "python BertScript/Test_result_Vis.py" + FORWARDED,
            command.render_shell(),
        )

    def test_visualization_command_forwards_weitech_options(self):
        args = forwarding_args(
            WeiTechFormatInputPATH="input path",
            WeiTechFormatOutputPATH="output path",
            WeiTechFormatSepWorkPool="separate pool",
        )
        forwarded = (
            " --train False --test True --task BDS --FixedTestFileBound 0"
            " --optional None --modelDir directory with spaces"
            " --WeiTechFormatInputPATH input path"
            " --WeiTechFormatOutputPATH output path"
            " --WeiTechFormatSepWorkPool separate pool"
        )
        command = visualization_command(args)
        self.assertEqual(
            "python BertScript/Test_result_Vis.py" + forwarded,
            command.render_shell(),
        )


if __name__ == "__main__":
    unittest.main()
