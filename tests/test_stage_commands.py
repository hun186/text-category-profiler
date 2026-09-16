import argparse
from dataclasses import FrozenInstanceError
import unittest

from text_category_profiler.pipeline.commands import (
    StageCommand,
    classifier_command,
    combine_command,
    dataset_command,
    visualization_commands,
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

    def test_visualization_commands_preserve_empty_path_false_suffix_behavior(self):
        commands = visualization_commands(forwarding_args())
        self.assertIsInstance(commands, tuple)
        self.assertEqual(2, len(commands))
        base = "python BertScript/Test_result_Vis.py" + FORWARDED
        self.assertEqual(base, commands[0].render_shell())
        self.assertEqual(
            base + " -WTFSepWorkPool False", commands[1].render_shell()
        )

    def test_visualization_suffixes_keep_alias_order_and_unquoted_spaces(self):
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
        commands = visualization_commands(args)
        self.assertEqual(
            "python BertScript/Test_result_Vis.py" + forwarded,
            commands[0].render_shell(),
        )
        self.assertEqual(
            "python BertScript/Test_result_Vis.py" + forwarded
            + " -WTFInpPath input path -WTFOptPath output path"
            + " -WTFSepWorkPool separate pool",
            commands[1].render_shell(),
        )


if __name__ == "__main__":
    unittest.main()
