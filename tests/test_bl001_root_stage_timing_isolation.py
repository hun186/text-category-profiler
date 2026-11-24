"""BL-001: root standalone stages must not share default timing state."""
import inspect
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest

from tests.test_tcf_main_characterization import default_args, load_main


STAGES = ("DataConvert", "RunClassfier", "CombineTestResult", "TestResultVis",
          "ArticleAnalysis")


class RootStageTimingIsolationTests(unittest.TestCase):
    def test_each_public_stage_has_nonmutable_optional_default(self):
        module = load_main()
        for name in STAGES:
            with self.subTest(stage=name):
                func = getattr(module, name)
                self.assertEqual(inspect.signature(func).parameters["exeTimeDict"].default,
                                 None)
                self.assertEqual(func.__defaults__, (None,))

    def test_omitted_timing_map_is_fresh_on_consecutive_stage_invocations(self):
        with TemporaryDirectory() as temp:
            args = default_args(_dataset_dir=temp, _output_dir=temp,
                                TRVWebHost=True, train=False)
            module = load_main(args)
            ticks = count(1000)
            module.time = types.SimpleNamespace(time=lambda: next(ticks))
            observed = []
            module.ShowElapsedTime = observed.append
            module.run_stage_command = lambda command, stage_name: None

            for name in STAGES[:-1]:
                with self.subTest(stage=name):
                    observed.clear()
                    getattr(module, name)(args)
                    getattr(module, name)(args)
                    self.assertEqual(len(observed), 2)
                    self.assertIsInstance(observed[0], int)
                    self.assertLess(observed[0], observed[1])

    def test_article_analysis_omitted_timing_shares_within_run_not_across_runs(self):
        args = default_args(TRVWebHost=True, task="")
        module = load_main(args)
        ticks = count(1000)
        module.time = types.SimpleNamespace(time=lambda: next(ticks))
        observations = []

        def combine(_args, exeTimeDict):
            observations.append(("combine", exeTimeDict,
                                 "prior_run" in exeTimeDict))
            exeTimeDict["prior_run"] = True

        def visualize(_args, exeTimeDict):
            observations.append(("vis", exeTimeDict,
                                 "prior_run" in exeTimeDict))

        module.CombineTestResult = combine
        module.TestResultVis = visualize
        module.BackupAndClean = lambda _args: None
        module.ArticleAnalysis(args)
        module.ArticleAnalysis(args)
        self.assertEqual([name for name, *_ in observations],
                         ["combine", "vis", "combine", "vis"])
        self.assertIs(observations[0][1], observations[1][1])
        self.assertIs(observations[2][1], observations[3][1])
        self.assertIsNot(observations[0][1], observations[2][1])
        self.assertEqual([x[2] for x in observations],
                         [False, True, False, True])
        self.assertIn("start", observations[0][1])
        self.assertIn("start", observations[2][1])

    def test_explicit_timing_map_preserves_identity_and_no_implicit_reset(self):
        module = load_main()
        supplied = {"start": 41, "custom": object()}
        self.assertIs(module._stage_timing(supplied), supplied)
        self.assertEqual(module._stage_timing(supplied)["start"], 41)
        for name in STAGES:
            with self.subTest(stage=name):
                self.assertEqual(getattr(module, name).__defaults__, (None,))

    def test_missing_start_in_explicit_map_is_not_silently_filled(self):
        module = load_main()
        supplied = {"custom": "intentionally incomplete"}
        self.assertIs(module._stage_timing(supplied), supplied)
        self.assertNotIn("start", supplied)


if __name__ == "__main__":
    unittest.main()
